from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(String(300))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    users = relationship("User", secondary=user_roles, back_populates="roles")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(80))
    bio: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    jobs = relationship("Job", cascade="all, delete-orphan", passive_deletes=True)
    applications = relationship("Application", cascade="all, delete-orphan", passive_deletes=True)
    intake_forms = relationship("DeviceIntakeForm", cascade="all, delete-orphan", passive_deletes=True)
    intake_orders = relationship("DeviceIntakeOrder", cascade="all, delete-orphan", passive_deletes=True)
    warehouse_tables = relationship("WarehouseTable", cascade="all, delete-orphan", passive_deletes=True)


class DeviceIntakeForm(Base):
    __tablename__ = "device_intake_forms"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    fields = relationship(
        "DeviceIntakeField",
        order_by="DeviceIntakeField.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DeviceIntakeField(Base):
    __tablename__ = "device_intake_fields"
    __table_args__ = (
        UniqueConstraint("form_id", "position", name="uq_device_intake_field_position"),
        CheckConstraint("field_type IN ('string','number','date','image')", name="ck_device_intake_field_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("device_intake_forms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    field_type: Mapped[str] = mapped_column(String(10))
    position: Mapped[int] = mapped_column(Integer)


class DeviceIntakeOrder(Base):
    __tablename__ = "device_intake_orders"
    __table_args__ = (
        CheckConstraint("status IN ('deferred','accepted')", name="ck_device_intake_order_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    form_id: Mapped[int | None] = mapped_column(ForeignKey("device_intake_forms.id", ondelete="SET NULL"), nullable=True, index=True)
    form_name: Mapped[str] = mapped_column(String(120))
    fields_snapshot: Mapped[list] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class WarehouseTable(Base):
    __tablename__ = "warehouse_tables"
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey("workshops.id"), nullable=True, index=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    columns = relationship(
        "WarehouseColumn",
        order_by="WarehouseColumn.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    rows = relationship(
        "WarehouseRow",
        order_by="WarehouseRow.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WarehouseColumn(Base):
    __tablename__ = "warehouse_columns"
    __table_args__ = (
        UniqueConstraint("table_id", "position", name="uq_warehouse_column_position"),
        CheckConstraint(
            "field_type IN ('string','number','date','image','barcode','qrcode')",
            name="ck_warehouse_column_type",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("warehouse_tables.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    field_type: Mapped[str] = mapped_column(String(12))
    position: Mapped[int] = mapped_column(Integer)


class WarehouseRow(Base):
    __tablename__ = "warehouse_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("warehouse_tables.id", ondelete="CASCADE"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("work_mode IN ('online','offline','hybrid')", name="ck_jobs_work_mode"),
        CheckConstraint("duration IN ('one_day','short','long')", name="ck_jobs_duration"),
        CheckConstraint("budget_type IN ('fixed','hourly','negotiable')", name="ck_jobs_budget_type"),
        CheckConstraint("status IN ('open','in_progress','closed')", name="ck_jobs_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120)); description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80)); work_mode: Mapped[str] = mapped_column(String(10))
    duration: Mapped[str] = mapped_column(String(10)); location: Mapped[str | None] = mapped_column(String(120))
    budget_type: Mapped[str] = mapped_column(String(12)); budget_min: Mapped[int | None] = mapped_column(Integer)
    budget_max: Mapped[int | None] = mapped_column(Integer); currency: Mapped[str] = mapped_column(String(3), default="USD")
    deadline: Mapped[date | None] = mapped_column(Date); skills: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    applications = relationship("Application", cascade="all, delete-orphan", passive_deletes=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "applicant_id", name="uq_application_job_applicant"),
                      CheckConstraint("status IN ('sent','accepted','declined')", name="ck_applications_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text); proposed_rate: Mapped[int | None] = mapped_column(Integer)
    estimated_time: Mapped[str | None] = mapped_column(String(120)); status: Mapped[str] = mapped_column(String(10), default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
