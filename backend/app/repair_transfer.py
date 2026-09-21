"""Tenant-scoped portable export and transactional CSV onboarding."""

import csv
import io
import json
import tempfile
import zipfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from .database import db
from .repair_access import access, event, utc
from .repair_models import *
from .models import User, WarehouseTable, WarehouseColumn, WarehouseRow
from .repair_schemas import OrderInput, CustomerInput
from .repairs import create_order_record
from .repair_files import storage

router = APIRouter(prefix="/v2", tags=["transfer"])


def export_dict(row):
    excluded = {"token_hash", "stripe_customer", "stripe_subscription"}
    return {
        c.name: getattr(row, c.name)
        for c in row.__table__.columns
        if c.name not in excluded
    }


@router.get("/export")
def export(a=Depends(access)):
    a.require("data.export")
    if a.scope != "all":
        raise HTTPException(403, "Экспорт мастерской требует полного доступа")
    archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with db() as s, zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            data = {
                "format": "who-could-workshop",
                "version": 1,
                "exported_at": utc().isoformat(),
                "workshop": export_dict(s.get(Workshop, a.workshop_id)),
            }
            for model in [
                Customer,
                Device,
                FormTemplate,
                Workflow,
                RepairOrder,
                Estimate,
                RepairPayment,
                RepairEvent,
                Attachment,
                WorkshopRole,
                Membership,
            ]:
                data[model.__tablename__] = [
                    export_dict(x)
                    for x in s.scalars(
                        select(model).where(model.workshop_id == a.workshop_id)
                    ).all()
                ]
            data["warehouse_tables"] = [
                export_dict(x)
                for x in s.scalars(
                    select(WarehouseTable).where(
                        WarehouseTable.workshop_id == a.workshop_id
                    )
                ).all()
            ]
            ids = [x["id"] for x in data["warehouse_tables"]]
            staff_ids = [x["user_id"] for x in data["workshop_members"]]
            data["staff"] = [
                {"id": u.id, "name": u.name, "email": u.email}
                for u in s.scalars(select(User).where(User.id.in_(staff_ids)))
            ]
            for model in [WarehouseColumn, WarehouseRow]:
                data[model.__tablename__] = [
                    export_dict(x)
                    for x in s.scalars(
                        select(model).where(model.table_id.in_(ids))
                    ).all()
                ]
            for file in data["repair_attachments"]:
                for suffix in [".jpg", ".thumb.jpg"]:
                    path = storage() / (file["storage_key"] + suffix)
                    if not path.is_file():
                        raise HTTPException(
                            409, "Экспорт прерван: отсутствует файл " + str(file["id"])
                        )
                    z.write(path, "files/" + path.name)
            z.writestr(
                "workshop.json",
                json.dumps(
                    data, ensure_ascii=False, default=lambda x: x.isoformat(), indent=2
                ),
            )
            event(s, a, None, "data.exported")
        archive.seek(0)

        def chunks():
            try:
                while chunk := archive.read(65536):
                    yield chunk
            finally:
                archive.close()

        return StreamingResponse(
            chunks(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="workshop-export.zip"',
                "Cache-Control": "no-store",
            },
        )
    except Exception:
        archive.close()
        raise


