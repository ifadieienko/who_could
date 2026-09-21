from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .database import db
from .models import DeviceIntakeOrder, now
from .service_models import CustomerPickup, MasterBoardColumn, MasterWorkItem


DEFAULT_COLUMNS = ("Диагностика", "В ремонте", "Тестирование")
TERMINAL_COLUMN = "Возврат устройства клиенту"


def _time(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def _has_role(user: dict, *names: str) -> bool:
    allowed = set(names)
    return any(role.get("name") in allowed for role in user.get("roles", []))


def _require_master(user: dict) -> None:
    if not _has_role(user, "master", "admin"):
        raise HTTPException(403, "Master role required")


def _order_public(order: DeviceIntakeOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "intake_owner_id": order.owner_id,
        "form_id": order.form_id,
        "form_name": order.form_name,
        "fields": order.fields_snapshot or [],
        "values": order.payload or {},
        "status": order.status,
        "created_at": _time(order.created_at),
        "updated_at": _time(order.updated_at),
    }


def _column_public(column: MasterBoardColumn) -> dict[str, Any]:
    return {
        "id": column.id,
        "name": column.name,
        "position": column.position,
        "is_terminal": column.is_terminal,
    }


def _work_public(item: MasterWorkItem, order: DeviceIntakeOrder) -> dict[str, Any]:
    return {
        "id": item.id,
        "column_id": item.column_id,
        "claimed_at": _time(item.claimed_at),
        "updated_at": _time(item.updated_at),
        "order": _order_public(order),
    }


def _pickup_public(item: CustomerPickup, order: DeviceIntakeOrder) -> dict[str, Any]:
    return {
        "id": item.id,
        "status": item.status,
        "master_id": item.master_id,
        "ready_at": _time(item.ready_at),
        "issued_at": _time(item.issued_at),
        "order": _order_public(order),
    }


def _ensure_columns(session, owner_id: int) -> list[MasterBoardColumn]:
    columns = list(session.scalars(
        select(MasterBoardColumn)
        .where(MasterBoardColumn.owner_id == owner_id)
        .order_by(MasterBoardColumn.position, MasterBoardColumn.id)
    ).all())
    if columns:
        terminal = next((column for column in columns if column.is_terminal), None)
        if terminal is None:
            terminal = MasterBoardColumn(
                owner_id=owner_id,
                name=TERMINAL_COLUMN,
                position=max((column.position for column in columns), default=-1) + 1,
                is_terminal=True,
            )
            session.add(terminal)
            session.flush()
            columns.append(terminal)
        return sorted(columns, key=lambda column: (column.position, column.id))

    for position, name in enumerate(DEFAULT_COLUMNS):
        session.add(MasterBoardColumn(owner_id=owner_id, name=name, position=position, is_terminal=False))
    session.add(MasterBoardColumn(
        owner_id=owner_id,
        name=TERMINAL_COLUMN,
        position=len(DEFAULT_COLUMNS),
        is_terminal=True,
    ))
    session.flush()
    return list(session.scalars(
        select(MasterBoardColumn)
        .where(MasterBoardColumn.owner_id == owner_id)
        .order_by(MasterBoardColumn.position, MasterBoardColumn.id)
    ).all())


class ColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("column name cannot be empty")
        return value


class ColumnUpdate(ColumnCreate):
    pass


class MoveOrder(BaseModel):
    column_id: int = Field(gt=0)


def build_service_router(current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/service", tags=["service-board"])

    @router.get("/board")
    def board(user: Annotated[dict, Depends(current_user)]):
        _require_master(user)
        with db() as session:
            columns = _ensure_columns(session, user["id"])
            incoming = list(session.scalars(
                select(DeviceIntakeOrder)
                .outerjoin(MasterWorkItem, MasterWorkItem.order_id == DeviceIntakeOrder.id)
                .where(DeviceIntakeOrder.status == "accepted", MasterWorkItem.id.is_(None))
                .order_by(DeviceIntakeOrder.updated_at, DeviceIntakeOrder.id)
            ).all())
            assigned_rows = session.execute(
                select(MasterWorkItem, DeviceIntakeOrder)
                .join(DeviceIntakeOrder, DeviceIntakeOrder.id == MasterWorkItem.order_id)
                .where(MasterWorkItem.master_id == user["id"])
                .order_by(MasterWorkItem.updated_at.desc(), MasterWorkItem.id.desc())
            ).all()
            return {
                "columns": [_column_public(column) for column in columns],
                "incoming": [_order_public(order) for order in incoming],
                "items": [_work_public(item, order) for item, order in assigned_rows],
            }

    @router.post("/columns", status_code=201)
    def create_column(payload: ColumnCreate, user: Annotated[dict, Depends(current_user)]):
        _require_master(user)
        with db() as session:
            columns = _ensure_columns(session, user["id"])
            terminal = next(column for column in columns if column.is_terminal)
            position = terminal.position
            terminal.position = position + 1
            session.flush()
            column = MasterBoardColumn(
                owner_id=user["id"],
                name=payload.name,
                position=position,
                is_terminal=False,
            )
            session.add(column)
            session.flush()
            return _column_public(column)

    @router.put("/columns/{column_id}")
    def update_column(column_id: int, payload: ColumnUpdate, user: Annotated[dict, Depends(current_user)]):
        _require_master(user)
        with db() as session:
            column = session.scalar(select(MasterBoardColumn).where(
                MasterBoardColumn.id == column_id,
                MasterBoardColumn.owner_id == user["id"],
            ))
            if not column:
                raise HTTPException(404, "Board column not found")
            if column.is_terminal:
                raise HTTPException(409, "Terminal board column cannot be renamed")
            column.name = payload.name
            session.flush()
            return _column_public(column)

    @router.delete("/columns/{column_id}", status_code=204)
    def delete_column(column_id: int, user: Annotated[dict, Depends(current_user)]):
        _require_master(user)
        with db() as session:
            column = session.scalar(select(MasterBoardColumn).where(
                MasterBoardColumn.id == column_id,
                MasterBoardColumn.owner_id == user["id"],
            ))
            if not column:
                raise HTTPException(404, "Board column not found")
            if column.is_terminal:
                raise HTTPException(409, "Terminal board column cannot be deleted")
            in_use = session.scalar(select(func.count()).select_from(MasterWorkItem).where(MasterWorkItem.column_id == column.id)) or 0
            if in_use:
                raise HTTPException(409, "Move cards out of this column before deleting it")
            session.delete(column)
        return Response(status_code=204)

    @router.put("/orders/{order_id}/column")
    def move_order(order_id: int, payload: MoveOrder, user: Annotated[dict, Depends(current_user)]):
        _require_master(user)
        try:
            with db() as session:
                column = session.scalar(select(MasterBoardColumn).where(
                    MasterBoardColumn.id == payload.column_id,
                    MasterBoardColumn.owner_id == user["id"],
                ))
                if not column:
                    raise HTTPException(404, "Board column not found")
                order = session.scalar(select(DeviceIntakeOrder).where(
                    DeviceIntakeOrder.id == order_id,
                    DeviceIntakeOrder.status == "accepted",
                ))
                if not order:
                    raise HTTPException(404, "Accepted intake order not found")
                item = session.scalar(select(MasterWorkItem).where(MasterWorkItem.order_id == order.id))
                if item is None:
                    item = MasterWorkItem(
                        order_id=order.id,
                        master_id=user["id"],
                        column_id=column.id,
                        claimed_at=now(),
                        updated_at=now(),
                    )
                    session.add(item)
                else:
                    if item.master_id != user["id"]:
                        raise HTTPException(409, "Order is already assigned to another master")
                    current_column = session.get(MasterBoardColumn, item.column_id)
                    if current_column and current_column.is_terminal and item.column_id != column.id:
                        raise HTTPException(409, "Completed order cannot be moved back from customer return")
                    item.column_id = column.id
                    item.updated_at = now()
                session.flush()

                if column.is_terminal:
                    pickup = session.scalar(select(CustomerPickup).where(CustomerPickup.order_id == order.id))
                    if pickup is None:
                        pickup = CustomerPickup(
                            order_id=order.id,
                            intake_owner_id=order.owner_id,
                            master_id=user["id"],
                            status="ready",
                            ready_at=now(),
                        )
                        session.add(pickup)
                        session.flush()
                return _work_public(item, order)
        except IntegrityError as exc:
            raise HTTPException(409, "Order is already assigned to another master") from exc

    @router.get("/pickup")
    def pickup_queue(user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            conditions = [CustomerPickup.status == "ready"]
            if not _has_role(user, "admin"):
                conditions.append(CustomerPickup.intake_owner_id == user["id"])
            rows = session.execute(
                select(CustomerPickup, DeviceIntakeOrder)
                .join(DeviceIntakeOrder, DeviceIntakeOrder.id == CustomerPickup.order_id)
                .where(*conditions)
                .order_by(CustomerPickup.ready_at, CustomerPickup.id)
            ).all()
            return [_pickup_public(item, order) for item, order in rows]

    @router.patch("/pickup/{pickup_id}/issue")
    def issue_to_customer(pickup_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            item = session.get(CustomerPickup, pickup_id)
            if not item:
                raise HTTPException(404, "Pickup item not found")
            if item.intake_owner_id != user["id"] and not _has_role(user, "admin"):
                raise HTTPException(403, "Only intake owner can issue this device")
            if item.status != "ready":
                raise HTTPException(409, "Device is already issued")
            item.status = "issued"
            item.issued_at = now()
            session.flush()
            order = session.get(DeviceIntakeOrder, item.order_id)
            return _pickup_public(item, order)

    return router
