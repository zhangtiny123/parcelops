"""Initial backend schema for core parcelops entities."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260323_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_order_id", sa.String(length=100), nullable=False),
        sa.Column("customer_ref", sa.String(length=100), nullable=True),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promised_service_level", sa.String(length=64), nullable=True),
        sa.Column("warehouse_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_order_id"),
    )
    op.create_index(
        "ix_order_records_external_order_id",
        "order_records",
        ["external_order_id"],
        unique=True,
    )
    op.create_index("ix_order_records_warehouse_id", "order_records", ["warehouse_id"])

    op.create_table(
        "recovery_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("issue_ids", sa.JSON(), nullable=False),
        sa.Column("draft_summary", sa.Text(), nullable=True),
        sa.Column("draft_email", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_cases_status", "recovery_cases", ["status"])

    op.create_table(
        "rate_card_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("service_level", sa.String(length=64), nullable=True),
        sa.Column("charge_type", sa.String(length=64), nullable=False),
        sa.Column("zone_min", sa.Integer(), nullable=True),
        sa.Column("zone_max", sa.Integer(), nullable=True),
        sa.Column("weight_min_lb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("weight_max_lb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("expected_rate", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=True),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rate_card_rules_charge_type", "rate_card_rules", ["charge_type"]
    )
    op.create_index(
        "ix_rate_card_rules_provider_name", "rate_card_rules", ["provider_name"]
    )
    op.create_index(
        "ix_rate_card_rules_provider_type", "rate_card_rules", ["provider_type"]
    )

    op.create_table(
        "shipments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_shipment_id", sa.String(length=100), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("tracking_number", sa.String(length=64), nullable=False),
        sa.Column("carrier", sa.String(length=64), nullable=False),
        sa.Column("service_level", sa.String(length=64), nullable=True),
        sa.Column("origin_zip", sa.String(length=16), nullable=True),
        sa.Column("destination_zip", sa.String(length=16), nullable=True),
        sa.Column("zone", sa.String(length=16), nullable=True),
        sa.Column("weight_lb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("dim_weight_lb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warehouse_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["order_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shipments_carrier", "shipments", ["carrier"])
    op.create_index(
        "ix_shipments_external_shipment_id",
        "shipments",
        ["external_shipment_id"],
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"])
    op.create_index("ix_shipments_warehouse_id", "shipments", ["warehouse_id"])

    op.create_table(
        "parcel_invoice_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("tracking_number", sa.String(length=64), nullable=False),
        sa.Column("carrier", sa.String(length=64), nullable=False),
        sa.Column("charge_type", sa.String(length=64), nullable=False),
        sa.Column("service_level_billed", sa.String(length=64), nullable=True),
        sa.Column("billed_weight_lb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("zone_billed", sa.String(length=16), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("shipment_id", sa.String(length=36), nullable=True),
        sa.Column("raw_row_ref", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_parcel_invoice_lines_carrier", "parcel_invoice_lines", ["carrier"]
    )
    op.create_index(
        "ix_parcel_invoice_lines_invoice_number",
        "parcel_invoice_lines",
        ["invoice_number"],
    )
    op.create_index(
        "ix_parcel_invoice_lines_shipment_id",
        "parcel_invoice_lines",
        ["shipment_id"],
    )
    op.create_index(
        "ix_parcel_invoice_lines_tracking_number",
        "parcel_invoice_lines",
        ["tracking_number"],
    )

    op.create_table(
        "shipment_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tracking_number", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("raw_row_ref", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shipment_events_tracking_number", "shipment_events", ["tracking_number"]
    )

    op.create_table(
        "three_pl_invoice_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("warehouse_id", sa.String(length=64), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("charge_type", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("unit_rate", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("raw_row_ref", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["order_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_three_pl_invoice_lines_invoice_number",
        "three_pl_invoice_lines",
        ["invoice_number"],
    )
    op.create_index(
        "ix_three_pl_invoice_lines_order_id", "three_pl_invoice_lines", ["order_id"]
    )
    op.create_index("ix_three_pl_invoice_lines_sku", "three_pl_invoice_lines", ["sku"])
    op.create_index(
        "ix_three_pl_invoice_lines_warehouse_id",
        "three_pl_invoice_lines",
        ["warehouse_id"],
    )

    op.create_table(
        "recovery_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "estimated_recoverable_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
        sa.Column("shipment_id", sa.String(length=36), nullable=True),
        sa.Column("parcel_invoice_line_id", sa.String(length=36), nullable=True),
        sa.Column("three_pl_invoice_line_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parcel_invoice_line_id"], ["parcel_invoice_lines.id"]
        ),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"]),
        sa.ForeignKeyConstraint(
            ["three_pl_invoice_line_id"],
            ["three_pl_invoice_lines.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recovery_issues_detected_at", "recovery_issues", ["detected_at"]
    )
    op.create_index(
        "ix_recovery_issues_issue_type",
        "recovery_issues",
        ["issue_type"],
    )
    op.create_index(
        "ix_recovery_issues_parcel_invoice_line_id",
        "recovery_issues",
        ["parcel_invoice_line_id"],
    )
    op.create_index(
        "ix_recovery_issues_provider_name",
        "recovery_issues",
        ["provider_name"],
    )
    op.create_index("ix_recovery_issues_severity", "recovery_issues", ["severity"])
    op.create_index(
        "ix_recovery_issues_shipment_id", "recovery_issues", ["shipment_id"]
    )
    op.create_index("ix_recovery_issues_status", "recovery_issues", ["status"])
    op.create_index(
        "ix_recovery_issues_three_pl_invoice_line_id",
        "recovery_issues",
        ["three_pl_invoice_line_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recovery_issues_three_pl_invoice_line_id", table_name="recovery_issues"
    )
    op.drop_index("ix_recovery_issues_status", table_name="recovery_issues")
    op.drop_index("ix_recovery_issues_shipment_id", table_name="recovery_issues")
    op.drop_index("ix_recovery_issues_severity", table_name="recovery_issues")
    op.drop_index("ix_recovery_issues_provider_name", table_name="recovery_issues")
    op.drop_index(
        "ix_recovery_issues_parcel_invoice_line_id", table_name="recovery_issues"
    )
    op.drop_index("ix_recovery_issues_issue_type", table_name="recovery_issues")
    op.drop_index("ix_recovery_issues_detected_at", table_name="recovery_issues")
    op.drop_table("recovery_issues")

    op.drop_index(
        "ix_three_pl_invoice_lines_warehouse_id", table_name="three_pl_invoice_lines"
    )
    op.drop_index("ix_three_pl_invoice_lines_sku", table_name="three_pl_invoice_lines")
    op.drop_index(
        "ix_three_pl_invoice_lines_order_id", table_name="three_pl_invoice_lines"
    )
    op.drop_index(
        "ix_three_pl_invoice_lines_invoice_number", table_name="three_pl_invoice_lines"
    )
    op.drop_table("three_pl_invoice_lines")

    op.drop_index("ix_shipment_events_tracking_number", table_name="shipment_events")
    op.drop_table("shipment_events")

    op.drop_index(
        "ix_parcel_invoice_lines_tracking_number", table_name="parcel_invoice_lines"
    )
    op.drop_index(
        "ix_parcel_invoice_lines_shipment_id", table_name="parcel_invoice_lines"
    )
    op.drop_index(
        "ix_parcel_invoice_lines_invoice_number", table_name="parcel_invoice_lines"
    )
    op.drop_index("ix_parcel_invoice_lines_carrier", table_name="parcel_invoice_lines")
    op.drop_table("parcel_invoice_lines")

    op.drop_index("ix_shipments_warehouse_id", table_name="shipments")
    op.drop_index("ix_shipments_tracking_number", table_name="shipments")
    op.drop_index("ix_shipments_order_id", table_name="shipments")
    op.drop_index("ix_shipments_external_shipment_id", table_name="shipments")
    op.drop_index("ix_shipments_carrier", table_name="shipments")
    op.drop_table("shipments")

    op.drop_index("ix_rate_card_rules_provider_type", table_name="rate_card_rules")
    op.drop_index("ix_rate_card_rules_provider_name", table_name="rate_card_rules")
    op.drop_index("ix_rate_card_rules_charge_type", table_name="rate_card_rules")
    op.drop_table("rate_card_rules")

    op.drop_index("ix_recovery_cases_status", table_name="recovery_cases")
    op.drop_table("recovery_cases")

    op.drop_index("ix_order_records_warehouse_id", table_name="order_records")
    op.drop_index("ix_order_records_external_order_id", table_name="order_records")
    op.drop_table("order_records")
