"""Axiom HTTP API: market/quant endpoints for the UI, SSE-streamed agent runs, memory, approvals."""

from __future__ import annotations

import asyncio
import hmac
import json
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from axiom import services
from axiom.actions import approval
from axiom.actions.executors import build_executor
from axiom.agents.toolbox import McpToolBox
from axiom.agents.trace import Tracer
from axiom.config import get_settings
from axiom.data import market, news, sec
from axiom.llm.client import LLMClient, TokenBudget
from axiom.llm.providers import build_chain
from axiom.llm.types import AllProvidersFailed, BudgetExceeded, LLMError
from axiom.memory import scorer
from axiom.memory.store import Store, get_store
from axiom.pipeline import run_pipeline
from axiom.quant.backtest import STRATEGIES


# ----------------------------------------------------------------------------- guards
def client_ip(request: Request) -> str:
    """The caller's address. Behind a trusted proxy (Vercel, Cloud Run) the socket peer is the proxy, so the
    real client comes from X-Forwarded-For; trusting that header anywhere else would let anyone spoof it."""
    if get_settings().trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd.strip():
            return fwd.split(",")[0].strip()
        real = request.headers.get("x-real-ip", "").strip()
        if real:
            return real
    return request.client.host if request.client else "unknown"


def _seconds_to_next(unit: str) -> int:
    now = datetime.now(UTC)
    if unit == "hour":
        return 3600 - (now.minute * 60 + now.second)
    return 86400 - (now.hour * 3600 + now.minute * 60 + now.second)


def check_quota(st: Store, ip: str, *, hourly: int, daily: int) -> tuple[str, int] | None:
    """Count one analysis against the per-client hourly cap and the global daily cap. Both live in the
    store, so they hold across serverless instances. Returns (message, retry_after_seconds) when refused.
    The daily cap is checked first so a refused request does not eat the client's hourly allowance."""
    now = datetime.now(UTC)
    if not st.hit("global", now.strftime("%Y%m%d"), daily):
        return (
            "Today's free analysis budget for this demo is used up. It resets at 00:00 UTC.",
            _seconds_to_next("day"),
        )
    if not st.hit(f"ip:{ip}", now.strftime("%Y%m%d%H"), hourly):
        return ("Rate limit reached; try again later.", _seconds_to_next("hour"))
    return None


def authorized_cron(request: Request) -> None:
    """Vercel Cron (and our own scripts) send `Authorization: Bearer <CRON_SECRET>`. No secret = disabled."""
    secret = get_settings().cron_secret
    if not secret:
        raise HTTPException(404, "Not found")
    sent = request.headers.get("authorization", "")
    if not hmac.compare_digest(sent.encode(), f"Bearer {secret}".encode()):
        raise HTTPException(401, "Invalid cron secret")


def require_token(request: Request) -> None:
    """Mutations need `Authorization: Bearer <AXIOM_API_TOKEN>`. If no token is configured they are
    only allowed while actions are dry-run (nothing external can be written)."""
    s = get_settings()
    if s.api_token:
        if request.headers.get("authorization", "") != f"Bearer {s.api_token}":
            raise HTTPException(401, "Missing or invalid API token")
    elif build_executor(s).name != "dry_run":
        raise HTTPException(403, "AXIOM_API_TOKEN must be set before real actions can be approved")


_VISITOR_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")


def visitor_id(request: Request) -> str:
    """The anonymous id the Angular app sends in `X-Axiom-Visitor`. It scopes a watchlist; it is not
    authentication (anyone holding the id can edit that list)."""
    v = request.headers.get("x-axiom-visitor", "")
    if not _VISITOR_RE.match(v):
        raise HTTPException(400, "X-Axiom-Visitor header must be 16 to 64 letters, digits or dashes")
    return v


class AnalyzeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    equity: float = Field(100_000.0, gt=0, le=1e9)


class TradeIn(BaseModel):
    ticker: str
    quantity: float = Field(gt=0, le=1e7)


