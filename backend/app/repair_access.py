import os
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select, or_
from .database import db
from .models import User
from .repair_models import (
    LoginSession,
    Membership,
    WorkshopRole,
    Workshop,
    RepairOrder,
    RepairEvent,
)
from .security import SESSION_COOKIE_NAME, read_token
from .core.permissions import effective_permissions


def utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def dt(v):
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v and v.tzinfo else v


def current_user(request: Request):
    token = read_token(request.cookies.get(SESSION_COOKIE_NAME, ""))
    if not token:
        raise HTTPException(401, "Войдите в систему")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin", "").rstrip("/")
        expected = f"{request.url.scheme}://{request.headers.get('host','')}"
        allowed = {expected}
        if os.getenv("WHO_COULD_ENV") == "development":
            allowed |= {"http://localhost:5173", "http://127.0.0.1:5173"}
        if origin not in allowed:
            raise HTTPException(403, "Недопустимый источник запроса")
    with db() as s:
        login = s.get(
            LoginSession,
            hashlib.sha256(request.cookies[SESSION_COOKIE_NAME].encode()).hexdigest(),
        )
        if not login or login.expires_at < utc():
            raise HTTPException(401, "Сессия завершена")
        user = s.get(User, token["sub"])
        if not user:
            raise HTTPException(401, "Пользователь не найден")
        return {"id": user.id, "name": user.name, "email": user.email}


@dataclass
class Access:
    user_id: int
    workshop_id: int
    permissions: set
    scope: str
    owner: bool
    writable: bool

    def __post_init__(self):
        self.permissions = effective_permissions(self.permissions, self.owner)

    @property
    def organization_id(self):
        return self.workshop_id

    def require(self, p):
        if p not in self.permissions:
            raise HTTPException(403, "Недостаточно прав: " + p)

    def write(self):
        if not self.writable:
            raise HTTPException(
                402, "Подписка истекла. Чтение и экспорт остаются доступны."
            )


def access(user=Depends(current_user), x_workshop_id: int | None = Header(None), x_organization_id: int | None = Header(None)):
    if x_workshop_id is not None and x_organization_id is not None and x_workshop_id != x_organization_id:
        raise HTTPException(400, "Conflicting organization headers")
    tenant_id = x_organization_id if x_organization_id is not None else x_workshop_id
    if tenant_id is None or tenant_id < 1:
        raise HTTPException(422, "Organization header required")
    with db() as s:
        row = s.execute(
            select(Membership, WorkshopRole, Workshop)
            .join(WorkshopRole, WorkshopRole.id == Membership.role_id)
            .join(Workshop, Workshop.id == Membership.workshop_id)
            .where(
                Membership.user_id == user["id"],
                Membership.workshop_id == tenant_id,
                Membership.active.is_(True),
            )
        ).first()
        if not row:
            raise HTTPException(403, "Нет доступа к мастерской")
        m, r, w = row
        until = w.paid_until if w.stripe_subscription else w.trial_until
        writable = os.getenv("BILLING_ENFORCED", "false").lower() != "true" or (
            until is not None and until + timedelta(days=7) > utc()
        )
        return Access(
            user["id"], w.id, set(r.permissions), r.scope, r.is_owner, writable
        )


def order_filters(a):
    out = [RepairOrder.workshop_id == a.workshop_id]
    if a.scope == "own":
        out.append(
            or_(RepairOrder.assigned_to == a.user_id, RepairOrder.assigned_to.is_(None))
        )
    return out


def get_order(s, a, public_id, version=None):
    a.require("orders.read")
    query = select(RepairOrder).where(
        *order_filters(a), RepairOrder.public_id == public_id
    )
    if version is not None:
        from .plans import lock_workshop

        lock_workshop(s, a.workshop_id)
        query = query.with_for_update()
    o = s.scalar(query)
    if not o:
        raise HTTPException(404, "Заказ не найден")
    if version is not None:
        a.write()
        if o.version != version:
            raise HTTPException(
                409, "Заказ изменён другим сотрудником. Обновите карточку."
            )
    return o


def touch(o):
    o.version += 1
    o.updated_at = utc()


def event(s, a, o, kind, data=None):
    s.add(
        RepairEvent(
            workshop_id=a.workshop_id,
            order_id=o.id if o else None,
            actor_id=a.user_id,
            kind=kind,
            data=data or {},
        )
    )
