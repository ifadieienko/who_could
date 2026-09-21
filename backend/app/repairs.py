from types import SimpleNamespace
from copy import deepcopy
from .plans import enforce_limit
import hashlib
import secrets
from datetime import date, timedelta
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from .database import db
from .models import User
from .repair_access import (
    access,
    current_user,
    get_order,
    order_filters,
    event,
    touch,
    utc,
    dt,
)
from .repair_defaults import DEFAULT_FIELDS, DEFAULT_STAGES, DEFAULT_ROLES, PERMISSIONS
from .repair_models import *
from .repair_schemas import *
from .security import hash_password

router = APIRouter(prefix="/v2", tags=["workshops"])


def seed_workshop(s, user, name):
    w = Workshop(name=name, trial_until=utc() + timedelta(days=14))
    s.add(w)
    s.flush()
    for name, (permissions, scope) in DEFAULT_ROLES.items():
        role = WorkshopRole(
            workshop_id=w.id,
            name=name,
            permissions=permissions,
            scope=scope,
            is_owner=name == "owner",
        )
        s.add(role)
        s.flush()
        if name == "owner":
            s.add(Membership(workshop_id=w.id, user_id=user.id, role_id=role.id))
    s.add(
        FormTemplate(
            workshop_id=w.id,
            family=str(uuid4()),
            name="Телефоны и компьютеры",
            revision=1,
            published=True,
            fields=DEFAULT_FIELDS,
            layout={"columns": 2},
        )
    )
    for phase, label, key in [
        ("diagnosis", "Диагностика", "diagnosis"),
        ("repair", "Ремонт", "work_done"),
        ("quality", "Проверка качества", "test_result"),
    ]:
        s.add(
            FormTemplate(
                workshop_id=w.id,
                family=str(uuid4()),
                name=label,
                purpose=phase,
                published=True,
                fields=[
                    {
                        "key": key,
                        "label": label,
                        "type": "text",
                        "required": True,
                        "width": 2,
                    }
                ],
                layout={"columns": 2},
            )
        )
    s.add(
        Workflow(
            workshop_id=w.id,
            family=str(uuid4()),
            name="Стандартный ремонт",
            revision=1,
            stages=DEFAULT_STAGES,
        )
    )
    return w


def scoped(s, cls, id, a):
    x = s.scalar(select(cls).where(cls.id == id, cls.workshop_id == a.workshop_id))
    if not x:
        raise HTTPException(404, "Запись не найдена")
    return x


def visible_fields(o, a):
    return [
        f
        for f in o.template_snapshot.get("fields", [])
        if not f.get("read_permission") or f["read_permission"] in a.permissions
    ]


def normalize_values(s, o, values, a, required=False, required_keys=()):
    fields = o.template_snapshot.get("fields", [])
    by_key = {f["key"]: f for f in fields}
    if set(values) - set(by_key):
        raise HTTPException(422, "Неизвестное поле формы")
    result = dict(o.values or {})
    for key, value in values.items():
        f = by_key[key]
        if value == result.get(key):
            continue
        for p in (f.get("read_permission"), f.get("write_permission")):
            if p and p not in a.permissions and value != result.get(key):
                raise HTTPException(403, "Нет прав на поле " + key)
        if value is None or value == "":
            result[key] = None
            continue
        typ = f["type"]
        if typ in {"string", "text", "select"}:
            if not isinstance(value, str) or len(value) > 10000:
                raise HTTPException(422, "Некорректный текст: " + key)
            value = value.strip()
            if typ == "select" and value not in f.get("options", []):
                raise HTTPException(422, "Недопустимый вариант: " + key)
        elif typ == "number":
            import math

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or abs(value) > 1e12
            ):
                raise HTTPException(422, "Некорректное число: " + key)
        elif typ == "checkbox":
            if not isinstance(value, bool):
                raise HTTPException(422, "Ожидается checkbox: " + key)
        elif typ == "date":
            try:
                date.fromisoformat(value)
            except (ValueError, TypeError):
                raise HTTPException(422, "Некорректная дата: " + key)
        elif typ == "image":
            if not isinstance(value, int) or isinstance(value, bool):
                raise HTTPException(422, "Загрузите изображение: " + key)
            file = s.scalar(
                select(Attachment).where(
                    Attachment.id == value,
                    Attachment.order_id == o.id,
                    Attachment.workshop_id == a.workshop_id,
                )
            )
            if not file:
                raise HTTPException(422, "Изображение не принадлежит заказу")
        result[key] = value
    missing = []
    for f in fields:
        c = f.get("condition")
        if c and result.get(c["field"]) != c["equals"]:
            continue
        if (required and f.get("required")) or f["key"] in required_keys:
            v = result.get(f["key"])
            if v is None or v == "" or (f["type"] == "checkbox" and v is not True):
                missing.append(f["label"])
    if missing:
        raise HTTPException(422, "Заполните: " + ", ".join(missing))
    return result


def form_proxy(o, form):
    return SimpleNamespace(
        id=o.id, template_snapshot=form["template"], values=form["values"]
    )


