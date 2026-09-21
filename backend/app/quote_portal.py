import hashlib
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from .database import db
from .repair_models import Estimate, RepairOrder, RepairEvent, Workshop
from .repair_access import utc, touch
from .repair_schemas import Decision

router = APIRouter(prefix="/public/quotes", tags=["customer-approval"])


def load(s, token, lock=False):
    if len(token) > 100:
        raise HTTPException(404, "Ссылка недоступна")
    q = s.scalar(
        select(Estimate).where(
            Estimate.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if not q:
        raise HTTPException(404, "Ссылка недоступна")
    # Same lock order as staff edits: order, then estimate.
    o = (
        s.scalar(
            select(RepairOrder).where(RepairOrder.id == q.order_id).with_for_update()
        )
        if lock
        else s.get(RepairOrder, q.order_id)
    )
    if lock:
        s.refresh(q, with_for_update=True)
    if q.expires_at < utc() or q.status == "superseded":
        raise HTTPException(410, "Ссылка истекла или смета заменена")
    latest = s.scalar(
        select(Estimate.id)
        .where(Estimate.order_id == o.id)
        .order_by(Estimate.revision.desc())
        .limit(1)
        .with_for_update()
    )
    if latest != q.id:
        raise HTTPException(410, "Смета заменена новой версией")
    return q, o


@router.get("/{token}")
def quote(token: str):
    with db() as s:
        q, o = load(s, token)
        w = s.get(Workshop, o.workshop_id)
        return {
            "workshop": w.name,
            "number": o.id,
            "revision": q.revision,
            "lines": q.lines,
            "total_cents": q.total_cents,
            "currency": q.currency,
            "status": q.status,
            "expires_at": q.expires_at,
        }


@router.post("/{token}")
def decide(token: str, p: Decision):
    with db() as s:
        q, o = load(s, token, True)
        if q.status != "pending":
            raise HTTPException(409, "Решение уже зарегистрировано")
        if o.status in {"issued", "cancelled"}:
            raise HTTPException(409, "Заказ закрыт")
        q.status = p.decision
        q.decision_at = utc()
        q.decision_name = p.name
        touch(o)
        s.add(
            RepairEvent(
                workshop_id=o.workshop_id,
                order_id=o.id,
                kind="estimate." + p.decision,
                data={
                    "revision": q.revision,
                    "name": p.name,
                    "total_cents": q.total_cents,
                    "channel": "customer_link",
                },
            )
        )
        return {"status": q.status}
