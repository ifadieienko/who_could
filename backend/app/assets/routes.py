"""Tenant-scoped customer, site and asset records, with cursor-based browsing."""

import html
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from app.assets.models import Asset, Site
from app.assets.schemas import (
    AssetInput,
    AssetEdit,
    CustomerRecord,
    CustomerEdit,
    SiteInput,
    SiteEdit,
)
from app.core.tenancy.records import scoped
from app.database import db
from app.jobs.serialization import summary
from app.plans import lock_workshop
from app.repair_access import access, event, order_filters, utc
from app.repair_models import Customer, RepairOrder, Attachment
from app.forms.service import restricted_attachment_ids
from app.repair_files import qr_svg

router = APIRouter(prefix="/v2", tags=["assets"])


def serialized(record):
    result = {c.name: getattr(record, c.name) for c in record.__table__.columns}
    result["organization_id"] = result.pop("workshop_id")
    return result


def page(s, query, model, after, limit, serialize=serialized):
    if after:
        query = query.where(model.id > after)
    rows = s.scalars(query.order_by(model.id).limit(limit + 1)).all()
    return {
        "items": [serialize(x) for x in rows[:limit]],
        "next": rows[limit - 1].id if len(rows) > limit else None,
    }


def full_scope(a):
    # Assets and customer records can be shared by multiple jobs; changing one
    # must not be possible from a role limited to its own assigned work.
    if a.scope != "all":
        raise HTTPException(
            403, "Shared record changes require organization-wide scope"
        )


def asset_query(a):
    query = select(Asset).where(Asset.workshop_id == a.workshop_id)
    if a.scope == "own":
        query = query.where(
            Asset.id.in_(select(RepairOrder.device_id).where(*order_filters(a)))
        )
    return query


def asset_record(s, id, a, version=None):
    a.require("assets.read")
    if version is not None:
        a.write()
        full_scope(a)
        lock_workshop(s, a.workshop_id)
    query = asset_query(a).where(Asset.id == id)
    row = s.scalar(query.with_for_update() if version is not None else query)
    if not row:
        raise HTTPException(404, "Asset not found")
    if version is not None and row.version != version:
        raise HTTPException(409, "Asset changed; reload the record")
    return row


def revision(row, version):
    if row.version != version:
        raise HTTPException(409, "Record changed; reload it before saving")


def customer_site(s, p, a):
    scoped(s, Customer, p.customer_id, a)
    if p.site_id:
        site = scoped(s, Site, p.site_id, a)
        if site.customer_id != p.customer_id:
            raise HTTPException(422, "Site belongs to a different customer")


@router.get("/customer-records")
def customers(
    q: str = Query("", max_length=120),
    after: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    a=Depends(access),
):
    a.require("customers.read")
    with db() as s:
        query = select(Customer).where(
            Customer.workshop_id == a.workshop_id,
            or_(
                *(
                    column.contains(q, autoescape=True)
                    for column in [
                        Customer.name,
                        Customer.company_name,
                        Customer.email,
                        Customer.phone,
                        Customer.tax_id,
                    ]
                )
            ),
        )
        return page(s, query, Customer, after, limit)


@router.post("/customer-records", status_code=201)
def create_customer(p: CustomerRecord, a=Depends(access)):
    a.require("customers.write")
    a.write()
    full_scope(a)
    with db() as s:
        row = Customer(workshop_id=a.workshop_id, **p.model_dump())
        s.add(row)
        s.flush()
        event(s, a, None, "customer.created", {"customer_id": row.id})
        return serialized(row)


@router.get("/customer-records/{id}")
def customer(id: int, a=Depends(access)):
    a.require("customers.read")
    with db() as s:
        return serialized(scoped(s, Customer, id, a))


@router.patch("/customer-records/{id}")
def edit_customer(id: int, p: CustomerEdit, a=Depends(access)):
    a.require("customers.write")
    a.write()
    full_scope(a)
    with db() as s:
        lock_workshop(s, a.workshop_id)
        row = scoped(s, Customer, id, a)
        revision(row, p.version)
        before = serialized(row)
        for key, value in p.model_dump(exclude={"version"}).items():
            setattr(row, key, value)
        row.version += 1
        event(
            s,
            a,
            None,
            "customer.updated",
            {"customer_id": id, "before": before, "after": serialized(row)},
        )
        return serialized(row)


@router.get("/sites")
def sites(
    customer_id: int | None = None,
    after: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    a=Depends(access),
):
    a.require("customers.read")
    with db() as s:
        query = select(Site).where(Site.workshop_id == a.workshop_id)
        if customer_id:
            scoped(s, Customer, customer_id, a)
            query = query.where(Site.customer_id == customer_id)
        return page(s, query, Site, after, limit)


@router.post("/sites", status_code=201)
def create_site(p: SiteInput, a=Depends(access)):
    a.require("customers.write")
    a.write()
    full_scope(a)
    with db() as s:
        scoped(s, Customer, p.customer_id, a)
        row = Site(workshop_id=a.workshop_id, **p.model_dump())
        s.add(row)
        s.flush()
        event(
            s,
            a,
            None,
            "site.created",
            {"site_id": row.id, "customer_id": row.customer_id},
        )
        return serialized(row)


