"""Add upload job tracking for raw ingestion."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260323_0002"
down_revision = "20260323_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_upload_jobs_file_type", "upload_jobs", ["file_type"])
    op.create_index("ix_upload_jobs_source_kind", "upload_jobs", ["source_kind"])
    op.create_index("ix_upload_jobs_status", "upload_jobs", ["status"])
    op.create_index("ix_upload_jobs_uploaded_at", "upload_jobs", ["uploaded_at"])


def downgrade() -> None:
    op.drop_index("ix_upload_jobs_uploaded_at", table_name="upload_jobs")
    op.drop_index("ix_upload_jobs_status", table_name="upload_jobs")
    op.drop_index("ix_upload_jobs_source_kind", table_name="upload_jobs")
    op.drop_index("ix_upload_jobs_file_type", table_name="upload_jobs")
    op.drop_table("upload_jobs")
