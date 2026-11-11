"""The trading desk: the four research agents review every candidate entry before the risk kernel sees it.

The wrapped brain (rules, or the LLM selector) proposes an entry. The desk then runs the same pipeline the
Analyze tab uses, unchanged: Technical Analyst and Fundamental Auditor gather evidence through MCP tools,
the Lead Synthesizer writes a memo, the Risk Critic challenges it, and the deterministic policy guard caps
the rating. The memo is mapped to a decision by fixed rules:

  * SELL or STRONG_SELL: veto. HOLD: veto (or half size if `hold_policy="half"`).
  * BUY or STRONG_BUY: enter. If the Critic raised issues, or conviction ended below 0.5, the desk asks
    for half the size. It can only ask for less than the kernel's own size, never more.
  * NO_CALL, an error, a timeout or the hourly cap: the desk has no view, so the wrapped brain's decision
    stands, marked `degraded`.

Boundaries, all enforced in code:
  * The desk is consulted only for entries. Exits, holds and stops stay mechanical.
  * It never sees an order tool, never sets a quantity or a stop. `size_factor` is at most 1.
  * A review runs in the background. If it is not ready within `wait` seconds the desk answers
    `stay_flat` with `reviewing=True`, and the live loop asks again on its next tick for the same bar, so
    a slow LLM can never hang a tick or trip the watchdog.
  * Like the LLM brain, it is never run over history.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Literal

from axiom.agents.orchestrator import AnalysisResult, analyze
from axiom.agents.toolbox import McpToolBox, ToolBox
from axiom.agents.trace import TraceEvent, Tracer

from .brain import Brain, Decision, MarketView, RuleBrain
from .symbols import parse

Analyzer = Callable[..., Awaitable[AnalysisResult]]
BoxFactory = Callable[[], AbstractAsyncContextManager[ToolBox]]
HoldPolicy = Literal["veto", "half"]
BULLISH = ("BUY", "STRONG_BUY")
BEARISH = ("SELL", "STRONG_SELL")
HALF = 0.5
LOW_CONVICTION = 0.5
_KEEP = {"run_start", "handoff", "tool_call", "tool_result", "finding", "agent_error", "memo_draft",
         "critique", "guardrail", "final", "error", "run_end"}  # fmt: skip


@dataclass
class DeskTracer(Tracer):
    """A tracer that also hands every event to a callback, so the cockpit can show the run as it happens."""

    on_event: Callable[[TraceEvent], None] | None = None

    def emit(self, type_: str, agent: str = "system", **data: Any) -> TraceEvent:
        ev = super().emit(type_, agent, **data)
        if self.on_event is not None:
            try:
                self.on_event(ev)
            except Exception:  # a broken listener must never stop a review
                pass
        return ev


@dataclass
class DeskReview:
    """What the desk concluded about one candidate entry. `ok=False` means it has no view."""

    ok: bool
    symbol: str
    strategy: str | None
    started_at: float
    finished_at: float | None = None
    run_id: str | None = None
    rating: str | None = None
    conviction: float | None = None
    thesis: str | None = None
    stances: dict[str, str] = field(default_factory=dict)
    critic_ok: bool | None = None  # None: the Critic did not run or its reply was invalid
    critic_issues: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    error: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "rating": self.rating, "conviction": self.conviction,
            "thesis": self.thesis, "stances": self.stances, "critic_ok": self.critic_ok,
            "critic_issues": self.critic_issues, "guardrails": self.guardrails, "degraded": self.degraded,
            "evidence": self.evidence, "error": self.error,
        }  # fmt: skip


@dataclass
class _Job:
    strategy: str | None
    started: float
    task: asyncio.Task[DeskReview]


def review_from(result: AnalysisResult, symbol: str, strategy: str | None, started: float) -> DeskReview:
    critique = next((e["data"] for e in reversed(result.events) if e["type"] == "critique"), None)
    cited = sorted({i for c in result.memo.all_claims for i in c.evidence if i in result.evidence})
    return DeskReview(
        ok=result.memo.rating != "NO_CALL",
        symbol=symbol,
        strategy=strategy,
        started_at=started,
        run_id=result.run_id,
        rating=result.memo.rating,
        conviction=round(result.memo.conviction, 2),
        thesis=result.memo.thesis,
        stances={f.agent: f.stance for f in result.findings},
        critic_ok=None if critique is None else bool(critique.get("ok")),
        critic_issues=[] if critique is None else [str(x)[:300] for x in critique.get("issues", [])][:3],
        guardrails=[g[:300] for g in result.guardrails][:6],
        degraded=[d[:300] for d in result.degraded][:4],
        evidence=cited,
        error=None if result.memo.rating != "NO_CALL" else "the desk issued no rating (NO_CALL)",
    )


def _event_view(ev: TraceEvent, symbol: str) -> dict[str, Any]:
    """A small, display-safe copy of a trace event: long strings are cut, the memo's markdown is dropped."""
    data: dict[str, Any] = {}
    for k, v in ev.data.items():
        if k == "markdown":
            continue
        data[k] = v[:400] if isinstance(v, str) else v
    return {"seq": ev.seq, "ts": ev.ts, "run_id": ev.run_id, "kind": ev.type, "agent": ev.agent,
            "symbol": symbol, "data": data}  # fmt: skip


