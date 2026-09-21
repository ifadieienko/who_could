import html
import io
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
import qrcode
import qrcode.image.svg
from sqlalchemy import select
from .database import db
from .repair_access import access, get_order, touch, event
from .repair_models import Attachment, Workshop, Device, Customer

router = APIRouter(prefix="/v2", tags=["files"])
Image.MAX_IMAGE_PIXELS = 25_000_000


def storage():
    root = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def encode_image(raw):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP", "GIF"}:
                raise ValueError("format")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((2400, 2400))
            full = io.BytesIO()
            image.save(full, "JPEG", quality=88)
            image.thumbnail((320, 320))
            thumb = io.BytesIO()
            image.save(thumb, "JPEG", quality=78)
            return full.getvalue(), thumb.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(
            422, "Повреждённое или слишком большое изображение"
        ) from exc


@router.post("/orders/{id}/attachments", status_code=201)
def upload(
    id: str,
    version: int = Form(...),
    phase: str = Form("intake"),
    file: UploadFile = File(...),
    a=Depends(access),
):
    a.require("orders.edit")
    if phase not in {"intake", "repair", "quality"}:
        raise HTTPException(422, "Недопустимый этап фотографии")
    raw = file.file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Изображение должно быть не больше 10 МБ")
    full, thumb = encode_image(raw)
    key = uuid.uuid4().hex
    root = storage()
    paths = [root / (key + ".jpg"), root / (key + ".thumb.jpg")]
    try:
        with db() as s:
            o = get_order(s, a, id, version)
            if o.status in {"issued", "cancelled"}:
                raise HTTPException(409, "Заказ закрыт")
            if phase == "intake" and o.status != "draft":
                raise HTTPException(
                    409,
                    "Фото приёмки добавляются до принятия. Поздние фото сохраняйте как ремонтные.",
                )
            paths[0].write_bytes(full)
            paths[1].write_bytes(thumb)
            f = Attachment(
                workshop_id=a.workshop_id,
                order_id=o.id,
                storage_key=key,
                filename=(Path(file.filename or "photo").name[:190] + ".jpg"),
                phase=phase,
                size=len(full),
            )
            s.add(f)
            s.flush()
            touch(o)
            event(s, a, o, "photo.added", {"attachment": f.id, "phase": phase})
            result = {"id": f.id, "version": o.version}
        return result
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise


@router.get("/files/{id}")
def download(id: int, thumb: bool = False, a=Depends(access)):
    with db() as s:
        from .repair_models import RepairOrder

        f = s.scalar(
            select(Attachment).where(
                Attachment.id == id, Attachment.workshop_id == a.workshop_id
            )
        )
        if not f:
            raise HTTPException(404, "Файл не найден")
        o = s.get(RepairOrder, f.order_id)
        get_order(s, a, o.public_id)
        # A file referenced by a restricted field has the same restrictions.
        for spec in o.template_snapshot.get("fields", []):
            if (
                spec["type"] == "image"
                and o.values.get(spec["key"]) == id
                and spec.get("read_permission") not in {None, *a.permissions}
            ):
                raise HTTPException(403, "Нет доступа к файлу")
        path = storage() / (f.storage_key + (".thumb.jpg" if thumb else ".jpg"))
        if not path.is_file():
            raise HTTPException(404, "Файл недоступен в хранилище")
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )


def qr_svg(value):
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    code.add_data(value)
    code.make(fit=True)
    return (
        code.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        .to_string()
        .decode()
    )


@router.get("/orders/{id}/label", response_class=HTMLResponse)
def label(id: str, a=Depends(access)):
    with db() as s:
        o = get_order(s, a, id)
        d = s.get(Device, o.device_id) if o.device_id else None
        base = os.getenv("PUBLIC_URL", "").rstrip("/")
        if not base:
            raise HTTPException(503, "Для QR задайте PUBLIC_URL с адресом приложения")
        body = f'<div class="label">{qr_svg(base+"/orders/"+o.public_id+"?workshop="+str(a.workshop_id))}<div><b>#{o.id}</b><p>{html.escape(d.model if d else "Устройство")}</p><small>{o.created_at:%Y-%m-%d}</small></div></div>'
        return HTMLResponse(
            '<!doctype html><meta charset="utf-8"><title>Этикетка</title><style>@page{size:62mm 40mm;margin:2mm}body{font:12px sans-serif;margin:0}.label{display:flex;align-items:center;width:58mm;height:36mm;overflow:hidden}svg{width:30mm;height:30mm;flex-shrink:0}p{overflow-wrap:anywhere}b{font-size:18px}</style>'
            + body,
            headers={"Cache-Control": "no-store"},
        )


@router.get("/orders/{id}/document", response_class=HTMLResponse)
def document(id: str, kind: str = "intake", a=Depends(access)):
    a.require("contacts.read")
    with db() as s:
        o = get_order(s, a, id)
        c = s.get(Customer, o.customer_id) if o.customer_id else None
        d = s.get(Device, o.device_id) if o.device_id else None
        w = s.get(Workshop, a.workshop_id)
        if kind not in {"intake", "issue"}:
            raise HTTPException(422, "Неизвестный документ")
        if kind == "intake" and not o.intake_snapshot:
            raise HTTPException(409, "Сначала примите заказ")
        if kind == "issue" and not o.receipt:
            raise HTTPException(409, "Сначала зарегистрируйте выдачу")
        snapshot = o.intake_snapshot if kind == "intake" else o.receipt
        rows = [
            ("Мастерская", w.name),
            ("Заказ", str(o.id)),
            ("Клиент", c.name if c else ""),
            ("Устройство", d.model if d else ""),
            ("S/N", d.serial if d else ""),
            ("Состояние", snapshot.get("condition", "")),
            ("Комплектность", snapshot.get("accessories", "")),
        ]
        if kind == "intake":
            rows.append(("Заявленная неисправность", snapshot.get("problem", "")))
        else:
            rows += [
                ("Получатель", snapshot["receiver"]),
                ("Дата выдачи", snapshot["issued_at"]),
                ("Примечание", snapshot["note"]),
            ]
            if "finance.read" in a.permissions:
                rows += [
                    ("Стоимость, PLN", f"{snapshot['total_cents']/100:.2f}"),
                    ("Оплачено, PLN", f"{snapshot['paid_cents']/100:.2f}"),
                ]
        for f in o.template_snapshot.get("fields", []):
            if f.get("read_permission") and f["read_permission"] not in a.permissions:
                continue
            if f["type"] == "image":
                continue
            value = snapshot.get("values", {}).get(f["key"])
            if value is not None:
                rows.append((f["label"], str(value)))
        body = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>"
            for k, v in rows
        )
        return HTMLResponse(
            '<!doctype html><meta charset="utf-8"><title>Документ заказа</title><style>@page{size:A4;margin:18mm}body{font:14px sans-serif}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;text-align:left;padding:10px;white-space:pre-wrap}th{width:30%}footer{margin-top:60px}</style><h1>'
            + ("Акт приёма" if kind == "intake" else "Акт выдачи")
            + "</h1><table>"
            + body
            + "</table><footer>Подпись клиента: ____________________ &nbsp; Сотрудник: ____________________</footer>",
            headers={"Cache-Control": "no-store"},
        )
