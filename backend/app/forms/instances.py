"""Stage form instances, transactionally mirrored for the repair compatibility API."""
from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import select
from app.forms.service import form_proxy, normalize_values, visible_fields
from app.repair_access import event, touch, utc
from app.repair_models import FormTemplate, JobFormInstance


def create_instances(s, job):
    """Called once for a new job, including warranty jobs. Never refresh schemas."""
    for slot, form in job.stage_forms.items():
        snapshot = form["template"]
        template = s.scalar(select(FormTemplate).where(
            FormTemplate.id == snapshot.get("id"),
            FormTemplate.workshop_id == job.workshop_id,
        ))
        s.add(JobFormInstance(
            workshop_id=job.workshop_id, job_id=job.id, slot_key=slot,
            form_template_family=template.family if template else None,
            form_revision=snapshot.get("revision"),
            schema_snapshot=deepcopy(snapshot), values=deepcopy(form["values"]),
            version=1, created_at=job.created_at, updated_at=job.updated_at,
        ))
    s.flush()


def get_instance(s, job, slot):
    instance = s.scalar(select(JobFormInstance).where(
        JobFormInstance.job_id == job.id,
        JobFormInstance.workshop_id == job.workshop_id,
        JobFormInstance.slot_key == slot,
    ))
    if instance is None:
        raise HTTPException(404, "Форма не назначена заказу")
    return instance


def serialize_instance(job, instance, a):
    proxy = form_proxy(job, {"template": instance.schema_snapshot, "values": instance.values})
    fields = visible_fields(proxy, a)
    return {
        "id": instance.id, "job_id": job.public_id, "slot_key": instance.slot_key,
        "form_template_family": instance.form_template_family,
        "form_revision": instance.form_revision,
        "schema_snapshot": {**instance.schema_snapshot, "fields": fields},
        "values": {f["key"]: instance.values.get(f["key"]) for f in fields},
        "version": instance.version,
        "created_at": instance.created_at, "updated_at": instance.updated_at,
    }


def edit_instance(s, job, slot, values, a, *, form_version=None):
    # The caller holds the job/workshop lock and has checked the job version.
    if job.status in {"issued", "cancelled"}:
        raise HTTPException(409, "Заказ закрыт")
    instance = get_instance(s, job, slot)
    if form_version is not None and instance.version != form_version:
        raise HTTPException(409, "Форма изменена другим сотрудником. Обновите карточку.")
    proxy = form_proxy(job, {"template": instance.schema_snapshot, "values": instance.values})
    normalized = normalize_values(s, proxy, values, a)
    changes = {
        key: {"before": instance.values.get(key), "after": value}
        for key, value in normalized.items() if value != instance.values.get(key)
    }
    # Versions represent changes to values, not unrelated job edits or no-op saves.
    if normalized != instance.values:
        instance.values = normalized
        instance.version += 1
        instance.updated_at = utc()
    job.stage_forms = {**job.stage_forms, slot: {
        "template": deepcopy(instance.schema_snapshot), "values": deepcopy(normalized),
    }}
    touch(job)
    event(s, a, job, "form.updated", {"phase": slot, "value_changes": changes})
    return instance