def public_forms(o, a, forms=None):
    return {
        phase: {
            "template": {
                **form["template"],
                "fields": visible_fields(form_proxy(o, form), a),
            },
            "values": {
                f["key"]: form["values"].get(f["key"])
                for f in visible_fields(form_proxy(o, form), a)
            },
        }
        for phase, form in (o.stage_forms if forms is None else forms).items()
    }


def restricted_attachment_ids(o, a):
    forms = [
        {"template": o.template_snapshot, "values": o.values},
        *o.stage_forms.values(),
    ]
    return {
        form["values"].get(f["key"])
        for form in forms
        for f in form["template"].get("fields", [])
        if f["type"] == "image"
        and f.get("read_permission")
        and f["read_permission"] not in a.permissions
    } - {None}


@router.patch("/orders/{id}/forms/{phase}")
def edit_stage_form(id: str, phase: FormPhase, p: StageFormEdit, a=Depends(access)):
    a.require("orders.edit")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status in {"issued", "cancelled"}:
            raise HTTPException(409, "Заказ закрыт")
        form = o.stage_forms.get(phase)
        if not form:
            raise HTTPException(404, "Форма не назначена заказу")
        values = normalize_values(s, form_proxy(o, form), p.values, a)
        changes = {
            key: {"before": form["values"].get(key), "after": value}
            for key, value in values.items()
            if value != form["values"].get(key)
        }
        o.stage_forms = {**o.stage_forms, phase: {**form, "values": values}}
        touch(o)
        event(s, a, o, "form.updated", {"phase": phase, "value_changes": changes})
        return detail(s, o, a)


def stage_of(o):
    return next((s for s in o.workflow_snapshot if s["key"] == o.stage), {})


def latest_estimate(s, o):
    return s.scalar(
        select(Estimate)
        .where(Estimate.order_id == o.id)
        .order_by(Estimate.revision.desc())
        .limit(1)
    )


def paid(s, o):
    return int(
        s.scalar(
            select(func.coalesce(func.sum(RepairPayment.amount_cents), 0)).where(
                RepairPayment.order_id == o.id
            )
        )
        or 0
    )


def summary(s, o, a):
    device = s.get(Device, o.device_id) if o.device_id else None
    stage = stage_of(o)
    deadline = o.stage_deadline or dt(o.stage_entered_at) + timedelta(
        hours=stage.get("sla_hours", 48)
    )
    return {
        "id": o.public_id,
        "number": o.id,
        "model": (
            device.model if device else o.template_snapshot.get("name", "Устройство")
        ),
        "serial": device.serial if device else "",
        "problem": o.problem,
        "location": o.location,
        "assigned_to": o.assigned_to,
        "stage": o.stage,
        "stage_name": stage.get("name", o.stage),
        "status": o.status,
        "version": o.version,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
        "stage_entered_at": o.stage_entered_at,
        "due_at": o.due_at,
        "stalled": o.status not in {"issued", "cancelled", "draft"}
        and (deadline < utc() or (o.due_at is not None and o.due_at < utc())),
        "warranty_of": (
            s.get(RepairOrder, o.warranty_of).public_id if o.warranty_of else None
        ),
    }


