# Task 13: AI Copilot Backend With Tool-Calling

## Whole-picture context

The AI layer should answer grounded questions over internal data and workflows. It should not guess.

## Specific task goal

Implement the backend AI orchestration layer with tool-style functions over the existing data model.

## Requirements

- Add a provider-agnostic LLM adapter.
- Implement tool functions such as get dashboard metrics, search issues, get issue detail, lookup shipment, and create case draft.
- AI responses must be grounded in tool outputs.
- Store trace data for prompt input, tool calls, response text, latency, and token or cost metadata when available.
- Add a backend chat endpoint.

## Output

A backend copilot that can answer questions using real system data.

## Acceptance criteria

- The copilot can answer data-grounded questions.
- Tool calls are logged.
- Unsupported questions are handled safely.
- The AI layer is isolated from core business logic.