@router.get("/sites/{id}")
def site(id: int, a=Depends(access)):
    a.require("customers.read")
    with db() as s:
        return serialized(scoped(s, Site, id, a))


@router.patch("/sites/{id}")
def edit_site(id: int, p: SiteEdit, a=Depends(access)):
    a.require("customers.write")
    a.write()
    full_scope(a)
    with db() as s:
        lock_workshop(s, a.workshop_id)
        row = scoped(s, Site, id, a)
        revision(row, p.version)
        scoped(s, Customer, p.customer_id, a)
        if p.customer_id != row.customer_id:
            raise HTTPException(422, "Create a new site to change its customer")
        for key, value in p.model_dump(exclude={"version"}).items():
            setattr(row, key, value)
        row.version += 1
        event(s, a, None, "site.updated", {"site_id": id})
        return serialized(row)


@router.get("/assets")
def assets(
    q: str = Query("", max_length=120),
    customer_id: int | None = None,
    after: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    a=Depends(access),
):
    a.require("assets.read")
    with db() as s:
        query = asset_query(a).where(
            or_(
                *(
                    column.contains(q, autoescape=True)
                    for column in [
                        Asset.name,
                        Asset.model,
                        Asset.serial,
                        Asset.external_id,
                        Asset.manufacturer,
                    ]
                )
            )
        )
        if customer_id:
            scoped(s, Customer, customer_id, a)
            query = query.where(Asset.customer_id == customer_id)
        return page(s, query, Asset, after, limit)


@router.post("/assets", status_code=201)
def create_asset(p: AssetInput, a=Depends(access)):
    a.require("assets.write")
    a.write()
    full_scope(a)
    try:
        with db() as s:
            customer_site(s, p, a)
            row = Asset(workshop_id=a.workshop_id, **p.model_dump())
            s.add(row)
            s.flush()
            event(s, a, None, "asset.created", {"asset_id": row.id})
            return serialized(row)
    except IntegrityError:
        raise HTTPException(409, "An asset with this external ID already exists")


@router.get("/assets/{id}")
def asset(id: int, a=Depends(access)):
    with db() as s:
        return serialized(asset_record(s, id, a))


@router.patch("/assets/{id}")
def edit_asset(id: int, p: AssetEdit, a=Depends(access)):
    a.require("assets.write")
    try:
        with db() as s:
            row = asset_record(s, id, a, p.version)
            customer_site(s, p, a)
            if p.customer_id != row.customer_id:
                raise HTTPException(
                    422,
                    "Changing an asset's customer requires a separate ownership transfer",
                )
            changes = {
                key: {"before": getattr(row, key), "after": value}
                for key, value in p.model_dump(exclude={"version"}).items()
                if getattr(row, key) != value
            }
            for key, value in p.model_dump(exclude={"version"}).items():
                setattr(row, key, value)
            row.version += 1
            row.updated_at = utc()
            event(s, a, None, "asset.updated", {"asset_id": id, "changes": changes})
            return serialized(row)
    except IntegrityError:
        raise HTTPException(409, "An asset with this external ID already exists")


@router.get("/assets/{id}/jobs")
def asset_jobs(
    id: int,
    after: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    a=Depends(access),
):
    a.require("jobs.read")
    with db() as s:
        asset_record(s, id, a)
        query = select(RepairOrder).where(
            *order_filters(a), RepairOrder.device_id == id
        )
        return page(s, query, RepairOrder, after, limit, lambda row: summary(s, row, a))


@router.get("/assets/{id}/files")
def asset_files(
    id: int,
    after: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    a=Depends(access),
):
    a.require("jobs.read")
    with db() as s:
        asset_record(s, id, a)
        query = (
            select(Attachment, RepairOrder)
            .join(RepairOrder, RepairOrder.id == Attachment.order_id)
            .where(
                *order_filters(a),
                RepairOrder.device_id == id,
                Attachment.workshop_id == a.workshop_id,
            )
        )
        if after:
            query = query.where(Attachment.id > after)
        rows = s.execute(query.order_by(Attachment.id).limit(limit + 1)).all()
        return {
            "items": [
                {
                    "id": f.id,
                    "filename": f.filename,
                    "job_id": o.public_id,
                    "phase": f.phase,
                    "created_at": f.created_at,
                }
                for f, o in rows[:limit]
                if f.id not in restricted_attachment_ids(o, a)
            ],
            "next": rows[limit - 1][0].id if len(rows) > limit else None,
        }


@router.get("/assets/{id}/label", response_class=HTMLResponse)
def asset_label(id: int, a=Depends(access)):
    with db() as s:
        row = asset_record(s, id, a)
        base = os.getenv("PUBLIC_URL", "").rstrip("/")
        if not base:
            raise HTTPException(503, "PUBLIC_URL is required to print QR labels")
        url = f"{base}/assets/{row.id}?workshop={a.workshop_id}"
        return HTMLResponse(
            '<!doctype html><meta charset="utf-8"><title>Asset label</title><style>@page{size:62mm 40mm;margin:2mm}body{font:12px sans-serif;margin:0;display:flex;align-items:center}svg{width:30mm;height:30mm}span{overflow-wrap:anywhere;max-width:28mm}</style>'
            + qr_svg(url)
            + "<span>"
            + html.escape(row.name or row.model)
            + "<br>"
            + html.escape(row.serial)
            + "</span>"
        )
