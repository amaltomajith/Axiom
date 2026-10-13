"""The agent loop: tool-calling turns, then a validated structured answer.

Robustness for small/free models is built in rather than hoped for:
* a model that answers without calling any tool is nudged once;
* any `required_tools` it never called are fetched deterministically ("prefetch") and shown to it as
  if it had called them, so the final answer is always grounded;
* the final JSON is validated against a Pydantic schema plus an optional semantic validator
  (faithfulness) with a bounded number of repair rounds.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from axiom.llm.client import LLMClient
from axiom.llm.types import LLMError

from .jsonutil import extract_json
from .toolbox import ToolRunner
from .trace import Tracer

T = TypeVar("T", bound=BaseModel)
Validator = Callable[[Any], list[str]]


@dataclass
class AgentSpec:
    name: str
    system: str
    required_tools: list[str] = field(default_factory=list)
    max_steps: int = 6
    max_repairs: int = 2
    temperature: float = 0.2
    max_tokens: int = 1400


class AgentFailed(LLMError):
    pass


async def run_agent(
    spec: AgentSpec,
    task: str,
    schema: type[T],
    llm: LLMClient,
    tools: ToolRunner | None,
    tracer: Tracer,
    *,
    validator: Validator | None = None,
    tool_args: dict[str, Any] | None = None,
) -> T:
    """Run one agent to a validated `schema` instance. `tool_args` are the default args used when a
    required tool has to be prefetched (e.g. {"ticker": "AAPL"})."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": spec.system},
        {"role": "user", "content": task},
    ]
    tool_specs = await tools.specs() if tools else None
    tracer.emit(
        "agent_start", spec.name, task=task[:300], tools=[s["function"]["name"] for s in tool_specs or []]
    )
    sink = tracer.sink(spec.name)
    nudged = prefetched = False
    repairs = 0
    step = 0
    max_tokens = spec.max_tokens

    while True:
        step += 1
        force_final = step > spec.max_steps
        res = await llm.chat(
            messages,
            tools=None if force_final else tool_specs,
            temperature=spec.temperature,
            max_tokens=max_tokens,
            trace=sink,
            label=f"{spec.name}:step{step}",
        )

        if res.tool_calls and tools and not force_final:
            messages.append(res.assistant_message())
            outputs = await asyncio.gather(*(tools.run(tc.name, tc.arguments) for tc in res.tool_calls))
            for tc, out in zip(res.tool_calls, outputs, strict=True):
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
            continue

        # ---- the model wants to answer
        if tools and spec.required_tools:
            if not tools.called and not nudged:
                nudged = True
                tracer.emit(
                    "guardrail",
                    spec.name,
                    name="no_tool_use_nudge",
                    detail="answered before calling any tool",
                )
                messages += [res.assistant_message(), _nudge(spec)]
                continue
            missing = [t for t in spec.required_tools if t not in tools.called]
            if missing and not prefetched:
                prefetched = True
                tracer.emit(
                    "guardrail", spec.name, name="required_tool_prefetch", detail=f"fetching {missing}"
                )
                messages += await _prefetch(missing, tools, tool_args or {})
                continue

        try:
            obj = schema.model_validate(extract_json(res.content))
            problems = validator(obj) if validator else []
        except (ValueError, ValidationError) as e:
            problems = [_describe(e)]
            obj = None

        if obj is not None and not problems:
            tracer.emit("agent_done", spec.name, steps=step, tools_called=tools.called if tools else [])
            return obj

        if res.finish_reason == "length":
            # cut off mid-answer (often a reasoning model spending its budget thinking): retry with more room
            max_tokens = min(max_tokens * 2, 4000)
            problems = [
                f"output was cut off at the token limit; keep it concise ({'; '.join(problems)[:120]})"
            ]
        repairs += 1
        tracer.emit(
            "guardrail", spec.name, name="output_repair", detail="; ".join(problems)[:400], attempt=repairs
        )
        if repairs > spec.max_repairs:
            raise AgentFailed(f"{spec.name} could not produce valid output: {'; '.join(problems)[:300]}")
        messages += [
            res.assistant_message(),
            {
                "role": "user",
                "content": "Your answer was rejected:\n- "
                + "\n- ".join(problems)
                + f"\nReturn ONLY the corrected JSON object for the {schema.__name__} schema.",
            },
        ]


def _nudge(spec: AgentSpec) -> dict[str, Any]:
    return {
        "role": "user",
        "content": (
            "You have not called any tools yet. You must gather evidence with tools before answering. "
            f"Call these now: {', '.join(spec.required_tools)}."
        ),
    }


async def _prefetch(missing: list[str], tools: ToolRunner, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the missing tools ourselves and splice them into the transcript as a valid tool exchange."""
    outs = await asyncio.gather(*(tools.run(name, dict(args)) for name in missing))
    calls = [
        {"id": f"prefetch_{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(args)}}
        for i, n in enumerate(missing)
    ]
    msgs: list[dict[str, Any]] = [{"role": "assistant", "content": "", "tool_calls": calls}]
    msgs += [
        {"role": "tool", "tool_call_id": c["id"], "content": o} for c, o in zip(calls, outs, strict=True)
    ]
    msgs.append(
        {"role": "user", "content": "Those tool results are now available. Produce your final JSON answer."}
    )
    return msgs


def _describe(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "schema errors: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5]
        )
    return str(e)
