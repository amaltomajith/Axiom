from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

StepKind = Literal["paper_trade", "notion_page", "sheet_row", "slack_message"]
StepStatus = Literal["pending", "done", "failed", "skipped"]
PlanStatus = Literal["proposed", "executed", "partial", "failed", "rejected"]


class ActionStep(BaseModel):
    kind: StepKind
    title: str
    preview: dict[str, Any]  # exactly what will be written; shown to the user before approval
    idempotency_key: str
    status: StepStatus = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None


class ActionPlan(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    run_id: str
    ticker: str
    created_at: float = Field(default_factory=time.time)
    status: PlanStatus = "proposed"
    rating: str
    conviction: float
    executor: str = "dry_run"  # dry_run | composio: tells the user whether anything will really be written
    steps: list[ActionStep]
    decided_at: float | None = None
    result: dict[str, Any] | None = None
