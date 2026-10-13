"""Render a memo as Markdown with [T#] citation markers and an evidence index."""

from __future__ import annotations

import json

from .faithfulness import Evidence
from .schemas import Claim, Finding, Memo, PositionPlan

DISCLAIMER = (
    "*Research tooling output, not financial advice. Based on daily bars and public filings; "
    "past performance and backtests do not predict future results.*"
)


def _cite(c: Claim) -> str:
    refs = " ".join(f"[{e}]" for e in c.evidence)
    return f"- {c.text} {refs}".rstrip()


def _evidence_rows(evidence: Evidence, used: set[str]) -> list[str]:
    rows = ["| Ref | Tool | As of | Source |", "|---|---|---|---|"]
    for eid in sorted(used, key=lambda x: int(x[1:])):
        item = evidence.items.get(eid)
        if not item:
            continue
        as_of = provider = ""
        try:
            meta = json.loads(item["text"]).get("meta", {})
            as_of, provider = meta.get("as_of", ""), meta.get("provider", "")
        except (json.JSONDecodeError, AttributeError):
            pass
        rows.append(f"| {eid} | `{item['tool']}` | {as_of} | {provider} |")
    return rows


def render_markdown(
    memo: Memo,
    findings: list[Finding],
    position: PositionPlan,
    evidence: Evidence,
    guardrails: list[str],
    degraded: list[str],
) -> str:
    used = {e for c in memo.all_claims for e in c.evidence}
    out = [
        f"# {memo.ticker}: {memo.rating.replace('_', ' ').title()}",
        f"**Conviction:** {memo.conviction:.0%}. **Horizon:** {memo.horizon_days} days.",
        "",
        memo.thesis,
        "",
        "## Bull case",
        *[_cite(c) for c in memo.bull_case],
        "",
        "## Bear case",
        *[_cite(c) for c in memo.bear_case],
        "",
        "## Key risks",
        *[f"- {r}" for r in memo.key_risks],
    ]
    if memo.what_would_change_my_mind:
        out += ["", "## What would change my mind", *[f"- {r}" for r in memo.what_would_change_my_mind]]
    if memo.prior_theses_addressed:
        out += ["", "## Prior theses", memo.prior_theses_addressed]

    out += ["", "## Analyst views"]
    for f in findings:
        out.append(f"- **{f.agent}**, {f.stance} ({f.confidence:.0%}): {f.summary}")

    out += ["", "## Position plan (paper)"]
    if position.action == "open_long":
        out.append(
            f"- Long {position.shares} shares near ${position.entry_reference}, stop ${position.stop_price}, "
            f"risk ${position.risk_amount} ({position.position_pct:.1%} of equity)."
        )
    else:
        out.append(f"- {position.action.replace('_', ' ').capitalize()}.")
    out += [f"- {n}" for n in position.notes]
    out += [f"- ⚠ {v}" for v in position.violations]

    if guardrails or degraded:
        out += ["", "## Guardrails applied", *[f"- {g}" for g in [*guardrails, *degraded]]]
    out += ["", "## Evidence", *_evidence_rows(evidence, used), "", DISCLAIMER]
    return "\n".join(out)