class DeskBrain:
    name = "desk"

    def __init__(
        self,
        inner: Brain | None = None,
        *,
        llm_factory: Callable[[], Any],
        box_factory: BoxFactory = McpToolBox.inprocess,
        analyzer: Analyzer = analyze,
        max_runs_per_hour: int = 6,
        timeout: float = 240.0,
        wait: float = 20.0,
        ttl: float = 4 * 3600.0,
        hold_policy: HoldPolicy = "veto",
        equity: float = 100_000.0,
        memory: Callable[[str], str] | None = None,
        narrator: Any = None,
        clock: Callable[[], float] = time.time,
    ):
        self.inner = inner or RuleBrain()
        self.llm_factory = llm_factory
        self.box_factory = box_factory
        self.analyzer = analyzer
        self.max_runs_per_hour = max_runs_per_hour
        self.timeout = timeout
        self.wait = wait
        self.ttl = ttl
        self.hold_policy: HoldPolicy = hold_policy
        self.equity = equity
        self.memory = memory
        self.narrator = narrator
        self.clock = clock
        self.runs: deque[float] = deque()
        self.jobs: dict[str, _Job] = {}
        self.listeners: list[Callable[[dict], None]] = []
        self.last: dict[
            str, dict[str, Any]
        ] = {}  # symbol -> {"review": ..., "events": [...]} for the cockpit
        self.last_error: str | None = None

    @classmethod
    def from_settings(cls, *, bar_seconds: float = 3600.0) -> DeskBrain:
        from axiom.config import get_settings
        from axiom.llm.client import LLMClient, TokenBudget

        from .llm_brain import LLMBrain

        s = get_settings()
        return cls(
            RuleBrain(),
            llm_factory=lambda: LLMClient(budget=TokenBudget(s.run_token_budget, s.run_max_llm_calls)),
            max_runs_per_hour=s.trader_max_desk_runs_per_hour,
            ttl=max(bar_seconds, 4 * 3600.0),
            hold_policy="half" if s.trader_desk_hold == "half" else "veto",
            equity=s.trader_starting_cash,
            # the narrator only rewrites journal entries; its numbers are checked against the facts
            narrator=LLMBrain(LLMClient(), max_calls_per_hour=s.trader_max_llm_calls_per_hour),
        )

    # --------------------------------------------------------------- budget
    def _take_run(self) -> bool:
        now = self.clock()
        while self.runs and now - self.runs[0] >= 3600:
            self.runs.popleft()
        if len(self.runs) >= self.max_runs_per_hour:
            return False
        self.runs.append(now)
        return True

    def runs_left(self) -> int:
        now = self.clock()
        return max(0, self.max_runs_per_hour - sum(1 for t in self.runs if now - t < 3600))

    # --------------------------------------------------------------- decide
    async def decide(self, view: MarketView) -> Decision:
        base = await self.inner.decide(view)
        if base.action != "enter_long":
            return base
        now = self.clock()
        job = self.jobs.get(view.symbol)
        if job is not None and (job.strategy != base.strategy or now - job.started >= self.ttl):
            job.task.cancel()
            job = None
        if job is None:
            if not self._take_run():
                return _stands(base, "the hourly cap on desk reviews was reached", None)
            task = asyncio.create_task(self._review(view, base, now))
            job = self.jobs[view.symbol] = _Job(base.strategy, now, task)
        if not job.task.done():
            await asyncio.wait({job.task}, timeout=self.wait)
        if not job.task.done():
            return Decision(
                symbol=view.symbol, ts=view.ts, action="stay_flat", strategy=base.strategy, source="desk",
                reviewing=True, flags=base.flags,
                reason=f"The trading desk is still reviewing the {base.strategy} entry.",
            )  # fmt: skip
        try:
            review = job.task.result()
        except (asyncio.CancelledError, Exception) as e:  # _review catches everything; this is a backstop
            review = DeskReview(False, view.symbol, base.strategy, job.started, error=type(e).__name__)
        return self._map(view, base, review)

    async def _review(self, view: MarketView, base: Decision, started: float) -> DeskReview:
        sym = view.symbol
        events: list[dict[str, Any]] = []
        self.last[sym] = {"review": None, "events": events, "started_at": started, "strategy": base.strategy}

        def on_event(ev: TraceEvent) -> None:
            if ev.type not in _KEEP:
                return
            item = _event_view(ev, sym)
            events.append(item)
            del events[:-200]
            self._publish({"type": "desk", "ts": ev.ts, **item})

        tracer = DeskTracer(on_event=on_event)

        async def work() -> AnalysisResult:
            async with self.box_factory() as box:
                return await self.analyzer(
                    parse(sym).yahoo,
                    llm=self.llm_factory(),
                    box=box,
                    equity=self.equity,
                    tracer=tracer,
                    memory_context=self.memory(sym) if self.memory else "",
                )

        try:
            result = await asyncio.wait_for(work(), self.timeout)
            review = review_from(result, sym, base.strategy, started)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"[:200]
            why = (
                "the review timed out"
                if isinstance(e, TimeoutError)
                else f"the review failed ({type(e).__name__})"
            )
            review = DeskReview(False, sym, base.strategy, started, run_id=tracer.run_id, error=why)
        review.finished_at = self.clock()
        self.last[sym]["review"] = review.summary()
        self._publish({"type": "desk_done", "ts": review.finished_at, "symbol": sym, "run_id": review.run_id,
                       "review": review.summary()})  # fmt: skip
        return review

    def _publish(self, ev: dict) -> None:
        for fn in list(self.listeners):
            try:
                fn(ev)
            except Exception:  # a broken listener must never stop a review
                pass

    # ------------------------------------------------------------------ map
    def _map(self, view: MarketView, base: Decision, r: DeskReview) -> Decision:
        if not r.ok:
            return _stands(base, r.error or "the desk had no view", r)
        views = ", ".join(f"{agent} {stance.replace('_', ' ')}" for agent, stance in r.stances.items())
        head = (
            f"The trading desk rated {view.symbol} {r.rating} with conviction {r.conviction:.2f} ({views})."
        )
        d: dict[str, Any] = dict(
            symbol=view.symbol, ts=view.ts, source="desk", strategy=base.strategy, flags=base.flags,
            confidence=round(min(0.9, max(0.1, r.conviction or 0.0)), 2), thesis=r.thesis, desk=r.summary(),
        )  # fmt: skip
        hold_veto = r.rating == "HOLD" and self.hold_policy == "veto"
        if r.rating in BEARISH or hold_veto:
            return Decision(**d, action="stay_flat", veto=True,
                            reason=f"{head} It vetoed the {base.strategy} entry: {r.thesis}")  # fmt: skip
        factor, why = 1.0, ""
        if r.rating == "HOLD":
            factor, why = HALF, "the desk was not convinced"
        elif r.critic_ok is False:
            issue = f": {r.critic_issues[0]}" if r.critic_issues else ""
            factor, why = HALF, f"the Risk Critic raised issues{issue}"
        elif (r.conviction or 0.0) < LOW_CONVICTION:
            factor, why = HALF, f"conviction ended below {LOW_CONVICTION:.2f}"
        size = (
            f" It asked for half the size the risk rules allow because {why.rstrip('.')}."
            if factor < 1.0
            else " It asked for no size cut."
        )
        return Decision(
            **d,
            action="enter_long",
            size_factor=factor,
            expected_move_pct=base.expected_move_pct,
            horizon_bars=base.horizon_bars,
            reason=f"{head}{size} Thesis: {r.thesis}",
        )

    # -------------------------------------------------------------- narrate
    async def narrate(self, template: str, facts: dict) -> tuple[str, bool, list[str]]:
        if self.narrator is None:
            return template, False, []
        return await self.narrator.narrate(template, facts)

    def status(self) -> dict[str, Any]:
        return {
            "runs_left": self.runs_left(),
            "max_runs_per_hour": self.max_runs_per_hour,
            "hold_policy": self.hold_policy,
            "reviewing": [s for s, j in self.jobs.items() if not j.task.done()],
            "last_error": self.last_error,
            "runs": self.last,
        }


def _stands(base: Decision, why: str, r: DeskReview | None) -> Decision:
    """The desk had no view: the wrapped brain's decision goes ahead, marked so the journal says so."""
    return base.model_copy(
        update={
            "degraded": True,
            "desk": r.summary() if r else {"error": why},
            "reason": f"{base.reason} (The trading desk did not review this: {why}.)",
        }
    )
