"""customers / routes domain. Legacy API behavior is preserved."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from app.core.tenancy.records import scoped
from app.database import db
from app.repair_access import access
from app.repair_models import Customer, Device

router = APIRouter()


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
def devices(
    customer_id: int,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    a=Depends(access),
):
    a.require("contacts.read")
    with db() as s:
        scoped(s, Customer, customer_id, a)
        return [
            {"id": d.id, "model": d.model, "serial": d.serial}
            for d in s.scalars(
                select(Device)
                .order_by(Device.id)
                .limit(limit)
                .where(
                    Device.workshop_id == a.workshop_id,
                    Device.customer_id == customer_id,
                    Device.id > after,
                )
            ).all()
        ]
