"""Where a trading session keeps its record: orders, contracts, journal, equity curve, state.

`StoreLedger` persists to the app's database (SQLite or Postgres) for the live agent. `MemoryLedger` keeps a
Time Machine replay in memory (thousands of bars, no per-bar writes) and can be flushed to the store at the end.
Both expose the same methods, so the engine does not know which one it has.
"""

from __future__ import annotations

import json
from typing import Any

from axiom.db import upsert_sql

from .journal import GENESIS, seal
from .models import JournalEntry, Order


class MemoryLedger:
    def __init__(self, session: str):
        self.session = session
        self._orders: dict[str, dict] = {}
        self._contracts: dict[str, dict] = {}
        self._journal: list[JournalEntry] = []
        self._equity: dict[float, dict] = {}
        self._state: dict[str, Any] = {}

    # orders
    def save_order(self, o: Order) -> None:
        self._orders[o.id] = o.model_dump()

    def orders(self, limit: int = 200) -> list[dict]:
        return sorted(self._orders.values(), key=lambda o: o["submitted_at"], reverse=True)[:limit]

    # contracts
    def save_contract(self, c: dict) -> None:
        self._contracts[c["id"]] = dict(c)

    def contracts(self, status: str | None = None, limit: int = 500) -> list[dict]:
        rows = [c for c in self._contracts.values() if status is None or c["status"] == status]
        return sorted(rows, key=lambda c: c["created_at"], reverse=True)[:limit]

    # journal
    def append_journal(
        self, kind: str, text: str, *, ts: float, symbol: str | None = None, facts: dict | None = None
    ) -> JournalEntry:
        prev = self._journal[-1].hash if self._journal else GENESIS
        e = seal(
            JournalEntry(session=self.session, seq=len(self._journal) + 1, ts=ts, kind=kind, symbol=symbol,
                         text=text, facts=_jsonable(facts or {})),
            prev,
        )  # fmt: skip
        self._journal.append(e)
        return e

    def journal(self, limit: int = 200, after_seq: int = 0) -> list[JournalEntry]:
        rows = [e for e in self._journal if e.seq > after_seq]
        return rows[-limit:]

    def journal_all(self) -> list[JournalEntry]:
        return list(self._journal)

    # equity
    def snapshot(self, ts: float, equity: float, cash: float, benchmark: float | None = None) -> None:
        self._equity[ts] = {"ts": ts, "equity": equity, "cash": cash, "benchmark": benchmark}

    def equity_curve(self, limit: int = 5000) -> list[dict]:
        return [self._equity[k] for k in sorted(self._equity)][-limit:]

    # state
    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    def flush_to(self, store) -> StoreLedger:
        """Copy this replay into the database under the same session, in a single transaction."""
        led = StoreLedger(store, self.session)
        led.clear()
        with store.db.connect() as c:
            for o in self._orders.values():
                c.execute(upsert_sql("trade_orders", _ORDER_COLS, "id"), _order_row(self.session, o))
            for k in self._contracts.values():
                c.execute(upsert_sql("trade_contracts", _CONTRACT_COLS, "id"), _contract_row(self.session, k))
            for e in self._journal:
                c.execute(_JOURNAL_INSERT, _journal_row(e))
            for s in self._equity.values():
                c.execute(_EQUITY_UPSERT, (self.session, s["ts"], s["equity"], s["cash"], s["benchmark"]))
        return led


_ORDER_COLS = ["id", "session", "ts", "symbol", "side", "status", "order_json"]
_CONTRACT_COLS = ["id", "session", "created_at", "symbol", "status", "contract_json"]
_JOURNAL_INSERT = (
    "INSERT INTO journal (session, seq, ts, kind, symbol, text, facts_json, prev_hash, hash)"
    " VALUES (?,?,?,?,?,?,?,?,?)"
)
_EQUITY_UPSERT = (
    "INSERT INTO equity_snapshots (session, ts, equity, cash, benchmark) VALUES (?,?,?,?,?)"
    " ON CONFLICT (session, ts) DO UPDATE SET equity=excluded.equity, cash=excluded.cash,"
    " benchmark=excluded.benchmark"
)


def _jsonable(d: dict) -> dict:
    return json.loads(json.dumps(d, default=str))


def _order_row(session: str, o: dict) -> tuple:
    return (o["id"], session, o["submitted_at"], o["symbol"], o["side"], o["status"], json.dumps(o))


def _contract_row(session: str, c: dict) -> tuple:
    return (c["id"], session, c["created_at"], c["symbol"], c["status"], json.dumps(c, default=str))


