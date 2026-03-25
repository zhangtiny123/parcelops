from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional
from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.copilot.adapters import CopilotConfigurationError
from app.copilot.service import run_copilot_chat
from app.copilot.types import ChatMessage
from app.db.session import get_db
from app.settings import get_settings

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotChatMessageRequest(BaseModel):
    role: Literal["assistant", "system", "user"]
    content: str


class CopilotUsageRead(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[Decimal] = None


class CopilotReferenceRead(BaseModel):
    kind: str
    id: str
    label: str
    detail: Optional[str] = None


class CopilotToolCallRead(BaseModel):
    name: str
    arguments: dict[str, Any]


class CopilotChatRequest(BaseModel):
    messages: list[CopilotChatMessageRequest]


class CopilotChatResponse(BaseModel):
    trace_id: str
    provider_name: str
    model_name: str
    status: str
    message: str
    references: list[CopilotReferenceRead]
    tool_calls: list[CopilotToolCallRead]
    latency_ms: int
    usage: Optional[CopilotUsageRead] = None


@router.post("/chat", response_model=CopilotChatResponse)
def chat_with_copilot(
    request: CopilotChatRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CopilotChatResponse:
    try:
        result = run_copilot_chat(
            messages=[
                ChatMessage(role=message.role, content=message.content)
                for message in request.messages
            ],
            db=db,
            settings=get_settings(),
        )
    except CopilotConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Copilot chat failed.",
        ) from exc

    return CopilotChatResponse(
        trace_id=result.trace_id,
        provider_name=result.provider_name,
        model_name=result.model_name,
        status=result.status,
        message=result.message,
        references=[
            CopilotReferenceRead(
                kind=reference.kind,
                id=reference.id,
                label=reference.label,
                detail=reference.detail,
            )
            for reference in result.references
        ],
        tool_calls=[
            CopilotToolCallRead(
                name=tool_result.name,
                arguments=tool_result.arguments,
            )
            for tool_result in result.tool_results
        ],
        latency_ms=result.latency_ms,
        usage=(
            CopilotUsageRead(
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
                estimated_cost_usd=result.usage.estimated_cost_usd,
            )
            if result.usage is not None
            else None
        ),
    )
