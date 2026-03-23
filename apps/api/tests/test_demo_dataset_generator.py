import csv
import importlib
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

generate_demo_dataset = importlib.import_module("scripts.generate_demo_dataset")
DEFAULT_SEED = generate_demo_dataset.DEFAULT_SEED
billable_weight = generate_demo_dataset.billable_weight
generate_dataset = generate_demo_dataset.generate_dataset


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file_handle:
        return list(csv.DictReader(file_handle))


def test_generate_demo_dataset(tmp_path: Path) -> None:
    summary = generate_dataset(tmp_path)

    assert summary.seed == DEFAULT_SEED
    assert summary.anomaly_counts == {
        "duplicate_charge": 4,
        "billed_weight_mismatch": 4,
        "zone_mismatch": 3,
        "incorrect_3pl_rate": 3,
        "orphan_parcel_invoice_line": 2,
        "orphan_3pl_invoice_line": 2,
    }

    expected_files = {
        "orders.csv",
        "shipments.csv",
        "parcel_invoice_lines.csv",
        "shipment_events.csv",
        "three_pl_invoice_lines.csv",
        "rate_card_rules.csv",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected_files

    orders = read_csv_rows(tmp_path / "orders.csv")
    shipments = read_csv_rows(tmp_path / "shipments.csv")
    parcel_invoice_lines = read_csv_rows(tmp_path / "parcel_invoice_lines.csv")
    shipment_events = read_csv_rows(tmp_path / "shipment_events.csv")
    three_pl_invoice_lines = read_csv_rows(tmp_path / "three_pl_invoice_lines.csv")
    rate_card_rules = read_csv_rows(tmp_path / "rate_card_rules.csv")

    assert len(orders) == 240
    assert len(shipments) == 240
    assert len(shipment_events) == 960
    assert len(parcel_invoice_lines) > 430
    assert len(three_pl_invoice_lines) > 420
    assert len(rate_card_rules) == 175

    shipments_by_tracking = {row["tracking_number"]: row for row in shipments}
    order_ids = {row["external_order_id"] for row in orders}
    three_pl_rates = {
        row["charge_type"]: Decimal(row["expected_rate"])
        for row in rate_card_rules
        if row["provider_type"] == "3pl"
    }

    duplicate_count = count_duplicate_charges(parcel_invoice_lines)
    billed_weight_mismatch_count = count_billed_weight_mismatches(
        parcel_invoice_lines, shipments_by_tracking
    )
    zone_mismatch_count = count_zone_mismatches(
        parcel_invoice_lines, shipments_by_tracking
    )
    orphan_parcel_count = sum(
        1
        for row in parcel_invoice_lines
        if row["charge_type"] == "transportation"
        and row["tracking_number"] not in shipments_by_tracking
    )
    incorrect_3pl_rate_count = sum(
        1
        for row in three_pl_invoice_lines
        if row["external_order_id"] in order_ids
        and Decimal(row["unit_rate"]) != three_pl_rates[row["charge_type"]]
    )
    orphan_3pl_count = sum(
        1 for row in three_pl_invoice_lines if row["external_order_id"] not in order_ids
    )

    assert duplicate_count == 4
    assert billed_weight_mismatch_count == 4
    assert zone_mismatch_count == 3
    assert incorrect_3pl_rate_count == 3
    assert orphan_parcel_count == 2
    assert orphan_3pl_count == 2


def count_duplicate_charges(parcel_invoice_lines: list[dict[str, str]]) -> int:
    seen: dict[tuple[str, ...], int] = {}
    for row in parcel_invoice_lines:
        key = (
            row["invoice_number"],
            row["tracking_number"],
            row["charge_type"],
            row["service_level_billed"],
            row["billed_weight_lb"],
            row["zone_billed"],
            row["amount"],
        )
        seen[key] = seen.get(key, 0) + 1
    return sum(count - 1 for count in seen.values() if count > 1)


def count_billed_weight_mismatches(
    parcel_invoice_lines: list[dict[str, str]],
    shipments_by_tracking: dict[str, dict[str, str]],
) -> int:
    count = 0
    for row in parcel_invoice_lines:
        if row["charge_type"] != "transportation":
            continue
        shipment = shipments_by_tracking.get(row["tracking_number"])
        if shipment is None:
            continue
        billed_weight = Decimal(row["billed_weight_lb"])
        expected_billable_weight = billable_weight(
            Decimal(shipment["weight_lb"]), Decimal(shipment["dim_weight_lb"])
        )
        if billed_weight > expected_billable_weight:
            count += 1
    return count


def count_zone_mismatches(
    parcel_invoice_lines: list[dict[str, str]],
    shipments_by_tracking: dict[str, dict[str, str]],
) -> int:
    count = 0
    for row in parcel_invoice_lines:
        if row["charge_type"] != "transportation":
            continue
        shipment = shipments_by_tracking.get(row["tracking_number"])
        if shipment is None:
            continue
        if row["zone_billed"] != shipment["zone"]:
            count += 1
    return count
