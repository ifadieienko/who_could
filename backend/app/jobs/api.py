"""Generic job reads and writes sharing the existing repair lifecycle."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.database import db
from app.forms.instances import edit_instance, serialize_instance
from app.forms.schemas import InstanceEdit
from app.repair_schemas import FormSlot
from app.repair_models import JobFormInstance
from app.jobs.models import Job
from app.jobs.schemas import JobInput, JobEdit
from app.jobs.service import create_order_record, edit_order_record
from app.repair_schemas import OrderInput
from app.repair_models import Workshop
from app.jobs.serialization import detail, summary
from app.repair_access import access, get_order, order_filters

router = APIRouter(prefix="/jobs", tags=["jobs"])


def serialize(s, job, a, full=False):
    data = detail(s, job, a) if full else summary(s, job, a)
    data["organization_id"] = job.workshop_id
    data["asset_id"] = job.device_id
    data.update(vertical_key=job.vertical_key, job_type=job.job_type,
                priority=job.priority, site_id=job.site_id)
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


@router.post("", status_code=201)
def create_job(p: JobInput, a=Depends(access)):
    a.require("jobs.create")
    a.require("customers.read")
    a.write()
    legacy = p.model_dump(exclude={"asset_id", "description", "job_type", "priority", "site_id"})
    legacy.update(device_id=p.asset_id, problem=p.description)
    with db() as s:
        organization = s.get(Workshop, a.organization_id)
        record = create_order_record(s, OrderInput(**legacy), a, job_metadata={
            "vertical_key": organization.vertical_key,
            "job_type": p.job_type,
            "priority": p.priority,
            "site_id": p.site_id,
        })
        return serialize(s, record, a, full=True)


@router.patch("/{id}")
def edit_job(id: str, p: JobEdit, a=Depends(access)):
    a.require("jobs.edit")
    with db() as s:
        record = get_order(s, a, id, p.version)
        edit_order_record(s, record, p, a)
        return serialize(s, record, a, full=True)


@router.get("/{id}/forms")
def job_forms(id: str, a=Depends(access)):
    with db() as s:
        job = get_order(s, a, id)
        instances = s.scalars(select(JobFormInstance).where(
            JobFormInstance.job_id == job.id,
            JobFormInstance.workshop_id == a.workshop_id,
        ).order_by(JobFormInstance.slot_key)).all()
        return {"job_version": job.version,
                "items": [serialize_instance(job, instance, a) for instance in instances]}


@router.patch("/{id}/forms/{slot}")
def edit_job_form(id: str, slot: FormSlot, p: InstanceEdit, a=Depends(access)):
    a.require("jobs.edit")
    with db() as s:
        job = get_order(s, a, id, p.job_version)
        instance = edit_instance(s, job, slot, p.values, a, form_version=p.version)
        return {"job_version": job.version, "form": serialize_instance(job, instance, a)}
