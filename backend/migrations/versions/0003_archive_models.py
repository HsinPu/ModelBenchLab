"""Keep historical model configs when removing them from management."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("model_configs") as batch:
        batch.add_column(sa.Column("deleted_at", sa.String(40), nullable=True))


def downgrade():
    raise RuntimeError(
        "Restore a backup to downgrade; archived models must be preserved"
    )
