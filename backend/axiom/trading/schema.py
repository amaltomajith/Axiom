"""Autopilot tables. Created with the rest of the store (memory/store.py). Every row carries a `session`:
`live` for the running agent, `replay:<id>` for a Time Machine run, so the two never mix."""

TRADING_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_orders (
  id TEXT PRIMARY KEY, session TEXT NOT NULL, ts REAL NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
  status TEXT NOT NULL, order_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS trade_orders_session ON trade_orders (session, ts DESC);
CREATE TABLE IF NOT EXISTS trade_contracts (
  id TEXT PRIMARY KEY, session TEXT NOT NULL, created_at REAL NOT NULL, symbol TEXT NOT NULL,
  status TEXT NOT NULL, contract_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS trade_contracts_session ON trade_contracts (session, created_at DESC);
CREATE TABLE IF NOT EXISTS journal (
  session TEXT NOT NULL, seq INTEGER NOT NULL, ts REAL NOT NULL, kind TEXT NOT NULL, symbol TEXT,
  text TEXT NOT NULL, facts_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL,
  PRIMARY KEY (session, seq));
CREATE TABLE IF NOT EXISTS equity_snapshots (
  session TEXT NOT NULL, ts REAL NOT NULL, equity REAL NOT NULL, cash REAL NOT NULL, benchmark REAL,
  PRIMARY KEY (session, ts));
CREATE TABLE IF NOT EXISTS trader_state (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS desk_reviews (
  run_id TEXT PRIMARY KEY, session TEXT NOT NULL, ts REAL NOT NULL, symbol TEXT NOT NULL,
  review_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS desk_reviews_session ON desk_reviews (session, ts DESC);
"""
