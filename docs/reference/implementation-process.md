# Implementation Process

## Task-by-task workflow

For each task:

- treat it as independently implementable
- keep changes scoped
- update docs when behavior changes
- avoid solving future tasks inside the current one unless necessary
- keep interfaces practical instead of over-engineered

## Recommended implementation order

1. Task 01: bootstrap
2. Task 02: backend and database foundation
3. Task 03: dataset generator
4. Task 04: upload API
5. Task 05: mapping backend
6. Task 06: normalization
7. Task 07: issue engine
8. Task 08: dashboard APIs
9. Task 09: frontend shell
10. Task 10: upload UI
11. Task 11: dashboard and issue detail
12. Task 12: recovery cases
13. Task 13: AI backend
14. Task 14: AI frontend
15. Task 15: dispute draft generator
16. Task 16: observability
17. Task 17: evals
18. Task 18: polish

## Implementation rules

- Do not redesign the product unless necessary.
- Keep each PR or task scoped to the assigned task.
- Prefer simple solutions over clever abstractions.
- Keep domain logic in backend services, not scattered across controllers.
- Keep AI orchestration separate from core deterministic recovery logic.
- Use deterministic calculations for money-related outputs whenever possible.
- Make all user-facing issue explanations inspectable.
- Preserve traceability back to source data.
- Update docs when interfaces or commands change.
