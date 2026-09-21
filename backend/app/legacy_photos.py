"""Idempotently externalise legacy intake data URLs after schema migration."""

import base64
import binascii
from fastapi import HTTPException
from uuid import uuid4
from sqlalchemy import select
from .database import db
from .repair_models import RepairOrder, Attachment, RepairEvent
from .repair_files import storage, encode_image


def migrate():
    with db() as s:
        ids = list(
            s.scalars(
                select(RepairOrder.id).where(RepairOrder.external_id.like("legacy:%"))
            )
        )
    for id in ids:
        paths = []
        try:
            with db() as s:
                o = s.scalar(
                    select(RepairOrder).where(RepairOrder.id == id).with_for_update()
                )
                values = dict(o.values)
                changed = False
                for f in o.template_snapshot.get("fields", []):
                    v = values.get(f["key"])
                    if (
                        f["type"] != "image"
                        or not isinstance(v, str)
                        or not v.startswith("data:image/")
                    ):
                        continue
                    try:
                        full, thumb = encode_image(
                            base64.b64decode(v.split(",", 1)[1], validate=True)
                        )
                    except (ValueError, binascii.Error, HTTPException):
                        existing = s.scalars(
                            select(RepairEvent).where(
                                RepairEvent.order_id == o.id,
                                RepairEvent.kind == "legacy.photo_failed",
                            )
                        ).all()
                        if not any(e.data.get("field") == f["key"] for e in existing):
                            s.add(
                                RepairEvent(
                                    workshop_id=o.workshop_id,
                                    order_id=o.id,
                                    actor_id=None,
                                    kind="legacy.photo_failed",
                                    data={
                                        "field": f["key"],
                                        "message": "Не удалось преобразовать старое фото. Исходное значение сохранено.",
                                    },
                                )
                            )
                        continue
                    key = uuid4().hex
                    for suffix, data in [(".jpg", full), (".thumb.jpg", thumb)]:
                        path = storage() / (key + suffix)
                        path.write_bytes(data)
                        paths.append(path)
                    file = Attachment(
                        workshop_id=o.workshop_id,
                        order_id=o.id,
                        storage_key=key,
                        filename="legacy-photo.jpg",
                        phase="intake",
                        size=len(full),
                    )
                    s.add(file)
                    s.flush()
                    values[f["key"]] = file.id
                    changed = True
                if changed:
                    o.values = values
                    if o.intake_snapshot:
                        o.intake_snapshot = {**o.intake_snapshot, "values": values}
        except Exception:
            for path in paths:
                path.unlink(missing_ok=True)
            raise


if __name__ == "__main__":
    migrate()
