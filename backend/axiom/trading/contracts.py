"""Trade Contracts: before every entry the agent pre-commits a falsifiable thesis, and each one is graded.

A contract states the probability the trade ends in profit (`confidence`), the expected move, a horizon, and
machine-checkable invalidation conditions:

  price_below    the stop-loss (enforced by the broker and the engine)
  signal_flip    the chosen strategy's signal turns off (enforced by the brain)
  time_stop      the stated horizon passed without the exit firing (enforced here)
  regime_change  the market regime turned to a downtrend after a non-downtrend entry (enforced here)

The last two apply only when the brain stated a horizon (the LLM brain does). A rule-brain contract keeps the
strategy's own exits, so the Time Machine trades exactly what the tournament evaluated.

At close a contract is graded: outcome (1 if it made money after fees), whether the expected move was
reached, and its Brier score `(confidence - outcome)^2`. The calibration summary feeds the autonomy ladder.

In SHADOW mode nothing trades, so the engine opens *virtual* contracts on would-be entries; they are graded
from the bars themselves (stop on the bar's low, costs charged) so the agent can earn its first promotion.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from .models import AccountState, OrderIntent, RiskVerdict
from .symbols import parse

if TYPE_CHECKING:
    from .brain import Decision
    from .engine import Engine

BUCKETS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)]


def contract_id(session: str, symbol: str, ts: float, shadow: bool) -> str:
    """Deterministic, so a replay reproduces its journal hashes exactly."""
    raw = f"{session}|{symbol}|{ts:.3f}|{'shadow' if shadow else 'real'}"
    return "c-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def brier(confidence: float | None, outcome: int) -> float:
    p = 0.5 if confidence is None else float(confidence)
    return round((p - outcome) ** 2, 4)


def grade_letter(outcome: int, target_hit: bool, planned_exit: bool) -> str:
    """A: profit and the expected move reached. B: profit short of it. C: a loss closed by one of the
    contract's own conditions (the plan worked, the thesis did not). D: a loss closed any other way."""
    if outcome:
        return "A" if target_hit else "B"
    return "C" if planned_exit else "D"


PLANNED = ("stop", "signal", "time stop", "regime")


