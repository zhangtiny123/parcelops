"""Add upload mappings for schema inference support."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260323_0003"
down_revision = "20260323_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("upload_job_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("column_mappings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["upload_job_id"], ["upload_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_job_id"),
    )
    op.create_index(
        "ix_upload_mappings_source_kind", "upload_mappings", ["source_kind"]
    )
    op.create_index(
        "ix_upload_mappings_upload_job_id",
        "upload_mappings",
        ["upload_job_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_upload_mappings_upload_job_id", table_name="upload_mappings")
    op.drop_index("ix_upload_mappings_source_kind", table_name="upload_mappings")
    op.drop_table("upload_mappings")
