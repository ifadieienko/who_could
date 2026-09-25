"""Compatibility entry point for the repair API.

Domain modules own implementations; existing callers keep their imports and URLs.
"""
from fastapi import APIRouter
from app.organizations.service import seed_workshop
from app.jobs.service import create_order_record
from app.core.tenancy.records import scoped
from app.forms.service import restricted_attachment_ids
from app.organizations.routes import router as organizations_router
from app.forms.routes import router as forms_router
from app.workflows.routes import router as workflows_router
from app.customers.routes import router as customers_router
from app.jobs.finance_routes import router as finance_router
from app.core.mail.routes import router as mail_router
from app.jobs.routes import router as jobs_router

router = APIRouter(prefix="/v2", tags=["workshops"])
router.include_router(organizations_router)
router.include_router(forms_router)
router.include_router(workflows_router)
router.include_router(customers_router)
router.include_router(finance_router)
router.include_router(mail_router)
router.include_router(jobs_router)
