"""jobs / serialization domain. Legacy API behavior is preserved."""

from datetime import timedelta
from sqlalchemy import select
from app.forms.service import (
    form_proxy,
    public_forms,
    restricted_attachment_ids,
    visible_fields,
)
from app.jobs.finance_service import paid
from app.repair_access import dt, utc
from app.repair_models import (
    Attachment,
    Customer,
    Device,
    Estimate,
    RepairEvent,
    RepairOrder,
    RepairPayment,
)
from app.workflows.service import stage_of


def summary(s, o, a):
    device = s.get(Device, o.device_id) if o.device_id else None
    stage = stage_of(o)
    deadline = o.stage_deadline or dt(o.stage_entered_at) + timedelta(
        hours=stage.get("sla_hours", 48)
    )
    return {
        "id": o.public_id,
        "number": o.id,
        "organization_id": o.workshop_id,
        "asset_id": o.device_id,
        "site_id": o.site_id,
        "vertical_key": o.vertical_key,
        "job_type": o.job_type,
        "priority": o.priority,
        "description": o.problem,
        "currency": o.currency,
        "model": (
            (device.model or device.name)
            if device
            else o.template_snapshot.get("name", "Устройство")
        ),
        "serial": device.serial if device else "",
        "problem": o.problem,
        "location": o.location,
        "assigned_to": o.assigned_to,
        "stage": o.stage,
        "stage_name": stage.get("name", o.stage),
        "status": o.status,
        "version": o.version,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
        "stage_entered_at": o.stage_entered_at,
        "due_at": o.due_at,
        "stalled": o.status not in {"issued", "cancelled", "draft"}
        and (deadline < utc() or (o.due_at is not None and o.due_at < utc())),
        "warranty_of": (
            s.get(RepairOrder, o.warranty_of).public_id if o.warranty_of else None
        ),
    }


def detail(s, o, a, events_before=None, attachments_before=None):
    files_query = select(Attachment).where(
        Attachment.order_id == o.id,
        Attachment.id.notin_(restricted_attachment_ids(o, a)),
    )
    events_query = select(RepairEvent).where(RepairEvent.order_id == o.id)
    if "finance.read" not in a.permissions:
        events_query = events_query.where(
            ~RepairEvent.kind.startswith("estimate"),
            ~RepairEvent.kind.startswith("payment"),
        )
    if attachments_before:
        files_query = files_query.where(Attachment.id < attachments_before)
    if events_before:
        events_query = events_query.where(RepairEvent.id < events_before)
    files_page = s.scalars(files_query.order_by(Attachment.id.desc()).limit(31)).all()
    events_page = s.scalars(
        events_query.order_by(RepairEvent.id.desc()).limit(31)
    ).all()

    data = summary(s, o, a)
    fields = visible_fields(o, a)
    keys = {f["key"] for f in fields}
    data.update(
        {
            "condition": o.condition,
            "accessories": o.accessories,
            "template": {**o.template_snapshot, "fields": fields},
            "values": {k: v for k, v in o.values.items() if k in keys},
            "stage_forms": public_forms(o, a),
            "workflow": o.workflow_snapshot,
            "checks": o.checks,
            "intake_snapshot": {
                k: v for k, v in o.intake_snapshot.items() if k != "values"
            },
            "customer": None,
            "device_id": o.device_id,
            "customer_id": o.customer_id,
            "attachments_next": files_page[29].id if len(files_page) > 30 else None,
            "events_next": events_page[29].id if len(events_page) > 30 else None,
            "attachments": [
                {
                    "id": f.id,
                    "filename": f.filename,
                    "phase": f.phase,
                    "created_at": f.created_at,
                }
                for f in files_page[:30]
            ],
            "events": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "data": e.data,
                    "actor_id": e.actor_id,
                    "created_at": e.created_at,
                }
                for e in events_page[:30]
                if not e.kind.startswith(("estimate", "payment"))
                or "finance.read" in a.permissions
            ],
            "receipt": (
                (
                    {
                        **o.receipt,
                        "stage_forms": public_forms(
                            o, a, o.receipt.get("stage_forms", {})
                        ),
                        "values": {
                            k: v
                            for k, v in o.receipt.get("values", {}).items()
                            if k in keys
                        },
                    }
                    if o.receipt
                    else None
                )
                if "finance.read" in a.permissions
                else ({"issued_at": o.receipt["issued_at"]} if o.receipt else None)
            ),
        }
    )
    restricted_files = restricted_attachment_ids(o, a)
    data["attachments"] = [
        f for f in data["attachments"] if f["id"] not in restricted_files
    ]
    for item in data["events"]:
        item["data"] = dict(item["data"])
        event_keys = keys
        if item["data"].get("phase") in o.stage_forms:
            event_keys = {
                f["key"]
                for f in visible_fields(
                    form_proxy(o, o.stage_forms[item["data"]["phase"]]), a
                )
            }
        if "value_changes" in item["data"]:
            item["data"]["value_changes"] = {
                k: v
                for k, v in item["data"]["value_changes"].items()
                if k in event_keys
            }
        if "contacts.read" not in a.permissions:
            item["data"].pop("receiver", None)
        old_receipt = item["data"].get("previous_receipt")
        if old_receipt:
            item["data"]["previous_receipt"] = (
                {
                    **old_receipt,
                    "stage_forms": public_forms(
                        o, a, old_receipt.get("stage_forms", {})
                    ),
                    "values": {
                        k: v
                        for k, v in old_receipt.get("values", {}).items()
                        if k in keys
                    },
                }
                if "finance.read" in a.permissions
                else {"issued_at": old_receipt.get("issued_at")}
            )
    if "contacts.read" in a.permissions and o.customer_id:
        c = s.get(Customer, o.customer_id)
        data["customer"] = {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
        }
    if "finance.read" in a.permissions:
        data["estimates"] = [
            {
                "id": q.id,
                "revision": q.revision,
                "lines": q.lines,
                "total_cents": q.total_cents,
                "currency": q.currency,
                "status": q.status,
                "decision_at": q.decision_at,
                "decision_name": q.decision_name,
                "expires_at": q.expires_at,
            }
            for q in s.scalars(
                select(Estimate)
                .where(Estimate.order_id == o.id)
                .order_by(Estimate.revision.desc())
            ).all()
        ]
        data["payments"] = [
            {
                "id": p.id,
                "amount_cents": p.amount_cents,
                "method": p.method,
                "reference": p.reference,
                "created_at": p.created_at,
            }
            for p in s.scalars(
                select(RepairPayment).where(RepairPayment.order_id == o.id)
            ).all()
        ]
        data["paid_cents"] = paid(s, o)
    return data
