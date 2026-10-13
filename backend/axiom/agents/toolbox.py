"""Agents reach the world only through MCP tools. This module is the MCP client side.

`McpToolBox` speaks plain MCP (list_tools / call_tool), so the same agent code runs against the
in-process Axiom server (dev/tests), a stdio subprocess, or a remote streamable-HTTP server.
`ToolRunner` adds per-agent allowlists, evidence ids, truncation, timeouts and tracing.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Protocol

from mcp import ClientSession

from .faithfulness import Evidence
from .trace import Tracer

MAX_RESULT_CHARS = 6000
TOOL_TIMEOUT = 90.0


@contextmanager
def _unwrap_single_error() -> Iterator[None]:
    """anyio task groups wrap errors in an ExceptionGroup; callers want the real exception
    (e.g. BudgetExceeded), so unwrap groups that carry exactly one."""
    try:
        yield
    except BaseExceptionGroup as eg:
        inner: BaseException = eg
        while isinstance(inner, BaseExceptionGroup) and len(inner.exceptions) == 1:
            inner = inner.exceptions[0]
        if inner is eg:
            raise
        raise inner from None


class ToolBox(Protocol):
    async def specs(self) -> list[dict[str, Any]]: ...
    async def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]: ...


def _trim_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop noise (titles) that wastes tokens on small models."""
    out = {k: v for k, v in schema.items() if k != "title"}
    if "properties" in out:
        out["properties"] = {
            n: _trim_schema(p) if isinstance(p, dict) else p for n, p in out["properties"].items()
        }
    return out


class McpToolBox:
    def __init__(self, session: ClientSession):
        self.session = session
        self._specs: list[dict[str, Any]] | None = None

    async def specs(self) -> list[dict[str, Any]]:
        if self._specs is None:
            tools = (await self.session.list_tools()).tools
            self._specs = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        # cleandoc: Python 3.13 strips docstring indentation at compile time and 3.12 does not,
                        # so without it the prompt (and every recorded eval) would differ per interpreter.
                        "description": inspect.cleandoc(t.description or "").split("\n\n")[0],
                        "parameters": _trim_schema(t.inputSchema),
                    },
                }
                for t in tools
            ]
        return self._specs

    async def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        res = await self.session.call_tool(name, args)
        text = "\n".join(getattr(c, "text", "") for c in res.content)
        return text, not res.isError

    # -- constructors -----------------------------------------------------------------

    @classmethod
    @asynccontextmanager
    async def inprocess(cls) -> AsyncIterator[McpToolBox]:
        """Connect to the Axiom MCP server running in this process (still full MCP protocol)."""
        from mcp.shared.memory import create_connected_server_and_client_session

        from axiom.mcp_server.server import mcp

        with _unwrap_single_error():
            async with create_connected_server_and_client_session(mcp._mcp_server) as session:
                yield cls(session)

    @classmethod
    @asynccontextmanager
    async def http(cls, url: str) -> AsyncIterator[McpToolBox]:
        from mcp.client.streamable_http import streamablehttp_client

        with _unwrap_single_error():
            async with streamablehttp_client(url) as (read, write, _), ClientSession(read, write) as session:
                await session.initialize()
                yield cls(session)


class ToolRunner:
    """One agent's view of the toolbox: allowlisted, evidence-recording and traced."""

    def __init__(
        self,
        box: ToolBox,
        evidence: Evidence,
        tracer: Tracer,
        agent: str,
        allow: list[str],
        namespace: int = 0,
    ):
        self.box, self.evidence, self.tracer, self.agent, self.allow = box, evidence, tracer, agent, allow
        self.namespace = namespace
        self.called: list[str] = []

    async def specs(self) -> list[dict[str, Any]]:
        return [s for s in await self.box.specs() if s["function"]["name"] in self.allow]

    async def run(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool and return the text the LLM will see (prefixed with its evidence id)."""
        if name not in self.allow:
            self.tracer.emit("guardrail", self.agent, name="tool_not_allowed", detail=f"{name} blocked")
            return f"ERROR: tool {name!r} is not available to you. Available: {self.allow}"
        if "__error__" in args:
            return f"ERROR: could not parse tool arguments ({args['__error__']}). Send valid JSON."
        self.tracer.emit("tool_call", self.agent, tool=name, args=args)
        eid = self.evidence.reserve(name, args, self.namespace)  # call order, not completion order
        t0 = time.monotonic()
        try:
            text, ok = await asyncio.wait_for(self.box.call(name, args), TOOL_TIMEOUT)
        except TimeoutError:
            text, ok = f"tool timed out after {TOOL_TIMEOUT:.0f}s", False
        except Exception as e:  # transport-level failure
            text, ok = f"tool call failed: {type(e).__name__}: {e}", False
        ms = int((time.monotonic() - t0) * 1000)
        self.called.append(name)

        if not ok:
            self.evidence.discard(eid)
            self.tracer.emit(
                "tool_result", self.agent, tool=name, ok=False, latency_ms=ms, preview=text[:300]
            )
            return f"ERROR from {name}: {text[:500]}"

        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + '..."[truncated]"'
        self.evidence.fill(eid, text)
        self.tracer.emit(
            "tool_result",
            self.agent,
            tool=name,
            ok=True,
            evidence_id=eid,
            latency_ms=ms,
            chars=len(text),
            preview=_preview(text),
        )
        return f"[evidence_id={eid} tool={name}]\n{text}"


def _preview(text: str) -> str:
    try:
        body = json.loads(text)
        meta = body.get("meta", {}) if isinstance(body, dict) else {}
        keys = ", ".join(list(body)[:6]) if isinstance(body, dict) else ""
        return f"{meta.get('ticker', '')} as_of={meta.get('as_of', '')} provider={meta.get('provider', '')} keys=[{keys}]"
    except (json.JSONDecodeError, AttributeError):
        return text[:200]
