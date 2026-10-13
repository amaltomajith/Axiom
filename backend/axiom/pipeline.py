"""One call that runs a full analysis and does all the bookkeeping around it.

recall prior theses -> analyze (multi-agent) -> persist run -> record immutable thesis -> propose actions.
Used by the HTTP API and by the scheduled briefing, so both behave identically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from axiom.actions import approval
from axiom.actions.executors import Executor, build_executor
from axiom.actions.models import ActionPlan
from axiom.actions.planner import propose
from axiom.agents.orchestrator import AnalysisResult, analyze
from axiom.agents.toolbox import ToolBox
from axiom.agents.trace import Tracer
from axiom.llm.client import LLMClient
from axiom.memory import scorer
from axiom.memory.store import Store


@dataclass
class PipelineOutcome:
    result: AnalysisResult
    thesis_id: str
    action: ActionPlan | None
    action_reason: str


def _last_close(result: AnalysisResult) -> float | None:
    for item in result.evidence.values():
        if item["tool"] == "get_price_summary":
            try:
                return float(json.loads(item["text"])["last_close"])
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
    return result.position.entry_reference


def _issue_date(result: AnalysisResult) -> str:
    for item in result.evidence.values():
        if item["tool"] == "get_price_summary":
            try:
                return str(json.loads(item["text"])["meta"]["as_of"])
            except (KeyError, json.JSONDecodeError):
                continue
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d")


async def run_pipeline(
    ticker: str,
    *,
    llm: LLMClient,
    box: ToolBox,
    store: Store,
    equity: float = 100_000.0,
    tracer: Tracer | None = None,
    executor: Executor | None = None,
) -> PipelineOutcome:
    from axiom.data.market import normalize_ticker

    t = normalize_ticker(ticker)
    memory_context = scorer.recall(store, t)
    result = await analyze(t, llm=llm, box=box, equity=equity, tracer=tracer, memory_context=memory_context)

    store.save_run(result.run_id, t, result.to_dict(), result.events)

    price = _last_close(result)
    thesis_id = ""
    if price is not None:
        thesis_id = store.add_thesis(
            run_id=result.run_id,
            ticker=t,
            issue_date=_issue_date(result),
            horizon_days=result.memo.horizon_days,
            price_at_issue=price,
            rating=result.memo.rating,
            conviction=result.memo.conviction,
            stop_price=result.position.stop_price,
            memo=result.memo.model_dump(),
            findings=[f.model_dump() for f in result.findings],
        )

    executor = executor or build_executor()
    plan, reason = propose(result, executor.name)
    if plan is not None:
        approval.save(store, plan)
    return PipelineOutcome(result, thesis_id, plan, reason)
