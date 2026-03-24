"""Add upload normalization tracking for canonical loaders."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260323_0004"
down_revision = "20260323_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "upload_jobs",
        sa.Column("normalization_task_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "upload_jobs",
        sa.Column(
            "normalized_row_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "upload_jobs",
        sa.Column(
            "normalization_error_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "upload_jobs",
        sa.Column("normalization_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "upload_jobs",
        sa.Column(
            "normalization_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column("upload_jobs", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index(
        "ix_upload_jobs_normalization_task_id",
        "upload_jobs",
        ["normalization_task_id"],
    )

    op.create_table(
        "upload_normalization_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("upload_job_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row_ref", sa.String(length=128), nullable=False),
        sa.Column("canonical_table", sa.String(length=64), nullable=False),
        sa.Column("canonical_record_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["upload_job_id"], ["upload_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_upload_normalization_records_canonical_table",
        "upload_normalization_records",
        ["canonical_table"],
    )
    op.create_index(
        "ix_upload_normalization_records_raw_row_ref",
        "upload_normalization_records",
        ["raw_row_ref"],
    )
    op.create_index(
        "ix_upload_normalization_records_source_kind",
        "upload_normalization_records",
        ["source_kind"],
    )
    op.create_index(
        "ix_upload_normalization_records_upload_job_id",
        "upload_normalization_records",
        ["upload_job_id"],
    )

    op.create_table(
        "upload_normalization_errors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("upload_job_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row_ref", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("row_data_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["upload_job_id"], ["upload_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_upload_normalization_errors_raw_row_ref",
        "upload_normalization_errors",
        ["raw_row_ref"],
    )
    op.create_index(
        "ix_upload_normalization_errors_source_kind",
        "upload_normalization_errors",
        ["source_kind"],
    )
    op.create_index(
        "ix_upload_normalization_errors_upload_job_id",
        "upload_normalization_errors",
        ["upload_job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_upload_normalization_errors_upload_job_id",
        table_name="upload_normalization_errors",
    )
    op.drop_index(
        "ix_upload_normalization_errors_source_kind",
        table_name="upload_normalization_errors",
    )
    op.drop_index(
        "ix_upload_normalization_errors_raw_row_ref",
        table_name="upload_normalization_errors",
    )
    op.drop_table("upload_normalization_errors")

    op.drop_index(
        "ix_upload_normalization_records_upload_job_id",
        table_name="upload_normalization_records",
    )
    op.drop_index(
        "ix_upload_normalization_records_source_kind",
        table_name="upload_normalization_records",
    )
    op.drop_index(
        "ix_upload_normalization_records_raw_row_ref",
        table_name="upload_normalization_records",
    )
    op.drop_index(
        "ix_upload_normalization_records_canonical_table",
        table_name="upload_normalization_records",
    )
    op.drop_table("upload_normalization_records")

    op.drop_index(
        "ix_upload_jobs_normalization_task_id",
        table_name="upload_jobs",
    )
    op.drop_column("upload_jobs", "last_error")
    op.drop_column("upload_jobs", "normalization_completed_at")
    op.drop_column("upload_jobs", "normalization_started_at")
    op.drop_column("upload_jobs", "normalization_error_count")
    op.drop_column("upload_jobs", "normalized_row_count")
    op.drop_column("upload_jobs", "normalization_task_id")
