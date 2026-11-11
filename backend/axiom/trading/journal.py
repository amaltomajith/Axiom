"""The trade journal: plain-language entries in a sha256 hash chain.

Each entry's hash covers its content and the previous entry's hash, so editing, deleting or reordering any
past entry breaks `verify_chain`. The text always comes from a template over verified facts; an LLM may
rewrite it only if every number it writes appears in those facts (see `accept_rewrite`).
"""

from __future__ import annotations

import hashlib
import json
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
