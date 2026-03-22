# Domain Model

These are the canonical entities for the MVP.

## Shipment

Represents a shipped parcel tied to an order.

Suggested fields:

- `id`
- `external_shipment_id`
- `order_id`
- `tracking_number`
- `carrier`
- `service_level`
- `origin_zip`
- `destination_zip`
- `zone`
- `weight_lb`
- `dim_weight_lb`
- `shipped_at`
- `delivered_at`
- `warehouse_id`

## ParcelInvoiceLine

Represents one billed line from a parcel carrier invoice.

Suggested fields:

- `id`
- `invoice_number`
- `invoice_date`
- `tracking_number`
- `carrier`
- `charge_type`
- `service_level_billed`
- `billed_weight_lb`
- `zone_billed`
- `amount`
- `currency`
- `shipment_id` nullable
- `raw_row_ref`

## ShipmentEvent

Represents tracking or status events.

Suggested fields:

- `id`
- `tracking_number`
- `event_type`
- `event_time`
- `location`
- `raw_row_ref`

## OrderRecord

Represents order-side context.

Suggested fields:

- `id`
- `external_order_id`
- `customer_ref`
- `order_date`
- `promised_service_level`
- `warehouse_id`

## ThreePLInvoiceLine

Represents one billed line from a 3PL invoice.

Suggested fields:

- `id`
- `invoice_number`
- `invoice_date`
- `warehouse_id`
- `order_id`
- `sku`
- `charge_type`
- `quantity`
- `unit_rate`
- `amount`
- `raw_row_ref`

## RateCardRule

Represents simplified contracted pricing logic.

Suggested fields:

- `id`
- `provider_type` with values `parcel` or `3pl`
- `provider_name`
- `service_level`
- `charge_type`
- `zone_min`
- `zone_max`
- `weight_min_lb`
- `weight_max_lb`
- `expected_rate`
- `effective_start`
- `effective_end`

## RecoveryIssue

Represents a detected anomaly or recoverable problem.

Suggested fields:

- `id`
- `issue_type`
- `provider_name`
- `severity`
- `status`
- `confidence`
- `estimated_recoverable_amount`
- `shipment_id` nullable
- `parcel_invoice_line_id` nullable
- `three_pl_invoice_line_id` nullable
- `summary`
- `evidence_json`
- `detected_at`

## RecoveryCase

Represents a grouped action item or dispute case.

Suggested fields:

- `id`
- `title`
- `status`
- `issue_ids`
- `draft_summary`
- `draft_email`
- `created_at`
- `updated_at`
