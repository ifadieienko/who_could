"""core / mail / routes domain. Legacy API behavior is preserved."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.database import db
from app.repair_access import access
from app.repair_models import Outbox

router = APIRouter()


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

