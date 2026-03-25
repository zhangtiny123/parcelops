from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models.copilot import (
    COPILOT_TRACE_STATUS_FAILED,
    CopilotTrace,
)
from app.settings import Settings
from app.structured_logging import get_logger, log_event

from .adapters import get_llm_adapter
from .tools import CopilotToolbox
from .types import ChatMessage, Reference, ToolExecutionResult, UsageStats

logger = get_logger(__name__)


@dataclass(frozen=True)
class CopilotChatResult:
    trace_id: str
    provider_name: str
    model_name: str
    status: str
    message: str
    references: list[Reference]
    tool_results: list[ToolExecutionResult]
    latency_ms: int
    usage: Optional[UsageStats]


def run_copilot_chat(
    messages: list[ChatMessage],
    db: Session,
    settings: Settings,
) -> CopilotChatResult:
    adapter = get_llm_adapter(settings.copilot_provider)
    toolbox = CopilotToolbox(db)
    started_at = perf_counter()
    tool_results: list[ToolExecutionResult] = []
    response_status = COPILOT_TRACE_STATUS_FAILED
    response_message = "Copilot orchestration failed."
    references: list[Reference] = []
    usage: Optional[UsageStats] = None

    try:
        plan = adapter.plan(messages, toolbox.definitions())
        if plan.status == "unsupported":
            response_status = plan.status
            response_message = (
                plan.refusal_message
                or "I can only answer grounded questions about ParcelOps data."
            )
        else:
            for tool_call in plan.tool_calls:
                tool_results.append(
                    toolbox.execute(tool_call.name, tool_call.arguments)
                )

            answer = adapter.compose_answer(messages, tool_results)
            response_status = answer.status
            response_message = answer.message
            references = answer.references
            usage = answer.usage
    except Exception as exc:
        response_message = f"Copilot orchestration failed: {exc}"
        latency_ms = _latency_ms(started_at)
        trace = _persist_trace(
            db=db,
            adapter=adapter,
            status=response_status,
            messages=messages,
            tool_results=tool_results,
            message=response_message,
            references=references,
            latency_ms=latency_ms,
            usage=usage,
        )
        logger.exception(
            "copilot.chat.failed",
            extra={
                "event": "copilot.chat.failed",
                "trace_id": trace.id,
                "status": response_status,
                "provider_name": adapter.provider_name,
                "model_name": adapter.model_name,
                "latency_ms": latency_ms,
            },
        )
        raise

    latency_ms = _latency_ms(started_at)
    trace = _persist_trace(
        db=db,
        adapter=adapter,
        status=response_status,
        messages=messages,
        tool_results=tool_results,
        message=response_message,
        references=references,
        latency_ms=latency_ms,
        usage=usage,
    )
    log_event(
        logger,
        logging.INFO,
        "copilot.chat.completed",
        trace_id=trace.id,
        status=response_status,
        provider_name=adapter.provider_name,
        model_name=adapter.model_name,
        tool_call_count=len(tool_results),
        reference_count=len(references),
        latency_ms=latency_ms,
    )

    return CopilotChatResult(
        trace_id=trace.id,
        provider_name=adapter.provider_name,
        model_name=adapter.model_name,
        status=response_status,
        message=response_message,
        references=references,
        tool_results=tool_results,
        latency_ms=latency_ms,
        usage=usage,
    )


def _persist_trace(
    *,
    db: Session,
    adapter: object,
    status: str,
    messages: list[ChatMessage],
    tool_results: list[ToolExecutionResult],
    message: str,
    references: list[Reference],
    latency_ms: int,
    usage: Optional[UsageStats],
) -> CopilotTrace:
    trace = CopilotTrace(
        provider_name=str(getattr(adapter, "provider_name", "unknown")),
        model_name=str(getattr(adapter, "model_name", "unknown")),
        status=status,
        request_messages_json=jsonable_encoder(messages),
        tool_calls_json=jsonable_encoder(
            [
                {
                    "name": tool_result.name,
                    "arguments": tool_result.arguments,
                    "output": tool_result.output,
                    "references": tool_result.references,
                }
                for tool_result in tool_results
            ]
        ),
        response_text=message,
        response_references_json=jsonable_encoder(references),
        latency_ms=latency_ms,
        prompt_tokens=usage.prompt_tokens if usage is not None else None,
        completion_tokens=usage.completion_tokens if usage is not None else None,
        total_tokens=usage.total_tokens if usage is not None else None,
        estimated_cost_usd=(usage.estimated_cost_usd if usage is not None else None),
    )
    db.add(trace)
    db.commit()
    return trace


def _latency_ms(started_at: float) -> int:
    return max(1, int((perf_counter() - started_at) * 1000))
