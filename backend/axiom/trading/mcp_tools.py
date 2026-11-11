"""What the five trading MCP tools do. The MCP server (`axiom/mcp_server/server.py`) only declares them.

Every tool acts on the same `TraderService` as the API and gets no shortcut:
  * an entry goes through `Engine.propose`: the strategy must have qualified and be signalling, the risk
    kernel sizes it (a caller may only ask for a fraction of that size), and Supervised mode queues it for a
    human. No tool accepts a quantity, a price or a stop for an entry.
  * a stop can only be raised; closing and flattening only ever reduce risk.
  * the research agents cannot call any of them: their allowlists (`agents/prompts.py`) do not name them.

Errors come back as `{"ok": False, "error": ...}` so an MCP client reads a reason, not a stack trace.
"""

from __future__ import annotations

from typing import Any

from .broker.base import BrokerError
from .contracts import outcomes_by_regime
from .service import current
from .symbols import parse

TRADING_TOOLS = [
    "place_paper_bracket_order",
    "modify_stop_loss",
    "close_paper_position",
    "emergency_flatten_all",
    "get_past_trade_outcomes",
]


def _engine():
    return current().need().engine


async def _run(fn) -> dict[str, Any]:
    try:
        return {"paper": True, **(await fn())}
    except (ValueError, KeyError, RuntimeError, BrokerError) as e:
        return {"ok": False, "paper": True, "error": str(e)[:300]}


async def place_order(symbol: str, reason: str, strategy: str | None, size_fraction: float) -> dict:
    async def go() -> dict:
        out = await _engine().propose(
            parse(symbol).name, strategy=strategy, size_fraction=size_fraction, reason=reason
        )
        v = out.pop("verdict")
        return {
            "ok": out["status"] in ("submitted", "pending_approval"),
            **out,
            "qty": v["qty"], "price": v["price"], "stop_price": v["stop_price"], "notional": v["notional"],
            "risk_amount": v["risk_amount"], "blocked_by": v["blocked_by"],
            "checks": [{"rule": c["rule"], "ok": c["ok"], "detail": c["detail"]} for c in v["checks"]],
        }  # fmt: skip

    return await _run(go)


async def modify_stop(symbol: str, stop_price: float) -> dict:
    return await _run(lambda: _engine().tighten_stop(parse(symbol).name, stop_price))


async def close_position(symbol: str, reason: str) -> dict:
    return await _run(lambda: _engine().close_position(parse(symbol).name, reason))


async def flatten_all(reason: str) -> dict:
    async def go() -> dict:
        out = await current().kill(reason.strip()[:200] or "emergency flatten through an MCP tool")
        return {**out, "killed": True, "note": "The kill switch is engaged. Only a human can resume trading."}

    return await _run(go)


async def past_outcomes(session: str = "live") -> dict:
    async def go() -> dict:
        rows = outcomes_by_regime(current().ledger(session).contracts())
        return {
            "ok": True, "session": session, "graded_trades": sum(r["trades"] for r in rows), "groups": rows,
            "note": "Paper trades only. A handful of trades is an anecdote, not evidence of an edge.",
        }  # fmt: skip

    return await _run(go)
