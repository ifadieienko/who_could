from base64 import b64encode
from datetime import date
from enum import Enum
from io import BytesIO
from typing import Annotated, Any, Callable

import barcode
import qrcode
from barcode.writer import SVGWriter
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from qrcode.image.svg import SvgPathImage
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .database import db
from .models import WarehouseColumn, WarehouseRow, WarehouseTable


class WarehouseFieldType(str, Enum):
    string = "string"
    number = "number"
    date = "date"
    image = "image"
    barcode = "barcode"
    qrcode = "qrcode"


class WarehouseColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_type: WarehouseFieldType

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("column name cannot be empty")
        return value


class WarehouseTableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    columns: list[WarehouseColumnCreate] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("table name cannot be empty")
        return value


class WarehouseRowCreate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class WarehouseCodePreview(BaseModel):
    kind: WarehouseFieldType
    value: str = Field(min_length=1, max_length=500)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: WarehouseFieldType) -> WarehouseFieldType:
        if value not in {WarehouseFieldType.barcode, WarehouseFieldType.qrcode}:
            raise ValueError("kind must be barcode or qrcode")
        return value


class WarehouseColumnPublic(BaseModel):
    id: int
    name: str
    field_type: WarehouseFieldType
    position: int


class WarehouseRowPublic(BaseModel):
    id: int
    values: dict[str, Any]
    created_at: str


class WarehouseTableSummary(BaseModel):
    id: int
    name: str
    columns: list[WarehouseColumnPublic]
    row_count: int
    created_at: str


class WarehouseTablePublic(WarehouseTableSummary):
    rows: list[WarehouseRowPublic]


def _time(value) -> str:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else str(value)


def _column_public(column: WarehouseColumn) -> WarehouseColumnPublic:
    return WarehouseColumnPublic(
        id=column.id,
        name=column.name,
        field_type=column.field_type,
        position=column.position,
    )


def _row_public(row: WarehouseRow) -> WarehouseRowPublic:
    return WarehouseRowPublic(id=row.id, values=row.payload or {}, created_at=_time(row.created_at))


def _table_public(table: WarehouseTable) -> WarehouseTablePublic:
    return WarehouseTablePublic(
        id=table.id,
        name=table.name,
        columns=[_column_public(column) for column in table.columns],
        rows=[_row_public(row) for row in table.rows],
        row_count=len(table.rows),
        created_at=_time(table.created_at),
    )


def _load_table(session, table_id: int, owner_id: int, include_rows: bool = True) -> WarehouseTable | None:
    options = [selectinload(WarehouseTable.columns)]
    if include_rows:
        options.append(selectinload(WarehouseTable.rows))
    return session.scalar(
        select(WarehouseTable)
        .options(*options)
        .where(WarehouseTable.id == table_id, WarehouseTable.owner_id == owner_id)
    )


def _svg_data_url(data: bytes) -> str:
    return "data:image/svg+xml;base64," + b64encode(data).decode("ascii")


def _barcode_svg(value: str) -> str:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise HTTPException(422, "Barcode value must contain ASCII characters only") from exc
    output = BytesIO()
    try:
        code = barcode.get("code128", value, writer=SVGWriter())
        code.write(output, options={"write_text": True, "module_height": 12, "quiet_zone": 1})
    except Exception as exc:
        raise HTTPException(422, "Barcode value cannot be encoded") from exc
    return _svg_data_url(output.getvalue())


def _qrcode_svg(value: str) -> str:
    output = BytesIO()
    try:
        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=2)
        code.add_data(value)
        code.make(fit=True)
        image = code.make_image(image_factory=SvgPathImage)
        image.save(output)
    except Exception as exc:
        raise HTTPException(422, "QR code value cannot be encoded") from exc
    return _svg_data_url(output.getvalue())


def _code_payload(kind: str, value: str) -> dict[str, str]:
    value = value.strip()
    if not value:
        raise HTTPException(422, f"{kind} value cannot be empty")
    if len(value) > 500:
        raise HTTPException(422, f"{kind} value is too long")
    image = _barcode_svg(value) if kind == "barcode" else _qrcode_svg(value)
    return {"value": value, "image": image}


