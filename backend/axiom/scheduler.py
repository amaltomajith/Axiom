"""Daily briefing: analyse the watchlist, score matured theses, post one digest.

    uv run python -m axiom.scheduler --once      # run now (useful for testing / cron)
    SCHEDULER_ENABLED=true  -> the API process runs it on SCHEDULER_CRON

The digest is read-style (no trades), so it is the one action that is auto-approved. Per-ticker runs
share a token budget so a long watchlist cannot burn a free LLM quota.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from axiom.actions import approval
from axiom.actions.executors import Executor, build_executor
from axiom.actions.planner import digest_plan
from axiom.agents.toolbox import McpToolBox
from axiom.config import get_settings
from axiom.llm.client import LLMClient, TokenBudget
from axiom.llm.types import LLMError
from axiom.memory import scorer
from axiom.memory.store import Store, get_store
from axiom.pipeline import run_pipeline

log = logging.getLogger("axiom.scheduler")
MAX_WATCHLIST_PER_RUN = 8


def _line(ticker: str, memo: dict[str, Any]) -> str:
    return (
        f"• {ticker}: {memo['rating'].replace('_', ' ')} ({memo['conviction']:.0%}): {memo['thesis'][:110]}"
    )


async def run_briefing(
    store: Store | None = None,
    llm_factory=None,
    executor: Executor | None = None,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    store = store or get_store()
    s = get_settings()
    executor = executor or build_executor(s)
    names = tickers or [w["ticker"] for w in store.watchlist()][:MAX_WATCHLIST_PER_RUN]
    scoring = await scorer.score_due(store)  # first: learn from what has matured

    lines: list[str] = []
    failures: list[str] = []
    for t in names:
        llm = (
            llm_factory or (lambda: LLMClient(budget=TokenBudget(s.run_token_budget, s.run_max_llm_calls)))
        )()
        try:
            async with McpToolBox.inprocess() as box:
                out = await run_pipeline(t, llm=llm, box=box, store=store, executor=executor)
            lines.append(_line(t, out.result.memo.model_dump()))
        except (LLMError, Exception) as e:  # one bad ticker must not sink the briefing
            failures.append(f"{t}: {type(e).__name__}")
            log.warning("briefing: %s failed: %s", t, e)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    card = scorer.scorecard(store)
    parts = [f"*Axiom briefing {today}*"]
    parts += lines or ["(watchlist empty or all analyses failed)"]
    if scoring["scored"]:
        parts.append(f"Scored {scoring['scored']} matured theses.")
    if card["n_directional"]:
        parts.append(
            f"Track record: {card['direction_hit_rate']:.0%} hit rate over {card['n_directional']} calls. {card['sample_note']}"
        )
    if failures:
        parts.append("Failed: " + ", ".join(failures))
    parts.append("Research only, not financial advice.")
    text = "\n".join(parts)

    plan = digest_plan(f"briefing-{today}", text)
    approval.save(store, plan)
    done = await approval.approve(store, plan.id, executor)  # digest is the only auto-approved action
    return {
        "text": text,
        "analyzed": len(lines),
        "failed": failures,
        "scoring": scoring,
        "digest_status": done.status,
    }


def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_briefing, CronTrigger.from_crontab(get_settings().scheduler_cron), id="daily-briefing"
    )
    scheduler.start()
    log.info("scheduler started: %s", get_settings().scheduler_cron)
    return scheduler


def main() -> None:
    p = argparse.ArgumentParser(description="Axiom daily briefing")
    p.add_argument("--once", action="store_true", help="run the briefing now and exit")
    p.add_argument("tickers", nargs="*", help="override the watchlist")
    args = p.parse_args()
    if not args.once:
        p.error("use --once (the scheduled mode runs inside the API when SCHEDULER_ENABLED=true)")
    result = asyncio.run(run_briefing(tickers=[t.upper() for t in args.tickers] or None))
    print(result["text"])
    print(f"\n[{result['digest_status']}] analyzed={result['analyzed']} failed={result['failed']}")


if __name__ == "__main__":
    main()
