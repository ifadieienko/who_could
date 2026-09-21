"""Server-owned entitlements. Resource growth is serialized per workshop."""

import os
from fastapi import HTTPException
from sqlalchemy import select, func
from .repair_models import Workshop, Membership, RepairOrder, Attachment

PLANS = {
    "starter": {
        "name": "Starter",
        "members": 3,
        "open_orders": 100,
        "storage_bytes": 1024**3,
    },
    "pro": {
        "name": "Pro",
        "members": 15,
        "open_orders": 1000,
        "storage_bytes": 10 * 1024**3,
    },
    "business": {
        "name": "Business",
        "members": 50,
        "open_orders": 10000,
        "storage_bytes": 50 * 1024**3,
    },
}


def price_for(plan):
    return os.getenv("STRIPE_PRICE_" + plan.upper()) or (
        os.getenv("STRIPE_PRICE_ID") if plan == "starter" else None
    )


def plan_for_subscription(sub):
    prices = [
        item.get("price", {}).get("id") for item in sub.get("items", {}).get("data", [])
    ]
    matches = [
        code for code in PLANS if price_for(code) and prices == [price_for(code)]
    ]
    if len(matches) != 1:
        raise HTTPException(
            409, "Подписка содержит неизвестный или неоднозначный тариф"
        )
    return matches[0]


def lock_workshop(s, workshop_id):
    return s.scalar(
        select(Workshop).where(Workshop.id == workshop_id).with_for_update()
    )


def usage(s, workshop_id):
    return {
        "members": s.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workshop_id == workshop_id, Membership.active.is_(True))
        ),
        "open_orders": s.scalar(
            select(func.count())
            .select_from(RepairOrder)
            .where(
                RepairOrder.workshop_id == workshop_id,
                RepairOrder.status.notin_(["issued", "cancelled"]),
            )
        ),
        # Normalized originals; thumbnails are supplementary and do not consume the customer quota.
        "storage_bytes": int(
            s.scalar(
                select(func.coalesce(func.sum(Attachment.size), 0)).where(
                    Attachment.workshop_id == workshop_id
                )
            )
        ),
    }


def enforce_limit(s, workshop_id, resource, increment=1):
    workshop = lock_workshop(s, workshop_id)
    limit = PLANS.get(workshop.plan, PLANS["starter"])[resource]
    # Flush preceding writes (notably CSV imports) before counting usage.
    s.flush()
    if usage(s, workshop_id)[resource] + increment > limit:
        labels = {
            "members": "активных сотрудников",
            "open_orders": "открытых заказов",
            "storage_bytes": "хранилища фотографий",
        }
        raise HTTPException(
            402,
            f"Достигнут лимит {labels[resource]}. Освободите ресурс или смените тариф.",
        )
