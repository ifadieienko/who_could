"""jobs / finance_routes domain. Legacy API behavior is preserved."""

import hashlib
import secrets

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.database import db
from app.jobs.finance_service import latest_estimate, queue_email
from app.jobs.serialization import detail
from app.repair_access import access, event, get_order, touch, utc
from app.repair_models import Estimate, RepairPayment
from app.repair_schemas import EstimateInput, PaymentInput

router = APIRouter()


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

