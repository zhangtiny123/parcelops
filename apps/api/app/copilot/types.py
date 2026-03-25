from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Optional

ChatRole = Literal["assistant", "system", "user"]
CopilotStatus = Literal["completed", "unsupported"]


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str


@dataclass(frozen=True)
class Reference:
    kind: str
    id: str
    label: str
    detail: Optional[str] = None


@dataclass(frozen=True)
class UsageStats:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[Decimal] = None


@dataclass(frozen=True)
class ToolCallRequest:
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    arguments: dict[str, object]
    output: dict[str, object]
    references: list[Reference] = field(default_factory=list)


@dataclass(frozen=True)
class AdapterPlan:
    status: CopilotStatus
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    refusal_message: Optional[str] = None


@dataclass(frozen=True)
class CopilotAnswer:
    status: CopilotStatus
    message: str
    references: list[Reference] = field(default_factory=list)
    usage: Optional[UsageStats] = None
