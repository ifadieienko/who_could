"""Generic Job API and explicit compatibility routes to the shared lifecycle."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute
from app.assets.routes import asset_record
from app.core.tenancy.records import scoped
from app.database import db
from app.jobs.schemas import JobInput
from app.jobs.service import create_job_record
from app.jobs.serialization import detail
from app.jobs.routes import router as lifecycle_router
from app.jobs.finance_routes import router as finance_router
from app.repair_files import router as files_router
from app.repair_access import access
from app.repair_models import Site
from app.repair_schemas import OrderInput

router = APIRouter(prefix="/v2", tags=["jobs"])


@router.post("/jobs", status_code=201)
def create_job(p: JobInput, a=Depends(access)):
    a.require("jobs.create")
    a.require("customers.read")
    a.write()
    with db() as s:
        asset = asset_record(s, p.asset_id, a)
        if asset.status != "active":
            raise HTTPException(409, "Choose an active asset")
        if p.site_id:
            site = scoped(s, Site, p.site_id, a)
            if site.customer_id != asset.customer_id:
                raise HTTPException(422, "Site belongs to a different customer")
        data = OrderInput(
            template_id=p.template_id,
            workflow_id=p.workflow_id,
            device_id=asset.id,
            customer_id=asset.customer_id,
            problem=p.description,
            values=p.values,
            stage_forms=p.stage_forms,
            due_at=p.due_at,
            draft=p.draft,
        )
        job = create_job_record(
            s, data, a, job_type=p.job_type, priority=p.priority, site_id=p.site_id
        )
        return detail(s, job, a)


# Copy routing metadata, not implementations. Every old/new URL uses the same
# permission checks, tenant filters, version locks and transition guards.
for source in (lifecycle_router, finance_router, files_router):
    for route in source.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path.removeprefix("/v2")
        if not path.startswith("/orders") or (
            path == "/orders" and "POST" in route.methods
        ):
            continue
        router.add_api_route(
            path.replace("/orders", "/jobs", 1),
            route.endpoint,
            methods=list(route.methods),
            status_code=route.status_code,
            response_class=route.response_class,
            name="jobs_" + route.name,
            response_model=route.response_model,
        )
