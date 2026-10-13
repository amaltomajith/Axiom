from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# A trace sink: (event_type, data) -> None. The orchestrator wires this to SSE.
TraceFn = Callable[[str, dict[str, Any]], None]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    cached: bool = False
    finish_reason: str = ""

    def assistant_message(self) -> dict[str, Any]:
        """The assistant turn to append to the transcript (OpenAI chat format)."""
        import json

        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        return msg


class LLMError(Exception):
    pass


class BudgetExceeded(LLMError):
    pass


class AllProvidersFailed(LLMError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("All LLM providers failed: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))
