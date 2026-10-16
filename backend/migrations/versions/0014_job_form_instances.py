"""Preserve stage form snapshots as separately versioned job instances."""
from alembic import op
import sqlalchemy as sa

revision = "0014_job_form_instances"
down_revision = "0013_generic_jobs"
branch_labels = depends_on = None


def upgrade():
    instances = op.create_table(
        "job_form_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workshop_id", sa.Integer(), sa.ForeignKey("workshops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("repair_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slot_key", sa.String(20), nullable=False),
        sa.Column("form_template_family", sa.String(40), nullable=True),
        sa.Column("form_revision", sa.Integer(), nullable=True),
        sa.Column("schema_snapshot", sa.JSON(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", "slot_key", name="uq_job_form_slot"),
    )
    op.create_index("ix_job_form_instances_workshop_id", "job_form_instances", ["workshop_id"])
    connection = op.get_bind()
    orders = sa.table("repair_orders", sa.column("id", sa.Integer()),
        sa.column("workshop_id", sa.Integer()), sa.column("stage_forms", sa.JSON()),
        sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()))
    templates = sa.table("repair_templates", sa.column("id", sa.Integer()),
        sa.column("workshop_id", sa.Integer()), sa.column("family", sa.String(40)))
    after = 0
    while True:
        batch = connection.execute(sa.select(orders).where(orders.c.id > after).order_by(orders.c.id).limit(200)).mappings().all()
        if not batch:
            break
        for job in batch:
            for slot, form in (job["stage_forms"] or {}).items():
                snapshot = form["template"]
                family = connection.execute(sa.select(templates.c.family).where(
                    templates.c.id == snapshot.get("id"),
                    templates.c.workshop_id == job["workshop_id"],
                )).scalar_one_or_none()
                connection.execute(instances.insert().values(
                    workshop_id=job["workshop_id"], job_id=job["id"], slot_key=slot,
                    form_template_family=family, form_revision=snapshot.get("revision"),
                    schema_snapshot=snapshot, values=form["values"], version=1,
                    created_at=job["created_at"], updated_at=job["updated_at"],
                ))
        after = batch[-1]["id"]


def downgrade():
    raise RuntimeError("Restore a verified backup; form instances and versions must be preserved.")
