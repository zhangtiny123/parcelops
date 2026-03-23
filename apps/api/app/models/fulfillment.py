from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.common import generate_uuid


class OrderRecord(Base):
    __tablename__ = "order_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    external_order_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    customer_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    promised_service_level: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    warehouse_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    external_shipment_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("order_records.id"),
        nullable=True,
        index=True,
    )
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    origin_zip: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    destination_zip: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    weight_lb: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    dim_weight_lb: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    warehouse_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_row_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
