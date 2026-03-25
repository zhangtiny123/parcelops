#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from random import Random

DEFAULT_SEED = 20260323
DEFAULT_ORDER_COUNT = 240
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "generated"


@dataclass(frozen=True)
class Warehouse:
    warehouse_id: str
    city: str
    state: str
    origin_zip: str
    region: str


@dataclass(frozen=True)
class Destination:
    city: str
    state: str
    destination_zip: str
    region: str
    is_remote: bool


@dataclass(frozen=True)
class Sku:
    sku: str
    unit_weight_lb: Decimal
    unit_price_usd: Decimal


@dataclass(frozen=True)
class OrderRecord:
    external_order_id: str
    customer_ref: str
    order_date: datetime
    promised_service_level: str
    warehouse: Warehouse
    channel: str
    sku: Sku
    quantity: int
    order_value_usd: Decimal
    destination_name: str
    destination: Destination
    is_residential: bool

    def to_row(self) -> dict[str, str]:
        return {
            "external_order_id": self.external_order_id,
            "customer_ref": self.customer_ref,
            "order_date": format_timestamp(self.order_date),
            "promised_service_level": self.promised_service_level,
            "warehouse_id": self.warehouse.warehouse_id,
            "channel": self.channel,
            "sku": self.sku.sku,
            "quantity": str(self.quantity),
            "unit_price_usd": format_decimal(self.sku.unit_price_usd),
            "order_value_usd": format_decimal(self.order_value_usd),
            "destination_name": self.destination_name,
            "destination_city": self.destination.city,
            "destination_state": self.destination.state,
            "destination_zip": self.destination.destination_zip,
            "is_residential": boolean_text(self.is_residential),
        }


@dataclass(frozen=True)
class ShipmentRecord:
    external_shipment_id: str
    external_order_id: str
    tracking_number: str
    carrier: str
    service_level: str
    warehouse: Warehouse
    destination: Destination
    zone: int
    weight_lb: Decimal
    dim_weight_lb: Decimal
    shipped_at: datetime
    delivered_at: datetime
    is_residential: bool

    def to_row(self) -> dict[str, str]:
        return {
            "external_shipment_id": self.external_shipment_id,
            "external_order_id": self.external_order_id,
            "tracking_number": self.tracking_number,
            "carrier": self.carrier,
            "service_level": self.service_level,
            "origin_zip": self.warehouse.origin_zip,
            "destination_zip": self.destination.destination_zip,
            "zone": str(self.zone),
            "weight_lb": format_decimal(self.weight_lb),
            "dim_weight_lb": format_decimal(self.dim_weight_lb),
            "shipped_at": format_timestamp(self.shipped_at),
            "delivered_at": format_timestamp(self.delivered_at),
            "warehouse_id": self.warehouse.warehouse_id,
        }


@dataclass(frozen=True)
class GenerationSummary:
    seed: int
    output_dir: Path
    row_counts: dict[str, int]
    anomaly_counts: dict[str, int]


WAREHOUSES = (
    Warehouse("WH-NJ-01", "Edison", "NJ", "08817", "east"),
    Warehouse("WH-IL-01", "Joliet", "IL", "60431", "central"),
    Warehouse("WH-CA-01", "Ontario", "CA", "91761", "west"),
)

DESTINATIONS = (
    Destination("New York", "NY", "10001", "east", False),
    Destination("Boston", "MA", "02108", "east", False),
    Destination("Philadelphia", "PA", "19103", "east", False),
    Destination("Miami", "FL", "33101", "south", False),
    Destination("Atlanta", "GA", "30303", "south", False),
    Destination("Charlotte", "NC", "28202", "south", False),
    Destination("Dallas", "TX", "75201", "south", False),
    Destination("Houston", "TX", "77002", "south", False),
    Destination("Chicago", "IL", "60601", "central", False),
    Destination("Minneapolis", "MN", "55401", "central", False),
    Destination("Columbus", "OH", "43215", "central", False),
    Destination("Denver", "CO", "80202", "mountain", False),
    Destination("Salt Lake City", "UT", "84101", "mountain", False),
    Destination("Boise", "ID", "83702", "mountain", True),
    Destination("Phoenix", "AZ", "85004", "west", False),
    Destination("Los Angeles", "CA", "90014", "west", False),
    Destination("San Francisco", "CA", "94103", "west", False),
    Destination("Seattle", "WA", "98101", "west", False),
)

