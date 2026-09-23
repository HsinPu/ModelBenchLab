"""Separate connection credentials and add a per-connection model catalog."""

from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("credential_version", sa.Integer, nullable=False),
        sa.Column("usage", sa.JSON, nullable=False),
        sa.Column("last_checked_at", sa.String(40)),
        sa.Column("last_synced_at", sa.String(40)),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    with op.batch_alter_table("model_configs") as batch:
        batch.add_column(sa.Column("connection_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true())
        )
        batch.add_column(
            sa.Column("routing", sa.JSON, nullable=False, server_default="{}")
        )
        batch.create_foreign_key(
            "fk_model_connection", "provider_connections", ["connection_id"], ["id"]
        )
    op.create_table(
        "model_catalog",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("provider_connections.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("author", sa.String(100), nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("available", sa.Boolean, nullable=False),
        sa.Column("synced_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "connection_id", "model_id", name="uq_catalog_connection_model"
        ),
    )
    bind = op.get_bind()
    meta = sa.MetaData()
    models = sa.Table("model_configs", meta, autoload_with=bind)
    connections = sa.Table("provider_connections", meta, autoload_with=bind)
    for model in bind.execute(sa.select(models)).mappings().all():
        if model["provider"] == "demo":
            continue
        connection_id = str(uuid4())
        # One connection per legacy model; identical endpoints may use different keys.
        bind.execute(
            connections.insert().values(
                id=connection_id,
                name=model["name"],
                provider=model["provider"],
                endpoint=model["endpoint"],
                secret=model["secret"],
                enabled=True,
                status="unverified",
                credential_version=1,
                usage={},
                error="",
                created_at=model["created_at"],
            )
        )
        bind.execute(
            models.update()
            .where(models.c.id == model["id"])
            .values(connection_id=connection_id, secret="")
        )


def downgrade():
    raise RuntimeError(
        "Restore a backup to downgrade; connection credentials must not be discarded"
    )
