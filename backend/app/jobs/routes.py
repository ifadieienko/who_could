"""jobs / routes domain. Legacy API behavior is preserved."""

from copy import deepcopy
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from uuid import uuid4
from app.database import db
from app.forms.service import form_proxy, normalize_values
from app.jobs.finance_service import latest_estimate, paid, queue_email
from app.jobs.serialization import detail, summary
from app.jobs.service import create_order_record, freeze_intake
from app.plans import enforce_limit
from app.repair_access import access, dt, event, get_order, order_filters, touch, utc
from app.repair_models import Device, Membership, RepairOrder
from app.repair_schemas import Assignment, FormPhase, Issue, Note, OrderEdit, OrderInput, Reopen, StageFormEdit, Transition, Version
from app.workflows.service import stage_of

router = APIRouter()


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

