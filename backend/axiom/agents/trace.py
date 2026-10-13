"""Trace events: the observable record of a run (streamed to the UI over SSE and stored with the memo).

We trace *actions and structured outputs* (tool calls, results, findings, guardrail decisions), not the
model's private chain-of-thought.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from axiom.llm.types import TraceFn


@dataclass
class TraceEvent:
    seq: int
    ts: float
    run_id: str
    type: str
    agent: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Tracer:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    events: list[TraceEvent] = field(default_factory=list)
    queue: asyncio.Queue[TraceEvent | None] | None = None
    _seq: int = 0

    def emit(self, type_: str, agent: str = "system", **data: Any) -> TraceEvent:
        self._seq += 1
        ev = TraceEvent(self._seq, time.time(), self.run_id, type_, agent, data)
        self.events.append(ev)
        if self.queue is not None:
            self.queue.put_nowait(ev)
        return ev

    def sink(self, agent: str) -> TraceFn:
        """Adapter handed to the LLM client so its events are attributed to an agent."""
        return lambda type_, data: self.emit(type_, agent, **data)

    def close(self) -> None:
        if self.queue is not None:
            self.queue.put_nowait(None)