def _journal_row(e: JournalEntry) -> tuple:
    return (e.session, e.seq, e.ts, e.kind, e.symbol, e.text, json.dumps(e.facts), e.prev_hash, e.hash)


class StoreLedger:
    def __init__(self, store, session: str = "live"):
        self.store = store
        self.session = session

    def _c(self):
        return self.store.db.connect()

    def clear(self) -> None:
        with self._c() as c:
            for t in ("trade_orders", "trade_contracts", "journal", "equity_snapshots"):
                c.execute(f"DELETE FROM {t} WHERE session=?", (self.session,))

    # orders
    def save_order(self, o: Order) -> None:
        with self._c() as c:
            c.execute(upsert_sql("trade_orders", _ORDER_COLS, "id"), _order_row(self.session, o.model_dump()))

    def orders(self, limit: int = 200) -> list[dict]:
        with self._c() as c:
            rows = c.execute(
                "SELECT order_json FROM trade_orders WHERE session=? ORDER BY ts DESC LIMIT ?",
                (self.session, limit),
            ).fetchall()
        return [json.loads(r["order_json"]) for r in rows]

    # contracts
    def save_contract(self, k: dict) -> None:
        with self._c() as c:
            c.execute(upsert_sql("trade_contracts", _CONTRACT_COLS, "id"), _contract_row(self.session, k))

    def contracts(self, status: str | None = None, limit: int = 500) -> list[dict]:
        q, args = "SELECT contract_json FROM trade_contracts WHERE session=?", [self.session]
        if status:
            q, args = q + " AND status=?", [*args, status]
        with self._c() as c:
            rows = c.execute(q + " ORDER BY created_at DESC LIMIT ?", [*args, limit]).fetchall()
        return [json.loads(r["contract_json"]) for r in rows]

    # journal
    def append_journal(
        self, kind: str, text: str, *, ts: float, symbol: str | None = None, facts: dict | None = None
    ) -> JournalEntry:
        with self._c() as c:
            last = c.execute(
                "SELECT seq, hash FROM journal WHERE session=? ORDER BY seq DESC LIMIT 1", (self.session,)
            ).fetchone()
            seq, prev = (int(last["seq"]) + 1, last["hash"]) if last else (1, GENESIS)
            e = seal(
                JournalEntry(session=self.session, seq=seq, ts=ts, kind=kind, symbol=symbol, text=text,
                             facts=_jsonable(facts or {})),
                prev,
            )  # fmt: skip
            c.execute(_JOURNAL_INSERT, _journal_row(e))
        return e

    def _rows(self, sql: str, args: tuple) -> list[JournalEntry]:
        with self._c() as c:
            rows = c.execute(sql, args).fetchall()
        return [
            JournalEntry(session=r["session"], seq=int(r["seq"]), ts=float(r["ts"]), kind=r["kind"],
                         symbol=r["symbol"], text=r["text"], facts=json.loads(r["facts_json"]),
                         prev_hash=r["prev_hash"], hash=r["hash"])
            for r in rows
        ]  # fmt: skip

    def journal(self, limit: int = 200, after_seq: int = 0) -> list[JournalEntry]:
        rows = self._rows(
            "SELECT * FROM journal WHERE session=? AND seq>? ORDER BY seq DESC LIMIT ?",
            (self.session, after_seq, limit),
        )
        return rows[::-1]

    def journal_all(self) -> list[JournalEntry]:
        return self._rows("SELECT * FROM journal WHERE session=? ORDER BY seq", (self.session,))

    # equity
    def snapshot(self, ts: float, equity: float, cash: float, benchmark: float | None = None) -> None:
        with self._c() as c:
            c.execute(_EQUITY_UPSERT, (self.session, ts, equity, cash, benchmark))

    def equity_curve(self, limit: int = 5000) -> list[dict]:
        with self._c() as c:
            rows = c.execute(
                "SELECT ts, equity, cash, benchmark FROM equity_snapshots WHERE session=? ORDER BY ts DESC LIMIT ?",
                (self.session, limit),
            ).fetchall()
        return [dict(r) for r in rows][::-1]

    # state (scoped by session so a replay can never flip the live kill switch)
    def get_state(self, key: str, default: Any = None) -> Any:
        with self._c() as c:
            r = c.execute("SELECT v FROM trader_state WHERE k=?", (f"{self.session}:{key}",)).fetchone()
        return default if r is None else json.loads(r["v"])

    def set_state(self, key: str, value: Any) -> None:
        with self._c() as c:
            c.execute(
                upsert_sql("trader_state", ["k", "v"], "k"), (f"{self.session}:{key}", json.dumps(value))
            )
