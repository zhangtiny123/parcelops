# Anomaly Rules

The MVP should start with deterministic issue detection for the following cases.

## Parcel billing rules

1. Duplicate charge
2. Billed weight mismatch
3. Zone mismatch
4. Service level mismatch
5. Missing contracted rate or discount
6. Unexpected surcharge spike
7. Invoice line without matched shipment

## 3PL rules

8. Unexpected pick or pack charge
9. Incorrect unit rate vs rate card
10. Invoice line without matched order or shipment

## Each generated issue should include

- issue type
- human-readable explanation
- evidence payload
- estimated recoverable amount
- confidence score
