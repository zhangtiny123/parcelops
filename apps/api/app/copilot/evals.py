from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence

from sqlalchemy.orm import Session

from app.settings import Settings

from .service import run_copilot_chat
from .types import ChatMessage, ToolExecutionResult

DEFAULT_EVAL_DATASET_PATH = Path(__file__).resolve().with_name("eval_dataset.json")
HallucinationRisk = Literal["low", "medium", "high"]


class CopilotEvalDatasetError(ValueError):
    """Raised when the copilot eval dataset is missing required structure."""


@dataclass(frozen=True)
class CopilotEvalToolCallExpectation:
    name: str
    arguments: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CopilotEvalExpectation:
    status: str
    tool_calls: tuple[CopilotEvalToolCallExpectation, ...] = ()
    correctness_must_include: tuple[str, ...] = ()
    groundedness_must_include: tuple[str, ...] = ()
    required_reference_ids: tuple[str, ...] = ()
    forbidden_fragments: tuple[str, ...] = ()
    min_reference_count: Optional[int] = None
    max_reference_count: Optional[int] = None


@dataclass(frozen=True)
class CopilotEvalCase:
    id: str
    category: str
    question: str
    scoring_notes: str
    expected: CopilotEvalExpectation


@dataclass(frozen=True)
class CopilotEvalDataset:
    name: str
    description: str
    cases: tuple[CopilotEvalCase, ...]


@dataclass(frozen=True)
class CopilotEvalMetricResult:
    score: float
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...]


@dataclass(frozen=True)
class CopilotEvalCaseResult:
    case_id: str
    category: str
    question: str
    passed: bool
    trace_id: Optional[str]
    status: str
    response_message: str
    actual_tool_calls: tuple[dict[str, object], ...]
    actual_reference_ids: tuple[str, ...]
    correctness: CopilotEvalMetricResult
    groundedness: CopilotEvalMetricResult
    tool_call_success: CopilotEvalMetricResult
    hallucination_risk_score: float
    hallucination_risk: HallucinationRisk
    failures: tuple[str, ...]
    scoring_notes: str
    error_message: Optional[str] = None


