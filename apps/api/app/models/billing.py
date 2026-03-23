from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.common import generate_uuid


class ParcelInvoiceLine(Base):
    __tablename__ = "parcel_invoice_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    charge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    service_level_billed: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    billed_weight_lb: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    zone_billed: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    shipment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("shipments.id"),
        nullable=True,
        index=True,
    )
    raw_row_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class ThreePLInvoiceLine(Base):
    __tablename__ = "three_pl_invoice_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("order_records.id"),
        nullable=True,
        index=True,
    )
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    charge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unit_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    raw_row_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class RateCardRule(Base):
    __tablename__ = "rate_card_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    charge_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    zone_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    zone_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weight_min_lb: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    weight_max_lb: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    expected_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    effective_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
