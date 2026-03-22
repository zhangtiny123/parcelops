# Task 08: Metrics and Dashboard APIs

## Whole-picture context

Operators need a top-level summary before drilling into details.

## Specific task goal

Build backend endpoints for dashboard metrics and trend summaries.

## Requirements

- Add APIs for total recoverable amount, issues by type, issues by provider, trend over time, and top high-severity issues.
- Prefer fast query patterns.
- Keep response shapes frontend-friendly.

## Output

Backend APIs that support the dashboard.

## Acceptance criteria

- APIs return usable aggregate metrics.
- Numbers align with issue records in the database.
- The trend response is simple to chart in the frontend.
