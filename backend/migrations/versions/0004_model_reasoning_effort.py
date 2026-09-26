"""Store optional per-model reasoning effort."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("model_configs") as batch:
        batch.add_column(sa.Column("reasoning_effort", sa.String(10), nullable=True))


def downgrade():
    with op.batch_alter_table("model_configs") as batch:
        batch.drop_column("reasoning_effort")
