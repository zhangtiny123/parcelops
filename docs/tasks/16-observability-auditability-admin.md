# Task 16: Observability, Auditability, and Admin Visibility

## Whole-picture context

Because this is an AI plus operations product, traceability matters.

## Specific task goal

Add enough observability so a reviewer can inspect what happened.

## Requirements

- Add structured application logging.
- Add AI trace persistence.
- Add import and normalization status visibility.
- Add a simple admin or debug page or API for recent jobs, failed jobs, and recent copilot traces.
- Preserve source references where possible.

## Output

Basic but credible auditability.

## Acceptance criteria

- A developer can inspect import failures.
- A developer can inspect AI traces.
- Detection runs and status transitions are visible.
