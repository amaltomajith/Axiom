"""Turn a finished analysis into a reviewable action plan, or explain why none is proposed.

Gate: a directional rating (BUY/SELL family), conviction above a threshold, no risk-limit violations.
Nothing here writes anywhere; execution happens only after explicit human approval.
"""

from __future__ import annotations

from datetime import UTC, datetime

from axiom.agents.orchestrator import AnalysisResult
from axiom.config import get_settings

from .models import ActionPlan, ActionStep

DIRECTIONAL = {"STRONG_BUY", "BUY", "SELL", "STRONG_SELL"}


def propose(result: AnalysisResult, executor_name: str) -> tuple[ActionPlan | None, str]:
    """Return (plan, reason). plan is None when nothing should be proposed."""
    s = get_settings()
    m, pos = result.memo, result.position
    if m.rating not in DIRECTIONAL:
        return None, f"{m.rating}: no action proposed (only directional ratings trigger actions)."
    if m.conviction < s.action_min_conviction:
        return (
            None,
            f"Conviction {m.conviction:.0%} is below the {s.action_min_conviction:.0%} action threshold.",
        )
    if pos.violations:
        return None, "Risk limits violated: " + "; ".join(pos.violations)
    if any("Synthesizer degraded" in d for d in result.degraded):
        return None, "Synthesis degraded; refusing to act on an unvalidated memo."

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    key = lambda kind: f"{result.run_id}:{kind}"  # noqa: E731
    steps: list[ActionStep] = []

    if pos.action == "open_long" and pos.shares > 0:
        steps.append(
            ActionStep(
                kind="paper_trade",
                title=f"Record paper BUY {pos.shares} {result.ticker}",
                preview={
                    "ticker": result.ticker,
                    "side": "BUY",
                    "quantity": pos.shares,
                    "entry_price": pos.entry_reference,
                    "stop_price": pos.stop_price,
                    "risk_amount": pos.risk_amount,
                },
                idempotency_key=key("paper_trade"),
            )
        )
    steps.append(
        ActionStep(
            kind="notion_page",
            title=f"Create Notion page: {result.ticker} {m.rating} ({today})",
            preview={
                "title": f"{result.ticker} {m.rating.replace('_', ' ')}: {today}",
                "markdown": result.markdown,
            },
            idempotency_key=key("notion_page"),
        )
    )
    steps.append(
        ActionStep(
            kind="sheet_row",
            title="Append a row to the trade log sheet",
            preview={
                "columns": ["date", "ticker", "rating", "conviction", "entry", "stop", "shares", "risk_amount", "run_id"],
                "values": [today, result.ticker, m.rating, m.conviction, pos.entry_reference, pos.stop_price,
                           pos.shares, pos.risk_amount, result.run_id],
            },
            idempotency_key=key("sheet_row"),
        )
    )  # fmt: skip
    steps.append(
        ActionStep(
            kind="slack_message",
            title="Post a summary alert",
            preview={"text": _slack_text(result, today)},
            idempotency_key=key("slack_message"),
        )
    )
    return (
        ActionPlan(
            run_id=result.run_id,
            ticker=result.ticker,
            rating=m.rating,
            conviction=m.conviction,
            executor=executor_name,
            steps=steps,
        ),
        "Plan proposed; awaiting approval.",
    )


def _slack_text(r: AnalysisResult, today: str) -> str:
    m, pos = r.memo, r.position
    plan = (
        f"Long {pos.shares} @ ~${pos.entry_reference}, stop ${pos.stop_price}"
        if pos.action == "open_long"
        else pos.action.replace("_", " ")
    )
    return (
        f"*{r.ticker}: {m.rating.replace('_', ' ')}* (conviction {m.conviction:.0%}, {today})\n"
        f"{m.thesis[:300]}\nPaper plan: {plan}. Research only, not financial advice."
    )


def digest_plan(run_id: str, text: str) -> ActionPlan:
    """A read-style digest (no trades): a single Slack post, safe to auto-approve."""
    return ActionPlan(
        run_id=run_id,
        ticker="*",
        rating="DIGEST",
        conviction=0.0,
        steps=[
            ActionStep(
                kind="slack_message",
                title="Post daily briefing",
                preview={"text": text},
                idempotency_key=f"{run_id}:slack_digest",
            )
        ],
    )
