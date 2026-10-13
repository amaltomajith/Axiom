"""LLM-as-judge for *semantic* faithfulness: does the cited evidence actually say what the claim says?

The mechanical checker in axiom.agents.faithfulness proves every number exists in the cited tool result.
It cannot tell that "net margin was 22.7% last year" borrowed 22.7 from an EPS growth field. A judge can.
Caveat (stated in the report): the judge is the same free model family as the agents, so it is a noisy,
somewhat self-favouring signal, useful for trends and regressions, not an absolute truth.
"""

from __future__ import annotations

from typing import Any

from axiom.agents.jsonutil import extract_json
from axiom.llm.client import LLMClient

SYSTEM = """You verify claims against evidence. For each numbered claim, decide whether EVERY factual
statement in it is directly supported by the evidence JSON shown for it: numbers must match AND refer to the
same quantity the claim describes (for example a revenue growth figure must not be used as a margin).
Reply ONLY with JSON: {"verdicts": [{"id": 1, "supported": true, "reason": "short"}]}"""


async def judge_claims(llm: LLMClient, items: list[dict[str, str]]) -> list[bool | None]:
    """items: [{claim, evidence}] -> supported flag per item (None if the judge failed to answer)."""
    if not items:
        return []
    body = "\n\n".join(
        f"CLAIM {i + 1}: {it['claim']}\nEVIDENCE {i + 1}: {it['evidence'][:1500]}"
        for i, it in enumerate(items)
    )
    res = await llm.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}],
        temperature=0.0,
        max_tokens=900,
        label="judge",
    )
    try:
        verdicts: list[dict[str, Any]] = extract_json(res.content)["verdicts"]
    except (ValueError, KeyError, TypeError):
        return [None] * len(items)
    by_id = {int(v.get("id", 0)): v.get("supported") for v in verdicts if isinstance(v, dict)}
    return [by_id.get(i + 1) if isinstance(by_id.get(i + 1), bool) else None for i in range(len(items))]
