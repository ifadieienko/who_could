"""organizations / service domain. Legacy API behavior is preserved."""

from datetime import timedelta
from uuid import uuid4
from app.repair_access import utc
from app.core.permissions import effective_permissions
from app.repair_defaults import DEFAULT_FIELDS, DEFAULT_ROLES, DEFAULT_STAGES
from app.repair_models import FormTemplate, Membership, Workflow, Workshop, WorkshopRole


def seed_workshop(s, user, name):
    w = Workshop(name=name, trial_until=utc() + timedelta(days=14))
    s.add(w)
    s.flush()
    for name, (permissions, scope) in DEFAULT_ROLES.items():
        role = WorkshopRole(
            workshop_id=w.id,
            name=name,
            permissions=sorted(effective_permissions(permissions) | ({"assets.read", "assets.write"} if "orders.create" in permissions else set())),
            scope=scope,
            is_owner=name == "owner",
        )
        s.add(role)
        s.flush()
        if name == "owner":
            s.add(Membership(workshop_id=w.id, user_id=user.id, role_id=role.id))
    s.add(
        FormTemplate(
            workshop_id=w.id,
            family=str(uuid4()),
            name="Телефоны и компьютеры",
            revision=1,
            published=True,
            fields=DEFAULT_FIELDS,
            layout={"columns": 2},
        )
    )
    for phase, label, key in [
        ("diagnosis", "Диагностика", "diagnosis"),
        ("repair", "Ремонт", "work_done"),
        ("quality", "Проверка качества", "test_result"),
    ]:
        s.add(
            FormTemplate(
                workshop_id=w.id,
                family=str(uuid4()),
                name=label,
                purpose=phase,
                published=True,
                fields=[
                    {
                        "key": key,
                        "label": label,
                        "type": "text",
                        "required": True,
                        "width": 2,
                    }
                ],
                layout={"columns": 2},
            )
        )
    s.add(
        Workflow(
            workshop_id=w.id,
            family=str(uuid4()),
            name="Стандартный ремонт",
            revision=1,
            stages=DEFAULT_STAGES,
        )
    )
    return w