def detail(s, o, a, events_before=None, attachments_before=None):
    files_query = select(Attachment).where(
        Attachment.order_id == o.id,
        Attachment.id.notin_(restricted_attachment_ids(o, a)),
    )
    events_query = select(RepairEvent).where(RepairEvent.order_id == o.id)
    if "finance.read" not in a.permissions:
        events_query = events_query.where(
            ~RepairEvent.kind.startswith("estimate"),
            ~RepairEvent.kind.startswith("payment"),
        )
    if attachments_before:
        files_query = files_query.where(Attachment.id < attachments_before)
    if events_before:
        events_query = events_query.where(RepairEvent.id < events_before)
    files_page = s.scalars(files_query.order_by(Attachment.id.desc()).limit(31)).all()
    events_page = s.scalars(
        events_query.order_by(RepairEvent.id.desc()).limit(31)
    ).all()

    data = summary(s, o, a)
    fields = visible_fields(o, a)
    keys = {f["key"] for f in fields}
    data.update(
        {
            "condition": o.condition,
            "accessories": o.accessories,
            "template": {**o.template_snapshot, "fields": fields},
            "values": {k: v for k, v in o.values.items() if k in keys},
            "stage_forms": public_forms(o, a),
            "workflow": o.workflow_snapshot,
            "checks": o.checks,
            "intake_snapshot": {
                k: v for k, v in o.intake_snapshot.items() if k != "values"
            },
            "customer": None,
            "device_id": o.device_id,
            "customer_id": o.customer_id,
            "attachments_next": files_page[29].id if len(files_page) > 30 else None,
            "events_next": events_page[29].id if len(events_page) > 30 else None,
            "attachments": [
                {
                    "id": f.id,
                    "filename": f.filename,
                    "phase": f.phase,
                    "created_at": f.created_at,
                }
                for f in files_page[:30]
            ],
            "events": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "data": e.data,
                    "actor_id": e.actor_id,
                    "created_at": e.created_at,
                }
                for e in events_page[:30]
                if not e.kind.startswith(("estimate", "payment"))
                or "finance.read" in a.permissions
            ],
            "receipt": (
                (
                    {
                        **o.receipt,
                        "stage_forms": public_forms(
                            o, a, o.receipt.get("stage_forms", {})
                        ),
                        "values": {
                            k: v
                            for k, v in o.receipt.get("values", {}).items()
                            if k in keys
                        },
                    }
                    if o.receipt
                    else None
                )
                if "finance.read" in a.permissions
                else ({"issued_at": o.receipt["issued_at"]} if o.receipt else None)
            ),
        }
    )
    restricted_files = restricted_attachment_ids(o, a)
    data["attachments"] = [
        f for f in data["attachments"] if f["id"] not in restricted_files
    ]
    for item in data["events"]:
        item["data"] = dict(item["data"])
        event_keys = keys
        if item["data"].get("phase") in o.stage_forms:
            event_keys = {
                f["key"]
                for f in visible_fields(
                    form_proxy(o, o.stage_forms[item["data"]["phase"]]), a
                )
            }
        if "value_changes" in item["data"]:
            item["data"]["value_changes"] = {
                k: v
                for k, v in item["data"]["value_changes"].items()
                if k in event_keys
            }
        if "contacts.read" not in a.permissions:
            item["data"].pop("receiver", None)
        old_receipt = item["data"].get("previous_receipt")
        if old_receipt:
            item["data"]["previous_receipt"] = (
                {
                    **old_receipt,
                    "stage_forms": public_forms(
                        o, a, old_receipt.get("stage_forms", {})
                    ),
                    "values": {
                        k: v
                        for k, v in old_receipt.get("values", {}).items()
                        if k in keys
                    },
                }
                if "finance.read" in a.permissions
                else {"issued_at": old_receipt.get("issued_at")}
            )
    if "contacts.read" in a.permissions and o.customer_id:
        c = s.get(Customer, o.customer_id)
        data["customer"] = {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
        }
    if "finance.read" in a.permissions:
        data["estimates"] = [
            {
                "id": q.id,
                "revision": q.revision,
                "lines": q.lines,
                "total_cents": q.total_cents,
                "currency": q.currency,
                "status": q.status,
                "decision_at": q.decision_at,
                "decision_name": q.decision_name,
                "expires_at": q.expires_at,
            }
            for q in s.scalars(
                select(Estimate)
                .where(Estimate.order_id == o.id)
                .order_by(Estimate.revision.desc())
            ).all()
        ]
        data["payments"] = [
            {
                "id": p.id,
                "amount_cents": p.amount_cents,
                "method": p.method,
                "reference": p.reference,
                "created_at": p.created_at,
            }
            for p in s.scalars(
                select(RepairPayment).where(RepairPayment.order_id == o.id)
            ).all()
        ]
        data["paid_cents"] = paid(s, o)
    return data


@router.get("/orders/{id}/attachments")
def attachment_page(id: str, before: int | None = Query(None, ge=1), a=Depends(access)):
    with db() as s:
        data = detail(s, get_order(s, a, id), a, attachments_before=before)
        return {"items": data["attachments"], "next": data["attachments_next"]}


@router.get("/orders/{id}/events")
def event_page(id: str, before: int | None = Query(None, ge=1), a=Depends(access)):
    with db() as s:
        data = detail(s, get_order(s, a, id), a, events_before=before)
        return {"items": data["events"], "next": data["events_next"]}


@router.get("/workshops")
def workshops(user=Depends(current_user)):
    with db() as s:
        return [
            {
                "id": w.id,
                "name": w.name,
                "permissions": r.permissions,
                "scope": r.scope,
                "owner": r.is_owner,
                "billing_status": w.billing_status,
                "trial_until": w.trial_until,
                "paid_until": w.paid_until,
            }
            for w, m, r in s.execute(
                select(Workshop, Membership, WorkshopRole)
                .join(Membership, Membership.workshop_id == Workshop.id)
                .join(WorkshopRole, WorkshopRole.id == Membership.role_id)
                .where(Membership.user_id == user["id"], Membership.active.is_(True))
            ).all()
        ]


@router.get("/templates")
def templates(a=Depends(access)):
    a.require("orders.read")
    with db() as s:
        return [
            {
                "id": t.id,
                "name": t.name,
                "purpose": t.purpose,
                "revision": t.revision,
                "published": t.published,
                "archived": t.archived,
                "columns": t.layout.get("columns", 2),
                "fields": [
                    f
                    for f in t.fields
                    if not f.get("read_permission")
                    or f["read_permission"] in a.permissions
                ],
            }
            for t in s.scalars(
                select(FormTemplate).where(
                    FormTemplate.workshop_id == a.workshop_id,
                    FormTemplate.archived.is_(False),
                )
            ).all()
        ]


