"""Record/replay LLM wrapper: evals run live once (free local/Groq model), then replay at $0 forever.

Recordings are JSONL keyed by the request hash (provider-independent), so they are git-friendly and a
CI run can assert the *pipeline* still behaves identically on the recorded model outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from axiom.llm.client import LLMClient, TokenBudget, _request_key
from axiom.llm.types import ChatResult, LLMError, ToolCall, TraceFn, Usage


def _dump(res: ChatResult) -> dict[str, Any]:
    return {
        "content": res.content,
        "tool_calls": [tc.__dict__ for tc in res.tool_calls],
        "usage": res.usage.__dict__,
        "provider": res.provider,
        "model": res.model,
        "finish_reason": res.finish_reason,
        "latency_ms": res.latency_ms,
    }


def _load(d: dict[str, Any]) -> ChatResult:
    return ChatResult(
        content=d["content"],
        tool_calls=[ToolCall(**tc) for tc in d["tool_calls"]],
        usage=Usage(**d["usage"]),
        provider=d["provider"],
        model=d["model"],
        finish_reason=d.get("finish_reason", ""),
        latency_ms=d.get("latency_ms", 0),
        cached=True,
    )


class RecordingLLM(LLMClient):
    """mode='record': call the real chain and append; mode='replay': serve only recorded answers."""

    def __init__(self, path: Path, mode: str, budget: TokenBudget | None = None):
        super().__init__(budget=budget, cache_mode="off")
        self.path, self.mode = Path(path), mode
        self.store: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.store[rec["key"]] = rec["response"]
        self.misses = 0

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
        key = _request_key(messages, tools, temperature, max_tokens)
        if key in self.store:
            res = _load(self.store[key])
            if self.budget:
                self.budget.add(res.usage, cached=True)
            self._emit(trace, res, label)
            return res
        if self.mode == "replay":
            self.misses += 1
            raise LLMError(f"no recording for request ({label}); re-record with --record")
        res = await super().chat(
            messages, tools=tools, temperature=temperature, max_tokens=max_tokens, trace=trace, label=label
        )
        self.store[key] = _dump(res)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "response": self.store[key]}) + "\n")
        return res
