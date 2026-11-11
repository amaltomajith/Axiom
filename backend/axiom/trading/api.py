"""HTTP routes for the Autopilot under /api/trader. Reads are public; every POST needs control rights.

Control rights: with `AXIOM_API_TOKEN` set, a POST must send `Authorization: Bearer <token>`. With no token
configured, a POST is allowed only from this machine directly: a loopback peer and no proxy or tunnel headers
(a Cloudflare quick tunnel also connects from loopback, but adds `cf-connecting-ip`). So a laptop demo works
out of the box, and a public URL is read-only until a token is set.

Guest actions: with `TRADER_GUEST_ACTIONS=true`, anyone may also play one of the named scenarios and ask the
desk for a review. A scenario runs on the simulator and a review orders nothing (it is capped per hour), so
neither can touch the broker. Everything else still needs control rights.
"""

from __future__ import annotations

import asyncio
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from axiom.config import get_settings

from . import scenarios
from .service import TraderService

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
FORWARD_HEADERS = ("cf-connecting-ip", "x-forwarded-for", "forwarded", "x-real-ip", "cf-ray")
SESSION = Query("live", pattern=r"^(live|replay:[A-Za-z0-9_-]{1,40})$")


def require_control(request: Request) -> None:
    token = get_settings().api_token
    if token:
        sent = request.headers.get("authorization", "")
        if not hmac.compare_digest(sent.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "Missing or invalid API token")
        return
    peer = request.client.host if request.client else ""
    if peer in LOOPBACK and not any(h in request.headers for h in FORWARD_HEADERS):
        return
    raise HTTPException(403, "Set AXIOM_API_TOKEN to control the trader from another machine")


def control_or_guest(request: Request) -> bool:
    """True with full control rights, False for a guest when guest actions are on; otherwise refuse."""
    try:
        require_control(request)
        return True
    except HTTPException:
        if get_settings().trader_guest_actions:
            return False
        raise


class KillIn(BaseModel):
    reason: str = Field("a human pressed the kill switch", max_length=200)


class AutonomyIn(BaseModel):
    level: str = Field(pattern="^(SHADOW|SUPERVISED|AUTONOMOUS)$")
    lock: bool = True


class ReviewIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)


class ReplayIn(BaseModel):
    symbols: list[str] | None = Field(default=None, max_length=12)
    bars: int = Field(1000, ge=300, le=3000)
    delay: float = Field(0.0, ge=0.0, le=0.5)  # seconds per bar: 0 is as fast as possible
    scenario: str | None = Field(default=None, pattern="^(breakout|flash_crash|trojan_headline)$")


