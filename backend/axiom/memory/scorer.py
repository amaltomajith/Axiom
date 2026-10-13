"""Close the loop: score each thesis against what actually happened, then aggregate honestly.

A thesis made at `issue_date` with horizon H (trading days) is scorable once H bars exist after the
issue date. Scoring never edits the thesis; it writes a separate outcome row.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from axiom.data import market

from .store import Store

log = logging.getLogger(__name__)
BENCHMARK = "SPY"
MIN_SAMPLE = 30  # below this, hit rates are anecdotes and the UI says so

_DIRECTION = {"STRONG_BUY": 1, "BUY": 1, "SELL": -1, "STRONG_SELL": -1}


def direction_of(rating: str) -> int:
    return _DIRECTION.get(rating, 0)


def _last_idx_on_or_before(index: pd.DatetimeIndex, day: pd.Timestamp) -> int:
    return int(index.searchsorted(day, side="right")) - 1


async def score_thesis(thesis: dict, today: date | None = None) -> dict | None:
    """Return an outcome dict, or None if not yet due / not scorable."""
    today = today or datetime.now(UTC).date()
    issue = pd.Timestamp(thesis["issue_date"])
    age = (pd.Timestamp(today) - issue).days
    if age < 1:
        return None
    horizon = int(thesis["horizon_days"])
    bars = max(60, min(1500, int(age * 0.75) + horizon + 40))
    df, _ = await market.fetch_ohlcv(thesis["ticker"], bars)
    i0 = _last_idx_on_or_before(df.index, issue)
    if i0 < 0:
        return None
    ih = i0 + horizon
    if ih >= len(df):
        return None  # horizon not reached yet

    entry = float(thesis["price_at_issue"])
    exit_price = float(df["close"].iloc[ih])
    horizon_date = df.index[ih]
    ret = exit_price / entry - 1

    bench_ret = None
    try:
        spy, _ = await market.fetch_ohlcv(BENCHMARK, bars)
        b0, bh = _last_idx_on_or_before(spy.index, issue), _last_idx_on_or_before(spy.index, horizon_date)
        if b0 >= 0 and bh > b0:
            bench_ret = float(spy["close"].iloc[bh] / spy["close"].iloc[b0] - 1)
    except market.DataError:
        log.warning("benchmark unavailable while scoring %s", thesis["id"])
    excess = None if bench_ret is None else ret - bench_ret

    d = direction_of(thesis["rating"])
    direction_hit = None if d == 0 else int((ret > 0) == (d > 0) and ret != 0)
    beat = None if d == 0 or excess is None else int((excess > 0) == (d > 0) and excess != 0)
    stop_hit = None
    if thesis.get("stop_price") and d > 0:
        stop_hit = int(bool((df["low"].iloc[i0 + 1 : ih + 1] <= thesis["stop_price"]).any()))
    brier = None
    if d != 0:
        p_up = min(0.99, max(0.01, 0.5 + d * 0.5 * float(thesis["conviction"])))
        brier = (p_up - (1.0 if ret > 0 else 0.0)) ** 2

    agents = {}
    for f in thesis.get("findings", []):
        stance = f.get("stance")
        hit = (
            None
            if stance not in ("bullish", "bearish")
            else int((ret > 0) == (stance == "bullish") and ret != 0)
        )
        agents[f.get("agent", "?")] = {"stance": stance, "hit": hit}

    return {
        "horizon_date": horizon_date.strftime("%Y-%m-%d"),
        "price_at_horizon": round(exit_price, 4),
        "ret_pct": round(ret * 100, 3),
        "benchmark_ret_pct": None if bench_ret is None else round(bench_ret * 100, 3),
        "excess_ret_pct": None if excess is None else round(excess * 100, 3),
        "direction_hit": direction_hit,
        "beat_benchmark": beat,
        "stop_hit": stop_hit,
        "brier": None if brier is None else round(brier, 4),
        "detail": {"agents": agents},
    }


async def score_due(store: Store, today: date | None = None) -> dict[str, int]:
    scored = skipped = failed = 0
    for t in store.theses(status="pending", limit=500):
        try:
            outcome = await score_thesis(t, today)
        except market.DataError as e:
            failed += 1
            log.warning("could not score %s: %s", t["id"], e)
            continue
        if outcome is None:
            skipped += 1
            continue
        store.save_outcome(t["id"], outcome)
        scored += 1
    return {"scored": scored, "not_yet_due": skipped, "failed": failed}


def _rate(vals: list[int | None]) -> tuple[int, float | None]:
    v = [x for x in vals if x is not None]
    return len(v), (round(sum(v) / len(v), 3) if v else None)


def scorecard(store: Store) -> dict[str, Any]:
    rows = store.scored()
    pending = len(store.theses(status="pending", limit=10_000))
    directional = [r for r in rows if r["direction_hit"] is not None]
    n_dir, hit_rate = _rate([r["direction_hit"] for r in directional])
    _, beat_rate = _rate([r["beat_benchmark"] for r in directional])
    _, stop_rate = _rate([r["stop_hit"] for r in directional])
    base_up = round(sum(1 for r in rows if r["ret_pct"] > 0) / len(rows), 3) if rows else None
    briers = [r["brier"] for r in directional if r["brier"] is not None]
    mean_brier = round(sum(briers) / len(briers), 4) if briers else None
    excess = [r["excess_ret_pct"] for r in directional if r["excess_ret_pct"] is not None]
    # signed so that a SELL that falls counts as a gain for the call
    signed_excess = [
        e * direction_of(r["rating"])
        for r, e in zip(directional, [r["excess_ret_pct"] or 0 for r in directional], strict=True)
    ]

    buckets = {"low (<0.4)": [], "mid (0.4-0.7)": [], "high (>=0.7)": []}
    for r in directional:
        c = r["conviction"]
        buckets["low (<0.4)" if c < 0.4 else "mid (0.4-0.7)" if c < 0.7 else "high (>=0.7)"].append(
            r["direction_hit"]
        )
    by_conv = {k: dict(zip(("n", "hit_rate"), _rate(v), strict=True)) for k, v in buckets.items()}

    agents: dict[str, list[int | None]] = {}
    for r in rows:
        for name, a in r["detail"].get("agents", {}).items():
            agents.setdefault(name, []).append(a["hit"])
    by_agent = {k: dict(zip(("n", "hit_rate"), _rate(v), strict=True)) for k, v in agents.items()}

    by_rating: dict[str, int] = {}
    for r in rows:
        by_rating[r["rating"]] = by_rating.get(r["rating"], 0) + 1

    return {
        "n_scored": len(rows),
        "n_pending": pending,
        "n_directional": n_dir,
        "sufficient_sample": n_dir >= MIN_SAMPLE,
        "sample_note": (
            f"{n_dir} directional calls scored; need >= {MIN_SAMPLE} before hit rates mean anything."
            if n_dir < MIN_SAMPLE
            else "Sample large enough for rough conclusions; still not proof of skill."
        ),
        "direction_hit_rate": hit_rate,
        "baseline_up_rate": base_up,  # what an 'always bullish' caller would have scored
        "beat_benchmark_rate": beat_rate,
        "mean_excess_return_pct": round(sum(signed_excess) / len(signed_excess), 3)
        if signed_excess
        else None,
        "mean_brier": mean_brier,
        "brier_skill_vs_coinflip": None if mean_brier is None else round(1 - mean_brier / 0.25, 3),
        "stop_hit_rate": stop_rate,
        "by_conviction": by_conv,
        "by_agent": by_agent,
        "by_rating": by_rating,
        "unused_excess_sample": len(excess),
    }


def recall(store: Store, ticker: str, n: int = 3) -> str:
    """Prior theses on this ticker, formatted for an agent prompt ('' if none)."""
    lines = []
    for t in store.theses(ticker=ticker, limit=n):
        head = f"- {t['issue_date']} {t['rating']} (conviction {t['conviction']:.2f}) at ${t['price_at_issue']:.2f}"
        if t["status"] == "scored":
            o = next((r for r in store.scored(ticker) if r["id"] == t["id"]), None)
            if o:
                ex = "" if o["excess_ret_pct"] is None else f", {o['excess_ret_pct']:+.1f}% vs {BENCHMARK}"
                verdict = {1: "call was right", 0: "call was wrong", None: "no directional call"}[
                    o["direction_hit"]
                ]
                lines.append(f"{head} -> {o['ret_pct']:+.1f}% over {t['horizon_days']}d{ex}; {verdict}.")
                continue
        lines.append(f"{head} -> still pending (horizon {t['horizon_days']} trading days).")
    return "\n".join(lines)