class ContractBook:
    # ------------------------------------------------------------- create
    def _new(self, eng: Engine, intent: OrderIntent, v: RiskVerdict, dec: Decision, now: float, *,
             shadow: bool) -> dict:  # fmt: skip
        horizon = int(dec.horizon_bars) if dec.horizon_bars else None
        r = eng.rankings.get(intent.symbol)
        trend = (r.regime.get("trend") if r else None) or "unknown"
        c = {
            "id": contract_id(eng.cfg.session, intent.symbol, now, shadow), "session": eng.cfg.session, "symbol": intent.symbol, "created_at": now,
            "status": "open", "shadow": shadow, "source": intent.source, "strategy": intent.strategy,
            "confidence": intent.confidence, "thesis": dec.thesis or dec.reason,
            "expected_move_pct": dec.expected_move_pct, "horizon_bars": horizon,
            "deadline_ts": None if horizon is None else now + horizon * eng.cfg.bar_seconds, "entry_price": round(v.price, 6),
            "stop_price": intent.stop_price, "qty": v.qty, "regime_at_entry": trend,
            "invalidation": [
                {"type": "price_below", "level": intent.stop_price},
                {"type": "signal_flip", "strategy": intent.strategy},
            ] + ([{"type": "time_stop", "after_bars": horizon},
                  {"type": "regime_change", "from": trend, "to": "downtrend"}] if horizon else []),
            "result": None,
        }  # fmt: skip
        eng.ledger.save_contract(c)
        return c

    def open(self, eng: Engine, intent: OrderIntent, v: RiskVerdict, dec: Decision, now: float) -> dict:
        return self._new(eng, intent, v, dec, now, shadow=False)

    def open_shadow(
        self, eng: Engine, intent: OrderIntent, v: RiskVerdict, dec: Decision, now: float
    ) -> dict | None:
        """A would-be entry in SHADOW mode. One virtual contract per symbol at a time."""
        if any(c["symbol"] == intent.symbol and c["shadow"] for c in eng.ledger.contracts(status="open")):
            return None
        c = self._new(eng, intent, v, dec, now, shadow=True)
        eng.journal(
            "shadow",
            f"Shadow mode: would have bought {intent.symbol} at about {v.price:,.2f} with a stop at "
            f"{intent.stop_price:,.2f} ({intent.strategy}). Nothing was traded; a virtual contract tracks it.",
            ts=now, symbol=intent.symbol,
            facts={"contract_id": c["id"], "price": round(v.price, 6), "stop_price": intent.stop_price,
                   "strategy": intent.strategy, "confidence": intent.confidence},
        )  # fmt: skip
        return c

    def cancel(self, eng: Engine, contract: dict, why: str, now: float) -> None:
        contract = {**contract, "status": "cancelled", "result": {"ts": now, "reason": why}}
        eng.ledger.save_contract(contract)

    # -------------------------------------------------------------- grade
    def _get(self, eng: Engine, contract_id: str) -> dict | None:
        return next((c for c in eng.ledger.contracts() if c["id"] == contract_id), None)

    def close(self, eng: Engine, contract_id: str, facts: dict, now: float) -> dict | None:
        c = self._get(eng, contract_id)
        if c is None or c["status"] != "open":
            return None
        return self._grade(eng, c, facts, now)

    def _grade(self, eng: Engine, c: dict, facts: dict, now: float) -> dict:
        pl, ret = facts.get("realized_pl"), facts.get("return_pct")
        outcome = int((pl if pl is not None else (ret or 0.0)) > 0)
        exp = c.get("expected_move_pct")
        target_hit = bool(outcome and exp is not None and ret is not None and ret >= exp)
        reason = str(facts.get("reason") or "")
        planned = any(p in reason.lower() for p in PLANNED)
        result = {
            "ts": now, "exit_price": facts.get("exit_price"), "return_pct": ret, "realized_pl": pl,
            "reason": reason, "outcome": outcome, "target_hit": target_hit,
            "brier": brier(c.get("confidence"), outcome), "grade": grade_letter(outcome, target_hit, planned),
            "held_bars": round((now - c["created_at"]) / eng.cfg.bar_seconds, 1),
            "benchmark_return_pct": facts.get("benchmark_return_pct"),
        }  # fmt: skip
        c = {**c, "status": "graded", "result": result}
        eng.ledger.save_contract(c)
        eng.journal("contract", _grade_text(c, result), ts=now, symbol=c["symbol"],
                    facts={"contract_id": c["id"], "shadow": c["shadow"], **result})  # fmt: skip
        if eng.autonomy is not None:
            eng.autonomy.on_graded(eng, now)
        return c

    # -------------------------------------------------------- invalidation
    async def check_invalidations(
        self, eng: Engine, acct: AccountState, now: float, index: dict[str, int]
    ) -> None:
        for c in eng.ledger.contracts(status="open"):
            sym = c["symbol"]
            if sym not in index or sym not in eng.books:
                continue
            book, i = eng.books[sym], index[sym]
            if c["shadow"]:
                self._check_shadow(eng, c, book, i, now)
                continue
            meta = eng.st["meta"].get(sym, {})
            if sym not in acct.positions:
                if meta.get("contract_id") != c["id"]:
                    self.cancel(eng, c, "the position is no longer open", now)
                continue
            why = self._breach(eng, c, now)
            if why:
                await eng._exit(sym, why, now)

    def _breach(self, eng: Engine, c: dict, now: float) -> str | None:
        if c.get("deadline_ts") is None:
            return None
        if now >= c["deadline_ts"] - 1:
            return f"time stop: the contract's horizon of {c['horizon_bars']} bars passed"
        r = eng.rankings.get(c["symbol"])
        trend = r.regime.get("trend") if r else None
        if trend == "downtrend" and c.get("regime_at_entry") != "downtrend":
            return f"regime changed from {c.get('regime_at_entry')} to downtrend"
        return None

    def _check_shadow(self, eng: Engine, c: dict, book, i: int, now: float) -> None:
        if book.ts[i] <= c["created_at"]:
            return
        low, close = float(book.df["low"].iloc[i]), float(book.close[i])
        opn = float(book.df["open"].iloc[i])
        stop, strat = c.get("stop_price"), c.get("strategy")
        exit_px, why = None, None
        if stop is not None and low <= stop:
            exit_px, why = min(opn, stop), f"stop-loss at {stop:,.2f} hit (shadow)"
        elif strat and float(book.signals.get(strat, [1.0] * (i + 1))[i]) == 0.0:
            exit_px, why = close, f"{strat} signal turned off (shadow)"
        else:
            why = self._breach(eng, c, now)
            exit_px = close if why else None
        if exit_px is None:
            return
        cost = eng.cfg.cost_bps.get(parse(c["symbol"]).kind, 10.0) / 1e4
        ret = (exit_px * (1 - cost)) / (c["entry_price"] * (1 + cost)) - 1
        self._grade(eng, c, {"exit_price": round(exit_px, 6), "return_pct": round(100 * ret, 2),
                             "realized_pl": None, "reason": why}, now)  # fmt: skip


def _grade_text(c: dict, r: dict) -> str:
    conf = c.get("confidence")
    stated = f"stated {conf:.0%} chance of profit" if conf is not None else "no stated confidence"
    ret = r.get("return_pct")
    exp = c.get("expected_move_pct")
    move = f"{ret:+.2f}%" if ret is not None else "n/a"
    target = f" against an expected {exp:+.2f}%" if exp is not None else ""
    return (
        f"Contract graded {r['grade']} for {c['symbol']}{' (shadow)' if c['shadow'] else ''}: {stated}, "
        f"result {move}{target}, {'profit' if r['outcome'] else 'no profit'}. Brier score {r['brier']:.2f} "
        f"(0 is perfect, 0.25 is a coin flip). Closed because {r['reason'].rstrip('.')}."
    )


