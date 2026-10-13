"""Multi-agent orchestration.

    Technical analyst ─┐
                       ├─> Risk Guard (tools) ─> Synthesizer ─> Critic ─> Policy guard ─> Position plan
    Fundamental auditor┘

Analysts run concurrently (bounded), each with its own tool allowlist. Everything the LLM may say is
checked mechanically: schema, citations/numbers (faithfulness), and policy caps on rating/conviction.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from axiom.config import get_settings
from axiom.data import market
from axiom.data.market import normalize_ticker
from axiom.llm.client import LLMClient
from axiom.llm.types import AllProvidersFailed, BudgetExceeded

from . import prompts
from .faithfulness import Evidence, check_claims
from .loop import AgentFailed, AgentSpec, run_agent
from .policy import apply_policy, technical_expected_stance
from .render import render_markdown
from .risk_guard import gather_risk_evidence, plan_for_rating
from .schemas import Critique, Finding, Memo, PositionPlan
from .toolbox import ToolBox, ToolRunner
from .trace import Tracer


@dataclass
class AnalysisResult:
    run_id: str
    ticker: str
    memo: Memo
    markdown: str
    findings: list[Finding]
    position: PositionPlan
    evidence: dict[str, dict]
    guardrails: list[str]
    degraded: list[str]
    usage: dict[str, int]
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "memo": self.memo.model_dump(),
            "markdown": self.markdown,
            "findings": [f.model_dump() for f in self.findings],
            "position": self.position.model_dump(),
            "evidence": {k: _evidence_view(v) for k, v in self.evidence.items()},
            "guardrails": self.guardrails,
            "degraded": self.degraded,
            "usage": self.usage,
        }


def _evidence_view(item: dict) -> dict[str, Any]:
    """What the UI needs to show a citation: tool, args, as-of/provider and a short excerpt."""
    meta: dict[str, Any] = {}
    try:
        parsed = json.loads(item["text"])
        meta = parsed.get("meta", {}) if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    return {
        "id": item["id"],
        "tool": item["tool"],
        "args": item["args"],
        "as_of": meta.get("as_of"),
        "provider": meta.get("provider"),
        "excerpt": item["text"][:600],
    }


def _insufficient(agent: str, why: str) -> Finding:
    from .schemas import Claim

    return Finding(
        agent=agent,
        stance="insufficient_data",
        confidence=0.0,
        summary=f"{agent} could not complete: {why}"[:480],
        claims=[Claim(text="No usable analysis was produced.", evidence=[])],
        caveats=[why[:200]],
    )


async def analyze(
    ticker: str,
    *,
    llm: LLMClient,
    box: ToolBox,
    equity: float = 100_000.0,
    tracer: Tracer | None = None,
    memory_context: str = "",
) -> AnalysisResult:
    tracer = tracer or Tracer()
    t = normalize_ticker(ticker)
    evidence = Evidence()
    degraded: list[str] = []
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    tracer.emit("run_start", "system", ticker=t, equity=equity, date=today)

    try:
        # Fail fast on an unknown/unavailable ticker BEFORE spending any LLM tokens. The fetch is
        # cached, so the analysts' own tool calls are then free.
        await market.fetch_ohlcv(t, 60)
        findings = await _run_analysts(t, today, llm, box, evidence, tracer, degraded)

        risk_tools = ToolRunner(box, evidence, tracer, "Risk Guard", prompts.RISK_TOOLS, namespace=3)
        tracer.emit(
            "handoff", "system", to="Risk Guard", reason="analysts finished; computing risk and sizing"
        )
        risk = await gather_risk_evidence(risk_tools, t, equity)

        memo, guardrails = await _synthesize(
            t, today, findings, risk, memory_context, llm, evidence, tracer, degraded
        )
        memo.ticker = t
        # what the model alone decided, before deterministic policy: evals compare it to the final call
        tracer.emit("memo_draft", "Lead Synthesizer", rating=memo.rating, conviction=memo.conviction)
        if not memory_context and memo.prior_theses_addressed:
            memo.prior_theses_addressed = ""  # model invented history; none was provided
            tracer.emit("guardrail", "Policy", name="prior_theses_stripped", detail="no prior theses existed")
        memo, adjustments = apply_policy(memo, findings, evidence)
        for note in adjustments:
            tracer.emit("guardrail", "Policy", name="policy_cap", detail=note)
        guardrails += adjustments

        position = plan_for_rating(memo.rating, risk["sizing"], equity, t)
        markdown = render_markdown(memo, findings, position, evidence, guardrails, degraded)
        usage = llm.budget.snapshot() if llm.budget else {}
        tracer.emit(
            "final", "Lead Synthesizer", rating=memo.rating, conviction=memo.conviction, markdown=markdown
        )
        result = AnalysisResult(
            tracer.run_id, t, memo, markdown, findings, position, evidence.items, guardrails, degraded, usage
        )
        tracer.emit("run_end", "system", usage=usage, degraded=degraded)
        result.events = [e.to_dict() for e in tracer.events]
        return result
    except (AllProvidersFailed, BudgetExceeded, market.DataError) as e:
        tracer.emit("error", "system", kind=type(e).__name__, message=str(e)[:400])
        raise
    finally:
        tracer.close()


async def _run_analysts(
    t: str, today: str, llm: LLMClient, box: ToolBox, evidence: Evidence, tracer: Tracer, degraded: list[str]
) -> list[Finding]:
    sem = asyncio.Semaphore(max(1, get_settings().agent_concurrency))
    specs = [
        (AgentSpec("Technical Analyst", prompts.TECHNICAL, prompts.TECH_REQUIRED), prompts.TECH_TOOLS, 1),
        (AgentSpec("Fundamental Auditor", prompts.FUNDAMENTAL, prompts.FUND_REQUIRED), prompts.FUND_TOOLS, 2),
    ]

    async def one(spec: AgentSpec, allow: list[str], namespace: int) -> Finding:
        async with sem:
            runner = ToolRunner(box, evidence, tracer, spec.name, allow, namespace)
            task = f"Analyze {t}. Today is {today}. Call your tools, then return the JSON finding."
            try:
                f = await run_agent(
                    spec,
                    task,
                    Finding,
                    llm,
                    runner,
                    tracer,
                    validator=lambda f, name=spec.name: _validate_finding(f, name, evidence),
                    tool_args={"ticker": t},
                )
                f.agent = spec.name
                tracer.emit(
                    "finding",
                    spec.name,
                    stance=f.stance,
                    confidence=f.confidence,
                    summary=f.summary,
                    claims=[c.model_dump() for c in f.claims],
                    caveats=f.caveats,
                )
                return f
            except AgentFailed as e:
                degraded.append(f"{spec.name} degraded: {e}")
                tracer.emit("agent_error", spec.name, message=str(e)[:300])
                return _insufficient(spec.name, str(e))

    return list(await asyncio.gather(*(one(s, a, n) for s, a, n in specs)))


def _validate_finding(f: Finding, agent: str, evidence: Evidence) -> list[str]:
    problems = check_claims(f.claims, evidence)
    if agent == "Technical Analyst":
        expected, why = technical_expected_stance(evidence)
        if f.stance != expected:
            problems.append(
                f"stance must follow the rubric: the evidence mandates '{expected}' ({why}); "
                f"you wrote '{f.stance}'. Set stance to '{expected}' and keep your claims."
            )
    return problems


def _fallback_memo(t: str, findings: list[Finding]) -> Memo:
    from .schemas import Claim

    def pick(stance: str) -> list[Claim]:
        cs = [c for f in findings if f.stance == stance for c in f.claims if c.evidence]
        return cs[:2] or [Claim(text="No supporting evidence was available for this side.", evidence=[])]

    return Memo(
        ticker=t,
        rating="NO_CALL",
        conviction=0.0,
        thesis="Automated synthesis could not be validated, so no rating is issued. Review the analyst views below.",
        bull_case=pick("bullish"),
        bear_case=pick("bearish"),
        key_risks=["Synthesis failed validation; rely on the individual analyst findings only."],
    )


async def _synthesize(
    t: str,
    today: str,
    findings: list[Finding],
    risk: dict[str, Any],
    memory_context: str,
    llm: LLMClient,
    evidence: Evidence,
    tracer: Tracer,
    degraded: list[str],
) -> tuple[Memo, list[str]]:
    payload = {
        "ticker": t,
        "today": today,
        "analysts": [f.model_dump() for f in findings],
        "risk_report": {
            "metrics": risk["metrics"],
            "sizing": risk["sizing"],
            "evidence_ids": [k for k, v in evidence.items.items() if v["tool"] in prompts.RISK_TOOLS],
        },
    }
    base_task = "Write the memo.\n" + json.dumps(payload, separators=(",", ":"))
    if memory_context:
        base_task += f"\nPRIOR THESES ON {t} (most recent first):\n{memory_context}"

    spec = AgentSpec("Lead Synthesizer", prompts.SYNTHESIZER, max_tokens=1600)
    tracer.emit("handoff", "system", to="Lead Synthesizer", reason="debating findings into a memo")

    async def draft(extra: str = "") -> Memo:
        return await run_agent(
            spec,
            base_task + extra,
            Memo,
            llm,
            None,
            tracer,
            validator=lambda m: check_claims(m.all_claims, evidence),
        )

    guardrails: list[str] = []
    try:
        memo = await draft()
    except AgentFailed as e:
        degraded.append(f"Synthesizer degraded: {e}")
        tracer.emit("agent_error", "Lead Synthesizer", message=str(e)[:300])
        return _fallback_memo(t, findings), guardrails

    # one critic pass; revise at most once, and only if the token budget allows it
    budget = llm.budget
    if budget is None or budget.tokens < 0.7 * budget.max_tokens:
        critic = AgentSpec("Risk Critic", prompts.CRITIC, max_tokens=500)
        try:
            review = await run_agent(
                critic,
                "Findings and draft:\n"
                + json.dumps(
                    {
                        "analysts": payload["analysts"],
                        "risk_report": payload["risk_report"],
                        "draft": memo.model_dump(),
                    },
                    separators=(",", ":"),
                ),
                Critique,
                llm,
                None,
                tracer,
            )
            tracer.emit("critique", "Risk Critic", ok=review.ok, issues=review.issues)
            if not review.ok and review.issues:
                guardrails.append("Critic raised: " + "; ".join(review.issues[:3]))
                try:
                    memo = await draft("\nREVIEWER ISSUES TO ADDRESS:\n- " + "\n- ".join(review.issues))
                except AgentFailed:
                    guardrails.append("Revision failed validation; kept the first draft.")
        except AgentFailed:
            tracer.emit("guardrail", "Risk Critic", name="critic_skipped", detail="critic output invalid")
    return memo, guardrails
