# Task 15: Dispute Draft Generator

## Whole-picture context

A strong demo should close the loop from insight to action.

## Specific task goal

Generate structured dispute or recovery drafts from selected issues and cases.

## Requirements

- Add a service that turns issue evidence into a short case summary, dispute email draft, and internal next-step note.
- Support deterministic template-first generation.
- AI can improve phrasing, but should not invent evidence.
- Expose this capability through case APIs and copilot tools.

## Output

Draft recovery artifacts tied to real issue evidence.

## Acceptance criteria

- Generated drafts reference actual issue facts.
- Users can edit the draft afterward.
- Output is readable and operationally useful.
