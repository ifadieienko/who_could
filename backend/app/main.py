from typing import Annotated
from urllib.parse import urlsplit
import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import EmailStr
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import db
from .intake import build_router
from .models import Application, Job, Role, User, user_roles
from .schemas import AdminUserCreate, ApplicationCreate, ApplicationPublic, ApplicationStatus, ApplicationStatusUpdate, AuthResponse, BudgetType, Dashboard, Duration, JobCreate, JobPublic, JobStatusUpdate, RoleAssignmentUpdate, RoleCreate, RolePublic, UserCreate, UserLogin, UserPublic, WorkMode
from .security import SESSION_COOKIE_NAME, TOKEN_TTL_SECONDS, create_token, hash_password, read_token, verify_password
from .warehouse import build_warehouse_router

app = FastAPI(title="Who could...? API", version="0.8.0")
_public_hostname = os.getenv("PUBLIC_HOSTNAME", "localhost")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[_public_hostname, "localhost", "127.0.0.1", "testserver"])
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _time(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def role_dict(role: Role) -> dict:
    return {"id": role.id, "name": role.name, "description": role.description, "is_system": role.is_system, "created_at": _time(role.created_at)}


def user_dict(user: User) -> dict:
    roles = sorted((role_dict(role) for role in user.roles), key=lambda role: role["name"])
    return {"id": user.id, "name": user.name, "email": user.email, "city": user.city, "bio": user.bio, "skills": user.skills, "roles": roles, "created_at": _time(user.created_at)}


SYSTEM_ROLES = {
    "user": "Базовая роль пользователя",
    "admin": "Администратор: управление пользователями и ролями",
}


def ensure_system_roles(session: Session) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name, description in SYSTEM_ROLES.items():
        role = session.scalar(select(Role).where(Role.name == name))
        if not role:
            role = Role(name=name, description=description, is_system=True)
            session.add(role)
            session.flush()
        elif not role.is_system:
            role.is_system = True
        roles[name] = role
    return roles


def assign_registration_roles(session: Session, user: User) -> None:
    roles = ensure_system_roles(session)
    user.roles.append(roles["user"])
    bootstrap_email = os.getenv("WHO_COULD_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    if bootstrap_email and user.email.lower() == bootstrap_email:
        user.roles.append(roles["admin"])
        return
    if os.getenv("WHO_COULD_ENV", "production").lower() == "development":
        has_admin = session.scalar(select(user_roles.c.user_id).where(user_roles.c.role_id == roles["admin"].id).limit(1))
        if has_admin is None:
            user.roles.append(roles["admin"])


def _resolve_roles(session: Session, role_ids: list[int]) -> list[Role]:
    system = ensure_system_roles(session)
    requested = set(role_ids)
    requested.add(system["user"].id)
    roles = list(session.scalars(select(Role).where(Role.id.in_(requested)).order_by(Role.name)).all())
    found = {role.id for role in roles}
    missing = sorted(requested - found)
    if missing:
        raise HTTPException(422, f"Unknown role ids: {missing}")
    return roles


def _admin_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(user_roles.join(Role, Role.id == user_roles.c.role_id)).where(Role.name == "admin")) or 0)


