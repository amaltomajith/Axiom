"""Deterministic guardrails applied AFTER the LLM writes a memo.

Prompts are requests; this module is enforcement. It caps what the rating and conviction may be given
the actual evidence, and records every adjustment so the UI can show why a call was softened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .faithfulness import Evidence
from .schemas import RATING_ORDER, Finding, Memo, Rating

STRONG: set[Rating] = {"STRONG_BUY", "STRONG_SELL"}


@dataclass
class EvidenceSummary:
    backtest_verdicts: list[str]
    any_edge: bool
    high_vol: bool


def summarize_evidence(evidence: Evidence) -> EvidenceSummary:
    verdicts, high_vol = [], False
    for item in evidence.items.values():
        try:
            body = json.loads(item["text"])
        except json.JSONDecodeError:
            continue
        if item["tool"] in ("run_backtest", "run_walk_forward_model") and "verdict" in body:
            verdicts.append(body["verdict"])
        if item["tool"] == "get_regime" and body.get("volatility") == "high":
            high_vol = True
    return EvidenceSummary(verdicts, "edge_detected" in verdicts, high_vol)


def technical_expected_stance(evidence: Evidence) -> tuple[str, str]:
    """The stance the technical evidence mandates, as a published rubric (not model judgement):

    * insufficient_data: every backtest verdict was 'insufficient_data' (or none ran);
    * bullish: at least one backtest/walk-forward verdict is 'edge_detected' and the trend is not down;
    * bearish: the trend is down and no verdict shows an edge;
    * neutral: everything else (mixed or unproven evidence).
    """
    ev = summarize_evidence(evidence)
    trend = None
    for item in evidence.items.values():
        if item["tool"] == "get_regime":
            try:
                trend = json.loads(item["text"]).get("trend")
            except json.JSONDecodeError:
                pass
    if not ev.backtest_verdicts or all(v == "insufficient_data" for v in ev.backtest_verdicts):
        return "insufficient_data", "no backtest produced a usable verdict"
    if ev.any_edge and trend != "downtrend":
        return "bullish", f"a backtest verdict is edge_detected and the trend is {trend}"
    if trend == "downtrend" and not ev.any_edge:
        return "bearish", "the trend is a downtrend and no backtest shows an edge"
    return (
        "neutral",
        f"verdicts {sorted(set(ev.backtest_verdicts))} with trend {trend} do not justify a directional stance",
    )


def _direction(r: Rating) -> int:
    return 1 if r in ("BUY", "STRONG_BUY") else -1 if r in ("SELL", "STRONG_SELL") else 0


def _demote(r: Rating) -> Rating:
    if r == "STRONG_BUY":
        return "BUY"
    if r == "STRONG_SELL":
        return "SELL"
    return r


def apply_policy(memo: Memo, findings: list[Finding], evidence: Evidence) -> tuple[Memo, list[str]]:
    """Return (possibly softened memo, human-readable adjustments)."""
    notes: list[str] = []
    m = memo.model_copy(deep=True)
    ev = summarize_evidence(evidence)
    stances = [f.stance for f in findings]
    usable = [s for s in stances if s != "insufficient_data"]

    if m.rating != "NO_CALL" and not usable:
        m.rating, m.conviction = "NO_CALL", 0.0
        notes.append("Downgraded to NO_CALL: no analyst had sufficient data.")

    direction = _direction(m.rating)
    if direction and len(set(usable)) > 1 and {"bullish", "bearish"} <= set(usable):
        m.rating, m.conviction = "HOLD", min(m.conviction, 0.4)
        notes.append("Downgraded to HOLD: technical and fundamental analysts disagree.")
    elif direction and len(usable) == 1 and len(stances) > 1:
        m.conviction = min(m.conviction, 0.5)
        notes.append("Conviction capped at 0.5: only one analyst had sufficient data.")

    if direction and usable:
        agree = [f for f in findings if f.stance == ("bullish" if direction > 0 else "bearish")]
        if not agree:
            m.rating, m.conviction = "HOLD", min(m.conviction, 0.4)
            notes.append("Downgraded to HOLD: no analyst supports the proposed direction.")

    if m.rating in STRONG:
        weak = [f for f in findings if f.confidence <= 0.7]
        if weak or not ev.any_edge:
            m.rating = _demote(m.rating)
            why = (
                "no backtest showed a statistically supported edge"
                if not ev.any_edge
                else "analyst confidence <= 0.7"
            )
            notes.append(f"STRONG rating reduced one notch: {why}.")

    if _direction(m.rating) and ev.backtest_verdicts and not ev.any_edge and m.conviction > 0.6:
        m.conviction = 0.6
        notes.append("Conviction capped at 0.6: backtests found no edge over buy-and-hold.")

    if _direction(m.rating) and ev.high_vol and m.conviction > 0.7:
        m.conviction = 0.7
        notes.append("Conviction capped at 0.7: volatility regime is high.")

    # Thin evidence lowers confidence in ANY rating, including HOLD: an analyst that could not assess the
    # stock, or backtests that all lack data, must not coexist with a confident memo.
    if m.conviction > 0.5 and (
        "insufficient_data" in stances
        or (ev.backtest_verdicts and all(v == "insufficient_data" for v in ev.backtest_verdicts))
    ):
        m.conviction = 0.5
        notes.append("Conviction capped at 0.5: evidence is insufficient for at least one analyst.")

    if m.rating == "NO_CALL":
        m.conviction = min(m.conviction, 0.3)
    return m, notes


def rating_index(r: Rating) -> int | None:
    return RATING_ORDER.index(r) if r in RATING_ORDER else None
