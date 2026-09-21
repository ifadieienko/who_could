"""Workshop-owned records. User deactivation never deletes business history."""

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Workshop(Base):
    __tablename__ = "workshops"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    trial_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    billing_status: Mapped[str] = mapped_column(String(30), default="trialing")
    stripe_customer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_subscription: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan: Mapped[str] = mapped_column(String(30), default="starter")
    billing_updated: Mapped[int] = mapped_column(Integer, default=0)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkshopRole(Base):
    __tablename__ = "workshop_roles"
    __table_args__ = (UniqueConstraint("workshop_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshops.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    scope: Mapped[str] = mapped_column(String(10), default="all")
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)


class Membership(Base):
    __tablename__ = "workshop_members"
    __table_args__ = (UniqueConstraint("workshop_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshops.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("workshop_roles.id", ondelete="RESTRICT")
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FormTemplate(Base):
    __tablename__ = "repair_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    family: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(160))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose: Mapped[str] = mapped_column(String(20), default="intake")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    layout: Mapped[dict] = mapped_column(JSON, default=dict)


class Workflow(Base):
    __tablename__ = "repair_workflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    family: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    stages: Mapped[list] = mapped_column(JSON)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Customer(Base):
    __tablename__ = "repair_customers"
    __table_args__ = (UniqueConstraint("workshop_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Device(Base):
    __tablename__ = "repair_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("repair_customers.id"))
    model: Mapped[str] = mapped_column(String(160))
    serial: Mapped[str] = mapped_column(String(160), default="")


class RepairOrder(Base):
    __tablename__ = "repair_orders"
    __table_args__ = (UniqueConstraint("workshop_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_customers.id"), nullable=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_devices.id"), nullable=True, index=True
    )
    warranty_of: Mapped[int | None] = mapped_column(
        ForeignKey("repair_orders.id"), nullable=True
    )
    problem: Mapped[str] = mapped_column(Text, default="")
    condition: Mapped[str] = mapped_column(Text, default="")
    accessories: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    template_snapshot: Mapped[dict] = mapped_column(JSON)
    intake_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    stage_forms: Mapped[dict] = mapped_column(JSON, default=dict)
    workflow_snapshot: Mapped[list] = mapped_column(JSON)
    stage: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    stage_deadline: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RepairEvent(Base):
    __tablename__ = "repair_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_orders.id"), nullable=True, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Attachment(Base):
    __tablename__ = "repair_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("repair_orders.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    filename: Mapped[str] = mapped_column(String(200))
    phase: Mapped[str] = mapped_column(String(20), default="intake")
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Estimate(Base):
    __tablename__ = "repair_estimates"
    __table_args__ = (UniqueConstraint("order_id", "revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("repair_orders.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    lines: Mapped[list] = mapped_column(JSON)
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class RepairPayment(Base):
    __tablename__ = "repair_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("repair_orders.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Outbox(Base):
    __tablename__ = "repair_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_orders.id"), nullable=True, index=True
    )
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt: Mapped[datetime] = mapped_column(DateTime, default=now)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AccountToken(Base):
    __tablename__ = "account_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
