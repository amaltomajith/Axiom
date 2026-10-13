"""Capture the REAL data the landing page shows (no mock numbers).

    uv run python scripts/capture_snapshot.py            # backend must be running on :8000

Writes ../src/landing/snapshot.json from:
  * the most recent stored analysis run (memo, evidence, trace events), prices, forecast cone, a backtest;
  * a real approval payload built by the action planner from the eval suite's positive-control run (replayed
    from the committed recording, fictional ticker ACME), so the page can show exactly what an approval
    request contains;
  * the headline numbers parsed from docs/eval-report.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "src" / "landing" / "snapshot.json"
API = os.environ.get("AXIOM_API", "http://localhost:8000")

os.environ.setdefault("CACHE_DB", str(Path(tempfile.mkdtemp()) / "snap.db"))
os.environ.setdefault("LLM_CHAIN", "ollama")
sys.path.insert(0, str(ROOT / "backend"))


def eval_numbers() -> dict:
    text = (ROOT / "docs" / "eval-report.md").read_text(encoding="utf-8")

    def cell(label: str) -> str:
        m = re.search(rf"\|\s*{re.escape(label)}[^|]*\|\s*([^|]+?)\s*\|", text)
        return m.group(1).strip("* ") if m else ""

    cases = []
    for line in text.splitlines():
        m = re.match(
            r"\|\s*(random_walk|conflict|thin_data|earned_edge|inj_direct\+bypass)\s*\|\s*[^|]*\|\s*([^|]+?)\s*\|",
            line,
        )
        if m:
            cases.append({"name": m.group(1), "rating": m.group(2).replace("→", "to")})
    return {
        "passed": cell("Cases passed"),
        "honesty": cell("Honesty scenarios passed"),
        "injection": cell("Injection cases passed (final output)"),
        "draft_resisted": cell("Injection, sanitizer bypassed: model's own draft avoided STRONG_BUY"),
        "control_obeyed": cell("**Control** (no defences, bare prompt): model obeyed the injection")
        or cell("Control"),
        "judge": cell("Judge-supported memo claims"),
        "cases": cases,
    }


async def approval_payload() -> dict:
    """Run the eval's positive-control case in replay mode and ask the real planner for its action plan."""
    from axiom.actions.planner import propose
    from axiom.agents.orchestrator import analyze
    from axiom.agents.toolbox import McpToolBox
    from axiom.agents.trace import Tracer
    from axiom.llm.client import TokenBudget
    from evals.recording import RecordingLLM
    from evals.scenarios import SCENARIOS, TICKER, world

    llm = RecordingLLM(
        ROOT / "backend" / "evals" / "recordings" / "qwen3-8b.jsonl", "replay", TokenBudget(10**6, 100)
    )
    with world(SCENARIOS["earned_edge"]):
        async with McpToolBox.inprocess() as box:
            result = await analyze(TICKER, llm=llm, box=box, tracer=Tracer())
    plan, why = propose(result, "dry_run")
    return {
        "source": "Eval suite positive control (fictional ticker ACME), replayed from the committed recording",
        "reason": why,
        "rating": result.memo.rating,
        "plan": plan.model_dump() if plan else None,
    }


def trim_events(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        d = dict(e["data"])
        d.pop("markdown", None)
        out.append({**e, "data": d})
    return out


async def main() -> None:
    async with httpx.AsyncClient(timeout=120) as c:
        runs = (await c.get(f"{API}/api/runs?limit=20")).json()
        run = next((r for r in runs if r.get("rating")), None)
        if not run:
            sys.exit("No stored analysis run yet. Run an analysis in the app first, then re-run this script.")
        detail = (await c.get(f"{API}/api/runs/{run['run_id']}")).json()
        ticker = run["ticker"]
        bars = (await c.get(f"{API}/api/market/{ticker}/ohlcv?bars=90")).json()
        forecast = (await c.get(f"{API}/api/quant/{ticker}/forecast?horizon=14")).json()
        backtest = (await c.get(f"{API}/api/quant/{ticker}/backtest?strategy=sma_cross")).json()
        scorecard = (await c.get(f"{API}/api/scorecard")).json()

    result = detail["result"]
    snapshot = {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "ticker": ticker,
        "provider": bars["provider"],
        "bars": bars["bars"],
        "cone": forecast.get("cone"),
        "calibration": forecast.get("calibration"),
        "result": {
            k: result[k]
            for k in ("memo", "findings", "position", "evidence", "guardrails", "degraded", "usage")
        },
        "events": trim_events(detail["events"]),
        "backtest": {
            k: backtest[k]
            for k in (
                "strategy",
                "metrics",
                "benchmark_metrics",
                "verdict",
                "message",
                "sharpe_diff",
                "sharpe_diff_ci95",
                "equity_curve",
                "assumptions",
            )
        },
        "scorecard": {k: scorecard[k] for k in ("n_scored", "n_pending", "sufficient_sample", "sample_note")},
        "approval": await approval_payload(),
        "evals": eval_numbers(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {ticker} {result['memo']['rating']}, {len(snapshot['events'])} events"
    )
    print("evals:", json.dumps(snapshot["evals"], ensure_ascii=False)[:400])


if __name__ == "__main__":
    asyncio.run(main())
