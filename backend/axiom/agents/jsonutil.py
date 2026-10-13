"""Pull one JSON object out of messy model output (fences, prose, trailing text)."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Return the first balanced JSON object found in `text`; raise ValueError if none parses."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for blob in candidates:
        start = blob.find("{")
        while start != -1:
            end = _matching_brace(blob, start)
            if end is not None:
                try:
                    return json.loads(blob[start : end + 1])
                except json.JSONDecodeError:
                    pass
            start = blob.find("{", start + 1)
    raise ValueError("no valid JSON object found in the response")


def _matching_brace(s: str, start: int) -> int | None:
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None