SKUS = (
    Sku("SKU-A100", Decimal("0.70"), Decimal("14.00")),
    Sku("SKU-B210", Decimal("1.20"), Decimal("22.00")),
    Sku("SKU-C330", Decimal("2.40"), Decimal("38.00")),
    Sku("SKU-D410", Decimal("3.60"), Decimal("52.00")),
    Sku("SKU-E515", Decimal("4.80"), Decimal("68.00")),
    Sku("SKU-F640", Decimal("6.90"), Decimal("94.00")),
    Sku("SKU-G725", Decimal("8.40"), Decimal("118.00")),
)

CHANNELS = ("shopify", "amazon", "wholesale", "retail")
SERVICE_LEVELS = ("Ground", "2Day", "Overnight")

ZONE_BASE = {
    ("east", "east"): 2,
    ("east", "south"): 4,
    ("east", "central"): 4,
    ("east", "mountain"): 6,
    ("east", "west"): 8,
    ("central", "east"): 4,
    ("central", "south"): 4,
    ("central", "central"): 3,
    ("central", "mountain"): 5,
    ("central", "west"): 7,
    ("west", "east"): 8,
    ("west", "south"): 6,
    ("west", "central"): 7,
    ("west", "mountain"): 4,
    ("west", "west"): 2,
}

PARCEL_SERVICE_BASE = {
    ("UPS", "Ground"): Decimal("7.40"),
    ("UPS", "2Day"): Decimal("13.90"),
    ("UPS", "Overnight"): Decimal("24.80"),
    ("FedEx", "Ground"): Decimal("7.65"),
    ("FedEx", "2Day"): Decimal("14.20"),
    ("FedEx", "Overnight"): Decimal("25.10"),
}

WEIGHT_BANDS = (
    (Decimal("0.00"), Decimal("1.00"), Decimal("0.00")),
    (Decimal("1.01"), Decimal("5.00"), Decimal("3.80")),
    (Decimal("5.01"), Decimal("10.00"), Decimal("7.75")),
    (Decimal("10.01"), Decimal("20.00"), Decimal("12.90")),
)

PARCEL_SURCHARGE_RATES = {
    ("UPS", "residential_surcharge"): Decimal("4.85"),
    ("UPS", "delivery_area_surcharge"): Decimal("6.40"),
    ("FedEx", "residential_surcharge"): Decimal("4.95"),
    ("FedEx", "delivery_area_surcharge"): Decimal("6.55"),
}

THREE_PL_PROVIDER = "FlexFulfill 3PL"
THREE_PL_RATES = {
    "pick_fee": Decimal("2.10"),
    "additional_item_fee": Decimal("0.65"),
    "packaging_fee": Decimal("0.40"),
}

ANOMALY_PLAN = {
    "duplicate_charge": 4,
    "billed_weight_mismatch": 4,
    "zone_mismatch": 3,
    "incorrect_3pl_rate": 3,
    "orphan_parcel_invoice_line": 2,
    "orphan_3pl_invoice_line": 2,
}

ORDER_FIELDS = (
    "external_order_id",
    "customer_ref",
    "order_date",
    "promised_service_level",
    "warehouse_id",
    "channel",
    "sku",
    "quantity",
    "unit_price_usd",
    "order_value_usd",
    "destination_name",
    "destination_city",
    "destination_state",
    "destination_zip",
    "is_residential",
)

SHIPMENT_FIELDS = (
    "external_shipment_id",
    "external_order_id",
    "tracking_number",
    "carrier",
    "service_level",
    "origin_zip",
    "destination_zip",
    "zone",
    "weight_lb",
    "dim_weight_lb",
    "shipped_at",
    "delivered_at",
    "warehouse_id",
)