@dataclass(frozen=True)
class CopilotEvalRunResult:
    dataset_name: str
    dataset_description: str
    total_case_count: int
    passed_case_count: int
    failed_case_count: int
    average_correctness: float
    average_groundedness: float
    average_tool_call_success: float
    high_risk_case_count: int
    medium_risk_case_count: int
    low_risk_case_count: int
    case_results: tuple[CopilotEvalCaseResult, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def load_copilot_eval_dataset(
    path: Path = DEFAULT_EVAL_DATASET_PATH,
) -> CopilotEvalDataset:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CopilotEvalDatasetError(
            f"Copilot eval dataset not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CopilotEvalDatasetError(
            f"Copilot eval dataset is invalid JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise CopilotEvalDatasetError("Copilot eval dataset root must be an object.")

    name = _require_str(payload, "name")
    description = _require_str(payload, "description")
    raw_cases = _require_list(payload, "cases")
    cases = tuple(_load_eval_case(item, index) for index, item in enumerate(raw_cases))
    if not cases:
        raise CopilotEvalDatasetError(
            "Copilot eval dataset must contain at least one case."
        )

    return CopilotEvalDataset(name=name, description=description, cases=cases)


def select_copilot_eval_cases(
    dataset: CopilotEvalDataset,
    case_ids: Optional[Sequence[str]] = None,
) -> tuple[CopilotEvalCase, ...]:
    if not case_ids:
        return dataset.cases

    requested_case_ids = {case_id.strip() for case_id in case_ids if case_id.strip()}
    cases_by_id = {case.id: case for case in dataset.cases}
    missing_case_ids = sorted(
        case_id for case_id in requested_case_ids if case_id not in cases_by_id
    )
    if missing_case_ids:
        raise CopilotEvalDatasetError(
            "Unknown copilot eval case id(s): " + ", ".join(missing_case_ids)
        )
    return tuple(cases_by_id[case_id] for case_id in case_ids if case_id.strip())


def run_copilot_eval_cases(
    *,
    dataset: CopilotEvalDataset,
    cases: Sequence[CopilotEvalCase],
    session_factory: Callable[[], Session],
    settings: Settings,
) -> CopilotEvalRunResult:
    if not cases:
        raise ValueError("At least one copilot eval case is required.")

    case_results = tuple(
        _run_copilot_eval_case(
            case=case,
            session_factory=session_factory,
            settings=settings,
        )
        for case in cases
    )

    total_case_count = len(case_results)
    passed_case_count = sum(1 for case_result in case_results if case_result.passed)
    failed_case_count = total_case_count - passed_case_count
    average_correctness = _average(
        case_result.correctness.score for case_result in case_results
    )
    average_groundedness = _average(
        case_result.groundedness.score for case_result in case_results
    )
    average_tool_call_success = _average(
        case_result.tool_call_success.score for case_result in case_results
    )
    high_risk_case_count = sum(
        1 for case_result in case_results if case_result.hallucination_risk == "high"
    )
    medium_risk_case_count = sum(
        1 for case_result in case_results if case_result.hallucination_risk == "medium"
    )
    low_risk_case_count = sum(
        1 for case_result in case_results if case_result.hallucination_risk == "low"
    )

    return CopilotEvalRunResult(
        dataset_name=dataset.name,
        dataset_description=dataset.description,
        total_case_count=total_case_count,
        passed_case_count=passed_case_count,
        failed_case_count=failed_case_count,
        average_correctness=average_correctness,
        average_groundedness=average_groundedness,
        average_tool_call_success=average_tool_call_success,
        high_risk_case_count=high_risk_case_count,
        medium_risk_case_count=medium_risk_case_count,
        low_risk_case_count=low_risk_case_count,
        case_results=case_results,
    )


def render_copilot_eval_report(run_result: CopilotEvalRunResult) -> str:
    lines = [
        "Copilot Eval Harness",
        f"Dataset: {run_result.dataset_name}",
        f"Description: {run_result.dataset_description}",
        (
            "Summary: "
            f"{run_result.passed_case_count}/{run_result.total_case_count} passed, "
            f"{run_result.failed_case_count} failed"
        ),
        (
            "Averages: "
            f"correctness={_format_score(run_result.average_correctness)}, "
            f"groundedness={_format_score(run_result.average_groundedness)}, "
            f"tool_call_success={_format_score(run_result.average_tool_call_success)}"
        ),
        (
            "Hallucination risk: "
            f"low={run_result.low_risk_case_count}, "
            f"medium={run_result.medium_risk_case_count}, "
            f"high={run_result.high_risk_case_count}"
        ),
        "",
    ]

    case_id_width = max(
        len("Case"),
        max(len(case_result.case_id) for case_result in run_result.case_results),
    )
    status_width = len("Result")
    score_width = len("Ground")
    risk_width = len("Risk")
    header = (
        f"{'Case':<{case_id_width}}  "
        f"{'Result':<{status_width}}  "
        f"{'Correct':>{score_width}}  "
        f"{'Ground':>{score_width}}  "
        f"{'Tools':>{score_width}}  "
        f"{'Risk':<{risk_width}}  Question"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for case_result in run_result.case_results:
        lines.append(
            f"{case_result.case_id:<{case_id_width}}  "
            f"{('PASS' if case_result.passed else 'FAIL'):<{status_width}}  "
            f"{_format_score(case_result.correctness.score):>{score_width}}  "
            f"{_format_score(case_result.groundedness.score):>{score_width}}  "
            f"{_format_score(case_result.tool_call_success.score):>{score_width}}  "
            f"{case_result.hallucination_risk:<{risk_width}}  "
            f"{_truncate(case_result.question, 72)}"
        )

    failing_results = [
        case_result for case_result in run_result.case_results if not case_result.passed
    ]
    if failing_results:
        lines.extend(["", "Failing prompts:"])
        for case_result in failing_results:
            lines.append(
                f"- {case_result.case_id} [{case_result.category}] "
                f"(trace={case_result.trace_id or 'n/a'}, risk={case_result.hallucination_risk})"
            )
            lines.append(f"  Question: {case_result.question}")
            lines.append(
                "  Tools: "
                + (
                    ", ".join(
                        _format_tool_call(tool_call)
                        for tool_call in case_result.actual_tool_calls
                    )
                    if case_result.actual_tool_calls
                    else "none"
                )
            )
            lines.append(
                "  References: "
                + (
                    ", ".join(case_result.actual_reference_ids)
                    if case_result.actual_reference_ids
                    else "none"
                )
            )
            if case_result.error_message:
                lines.append(f"  Error: {case_result.error_message}")
            lines.append("  Failures: " + "; ".join(case_result.failures))
            lines.append("  Notes: " + case_result.scoring_notes)

    return "\n".join(lines)


def _run_copilot_eval_case(
    *,
    case: CopilotEvalCase,
    session_factory: Callable[[], Session],
    settings: Settings,
) -> CopilotEvalCaseResult:
    try:
        with session_factory() as db:
            chat_result = run_copilot_chat(
                messages=[ChatMessage(role="user", content=case.question)],
                db=db,
                settings=settings,
            )
    except Exception as exc:
        correctness = _metric_result(
            [(False, f"copilot chat raised an exception: {exc}")]
        )
        groundedness = _metric_result([(False, "groundedness could not be evaluated")])
        tool_call_success = _metric_result(
            [(False, "tool call success could not be evaluated")]
        )
        failures = (
            correctness.failures + groundedness.failures + tool_call_success.failures
        )
        return CopilotEvalCaseResult(
            case_id=case.id,
            category=case.category,
            question=case.question,
            passed=False,
            trace_id=None,
            status="error",
            response_message="",
            actual_tool_calls=(),
            actual_reference_ids=(),
            correctness=correctness,
            groundedness=groundedness,
            tool_call_success=tool_call_success,
            hallucination_risk_score=1.0,
            hallucination_risk="high",
            failures=failures,
            scoring_notes=case.scoring_notes,
            error_message=str(exc),
        )

    actual_tool_calls = tuple(
        {
            "name": tool_result.name,
            "arguments": _normalize_structure(tool_result.arguments),
        }
        for tool_result in chat_result.tool_results
    )
    actual_reference_ids = tuple(reference.id for reference in chat_result.references)

    correctness = _score_correctness(
        expected=case.expected,
        actual_status=chat_result.status,
        message=chat_result.message,
    )
    groundedness = _score_groundedness(
        expected=case.expected,
        message=chat_result.message,
        actual_reference_ids=actual_reference_ids,
    )
    tool_call_success = _score_tool_calls(
        expected_tool_calls=case.expected.tool_calls,
        actual_tool_results=chat_result.tool_results,
    )
    hallucination_risk_score, hallucination_risk = _score_hallucination_risk(
        correctness=correctness,
        groundedness=groundedness,
        tool_call_success=tool_call_success,
        message=chat_result.message,
        expected=case.expected,
        actual_reference_ids=actual_reference_ids,
    )

    failures = tuple(
        dict.fromkeys(
            correctness.failures + groundedness.failures + tool_call_success.failures
        )
    )
    passed = (
        correctness.score == 1.0
        and groundedness.score == 1.0
        and tool_call_success.score == 1.0
        and hallucination_risk == "low"
    )

    return CopilotEvalCaseResult(
        case_id=case.id,
        category=case.category,
        question=case.question,
        passed=passed,
        trace_id=chat_result.trace_id,
        status=chat_result.status,
        response_message=chat_result.message,
        actual_tool_calls=actual_tool_calls,
        actual_reference_ids=actual_reference_ids,
        correctness=correctness,
        groundedness=groundedness,
        tool_call_success=tool_call_success,
        hallucination_risk_score=hallucination_risk_score,
        hallucination_risk=hallucination_risk,
        failures=failures,
        scoring_notes=case.scoring_notes,
    )


def _score_correctness(
    *,
    expected: CopilotEvalExpectation,
    actual_status: str,
    message: str,
) -> CopilotEvalMetricResult:
    checks: list[tuple[bool, str]] = [
        (
            actual_status == expected.status,
            f"expected status '{expected.status}' but got '{actual_status}'",
        )
    ]
    for fragment in expected.correctness_must_include:
        checks.append(
            (
                fragment in message,
                f"missing required answer fragment '{fragment}'",
            )
        )
    return _metric_result(checks)


def _score_groundedness(
    *,
    expected: CopilotEvalExpectation,
    message: str,
    actual_reference_ids: Sequence[str],
) -> CopilotEvalMetricResult:
    checks: list[tuple[bool, str]] = []
    for fragment in expected.groundedness_must_include:
        checks.append(
            (
                fragment in message,
                f"missing grounded fact fragment '{fragment}'",
            )
        )
    for reference_id in expected.required_reference_ids:
        checks.append(
            (
                reference_id in actual_reference_ids,
                f"missing required reference '{reference_id}'",
            )
        )
    if expected.min_reference_count is not None:
        checks.append(
            (
                len(actual_reference_ids) >= expected.min_reference_count,
                (
                    f"expected at least {expected.min_reference_count} reference(s) "
                    f"but got {len(actual_reference_ids)}"
                ),
            )
        )
    if expected.max_reference_count is not None:
        checks.append(
            (
                len(actual_reference_ids) <= expected.max_reference_count,
                (
                    f"expected at most {expected.max_reference_count} reference(s) "
                    f"but got {len(actual_reference_ids)}"
                ),
            )
        )
    for fragment in expected.forbidden_fragments:
        checks.append(
            (
                fragment not in message,
                f"found forbidden fragment '{fragment}' in response",
            )
        )
    return _metric_result(checks)


def _score_tool_calls(
    *,
    expected_tool_calls: Sequence[CopilotEvalToolCallExpectation],
    actual_tool_results: Sequence[ToolExecutionResult],
) -> CopilotEvalMetricResult:
    checks: list[tuple[bool, str]] = [
        (
            len(actual_tool_results) == len(expected_tool_calls),
            (
                f"expected {len(expected_tool_calls)} tool call(s) "
                f"but got {len(actual_tool_results)}"
            ),
        )
    ]

    for index, expected_tool_call in enumerate(expected_tool_calls):
        if index >= len(actual_tool_results):
            checks.append(
                (
                    False,
                    f"missing tool call #{index + 1} ({expected_tool_call.name})",
                )
            )
            continue

        actual_tool_result = actual_tool_results[index]
        checks.append(
            (
                actual_tool_result.name == expected_tool_call.name,
                (
                    f"tool call #{index + 1} expected '{expected_tool_call.name}' "
                    f"but got '{actual_tool_result.name}'"
                ),
            )
        )

        normalized_arguments_value = _normalize_structure(
            actual_tool_result.arguments
        )
        normalized_arguments: dict[str, object] = {}
        if isinstance(normalized_arguments_value, dict):
            normalized_arguments = {
                str(argument_name): argument_value
                for argument_name, argument_value in normalized_arguments_value.items()
            }
        for argument_name, expected_value in expected_tool_call.arguments.items():
            actual_value = normalized_arguments.get(argument_name)
            normalized_expected_value = _normalize_structure(expected_value)
            checks.append(
                (
                    actual_value == normalized_expected_value,
                    (
                        f"tool '{actual_tool_result.name}' argument '{argument_name}' "
                        f"expected {normalized_expected_value!r} but got {actual_value!r}"
                    ),
                )
            )
    return _metric_result(checks)


def _score_hallucination_risk(
    *,
    correctness: CopilotEvalMetricResult,
    groundedness: CopilotEvalMetricResult,
    tool_call_success: CopilotEvalMetricResult,
    message: str,
    expected: CopilotEvalExpectation,
    actual_reference_ids: Sequence[str],
) -> tuple[float, HallucinationRisk]:
    penalty = 0.0
    penalty += (1.0 - correctness.score) * 0.35
    penalty += (1.0 - groundedness.score) * 0.40
    penalty += (1.0 - tool_call_success.score) * 0.25

    forbidden_hits = sum(
        1 for fragment in expected.forbidden_fragments if fragment in message
    )
    if forbidden_hits:
        penalty += min(0.40, 0.20 * forbidden_hits)

    missing_references = sum(
        1
        for reference_id in expected.required_reference_ids
        if reference_id not in actual_reference_ids
    )
    if missing_references:
        penalty += min(0.40, 0.20 * missing_references)

    hallucination_risk_score = round(min(1.0, penalty), 2)
    if hallucination_risk_score >= 0.67:
        hallucination_risk: HallucinationRisk = "high"
    elif hallucination_risk_score >= 0.34:
        hallucination_risk = "medium"
    else:
        hallucination_risk = "low"
    return hallucination_risk_score, hallucination_risk


def _load_eval_case(payload: object, index: int) -> CopilotEvalCase:
    if not isinstance(payload, dict):
        raise CopilotEvalDatasetError(
            f"Copilot eval case #{index + 1} must be an object."
        )

    expected_payload = payload.get("expected")
    if not isinstance(expected_payload, dict):
        raise CopilotEvalDatasetError(
            f"Copilot eval case '{payload.get('id', index + 1)}' is missing an object-valued 'expected' section."
        )

    raw_tool_calls = expected_payload.get("tool_calls", [])
    if not isinstance(raw_tool_calls, list):
        raise CopilotEvalDatasetError(
            f"Copilot eval case '{payload.get('id', index + 1)}' must define 'tool_calls' as a list."
        )

    tool_calls = []
    for raw_tool_call in raw_tool_calls:
        if not isinstance(raw_tool_call, dict):
            raise CopilotEvalDatasetError(
                f"Copilot eval case '{payload.get('id', index + 1)}' has an invalid tool call entry."
            )
        arguments = raw_tool_call.get("arguments", {})
        if not isinstance(arguments, dict):
            raise CopilotEvalDatasetError(
                f"Copilot eval case '{payload.get('id', index + 1)}' has a non-object tool-call arguments block."
            )
        tool_calls.append(
            CopilotEvalToolCallExpectation(
                name=_require_str(raw_tool_call, "name"),
                arguments={str(key): value for key, value in arguments.items()},
            )
        )

    expected = CopilotEvalExpectation(
        status=_require_str(expected_payload, "status"),
        tool_calls=tuple(tool_calls),
        correctness_must_include=_tuple_of_strs(
            expected_payload,
            "correctness_must_include",
        ),
        groundedness_must_include=_tuple_of_strs(
            expected_payload,
            "groundedness_must_include",
        ),
        required_reference_ids=_tuple_of_strs(
            expected_payload,
            "required_reference_ids",
        ),
        forbidden_fragments=_tuple_of_strs(
            expected_payload,
            "forbidden_fragments",
        ),
        min_reference_count=_optional_int(expected_payload, "min_reference_count"),
        max_reference_count=_optional_int(expected_payload, "max_reference_count"),
    )

    return CopilotEvalCase(
        id=_require_str(payload, "id"),
        category=_require_str(payload, "category"),
        question=_require_str(payload, "question"),
        scoring_notes=_require_str(payload, "scoring_notes"),
        expected=expected,
    )


def _metric_result(checks: Sequence[tuple[bool, str]]) -> CopilotEvalMetricResult:
    if not checks:
        return CopilotEvalMetricResult(
            score=1.0,
            checks_passed=0,
            checks_total=0,
            failures=(),
        )

    checks_passed = sum(1 for passed, _ in checks if passed)
    checks_total = len(checks)
    score = round(checks_passed / checks_total, 2)
    failures = tuple(reason for passed, reason in checks if not passed)
    return CopilotEvalMetricResult(
        score=score,
        checks_passed=checks_passed,
        checks_total=checks_total,
        failures=failures,
    )


def _normalize_structure(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize_structure(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_structure(item) for item in value]
    return value


def _require_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CopilotEvalDatasetError(f"Expected '{key}' to be a non-empty string.")
    return value.strip()


def _require_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise CopilotEvalDatasetError(f"Expected '{key}' to be a list.")
    return value


def _tuple_of_strs(payload: dict[str, object], key: str) -> tuple[str, ...]:
    raw_items = payload.get(key, [])
    if raw_items is None:
        return ()
    if not isinstance(raw_items, list):
        raise CopilotEvalDatasetError(f"Expected '{key}' to be a list of strings.")
    normalized_items: list[str] = []
    for item in raw_items:
        if not isinstance(item, str) or not item.strip():
            raise CopilotEvalDatasetError(
                f"Expected '{key}' to contain only non-empty strings."
            )
        normalized_items.append(item)
    return tuple(normalized_items)


def _optional_int(payload: dict[str, object], key: str) -> Optional[int]:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise CopilotEvalDatasetError(f"Expected '{key}' to be an integer.")
    return value


def _average(values: Sequence[float] | Any) -> float:
    values_list = list(values)
    if not values_list:
        return 0.0
    return round(sum(values_list) / len(values_list), 2)


def _format_score(score: float) -> str:
    return f"{score:.2f}"


def _format_tool_call(tool_call: dict[str, object]) -> str:
    name = str(tool_call.get("name", "unknown"))
    arguments = tool_call.get("arguments", {})
    if not isinstance(arguments, dict) or not arguments:
        return name
    arguments_summary = ", ".join(
        f"{argument_name}={argument_value!r}"
        for argument_name, argument_value in sorted(arguments.items())
        if argument_value is not None
    )
    return f"{name}({arguments_summary})" if arguments_summary else name


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
