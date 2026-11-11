"""The LLM brain: a free LLM picks among strategies the tournament already qualified, or stays flat.

Boundaries, all enforced in code:
  * It is consulted only when the rule brain has a candidate entry. Exits and holds stay mechanical, so an
    LLM can never keep a losing position open longer than the rules would.
  * It may choose only a strategy that qualified on the trailing window and is signalling long now, or
    `stay_flat` (a veto). It never sees an order API, never sets quantity or the stop.
  * Its reply must be one JSON object of a fixed schema (`extra="forbid"`): asking for a size, a leverage,
    or anything else makes the reply invalid, and the rule brain decides instead, marked `degraded`.
  * Numbers in its thesis must appear in the facts it was given, or the thesis is discarded.
  * News reaches it sanitized and fenced as untrusted data; suspected injections are redacted and flagged.
  * Calls are capped per hour and cached by the LLM client.

It is never run over history: an LLM may remember what happened next. It is judged forward, on paper, by
its trade contracts.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from axiom.agents.jsonutil import extract_json
from axiom.config import get_settings
from axiom.security import UNTRUSTED_NOTICE, fence

from .brain import Decision, MarketView, rule_decision
from .journal import accept_rewrite, unsupported_numbers
from .strategies import DESCRIPTIONS

NewsFn = Callable[[str], Awaitable[list[dict]]]

SYSTEM = (
    "You are the strategy selector inside a paper-trading agent. A deterministic risk kernel sizes every "
    "trade and sets the stop; you cannot change either. You receive facts about one symbol and the "
    "strategies that qualified in a walk-forward tournament and are signalling long. Choose one of them, "
    "or choose stay_flat if the facts or the news argue against entering now.\n"
    "Reply with ONE JSON object and nothing else, with exactly these keys:\n"
    '{"action": "enter_long" | "stay_flat", "strategy": <one of the candidate names, or null>, '
    '"confidence": <probability 0..1 that the trade ends in profit after fees>, '
    '"thesis": <one or two sentences; use only numbers that appear in the facts>, '
    '"expected_move_pct": <expected gain in percent if right, or null>, '
    '"horizon_bars": <bars you expect the trade to need, 1..200, or null>}\n'
    "Be calibrated: most short-horizon trades are close to a coin flip. " + UNTRUSTED_NOTICE
)

NARRATE_SYSTEM = (
    "Rewrite this trading journal entry in plain, friendly English for a non-expert, in at most three "
    "sentences. Keep every number exactly as written. Do not add any number, fact or opinion that is not "
    "in the entry. Reply with the rewritten text only."
)


class LLMChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["enter_long", "stay_flat"]
    strategy: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    thesis: str = Field(min_length=1, max_length=600)
    expected_move_pct: float | None = Field(default=None, gt=0.0, le=50.0)
    horizon_bars: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def _entry_fields(self) -> LLMChoice:
        if self.action == "enter_long":
            if not self.strategy:
                raise ValueError("enter_long needs a strategy")
            if self.expected_move_pct is None or self.horizon_bars is None:
                raise ValueError("enter_long needs expected_move_pct and horizon_bars")
        return self


class LLMBrain:
    name = "llm"

    def __init__(
        self,
        llm,
        *,
        max_calls_per_hour: int = 20,
        news: NewsFn | None = None,
        timeout: float = 45.0,
        clock: Callable[[], float] = time.time,
        narrate_entries: bool = True,
    ):
        self.llm = llm
        self.max_calls_per_hour = max_calls_per_hour
        self.news = news
        self.timeout = timeout
        self.clock = clock
        self.narrate_entries = narrate_entries
        self.calls: deque[float] = deque()
        self.last_error: str | None = None

    @classmethod
    def from_settings(cls) -> LLMBrain:
        from axiom.llm.client import LLMClient

        from .data import fetch_news
        from .symbols import parse

        s = get_settings()

        async def news(symbol: str) -> list[dict]:
            return await fetch_news(parse(symbol), key=s.alpaca_api_key, secret=s.alpaca_secret_key)

        return cls(LLMClient(), max_calls_per_hour=s.trader_max_llm_calls_per_hour, news=news)

    # --------------------------------------------------------------- budget
    def _take_call(self) -> bool:
        now = self.clock()
        while self.calls and now - self.calls[0] >= 3600:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls_per_hour:
            return False
        self.calls.append(now)
        return True

    def calls_left(self) -> int:
        now = self.clock()
        return max(0, self.max_calls_per_hour - sum(1 for t in self.calls if now - t < 3600))

    # --------------------------------------------------------------- decide
    async def decide(self, view: MarketView) -> Decision:
        base = rule_decision(view)
        if base.action != "enter_long" or view.ranking is None:
            return base
        candidates = [s for s in view.ranking.qualified if view.signals_now.get(s.strategy) == 1.0]
        if not candidates:
            return base
        news = view.news
        if not news and self.news is not None:
            try:
                news = await self.news(view.symbol)
            except Exception:
                news = []
        flags = [
            f"A headline from {n.get('source') or 'an unknown source'} looked like a prompt injection"
            f"{': ' + repr(n['excerpt']) if n.get('excerpt') else ''}. It was redacted before the LLM saw it "
            "and ignored."
            for n in news
            if n.get("injection_suspected")
        ]
        if not self._take_call():
            return _fallback(base, "the hourly LLM call cap was reached", flags)

        facts = _facts(view, candidates)
        headlines = "\n".join(
            f"- [{n.get('date') or '?'}] {n.get('source') or '?'}: {n['headline']}"
            + (f" | {n['summary']}" if n.get("summary") else "")
            for n in news
        )
        user = "FACTS\n" + json.dumps(facts, indent=1) + "\n\nNEWS\n" + fence("news", headlines or "(none)")
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        try:
            res = await asyncio.wait_for(
                self.llm.chat(messages, temperature=0.1, max_tokens=1500, label=f"trader:{view.symbol}"),
                timeout=self.timeout,
            )
            choice = LLMChoice.model_validate(extract_json(res.content or ""))
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"[:200]
            return _fallback(base, f"the LLM reply was rejected ({type(e).__name__})", flags)

        names = {c.strategy for c in candidates}
        if choice.action == "enter_long" and choice.strategy not in names:
            return _fallback(
                base,
                f"the LLM picked {choice.strategy!r}, which is not a qualified, signalling strategy",
                flags,
            )
        stated = choice.model_dump(exclude={"thesis", "strategy", "action"})
        bad = unsupported_numbers(choice.thesis, facts, stated)
        thesis = choice.thesis.strip()
        if bad:
            flags.append(
                f"The LLM thesis used numbers not in its facts ({', '.join(bad[:5])}); it was discarded."
            )
            thesis = None
        conf = round(min(0.95, max(0.05, choice.confidence)), 2)
        d = dict(symbol=view.symbol, ts=view.ts, source="llm", flags=flags, confidence=conf, thesis=thesis)
        if choice.action == "stay_flat":
            why = thesis or "no usable reason given"
            return Decision(**d, action="stay_flat", strategy=base.strategy, veto=True,
                            reason=f"The LLM vetoed the {base.strategy} entry: {why}")  # fmt: skip
        return Decision(
            **d,
            action="enter_long",
            strategy=choice.strategy,
            expected_move_pct=round(choice.expected_move_pct or 0.0, 2),
            horizon_bars=choice.horizon_bars,
            reason=(
                f"The LLM chose {choice.strategy} among {len(candidates)} qualified, signalling strategies. "
                f"{('Thesis: ' + thesis) if thesis else base.reason}"
            ),
        )

    # -------------------------------------------------------------- narrate
    async def narrate(self, template: str, facts: dict) -> tuple[str, bool, list[str]]:
        """Plain-language rewrite of a journal entry, accepted only if every number checks out."""
        if not self.narrate_entries or not self._take_call():
            return template, False, []
        try:
            res = await asyncio.wait_for(
                self.llm.chat(
                    [{"role": "system", "content": NARRATE_SYSTEM}, {"role": "user", "content": template}],
                    temperature=0.2, max_tokens=1000, label="trader:narrate",
                ),
                timeout=self.timeout,
            )  # fmt: skip
        except Exception:
            return template, False, []
        return accept_rewrite(template, res.content, facts)


def _fallback(base: Decision, why: str, flags: list[str]) -> Decision:
    return base.model_copy(
        update={"degraded": True, "flags": flags, "reason": f"{base.reason} (Rule brain decided: {why}.)"}
    )


def _facts(view: MarketView, candidates) -> dict:
    r = view.ranking
    return {
        "symbol": view.symbol,
        "asset": view.kind,
        "price": round(view.price, 6),
        "atr_14": round(view.atr, 6),
        "atr_pct_of_price": round(100 * view.atr / view.price, 2) if view.price else None,
        "regime": r.regime if r else None,
        "buy_and_hold_sharpe_trailing": round(r.benchmark_sharpe, 2) if r else None,
        "buy_and_hold_return_pct_trailing": round(100 * r.benchmark_return, 2) if r else None,
        "candidates": [
            {
                "strategy": c.strategy,
                "what_it_does": DESCRIPTIONS.get(c.strategy, ""),
                "sharpe_trailing": round(c.sharpe, 2),
                "return_pct_trailing": round(100 * c.total_return, 2),
                "max_drawdown_pct_trailing": round(100 * c.max_drawdown, 2),
                "trades_trailing": c.trades,
            }
            for c in candidates
        ],  # fmt: skip
    }