SHIPMENT_EVENT_FIELDS = (
    "external_shipment_id",
    "tracking_number",
    "event_type",
    "event_time",
    "location",
    "raw_row_ref",
)

PARCEL_INVOICE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "external_shipment_id",
    "tracking_number",
    "carrier",
    "charge_type",
    "service_level_billed",
    "billed_weight_lb",
    "zone_billed",
    "amount",
    "currency",
    "raw_row_ref",
)

THREE_PL_INVOICE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "warehouse_id",
    "external_order_id",
    "sku",
    "charge_type",
    "quantity",
    "unit_rate",
    "amount",
    "raw_row_ref",
)

RATE_CARD_FIELDS = (
    "provider_type",
    "provider_name",
    "service_level",
    "charge_type",
    "zone_min",
    "zone_max",
    "weight_min_lb",
    "weight_max_lb",
    "expected_rate",
    "effective_start",
    "effective_end",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the reusable ParcelOps synthetic demo dataset."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write the generated CSV files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    args = parser.parse_args()

    summary = generate_dataset(args.output_dir, seed=args.seed)
    print(f"Generated demo dataset in {summary.output_dir} with seed {summary.seed}.")
    for file_name, row_count in summary.row_counts.items():
        print(f"- {file_name}: {row_count} rows")
    anomaly_summary = ", ".join(
        f"{name}={count}" for name, count in summary.anomaly_counts.items()
    )
    total_anomalies = sum(summary.anomaly_counts.values())
    print(f"- anomalies: {anomaly_summary} (total={total_anomalies})")


def generate_dataset(output_dir: Path, seed: int = DEFAULT_SEED) -> GenerationSummary:
    rng = Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    orders = build_orders(rng)
    shipments = build_shipments(orders, rng)
    rate_card_rules = build_rate_card_rules()
    parcel_invoice_lines, parcel_anomalies = build_parcel_invoice_lines(shipments, rng)
    shipment_events = build_shipment_events(shipments)
    three_pl_invoice_lines, three_pl_anomalies = build_three_pl_invoice_lines(
        orders, rng
    )

    row_counts = {
        "orders.csv": write_csv(
            output_dir / "orders.csv",
            ORDER_FIELDS,
            [order.to_row() for order in orders],
        ),
        "shipments.csv": write_csv(
            output_dir / "shipments.csv",
            SHIPMENT_FIELDS,
            [shipment.to_row() for shipment in shipments],
        ),
        "parcel_invoice_lines.csv": write_csv(
            output_dir / "parcel_invoice_lines.csv",
            PARCEL_INVOICE_FIELDS,
            parcel_invoice_lines,
        ),
        "shipment_events.csv": write_csv(
            output_dir / "shipment_events.csv",
            SHIPMENT_EVENT_FIELDS,
            shipment_events,
        ),
        "three_pl_invoice_lines.csv": write_csv(
            output_dir / "three_pl_invoice_lines.csv",
            THREE_PL_INVOICE_FIELDS,
            three_pl_invoice_lines,
        ),
        "rate_card_rules.csv": write_csv(
            output_dir / "rate_card_rules.csv",
            RATE_CARD_FIELDS,
            rate_card_rules,
        ),
    }

    anomaly_counts = {
        "duplicate_charge": parcel_anomalies["duplicate_charge"],
        "billed_weight_mismatch": parcel_anomalies["billed_weight_mismatch"],
        "zone_mismatch": parcel_anomalies["zone_mismatch"],
        "incorrect_3pl_rate": three_pl_anomalies["incorrect_3pl_rate"],
        "orphan_parcel_invoice_line": parcel_anomalies["orphan_parcel_invoice_line"],
        "orphan_3pl_invoice_line": three_pl_anomalies["orphan_3pl_invoice_line"],
    }

    return GenerationSummary(
        seed=seed,
        output_dir=output_dir,
        row_counts=row_counts,
        anomaly_counts=anomaly_counts,
    )


def build_orders(rng: Random) -> list[OrderRecord]:
    base_time = datetime(2026, 3, 1, 13, 0, tzinfo=timezone.utc)
    orders: list[OrderRecord] = []

    for index in range(DEFAULT_ORDER_COUNT):
        destination = DESTINATIONS[index % len(DESTINATIONS)]
        warehouse = choose_warehouse(destination, rng)
        sku = SKUS[rng.randrange(len(SKUS))]
        quantity = weighted_choice(rng, ((1, 52), (2, 26), (3, 14), (4, 8)))
        service_level = weighted_choice(
            rng, (("Ground", 72), ("2Day", 20), ("Overnight", 8))
        )
        order_value = quantize_money(sku.unit_price_usd * quantity)
        order_date = base_time + timedelta(hours=(index * 5) + rng.randint(0, 3))
        orders.append(
            OrderRecord(
                external_order_id=f"ORD-{index + 1:05d}",
                customer_ref=f"CUST-{1000 + (index % 60):04d}",
                order_date=order_date,
                promised_service_level=service_level,
                warehouse=warehouse,
                channel=CHANNELS[index % len(CHANNELS)],
                sku=sku,
                quantity=quantity,
                order_value_usd=order_value,
                destination_name=f"Customer {index + 1:04d}",
                destination=destination,
                is_residential=rng.random() < 0.84,
            )
        )

    return orders


def build_shipments(orders: list[OrderRecord], rng: Random) -> list[ShipmentRecord]:
    shipments: list[ShipmentRecord] = []

    for index, order in enumerate(orders):
        carrier = weighted_choice(rng, (("UPS", 56), ("FedEx", 44)))
        zone = estimate_zone(
            order.warehouse.region,
            order.destination.region,
            order.destination.is_remote,
            rng,
        )
        shipped_at = order.order_date + timedelta(
            hours=weighted_choice(rng, ((8, 35), (12, 35), (24, 20), (36, 10)))
        )
        delivered_at = shipped_at + timedelta(
            days=transit_days(
                order.promised_service_level, zone, order.destination.is_remote
            )
        )
        actual_weight = quantize_weight(
            (order.sku.unit_weight_lb * order.quantity)
            + Decimal("0.35")
            + Decimal(rng.randrange(0, 8)) / Decimal("10")
        )
        dim_multiplier = Decimal("1.05") + (
            Decimal(rng.randrange(0, 7)) / Decimal("10")
        )
        dim_weight = quantize_weight(max(actual_weight, actual_weight * dim_multiplier))
        shipments.append(
            ShipmentRecord(
                external_shipment_id=f"SHP-{index + 1:05d}",
                external_order_id=order.external_order_id,
                tracking_number=tracking_number_for(carrier, index + 1),
                carrier=carrier,
                service_level=order.promised_service_level,
                warehouse=order.warehouse,
                destination=order.destination,
                zone=zone,
                weight_lb=actual_weight,
                dim_weight_lb=dim_weight,
                shipped_at=shipped_at,
                delivered_at=delivered_at,
                is_residential=order.is_residential,
            )
        )

    return shipments


def build_shipment_events(shipments: list[ShipmentRecord]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    row_number = 1

    for shipment in shipments:
        in_transit_time = (
            shipment.shipped_at + (shipment.delivered_at - shipment.shipped_at) / 2
        )
        events = (
            (
                "label_created",
                shipment.shipped_at - timedelta(hours=6),
                f"{shipment.warehouse.city}, {shipment.warehouse.state}",
            ),
            (
                "picked_up",
                shipment.shipped_at,
                f"{shipment.warehouse.city}, {shipment.warehouse.state}",
            ),
            ("in_transit", in_transit_time, f"Zone {shipment.zone} network"),
            (
                "delivered",
                shipment.delivered_at,
                f"{shipment.destination.city}, {shipment.destination.state}",
            ),
        )
        for event_type, event_time, location in events:
            rows.append(
                {
                    "external_shipment_id": shipment.external_shipment_id,
                    "tracking_number": shipment.tracking_number,
                    "event_type": event_type,
                    "event_time": format_timestamp(event_time),
                    "location": location,
                    "raw_row_ref": f"EVT-{row_number:06d}",
                }
            )
            row_number += 1

    return rows


def build_rate_card_rules() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    effective_start = "2026-01-01"
    effective_end = "2026-12-31"

    for carrier in ("UPS", "FedEx"):
        for service_level in SERVICE_LEVELS:
            for zone in range(2, 9):
                for weight_min, weight_max, weight_adder in WEIGHT_BANDS:
                    rows.append(
                        {
                            "provider_type": "parcel",
                            "provider_name": carrier,
                            "service_level": service_level,
                            "charge_type": "transportation",
                            "zone_min": str(zone),
                            "zone_max": str(zone),
                            "weight_min_lb": format_decimal(weight_min),
                            "weight_max_lb": format_decimal(weight_max),
                            "expected_rate": format_decimal(
                                parcel_transport_rate(
                                    carrier, service_level, zone, weight_max
                                )
                            ),
                            "effective_start": effective_start,
                            "effective_end": effective_end,
                        }
                    )

        for charge_type in ("residential_surcharge", "delivery_area_surcharge"):
            rows.append(
                {
                    "provider_type": "parcel",
                    "provider_name": carrier,
                    "service_level": "",
                    "charge_type": charge_type,
                    "zone_min": "",
                    "zone_max": "",
                    "weight_min_lb": "",
                    "weight_max_lb": "",
                    "expected_rate": format_decimal(
                        PARCEL_SURCHARGE_RATES[(carrier, charge_type)]
                    ),
                    "effective_start": effective_start,
                    "effective_end": effective_end,
                }
            )

    for charge_type, expected_rate in THREE_PL_RATES.items():
        rows.append(
            {
                "provider_type": "3pl",
                "provider_name": THREE_PL_PROVIDER,
                "service_level": "",
                "charge_type": charge_type,
                "zone_min": "",
                "zone_max": "",
                "weight_min_lb": "",
                "weight_max_lb": "",
                "expected_rate": format_decimal(expected_rate),
                "effective_start": effective_start,
                "effective_end": effective_end,
            }
        )

    return rows


def build_parcel_invoice_lines(
    shipments: list[ShipmentRecord], rng: Random
) -> tuple[list[dict[str, str]], Counter[str]]:
    rows: list[dict[str, str]] = []
    transport_rows_by_shipment_id: dict[str, dict[str, str]] = {}
    row_number = 1

    for shipment in shipments:
        invoice_date = shipment.shipped_at.date() + timedelta(days=5)
        invoice_number = f"{shipment.carrier[:2].upper()}-{invoice_date:%Y%m%d}-{shipment.shipped_at.isocalendar()[1]:02d}"
        billed_weight = billable_weight(shipment.weight_lb, shipment.dim_weight_lb)
        transport_row = {
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "external_shipment_id": shipment.external_shipment_id,
            "tracking_number": shipment.tracking_number,
            "carrier": shipment.carrier,
            "charge_type": "transportation",
            "service_level_billed": shipment.service_level,
            "billed_weight_lb": format_decimal(billed_weight),
            "zone_billed": str(shipment.zone),
            "amount": format_decimal(
                parcel_transport_rate(
                    shipment.carrier,
                    shipment.service_level,
                    shipment.zone,
                    billed_weight,
                )
            ),
            "currency": "USD",
            "raw_row_ref": f"PAR-{row_number:06d}",
        }
        rows.append(transport_row)
        transport_rows_by_shipment_id[shipment.external_shipment_id] = transport_row
        row_number += 1

        if shipment.is_residential:
            rows.append(
                {
                    "invoice_number": invoice_number,
                    "invoice_date": invoice_date.isoformat(),
                    "external_shipment_id": shipment.external_shipment_id,
                    "tracking_number": shipment.tracking_number,
                    "carrier": shipment.carrier,
                    "charge_type": "residential_surcharge",
                    "service_level_billed": shipment.service_level,
                    "billed_weight_lb": "",
                    "zone_billed": "",
                    "amount": format_decimal(
                        PARCEL_SURCHARGE_RATES[
                            (shipment.carrier, "residential_surcharge")
                        ]
                    ),
                    "currency": "USD",
                    "raw_row_ref": f"PAR-{row_number:06d}",
                }
            )
            row_number += 1

        if shipment.destination.is_remote or (
            shipment.zone >= 7 and rng.random() < 0.28
        ):
            rows.append(
                {
                    "invoice_number": invoice_number,
                    "invoice_date": invoice_date.isoformat(),
                    "external_shipment_id": shipment.external_shipment_id,
                    "tracking_number": shipment.tracking_number,
                    "carrier": shipment.carrier,
                    "charge_type": "delivery_area_surcharge",
                    "service_level_billed": shipment.service_level,
                    "billed_weight_lb": "",
                    "zone_billed": "",
                    "amount": format_decimal(
                        PARCEL_SURCHARGE_RATES[
                            (shipment.carrier, "delivery_area_surcharge")
                        ]
                    ),
                    "currency": "USD",
                    "raw_row_ref": f"PAR-{row_number:06d}",
                }
            )
            row_number += 1

    anomalies = Counter()
    duplicate_indices = (11, 37, 88, 143)
    billed_weight_indices = (21, 54, 102, 171)
    zone_mismatch_indices = (26, 76, 129)

    for index in billed_weight_indices:
        shipment = shipments[index]
        row = transport_rows_by_shipment_id[shipment.external_shipment_id]
        inflated_weight = billable_weight(
            shipment.weight_lb + Decimal("2.50"),
            shipment.dim_weight_lb + Decimal("1.50"),
        )
        row["billed_weight_lb"] = format_decimal(inflated_weight)
        row["amount"] = format_decimal(
            parcel_transport_rate(
                shipment.carrier,
                shipment.service_level,
                shipment.zone,
                inflated_weight,
            )
        )
        anomalies["billed_weight_mismatch"] += 1

    for index in zone_mismatch_indices:
        shipment = shipments[index]
        row = transport_rows_by_shipment_id[shipment.external_shipment_id]
        mismatched_zone = min(
            8, shipment.zone + 2 if shipment.zone <= 6 else shipment.zone - 2
        )
        row["zone_billed"] = str(mismatched_zone)
        row["amount"] = format_decimal(
            parcel_transport_rate(
                shipment.carrier,
                shipment.service_level,
                mismatched_zone,
                Decimal(row["billed_weight_lb"]),
            )
        )
        anomalies["zone_mismatch"] += 1

    for index in duplicate_indices:
        shipment = shipments[index]
        source_row = transport_rows_by_shipment_id[shipment.external_shipment_id]
        duplicate_row = dict(source_row)
        duplicate_row["raw_row_ref"] = f"PAR-{row_number:06d}"
        rows.append(duplicate_row)
        row_number += 1
        anomalies["duplicate_charge"] += 1

    orphan_specs = (
        ("SHP-99001", "1Z9999900000000001", "UPS", "Ground", 7, Decimal("9.00")),
        ("SHP-99002", "790000000000", "FedEx", "2Day", 6, Decimal("4.50")),
    )
    for (
        external_shipment_id,
        tracking_number,
        carrier,
        service_level,
        zone,
        billed_weight,
    ) in orphan_specs:
        invoice_date = datetime(2026, 3, 25, tzinfo=timezone.utc).date()
        rows.append(
            {
                "invoice_number": f"{carrier[:2].upper()}-{invoice_date:%Y%m%d}-ORP",
                "invoice_date": invoice_date.isoformat(),
                "external_shipment_id": external_shipment_id,
                "tracking_number": tracking_number,
                "carrier": carrier,
                "charge_type": "transportation",
                "service_level_billed": service_level,
                "billed_weight_lb": format_decimal(billed_weight),
                "zone_billed": str(zone),
                "amount": format_decimal(
                    parcel_transport_rate(carrier, service_level, zone, billed_weight)
                ),
                "currency": "USD",
                "raw_row_ref": f"PAR-{row_number:06d}",
            }
        )
        row_number += 1
        anomalies["orphan_parcel_invoice_line"] += 1

    return rows, anomalies


def build_three_pl_invoice_lines(
    orders: list[OrderRecord], rng: Random
) -> tuple[list[dict[str, str]], Counter[str]]:
    rows: list[dict[str, str]] = []
    pick_fee_rows_by_order_id: dict[str, dict[str, str]] = {}
    row_number = 1

    for order in orders:
        invoice_date = order.order_date.date() + timedelta(days=2)
        invoice_number = f"3PL-{order.warehouse.warehouse_id}-{invoice_date:%Y%m%d}"
        pick_fee_row = {
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "warehouse_id": order.warehouse.warehouse_id,
            "external_order_id": order.external_order_id,
            "sku": order.sku.sku,
            "charge_type": "pick_fee",
            "quantity": "1",
            "unit_rate": format_decimal(THREE_PL_RATES["pick_fee"]),
            "amount": format_decimal(THREE_PL_RATES["pick_fee"]),
            "raw_row_ref": f"TPL-{row_number:06d}",
        }
        rows.append(pick_fee_row)
        pick_fee_rows_by_order_id[order.external_order_id] = pick_fee_row
        row_number += 1

        additional_items = order.quantity - 1
        if additional_items > 0:
            unit_rate = THREE_PL_RATES["additional_item_fee"]
            rows.append(
                {
                    "invoice_number": invoice_number,
                    "invoice_date": invoice_date.isoformat(),
                    "warehouse_id": order.warehouse.warehouse_id,
                    "external_order_id": order.external_order_id,
                    "sku": order.sku.sku,
                    "charge_type": "additional_item_fee",
                    "quantity": str(additional_items),
                    "unit_rate": format_decimal(unit_rate),
                    "amount": format_decimal(unit_rate * additional_items),
                    "raw_row_ref": f"TPL-{row_number:06d}",
                }
            )
            row_number += 1

        if rng.random() < 0.38:
            unit_rate = THREE_PL_RATES["packaging_fee"]
            rows.append(
                {
                    "invoice_number": invoice_number,
                    "invoice_date": invoice_date.isoformat(),
                    "warehouse_id": order.warehouse.warehouse_id,
                    "external_order_id": order.external_order_id,
                    "sku": order.sku.sku,
                    "charge_type": "packaging_fee",
                    "quantity": "1",
                    "unit_rate": format_decimal(unit_rate),
                    "amount": format_decimal(unit_rate),
                    "raw_row_ref": f"TPL-{row_number:06d}",
                }
            )
            row_number += 1

    anomalies = Counter()
    incorrect_rate_indices = (18, 96, 154)

    for index in incorrect_rate_indices:
        order = orders[index]
        row = pick_fee_rows_by_order_id[order.external_order_id]
        inflated_rate = quantize_money(THREE_PL_RATES["pick_fee"] + Decimal("0.75"))
        row["unit_rate"] = format_decimal(inflated_rate)
        row["amount"] = format_decimal(inflated_rate)
        anomalies["incorrect_3pl_rate"] += 1

    orphan_rows = (
        ("ORD-99001", "WH-NJ-01", "SKU-B210", "pick_fee", 1),
        ("ORD-99002", "WH-CA-01", "SKU-F640", "additional_item_fee", 3),
    )
    for external_order_id, warehouse_id, sku, charge_type, quantity in orphan_rows:
        unit_rate = THREE_PL_RATES[charge_type]
        invoice_date = datetime(2026, 3, 26, tzinfo=timezone.utc).date()
        rows.append(
            {
                "invoice_number": f"3PL-{warehouse_id}-{invoice_date:%Y%m%d}-ORP",
                "invoice_date": invoice_date.isoformat(),
                "warehouse_id": warehouse_id,
                "external_order_id": external_order_id,
                "sku": sku,
                "charge_type": charge_type,
                "quantity": str(quantity),
                "unit_rate": format_decimal(unit_rate),
                "amount": format_decimal(unit_rate * quantity),
                "raw_row_ref": f"TPL-{row_number:06d}",
            }
        )
        row_number += 1
        anomalies["orphan_3pl_invoice_line"] += 1

    return rows, anomalies


def choose_warehouse(destination: Destination, rng: Random) -> Warehouse:
    if destination.region == "east":
        choices = ((WAREHOUSES[0], 78), (WAREHOUSES[1], 18), (WAREHOUSES[2], 4))
    elif destination.region == "south":
        choices = ((WAREHOUSES[1], 58), (WAREHOUSES[0], 27), (WAREHOUSES[2], 15))
    elif destination.region == "central":
        choices = ((WAREHOUSES[1], 74), (WAREHOUSES[0], 14), (WAREHOUSES[2], 12))
    elif destination.region == "mountain":
        choices = ((WAREHOUSES[2], 44), (WAREHOUSES[1], 42), (WAREHOUSES[0], 14))
    else:
        choices = ((WAREHOUSES[2], 83), (WAREHOUSES[1], 13), (WAREHOUSES[0], 4))
    return weighted_choice(rng, choices)


def weighted_choice(rng: Random, options):
    total = sum(weight for _, weight in options)
    threshold = rng.uniform(0, total)
    current = 0.0
    for value, weight in options:
        current += weight
        if threshold <= current:
            return value
    return options[-1][0]


def estimate_zone(
    origin_region: str, destination_region: str, is_remote: bool, rng: Random
) -> int:
    zone = ZONE_BASE[(origin_region, destination_region)]
    if rng.random() < 0.34 and zone < 8:
        zone += 1
    if is_remote and zone < 8:
        zone += 1
    return min(zone, 8)


def transit_days(service_level: str, zone: int, is_remote: bool) -> int:
    if service_level == "Overnight":
        return 1
    if service_level == "2Day":
        return 2 if not is_remote else 3
    if zone <= 3:
        return 2
    if zone <= 5:
        return 3
    return 4 if not is_remote else 5


def tracking_number_for(carrier: str, sequence: int) -> str:
    if carrier == "UPS":
        return f"1Z{7000000000000000 + sequence:016d}"
    return f"{790000000000 + sequence:012d}"


def billable_weight(weight_lb: Decimal, dim_weight_lb: Decimal) -> Decimal:
    maximum_weight = max(weight_lb, dim_weight_lb)
    return quantize_weight(
        (maximum_weight * 2).to_integral_value(rounding=ROUND_CEILING) / Decimal("2")
    )


def parcel_transport_rate(
    carrier: str, service_level: str, zone: int, billed_weight_lb: Decimal
) -> Decimal:
    base_rate = PARCEL_SERVICE_BASE[(carrier, service_level)]
    zone_adder = Decimal(zone - 2) * Decimal("1.45")
    weight_adder = None
    for weight_min, weight_max, band_adder in WEIGHT_BANDS:
        lower_bound_matches = billed_weight_lb >= weight_min
        upper_bound_matches = billed_weight_lb <= weight_max
        if lower_bound_matches and upper_bound_matches:
            weight_adder = band_adder
            break
    if weight_adder is None:
        weight_adder = WEIGHT_BANDS[-1][2] + Decimal("3.20")
    return quantize_money(base_rate + zone_adder + weight_adder)


def write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]
) -> int:
    with path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def format_timestamp(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def quantize_money(value: Decimal | int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_weight(value: Decimal | int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def boolean_text(value: bool) -> str:
    return "true" if value else "false"


if __name__ == "__main__":
    main()
