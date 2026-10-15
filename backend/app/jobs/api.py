"""Generic, read-only job API over the existing repair lifecycle.

No snapshots are reconstructed from mutable organization or asset settings.
Writes remain on the compatibility API until the generic lifecycle is introduced.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.database import db
from app.jobs.models import Job
from app.jobs.serialization import detail, summary
from app.repair_access import access, get_order, order_filters

router = APIRouter(prefix="/jobs", tags=["jobs"])


def serialize(s, job, a, full=False):
    data = detail(s, job, a) if full else summary(s, job, a)
    data["organization_id"] = job.workshop_id
    data["asset_id"] = job.device_id
    data["description"] = data.pop("problem")
    data.pop("device_id", None)
    return data


@router.get("")
def jobs(
    after: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    status: str | None = Query(None, max_length=20),
    asset_id: int | None = Query(None, ge=1),
    customer_id: int | None = Query(None, ge=1),
    a=Depends(access),
):
    a.require("jobs.read")
    query = select(Job).where(*order_filters(a))
    if after is not None:
        query = query.where(Job.id > after)
    if status is not None:
        query = query.where(Job.status == status)
    if asset_id is not None:
        query = query.where(Job.device_id == asset_id)
    if customer_id is not None:
        # Filtering by contacts must not become a side channel for restricted roles.
        a.require("customers.read")
        query = query.where(Job.customer_id == customer_id)
    with db() as s:
        rows = s.scalars(query.order_by(Job.id).limit(limit + 1)).all()
        return {
            "items": [serialize(s, job, a) for job in rows[:limit]],
            "next": rows[limit - 1].id if len(rows) > limit else None,
        }


@router.get("/{id}")
def job(id: str, a=Depends(access)):
    with db() as s:
        return serialize(s, get_order(s, a, id), a, full=True)


@router.get("/{id}/events")
def events(id: str, before: int | None = Query(None, ge=1), a=Depends(access)):
    with db() as s:
        data = detail(s, get_order(s, a, id), a, events_before=before)
        return {"items": data["events"], "next": data["events_next"]}


@router.get("/{id}/attachments")
def attachments(id: str, before: int | None = Query(None, ge=1), a=Depends(access)):
    with db() as s:
        data = detail(s, get_order(s, a, id), a, attachments_before=before)
        return {"items": data["attachments"], "next": data["attachments_next"]}
