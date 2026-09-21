from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, now


class MasterBoardColumn(Base):
    __tablename__ = "master_board_columns"
    __table_args__ = (UniqueConstraint("owner_id", "position", name="uq_master_board_column_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MasterWorkItem(Base):
    __tablename__ = "master_work_items"
    __table_args__ = (UniqueConstraint("order_id", name="uq_master_work_items_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("device_intake_orders.id", ondelete="CASCADE"), index=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    column_id: Mapped[int] = mapped_column(ForeignKey("master_board_columns.id", ondelete="RESTRICT"), index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CustomerPickup(Base):
    __tablename__ = "customer_pickups"
    __table_args__ = (
        CheckConstraint("status IN ('ready','issued')", name="ck_customer_pickup_status"),
        UniqueConstraint("order_id", name="uq_customer_pickups_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("device_intake_orders.id", ondelete="CASCADE"), index=True)
    intake_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    master_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(10), default="ready", index=True)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
