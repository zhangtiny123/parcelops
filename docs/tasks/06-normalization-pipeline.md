# Task 06: Normalization Pipeline and Canonical Loaders

## Whole-picture context

Raw uploaded data must be transformed into canonical tables before anomaly detection can run.

## Specific task goal

Implement background jobs that read uploaded files plus saved mappings and load normalized records into the core domain tables.

## Requirements

- Use Celery for async job execution.
- Add a normalization job for each source kind.
- Convert mapped rows into canonical entities.
- Track normalization status per upload.
- Log row-level errors without failing the entire import.
- Preserve raw-row reference metadata for traceability.

## Output

Background normalization from uploaded files into canonical database tables.

## Acceptance criteria

- A normalization job can be triggered for an upload.
- Canonical records are inserted into Postgres.
- Partial row errors are captured and inspectable.
- Upload status changes through lifecycle states.