# ------------------------------------------------------------ outcome memory
def outcomes_by_regime(contracts: list[dict]) -> list[dict[str, Any]]:
    """How graded trades ended, grouped by the market regime at entry and the strategy: the desk's long-term
    memory. Shadow contracts (entries the agent was not allowed to take) count, and are reported apart."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for c in contracts:
        if c["status"] != "graded" or not c.get("result"):
            continue
        key = (c.get("regime_at_entry") or "unknown", c.get("strategy") or "unknown")
        g = groups.setdefault(key, {"n": 0, "wins": 0, "ret": 0.0, "stops": 0, "shadow": 0, "last_ts": 0.0})
        r = c["result"]
        g["n"] += 1
        g["wins"] += int(r["outcome"])
        g["ret"] += float(r.get("return_pct") or 0.0)
        g["stops"] += int(str(r.get("reason") or "").startswith("stop"))
        g["shadow"] += int(bool(c.get("shadow")))
        g["last_ts"] = max(g["last_ts"], float(r.get("ts") or 0.0))
    return [
        {
            "regime": regime, "strategy": strategy, "trades": g["n"], "wins": g["wins"],
            "win_rate": round(g["wins"] / g["n"], 3), "avg_return_pct": round(g["ret"] / g["n"], 2),
            "stop_outs": g["stops"], "shadow": g["shadow"], "last_ts": g["last_ts"],
        }
        for (regime, strategy), g in sorted(groups.items(), key=lambda kv: (-kv[1]["n"], kv[0]))
    ]  # fmt: skip


def outcomes_text(contracts: list[dict], *, limit: int = 6) -> str:
    """The same memory as a few plain lines, small enough to hand to the Synthesizer and the Critic."""
    rows = outcomes_by_regime(contracts)[:limit]
    return "\n".join(
        f"- {r['strategy']} (market regime at entry: {r['regime']}): {r['trades']} graded paper trade(s), {r['wins']} "
        f"profitable, average result {r['avg_return_pct']:+.2f}%, {r['stop_outs']} ended at the stop-loss."
        for r in rows
    )


# ---------------------------------------------------------------- calibration
def calibration(contracts: list[dict], *, last: int | None = None) -> dict[str, Any]:
    """Brier score, win rate and reliability buckets over graded contracts (newest `last` if given)."""
    graded = sorted((c for c in contracts if c["status"] == "graded"), key=lambda c: c["result"]["ts"])
    if last is not None:
        graded = graded[-last:]
    n = len(graded)
    if not n:
        return {"n": 0, "brier": None, "win_rate": None, "mean_confidence": None, "buckets": [],
                "grades": {}, "by_source": {}, "shadow": 0, "net_return_pct": 0.0}  # fmt: skip
    confs = [0.5 if c.get("confidence") is None else float(c["confidence"]) for c in graded]
    outs = [c["result"]["outcome"] for c in graded]
    buckets = []
    for lo, hi in BUCKETS:
        idx = [k for k, p in enumerate(confs) if lo <= p < hi]
        if idx:
            buckets.append({
                "lo": lo, "hi": min(hi, 1.0), "n": len(idx),
                "mean_confidence": round(sum(confs[k] for k in idx) / len(idx), 3),
                "win_rate": round(sum(outs[k] for k in idx) / len(idx), 3),
            })  # fmt: skip
    grades: dict[str, int] = {}
    by_source: dict[str, dict] = {}
    for c in graded:
        g = c["result"]["grade"]
        grades[g] = grades.get(g, 0) + 1
        s = by_source.setdefault(c.get("source") or "rule", {"n": 0, "brier_sum": 0.0, "wins": 0})
        s["n"] += 1
        s["brier_sum"] += c["result"]["brier"]
        s["wins"] += c["result"]["outcome"]
    return {
        "n": n,
        "brier": round(sum(c["result"]["brier"] for c in graded) / n, 4),
        "win_rate": round(sum(outs) / n, 3),
        "mean_confidence": round(sum(confs) / n, 3),
        "buckets": buckets,
        "grades": grades,
        "by_source": {
            k: {
                "n": v["n"],
                "brier": round(v["brier_sum"] / v["n"], 4),
                "win_rate": round(v["wins"] / v["n"], 3),
            }
            for k, v in by_source.items()
        },  # fmt: skip
        "shadow": sum(1 for c in graded if c["shadow"]),
        "net_return_pct": round(sum(c["result"].get("return_pct") or 0.0 for c in graded), 2),
    }
