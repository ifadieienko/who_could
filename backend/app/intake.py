from datetime import date
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .database import db
from .models import DeviceIntakeField, DeviceIntakeForm, DeviceIntakeOrder, now
from .schemas import (
    DeviceIntakeFormCreate,
    DeviceIntakeFormPublic,
    DeviceIntakeOrderCreate,
    DeviceIntakeOrderPublic,
    DeviceIntakeOrderStatus,
    DeviceIntakeOrderUpdate,
)
from .service_board import build_service_router


_IMAGE_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/webp;base64,",
    "data:image/gif;base64,",
)


def _time(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def _form_public(form: DeviceIntakeForm) -> DeviceIntakeFormPublic:
    return DeviceIntakeFormPublic(
        id=form.id,
        name=form.name,
        created_at=_time(form.created_at),
        fields=[
            {
                "id": field.id,
                "name": field.name,
                "field_type": field.field_type,
                "position": field.position,
            }
            for field in form.fields
        ],
    )


def _snapshot_fields(form: DeviceIntakeForm) -> list[dict[str, Any]]:
    return [
        {
            "id": field.id,
            "name": field.name,
            "field_type": field.field_type,
            "position": field.position,
        }
        for field in form.fields
    ]


def _order_public(order: DeviceIntakeOrder) -> DeviceIntakeOrderPublic:
    return DeviceIntakeOrderPublic(
        id=order.id,
        form_id=order.form_id,
        form_name=order.form_name,
        fields=order.fields_snapshot or [],
        values=order.payload or {},
        status=order.status,
        created_at=_time(order.created_at),
        updated_at=_time(order.updated_at),
    )


def _normalize_order_values(
    fields: list[dict[str, Any]],
    values: dict[str, Any],
    *,
    require_complete: bool,
) -> dict[str, Any]:
    by_id = {str(field["id"]): field for field in fields}
    unknown = sorted(set(values) - set(by_id))
    if unknown:
        raise HTTPException(422, f"Unknown device intake field ids: {unknown}")

    result: dict[str, Any] = {}
    missing: list[str] = []
    for key, field in by_id.items():
        value = values.get(key)
        if value is None or value == "":
            result[key] = None
            if require_complete:
                missing.append(field["name"])
            continue

        field_type = field["field_type"]
        if field_type == "string":
            if not isinstance(value, str):
                raise HTTPException(422, f"Field '{field['name']}' requires string")
            if len(value) > 10000:
                raise HTTPException(422, f"Field '{field['name']}' is too long")
            result[key] = value
        elif field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(422, f"Field '{field['name']}' requires number")
            result[key] = value
        elif field_type == "date":
            if not isinstance(value, str):
                raise HTTPException(422, f"Field '{field['name']}' requires date")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(422, f"Field '{field['name']}' requires YYYY-MM-DD date") from exc
            result[key] = value
        elif field_type == "image":
            if not isinstance(value, str) or not value.startswith(_IMAGE_PREFIXES):
                raise HTTPException(422, f"Field '{field['name']}' requires PNG, JPEG, WEBP or GIF image")
            if len(value) > 7_000_000:
                raise HTTPException(422, f"Image in field '{field['name']}' is too large")
            result[key] = value
        else:
            raise HTTPException(422, f"Unsupported device intake field type: {field_type}")

    if missing:
        raise HTTPException(422, "Не заполнены поля: " + ", ".join(missing))
    return result


def _load_form(session, form_id: int, owner_id: int) -> DeviceIntakeForm | None:
    return session.scalar(
        select(DeviceIntakeForm)
        .options(selectinload(DeviceIntakeForm.fields))
        .where(DeviceIntakeForm.id == form_id, DeviceIntakeForm.owner_id == owner_id)
    )


def _load_order(session, order_id: int, owner_id: int) -> DeviceIntakeOrder | None:
    return session.scalar(
        select(DeviceIntakeOrder).where(
            DeviceIntakeOrder.id == order_id,
            DeviceIntakeOrder.owner_id == owner_id,
        )
    )


def build_router(current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/device-intake", tags=["device-intake"])

    @router.get("/forms", response_model=list[DeviceIntakeFormPublic])
    def list_forms(user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            forms = session.scalars(
                select(DeviceIntakeForm)
                .options(selectinload(DeviceIntakeForm.fields))
                .where(DeviceIntakeForm.owner_id == user["id"])
                .order_by(DeviceIntakeForm.created_at.desc(), DeviceIntakeForm.id.desc())
            ).all()
            return [_form_public(form) for form in forms]

    @router.get("/forms/{form_id}", response_model=DeviceIntakeFormPublic)
    def get_form(form_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            form = _load_form(session, form_id, user["id"])
            if not form:
                raise HTTPException(404, "Device intake form not found")
            return _form_public(form)

    @router.post("/forms", response_model=DeviceIntakeFormPublic, status_code=201)
    def create_form(payload: DeviceIntakeFormCreate, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            form = DeviceIntakeForm(owner_id=user["id"], name=payload.name)
            form.fields = [
                DeviceIntakeField(name=field.name, field_type=field.field_type.value, position=index)
                for index, field in enumerate(payload.fields)
            ]
            session.add(form)
            session.flush()
            form = _load_form(session, form.id, user["id"])
            return _form_public(form)

    @router.delete("/forms/{form_id}", status_code=204)
    def delete_form(form_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            form = session.scalar(
                select(DeviceIntakeForm).where(
                    DeviceIntakeForm.id == form_id,
                    DeviceIntakeForm.owner_id == user["id"],
                )
            )
            if not form:
                raise HTTPException(404, "Device intake form not found")
            session.delete(form)
        return Response(status_code=204)

    @router.get("/orders", response_model=list[DeviceIntakeOrderPublic])
    def list_orders(user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            orders = session.scalars(
                select(DeviceIntakeOrder)
                .where(DeviceIntakeOrder.owner_id == user["id"])
                .order_by(DeviceIntakeOrder.updated_at.desc(), DeviceIntakeOrder.id.desc())
            ).all()
            return [_order_public(order) for order in orders]

    @router.get("/orders/{order_id}", response_model=DeviceIntakeOrderPublic)
    def get_order(order_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            order = _load_order(session, order_id, user["id"])
            if not order:
                raise HTTPException(404, "Device intake order not found")
            return _order_public(order)

    @router.post("/orders", response_model=DeviceIntakeOrderPublic, status_code=201)
    def create_order(payload: DeviceIntakeOrderCreate, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            form = _load_form(session, payload.form_id, user["id"])
            if not form:
                raise HTTPException(404, "Device intake form not found")
            fields = _snapshot_fields(form)
            values = _normalize_order_values(
                fields,
                payload.values,
                require_complete=payload.status == DeviceIntakeOrderStatus.accepted,
            )
            order = DeviceIntakeOrder(
                owner_id=user["id"],
                form_id=form.id,
                form_name=form.name,
                fields_snapshot=fields,
                payload=values,
                status=payload.status.value,
                created_at=now(),
                updated_at=now(),
            )
            session.add(order)
            session.flush()
            return _order_public(order)

    @router.put("/orders/{order_id}", response_model=DeviceIntakeOrderPublic)
    def update_order(
        order_id: int,
        payload: DeviceIntakeOrderUpdate,
        user: Annotated[dict, Depends(current_user)],
    ):
        with db() as session:
            order = _load_order(session, order_id, user["id"])
            if not order:
                raise HTTPException(404, "Device intake order not found")
            if order.status == DeviceIntakeOrderStatus.accepted.value:
                raise HTTPException(409, "Accepted device intake order cannot be edited")
            order.payload = _normalize_order_values(
                order.fields_snapshot or [],
                payload.values,
                require_complete=payload.status == DeviceIntakeOrderStatus.accepted,
            )
            order.status = payload.status.value
            order.updated_at = now()
            session.flush()
            return _order_public(order)

    router.include_router(build_service_router(current_user))
    return router
