"""organizations / routes domain. Legacy API behavior is preserved."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.core.tenancy.records import scoped
from app.database import db
from app.models import User
from app.plans import enforce_limit
from app.repair_access import access, current_user, event
from app.repair_defaults import PERMISSIONS
from app.repair_models import Membership, Workshop, WorkshopRole
from app.repair_schemas import MemberEdit, MemberInput, RoleInput
from app.security import hash_password
from app.core.permissions import effective_permissions
from app.organizations.schemas import OrganizationEdit

router = APIRouter()


@router.get("/organizations")
@router.get("/workshops")
def workshops(user=Depends(current_user)):
    with db() as s:
        return [
            {
                "id": w.id,
                "name": w.name,
                **organization_metadata(w),
                "permissions": sorted(effective_permissions(r.permissions, r.is_owner)),
                "scope": r.scope,
                "owner": r.is_owner,
                "billing_status": w.billing_status,
                "trial_until": w.trial_until,
                "paid_until": w.paid_until,
            }
            for w, m, r in s.execute(
                select(Workshop, Membership, WorkshopRole)
                .join(Membership, Membership.workshop_id == Workshop.id)
                .join(WorkshopRole, WorkshopRole.id == Membership.role_id)
                .where(Membership.user_id == user["id"], Membership.active.is_(True))
            ).all()
        ]


@router.get("/members")
def members(a=Depends(access)):
    a.require("orders.read")
    with db() as s:
        return [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email if "members.manage" in a.permissions else None,
                "active": m.active,
                "role_id": r.id,
                "role": r.name,
                "owner": r.is_owner,
            }
            for m, u, r in s.execute(
                select(Membership, User, WorkshopRole)
                .join(User, User.id == Membership.user_id)
                .join(WorkshopRole, WorkshopRole.id == Membership.role_id)
                .where(Membership.workshop_id == a.workshop_id)
            ).all()
        ]


@router.get("/roles")
def roles(a=Depends(access)):
    a.require("members.manage")
    with db() as s:
        return {
            "permissions": PERMISSIONS,
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "permissions": sorted(effective_permissions(r.permissions, r.is_owner)),
                    "scope": r.scope,
                    "owner": r.is_owner,
                }
                for r in s.scalars(
                    select(WorkshopRole).where(
                        WorkshopRole.workshop_id == a.workshop_id
                    )
                ).all()
            ],
        }


@router.post("/roles", status_code=201)
def create_role(p: RoleInput, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        if s.scalar(
            select(WorkshopRole).where(
                WorkshopRole.workshop_id == a.workshop_id, WorkshopRole.name == p.name
            )
        ):
            raise HTTPException(409, "Роль уже существует")
        r = WorkshopRole(workshop_id=a.workshop_id, **p.model_dump())
        s.add(r)
        s.flush()
        event(s, a, None, "role.created", {"role": r.id})
        return {"id": r.id}


@router.put("/roles/{id}")
def edit_role(id: int, p: RoleInput, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        r = scoped(s, WorkshopRole, id, a)
        if r.is_owner:
            raise HTTPException(409, "Права владельца не изменяются")
        if s.scalar(
            select(WorkshopRole).where(
                WorkshopRole.workshop_id == a.workshop_id,
                WorkshopRole.name == p.name,
                WorkshopRole.id != id,
            )
        ):
            raise HTTPException(409, "Роль уже существует")
        for k, v in p.model_dump().items():
            setattr(r, k, v)
        event(s, a, None, "role.updated", {"role": id})
        return {"id": id}


@router.post("/members", status_code=201)
def add_member(p: MemberInput, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        enforce_limit(s, a.workshop_id, "members")
        r = scoped(s, WorkshopRole, p.role_id, a)
        if r.is_owner:
            raise HTTPException(422, "Назначьте рабочую роль")
        if s.scalar(select(User).where(User.email == str(p.email).lower())):
            raise HTTPException(
                409,
                "Аккаунт с этим email уже существует. Используйте отдельный рабочий email.",
            )
        u = User(
            name=p.name,
            email=str(p.email).lower(),
            password_hash=hash_password(p.password),
        )
        s.add(u)
        s.flush()
        s.add(Membership(workshop_id=a.workshop_id, user_id=u.id, role_id=r.id))
        event(s, a, None, "member.created", {"user": u.id})
        return {"id": u.id}


@router.patch("/members/{id}")
def edit_member(id: int, p: MemberEdit, a=Depends(access)):
    a.require("members.manage")
    a.write()
    with db() as s:
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        m = s.scalar(
            select(Membership).where(
                Membership.workshop_id == a.workshop_id, Membership.user_id == id
            )
        )
        if not m:
            raise HTTPException(404, "Сотрудник не найден")
        old = s.get(WorkshopRole, m.role_id)
        new = scoped(s, WorkshopRole, p.role_id, a)
        if new.is_owner and not old.is_owner:
            raise HTTPException(
                422, "Передача роли владельца требует отдельной процедуры"
            )
        if old.is_owner and (not p.active or not new.is_owner):
            raise HTTPException(409, "Владелец сохраняет доступ")
        if p.active and not m.active:
            enforce_limit(s, a.workshop_id, "members")
        m.role_id = new.id
        m.active = p.active
        event(
            s,
            a,
            None,
            "member.updated",
            {"user": id, "active": p.active, "role": p.role_id},
        )
        return {"id": id}



def organization_metadata(w):
    return {key: getattr(w, key) for key in ("vertical_key", "locale", "timezone", "currency", "country", "settings", "version")}


@router.get("/organization")
def organization(a=Depends(access)):
    with db() as s:
        w = s.get(Workshop, a.organization_id)
        return {"id": w.id, "name": w.name, **organization_metadata(w)}


@router.patch("/organization")
def update_organization(p: OrganizationEdit, a=Depends(access)):
    a.require("organization.manage")
    a.write()
    with db() as s:
        w = s.scalar(select(Workshop).where(Workshop.id == a.organization_id).with_for_update())
        if w.version != p.version:
            raise HTTPException(409, "Organization changed; reload settings")
        before = {"name": w.name, **organization_metadata(w)}
        for key, value in p.model_dump(exclude={"version"}).items():
            setattr(w, key, value)
        w.version += 1
        after = {"name": w.name, **organization_metadata(w)}
        event(s, a, None, "organization.updated", {"before": before, "after": after})
        return {"id": w.id, **after}
