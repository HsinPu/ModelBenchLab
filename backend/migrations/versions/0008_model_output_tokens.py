"""Store per-model output token limits."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("model_configs") as batch:
        batch.add_column(
            sa.Column(
                "max_output_tokens",
                sa.Integer(),
                nullable=False,
                server_default="32768",
            )
        )


def downgrade():
    with op.batch_alter_table("model_configs") as batch:
        batch.drop_column("max_output_tokens")
