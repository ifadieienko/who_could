"""Workshop API. Legacy marketplace/admin routes are deliberately not mounted."""

from contextlib import asynccontextmanager
import hashlib
import os
import secrets
from datetime import timedelta
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, delete, text
from sqlalchemy.exc import IntegrityError
from .database import db
from .models import User
from .security import (
    SESSION_COOKIE_NAME,
    TOKEN_TTL_SECONDS,
    hash_password,
    verify_password,
    create_token,
)
from .repair_access import current_user, access, utc
from .repair_models import LoginSession, AccountToken, Membership, Outbox
from .repairs import router, seed_workshop
from .repair_files import router as files_router
from .quote_portal import router as quote_router


@asynccontextmanager
async def lifespan(app):
    from .legacy_photos import migrate

    migrate()
    yield


app = FastAPI(title="Who Could — Workshop", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        os.getenv("PUBLIC_HOSTNAME", "localhost"),
        "localhost",
        "127.0.0.1",
        "testserver",
    ],
)
if os.getenv("WHO_COULD_ENV") == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Content-Type", "X-Workshop-Id", "X-Organization-Id"],
    )


@app.middleware("http")
async def private_responses(request, call_next):
    if (
        request.url.path.startswith("/auth/")
        and request.method == "POST"
        and request.headers.get("origin")
    ):
        expected = f"{request.url.scheme}://{request.headers.get('host','')}"
        allowed = {expected}
        if os.getenv("WHO_COULD_ENV") == "development":
            allowed |= {"http://localhost:5173", "http://127.0.0.1:5173"}
        if request.headers["origin"].rstrip("/") not in allowed:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"detail": "Недопустимый источник запроса"}, status_code=403
            )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class Registration(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=120)
    workshop: str = Field(min_length=2, max_length=160)

    @field_validator("name", "workshop", mode="before")
    @classmethod
    def trim(cls, v):
        return v.strip() if isinstance(v, str) else v


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=120)


def session(s, u, response, request):
    token = create_token(u.id)
    s.add(
        LoginSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=u.id,
            expires_at=utc() + timedelta(seconds=TOKEN_TTL_SECONDS),
        )
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )
    return {"user": {"id": u.id, "name": u.name, "email": u.email}}


@app.post("/auth/register", status_code=201)
def register(p: Registration, request: Request, response: Response):
    try:
        with db() as s:
            u = User(
                name=p.name.strip(),
                email=str(p.email).lower(),
                password_hash=hash_password(p.password),
            )
            s.add(u)
            s.flush()
            seed_workshop(s, u, p.workshop.strip())
            return session(s, u, response, request)
    except IntegrityError:
        raise HTTPException(409, "Email уже зарегистрирован")


@app.post("/auth/login")
def login(p: Login, request: Request, response: Response):
    with db() as s:
        u = s.scalar(select(User).where(User.email == str(p.email).lower()))
        if not u or not verify_password(p.password, u.password_hash):
            raise HTTPException(401, "Неверный email или пароль")
        return session(s, u, response, request)


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, user=Depends(current_user)):
    with db() as s:
        s.execute(
            delete(LoginSession).where(
                LoginSession.token_hash
                == hashlib.sha256(
                    request.cookies[SESSION_COOKIE_NAME].encode()
                ).hexdigest()
            )
        )
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )


@app.get("/me")
def me(user=Depends(current_user)):
    return user


@app.get("/health")
def health():
    with db() as s:
        s.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


class ResetRequest(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str = Field(max_length=100)
    password: str = Field(min_length=12, max_length=120)


@app.post("/auth/reset-request")
def reset_request(p: ResetRequest):
    base = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not base or not os.getenv("SMTP_HOST") or not os.getenv("SMTP_FROM"):
        raise HTTPException(503, "Восстановление почтой пока не настроено")
    with db() as s:
        u = s.scalar(select(User).where(User.email == str(p.email).lower()))
        if u:
            m = s.scalar(select(Membership).where(Membership.user_id == u.id).limit(1))
            if m:
                token = secrets.token_urlsafe(32)
                s.add(
                    AccountToken(
                        user_id=u.id,
                        token_hash=hashlib.sha256(token.encode()).hexdigest(),
                        expires_at=utc() + timedelta(minutes=30),
                    )
                )
                s.add(
                    Outbox(
                        workshop_id=m.workshop_id,
                        order_id=None,
                        recipient=u.email,
                        subject="Сброс пароля",
                        body=base + "/reset/" + token,
                        dedupe_key="reset:" + secrets.token_hex(16),
                    )
                )
    return {"message": "Если аккаунт существует, инструкция отправлена на email."}


@app.post("/auth/reset-password")
def reset_password(p: ResetPassword):
    with db() as s:
        token = s.scalar(
            select(AccountToken)
            .where(
                AccountToken.token_hash == hashlib.sha256(p.token.encode()).hexdigest()
            )
            .with_for_update()
        )
        if not token or token.used or token.expires_at < utc():
            raise HTTPException(410, "Ссылка недоступна")
        u = s.get(User, token.user_id)
        u.password_hash = hash_password(p.password)
        token.used = True
        s.execute(delete(LoginSession).where(LoginSession.user_id == u.id))
    return {"message": "Пароль изменён. Войдите заново."}


app.include_router(router)
app.include_router(files_router)
app.include_router(quote_router)
from .repair_transfer import router as transfer_router

app.include_router(transfer_router)
from .billing import router as billing_router

app.include_router(billing_router)
from .warehouse import build_warehouse_router


def warehouse_access(a=Depends(access), request: Request = None):
    a.require("warehouse.manage")
    if request and request.method != "GET":
        a.write()
    return {"id": a.user_id, "workshop_id": a.workshop_id}


app.include_router(build_warehouse_router(warehouse_access))

from .assets.routes import router as assets_router
app.include_router(assets_router)

from .jobs.api import router as jobs_router
app.include_router(jobs_router)
