"""Plain-language journal templates. Every number comes from the facts passed in; nothing is invented."""

from __future__ import annotations

from .brain import Decision
from .models import Order, OrderIntent, RiskVerdict
from .risk import RULE_NAMES
from .strategies import DESCRIPTIONS
from .tournament import Ranking

# Plain names for the strategies. The ids stay in each entry's facts.
LABELS = {
    "sma_cross": "the moving-average trend strategy",
    "macd_trend": "the momentum strategy",
    "rsi_reversion": "the oversold-bounce strategy",
    "donchian_breakout": "the breakout strategy",
    "bollinger_reversion": "the dip-buying strategy",
}


def label(strategy: str | None) -> str:
    if not strategy:
        return "no strategy"
    return LABELS.get(strategy, strategy.replace("_", " "))


def money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def qty(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.6f}".rstrip("0").rstrip(".")


def pct(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:+.{digits}f}%"


def entry(intent: OrderIntent, v: RiskVerdict, dec: Decision, equity: float) -> str:
    who = (
        "The AI"
        if intent.source == "llm"
        else "The trading desk"
        if dec.source == "desk"
        else "A human"
        if intent.source == "human"
        else "The rules"
    )
    desc = DESCRIPTIONS.get(intent.strategy or "", "")
    conf = f" Its stated chance of ending in profit: {intent.confidence:.0%}." if intent.confidence else ""
    plan = ""
    if dec.expected_move_pct is not None and dec.horizon_bars:
        plan = f" The plan: about {pct(dec.expected_move_pct)} within {dec.horizon_bars} bars, or it sells."
    return (
        f"Bought {qty(v.qty)} {intent.symbol} at about {money(v.price)} ({money(v.notional)}). "
        f"{who} chose {label(intent.strategy)}{f' ({desc})' if desc else ''}. Why: {dec.reason} "
        f"The stop-loss sits at {money(intent.stop_price)}; if it is hit the loss is about {money(v.risk_amount)}, "
        f"{v.risk_amount / equity:.2%} of the account. The risk rules set the size, not the AI.{conf}{plan}"
    )


def veto(dec: Decision) -> str:
    return f"Did not buy {dec.symbol}. {dec.reason.rstrip('.')}. The rules alone would have bought."


def reviewed(dec: Decision) -> str:
    """One line for the proposal a human is asked to approve, when the desk reviewed it."""
    d = dec.desk or {}
    size = f" It asked for {dec.size_factor:.0%} of the size the risk rules allow." if dec.size_factor else ""
    return f" The trading desk rated it {d.get('rating')} with conviction {d.get('conviction')}.{size}"


def exit_(o: Order, f: dict) -> str:
    pl = f.get("realized_pl")
    verdict = "a gain" if pl and pl > 0 else "a loss" if pl and pl < 0 else "flat"
    bench = f.get("benchmark_return_pct")
    cf = (
        f" Over the same period the buy-and-hold basket moved {pct(bench)}, so this trade "
        f"{'beat' if (f.get('return_pct') or 0) > bench else 'trailed'} simply holding."
        if bench is not None and f.get("return_pct") is not None
        else ""
    )
    return (
        f"Sold {qty(o.filled_qty)} {o.symbol} at {money(o.filled_avg_price)} because {f['reason'].rstrip('.')}. "
        f"Entry was {money(f.get('entry_price'))}: {pct(f.get('return_pct'))}, {verdict} of {money(abs(pl) if pl is not None else None)} after fees.{cf}"
    )


def blocked(intent: OrderIntent, v: RiskVerdict, *, approved_by_human: bool = False) -> str:
    rule = v.blocked_by or "?"
    name = RULE_NAMES.get(rule, rule)
    lead = "A human approved a" if approved_by_human else "Wanted to buy"
    what = f"{lead} {intent.symbol}{' entry' if approved_by_human else ''} ({label(intent.strategy)})"
    return f"{what}, but the risk rules blocked it. Rule {rule}, {name}: {v.reason.split(': ', 1)[-1]} No order was sent."


def proposal(intent: OrderIntent, v: RiskVerdict) -> str:
    return (
        f"Proposed buying {qty(v.qty)} {intent.symbol} at about {money(v.price)} with a stop at "
        f"{money(intent.stop_price)}, using {label(intent.strategy)}. Waiting for a human to approve it."
    )


def tournament(r: Ranking) -> str:
    best = r.best
    regime = f"{r.regime.get('trend')}, {r.regime.get('volatility')} volatility"
    if best is None:
        return (
            f"Strategy check for {r.symbol}: none did well enough over the past year to be trusted "
            f"(market: {regime}). Simply holding scored {r.benchmark_sharpe:.2f}. Staying in cash until one does."
        )
    rest = ", ".join(f"{s.strategy} {s.sharpe:.2f}" for s in r.standings[1:4])
    return (
        f"Strategy check for {r.symbol}: {label(best.strategy)} now leads, scoring {best.sharpe:.2f} for "
        f"return against risk (simply holding scored {r.benchmark_sharpe:.2f}; others: {rest}). Market: {regime}."
    )


def halt(pl: float, limit: float, closed: int) -> str:
    return (
        f"Daily loss limit hit: equity is {pl:.2%} on the day against a limit of -{limit:.2%}. "
        f"Closed {closed} position(s) and halted new entries until the next UTC day."
    )


def new_day_unhalt(reason: str) -> str:
    return f"New trading day. The halt ({reason}) is lifted and the loss budget resets."


def kill(reason: str, closed: int) -> str:
    return f"Kill switch: {reason}. Cancelled open orders and closed {closed} position(s). No new trades until resumed."


def resume(who: str) -> str:
    return f"Kill switch released by {who}. Trading may resume, still under every kernel rule."


def autonomy(old: str, new: str, why: str) -> str:
    up = ["SHADOW", "SUPERVISED", "AUTONOMOUS"]
    word = "Promoted" if up.index(new) > up.index(old) else "Demoted"
    return f"{word} from {old} to {new}: {why}"
