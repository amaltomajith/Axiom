import pytest

from axiom.actions import approval
from axiom.actions.executors import (
    ComposioExecutor,
    DryRunExecutor,
    StepResult,
    build_executor,
    map_arguments,
)
from axiom.actions.models import ActionStep
from axiom.actions.planner import digest_plan, propose
from axiom.agents.orchestrator import AnalysisResult
from axiom.agents.schemas import Claim, Memo, PositionPlan
from axiom.config import Settings, get_settings
from axiom.memory.store import Store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    for k in ("COMPOSIO_API_KEY", "NOTION_PARENT_PAGE_ID", "SHEETS_SPREADSHEET_ID", "SLACK_CHANNEL"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def result(rating="BUY", conviction=0.65, position=None, degraded=None) -> AnalysisResult:
    c = [Claim(text="Last close was 100.0", evidence=["T1"])]
    memo = Memo(ticker="AAA", rating=rating, conviction=conviction, thesis="A sufficiently long thesis here.",
                bull_case=c, bear_case=c, key_risks=["r"])  # fmt: skip
    pos = position or PositionPlan(action="open_long", shares=50, entry_reference=100.0, stop_price=94.0,
                                   risk_amount=300.0, position_pct=0.05)  # fmt: skip
    return AnalysisResult("run1", "AAA", memo, "# AAA BUY\nbody", [], pos, {}, [], degraded or [], {})


# ------------------------------------------------------------------------------ planner gate


def test_directional_confident_result_gets_a_four_step_reviewable_plan():
    plan, why = propose(result(), "dry_run")
    assert plan and [s.kind for s in plan.steps] == [
        "paper_trade",
        "notion_page",
        "sheet_row",
        "slack_message",
    ]
    assert plan.status == "proposed" and plan.executor == "dry_run" and "awaiting approval" in why
    sheet = next(s for s in plan.steps if s.kind == "sheet_row")
    assert sheet.preview["values"][1:4] == ["AAA", "BUY", 0.65]
    keys = [s.idempotency_key for s in plan.steps]
    assert len(set(keys)) == 4 and all(k.startswith("run1:") for k in keys)


@pytest.mark.parametrize(
    "res,fragment",
    [
        (result("HOLD"), "no action proposed"),
        (result("NO_CALL", 0.0), "no action proposed"),
        (result(conviction=0.3), "below"),
        (result(position=PositionPlan(action="none", violations=["AAA is 30% of equity"])), "Risk limits"),
        (result(degraded=["Synthesizer degraded: x"]), "degraded"),
    ],
)
def test_gate_refuses_weak_or_unsafe_results(res, fragment):
    plan, why = propose(res, "dry_run")
    assert plan is None and fragment in why


def test_sell_plan_has_no_paper_trade_step():
    plan, _ = propose(result("SELL", 0.7, PositionPlan(action="avoid")), "dry_run")
    assert plan and "paper_trade" not in [s.kind for s in plan.steps]


# --------------------------------------------------------------------------------- approval


async def test_nothing_runs_before_approval_then_each_step_runs_once(store):
    plan, _ = propose(result(), "dry_run")
    approval.save(store, plan)
    assert store.trades() == [] and store.list_actions()[0]["status"] == "proposed"

    done = await approval.approve(store, plan.id, DryRunExecutor(), thesis_id="th1")
    assert done.status == "executed" and all(s.status == "done" for s in done.steps)
    assert store.trades()[0]["thesis_id"] == "th1" and store.trades()[0]["quantity"] == 50
    assert done.steps[1].result["dry_run"] is True

    with pytest.raises(approval.ActionError, match="already executed"):
        await approval.approve(store, plan.id, DryRunExecutor())
    assert len(store.trades()) == 1  # no double booking


async def test_idempotency_key_blocks_a_duplicate_plan_for_the_same_run(store):
    first, _ = propose(result(), "dry_run")
    approval.save(store, first)
    await approval.approve(store, first.id, DryRunExecutor())
    second, _ = propose(result(), "dry_run")  # same run_id => same keys
    approval.save(store, second)
    out = await approval.approve(store, second.id, DryRunExecutor())
    assert all(s.status == "skipped" for s in out.steps) and len(store.trades()) == 1


class FlakyExecutor:
    name = "flaky"

    def __init__(self):
        self.calls: list[str] = []
        self.fail_slack = True

    async def run(self, step: ActionStep) -> StepResult:
        self.calls.append(step.kind)
        if step.kind == "slack_message" and self.fail_slack:
            return StepResult(False, error="channel_not_found")
        return StepResult(True, {"id": f"ext-{step.kind}"})


async def test_partial_failure_then_retry_only_reruns_the_failed_step(store):
    plan, _ = propose(result(), "flaky")
    approval.save(store, plan)
    ex = FlakyExecutor()
    out = await approval.approve(store, plan.id, ex)
    assert out.status == "partial"
    assert [s.status for s in out.steps] == ["done", "done", "done", "failed"]
    assert out.steps[3].error == "channel_not_found"

    ex.fail_slack = False
    ex.calls.clear()
    fixed = await approval.retry_failed(store, plan.id, ex)
    assert fixed.status == "executed" and ex.calls == ["slack_message"]  # Notion/Sheet NOT duplicated
    assert [s.status for s in fixed.steps] == ["done"] * 4 and len(store.trades()) == 1


async def test_executor_exception_is_contained_and_key_released(store):
    class Boom:
        name = "boom"

        async def run(self, step):
            raise RuntimeError("network down")

    plan, _ = propose(result("SELL", 0.7, PositionPlan(action="avoid")), "boom")
    approval.save(store, plan)
    out = await approval.approve(store, plan.id, Boom())
    assert out.status == "failed" and "network down" in out.steps[0].error
    assert store.claim_key(plan.steps[0].idempotency_key, "x") is True  # released for retry


async def test_reject_blocks_execution(store):
    plan, _ = propose(result(), "dry_run")
    approval.save(store, plan)
    assert approval.reject(store, plan.id).status == "rejected"
    with pytest.raises(approval.ActionError):
        await approval.approve(store, plan.id, DryRunExecutor())
    with pytest.raises(approval.ActionError):
        approval.load(store, "nope")


def test_digest_plan_is_a_single_slack_step():
    p = digest_plan("daily-2026-01-01", "AAPL HOLD, NVDA BUY")
    assert [s.kind for s in p.steps] == ["slack_message"] and p.rating == "DIGEST"


# -------------------------------------------------------------------------------- composio


def test_argument_mapping_adapts_to_whatever_parameter_names_the_tool_exposes():
    logical = {"channel": "C1", "text": "hi"}
    assert map_arguments("slack_message", logical, {"channel", "markdown_text"}) == {
        "channel": "C1",
        "markdown_text": "hi",
    }
    assert map_arguments("slack_message", logical, {"channel_id", "text", "thread_ts"}) == {
        "channel_id": "C1",
        "text": "hi",
    }
    with pytest.raises(ValueError, match="cannot map"):
        map_arguments("slack_message", logical, {"foo", "bar"})


class FakeTool:
    def __init__(self, props):
        self.input_parameters = {"properties": {p: {} for p in props}}


class FakeComposio:
    def __init__(self, ok=True):
        self.executed: list[tuple] = []
        self.ok = ok
        parent = self

        class Tools:
            def get_raw_composio_tool_by_slug(self, slug):
                return FakeTool({"channel": 0, "markdown_text": 0} if "SLACK" in slug else {"parent_id": 0, "title": 0, "content": 0}
                                if "NOTION" in slug else {"spreadsheetId": 0, "range": 0, "values": 0})  # fmt: skip

            def execute(self, slug, arguments, user_id=None, **kw):
                parent.executed.append((slug, arguments, user_id))
                return {
                    "successful": parent.ok,
                    "data": {"ok": True},
                    "error": None if parent.ok else "denied",
                }

        self.tools = Tools()


def composio_settings(**kw) -> Settings:
    base = dict(
        composio_api_key="k", notion_parent_page_id="P1", sheets_spreadsheet_id="S1", slack_channel="#c"
    )
    return Settings(**{**base, **kw})


async def test_composio_executor_maps_and_executes_each_kind():
    fake = FakeComposio()
    ex = ComposioExecutor(composio_settings(), client=fake)
    plan, _ = propose(result(), "composio")
    outs = [await ex.run(s) for s in plan.steps if s.kind != "paper_trade"]
    assert all(o.ok for o in outs)
    by_slug = {slug: (args, uid) for slug, args, uid in fake.executed}
    notion_args, uid = by_slug["NOTION_CREATE_NOTION_PAGE"]
    assert notion_args["parent_id"] == "P1" and "AAA" in notion_args["title"] and uid == "axiom-default"
    sheet_args, _ = by_slug["GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND"]
    assert sheet_args["spreadsheetId"] == "S1" and sheet_args["values"][0][1] == "AAA"
    assert by_slug["SLACK_SEND_MESSAGE"][0] == {
        "channel": "#c",
        "markdown_text": by_slug["SLACK_SEND_MESSAGE"][0]["markdown_text"],
    }


async def test_composio_failures_and_missing_config_are_reported_not_raised():
    plan, _ = propose(result(), "composio")
    notion = next(s for s in plan.steps if s.kind == "notion_page")
    res = await ComposioExecutor(composio_settings(notion_parent_page_id=None), client=FakeComposio()).run(
        notion
    )
    assert not res.ok and "NOTION_PARENT_PAGE_ID" in res.error
    res = await ComposioExecutor(composio_settings(), client=FakeComposio(ok=False)).run(notion)
    assert not res.ok and "denied" in res.error


def test_builds_dry_run_without_a_key_and_never_pretends_otherwise():
    assert build_executor(Settings(composio_api_key=None)).name == "dry_run"


# ------------------------------------------------------------------------------- scheduler


async def test_briefing_analyzes_watchlist_posts_one_digest_and_survives_a_failing_ticker(
    tmp_path, monkeypatch
):
    from axiom import scheduler
    from axiom.data import market
    from axiom.data import news as news_data
    from axiom.data import sec as sec_data
    from axiom.llm.client import TokenBudget
    from axiom.llm.fake import ScriptedLLM

    from .conftest import world_slice
    from .test_agents import SEC_FAKE, good_handler, news_fake

    async def fake_fetch(ticker, bars=504):
        if ticker == "BAD":
            raise market.DataError("no data for BAD")
        return world_slice(bars), "synthetic"

    async def fake_sec(ticker, include_risk_factors=False):
        return SEC_FAKE

    async def fake_news(ticker, days=7, limit=8):
        return news_fake()

    monkeypatch.setattr(market, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(sec_data, "get_filing_summary", fake_sec)
    monkeypatch.setattr(news_data, "get_news_sentiment", fake_news)

    store = Store(tmp_path / "briefing.db")
    for t in ("AAPL", "BAD"):
        store.watch_add(t)
    sent = []

    class Capture(DryRunExecutor):
        async def run(self, step):
            sent.append(step)
            return await super().run(step)

    out = await scheduler.run_briefing(
        store=store,
        llm_factory=lambda: ScriptedLLM(good_handler(), TokenBudget(10**6, 100)),
        executor=Capture(),
    )
    assert out["analyzed"] == 1 and out["failed"] == ["BAD: DataError"] and out["digest_status"] == "executed"
    assert len(sent) == 1 and sent[0].kind == "slack_message"  # only the digest was auto-posted
    assert "AAPL" in out["text"] and "Failed: BAD" in out["text"] and "not financial advice" in out["text"]
    assert store.trades() == []  # the briefing never trades
    assert any(p["status"] == "proposed" for p in store.list_actions())  # AAPL's trade plan awaits a human
