"""jobs / finance_service domain. Legacy API behavior is preserved."""

from sqlalchemy import func, select
from app.repair_models import Customer, Estimate, Outbox, RepairPayment


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
