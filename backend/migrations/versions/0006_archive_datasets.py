"""Archive dataset versions without changing historical run snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("dataset_versions") as batch:
        batch.add_column(sa.Column("deleted_at", sa.String(40), nullable=True))


def downgrade():
    raise RuntimeError("Restore a backup to downgrade; archived datasets must be preserved")
