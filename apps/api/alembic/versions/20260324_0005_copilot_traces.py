"""Add copilot trace persistence."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260324_0005"
down_revision = "20260323_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_messages_json", sa.JSON(), nullable=False),
        sa.Column("tool_calls_json", sa.JSON(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("response_references_json", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "estimated_cost_usd", sa.Numeric(precision=10, scale=4), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copilot_traces_created_at",
        "copilot_traces",
        ["created_at"],
    )
    op.create_index(
        "ix_copilot_traces_provider_name",
        "copilot_traces",
        ["provider_name"],
    )
    op.create_index(
        "ix_copilot_traces_status",
        "copilot_traces",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_traces_status", table_name="copilot_traces")
    op.drop_index("ix_copilot_traces_provider_name", table_name="copilot_traces")
    op.drop_index("ix_copilot_traces_created_at", table_name="copilot_traces")
    op.drop_table("copilot_traces")
