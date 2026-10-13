"""Provider-agnostic chat client: fallback chain, retry-after aware backoff, response cache, budget.

Design notes
------------
* Free tiers fail with 429s, not bills. A 429 with a short Retry-After is waited out once; a long one
  (or a repeated failure) puts the provider on cooldown and the next provider in the chain is tried.
* The response cache is keyed on the *request* (messages, tools, params), not on the provider, so a
  recorded run can be replayed offline (LLM_CACHE=replay) for evals and CI at zero cost.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from axiom.config import get_settings
from axiom.data.cache import TTLCache, get_cache

from .providers import ProviderSpec, build_chain
from .types import AllProvidersFailed, BudgetExceeded, ChatResult, LLMError, ToolCall, TraceFn, Usage

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
MAX_INLINE_WAIT = 15.0  # seconds we are willing to sleep on a Retry-After before failing over
COOLDOWN = 60.0
# Shared across LLMClient instances (one is created per run) so a rate-limited provider is skipped
# by later runs instead of being rediscovered by every request.
_COOLDOWN: dict[str, float] = {}


class TokenBudget:
    """Hard cap on tokens / calls for one run, so a runaway loop cannot burn a free quota."""

    def __init__(self, max_tokens: int, max_calls: int):
        self.max_tokens, self.max_calls = max_tokens, max_calls
        self.tokens = self.calls = 0

    def check(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"LLM call budget exhausted ({self.max_calls} calls)")
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"Token budget exhausted ({self.tokens}/{self.max_tokens})")

    def add(self, usage: Usage, cached: bool) -> None:
        if not cached:
            self.calls += 1
            self.tokens += usage.total

    def snapshot(self) -> dict[str, int]:
        return {
            "tokens": self.tokens,
            "max_tokens": self.max_tokens,
            "calls": self.calls,
            "max_calls": self.max_calls,
        }


def _request_key(messages: list[dict], tools: list[dict] | None, temperature: float, max_tokens: int) -> str:
    blob = json.dumps(
        {"m": messages, "t": tools, "temp": temperature, "max": max_tokens}, sort_keys=True, default=str
    )
    return "llm:" + hashlib.sha256(blob.encode()).hexdigest()


def _parse_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"__error__": f"arguments not an object: {raw[:100]}"}
    except json.JSONDecodeError:
        return {"__error__": f"invalid JSON arguments: {raw[:100]}"}


class LLMClient:
    def __init__(
        self,
        providers: list[ProviderSpec] | None = None,
        *,
        budget: TokenBudget | None = None,
        cache: TTLCache | None = None,
        cache_mode: str | None = None,
        client_factory: Callable[[ProviderSpec], AsyncOpenAI] | None = None,
    ):
        s = get_settings()
        self.providers = providers if providers is not None else build_chain(s)
        self.budget = budget
        self.cache_mode = cache_mode or s.llm_cache
        self.cache_ttl = s.llm_cache_ttl_days * 86400
        self._cache = cache
        self._make = client_factory or (
            lambda p: AsyncOpenAI(base_url=p.base_url, api_key=p.api_key, timeout=p.timeout, max_retries=0)
        )
        self._clients: dict[str, AsyncOpenAI] = {}
        self._cooldown = _COOLDOWN

    @property
    def cache(self) -> TTLCache:
        return self._cache or get_cache()

    def _client(self, p: ProviderSpec) -> AsyncOpenAI:
        if p.name not in self._clients:
            self._clients[p.name] = self._make(p)
        return self._clients[p.name]

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
        if self.cache_mode != "off":
            hit = self.cache.get(key)
            if hit is not None:
                res = ChatResult(
                    content=hit["content"],
                    tool_calls=[ToolCall(**tc) for tc in hit["tool_calls"]],
                    usage=Usage(**hit["usage"]),
                    provider=hit["provider"],
                    model=hit["model"],
                    cached=True,
                    finish_reason=hit.get("finish_reason", ""),
                )
                self._emit(trace, res, label)
                if self.budget:
                    self.budget.add(res.usage, cached=True)
                return res
        if self.cache_mode == "replay":
            raise LLMError("LLM_CACHE=replay but no recorded response for this request")
        if self.budget:
            self.budget.check()

        errors: dict[str, str] = {}
        for p in self.providers:
            if self._cooldown.get(p.name, 0) > time.monotonic():
                errors[p.name] = "on cooldown after recent rate limit"
                continue
            try:
                res = await self._call_provider(p, messages, tools, temperature, max_tokens)
            except LLMError as e:
                errors[p.name] = str(e)
                if trace:
                    trace("guardrail", {"name": "provider_failover", "detail": f"{p.name}: {e}"})
                continue
            if self.cache_mode == "readwrite":
                self.cache.set(
                    key,
                    {
                        "content": res.content,
                        "tool_calls": [tc.__dict__ for tc in res.tool_calls],
                        "usage": res.usage.__dict__,
                        "provider": res.provider,
                        "model": res.model,
                        "finish_reason": res.finish_reason,
                    },
                    self.cache_ttl,
                )
            if self.budget:
                self.budget.add(res.usage, cached=False)
            self._emit(trace, res, label)
            return res
        raise AllProvidersFailed(errors or {"-": "no providers configured (set a key or run Ollama)"})

    @staticmethod
    def _emit(trace: TraceFn | None, res: ChatResult, label: str) -> None:
        if trace:
            trace(
                "llm_call",
                {
                    "label": label,
                    "provider": res.provider,
                    "model": res.model,
                    "prompt_tokens": res.usage.prompt_tokens,
                    "completion_tokens": res.usage.completion_tokens,
                    "latency_ms": res.latency_ms,
                    "cached": res.cached,
                    "tool_calls": [tc.name for tc in res.tool_calls],
                },
            )

    async def _call_provider(
        self,
        p: ProviderSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {
            "model": p.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if p.extra_body:
            kwargs["extra_body"] = p.extra_body
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        for attempt in (1, 2):
            t0 = time.monotonic()
            try:
                r = await self._client(p).chat.completions.create(**kwargs)
            except APIStatusError as e:
                status = e.status_code
                if status == 429 or status >= 500:
                    wait = _retry_after(e)
                    if attempt == 1 and wait is not None and wait <= MAX_INLINE_WAIT:
                        await asyncio.sleep(wait)
                        continue
                    self._cooldown[p.name] = time.monotonic() + (wait or COOLDOWN)
                    raise LLMError(f"HTTP {status} (rate limited/unavailable)") from e
                raise LLMError(f"HTTP {status}: {_short(e)}") from e
            except (APIConnectionError, APITimeoutError) as e:
                if attempt == 1:
                    await asyncio.sleep(1.0)
                    continue
                self._cooldown[p.name] = time.monotonic() + 15
                raise LLMError(f"connection problem: {type(e).__name__}") from e
            return _to_result(p, r, int((time.monotonic() - t0) * 1000), messages)
        raise LLMError("exhausted attempts")  # pragma: no cover


def _short(e: Exception) -> str:
    return re.sub(r"\s+", " ", str(e))[:200]


def _retry_after(e: APIStatusError) -> float | None:
    try:
        v = e.response.headers.get("retry-after")
        return float(v) if v is not None else None
    except (AttributeError, ValueError):
        return None


def _to_result(p: ProviderSpec, r: Any, latency_ms: int, messages: list[dict[str, Any]]) -> ChatResult:
    choice = r.choices[0]
    msg = choice.message
    content = _THINK.sub("", msg.content or "").strip()
    calls = [
        ToolCall(id=tc.id or f"call_{i}", name=tc.function.name, arguments=_parse_args(tc.function.arguments))
        for i, tc in enumerate(getattr(msg, "tool_calls", None) or [])
    ]
    u = getattr(r, "usage", None)
    usage = Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
    if usage.total == 0:  # some providers omit usage; estimate so the budget still works
        usage = Usage(sum(len(str(m.get("content") or "")) for m in messages) // 4, len(content) // 4)
    return ChatResult(
        content=content,
        tool_calls=calls,
        usage=usage,
        provider=p.name,
        model=getattr(r, "model", p.model) or p.model,
        latency_ms=latency_ms,
        finish_reason=choice.finish_reason or "",
    )
