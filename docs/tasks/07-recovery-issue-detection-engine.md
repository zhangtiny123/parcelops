# Task 07: Recovery Issue Detection Engine

## Whole-picture context

This is the core business value: finding billing errors and operational waste.

## Specific task goal

Implement the first deterministic issue detection engine using canonical data.

## Requirements

- Add detection services for the 10 MVP issue types.
- Create `RecoveryIssue` records from matched conditions.
- Include issue type, summary, evidence JSON, confidence, and recoverable amount estimate.
- Make detection idempotent for repeated runs.
- Add an API endpoint to trigger detection.
- Add an endpoint to list issues with filters.

## Output

A usable backend issue engine.

## Acceptance criteria

- Running detection creates issue records.
- Known seeded anomalies are detected.
- Re-running detection does not incorrectly duplicate issues.
- The issue list API supports basic filtering.
