"""Group large imported datasets and their batch runs."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("dataset_versions") as batch:
        batch.add_column(sa.Column("bundle_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("bundle_name", sa.String(100), nullable=True))
        batch.add_column(sa.Column("bundle_index", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("bundle_total", sa.Integer(), nullable=True))
        batch.create_index("ix_dataset_versions_bundle_id", ["bundle_id"])
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("batch_id", sa.String(36), nullable=True))
        batch.create_index("ix_runs_batch_id", ["batch_id"])


def downgrade():
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_batch_id")
        batch.drop_column("batch_id")
    with op.batch_alter_table("dataset_versions") as batch:
        batch.drop_index("ix_dataset_versions_bundle_id")
        batch.drop_column("bundle_total")
        batch.drop_column("bundle_index")
        batch.drop_column("bundle_name")
        batch.drop_column("bundle_id")
