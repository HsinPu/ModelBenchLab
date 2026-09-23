"""Adopt the existing v0.1 schema, or create it for a new installation."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    meta = sa.MetaData()
    sa.Table(
        "model_configs",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    sa.Table(
        "dataset_versions",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("cases", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    sa.Table(
        "prompt_versions",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    sa.Table(
        "runs",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("finished_at", sa.String(40)),
    )
    sa.Table(
        "run_items",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("model_id", sa.String(36), nullable=False),
        sa.Column("case_index", sa.Integer, nullable=False),
        sa.Column("repeat_index", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("result", sa.JSON),
        sa.Column("attempts", sa.JSON, nullable=False),
        sa.Column("started_at", sa.String(40)),
        sa.Column("finished_at", sa.String(40)),
    )
    sa.Table(
        "human_reviews",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "item_id",
            sa.String(36),
            sa.ForeignKey("run_items.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in meta.sorted_tables:
        if inspector.has_table(table.name):
            actual = {c["name"] for c in inspector.get_columns(table.name)}
            if not set(table.columns.keys()).issubset(actual):
                raise RuntimeError("Unexpected legacy schema: " + table.name)
        else:
            table.create(bind)


def downgrade():
    raise RuntimeError(
        "Restore the pre-upgrade backup to return to v0.1; destructive downgrade is disabled"
    )
