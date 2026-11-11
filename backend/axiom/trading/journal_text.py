"""Plain-language journal templates. Every number comes from the facts passed in; nothing is invented."""

from __future__ import annotations

from .brain import Decision
from .models import Order, OrderIntent, RiskVerdict
from .risk import RULE_NAMES
from .strategies import DESCRIPTIONS
from .tournament import Ranking


def money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def qty(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.6f}".rstrip("0").rstrip(".")


def pct(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:+.{digits}f}%"


def entry(intent: OrderIntent, v: RiskVerdict, dec: Decision, equity: float) -> str:
    who = (
        "The LLM brain"
        if intent.source == "llm"
        else "The trading desk"
        if dec.source == "desk"
        else "A human"
        if intent.source == "human"
        else "The rule brain"
    )
    strat = intent.strategy or "an unnamed strategy"
    desc = DESCRIPTIONS.get(strat, "")
    conf = f" Stated confidence that it ends in profit: {intent.confidence:.0%}." if intent.confidence else ""
    plan = ""
    if dec.expected_move_pct is not None and dec.horizon_bars:
        plan = f" Contract: expects about {pct(dec.expected_move_pct)} within {dec.horizon_bars} bars, or it exits."
    return (
        f"Bought {qty(v.qty)} {intent.symbol} at about {money(v.price)} ({money(v.notional)}). "
        f"{who} picked {strat}{f' ({desc})' if desc else ''}. Why: {dec.reason} "
        f"The stop-loss sits at {money(intent.stop_price)}; if it is hit the loss is about {money(v.risk_amount)}, "
        f"{v.risk_amount / equity:.2%} of equity. The risk kernel sized this trade, not the brain.{conf}{plan}"
    )


def veto(dec: Decision) -> str:
    return f"Did not buy {dec.symbol}. {dec.reason.rstrip('.')}. The rule brain alone would have entered."


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
    what = (
        f"{lead} {intent.symbol}{' entry' if approved_by_human else ''} ({intent.strategy or 'no strategy'})"
    )
    return f"{what}, but the risk kernel blocked it. Rule {rule}, {name}: {v.reason.split(': ', 1)[-1]} No order was sent."


def proposal(intent: OrderIntent, v: RiskVerdict) -> str:
    return (
        f"Proposed buying {qty(v.qty)} {intent.symbol} at about {money(v.price)} with a stop at "
        f"{money(intent.stop_price)} ({intent.strategy}). Supervised mode: waiting for a human to approve."
    )


def tournament(r: Ranking) -> str:
    best = r.best
    regime = f"{r.regime.get('trend')}, {r.regime.get('volatility')} volatility"
    if best is None:
        return (
            f"Tournament for {r.symbol}: no strategy qualified on the trailing window ({regime}). "
            f"Buy-and-hold Sharpe was {r.benchmark_sharpe:.2f}. Staying in cash until one does."
        )
    rest = ", ".join(f"{s.strategy} {s.sharpe:.2f}" for s in r.standings[1:4])
    return (
        f"Tournament for {r.symbol}: {best.strategy} now leads with Sharpe {best.sharpe:.2f} "
        f"(buy-and-hold {r.benchmark_sharpe:.2f}; others: {rest}). Market regime: {regime}."
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
