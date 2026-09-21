"""Workshop repair platform; preserves legacy tables and migrates their records."""

from alembic import op
import sqlalchemy as sa
import json
from datetime import datetime, timedelta
from uuid import uuid4

revision = "0009_workshop_platform"
down_revision = "0008_master_service_board"
branch_labels = None
depends_on = None

DEFAULT_FIELDS = [
    {
        "key": "diagnosis",
        "label": "Диагностика",
        "type": "text",
        "section": "Диагностика",
        "width": 2,
        "required": False,
    },
    {
        "key": "work_done",
        "label": "Выполненные работы",
        "type": "text",
        "section": "Ремонт",
        "width": 2,
        "required": False,
    },
]
DEFAULT_STAGES = [
    {
        "key": "received",
        "name": "Принято",
        "category": "active",
        "next": ["diagnosis"],
        "required_fields": [],
        "checks": [],
        "sla_hours": 24,
    },
    {
        "key": "diagnosis",
        "name": "Диагностика",
        "category": "active",
        "next": ["approval", "repair"],
        "required_fields": [],
        "checks": [],
        "sla_hours": 48,
    },
    {
        "key": "approval",
        "name": "Согласование",
        "category": "waiting",
        "next": ["repair", "diagnosis"],
        "required_fields": ["diagnosis"],
        "checks": [],
        "sla_hours": 72,
    },
    {
        "key": "repair",
        "name": "Ремонт",
        "category": "active",
        "next": ["quality", "diagnosis"],
        "required_fields": ["diagnosis"],
        "requires_quote": True,
        "checks": [],
        "sla_hours": 72,
    },
    {
        "key": "quality",
        "name": "Проверка",
        "category": "active",
        "next": ["ready", "repair"],
        "required_fields": ["work_done"],
        "checks": [],
        "sla_hours": 24,
    },
    {
        "key": "ready",
        "name": "Готово к выдаче",
        "category": "ready",
        "next": ["quality"],
        "required_fields": ["work_done"],
        "checks": [
            "Комплектность проверена",
            "Неисправность устранена",
            "Финальный тест пройден",
        ],
        "sla_hours": 168,
    },
]
DEFAULT_ROLES = {
    "owner": (
        [
            "orders.read",
            "orders.create",
            "orders.edit",
            "orders.assign",
            "orders.transition",
            "orders.issue",
            "orders.reopen",
            "contacts.read",
            "finance.read",
            "finance.write",
            "templates.manage",
            "members.manage",
            "data.export",
            "data.import",
            "billing.manage",
            "warehouse.manage",
        ],
        "all",
    ),
    "reception": (
        [
            "orders.read",
            "orders.create",
            "orders.edit",
            "orders.assign",
            "orders.issue",
            "contacts.read",
            "finance.read",
            "finance.write",
        ],
        "all",
    ),
    "master": (["orders.read", "orders.edit", "orders.transition"], "own"),
    "viewer": (["orders.read"], "all"),
}


