"""Persistent state: runs, immutable theses, scored outcomes, approvals, watchlist, paper trades.

SQLite by default (zero setup, one file); Postgres when DATABASE_URL is set (see axiom/db.py). The SQL is
portable (`?` placeholders, ON CONFLICT upserts), so there is one implementation for both.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from axiom.config import BACKEND_DIR, get_settings
from axiom.db import Db, upsert_sql

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, created_at REAL NOT NULL,
  result_json TEXT NOT NULL, events_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS theses (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL, created_at REAL NOT NULL,
  issue_date TEXT NOT NULL, horizon_days INTEGER NOT NULL, price_at_issue REAL NOT NULL,
  rating TEXT NOT NULL, conviction REAL NOT NULL, stop_price REAL,
  memo_json TEXT NOT NULL, findings_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
CREATE INDEX IF NOT EXISTS theses_ticker ON theses (ticker, created_at DESC);
CREATE TABLE IF NOT EXISTS outcomes (
  thesis_id TEXT PRIMARY KEY, scored_at REAL NOT NULL, horizon_date TEXT NOT NULL,
  price_at_horizon REAL NOT NULL, ret_pct REAL NOT NULL, benchmark_ret_pct REAL,
  excess_ret_pct REAL, direction_hit INTEGER, beat_benchmark INTEGER, stop_hit INTEGER,
  brier REAL, detail_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS actions (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL, created_at REAL NOT NULL,
  status TEXT NOT NULL, plan_json TEXT NOT NULL, decided_at REAL, result_json TEXT);
CREATE TABLE IF NOT EXISTS action_keys (key TEXT PRIMARY KEY, action_id TEXT NOT NULL, done_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS watchlist (ticker TEXT PRIMARY KEY, added_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper_trades (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL,
  entry_price REAL NOT NULL, entry_date TEXT NOT NULL, thesis_id TEXT, exit_price REAL, exit_date TEXT);
"""


USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
  key TEXT NOT NULL, bucket TEXT NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (key, bucket));
