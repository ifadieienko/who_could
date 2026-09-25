"""workflows / routes domain. Legacy API behavior is preserved."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from uuid import uuid4
from app.core.tenancy.records import scoped
from app.database import db
from app.repair_access import access, event
from app.repair_models import Workflow, Workshop
from app.repair_schemas import WorkflowInput

router = APIRouter()


@router.get("/workflows")
def workflows(a=Depends(access)):
    a.require("orders.read")
    with db() as s:
        return [
            {"id": w.id, "name": w.name, "revision": w.revision, "stages": w.stages}
            for w in s.scalars(
                select(Workflow).where(
                    Workflow.workshop_id == a.workshop_id, Workflow.archived.is_(False)
                )
            ).all()
        ]


@router.post("/workflows", status_code=201)
def create_workflow(p: WorkflowInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        w = Workflow(
            workshop_id=a.workshop_id,
            name=p.name,
            family=str(uuid4()),
            stages=[x.model_dump() for x in p.stages],
        )
        s.add(w)
        s.flush()
        event(s, a, None, "workflow.created", {"id": w.id})
        return {"id": w.id}


@router.post("/workflows/{id}/version", status_code=201)
def workflow_version(id: int, p: WorkflowInput, a=Depends(access)):
    a.require("templates.manage")
    a.write()
    with db() as s:
        old = scoped(s, Workflow, id, a)
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        revision = (
            s.scalar(
                select(Workflow.revision)
                .where(
                    Workflow.workshop_id == a.workshop_id, Workflow.family == old.family
                )
                .order_by(Workflow.revision.desc())
                .limit(1)
                .with_for_update()
            )
            or 0
        ) + 1
        w = Workflow(
            workshop_id=a.workshop_id,
            name=p.name,
            family=old.family,
            revision=revision,
            stages=[x.model_dump() for x in p.stages],
        )
        s.add(w)
        s.flush()
        old.archived = True
        event(s, a, None, "workflow.version", {"old": id, "new": w.id})
        return {"id": w.id}

