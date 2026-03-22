# Task 05: Schema Inference and Column Mapping Support

## Whole-picture context

Real operational files are messy and inconsistent. The product must help map unknown source columns into a canonical schema.

## Specific task goal

Build backend support for file preview, schema inference, and saved column mappings.

## Requirements

- Parse CSV and XLSX preview rows.
- Infer a candidate source kind for shipment, parcel invoice, shipment event, order, 3PL invoice, and rate card files.
- Create a canonical field definition registry.
- Create mapping objects that map source columns to canonical fields.
- Add endpoints to get a preview, get suggested mapping, and save mapping.
- Store mappings in the database.

## Output

A schema mapping backend that the UI can use later.

## Acceptance criteria

- The preview endpoint returns sample rows.
- Suggested mappings are returned for known columns.
- Users can save custom mappings.
- Mapping objects are reusable for normalization.
