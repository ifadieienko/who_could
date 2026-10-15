"""jobs / service domain. Legacy API behavior is preserved."""

from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from uuid import uuid4
from app.core.tenancy.records import scoped
from app.forms.service import normalize_values
from app.plans import enforce_limit
from app.repair_access import dt, event, utc, touch
from app.repair_models import Workshop, Attachment, Customer, Device, FormTemplate, RepairOrder, Workflow, Site


def create_order_record(s, p, a, *, job_metadata=None):
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
            workshop_id=a.workshop_id, customer_id=c.id, name=p.model, model=p.model, serial=p.serial
        )
        s.add(d)
        s.flush()
    metadata = job_metadata or {}
    if metadata.get("site_id") is not None:
        validate_job_site(s, metadata["site_id"], c.id, a)
    o = RepairOrder(
        **metadata,
        public_id=str(uuid4()),
        currency=s.get(Workshop, a.workshop_id).currency,
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
    event(s, a, o, "order.created", {"draft": p.draft, **metadata})
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



def validate_job_site(s, site_id, customer_id, a):
    a.require("customers.read")
    site = scoped(s, Site, site_id, a)
    if site.customer_id != customer_id:
        raise HTTPException(422, "Site belongs to another customer")


def edit_order_record(s, o, p, a):
    if "site_id" in p.model_fields_set:
        a.require("customers.read")
        if p.site_id is not None:
            validate_job_site(s, p.site_id, o.customer_id, a)
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
