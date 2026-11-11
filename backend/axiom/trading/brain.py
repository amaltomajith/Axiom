"""Brains decide what to do with one symbol at one bar. They never size, never place orders.

`RuleBrain` trades the tournament's best qualified strategy. `LLMBrain` (`llm_brain.py`) may only choose
among qualified strategies or stay flat, and falls back to `RuleBrain` on any failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel

from .models import AssetKind, Position
from .tournament import Ranking

DecisionAction = Literal["enter_long", "exit", "hold", "stay_flat"]


class Decision(BaseModel):
    symbol: str
    ts: float
    action: DecisionAction
    strategy: str | None = None
    reason: str = ""
    confidence: float | None = None  # stated probability the trade ends in profit
    source: Literal["rule", "llm"] = "rule"
    degraded: bool = False  # the LLM failed and the rule brain decided instead
    thesis: str | None = None
    expected_move_pct: float | None = None
    horizon_bars: int | None = None
    veto: bool = False  # the LLM declined an entry the rule brain would have taken
    flags: list[str] = []  # things the journal must record: redacted headlines, discarded thesis numbers


@dataclass
class MarketView:
    """Everything a brain may see at bar t. Built from data <= t only."""

    symbol: str
    kind: AssetKind
    ts: float
    price: float
    atr: float
    ranking: Ranking | None
    signals_now: dict[str, float]
    signals_prev: dict[str, float]
    position: Position | None = None
    held_strategy: str | None = None
    news: list[dict] = field(default_factory=list)


class Brain(Protocol):
    name: str

    async def decide(self, view: MarketView) -> Decision: ...


class RuleBrain:
    name = "rule"

    async def decide(self, view: MarketView) -> Decision:
        return rule_decision(view)


def rule_decision(view: MarketView) -> Decision:
    d = dict(symbol=view.symbol, ts=view.ts, source="rule")
    if view.position is not None and view.position.qty > 0:
        strat = view.held_strategy
        if strat and view.signals_now.get(strat, 0.0) == 0.0:
            return Decision(**d, action="exit", strategy=strat, reason=f"{strat} signal turned off.")
        return Decision(**d, action="hold", strategy=strat, reason=f"{strat or 'position'} signal still on.")
    best = view.ranking.best if view.ranking else None
    if best is None:
        why = "No strategy cleared the tournament gate on the trailing window; staying in cash."
        return Decision(**d, action="stay_flat", reason=why)
    if view.signals_now.get(best.strategy, 0.0) != 1.0:
        return Decision(**d, action="stay_flat", strategy=best.strategy,
                        reason=f"{best.strategy} qualified but is not signalling an entry.")  # fmt: skip
    bench = view.ranking.benchmark_sharpe if view.ranking else 0.0
    conf = round(min(0.8, 0.5 + 0.05 * max(0.0, best.sharpe)), 2)
    return Decision(
        **d,
        action="enter_long",
        strategy=best.strategy,
        confidence=conf,
        reason=(
            f"{best.strategy} ranked first with Sharpe {best.sharpe:.2f} on the trailing window "
            f"(buy-and-hold {bench:.2f}) and is signalling long."
        ),
        expected_move_pct=round(100 * 2 * view.atr / view.price, 2) if view.price else None,
    )
