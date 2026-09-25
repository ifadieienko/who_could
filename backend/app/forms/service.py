"""forms / service domain. Legacy API behavior is preserved."""

from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from types import SimpleNamespace
from app.repair_models import Attachment


def visible_fields(o, a):
    return [
        f
        for f in o.template_snapshot.get("fields", [])
        if not f.get("read_permission") or f["read_permission"] in a.permissions
    ]


def normalize_values(s, o, values, a, required=False, required_keys=()):
    fields = o.template_snapshot.get("fields", [])
    by_key = {f["key"]: f for f in fields}
    if set(values) - set(by_key):
        raise HTTPException(422, "Неизвестное поле формы")
    result = dict(o.values or {})
    for key, value in values.items():
        f = by_key[key]
        if value == result.get(key):
            continue
        for p in (f.get("read_permission"), f.get("write_permission")):
            if p and p not in a.permissions and value != result.get(key):
                raise HTTPException(403, "Нет прав на поле " + key)
        if value is None or value == "":
            result[key] = None
            continue
        typ = f["type"]
        if typ in {"string", "text", "select"}:
            if not isinstance(value, str) or len(value) > 10000:
                raise HTTPException(422, "Некорректный текст: " + key)
            value = value.strip()
            if typ == "select" and value not in f.get("options", []):
                raise HTTPException(422, "Недопустимый вариант: " + key)
        elif typ == "number":
            import math

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or abs(value) > 1e12
            ):
                raise HTTPException(422, "Некорректное число: " + key)
        elif typ == "checkbox":
            if not isinstance(value, bool):
                raise HTTPException(422, "Ожидается checkbox: " + key)
        elif typ == "date":
            try:
                date.fromisoformat(value)
            except (ValueError, TypeError):
                raise HTTPException(422, "Некорректная дата: " + key)
        elif typ == "image":
            if not isinstance(value, int) or isinstance(value, bool):
                raise HTTPException(422, "Загрузите изображение: " + key)
            file = s.scalar(
                select(Attachment).where(
                    Attachment.id == value,
                    Attachment.order_id == o.id,
                    Attachment.workshop_id == a.workshop_id,
                )
            )
            if not file:
                raise HTTPException(422, "Изображение не принадлежит заказу")
        result[key] = value
    missing = []
    for f in fields:
        c = f.get("condition")
        if c and result.get(c["field"]) != c["equals"]:
            continue
        if (required and f.get("required")) or f["key"] in required_keys:
            v = result.get(f["key"])
            if v is None or v == "" or (f["type"] == "checkbox" and v is not True):
                missing.append(f["label"])
    if missing:
        raise HTTPException(422, "Заполните: " + ", ".join(missing))
    return result


def form_proxy(o, form):
    return SimpleNamespace(
        id=o.id, template_snapshot=form["template"], values=form["values"]
    )


def public_forms(o, a, forms=None):
    return {
        phase: {
            "template": {
                **form["template"],
                "fields": visible_fields(form_proxy(o, form), a),
            },
            "values": {
                f["key"]: form["values"].get(f["key"])
                for f in visible_fields(form_proxy(o, form), a)
            },
        }
        for phase, form in (o.stage_forms if forms is None else forms).items()
    }


def restricted_attachment_ids(o, a):
    forms = [
        {"template": o.template_snapshot, "values": o.values},
        *o.stage_forms.values(),
    ]
    return {
        form["values"].get(f["key"])
        for form in forms
        for f in form["template"].get("fields", [])
        if f["type"] == "image"
        and f.get("read_permission")
        and f["read_permission"] not in a.permissions
    } - {None}

