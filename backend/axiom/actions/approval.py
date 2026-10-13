"""Human-in-the-loop execution: nothing runs until approve(), and each step runs at most once."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from axiom.memory.store import Store

from .executors import Executor
from .models import ActionPlan


class ActionError(Exception):
    pass


def save(store: Store, plan: ActionPlan) -> None:
    store.save_action(plan.model_dump())


def load(store: Store, plan_id: str) -> ActionPlan:
    raw = store.get_action(plan_id)
    if raw is None:
        raise ActionError(f"No such action plan {plan_id!r}")
    return ActionPlan.model_validate(raw)


def reject(store: Store, plan_id: str) -> ActionPlan:
    plan = load(store, plan_id)
    if plan.status != "proposed":
        raise ActionError(f"Plan is already {plan.status}; only proposed plans can be rejected")
    plan.status, plan.decided_at = "rejected", time.time()
    save(store, plan)
    return plan


async def approve(store: Store, plan_id: str, executor: Executor, thesis_id: str | None = None) -> ActionPlan:
    plan = load(store, plan_id)
    if plan.status != "proposed":
        raise ActionError(f"Plan is already {plan.status}; only proposed plans can be approved")

    for step in plan.steps:
        if step.status == "done":
            continue  # finished in an earlier attempt
        if not store.claim_key(step.idempotency_key, plan.id):
            step.status, step.error = "skipped", "already executed earlier (idempotency key)"
            continue
        try:
            if step.kind == "paper_trade":
                trade_id = store.add_trade(
                    {
                        "ticker": step.preview["ticker"],
                        "side": step.preview["side"],
                        "quantity": step.preview["quantity"],
                        "entry_price": step.preview["entry_price"],
                        "entry_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                        "thesis_id": thesis_id,
                    }
                )
                step.status, step.result = "done", {"trade_id": trade_id}
            else:
                res = await executor.run(step)
                step.status = "done" if res.ok else "failed"
                step.result, step.error = res.data, res.error
        except Exception as e:  # never leave a claimed key behind for a step that did not complete
            step.status, step.error = "failed", f"{type(e).__name__}: {e}"[:300]
        if step.status == "failed":
            store.release_key(step.idempotency_key)  # allow a retry of just this step

    statuses = {s.status for s in plan.steps}
    if statuses <= {"done", "skipped"}:
        plan.status = "executed"
    elif "done" in statuses:
        plan.status = "partial"
    else:
        plan.status = "failed"
    plan.decided_at = time.time()
    plan.result = {"executor": executor.name}
    save(store, plan)
    return plan


async def retry_failed(
    store: Store, plan_id: str, executor: Executor, thesis_id: str | None = None
) -> ActionPlan:
    """Re-run only failed steps of a partial/failed plan (done steps are protected by their keys)."""
    plan = load(store, plan_id)
    if plan.status not in ("partial", "failed"):
        raise ActionError(f"Plan is {plan.status}; nothing to retry")
    for step in plan.steps:
        if step.status == "failed":
            step.status, step.error = "pending", None
    plan.status = "proposed"
    save(store, plan)
    return await approve(store, plan_id, executor, thesis_id)