def _external_scheme(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded if forwarded in {"http", "https"} else request.url.scheme


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    expected = f"{_external_scheme(request)}://{request.headers.get('host', '')}"
    if origin.rstrip("/") == expected.rstrip("/"):
        return True
    if os.getenv("WHO_COULD_ENV", "production").lower() == "development":
        return origin in {"http://127.0.0.1:5173", "http://localhost:5173"}
    return False


def _set_session_cookie(response: Response, request: Request, user_id: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_token(user_id),
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=_external_scheme(request) == "https",
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Authentication required")
    payload = read_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired session")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not _same_origin(request):
        raise HTTPException(403, "Cross-site authenticated request rejected")
    with db() as session:
        user = session.scalar(select(User).options(selectinload(User.roles)).where(User.id == payload["sub"]))
        if not user:
            raise HTTPException(401, "User not found")
        return user_dict(user)


app.include_router(build_router(current_user))
app.include_router(build_warehouse_router(current_user))


def require_admin(user: Annotated[dict, Depends(current_user)]) -> dict:
    if not any(role["name"] == "admin" for role in user["roles"]):
        raise HTTPException(403, "Administrator role required")
    return user


def find_user_by_email(email: EmailStr) -> dict | None:
    with db() as session:
        user = session.scalar(select(User).options(selectinload(User.roles)).where(func.lower(User.email) == str(email).lower()))
        return user_dict(user) | {"password_hash": user.password_hash} if user else None


def job_query(session: Session, *conditions) -> list[JobPublic]:
    count = func.count(Application.id)
    rows = session.execute(select(Job, User.name, count).join(User, User.id == Job.owner_id).outerjoin(Application, Application.job_id == Job.id).where(*conditions).group_by(Job.id, User.name).order_by(Job.created_at.desc())).all()
    return [JobPublic(**{"id": j.id, "owner_id": j.owner_id, "owner_name": owner, "title": j.title, "description": j.description, "category": j.category, "work_mode": j.work_mode, "duration": j.duration, "location": j.location, "budget_type": j.budget_type, "budget_min": j.budget_min, "budget_max": j.budget_max, "currency": j.currency, "deadline": j.deadline, "skills": j.skills, "status": j.status, "created_at": _time(j.created_at), "applications_count": total}) for j, owner, total in rows]


def application_query(session: Session, *conditions) -> list[ApplicationPublic]:
    rows = session.execute(select(Application, Job.title, Job.owner_id, User.name).join(Job, Job.id == Application.job_id).join(User, User.id == Application.applicant_id).where(*conditions).order_by(Application.created_at.desc())).all()
    return [ApplicationPublic(**{"id": a.id, "job_id": a.job_id, "job_title": title, "applicant_id": a.applicant_id, "applicant_name": name, "owner_id": owner, "message": a.message, "proposed_rate": a.proposed_rate, "estimated_time": a.estimated_time, "status": a.status, "created_at": _time(a.created_at)}) for a, title, owner, name in rows]


@app.get("/health")
def health() -> dict:
    with db() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: UserCreate, request: Request, response: Response):
    try:
        with db() as session:
            user = User(name=payload.name.strip(), email=str(payload.email).lower(), password_hash=hash_password(payload.password), city=payload.city, bio=payload.bio, skills=payload.skills)
            session.add(user)
            session.flush()
            assign_registration_roles(session, user)
            session.flush()
            public = UserPublic(**user_dict(user))
    except IntegrityError as exc:
        raise HTTPException(409, "Email is already registered") from exc
    _set_session_cookie(response, request, public.id)
    return AuthResponse(user=public)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: UserLogin, request: Request, response: Response):
    user = find_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    public = UserPublic(**{k: user[k] for k in UserPublic.model_fields})
    _set_session_cookie(response, request, public.id)
    return AuthResponse(user=public)


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, _user: Annotated[dict, Depends(current_user)]):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=_external_scheme(request) == "https", httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"


@app.get("/me", response_model=UserPublic)
def me(user: Annotated[dict, Depends(current_user)]):
    return UserPublic(**user)


@app.get("/admin/users", response_model=list[UserPublic])
def admin_list_users(_admin: Annotated[dict, Depends(require_admin)]):
    with db() as session:
        users = session.scalars(select(User).options(selectinload(User.roles)).order_by(User.created_at, User.id)).all()
        return [UserPublic(**user_dict(user)) for user in users]


@app.post("/admin/users", response_model=UserPublic, status_code=201)
def admin_create_user(payload: AdminUserCreate, _admin: Annotated[dict, Depends(require_admin)]):
    try:
        with db() as session:
            roles = _resolve_roles(session, payload.role_ids)
            user = User(name=payload.name.strip(), email=str(payload.email).lower(), password_hash=hash_password(payload.password), city=payload.city, bio=payload.bio, skills=payload.skills)
            user.roles = roles
            session.add(user)
            session.flush()
            return UserPublic(**user_dict(user))
    except IntegrityError as exc:
        raise HTTPException(409, "Email is already registered") from exc


@app.delete("/admin/users/{user_id}", status_code=204)
def admin_delete_user(user_id: int, admin: Annotated[dict, Depends(require_admin)]):
    if user_id == admin["id"]:
        raise HTTPException(409, "You cannot delete your own account")
    with db() as session:
        user = session.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))
        if not user:
            raise HTTPException(404, "User not found")
        if any(role.name == "admin" for role in user.roles) and _admin_count(session) <= 1:
            raise HTTPException(409, "The last administrator cannot be deleted")
        session.delete(user)
    return Response(status_code=204)


@app.get("/admin/roles", response_model=list[RolePublic])
def admin_list_roles(_admin: Annotated[dict, Depends(require_admin)]):
    with db() as session:
        roles = session.scalars(select(Role).order_by(Role.is_system.desc(), Role.name)).all()
        return [RolePublic(**role_dict(role)) for role in roles]


@app.post("/admin/roles", response_model=RolePublic, status_code=201)
def admin_create_role(payload: RoleCreate, _admin: Annotated[dict, Depends(require_admin)]):
    try:
        with db() as session:
            role = Role(name=payload.name, description=payload.description.strip() if payload.description else None, is_system=False)
            session.add(role)
            session.flush()
            return RolePublic(**role_dict(role))
    except IntegrityError as exc:
        raise HTTPException(409, "Role name already exists") from exc


@app.put("/admin/users/{user_id}/roles", response_model=UserPublic)
def admin_set_user_roles(user_id: int, payload: RoleAssignmentUpdate, admin: Annotated[dict, Depends(require_admin)]):
    with db() as session:
        user = session.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))
        if not user:
            raise HTTPException(404, "User not found")
        roles = _resolve_roles(session, payload.role_ids)
        had_admin = any(role.name == "admin" for role in user.roles)
        has_admin = any(role.name == "admin" for role in roles)
        if user_id == admin["id"] and had_admin and not has_admin:
            raise HTTPException(409, "You cannot remove your own administrator role")
        if had_admin and not has_admin and _admin_count(session) <= 1:
            raise HTTPException(409, "The last administrator must keep the admin role")
        user.roles = roles
        session.flush()
        return UserPublic(**user_dict(user))


