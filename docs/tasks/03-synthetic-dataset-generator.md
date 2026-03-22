# Task 03: Synthetic Dataset Generator

## Whole-picture context

The demo needs realistic ecommerce parcel and 3PL data so the product can be shown end-to-end without real customer files.

## Specific task goal

Create a synthetic data generator that outputs realistic CSV files for shipments, parcel invoices, shipment events, orders, 3PL invoice lines, and rate cards.

## Requirements

- Add generator scripts under `scripts/` or `data/generated/`.
- Produce `orders.csv`, `shipments.csv`, `parcel_invoice_lines.csv`, `shipment_events.csv`, `three_pl_invoice_lines.csv`, and `rate_card_rules.csv`.
- Include enough data to show interesting dashboards.
- Seed anomalies intentionally, including duplicate charges, billed weight mismatch, zone mismatch, incorrect 3PL rate, and orphan invoice rows.
- Add a reproducible seed.

## Output

One command that generates a reusable demo dataset.

## Acceptance criteria

- Generated files are valid CSVs.
- The data looks realistic enough for demos.
- At least 10 to 20 anomalies are present by design.
- The `README` explains how to regenerate the dataset.
