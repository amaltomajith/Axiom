"""The trade journal: plain-language entries in a sha256 hash chain.

Each entry's hash covers its content and the previous entry's hash, so editing, deleting or reordering any
past entry breaks `verify_chain`. The text always comes from a template over verified facts; an LLM may
rewrite it only if every number it writes appears in those facts (see `accept_rewrite`).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import JournalEntry

GENESIS = "0" * 64


def entry_hash(e: JournalEntry) -> str:
    body = json.dumps(
        {"session": e.session, "seq": e.seq, "ts": round(e.ts, 3), "kind": e.kind, "symbol": e.symbol,
         "text": e.text, "facts": e.facts, "prev": e.prev_hash},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )  # fmt: skip
    return hashlib.sha256(body.encode()).hexdigest()


def seal(e: JournalEntry, prev_hash: str) -> JournalEntry:
    e.prev_hash = prev_hash
    e.hash = entry_hash(e)
    return e


def verify_chain(entries: list[JournalEntry]) -> dict[str, Any]:
    """Recompute every hash in order. Returns ok plus the first broken sequence number, if any."""
    prev = GENESIS
    for i, e in enumerate(sorted(entries, key=lambda x: x.seq)):
        if e.seq != i + 1:
            return {"ok": False, "n": len(entries), "broken_at": e.seq, "why": f"sequence gap before {e.seq}"}
        if e.prev_hash != prev:
            return {
                "ok": False,
                "n": len(entries),
                "broken_at": e.seq,
                "why": "link to the previous entry broken",
            }
        if entry_hash(e) != e.hash:
            return {"ok": False, "n": len(entries), "broken_at": e.seq, "why": "entry content was changed"}
        prev = e.hash
    return {"ok": True, "n": len(entries), "broken_at": None, "head": prev}


# ------------------------------------------------------------- LLM rewrites
def _numbers_in(value: Any) -> list[float]:
    """Every number reachable in a facts structure, plus the numbers written in any strings inside it."""
    from axiom.agents.faithfulness import parse_numbers

    out: list[float] = []
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, int | float):
        out.append(float(value))
    elif isinstance(value, str):
        out.extend(v for v, *_ in parse_numbers(value))
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_numbers_in(v))
    elif isinstance(value, list | tuple):
        for v in value:
            out.extend(_numbers_in(v))
    return out


def _supported(val: float, decimals: int, pct: bool, evidence: list[float]) -> bool:
    tol = 0.5 * 10**-decimals + 1e-9
    for ev in evidence:
        for form in (ev, ev * 100, abs(ev), abs(ev) * 100) if pct else (ev, abs(ev)):
            if abs(abs(val) - form) <= tol or (val and abs(abs(val) - form) / abs(val) <= 0.01):
                return True
    return False


def unsupported_numbers(text: str, *sources: Any) -> list[str]:
    """Number tokens in `text` that appear nowhere in `sources` (facts dicts, template strings, values).
    Years are ignored; everything else must match within its written precision or 1%."""
    from axiom.agents.faithfulness import parse_numbers

    evidence: list[float] = []
    for s in sources:
        evidence.extend(_numbers_in(s))
    bad = []
    for val, decimals, pct, raw in parse_numbers(text):
        if decimals == 0 and 1900 <= val <= 2100:
            continue
        if not _supported(val, decimals, pct, evidence):
            bad.append(raw)
    return bad


EM_DASH = chr(0x2014)
HYPHENS = "[" + chr(0x2010) + "-" + chr(0x2013) + "]"


def accept_rewrite(
    template: str, rewrite: str | None, facts: dict, *, max_len: int = 900
) -> tuple[str, bool, list[str]]:
    """Use an LLM's rewrite of a journal entry only if every number in it is in the facts or the template.
    Returns (text, accepted, unsupported_numbers). On any doubt the template wins."""
    if not rewrite or not rewrite.strip():
        return template, False, []
    text = re.sub(r"\s*" + EM_DASH + r"\s*", ", ", rewrite)  # the UI copy rule forbids it
    text = re.sub(HYPHENS, "-", text)  # hyphen variants and the en dash
    text = " ".join(text.split())
    if len(text) > max_len:
        return template, False, []
    bad = unsupported_numbers(text, facts, template)
    if bad:
        return template, False, bad
    return text, True, []