"""

_RUN_COLS = ["run_id", "ticker", "created_at", "result_json", "events_json"]
_OUTCOME_COLS = ["thesis_id", "scored_at", "horizon_date", "price_at_horizon", "ret_pct", "benchmark_ret_pct",
                 "excess_ret_pct", "direction_hit", "beat_benchmark", "stop_hit", "brier", "detail_json"]  # fmt: skip
_ACTION_COLS = ["id", "run_id", "ticker", "created_at", "status", "plan_json", "decided_at", "result_json"]


def _default_path() -> Path:
    return Path(get_settings().cache_db).with_name("axiom_state.db")


class Store:
    def __init__(self, path: Path | None = None, url: str | None = None):
        self.db = Db(url=url, path=None if url else Path(path or _default_path()))
        self.path = self.db.path
        self.db.init_schema(SCHEMA + USAGE_SCHEMA)

    def _conn(self):
        return self.db.connect()

    @property
    def ident(self) -> str:
        return self.db.ident

    # ----------------------------------------------------------------- usage
    def hit(self, key: str, window: str, limit: int) -> bool:
        """Count one use of `key` in `window` (an hour, a day). False (and not counted) once `limit` is
        reached. Atomic, so it also holds across serverless instances that share a Postgres."""
        if limit <= 0:
            return True
        with self._conn() as c:
            row = c.execute(
                "INSERT INTO usage (key, bucket, n) VALUES (?,?,1) ON CONFLICT (key, bucket) DO UPDATE"
                " SET n = usage.n + 1 WHERE usage.n < ? RETURNING n",
                (key, window, limit),
            ).fetchone()
        return row is not None

    def usage(self, key: str, window: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT n FROM usage WHERE key=? AND bucket=?", (key, window)).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------ runs
    def save_run(self, run_id: str, ticker: str, result: dict, events: list[dict]) -> None:
        with self._conn() as c:
            c.execute(
                upsert_sql("runs", _RUN_COLS, "run_id"),
                (run_id, ticker, time.time(), json.dumps(result), json.dumps(events)),
            )

    def get_run(self, run_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return (
            None
            if r is None
            else {"result": json.loads(r["result_json"]), "events": json.loads(r["events_json"])}
        )

    def list_runs(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT run_id, ticker, created_at, result_json FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            memo = json.loads(r["result_json"]).get("memo", {})
            out.append(
                {
                    "run_id": r["run_id"],
                    "ticker": r["ticker"],
                    "created_at": r["created_at"],
                    "rating": memo.get("rating"),
                    "conviction": memo.get("conviction"),
                }
            )
        return out

    # ---------------------------------------------------------------- theses
    def add_thesis(
        self,
        *,
        run_id: str,
        ticker: str,
        issue_date: str,
        horizon_days: int,
        price_at_issue: float,
        rating: str,
        conviction: float,
        stop_price: float | None,
        memo: dict,
        findings: list[dict],
    ) -> str:
        tid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute(
                "INSERT INTO theses (id, run_id, ticker, created_at, issue_date, horizon_days, price_at_issue,"
                " rating, conviction, stop_price, memo_json, findings_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, run_id, ticker, time.time(), issue_date, horizon_days, price_at_issue, rating,
                 conviction, stop_price, json.dumps(memo), json.dumps(findings)),
            )  # fmt: skip
        return tid

    def theses(self, ticker: str | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
        q, args = "SELECT * FROM theses WHERE 1=1", []
        if ticker:
            q, args = q + " AND ticker=?", [*args, ticker]
        if status:
            q, args = q + " AND status=?", [*args, status]
        q += " ORDER BY created_at DESC LIMIT ?"
        with self._conn() as c:
            rows = c.execute(q, [*args, limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["memo"], d["findings"] = json.loads(d.pop("memo_json")), json.loads(d.pop("findings_json"))
            out.append(d)
        return out

    def save_outcome(self, thesis_id: str, o: dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute(
                upsert_sql("outcomes", _OUTCOME_COLS, "thesis_id"),
                (
                    thesis_id, time.time(), o["horizon_date"], o["price_at_horizon"], o["ret_pct"],
                    o.get("benchmark_ret_pct"), o.get("excess_ret_pct"), o.get("direction_hit"),
                    o.get("beat_benchmark"), o.get("stop_hit"), o.get("brier"),
                    json.dumps(o.get("detail", {})),
                ),
            )  # fmt: skip
            c.execute("UPDATE theses SET status='scored' WHERE id=?", (thesis_id,))

    def scored(self, ticker: str | None = None) -> list[dict]:
        q = (
            "SELECT t.*, o.horizon_date, o.price_at_horizon, o.ret_pct, o.benchmark_ret_pct, o.excess_ret_pct,"
            " o.direction_hit, o.beat_benchmark, o.stop_hit, o.brier, o.detail_json FROM theses t"
            " JOIN outcomes o ON o.thesis_id = t.id"
        )
        args: list[Any] = []
        if ticker:
            q, args = q + " WHERE t.ticker=?", [ticker]
        with self._conn() as c:
            rows = c.execute(q + " ORDER BY t.created_at DESC", args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["memo"], d["findings"] = json.loads(d.pop("memo_json")), json.loads(d.pop("findings_json"))
            d["detail"] = json.loads(d.pop("detail_json"))
            out.append(d)
        return out

    # --------------------------------------------------------------- actions
    def save_action(self, action: dict) -> None:
        with self._conn() as c:
            c.execute(
                upsert_sql("actions", _ACTION_COLS, "id"),
                (action["id"], action["run_id"], action["ticker"], action["created_at"], action["status"],
                 json.dumps(action), action.get("decided_at"), json.dumps(action.get("result"))),
            )  # fmt: skip

    def get_action(self, action_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT plan_json FROM actions WHERE id=?", (action_id,)).fetchone()
        return None if r is None else json.loads(r["plan_json"])

    def list_actions(self, status: str | None = None, limit: int = 50) -> list[dict]:
        q, args = "SELECT plan_json FROM actions", []
        if status:
            q, args = q + " WHERE status=?", [status]
        with self._conn() as c:
            rows = c.execute(q + " ORDER BY created_at DESC LIMIT ?", [*args, limit]).fetchall()
        return [json.loads(r["plan_json"]) for r in rows]

    def claim_key(self, key: str, action_id: str) -> bool:
        """Atomically reserve an idempotency key. False means that step already ran."""
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO action_keys VALUES (?,?,?) ON CONFLICT DO NOTHING", (key, action_id, time.time())
            )
            return cur.rowcount == 1

    def release_key(self, key: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM action_keys WHERE key=?", (key,))

    # ------------------------------------------------------ watchlist / trades
    def watchlist(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM watchlist ORDER BY added_at").fetchall()]

    def watch_add(self, ticker: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO watchlist VALUES (?,?) ON CONFLICT DO NOTHING", (ticker, time.time()))

    def watch_remove(self, ticker: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))

    def add_trade(self, trade: dict) -> str:
        tid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute(
                "INSERT INTO paper_trades (id, ticker, side, quantity, entry_price, entry_date, thesis_id)"
                " VALUES (?,?,?,?,?,?,?)",
                (tid, trade["ticker"], trade["side"], trade["quantity"], trade["entry_price"],
                 trade["entry_date"], trade.get("thesis_id")),
            )  # fmt: skip
        return tid

    def trades(self) -> list[dict]:
        with self._conn() as c:
            return [
                dict(r) for r in c.execute("SELECT * FROM paper_trades ORDER BY entry_date DESC").fetchall()
            ]

    def close_trade(self, trade_id: str, exit_price: float, exit_date: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE paper_trades SET exit_price=?, exit_date=? WHERE id=?",
                (exit_price, exit_date, trade_id),
            )

    def delete_trade(self, trade_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM paper_trades WHERE id=?", (trade_id,))


_store: Store | None = None


def get_store() -> Store:
    global _store
    url = get_settings().database_url
    ident = url or str(_default_path())
    if _store is None or _store.ident != ident:
        _store = Store(url=url) if url else Store(_default_path())
    return _store


__all__ = ["Store", "get_store", "BACKEND_DIR"]
