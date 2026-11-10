"""Deterministic SYNTHETIC operational data for development and tests (no real research, no LLM calls).

Uses Axiom's own schema (Store) and the exact trace-event shapes the agents emit, so the warehouse SQL
is exercised on realistic structure. Tickers are real so the price step has something to fetch; the
ratings, outcomes and traces are invented. Never present numbers from this data as Axiom's results.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from axiom.db import upsert_sql
from axiom.memory.store import Store

TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM"]
RATINGS = ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]
RATING_WEIGHTS = [0.15, 0.3, 0.3, 0.15, 0.1]
AGENT_TOOLS = {
    "Technical Analyst": ["get_price_summary", "get_indicators", "get_regime", "run_backtest"],
    "Fundamental Auditor": ["fetch_sec_filing_summary", "get_company_news_sentiment", "get_peer_comparison"],
    "Risk Guard": ["get_risk_metrics", "get_forecast_cone", "size_position"],
}
BASE_TS = 1_785_542_400.0  # 2026-08-01T00:00:00Z
DAY = 86_400.0


def _ev(seq: int, ts: float, run_id: str, type_: str, agent: str, **data) -> dict:
    return {"seq": seq, "ts": round(ts, 3), "run_id": run_id, "type": type_, "agent": agent, "data": data}


def _events(rng: random.Random, run_id: str, ticker: str, t0: float) -> list[dict]:
    evs, seq, ts = [], 0, t0

    def add(type_: str, agent: str, dt: float = 0.05, **data) -> None:
        nonlocal seq, ts
        seq, ts = seq + 1, ts + dt
        evs.append(_ev(seq, ts, run_id, type_, agent, **data))

    add("run_start", "system", ticker=ticker, equity=100_000.0, date="synthetic")
    for agent, tools in AGENT_TOOLS.items():
        add("agent_start", agent)
        for tool in rng.sample(tools, k=min(len(tools), rng.randint(2, 3))):
            ms = int(rng.lognormvariate(math.log(180 if "sec" not in tool else 900), 0.6))
            ok = rng.random() > 0.04
            add("llm_call", agent, dt=rng.uniform(0.8, 3.0), label=f"{agent}:step", provider="synthetic",
                model="synthetic-model", prompt_tokens=rng.randint(900, 2600),
                completion_tokens=rng.randint(60, 400), latency_ms=rng.randint(700, 3200), cached=rng.random() < 0.1,
                tool_calls=[tool])  # fmt: skip
            add("tool_call", agent, tool=tool, args={"ticker": ticker})
            add("tool_result", agent, dt=ms / 1000, tool=tool, ok=ok, latency_ms=ms,
                **({"evidence_id": f"E{seq}", "chars": rng.randint(300, 4000), "preview": "synthetic"} if ok
                   else {"preview": "synthetic tool error"}))  # fmt: skip
        add("agent_done", agent, steps=3, tools_called=tools)
    add("llm_call", "Lead Synthesizer", dt=2.0, label="Lead Synthesizer:step1", provider="synthetic",
        model="synthetic-model", prompt_tokens=rng.randint(2500, 5000), completion_tokens=rng.randint(300, 900),
        latency_ms=rng.randint(1500, 5000), cached=False, tool_calls=[])  # fmt: skip
    add("run_end", "system", usage={"calls": 9}, degraded=[])
    return evs


def seed(path: Path, n_runs: int = 80, seed: int = 7) -> dict[str, int]:
    """Write a fresh synthetic database at `path` and return row counts per table."""
    path = Path(path)
    if path.exists():
        path.unlink()
    store = Store(path)
    rng = random.Random(seed)
    with store.db.connect() as c:
        for i in range(n_runs):
            run_id = f"syn{i:05d}"
            ticker = rng.choice(TICKERS)
            created = BASE_TS + i * (90 * DAY / n_runs) + rng.uniform(0, 3600)
            rating = rng.choices(RATINGS, RATING_WEIGHTS)[0]
            conviction = round(rng.uniform(0.2, 0.9), 2)
            horizon = rng.choice([5, 20, 60])
            price = round(rng.uniform(50, 500), 2)
            memo = {"rating": rating, "conviction": conviction, "synthetic": True}
            findings = [
                {"agent": a, "stance": rng.choice(["bullish", "bearish", "neutral"])} for a in AGENT_TOOLS
            ]
            result = {
                "run_id": run_id,
                "ticker": ticker,
                "memo": memo,
                "findings": findings,
                "synthetic": True,
            }
            c.execute(
                upsert_sql(
                    "runs", ["run_id", "ticker", "created_at", "result_json", "events_json"], "run_id"
                ),
                (
                    run_id,
                    ticker,
                    created,
                    json.dumps(result),
                    json.dumps(_events(rng, run_id, ticker, created)),
                ),
            )
            tid = f"th{i:05d}"
            issue = _date(created)
            c.execute(
                "INSERT INTO theses (id, run_id, ticker, created_at, issue_date, horizon_days, price_at_issue,"
                " rating, conviction, stop_price, memo_json, findings_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, run_id, ticker, created, issue, horizon, price, rating, conviction,
                 round(price * 0.92, 2) if rating in ("BUY", "STRONG_BUY") else None,
                 json.dumps(memo), json.dumps(findings)),
            )  # fmt: skip
            # score theses whose horizon (trading days ~ 1.4 calendar days each) has passed by day 90
            if created + horizon * 1.4 * DAY < BASE_TS + 90 * DAY:
                ret = rng.gauss(0.4, 4.0)
                bench = rng.gauss(0.3, 3.0)
                d = {"STRONG_BUY": 1, "BUY": 1, "SELL": -1, "STRONG_SELL": -1}.get(rating, 0)
                p_up = min(0.99, max(0.01, 0.5 + d * 0.5 * conviction))
                c.execute(
                    "INSERT INTO outcomes (thesis_id, scored_at, horizon_date, price_at_horizon, ret_pct,"
                    " benchmark_ret_pct, excess_ret_pct, direction_hit, beat_benchmark, stop_hit, brier, detail_json)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (tid, created + horizon * 1.4 * DAY + 3600, _date(created + horizon * 1.4 * DAY),
                     round(price * (1 + ret / 100), 4), round(ret, 3), round(bench, 3), round(ret - bench, 3),
                     None if d == 0 else int((ret > 0) == (d > 0)),
                     None if d == 0 else int((ret - bench > 0) == (d > 0)),
                     None, None if d == 0 else round((p_up - (1.0 if ret > 0 else 0.0)) ** 2, 4), "{}"),
                )  # fmt: skip
                c.execute("UPDATE theses SET status='scored' WHERE id=?", (tid,))
            if rating != "HOLD" and conviction >= 0.5:
                decided = created + rng.uniform(60, 7200) if rng.random() < 0.8 else None
                status = "pending" if decided is None else rng.choice(["executed", "rejected"])
                plan = {
                    "id": f"ac{i:05d}",
                    "run_id": run_id,
                    "ticker": ticker,
                    "status": status,
                    "synthetic": True,
                }
                c.execute(
                    "INSERT INTO actions (id, run_id, ticker, created_at, status, plan_json, decided_at, result_json)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (plan["id"], run_id, ticker, created, status, json.dumps(plan), decided, "null"),
                )
                if status == "executed":
                    c.execute(
                        "INSERT INTO action_keys VALUES (?,?,?)",
                        (f"{plan['id']}:notion", plan["id"], decided),
                    )
        for j, t in enumerate(TICKERS[:3]):
            c.execute("INSERT INTO watchlist VALUES (?,?)", (t, BASE_TS + j * DAY))
        for j in range(4):
            c.execute(
                "INSERT INTO paper_trades (id, ticker, side, quantity, entry_price, entry_date, thesis_id,"
                " exit_price, exit_date) VALUES (?,?,?,?,?,?,?,?,?)",
                (f"pt{j:03d}", TICKERS[j], "long", 10.0, 100.0 + j, _date(BASE_TS + j * 5 * DAY), f"th{j:05d}",
                 None if j % 2 else 105.0 + j, None if j % 2 else _date(BASE_TS + (j * 5 + 20) * DAY)),
            )  # fmt: skip
        for h in range(6):  # documentation-range IPs (RFC 5737), never real clients
            c.execute(
                "INSERT INTO usage VALUES (?,?,?)", (f"ip:198.51.100.{h % 3}", f"20260801{h:02d}", h + 1)
            )
        c.execute("INSERT INTO usage VALUES (?,?,?)", ("global", "20260801", 21))
    with store.db.connect() as c:
        return {
            t: int(c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"])
            for t in (
                "runs",
                "theses",
                "outcomes",
                "actions",
                "action_keys",
                "watchlist",
                "paper_trades",
                "usage",
            )
        }


def _date(ts: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")
