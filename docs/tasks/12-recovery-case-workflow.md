# Task 12: Recovery Case Workflow

## Whole-picture context

Finding problems is not enough. The product should turn findings into action.

## Specific task goal

Implement a recovery case model, APIs, and UI so operators can turn issues into dispute-ready cases.

## Requirements

- Allow creating a case from one or more issues.
- Store title, status, linked issue IDs, draft summary, and draft email.
- Add a case list page and case detail page.
- Support `open`, `pending`, and `resolved` statuses.
- Allow users to edit generated text.

## Output

A lightweight case management workflow.

## Acceptance criteria

- A user can create a case from selected issues.
- The case is stored in the database.
- A user can view and edit case details in the UI.
- Status updates persist.