@router.post("/import/csv")
def import_csv(
    file: UploadFile = File(...),
    template_id: int = Form(...),
    workflow_id: int = Form(...),
    kind: str = Form("orders"),
    dry_run: bool = Form(True),
    a=Depends(access),
):
    a.require("data.import")
    a.require("orders.create")
    a.require("contacts.read")
    a.write()
    if a.scope != "all":
        raise HTTPException(403, "Импорт требует полного доступа")
    if kind not in {"orders", "customers"}:
        raise HTTPException(422, "Неизвестный тип импорта")
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV не более 5 МБ")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise HTTPException(422, "Нужен корректный CSV UTF-8 с запятыми")
    if len(rows) > 1000:
        raise HTTPException(422, "Не более 1000 записей за импорт")
    if not rows:
        raise HTTPException(422, "CSV пуст")
    allowed = {
        "external_id",
        "customer_external_id",
        "name",
        "email",
        "phone",
        "model",
        "serial",
        "problem",
        "condition",
        "accessories",
        "location",
    }
    if not reader.fieldnames or set(reader.fieldnames) - allowed:
        raise HTTPException(422, "Неизвестные заголовки CSV")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise HTTPException(422, "Повторяющиеся заголовки CSV")
    errors = []
    prepared = []
    seen = set()
    for index, row in enumerate(rows, 2):
        try:
            if None in row:
                raise ValueError("Лишние значения в строке")
            row = {k: (v or "").strip() for k, v in row.items()}
            external = row.get("external_id", "")
            if not external or len(external) > 160 or external in seen:
                raise ValueError("Нужен уникальный external_id до 160 символов")
            seen.add(external)
            c = CustomerInput(
                name=row.get("name", ""),
                email=row.get("email") or None,
                phone=row.get("phone", ""),
            )
            p = None
            if kind == "orders":
                p = OrderInput(
                    template_id=template_id,
                    workflow_id=workflow_id,
                    customer=c,
                    model=row.get("model", ""),
                    serial=row.get("serial", ""),
                    problem=row.get("problem", ""),
                    condition=row.get("condition", ""),
                    accessories=row.get("accessories", ""),
                    location=row.get("location", ""),
                    draft=True,
                )
                if not p.model:
                    raise ValueError("model обязателен")
            customer_external = row.get("customer_external_id") or external
            if len(customer_external) > 160:
                raise ValueError("customer_external_id не более 160 символов")
            prepared.append((external, customer_external, c, p))
        except (ValidationError, ValueError) as e:
            errors.append({"line": index, "message": str(e)[:600]})
    if errors:
        return {
            "dry_run": True,
            "valid": False,
            "errors": errors,
            "created": 0,
            "skipped": 0,
        }
    with db() as s:
        # Prevent duplicate submissions from racing across import requests.
        s.scalar(select(Workshop).where(Workshop.id == a.workshop_id).with_for_update())
        from .repairs import scoped

        if kind == "orders":
            t = scoped(s, FormTemplate, template_id, a)
            w = scoped(s, Workflow, workflow_id, a)
            if t.purpose != "intake" or any(
                stage.get("form_phase") for stage in w.stages
            ):
                raise HTTPException(
                    422,
                    "Для CSV выберите форму приёма и процесс без отдельных форм этапов",
                )
            if not t.published or t.archived or w.archived:
                raise HTTPException(422, "Шаблон и процесс должны быть действующими")
            if any(
                set(x.get("required_fields", [])) - {f["key"] for f in t.fields}
                for x in w.stages
            ):
                raise HTTPException(422, "Форма несовместима с процессом")
        created = skipped = 0
        for external, customer_external, c, p in prepared:
            model = Customer if kind == "customers" else RepairOrder
            if s.scalar(
                select(model.id).where(
                    model.workshop_id == a.workshop_id, model.external_id == external
                )
            ):
                skipped += 1
                continue
            created += 1
            if dry_run:
                if kind == "orders":
                    from .plans import enforce_limit

                    enforce_limit(s, a.workshop_id, "open_orders", created)
                continue
            if kind == "customers":
                s.add(
                    Customer(
                        workshop_id=a.workshop_id,
                        external_id=external,
                        **c.model_dump(),
                    )
                )
            else:
                existing = s.scalar(
                    select(Customer).where(
                        Customer.workshop_id == a.workshop_id,
                        Customer.external_id == customer_external,
                    )
                )
                if not existing:
                    existing = Customer(
                        workshop_id=a.workshop_id,
                        external_id=customer_external,
                        **c.model_dump(),
                    )
                    s.add(existing)
                    s.flush()
                p.customer_id = existing.id
                if p.serial:
                    p.device_id = s.scalar(
                        select(Device.id)
                        .where(
                            Device.workshop_id == a.workshop_id,
                            Device.customer_id == existing.id,
                            Device.serial == p.serial,
                        )
                        .limit(1)
                    )
                order = create_order_record(s, p, a)
                order.external_id = external
            s.flush()
        if not dry_run:
            event(
                s,
                a,
                None,
                "data.imported",
                {"kind": kind, "created": created, "skipped": skipped},
            )
        return {
            "dry_run": dry_run,
            "valid": True,
            "errors": [],
            "created": created,
            "skipped": skipped,
        }
