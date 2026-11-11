"""Autopilot command line.

uv run python -m axiom.trading backtest [--symbols BTC/USD,SPY] [--out ../docs/backtest-report.md]
uv run python -m axiom.trading run            # the live loop (broker and brain from settings)
uv run python -m axiom.trading kill [reason]  # engage the kill switch: the running loop flattens next tick
uv run python -m axiom.trading resume
uv run python -m axiom.trading status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from axiom.config import BACKEND_DIR, get_settings

DEFAULT_REPORT = BACKEND_DIR.parent / "docs" / "backtest-report.md"


async def _backtest(args) -> int:
    from .data import fetch_daily
    from .replay import run_replay
    from .report import build_report, render_markdown
    from .symbols import parse_list

    syms = parse_list(args.symbols or get_settings().trader_symbols)
    print(f"Fetching daily history for {', '.join(s.name for s in syms)} ...", file=sys.stderr)
    frames = await fetch_daily(syms, args.bars)
    print("Replaying through the engine ...", file=sys.stderr)
    res = await run_replay(frames)
    rep = build_report(res)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(rep), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if args.save:
        from axiom.memory.store import get_store

        res.ledger.flush_to(get_store())
    a, b = rep["agent"], rep["benchmark"]
    print(
        f"verdict={rep['verdict']['verdict']} agent: return {a['total_return']:+.1%} sharpe {a['sharpe']} "
        f"maxDD {a['max_drawdown']:.1%} | buy-and-hold: return {b['total_return']:+.1%} sharpe {b['sharpe']} "
        f"maxDD {b['max_drawdown']:.1%}\nwrote {out} and {out.with_suffix('.json')}"
    )
    return 0


async def _run(args) -> int:
    from .live import Trader

    trader = Trader.from_settings()
    await trader.run_forever()
    return 0


def _ledger():
    from axiom.memory.store import get_store

    from .ledger import StoreLedger

    return StoreLedger(get_store(), "live")


def _kill(args) -> int:
    from .engine import KILL_FILE

    led = _ledger()
    led.set_state("killed", True)
    KILL_FILE.write_text(" ".join(args.reason) or "killed from the command line", encoding="utf-8")
    print("Kill switch engaged. The running loop flattens every position on its next tick.")
    return 0


def _resume(args) -> int:
    from .engine import KILL_FILE

    _ledger().set_state("killed", False)
    KILL_FILE.unlink(missing_ok=True)
    print("Kill switch released.")
    return 0


def _status(args) -> int:
    led = _ledger()
    eng = led.get_state("engine") or {}
    print(json.dumps({"killed": bool(led.get_state("killed")), **{k: eng.get(k) for k in
                      ("autonomy", "halted", "day", "day_start_equity", "trades_today", "meta")}}, indent=1))  # fmt: skip
    for e in led.journal(limit=args.n):
        print(f"[{e.seq}] {e.kind:<10} {e.text}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m axiom.trading", description="Axiom Autopilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest", help="replay history through the engine and write the report")
    b.add_argument("--symbols", default=None)
    b.add_argument("--bars", type=int, default=1500)
    b.add_argument("--out", default=str(DEFAULT_REPORT))
    b.add_argument("--save", action="store_true", help="also store the replay so the UI can browse it")
    sub.add_parser("run", help="run the live trading loop")
    k = sub.add_parser("kill", help="engage the kill switch")
    k.add_argument("reason", nargs="*")
    sub.add_parser("resume", help="release the kill switch")
    st = sub.add_parser("status", help="state and the latest journal entries")
    st.add_argument("-n", type=int, default=15)
    args = p.parse_args()
    if args.cmd == "backtest":
        sys.exit(asyncio.run(_backtest(args)))
    if args.cmd == "run":
        sys.exit(asyncio.run(_run(args)))
    sys.exit({"kill": _kill, "resume": _resume, "status": _status}[args.cmd](args))


if __name__ == "__main__":
    main()
