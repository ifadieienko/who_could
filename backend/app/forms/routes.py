"""forms / routes domain. Legacy API behavior is preserved."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from uuid import uuid4
from app.core.tenancy.records import scoped
from app.database import db
from app.repair_access import access, event
from app.repair_models import FormTemplate, Workshop
from app.repair_schemas import TemplateInput

router = APIRouter()


@router.get("/templates")
def templates(a=Depends(access)):
    a.require("orders.read")
    with db() as s:
        return [
            {
                "id": t.id,
                "name": t.name,
                "purpose": t.purpose,
                "revision": t.revision,
                "published": t.published,
                "archived": t.archived,
                "columns": t.layout.get("columns", 2),
                "fields": [
                    f
                    for f in t.fields
                    if not f.get("read_permission")
                    or f["read_permission"] in a.permissions
                ],
            }
            for t in s.scalars(
                select(FormTemplate).where(
                    FormTemplate.workshop_id == a.workshop_id,
                    FormTemplate.archived.is_(False),
                )
            ).all()
        ]


@router.post("/templates", status_code=201)
def create_template(p: TemplateInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = FormTemplate(
            workshop_id=a.workshop_id,
            family=str(uuid4()),
            name=p.name,
            purpose=p.purpose,
            fields=[f.model_dump() for f in p.fields],
            layout={"columns": p.columns},
        )
        s.add(t)
        s.flush()
        event(s, a, None, "template.created", {"id": t.id})
        return {"id": t.id}


@router.put("/templates/{id}")
def edit_template(id: int, p: TemplateInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        if t.published:
            raise HTTPException(409, "Создайте новую версию опубликованного шаблона")
        t.name = p.name
        t.purpose = p.purpose
        t.fields = [f.model_dump() for f in p.fields]
        t.layout = {"columns": p.columns}
        event(s, a, None, "template.edited", {"id": id})
        return {"id": id}


@router.post("/templates/{id}/version", status_code=201)
def template_version(id: int, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        # Serialise revision assignment through a workshop row lock.
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        revision = (
            s.scalar(
                select(FormTemplate.revision)
                .where(
                    FormTemplate.workshop_id == a.workshop_id,
                    FormTemplate.family == t.family,
                )
                .order_by(FormTemplate.revision.desc())
                .limit(1)
                .with_for_update()
            )
            or 0
        ) + 1
        new = FormTemplate(
            workshop_id=a.workshop_id,
            family=t.family,
            name=t.name,
            purpose=t.purpose,
            revision=revision,
            fields=t.fields,
            layout=t.layout,
        )
        s.add(new)
        s.flush()
        return {"id": new.id}


@router.post("/templates/{id}/publish")
def publish_template(id: int, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        t.published = True
        event(s, a, None, "template.published", {"id": id})
        return {"id": id}


@router.post("/templates/{id}/archive")
def archive_template(id: int, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        t = scoped(s, FormTemplate, id, a)
        t.archived = True
        event(s, a, None, "template.archived", {"id": id})
        return {"id": id}

