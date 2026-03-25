from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.billing import ParcelInvoiceLine
from app.models.common import utcnow
from app.models.fulfillment import OrderRecord, Shipment
from app.models.recovery import RecoveryIssue


def seed_copilot_eval_records(db: Session) -> None:
    now = utcnow()
    order = OrderRecord(
        id="order-1",
        external_order_id="SO-1001",
        customer_ref="customer-1001",
        order_date=now - timedelta(days=12),
        promised_service_level="Ground",
        warehouse_id="PHL-1",
    )
    shipment = Shipment(
        id="shipment-1",
        external_shipment_id="ext-shipment-1",
        order_id=order.id,
        tracking_number="1Z999AA10123456784",
        carrier="UPS",
        service_level="Ground",
        origin_zip="19104",
        destination_zip="10001",
        zone="4",
        weight_lb=Decimal("4.20"),
        dim_weight_lb=Decimal("5.10"),
        shipped_at=now - timedelta(days=11),
        delivered_at=now - timedelta(days=8),
        warehouse_id="PHL-1",
    )
    parcel_invoice_line = ParcelInvoiceLine(
        id="parcel-line-1",
        invoice_number="INV-1001",
        invoice_date=(now - timedelta(days=10)).date(),
        tracking_number=shipment.tracking_number,
        carrier="UPS",
        charge_type="transportation",
        amount=Decimal("18.75"),
        currency="USD",
        shipment_id=shipment.id,
        raw_row_ref="parcel.csv:2",
    )
    issues = [
        RecoveryIssue(
            id="issue-1",
            issue_type="billed_weight_mismatch",
            provider_name="UPS",
            severity="high",
            status="open",
            confidence=Decimal("0.9300"),
            estimated_recoverable_amount=Decimal("12.50"),
            shipment_id=shipment.id,
            parcel_invoice_line_id=parcel_invoice_line.id,
            summary="Billed weight exceeds the modeled shipment weight.",
            evidence_json={
                "invoice_number": "INV-1001",
                "tracking_number": shipment.tracking_number,
            },
            detected_at=now - timedelta(days=3),
        ),
        RecoveryIssue(
            id="issue-2",
            issue_type="duplicate_charge",
            provider_name="UPS",
            severity="medium",
            status="open",
            confidence=Decimal("0.8800"),
            estimated_recoverable_amount=Decimal("6.25"),
            parcel_invoice_line_id=parcel_invoice_line.id,
            summary="The same parcel line appears to have been billed twice.",
            evidence_json={"invoice_number": "INV-1001", "duplicate_count": 2},
            detected_at=now - timedelta(days=2),
        ),
        RecoveryIssue(
            id="issue-3",
            issue_type="duplicate_charge",
            provider_name="FedEx",
            severity="low",
            status="resolved",
            confidence=Decimal("0.7000"),
            estimated_recoverable_amount=Decimal("4.00"),
            summary="Prior-period issue used to validate dashboard deltas.",
            evidence_json={"invoice_number": "INV-2001"},
            detected_at=now - timedelta(days=45),
        ),
    ]

    db.add(order)
    db.add(shipment)
    db.add(parcel_invoice_line)
    db.add_all(issues)
    db.commit()
