"""Faithfulness gate: every claim must cite real evidence and every number must be traceable to it.

This is deliberately mechanical (no LLM judge): numbers in a claim must appear, within rounding
tolerance, in the tool results it cites. Unit forms are normalised ($, %, K/M/B/T suffixes, and
fraction<->percent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import Claim

# Window specs such as "50-day", "14 days", "1 year" are labels, not data claims, so they are skipped.
_WINDOW = r"(?!\s?-?\s?(?:day|days|week|weeks|month|months|year|years|period|bar|bars|session|sessions)\b)"
_NUM = re.compile(
    r"(?<![\w.])(?<![A-Za-z]-)[-+]?\$?\d[\d,]*+(?:\.\d+)?+"
    + _WINDOW
    + r"\s?(?:%|percent\b|[kKmMbBtT](?:illion|n)?\b)?"
)
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


def parse_numbers(text: str) -> list[tuple[float, int, bool, str]]:
    """Return (value, decimals, is_percent, raw_token) for each number in text."""
    out = []
    for m in _NUM.finditer(text):
        raw = m.group(0).strip()
        pct = raw.endswith("%") or raw.endswith("percent")
        body = raw.removesuffix("percent").rstrip("% ").replace("$", "").replace(",", "").strip()
        mult = 1.0
        suffix = re.search(r"([kKmMbBtT])(?:illion|n)?$", body)
        if suffix:
            mult = _SUFFIX[suffix.group(1).lower()]
            body = body[: suffix.start()].strip()
        try:
            val = float(body) * mult
        except ValueError:
            continue
        decimals = len(body.split(".")[1]) if "." in body else 0
        out.append((val, decimals, pct, raw))
    return out


def _is_year(val: float, decimals: int) -> bool:
    return decimals == 0 and 1900 <= val <= 2100


def _matches(claim_val: float, decimals: int, pct: bool, evidence: list[float]) -> bool:
    """Compare in the claim's own unit. A percentage claim may match an evidence value already in
    percent (6.4) or stored as a fraction (0.064). Tolerance is the claim's rounding precision, or 1%
    relative (for suffix-rounded magnitudes such as $416.2B)."""
    tol_abs = 0.5 * 10**-decimals + 1e-9
    for ev in evidence:
        for form in (ev, ev * 100) if pct else (ev,):
            if abs(claim_val - form) <= tol_abs:
                return True
            if claim_val != 0 and abs(claim_val - form) / abs(claim_val) <= 0.01:
                return True
    return False


@dataclass
class Evidence:
    """Registry of tool results for one run.

    Ids are deterministic even though agents run concurrently: each agent gets its own block
    (namespace 1 -> T101, T102...; namespace 2 -> T201...; namespace 0 -> T1, T2...), and an id is
    reserved *when the call starts* (call order), never when it finishes (completion order, which is a race).
    Deterministic ids make prompts reproducible, which is what lets recorded evals replay exactly.
    """

    items: dict[str, dict] = field(default_factory=dict)
    _counts: dict[int, int] = field(default_factory=dict)

    def reserve(self, tool: str, args: dict, namespace: int = 0) -> str:
        n = self._counts.get(namespace, 0) + 1
        self._counts[namespace] = n
        eid = f"T{namespace * 100 + n}"
        self.items[eid] = {"id": eid, "tool": tool, "args": args, "text": ""}
        return eid

    def fill(self, eid: str, text: str) -> None:
        self.items[eid]["text"] = text

    def discard(self, eid: str) -> None:
        self.items.pop(eid, None)

    def add(self, tool: str, args: dict, text: str, namespace: int = 0) -> str:
        eid = self.reserve(tool, args, namespace)
        self.fill(eid, text)
        return eid

    def numbers(self, eid: str) -> list[float]:
        text = self.items[eid]["text"]
        return [v for v, *_ in parse_numbers(text)]


def _block(eid: str) -> int:
    """The agent id-block an evidence id belongs to (T101 -> 1, T205 -> 2, T3 -> 0)."""
    return int(eid[1:]) // 100 if eid[1:].isdigit() else -1


def _same_block(evidence: Evidence, cited: list[str]) -> list[str]:
    """Ids from the cited evidence's own block only. Repair hints must not depend on what a *concurrent*
    agent has gathered so far, or the same run would produce different prompts depending on timing."""
    blocks = {_block(e) for e in cited}
    return sorted((k for k in evidence.items if _block(k) in blocks), key=lambda k: int(k[1:]))


def check_claim(claim: Claim, evidence: Evidence) -> list[str]:
    problems = []
    if not claim.evidence:
        return [f"no evidence cited for: {claim.text[:70]!r}"]
    unknown = [e for e in claim.evidence if e not in evidence.items]
    if unknown:
        return [
            f"unknown evidence id(s) {unknown} (valid: {_same_block(evidence, claim.evidence) or 'none'})"
        ]
    pool = [n for e in claim.evidence for n in evidence.numbers(e)]
    for val, decimals, pct, raw in parse_numbers(claim.text):
        if _is_year(val, decimals):
            continue
        if not _matches(val, decimals, pct, pool):
            # help the model fix it: say where the number actually appears, if anywhere
            elsewhere = [
                f"{eid} ({evidence.items[eid]['tool']})"
                for eid in _same_block(evidence, claim.evidence)
                if eid not in claim.evidence and _matches(val, decimals, pct, evidence.numbers(eid))
            ]
            hint = (
                f"; that figure appears in {', '.join(elsewhere)}: cite the correct evidence id"
                if elsewhere
                else "; it appears in no tool result, so remove or correct it"
            )
            problems.append(
                f"number {raw.strip()!r} not found in cited evidence {claim.evidence}{hint}: {claim.text[:70]!r}"
            )
    return problems


def check_claims(claims: list[Claim], evidence: Evidence) -> list[str]:
    return [p for c in claims for p in check_claim(c, evidence)]