def build_router(svc: TraderService) -> APIRouter:
    r = APIRouter(prefix="/api/trader", tags=["trader"])
    ctl = [Depends(require_control)]

    def guard(fn):
        """Map service errors to HTTP codes."""

        async def run(*a, **kw):
            try:
                out = fn(*a, **kw)
                return await out if asyncio.iscoroutine(out) else out
            except KeyError as e:
                raise HTTPException(404, f"Not found: {e}") from e
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
            except RuntimeError as e:
                raise HTTPException(409, str(e)) from e

        return run

    # ------------------------------------------------------------ reads
    @r.get("/status")
    async def status():
        return await svc.status()

    @r.get("/positions")
    async def positions():
        return await guard(svc.positions)()

    @r.get("/orders")
    async def orders(session: str = SESSION, limit: int = Query(200, ge=1, le=1000)):
        return await guard(lambda: svc.ledger(session).orders(limit))()

    @r.get("/journal")
    async def journal(
        session: str = SESSION, limit: int = Query(200, ge=1, le=2000), after_seq: int = Query(0, ge=0)
    ):
        return await guard(svc.journal)(session, limit, after_seq)

    @r.get("/journal/verify")
    async def journal_verify(session: str = SESSION):
        return await guard(svc.verify)(session)

    @r.get("/contracts")
    async def contracts(
        session: str = SESSION, status: str | None = Query(None, pattern="^(open|graded|cancelled)$")
    ):
        return await guard(lambda: svc.ledger(session).contracts(status))()

    @r.get("/calibration")
    async def calibration(session: str = SESSION):
        return await guard(svc.calibration)(session)

    @r.get("/equity")
    async def equity(session: str = SESSION, limit: int = Query(5000, ge=1, le=20000)):
        return await guard(lambda: svc.ledger(session).equity_curve(limit))()

    @r.get("/tournament")
    async def tournament():
        return svc.tournament()

    @r.get("/desk")
    async def desk():
        return svc.desk()

    @r.get("/desk/runs")
    async def desk_runs(limit: int = Query(20, ge=1, le=100)):
        return await guard(svc.desk_runs)(limit)

    @r.get("/desk/recorded")
    async def desk_recorded():
        rec = svc.recorded_review()
        if rec is None:
            raise HTTPException(404, "No recorded review is bundled")
        return rec

    @r.get("/desk/runs/{run_id}")
    async def desk_run(run_id: str):
        return await guard(svc.desk_run)(run_id)

    @r.get("/backtest/report")
    async def backtest_report():
        rep = svc.backtest_report()
        if rep is None:
            raise HTTPException(404, "No backtest report yet: run `python -m axiom.trading backtest`")
        return rep

    @r.get("/scenarios")
    async def scenario_list():
        return [s.to_dict() for s in scenarios.SCENARIOS.values()]

    @r.get("/replays")
    async def replays():
        return [j.to_dict() for j in sorted(svc.replays.values(), key=lambda j: -j.started_at)]

    @r.get("/replays/{rid}")
    async def replay(rid: str):
        job = svc.replays.get(rid)
        if job is None:
            raise HTTPException(404, "Unknown replay")
        return {**job.to_dict(), "report": job.report}

    @r.get("/stream")
    async def stream(request: Request, session: str = SESSION):
        """Server-sent events: journal entries, orders, state changes, ticks, approvals, replay progress."""
        q = svc.hub.subscribe()

        async def events():
            try:
                yield {"event": "hello", "data": json.dumps({"session": session})}
                while True:
                    ev = await q.get()
                    if ev.get("session") not in (session, None) and ev.get("type") != "replay":
                        continue
                    yield {"event": ev.get("type", "message"), "data": json.dumps(ev, default=str)}
            finally:
                svc.hub.unsubscribe(q)

        return EventSourceResponse(events(), ping=15)

    # ---------------------------------------------------------- controls
    @r.post("/kill", dependencies=ctl)
    async def kill(body: KillIn | None = None):
        return await guard(svc.kill)((body or KillIn()).reason)

    @r.post("/resume", dependencies=ctl)
    async def resume():
        return await guard(svc.resume)()

    @r.post("/start", dependencies=ctl)
    async def start():
        return await guard(svc.start)()

    @r.post("/stop", dependencies=ctl)
    async def stop():
        return await guard(svc.stop)()

    @r.post("/autonomy", dependencies=ctl)
    async def autonomy(body: AutonomyIn):
        return await guard(svc.set_autonomy)(body.level, body.lock)

    @r.post("/orders/{pending_id}/approve", dependencies=ctl)
    async def approve(pending_id: str):
        return await guard(svc.approve)(pending_id)

    @r.post("/orders/{pending_id}/reject", dependencies=ctl)
    async def reject(pending_id: str):
        return await guard(svc.reject)(pending_id)

    guest = [Depends(control_or_guest)]

    @r.post("/desk/review", dependencies=guest)
    async def desk_review(body: ReviewIn):
        return await guard(svc.review_now)(body.symbol)

    @r.post("/replay")
    async def start_replay(body: ReplayIn | None = None, full: bool = Depends(control_or_guest)):
        b = body or ReplayIn()
        if not full and b.scenario is None:
            raise HTTPException(
                403, "Visitors can play the three scenarios; a custom replay needs the API token"
            )
        job = await guard(svc.start_replay)(b.symbols, b.bars, b.delay, b.scenario)
        return job.to_dict()

    @r.post("/replays/{rid}/stop", dependencies=guest)
    async def stop_replay(rid: str):
        return await guard(svc.stop_replay)(rid)

    @r.post("/redteam", dependencies=ctl)
    async def redteam():
        return await guard(svc.redteam)()

    return r