@app.get("/jobs", response_model=list[JobPublic])
def list_jobs(q: str | None = Query(None, max_length=120), work_mode: WorkMode | None = None, duration: Duration | None = None, budget_type: BudgetType | None = None):
    conditions = [Job.status == "open"]
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(or_(func.lower(Job.title).like(pattern), func.lower(Job.description).like(pattern), func.lower(func.coalesce(Job.skills, "")).like(pattern)))
    for column, value in ((Job.work_mode, work_mode), (Job.duration, duration), (Job.budget_type, budget_type)):
        if value:
            conditions.append(column == value.value)
    with db() as session:
        return job_query(session, *conditions)


@app.post("/jobs", response_model=JobPublic, status_code=201)
def create_job(payload: JobCreate, user: Annotated[dict, Depends(current_user)]):
    with db() as session:
        job = Job(owner_id=user["id"], title=payload.title.strip(), description=payload.description.strip(), category=payload.category.strip(), work_mode=payload.work_mode.value, duration=payload.duration.value, location=payload.location, budget_type=payload.budget_type.value, budget_min=payload.budget_min, budget_max=payload.budget_max, currency=payload.currency, deadline=payload.deadline, skills=payload.skills)
        session.add(job)
        session.flush()
        return job_query(session, Job.id == job.id)[0]


@app.get("/jobs/{job_id}", response_model=JobPublic)
def get_job(job_id: int):
    with db() as session:
        jobs = job_query(session, Job.id == job_id)
    if not jobs:
        raise HTTPException(404, "Job not found")
    return jobs[0]


@app.patch("/jobs/{job_id}/status", response_model=JobPublic)
def update_job_status(job_id: int, payload: JobStatusUpdate, user: Annotated[dict, Depends(current_user)]):
    with db() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.owner_id != user["id"]:
            raise HTTPException(403, "Only the job owner can change its status")
        allowed = {"open": {"in_progress", "closed"}, "in_progress": {"closed"}, "closed": set()}
        if payload.status.value not in allowed[job.status]:
            raise HTTPException(409, f"Cannot change job status from {job.status} to {payload.status.value}")
        job.status = payload.status.value
        session.flush()
        return job_query(session, Job.id == job_id)[0]


@app.post("/jobs/{job_id}/applications", response_model=ApplicationPublic, status_code=201)
def apply_to_job(job_id: int, payload: ApplicationCreate, user: Annotated[dict, Depends(current_user)]):
    try:
        with db() as session:
            job = session.get(Job, job_id)
            if not job:
                raise HTTPException(404, "Job not found")
            if job.status != "open":
                raise HTTPException(409, "Job is not open")
            if job.owner_id == user["id"]:
                raise HTTPException(400, "You cannot apply to your own job")
            application = Application(job_id=job_id, applicant_id=user["id"], message=payload.message.strip(), proposed_rate=payload.proposed_rate, estimated_time=payload.estimated_time)
            session.add(application)
            session.flush()
            return application_query(session, Application.id == application.id)[0]
    except IntegrityError as exc:
        raise HTTPException(409, "You already applied to this job") from exc


@app.patch("/applications/{application_id}/status", response_model=ApplicationPublic)
def update_application_status(application_id: int, payload: ApplicationStatusUpdate, user: Annotated[dict, Depends(current_user)]):
    if payload.status is ApplicationStatus.sent:
        raise HTTPException(422, "Application status can only become accepted or declined")
    with db() as session:
        row = session.execute(select(Application, Job).join(Job).where(Application.id == application_id).with_for_update()).first()
        if not row:
            raise HTTPException(404, "Application not found")
        application, job = row
        if job.owner_id != user["id"]:
            raise HTTPException(403, "Only the job owner can manage applications")
        if application.status != "sent":
            raise HTTPException(409, f"Application is already {application.status}")
        if job.status != "open":
            raise HTTPException(409, "Applications can only be managed while the job is open")
        application.status = payload.status.value
        if payload.status is ApplicationStatus.accepted:
            job.status = "in_progress"
            session.execute(update(Application).where(Application.job_id == job.id, Application.id != application.id, Application.status == "sent").values(status="declined"))
        session.flush()
        return application_query(session, Application.id == application_id)[0]


@app.get("/dashboard", response_model=Dashboard)
def dashboard(user: Annotated[dict, Depends(current_user)]):
    with db() as session:
        return Dashboard(owned_jobs=job_query(session, Job.owner_id == user["id"]), sent_applications=application_query(session, Application.applicant_id == user["id"]), received_applications=application_query(session, Job.owner_id == user["id"]))