def create_app() -> FastAPI:
    settings = get_settings()
    run_gate = asyncio.Semaphore(max(1, settings.max_concurrent_runs))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if settings.scheduler_enabled:
            from axiom.scheduler import start_scheduler

            scheduler = start_scheduler()
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Axiom", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def default_llm() -> LLMClient:
        s = get_settings()
        return LLMClient(budget=TokenBudget(s.run_token_budget, s.run_max_llm_calls))

    app.state.llm_factory = default_llm  # tests (and evals) swap in a scripted/replay client
    store = lambda: get_store()  # noqa: E731  (resolved per call so tests can swap the DB path)

    @app.exception_handler(market.DataError)
    async def _data_error(_: Request, e: market.DataError):
        return JSONResponse({"error": str(e)}, status_code=400)

    @app.exception_handler(AllProvidersFailed)
    async def _llm_down(_: Request, e: AllProvidersFailed):
        return JSONResponse({"error": str(e)}, status_code=503)

    @app.exception_handler(approval.ActionError)
    async def _action_error(_: Request, e: approval.ActionError):
        return JSONResponse({"error": str(e)}, status_code=409)

    # ------------------------------------------------------------------ meta
    def config_snapshot() -> dict:
        s = get_settings()
        chain = build_chain(s)
        return {
            "ok": True,
            "llm_chain": [p.name for p in chain],
            "llm_models": {p.name: p.model for p in chain},
            "market_data": "twelvedata" if s.twelvedata_api_key else "yfinance",
            "news": "finnhub" if s.finnhub_api_key else "google_news_rss",
            "actions_executor": build_executor(s).name,
            "auth_required": bool(s.api_token),
            "scheduler": s.scheduler_enabled,
            "storage": "postgres" if s.database_url else "sqlite",
            "daily_cap": s.analyze_per_day or None,
        }

    @app.get("/api/health")
    async def health():
        return config_snapshot()

    @app.get("/api/status")
    async def status():
        """Everything the hub page shows about the API in one public call: the config snapshot from
        /api/health plus aggregate counts from the store. Counts only, never secrets or visitor ids.
        Kept separate from /api/health because both front ends poll health to wake the function."""
        body = config_snapshot()
        st = store()
        counts = await asyncio.to_thread(st.counts)
        cap = get_settings().analyze_per_day
        today = datetime.now(UTC).strftime("%Y%m%d")
        used = await asyncio.to_thread(st.usage, "global", today) if cap else None
        return {**body, "counts": counts, "analyses_today": {"used": used, "cap": cap or None}}

    # ------------------------------------------------------------ market data
    @app.get("/api/market/{ticker}/ohlcv")
    async def ohlcv(ticker: str, bars: int = Query(90, ge=5, le=1500)):
        df, provider = await market.fetch_ohlcv(ticker, bars)
        rows = [
            {"date": d.strftime("%Y-%m-%d"), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
             "volume": int(r.volume)}
            for d, r in df.iterrows()
        ]  # fmt: skip
        return {"ticker": market.normalize_ticker(ticker), "provider": provider, "bars": rows}

    @app.get("/api/quant/{ticker}/summary")
    async def summary(ticker: str):
        return await services.price_summary(ticker)

    @app.get("/api/quant/{ticker}/indicators")
    async def indicators(ticker: str):
        return await services.indicators(ticker)

    @app.get("/api/quant/{ticker}/regime")
    async def regime(ticker: str):
        return await services.regime(ticker)

    @app.get("/api/quant/{ticker}/risk")
    async def risk(ticker: str):
        return await services.risk_metrics(ticker)

    @app.get("/api/quant/{ticker}/forecast")
    async def forecast(ticker: str, horizon: int = Query(14, ge=1, le=60)):
        return await services.forecast_cone(ticker, horizon)

    @app.get("/api/quant/{ticker}/backtest")
    async def backtest(ticker: str, strategy: str = "sma_cross"):
        if strategy not in STRATEGIES:
            raise HTTPException(400, f"strategy must be one of {sorted(STRATEGIES)}")
        return await services.backtest(ticker, strategy, full_curve=True)

    @app.get("/api/quant/{ticker}/walk-forward")
    async def walk_forward(ticker: str):
        return await services.walk_forward(ticker, full_curve=True)

    @app.get("/api/news/{ticker}")
    async def get_news(ticker: str, days: int = Query(7, ge=1, le=30)):
        return await news.get_news_sentiment(ticker, days)

    @app.get("/api/filings/{ticker}")
    async def filings(ticker: str, risk_factors: bool = False):
        return await sec.get_filing_summary(ticker, risk_factors)

    # ----------------------------------------------------------- agent run (SSE)
    async def run_events(ticker: str, equity: float):
        """One analysis as SSE messages: `queued`, then `trace`s, then `result` or `error`. Shared by the POST
        route (React, fetch) and the GET route (EventSource), so both behave the same."""
        tracer = Tracer(queue=asyncio.Queue())
        if run_gate.locked():
            yield {
                "event": "queued",
                "data": json.dumps({"message": "Another analysis is running; you are queued."}),
            }
        task: asyncio.Task | None = None

        async def work():
            async with run_gate:
                llm = app.state.llm_factory()
                async with McpToolBox.inprocess() as box:
                    return await run_pipeline(
                        ticker, llm=llm, box=box, store=store(), equity=equity, tracer=tracer
                    )

        deadline = get_settings().run_deadline_seconds or None
        task = asyncio.create_task(asyncio.wait_for(work(), deadline))
        task.add_done_callback(lambda _t: tracer.close())
        try:
            while True:
                ev = await tracer.queue.get()
                if ev is None:
                    break
                yield {"event": "trace", "data": json.dumps(ev.to_dict())}
            outcome = await task  # the queue closes before persistence finishes, so wait for the task itself
            yield {
                "event": "result",
                "data": json.dumps(
                    {
                        **outcome.result.to_dict(),
                        "thesis_id": outcome.thesis_id,
                        "action": outcome.action.model_dump() if outcome.action else None,
                        "action_reason": outcome.action_reason,
                    }
                ),
            }
        except TimeoutError:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "error": f"The run hit this host's {deadline}s limit and was stopped.",
                        "kind": "deadline",
                    }
                ),
            }
        except (AllProvidersFailed, BudgetExceeded, LLMError, market.DataError) as e:
            yield {"event": "error", "data": json.dumps({"error": str(e), "kind": type(e).__name__})}
        except asyncio.CancelledError:  # client disconnected
            raise
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": f"{type(e).__name__}: {e}"[:300], "kind": "internal"}),
            }
        finally:
            if task and not task.done():
                task.cancel()

    @app.post("/api/analyze")
    async def analyze_endpoint(body: AnalyzeRequest, request: Request):
        ticker = market.normalize_ticker(body.ticker)
        s = get_settings()
        refused = check_quota(store(), client_ip(request), hourly=s.analyze_per_hour, daily=s.analyze_per_day)
        if refused is not None:
            msg, retry = refused
            raise HTTPException(429, msg, headers={"Retry-After": str(retry)})
        return EventSourceResponse(run_events(ticker, body.equity), ping=15)

    @app.get("/api/analyze/stream")
    async def analyze_stream(
        request: Request,
        ticker: str = Query(min_length=1, max_length=10),
        equity: float = Query(100_000.0, gt=0, le=1e9),
    ):
        """The same run for `EventSource`, which can only GET and cannot read an error response's body. So
        refusals are SSE `error` events with a `kind`, and a transport error always means "unreachable"."""

        async def refusal(error: str, kind: str, retry_after: int | None = None):
            yield {
                "event": "error",
                "data": json.dumps({"error": error, "kind": kind, "retry_after": retry_after}),
            }

        try:
            t = market.normalize_ticker(ticker)
        except market.DataError as e:
            return EventSourceResponse(refusal(str(e), "invalid_ticker"))
        s = get_settings()
        refused = check_quota(store(), client_ip(request), hourly=s.analyze_per_hour, daily=s.analyze_per_day)
        if refused is not None:
            msg, retry = refused
            return EventSourceResponse(refusal(msg, "rate_limited", retry))
        return EventSourceResponse(run_events(t, equity), ping=15)

    # ------------------------------------------------------------------- cron
    @app.api_route("/api/cron/daily", methods=["GET", "POST"], dependencies=[Depends(authorized_cron)])
    async def cron_daily():
        """Scheduled job for serverless hosts (no always-on process): score matured theses, then run the
        briefing. Vercel Cron calls this with GET. Scoring is idempotent, so a retry is harmless."""
        from axiom.scheduler import run_briefing

        out = await run_briefing(store=store())
        return {k: out[k] for k in ("analyzed", "failed", "scoring", "digest_status")}

    # ----------------------------------------------------------- runs / memory
    @app.get("/api/runs")
    async def runs(limit: int = Query(20, ge=1, le=100)):
        return store().list_runs(limit)

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: str):
        r = store().get_run(run_id)
        if r is None:
            raise HTTPException(404, "run not found")
        return r

    @app.get("/api/theses")
    async def theses(ticker: str | None = None, limit: int = Query(50, ge=1, le=200)):
        st = store()
        out = st.theses(ticker=ticker.upper() if ticker else None, limit=limit)
        scored = {r["id"]: r for r in st.scored(ticker.upper() if ticker else None)}
        for t in out:
            t["outcome"] = (
                {k: scored[t["id"]][k] for k in ("horizon_date", "price_at_horizon", "ret_pct", "benchmark_ret_pct",
                                                 "excess_ret_pct", "direction_hit", "beat_benchmark", "stop_hit", "brier")}
                if t["id"] in scored
                else None
            )  # fmt: skip
        return out

    @app.get("/api/scorecard")
    async def scorecard():
        return scorer.scorecard(store())

    @app.post("/api/score", dependencies=[Depends(require_token)])
    async def score_now():
        return await scorer.score_due(store())

    # ---------------------------------------------------------------- actions
    @app.get("/api/actions")
    async def actions(status: str | None = None):
        return store().list_actions(status)

    @app.get("/api/actions/{action_id}")
    async def action_detail(action_id: str):
        return approval.load(store(), action_id).model_dump()

    def _thesis_for(st: Store, run_id: str) -> str | None:
        return next((t["id"] for t in st.theses(limit=500) if t["run_id"] == run_id), None)

    @app.post("/api/actions/{action_id}/approve", dependencies=[Depends(require_token)])
    async def approve(action_id: str):
        st = store()
        plan = approval.load(st, action_id)
        done = await approval.approve(st, action_id, build_executor(), _thesis_for(st, plan.run_id))
        return done.model_dump()

    @app.post("/api/actions/{action_id}/retry", dependencies=[Depends(require_token)])
    async def retry(action_id: str):
        st = store()
        plan = approval.load(st, action_id)
        done = await approval.retry_failed(st, action_id, build_executor(), _thesis_for(st, plan.run_id))
        return done.model_dump()

    @app.post("/api/actions/{action_id}/reject", dependencies=[Depends(require_token)])
    async def reject(action_id: str):
        return approval.reject(store(), action_id).model_dump()

    # ------------------------------------------------------ watchlist / trades
    @app.get("/api/watchlist")
    async def get_watchlist():
        return store().watchlist()

    @app.put("/api/watchlist/{ticker}", dependencies=[Depends(require_token)])
    async def add_watch(ticker: str):
        store().watch_add(market.normalize_ticker(ticker))
        return store().watchlist()

    @app.delete("/api/watchlist/{ticker}", dependencies=[Depends(require_token)])
    async def del_watch(ticker: str):
        store().watch_remove(market.normalize_ticker(ticker))
        return store().watchlist()

    # ------------------------------------------------- per-visitor watchlist
    @app.get("/api/tickers/search")
    async def ticker_search(q: str = Query(min_length=1, max_length=40), limit: int = Query(8, ge=1, le=20)):
        return await sec.search_tickers(q, limit)

    @app.get("/api/visitor/watchlist")
    async def visitor_list(visitor: str = Depends(visitor_id)):
        return store().visitor_watchlist(visitor)

    def _watch_write(request: Request) -> None:
        bucket = datetime.now(UTC).strftime("%Y%m%d%H")
        if not store().hit(f"watch:{client_ip(request)}", bucket, get_settings().watch_writes_per_hour):
            raise HTTPException(
                429,
                "Too many watchlist changes; try again later.",
                headers={"Retry-After": str(_seconds_to_next("hour"))},
            )

    @app.put("/api/visitor/watchlist/{ticker}")
    async def visitor_add(ticker: str, request: Request, visitor: str = Depends(visitor_id)):
        t = market.normalize_ticker(ticker)
        _watch_write(request)
        cap = get_settings().visitor_watchlist_max
        if not store().visitor_watch_add(visitor, t, cap):
            raise HTTPException(409, f"Your watchlist is full ({cap} tickers). Remove one first.")
        return store().visitor_watchlist(visitor)

    @app.delete("/api/visitor/watchlist/{ticker}")
    async def visitor_remove(ticker: str, request: Request, visitor: str = Depends(visitor_id)):
        t = market.normalize_ticker(ticker)
        _watch_write(request)
        store().visitor_watch_remove(visitor, t)
        return store().visitor_watchlist(visitor)

    @app.get("/api/trades")
    async def get_trades():
        return store().trades()

    @app.post("/api/trades", dependencies=[Depends(require_token)])
    async def add_trade(t: TradeIn):
        df, _ = await market.fetch_ohlcv(t.ticker, 5)
        price = float(df["close"].iloc[-1])
        tid = store().add_trade(
            {"ticker": market.normalize_ticker(t.ticker), "side": "BUY", "quantity": t.quantity,
             "entry_price": price, "entry_date": df.index[-1].strftime("%Y-%m-%d")}
        )  # fmt: skip
        return {"id": tid, "entry_price": price}

    @app.post("/api/trades/{trade_id}/close", dependencies=[Depends(require_token)])
    async def close_trade(trade_id: str):
        st = store()
        trade = next((x for x in st.trades() if x["id"] == trade_id), None)
        if trade is None:
            raise HTTPException(404, "trade not found")
        df, _ = await market.fetch_ohlcv(trade["ticker"], 5)
        st.close_trade(trade_id, float(df["close"].iloc[-1]), df.index[-1].strftime("%Y-%m-%d"))
        return next(x for x in st.trades() if x["id"] == trade_id)

    @app.delete("/api/trades/{trade_id}", dependencies=[Depends(require_token)])
    async def delete_trade(trade_id: str):
        store().delete_trade(trade_id)
        return {"ok": True}

    return app


app = create_app()


def _unused(_: Any = None) -> None:  # keeps type-checkers quiet about re-exports
    return None
