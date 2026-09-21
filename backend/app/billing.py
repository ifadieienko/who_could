"""Stripe Checkout / customer portal. Secrets and price IDs are deployment settings."""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .database import db
from .repair_access import access
from .repair_models import Workshop, BillingEvent

router = APIRouter(tags=["billing"])


def stripe(path, data=None, key=None):
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret:
        raise HTTPException(503, "Оплата ещё не настроена")
    headers = {"Stripe-Version": "2024-06-20"}
    if key:
        headers["Idempotency-Key"] = key
    try:
        r = (
            httpx.post(
                "https://api.stripe.com/v1/" + path,
                data=data,
                auth=(secret, ""),
                headers=headers,
                timeout=20,
            )
            if data is not None
            else httpx.get(
                "https://api.stripe.com/v1/" + path,
                auth=(secret, ""),
                headers=headers,
                timeout=20,
            )
        )
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Платёжный сервис временно недоступен")


@router.get("/v2/billing")
def status(a=Depends(access)):
    a.require("billing.manage")
    with db() as s:
        w = s.get(Workshop, a.workshop_id)
        return {
            "status": w.billing_status,
            "trial_until": w.trial_until,
            "paid_until": w.paid_until,
            "writable": a.writable,
            "configured": bool(
                os.getenv("STRIPE_SECRET_KEY")
                and os.getenv("STRIPE_PRICE_ID")
                and os.getenv("PUBLIC_URL")
            ),
            "enforced": os.getenv("BILLING_ENFORCED", "false").lower() == "true",
        }


@router.post("/v2/billing/checkout")
def checkout(a=Depends(access)):
    a.require("billing.manage")
    price = os.getenv("STRIPE_PRICE_ID")
    base = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not price or not base:
        raise HTTPException(503, "Тариф или адрес приложения не настроен")
    with db() as s:
        w = s.scalar(
            select(Workshop).where(Workshop.id == a.workshop_id).with_for_update()
        )
        if w.stripe_subscription and w.billing_status not in {
            "canceled",
            "incomplete_expired",
        }:
            raise HTTPException(
                409, "Подписка уже создана. Используйте управление подпиской."
            )
        data = {
            "mode": "subscription",
            "line_items[0][price]": price,
            "line_items[0][quantity]": "1",
            "client_reference_id": str(w.id),
            "subscription_data[metadata][workshop_id]": str(w.id),
            "success_url": base + "/billing?success=1",
            "cancel_url": base + "/billing",
        }
        if w.stripe_customer:
            data["customer"] = w.stripe_customer
        result = stripe(
            "checkout/sessions", data, key=f"workshop-{w.id}-{int(time.time())//1800}"
        )
        return {"url": result["url"]}


@router.post("/v2/billing/portal")
def portal(a=Depends(access)):
    a.require("billing.manage")
    with db() as s:
        w = s.get(Workshop, a.workshop_id)
        if not w.stripe_customer:
            raise HTTPException(409, "Сначала оформите подписку")
        return {
            "url": stripe(
                "billing_portal/sessions",
                {
                    "customer": w.stripe_customer,
                    "return_url": os.getenv("PUBLIC_URL", "").rstrip("/") + "/billing",
                },
            )["url"]
        }


def verify_signature(raw, header, secret):
    try:
        parts = [x.split("=", 1) for x in header.split(",")]
        stamp = next(v for k, v in parts if k == "t")
        expected = hmac.new(
            secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        return abs(time.time() - int(stamp)) <= 300 and any(
            k == "v1" and hmac.compare_digest(v, expected) for k, v in parts
        )
    except (ValueError, StopIteration):
        return False


@router.post("/billing/webhook")
async def webhook(request: Request):
    raw = await request.body()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "Webhook не настроен")
    if len(raw) > 1024 * 1024 or not verify_signature(
        raw, request.headers.get("stripe-signature", ""), secret
    ):
        raise HTTPException(400, "Неверная подпись")
    try:
        ev = json.loads(raw)
        id = ev["id"]
        obj = ev["data"]["object"]
        kind = ev["type"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Некорректное событие")
    if kind not in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
    }:
        return {"received": True}
    # Fetch the authoritative current state so out-of-order deliveries cannot restore stale entitlement.
    subscription_id = (
        obj.get("subscription") if kind.startswith("invoice.") else obj.get("id")
    )
    if not isinstance(subscription_id, str) or not subscription_id.startswith("sub_"):
        return {"received": True}
    sub = stripe("subscriptions/" + subscription_id)
    try:
        wid = int(sub.get("metadata", {}).get("workshop_id", ""))
    except ValueError:
        return {"received": True}
    try:
        with db() as s:
            if s.get(BillingEvent, id):
                return {"received": True}
            w = s.scalar(select(Workshop).where(Workshop.id == wid).with_for_update())
            if not w:
                return {"received": True}
            sub = stripe(
                "subscriptions/" + subscription_id
            )  # refresh while holding the workshop lock
            if (
                w.stripe_subscription
                and w.stripe_subscription != subscription_id
                and w.billing_status not in {"canceled", "incomplete_expired"}
            ):
                raise HTTPException(409, "Другая действующая подписка")
            w.stripe_subscription = subscription_id
            w.stripe_customer = sub.get("customer")
            w.billing_status = sub["status"]
            end = sub.get("current_period_end", 0)
            if sub["status"] in {"active", "trialing"} and end:
                w.paid_until = datetime.fromtimestamp(end, timezone.utc).replace(
                    tzinfo=None
                )
            # Failed renewals retain the previously paid boundary plus the access layer's seven-day grace.
            if (
                sub["status"] in {"canceled", "unpaid", "incomplete_expired"}
                and w.paid_until is None
            ):
                w.trial_until = None
            s.add(BillingEvent(id=id))
    except IntegrityError:
        pass  # duplicate event delivery raced the primary key
    return {"received": True}
