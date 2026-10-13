"""A scriptable LLM for tests and offline evals: same interface as LLMClient, no network."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .client import LLMClient, TokenBudget
from .types import ChatResult, ToolCall, TraceFn, Usage

Handler = Callable[[list[dict[str, Any]], list[dict[str, Any]] | None, str], ChatResult]


def reply(content: str = "", tool_calls: list[tuple[str, dict[str, Any]]] | None = None) -> ChatResult:
    calls = [ToolCall(id=f"call_{i}", name=n, arguments=a) for i, (n, a) in enumerate(tool_calls or [])]
    est = max(1, (len(content) + 20 * len(calls)) // 4)
    return ChatResult(
        content=content, tool_calls=calls, usage=Usage(200, est), provider="scripted", model="scripted"
    )


class ScriptedLLM(LLMClient):
    def __init__(self, handler: Handler, budget: TokenBudget | None = None):
        super().__init__([], budget=budget, cache_mode="off")
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        trace: TraceFn | None = None,
        label: str = "",
    ) -> ChatResult:
        if self.budget:
            self.budget.check()
        res = self.handler(messages, tools, label)
        self.calls.append(
            {"label": label, "n_messages": len(messages), "tools": bool(tools), "max_tokens": max_tokens}
        )
        if self.budget:
            self.budget.add(res.usage, cached=False)
        self._emit(trace, res, label)
        return res
