"""Archive test records while retaining their snapshots, items, and reviews."""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("deleted_at", sa.String(40), nullable=True))


def downgrade():
    raise RuntimeError("Restore a backup to downgrade; archived test records must be preserved")
