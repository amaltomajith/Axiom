"""Risk Guard: position sizing and limit checks computed by tools and code, never by an LLM.

Runs before synthesis (so the memo can cite risk numbers) and again after the policy guard to turn the
*final* rating into a concrete, limit-checked plan.
"""

from __future__ import annotations

import json
from typing import Any

from axiom.quant import risk

from .schemas import PositionPlan, Rating
from .toolbox import ToolRunner

MAX_POSITION_PCT = 0.20
RISK_PER_TRADE = 0.01


def _json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    try:
        return json.loads(text[start:]) if start != -1 else None
    except json.JSONDecodeError:
        return None


async def gather_risk_evidence(tools: ToolRunner, ticker: str, equity: float) -> dict[str, Any]:
    """Call risk tools (traced, citable) and return their parsed payloads."""
    metrics_txt = await tools.run("get_risk_metrics", {"ticker": ticker})
    sizing_txt = await tools.run(
        "size_position",
        {
            "ticker": ticker,
            "equity": equity,
            "risk_per_trade": RISK_PER_TRADE,
            "max_position_pct": MAX_POSITION_PCT,
        },
    )
    return {
        "metrics": _json(metrics_txt),
        "sizing": _json(sizing_txt),
        "metrics_text": metrics_txt,
        "sizing_text": sizing_txt,
    }


def plan_for_rating(
    rating: Rating, sizing: dict[str, Any] | None, equity: float, ticker: str
) -> PositionPlan:
    if rating in ("BUY", "STRONG_BUY"):
        if not sizing or "shares" not in sizing:
            return PositionPlan(action="none", notes=["Sizing unavailable; no position proposed."])
        violations = risk.check_limits({ticker: sizing["notional"]}, equity, MAX_POSITION_PCT, 1.0)
        shares = 0 if violations else sizing["shares"]
        return PositionPlan(
            action="open_long" if shares > 0 else "none",
            shares=shares,
            entry_reference=sizing.get("price"),
            stop_price=sizing.get("stop_price"),
            risk_amount=sizing.get("risk_amount"),
            position_pct=sizing.get("position_pct"),
            violations=violations,
            notes=[
                f"Fixed-fractional sizing: {RISK_PER_TRADE:.0%} of equity at risk to a 2xATR stop, "
                f"capped at {MAX_POSITION_PCT:.0%} of equity ({sizing.get('binding_constraint')} bound).",
                "Paper-trade plan only. Not financial advice.",
            ],
        )
    if rating in ("SELL", "STRONG_SELL"):
        return PositionPlan(
            action="avoid", notes=["Bearish: avoid or exit. Axiom paper trading is long-only."]
        )
    return PositionPlan(action="none", notes=["No position proposed."])
