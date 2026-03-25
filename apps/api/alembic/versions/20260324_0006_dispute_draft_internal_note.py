"""Add internal dispute draft note to recovery cases."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260324_0006"
down_revision = "20260324_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recovery_cases",
        sa.Column("draft_internal_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recovery_cases", "draft_internal_note")