def _normalize_values(columns: list[WarehouseColumn], values: dict[str, Any]) -> dict[str, Any]:
    by_id = {str(column.id): column for column in columns}
    unknown = sorted(set(values) - set(by_id))
    if unknown:
        raise HTTPException(422, f"Unknown warehouse column ids: {unknown}")

    result: dict[str, Any] = {}
    for key, column in by_id.items():
        value = values.get(key)
        if value is None or value == "":
            result[key] = None
            continue

        if column.field_type == "string":
            if not isinstance(value, str):
                raise HTTPException(422, f"Column '{column.name}' requires string")
            if len(value) > 10000:
                raise HTTPException(422, f"Column '{column.name}' is too long")
            result[key] = value
        elif column.field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(422, f"Column '{column.name}' requires number")
            result[key] = value
        elif column.field_type == "date":
            if not isinstance(value, str):
                raise HTTPException(422, f"Column '{column.name}' requires date")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(422, f"Column '{column.name}' requires YYYY-MM-DD date") from exc
            result[key] = value
        elif column.field_type == "image":
            if not isinstance(value, str) or not value.startswith((
                "data:image/png;base64,",
                "data:image/jpeg;base64,",
                "data:image/webp;base64,",
                "data:image/gif;base64,",
            )):
                raise HTTPException(422, f"Column '{column.name}' requires PNG, JPEG, WEBP or GIF image")
            if len(value) > 7_000_000:
                raise HTTPException(422, f"Image in column '{column.name}' is too large")
            result[key] = value
        elif column.field_type in {"barcode", "qrcode"}:
            if not isinstance(value, str):
                raise HTTPException(422, f"Column '{column.name}' requires code value")
            result[key] = _code_payload(column.field_type, value)
        else:
            raise HTTPException(422, f"Unsupported warehouse column type: {column.field_type}")
    return result


def build_warehouse_router(current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/warehouse", tags=["warehouse"])

    @router.get("/tables", response_model=list[WarehouseTableSummary])
    def list_tables(user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            tables = list(session.scalars(
                select(WarehouseTable)
                .options(selectinload(WarehouseTable.columns))
                .where(WarehouseTable.owner_id == user["id"])
                .order_by(WarehouseTable.created_at.desc(), WarehouseTable.id.desc())
            ).all())
            counts: dict[int, int] = {}
            if tables:
                counts = {
                    table_id: count
                    for table_id, count in session.execute(
                        select(WarehouseRow.table_id, func.count(WarehouseRow.id))
                        .where(WarehouseRow.table_id.in_([table.id for table in tables]))
                        .group_by(WarehouseRow.table_id)
                    ).all()
                }
            return [
                WarehouseTableSummary(
                    id=table.id,
                    name=table.name,
                    columns=[_column_public(column) for column in table.columns],
                    row_count=int(counts.get(table.id, 0)),
                    created_at=_time(table.created_at),
                )
                for table in tables
            ]

    @router.post("/tables", response_model=WarehouseTablePublic, status_code=201)
    def create_table(payload: WarehouseTableCreate, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            table = WarehouseTable(owner_id=user["id"], name=payload.name)
            table.columns = [
                WarehouseColumn(name=column.name, field_type=column.field_type.value, position=index)
                for index, column in enumerate(payload.columns)
            ]
            session.add(table)
            session.flush()
            table = _load_table(session, table.id, user["id"])
            return _table_public(table)

    @router.get("/tables/{table_id}", response_model=WarehouseTablePublic)
    def get_table(table_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            table = _load_table(session, table_id, user["id"])
            if not table:
                raise HTTPException(404, "Warehouse table not found")
            return _table_public(table)

    @router.delete("/tables/{table_id}", status_code=204)
    def delete_table(table_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            table = _load_table(session, table_id, user["id"], include_rows=False)
            if not table:
                raise HTTPException(404, "Warehouse table not found")
            session.delete(table)
        return Response(status_code=204)

    @router.post("/tables/{table_id}/rows", response_model=WarehouseRowPublic, status_code=201)
    def create_row(table_id: int, payload: WarehouseRowCreate, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            table = _load_table(session, table_id, user["id"], include_rows=False)
            if not table:
                raise HTTPException(404, "Warehouse table not found")
            row = WarehouseRow(table_id=table.id, payload=_normalize_values(list(table.columns), payload.values))
            session.add(row)
            session.flush()
            return _row_public(row)

    @router.put("/tables/{table_id}/rows/{row_id}", response_model=WarehouseRowPublic)
    def update_row(table_id: int, row_id: int, payload: WarehouseRowCreate, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            table = _load_table(session, table_id, user["id"], include_rows=False)
            if not table:
                raise HTTPException(404, "Warehouse table not found")
            row = session.scalar(select(WarehouseRow).where(WarehouseRow.id == row_id, WarehouseRow.table_id == table.id))
            if not row:
                raise HTTPException(404, "Warehouse row not found")
            row.payload = _normalize_values(list(table.columns), payload.values)
            session.flush()
            return _row_public(row)

    @router.delete("/tables/{table_id}/rows/{row_id}", status_code=204)
    def delete_row(table_id: int, row_id: int, user: Annotated[dict, Depends(current_user)]):
        with db() as session:
            table = _load_table(session, table_id, user["id"], include_rows=False)
            if not table:
                raise HTTPException(404, "Warehouse table not found")
            row = session.scalar(select(WarehouseRow).where(WarehouseRow.id == row_id, WarehouseRow.table_id == table.id))
            if not row:
                raise HTTPException(404, "Warehouse row not found")
            session.delete(row)
        return Response(status_code=204)

    @router.post("/codes/preview")
    def preview_code(payload: WarehouseCodePreview, _user: Annotated[dict, Depends(current_user)]):
        return _code_payload(payload.kind.value, payload.value)

    return router