def upgrade():
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "workshops",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("trial_until", sa.DateTime(), nullable=True),
        sa.Column("billing_status", sa.String(length=30), nullable=False),
        sa.Column("stripe_customer", sa.String(length=100), nullable=True),
        sa.Column("stripe_subscription", sa.String(length=100), nullable=True),
        sa.Column("billing_updated", sa.Integer(), nullable=False),
        sa.Column("paid_until", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "account_tokens",
        sa.Column("token_hash", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_login_sessions_user_id", "login_sessions", ["user_id"], unique=False
    )
    op.create_table(
        "repair_customers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.UniqueConstraint("workshop_id", "external_id"),
    )
    op.create_index(
        "ix_repair_customers_workshop_id",
        "repair_customers",
        ["workshop_id"],
        unique=False,
    )
    op.create_table(
        "repair_templates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column("family", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_repair_templates_workshop_id",
        "repair_templates",
        ["workshop_id"],
        unique=False,
    )
    op.create_index(
        "ix_repair_templates_family", "repair_templates", ["family"], unique=False
    )
    op.create_table(
        "repair_workflows",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("family", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_repair_workflows_workshop_id",
        "repair_workflows",
        ["workshop_id"],
        unique=False,
    )
    op.create_index(
        "ix_repair_workflows_family", "repair_workflows", ["family"], unique=False
    )
    op.create_table(
        "workshop_roles",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id",
            sa.Integer(),
            sa.ForeignKey("workshops.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("workshop_id", "name"),
    )
    op.create_index(
        "ix_workshop_roles_workshop_id", "workshop_roles", ["workshop_id"], unique=False
    )
    op.create_table(
        "repair_devices",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("repair_customers.id"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("serial", sa.String(length=160), nullable=False),
    )
    op.create_index(
        "ix_repair_devices_workshop_id", "repair_devices", ["workshop_id"], unique=False
    )
    op.create_table(
        "workshop_members",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id",
            sa.Integer(),
            sa.ForeignKey("workshops.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("workshop_roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("workshop_id", "user_id"),
    )
    op.create_index(
        "ix_workshop_members_workshop_id",
        "workshop_members",
        ["workshop_id"],
        unique=False,
    )
    op.create_index(
        "ix_workshop_members_user_id", "workshop_members", ["user_id"], unique=False
    )
    op.create_table(
        "repair_orders",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("repair_customers.id"),
            nullable=True,
        ),
        sa.Column(
            "device_id", sa.Integer(), sa.ForeignKey("repair_devices.id"), nullable=True
        ),
        sa.Column(
            "warranty_of",
            sa.Integer(),
            sa.ForeignKey("repair_orders.id"),
            nullable=True,
        ),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("accessories", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=False),
        sa.Column("template_snapshot", sa.JSON(), nullable=False),
        sa.Column("intake_snapshot", sa.JSON(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("workflow_snapshot", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("stage_entered_at", sa.DateTime(), nullable=False),
        sa.Column("stage_deadline", sa.DateTime(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("workshop_id", "external_id"),
    )
    op.create_index(
        "ix_repair_orders_status", "repair_orders", ["status"], unique=False
    )
    op.create_index(
        "ix_repair_orders_assigned_to", "repair_orders", ["assigned_to"], unique=False
    )
    op.create_index(
        "ix_repair_orders_device_id", "repair_orders", ["device_id"], unique=False
    )
    op.create_index(
        "ix_repair_orders_stage_deadline", "repair_orders", ["stage_deadline"]
    )
    op.create_index(
        "ix_repair_orders_workshop_id", "repair_orders", ["workshop_id"], unique=False
    )
    op.create_index("ix_repair_orders_stage", "repair_orders", ["stage"], unique=False)
    op.create_table(
        "repair_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("repair_orders.id"), nullable=False
        ),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_repair_attachments_order_id",
        "repair_attachments",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_repair_attachments_workshop_id",
        "repair_attachments",
        ["workshop_id"],
        unique=False,
    )
    op.create_table(
        "repair_estimates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("repair_orders.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("decision_at", sa.DateTime(), nullable=True),
        sa.Column("decision_name", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("order_id", "revision"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_repair_estimates_workshop_id",
        "repair_estimates",
        ["workshop_id"],
        unique=False,
    )
    op.create_index(
        "ix_repair_estimates_order_id", "repair_estimates", ["order_id"], unique=False
    )
    op.create_table(
        "repair_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("repair_orders.id"), nullable=True
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_repair_events_workshop_id", "repair_events", ["workshop_id"], unique=False
    )
    op.create_index(
        "ix_repair_events_order_id", "repair_events", ["order_id"], unique=False
    )
    op.create_table(
        "repair_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("repair_orders.id"), nullable=True
        ),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("next_attempt", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_repair_outbox_order_id", "repair_outbox", ["order_id"], unique=False
    )
    op.create_table(
        "repair_payments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("repair_orders.id"), nullable=False
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("reference", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_repair_payments_order_id", "repair_payments", ["order_id"], unique=False
    )
    with op.batch_alter_table("warehouse_tables") as batch:
        batch.add_column(sa.Column("workshop_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_warehouse_workshop", "workshops", ["workshop_id"], ["id"]
        )
        batch.create_index("ix_warehouse_tables_workshop_id", ["workshop_id"])
    migrate_legacy(op.get_bind())


def migrate_legacy(bind):
    meta = sa.MetaData()
    meta.reflect(bind=bind)

    def rows(name):
        return bind.execute(sa.select(meta.tables[name])).mappings().all()

    def add(table_name, **values):
        table = meta.tables[table_name]
        defaults = {
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "stage_entered_at": datetime.utcnow(),
            "billing_status": "trialing",
            "billing_updated": 0,
            "revision": 1,
            "published": True,
            "archived": False,
            "active": True,
            "is_owner": False,
            "version": 1,
            "checks": {},
            "intake_snapshot": {},
            "values": {},
            "problem": "",
            "condition": "",
            "accessories": "",
            "location": "",
            "serial": "",
        }
        data = {k: v for k, v in defaults.items() if k in table.c}
        data.update(values)
        return bind.execute(table.insert().values(**data)).inserted_primary_key[0]

    users = rows("users")
    if not users:
        return
    wid = add(
        "workshops",
        name="Перенесённая мастерская",
        trial_until=datetime.utcnow() + timedelta(days=14),
    )
    roles = {
        name: add(
            "workshop_roles",
            workshop_id=wid,
            name=name,
            permissions=perms,
            scope=scope,
            is_owner=name == "owner",
        )
        for name, (perms, scope) in DEFAULT_ROLES.items()
    }
    old_roles = {r["id"]: r["name"] for r in rows("roles")}
    assignments = {u["id"]: set() for u in users}
    for r in rows("user_roles"):
        assignments[r["user_id"]].add(old_roles[r["role_id"]])
    admins = {uid for uid, names in assignments.items() if "admin" in names}
    if not admins:
        admins = {min(assignments)}
    for u in users:
        role = (
            "owner"
            if u["id"] in admins
            else "master" if "master" in assignments[u["id"]] else "reception"
        )
        add("workshop_members", workshop_id=wid, user_id=u["id"], role_id=roles[role])
    add(
        "repair_templates",
        workshop_id=wid,
        family=str(uuid4()),
        name="Телефоны и компьютеры",
        fields=DEFAULT_FIELDS,
        layout={"columns": 2},
    )
    add(
        "repair_workflows",
        workshop_id=wid,
        family=str(uuid4()),
        name="Стандартный ремонт",
        stages=DEFAULT_STAGES,
    )

    def json_value(v):
        return json.loads(v) if isinstance(v, str) else v

    def fields(items):
        return [
            {
                "key": "legacy_" + str(f["id"]),
                "label": f["name"],
                "type": f["field_type"],
                "required": False,
                "width": 1,
                "section": "Приём",
            }
            for f in items
        ]

    forms = {}
    old_fields = rows("device_intake_fields")
    for form in rows("device_intake_forms"):
        form_fields = fields(
            sorted(
                [f for f in old_fields if f["form_id"] == form["id"]],
                key=lambda x: x["position"],
            )
        )
        forms[form["id"]] = add(
            "repair_templates",
            workshop_id=wid,
            family=str(uuid4()),
            name=form["name"],
            fields=form_fields,
            layout={"columns": 2},
        )
    columns = {c["id"]: c for c in rows("master_board_columns")}
    work = {w["order_id"]: w for w in rows("master_work_items")}
    pickup = {p["order_id"]: p for p in rows("customer_pickups")}
    for old in rows("device_intake_orders"):
        # Stable per-order snapshot preserves arbitrary personal legacy stage names.
        owner_columns = sorted(
            [
                c
                for c in columns.values()
                if old["id"] in work and c["owner_id"] == work[old["id"]]["master_id"]
            ],
            key=lambda x: x["position"],
        )
        stages = [
            {
                "key": "legacy_" + str(c["id"]),
                "name": c["name"],
                "category": "ready" if c["is_terminal"] else "active",
                "required_fields": [],
                "checks": [],
                "next": [],
                "sla_hours": 48,
            }
            for c in owner_columns
        ]
        if not stages:
            stages = [
                {
                    "key": "received",
                    "name": "Принято",
                    "category": "active",
                    "next": ["ready"],
                    "required_fields": [],
                    "checks": [],
                    "sla_hours": 48,
                },
                {
                    "key": "ready",
                    "name": "Готово к выдаче",
                    "category": "ready",
                    "next": ["received"],
                    "required_fields": [],
                    "checks": [],
                    "sla_hours": 168,
                },
            ]
        else:
            for stage in stages:
                stage["next"] = [x["key"] for x in stages if x["key"] != stage["key"]]
        status = "draft" if old["status"] == "deferred" else "active"
        current = (
            "legacy_" + str(work[old["id"]]["column_id"])
            if old["id"] in work
            else stages[0]["key"]
        )
        receipt = None
        if old["id"] in pickup:
            status = "issued" if pickup[old["id"]]["status"] == "issued" else "ready"
            if status == "issued":
                receipt = {
                    "issued_at": str(pickup[old["id"]]["issued_at"]),
                    "receiver": "Не записан в прежней версии",
                    "issued_by": old["owner_id"],
                    "note": "Перенесено из прежней версии",
                    "total_cents": 0,
                    "paid_cents": 0,
                    "values": {},
                    "checks": {},
                }
        values = {
            "legacy_" + str(k): v for k, v in (json_value(old["payload"]) or {}).items()
        }
        snapshot = {
            "name": old["form_name"],
            "id": forms.get(old["form_id"]),
            "revision": 1,
            "fields": fields(json_value(old["fields_snapshot"]) or []),
            "layout": {"columns": 2},
        }
        oid = add(
            "repair_orders",
            public_id=str(uuid4()),
            workshop_id=wid,
            external_id="legacy:" + str(old["id"]),
            created_by=old["owner_id"],
            assigned_to=work[old["id"]]["master_id"] if old["id"] in work else None,
            template_snapshot=snapshot,
            workflow_snapshot=stages,
            values=values,
            stage=current,
            status=status,
            created_at=old["created_at"],
            updated_at=old["updated_at"],
            stage_entered_at=old["updated_at"],
            stage_deadline=old["updated_at"] + timedelta(hours=48),
            receipt=receipt,
            intake_snapshot=(
                {"values": values, "accepted_at": str(old["created_at"])}
                if old["status"] == "accepted"
                else {}
            ),
        )
        add(
            "repair_events",
            workshop_id=wid,
            order_id=oid,
            actor_id=old["owner_id"],
            kind="legacy.migrated",
            data={"original_order_id": old["id"]},
        )
    bind.execute(meta.tables["warehouse_tables"].update().values(workshop_id=wid))


def downgrade():
    raise RuntimeError(
        "This migration preserves business history. Restore the pre-upgrade database AND uploads backup for rollback; dropping live repair records is intentionally unsupported."
    )