@router.post("/templates", status_code=201)
def create_template(p: TemplateInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = FormTemplate(
            workshop_id=a.workshop_id,
            family=str(uuid4()),
            name=p.name,
            purpose=p.purpose,
            fields=[f.model_dump() for f in p.fields],
            layout={"columns": p.columns},
        )
        s.add(t)
        s.flush()
        event(s, a, None, "template.created", {"id": t.id})
        return {"id": t.id}


@router.put("/templates/{id}")
def edit_template(id: int, p: TemplateInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        if t.published:
            raise HTTPException(409, "Создайте новую версию опубликованного шаблона")
        t.name = p.name
        t.purpose = p.purpose
        t.fields = [f.model_dump() for f in p.fields]
        t.layout = {"columns": p.columns}
        event(s, a, None, "template.edited", {"id": id})
        return {"id": id}


@router.post("/templates/{id}/version", status_code=201)
def template_version(id: int, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        # Serialise revision assignment through a workshop row lock.
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        revision = (
            s.scalar(
                select(FormTemplate.revision)
                .where(
                    FormTemplate.workshop_id == a.workshop_id,
                    FormTemplate.family == t.family,
                )
                .order_by(FormTemplate.revision.desc())
                .limit(1)
                .with_for_update()
            )
            or 0
        ) + 1
        new = FormTemplate(
            workshop_id=a.workshop_id,
            family=t.family,
            name=t.name,
            purpose=t.purpose,
            revision=revision,
            fields=t.fields,
            layout=t.layout,
        )
        s.add(new)
        s.flush()
        return {"id": new.id}


@router.post("/templates/{id}/publish")
def publish_template(id: int, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        t.published = True
        event(s, a, None, "template.published", {"id": id})
        return {"id": id}


@router.post("/templates/{id}/archive")
def archive_template(id: int, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        t.archived = True
        event(s, a, None, "template.archived", {"id": id})
        return {"id": id}


@router.get("/workflows")
def workflows(a=Depends(access)):
    a.require("orders.read")
    with db() as s:
        return [
            {"id": w.id, "name": w.name, "revision": w.revision, "stages": w.stages}
            for w in s.scalars(
                select(Workflow).where(
                    Workflow.workshop_id == a.workshop_id, Workflow.archived.is_(False)
                )
            ).all()
        ]


@router.post("/workflows", status_code=201)
def create_workflow(p: WorkflowInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        w = Workflow(
            workshop_id=a.workshop_id,
            name=p.name,
            family=str(uuid4()),
            stages=[x.model_dump() for x in p.stages],
        )
        s.add(w)
        s.flush()
        event(s, a, None, "workflow.created", {"id": w.id})
        return {"id": w.id}


@router.post("/workflows/{id}/version", status_code=201)
def workflow_version(id: int, p: WorkflowInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        old = scoped(s, Workflow, id, a)
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        revision = (
            s.scalar(
                select(Workflow.revision)
                .where(
                    Workflow.workshop_id == a.workshop_id, Workflow.family == old.family
                )
                .order_by(Workflow.revision.desc())
                .limit(1)
                .with_for_update()
            )
            or 0
        ) + 1
        w = Workflow(
            workshop_id=a.workshop_id,
            name=p.name,
            family=old.family,
            revision=revision,
            stages=[x.model_dump() for x in p.stages],
        )
        s.add(w)
        s.flush()
        old.archived = True
        event(s, a, None, "workflow.version", {"old": id, "new": w.id})
        return {"id": w.id}


@router.get("/customers")
def customers(q: str = Query("", max_length=120), a=Depends(access)):
    a.require("contacts.read")
    with db() as s:
        return [
            {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email}
            for c in s.scalars(
                select(Customer)
                .where(
                    Customer.workshop_id == a.workshop_id,
                    or_(
                        Customer.name.contains(q, autoescape=True),
                        Customer.phone.contains(q, autoescape=True),
                        Customer.email.contains(q, autoescape=True),
                    ),
                )
                .limit(50)
            ).all()
        ]


@router.get("/devices")
def devices(customer_id: int, a=Depends(access)):
    a.require("contacts.read")
    with db() as s:
        scoped(s, Customer, customer_id, a)
        return [
            {"id": d.id, "model": d.model, "serial": d.serial}
            for d in s.scalars(
                select(Device).where(
                    Device.workshop_id == a.workshop_id,
                    Device.customer_id == customer_id,
                )
            ).all()
        ]


def create_order_record(s, p, a):
    enforce_limit(s, a.workshop_id, "open_orders")
    t = scoped(s, FormTemplate, p.template_id, a)
    w = scoped(s, Workflow, p.workflow_id, a)
    if not t.published or t.archived or w.archived:
        raise HTTPException(422, "Выберите опубликованный шаблон и действующий процесс")
    if t.purpose != "intake":
        raise HTTPException(422, "Для приёма выберите форму приёмки")
    forms = {}
    for phase, template_id in p.stage_forms.items():
        form = scoped(s, FormTemplate, template_id, a)
        if form.purpose != phase or not form.published or form.archived:
            raise HTTPException(422, "Выберите опубликованную форму нужного назначения")
        forms[phase] = {
            "template": {
                "id": form.id,
                "name": form.name,
                "revision": form.revision,
                "purpose": phase,
                "fields": form.fields,
                "layout": form.layout,
            },
            "values": {},
        }
    if any(
        stage.get("form_phase") and stage["form_phase"] not in forms
        for stage in w.stages
    ):
        raise HTTPException(422, "Для процесса необходимо выбрать формы этапов")
    keys = {f["key"] for f in t.fields}
    if any(set(stage.get("required_fields", [])) - keys for stage in w.stages):
        raise HTTPException(422, "В форме отсутствуют обязательные поля процесса")
    if p.warranty_of:
        raise HTTPException(422, "Создавайте гарантийное обращение из исходного заказа")
    c = scoped(s, Customer, p.customer_id, a) if p.customer_id else None
    if not c:
        if not p.customer:
            raise HTTPException(422, "Укажите клиента")
        c = Customer(workshop_id=a.workshop_id, **p.customer.model_dump())
        s.add(c)
        s.flush()
    d = scoped(s, Device, p.device_id, a) if p.device_id else None
    if d and d.customer_id != c.id:
        raise HTTPException(422, "Устройство другого клиента")
    if not d:
        if not p.model:
            raise HTTPException(422, "Укажите модель устройства")
        d = Device(
            workshop_id=a.workshop_id, customer_id=c.id, model=p.model, serial=p.serial
        )
        s.add(d)
        s.flush()
    o = RepairOrder(
        public_id=str(uuid4()),
        workshop_id=a.workshop_id,
        created_by=a.user_id,
        customer_id=c.id,
        device_id=d.id,
        problem=p.problem,
        condition=p.condition,
        accessories=p.accessories,
        location=p.location,
        template_snapshot={
            "id": t.id,
            "name": t.name,
            "revision": t.revision,
            "fields": t.fields,
            "layout": t.layout,
        },
        stage_forms=forms,
        workflow_snapshot=w.stages,
        stage=w.stages[0]["key"],
        stage_deadline=utc() + timedelta(hours=w.stages[0].get("sla_hours", 48)),
        status="draft" if p.draft else "active",
        values={},
        due_at=dt(p.due_at),
    )
    s.add(o)
    s.flush()
    o.values = normalize_values(s, o, p.values, a, required=not p.draft)
    if not p.draft:
        freeze_intake(s, o)
    event(s, a, o, "order.created", {"draft": p.draft})
    return o


def freeze_intake(s, o):
    o.intake_snapshot = {
        "problem": o.problem,
        "condition": o.condition,
        "accessories": o.accessories,
        "values": o.values,
        "accepted_at": utc().isoformat(),
        "attachments": [
            f.id
            for f in s.scalars(
                select(Attachment).where(
                    Attachment.order_id == o.id, Attachment.phase == "intake"
                )
            ).all()
        ],
    }


@router.post("/orders", status_code=201)
def create_order(p: OrderInput, a=Depends(access)):
    a.require("orders.create")
    a.require("contacts.read")
    a.write()
    with db() as s:
        return detail(s, create_order_record(s, p, a), a)


@router.get("/orders")
def orders(
    q: str = Query("", max_length=120),
    status: str | None = None,
    stalled: bool = False,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    a=Depends(access),
):
    a.require("orders.read")
    with db() as s:
        filters = order_filters(a)
        if status:
            filters.append(RepairOrder.status == status)
        if q:
            filters.append(
                or_(
                    RepairOrder.problem.contains(q, autoescape=True),
                    RepairOrder.location.contains(q, autoescape=True),
                    RepairOrder.id == int(q) if q.isdigit() else False,
                    RepairOrder.device_id.in_(
                        select(Device.id).where(
                            Device.workshop_id == a.workshop_id,
                            or_(
                                Device.model.contains(q, autoescape=True),
                                Device.serial.contains(q, autoescape=True),
                            ),
                        )
                    ),
                )
            )
        if stalled:
            filters.extend(
                [
                    RepairOrder.status.not_in(["issued", "cancelled", "draft"]),
                    or_(RepairOrder.stage_deadline < utc(), RepairOrder.due_at < utc()),
                ]
            )
        query = (
            select(RepairOrder)
            .where(*filters)
            .order_by(RepairOrder.updated_at.desc(), RepairOrder.id.desc())
        )
        total = s.scalar(select(func.count()).select_from(RepairOrder).where(*filters))
        return {
            "items": [
                summary(s, o, a)
                for o in s.scalars(query.offset((page - 1) * limit).limit(limit)).all()
            ],
            "total": total,
        }


@router.get("/orders/{id}")
def order(id: str, a=Depends(access)):
    with db() as s:
        return detail(s, get_order(s, a, id), a)


@router.patch("/orders/{id}")
def edit_order(id: str, p: OrderEdit, a=Depends(access)):
    a.require("orders.edit")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status in {"issued", "cancelled"}:
            raise HTTPException(409, "Заказ закрыт")
        changes = {
            k: v
            for k, v in p.model_dump(
                exclude_unset=True, exclude={"version", "reason", "values"}
            ).items()
            if getattr(o, k) != v
        }
        if (
            o.status != "draft"
            and any(k in changes for k in ["problem", "condition", "accessories"])
            and len(p.reason) < 3
        ):
            raise HTTPException(422, "Укажите причину исправления приёмки")
        previous = dict(o.values)
        metadata_changes = {
            k: {
                "before": str(getattr(o, k)) if k == "due_at" else getattr(o, k),
                "after": str(v) if k == "due_at" else v,
            }
            for k, v in changes.items()
        }
        if p.values is not None:
            o.values = normalize_values(s, o, p.values, a)
        value_changes = {
            k: {"before": previous.get(k), "after": v}
            for k, v in o.values.items()
            if v != previous.get(k)
        }
        for k, v in changes.items():
            setattr(o, k, dt(v) if k == "due_at" else v)
        touch(o)
        event(
            s,
            a,
            o,
            "order.edited",
            {
                "fields": list(changes) + (["values"] if value_changes else []),
                "reason": p.reason,
                "metadata_changes": metadata_changes,
                "value_changes": value_changes,
            },
        )
        return detail(s, o, a)


@router.post("/orders/{id}/accept")
def accept_order(id: str, p: Version, a=Depends(access)):
    a.require("orders.create")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status != "draft":
            raise HTTPException(409, "Заказ уже принят")
        normalize_values(s, o, {}, a, required=True)
        freeze_intake(s, o)
        o.status = "active"
        o.stage_entered_at = utc()
        o.stage_deadline = utc() + timedelta(hours=stage_of(o).get("sla_hours", 48))
        touch(o)
        event(s, a, o, "order.accepted")
        return detail(s, o, a)


@router.post("/orders/{id}/assign")
def assign_order(id: str, p: Assignment, a=Depends(access)):
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status in {"issued", "cancelled"}:
            raise HTTPException(409, "Заказ закрыт")
        if "orders.assign" not in a.permissions:
            a.require("orders.transition")
            if p.user_id != a.user_id or o.assigned_to not in {None, a.user_id}:
                raise HTTPException(403, "Можно взять только свободный заказ")
        if p.user_id is not None:
            m = s.scalar(
                select(Membership).where(
                    Membership.workshop_id == a.workshop_id,
                    Membership.user_id == p.user_id,
                    Membership.active.is_(True),
                )
            )
            if not m:
                raise HTTPException(422, "Сотрудник недоступен")
        old = o.assigned_to
        o.assigned_to = p.user_id
        touch(o)
        event(s, a, o, "order.assigned", {"from": old, "to": p.user_id})
        return detail(s, o, a)


@router.post("/orders/{id}/transition")
def transition(id: str, p: Transition, a=Depends(access)):
    a.require("orders.transition")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status in {"draft", "issued", "cancelled"}:
            raise HTTPException(409, "Переход сейчас недоступен")
        current = stage_of(o)
        phase = current.get("form_phase")
        if phase:
            form = o.stage_forms.get(phase)
            if not form:
                raise HTTPException(409, "Форма этапа отсутствует")
            normalize_values(s, form_proxy(o, form), {}, a, required=True)
        if p.target not in current.get("next", []):
            raise HTTPException(409, "Недопустимый переход")
        target = next(x for x in o.workflow_snapshot if x["key"] == p.target)
        a.require(target.get("permission", "orders.transition"))
        normalize_values(s, o, {}, a, required_keys=target.get("required_fields", []))
        needed = set(target.get("checks", []))
        if not needed.issubset(set(p.checks)):
            raise HTTPException(422, "Выполните обязательные проверки")
        if target.get("requires_quote"):
            q = latest_estimate(s, o)
            if not q or q.status != "accepted":
                raise HTTPException(409, "Нужна принятая актуальная смета")
        old = o.stage
        o.stage = p.target
        o.status = target["category"]
        o.stage_entered_at = utc()
        o.stage_deadline = utc() + timedelta(hours=target.get("sla_hours", 48))
        o.checks = {
            **o.checks,
            p.target: {
                "items": sorted(needed),
                "by": a.user_id,
                "at": utc().isoformat(),
            },
        }
        touch(o)
        event(
            s,
            a,
            o,
            "order.transition",
            {"from": old, "to": p.target, "checks": sorted(needed), "reason": p.reason},
        )
        if target["category"] == "ready":
            queue_email(
                s,
                o,
                "Устройство готово к выдаче",
                f"Заказ #{o.id} готов. Свяжитесь с мастерской для получения.",
                f"ready:{o.id}:{o.version}",
            )
        return detail(s, o, a)


@router.post("/orders/{id}/notes")
def note(id: str, p: Note, a=Depends(access)):
    a.require("orders.edit")
    with db() as s:
        o = get_order(s, a, id, p.version)
        touch(o)
        event(s, a, o, "note", {"text": p.text})
        return detail(s, o, a)


@router.post("/orders/{id}/issue")
def issue(id: str, p: Issue, a=Depends(access)):
    a.require("orders.issue")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status != "ready":
            raise HTTPException(
                409, "Сначала завершите проверку и подготовьте устройство к выдаче"
            )
        normalize_values(
            s, o, {}, a, required_keys=stage_of(o).get("required_fields", [])
        )
        for phase in {stage.get("form_phase") for stage in o.workflow_snapshot} - {
            None
        }:
            form = o.stage_forms.get(phase)
            if not form:
                raise HTTPException(409, "Форма этапа отсутствует")
            normalize_values(s, form_proxy(o, form), {}, a, required=True)
        q = latest_estimate(s, o)
        total = q.total_cents if q and q.status == "accepted" else 0
        balance = total - paid(s, o)
        if q and q.status != "accepted":
            raise HTTPException(
                409,
                "Для выдачи согласуйте актуальную смету; при отказе от ремонта создайте смету фактических работ, включая нулевую стоимость",
            )
        if balance > 0:
            a.require("finance.write")
            if len(p.outstanding_reason) < 3:
                raise HTTPException(
                    422,
                    "Есть задолженность. Запишите оплату или причину выдачи без расчёта",
                )
        receipt = {
            "stage_forms": deepcopy(o.stage_forms),
            "issued_at": utc().isoformat(),
            "receiver": p.receiver,
            "issued_by": a.user_id,
            "note": p.note,
            "outstanding_reason": p.outstanding_reason,
            "estimate_revision": q.revision if q else None,
            "total_cents": total,
            "paid_cents": paid(s, o),
            "checks": o.checks,
            "values": o.values,
            "condition": o.condition,
            "accessories": o.accessories,
        }
        o.receipt = receipt
        o.status = "issued"
        touch(o)
        event(s, a, o, "order.issued", {"receiver": p.receiver, "note": p.note})
        return detail(s, o, a)


@router.post("/orders/{id}/reopen")
def reopen(id: str, p: Reopen, a=Depends(access)):
    a.require("orders.reopen")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status in {"issued", "cancelled"}:
            enforce_limit(s, a.workshop_id, "open_orders")
        if o.status not in {"issued", "cancelled", "ready"}:
            raise HTTPException(409, "Заказ уже открыт")
        event(
            s,
            a,
            o,
            "order.reopened",
            {"reason": p.reason, "previous_receipt": o.receipt},
        )
        o.stage = o.workflow_snapshot[0]["key"]
        o.status = "active"
        o.receipt = None
        o.checks = {}
        o.stage_entered_at = utc()
        o.stage_deadline = utc() + timedelta(hours=stage_of(o).get("sla_hours", 48))
        touch(o)
        return detail(s, o, a)


@router.post("/orders/{id}/cancel")
def cancel(id: str, p: Reopen, a=Depends(access)):
    a.require("orders.reopen")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status == "issued":
            raise HTTPException(409, "Устройство уже выдано")
        o.status = "cancelled"
        touch(o)
        event(s, a, o, "order.cancelled", {"reason": p.reason})
        return detail(s, o, a)


@router.post("/orders/{id}/warranty", status_code=201)
def warranty(id: str, p: Note, a=Depends(access)):
    a.require("orders.create")
    with db() as s:
        enforce_limit(s, a.workshop_id, "open_orders")
        old = get_order(s, a, id, p.version)
        if old.status != "issued":
            raise HTTPException(409, "Гарантийное обращение создаётся после выдачи")
        o = RepairOrder(
            public_id=str(uuid4()),
            workshop_id=a.workshop_id,
            created_by=a.user_id,
            customer_id=old.customer_id,
            device_id=old.device_id,
            warranty_of=old.id,
            problem=p.text,
            template_snapshot=old.template_snapshot,
            stage_forms={
                phase: {"template": f["template"], "values": {}}
                for phase, f in old.stage_forms.items()
            },
            workflow_snapshot=old.workflow_snapshot,
            stage=old.workflow_snapshot[0]["key"],
            status="draft",
            values={},
        )
        s.add(o)
        s.flush()
        event(s, a, o, "warranty.created", {"original": old.public_id})
        touch(old)
        event(s, a, old, "warranty.linked", {"order": o.public_id})
        return detail(s, o, a)


@router.get("/orders/{id}/history")
def history(id: str, a=Depends(access)):
    with db() as s:
        o = get_order(s, a, id)
        if not o.device_id:
            return []
        return [
            summary(s, x, a)
            for x in s.scalars(
                select(RepairOrder)
                .where(*order_filters(a), RepairOrder.device_id == o.device_id)
                .order_by(RepairOrder.created_at.desc())
            ).all()
        ]


def queue_email(s, o, subject, body, key):
    c = s.get(Customer, o.customer_id) if o.customer_id else None
    if c and c.email:
        s.add(
            Outbox(
                workshop_id=o.workshop_id,
                order_id=o.id,
                recipient=c.email,
                subject=subject,
                body=body,
                dedupe_key=key,
            )
        )


@router.post("/orders/{id}/estimates", status_code=201)
def estimate(id: str, p: EstimateInput, a=Depends(access)):
    import os

    a.require("finance.write")
    with db() as s:
        o = get_order(s, a, id, p.version)
        if o.status in {"draft", "issued", "cancelled"}:
            raise HTTPException(409, "Смета доступна для принятого открытого заказа")
        old = latest_estimate(s, o)
        for q in s.scalars(
            select(Estimate).where(
                Estimate.order_id == o.id, Estimate.status == "pending"
            )
        ).all():
            q.status = "superseded"
        token = secrets.token_urlsafe(32)
        q = Estimate(
            workshop_id=a.workshop_id,
            order_id=o.id,
            revision=(old.revision + 1 if old else 1),
            lines=[x.model_dump() for x in p.lines],
            total_cents=sum(x.quantity * x.unit_cents for x in p.lines),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=utc() + timedelta(days=7),
        )
        s.add(q)
        s.flush()
        touch(o)
        event(
            s,
            a,
            o,
            "estimate.created",
            {"revision": q.revision, "total_cents": q.total_cents},
        )
        link = "/quote/" + token
        base = os.getenv("PUBLIC_URL", "").rstrip("/")
        if base:
            queue_email(
                s,
                o,
                "Согласование стоимости ремонта",
                f"Заказ #{o.id}. Смета №{q.revision}: {q.total_cents/100:.2f} PLN. Решение: {base}{link}",
                f"estimate:{q.id}",
            )
        return {"order": detail(s, o, a), "approval_path": link}


@router.post("/orders/{id}/payments", status_code=201)
def payment(id: str, p: PaymentInput, a=Depends(access)):
    a.require("finance.write")
    with db() as s:
        o = get_order(s, a, id, p.version)
        s.add(
            RepairPayment(
                workshop_id=a.workshop_id,
                order_id=o.id,
                amount_cents=p.amount_cents,
                method=p.method,
                reference=p.reference,
            )
        )
        s.flush()
        touch(o)
        event(
            s,
            a,
            o,
            "payment.recorded",
            {"amount_cents": p.amount_cents, "method": p.method},
        )
        return detail(s, o, a)


@router.get("/members")
def members(a=Depends(access)):
    a.require("orders.read")
    with db() as s:
        return [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email if "members.manage" in a.permissions else None,
                "active": m.active,
                "role_id": r.id,
                "role": r.name,
                "owner": r.is_owner,
            }
            for m, u, r in s.execute(
                select(Membership, User, WorkshopRole)
                .join(User, User.id == Membership.user_id)
                .join(WorkshopRole, WorkshopRole.id == Membership.role_id)
                .where(Membership.workshop_id == a.workshop_id)
            ).all()
        ]


@router.get("/roles")
def roles(a=Depends(access)):
    a.require("members.manage")
    with db() as s:
        return {
            "permissions": PERMISSIONS,
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "permissions": r.permissions,
                    "scope": r.scope,
                    "owner": r.is_owner,
                }
                for r in s.scalars(
                    select(WorkshopRole).where(
                        WorkshopRole.workshop_id == a.workshop_id
                    )
                ).all()
            ],
        }


@router.post("/roles", status_code=201)
def create_role(p: RoleInput, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        if s.scalar(
            select(WorkshopRole).where(
                WorkshopRole.workshop_id == a.workshop_id, WorkshopRole.name == p.name
            )
        ):
            raise HTTPException(409, "Роль уже существует")
        r = WorkshopRole(workshop_id=a.workshop_id, **p.model_dump())
        s.add(r)
        s.flush()
        event(s, a, None, "role.created", {"role": r.id})
        return {"id": r.id}


@router.put("/roles/{id}")
def edit_role(id: int, p: RoleInput, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        r = scoped(s, WorkshopRole, id, a)
        if r.is_owner:
            raise HTTPException(409, "Права владельца не изменяются")
        if s.scalar(
            select(WorkshopRole).where(
                WorkshopRole.workshop_id == a.workshop_id,
                WorkshopRole.name == p.name,
                WorkshopRole.id != id,
            )
        ):
            raise HTTPException(409, "Роль уже существует")
        for k, v in p.model_dump().items():
            setattr(r, k, v)
        event(s, a, None, "role.updated", {"role": id})
        return {"id": id}


@router.post("/members", status_code=201)
def add_member(p: MemberInput, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        enforce_limit(s, a.workshop_id, "members")
        r = scoped(s, WorkshopRole, p.role_id, a)
        if r.is_owner:
            raise HTTPException(422, "Назначьте рабочую роль")
        if s.scalar(select(User).where(User.email == str(p.email).lower())):
            raise HTTPException(
                409,
                "Аккаунт с этим email уже существует. Используйте отдельный рабочий email.",
            )
        u = User(
            name=p.name,
            email=str(p.email).lower(),
            password_hash=hash_password(p.password),
        )
        s.add(u)
        s.flush()
        s.add(Membership(workshop_id=a.workshop_id, user_id=u.id, role_id=r.id))
        event(s, a, None, "member.created", {"user": u.id})
        return {"id": u.id}


@router.patch("/members/{id}")
def edit_member(id: int, p: MemberEdit, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        m = s.scalar(
            select(Membership).where(
                Membership.workshop_id == a.workshop_id, Membership.user_id == id
            )
        )
        if not m:
            raise HTTPException(404, "Сотрудник не найден")
        old = s.get(WorkshopRole, m.role_id)
        new = scoped(s, WorkshopRole, p.role_id, a)
        if new.is_owner and not old.is_owner:
            raise HTTPException(
                422, "Передача роли владельца требует отдельной процедуры"
            )
        if old.is_owner and (not p.active or not new.is_owner):
            raise HTTPException(409, "Владелец сохраняет доступ")
        if p.active and not m.active:
            enforce_limit(s, a.workshop_id, "members")
        m.role_id = new.id
        m.active = p.active
        event(
            s,
            a,
            None,
            "member.updated",
            {"user": id, "active": p.active, "role": p.role_id},
        )
        return {"id": id}


@router.get("/outbox")
def outbox(a=Depends(access)):
    a.require("contacts.read")
    with db() as s:
        return [
            {
                "id": m.id,
                "subject": m.subject,
                "status": m.status,
                "attempts": m.attempts,
                "last_error": m.last_error,
            }
            for m in s.scalars(
                select(Outbox)
                .where(Outbox.workshop_id == a.workshop_id)
                .order_by(Outbox.id.desc())
                .limit(100)
            ).all()
        ]
