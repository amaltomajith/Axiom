"""Exercise the MCP server over a real in-memory client session (full protocol round-trip)."""

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from axiom.config import get_settings
from axiom.data import market
from axiom.mcp_server.server import mcp

from .conftest import make_ohlcv

EXPECTED_TOOLS = {
    "get_price_summary",
    "get_indicators",
    "get_regime",
    "get_risk_metrics",
    "get_company_news_sentiment",
    "fetch_sec_filing_summary",
    "run_backtest",
    "run_walk_forward_model",
    "get_forecast_cone",
    "size_position",
    "get_peer_comparison",
}


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    get_settings.cache_clear()

    async def fake_fetch(ticker, bars=504):
        t = market.normalize_ticker(ticker)
        df = make_ohlcv(max(bars, 300), seed=sum(map(ord, t)))
        return df.iloc[-bars:], "synthetic"

    monkeypatch.setattr(market, "fetch_ohlcv", fake_fetch)
    yield
    get_settings.cache_clear()


async def call(client, name, **args):
    res = await client.call_tool(name, args)
    return res, (json.loads(res.content[0].text) if res.content else None)


async def test_lists_all_tools_with_descriptions_and_schemas():
    async with connect(mcp._mcp_server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == EXPECTED_TOOLS
    for t in tools.values():
        assert t.description and len(t.description) > 30
        assert t.inputSchema["properties"]
    assert tools["size_position"].inputSchema["required"] == ["ticker", "equity"]


async def test_core_tools_return_compact_metadata_tagged_results():
    async with connect(mcp._mcp_server) as client:
        for name in ("get_price_summary", "get_indicators", "get_regime", "get_risk_metrics"):
            res, body = await call(client, name, ticker="AAPL")
            assert not res.isError, body
            assert body["meta"]["tool"] == name and body["meta"]["provider"] == "synthetic"
            assert len(res.content[0].text) < 3000  # token-frugal by design


async def test_backtest_reports_verdict_and_thin_curve():
    async with connect(mcp._mcp_server) as client:
        res, body = await call(client, "run_backtest", ticker="MSFT", strategy="sma_cross")
    assert body["verdict"] in {"no_edge", "unproven", "edge_detected", "insufficient_data"}
    assert "equity_curve" not in body and len(body["equity_curve_sampled"]) <= 30
    assert body["metrics"]["n_days"] > 200


async def test_walk_forward_exposes_skill_stats():
    async with connect(mcp._mcp_server) as client:
        res, body = await call(client, "run_walk_forward_model", ticker="NVDA")
    assert not res.isError
    assert {"oos_r2_vs_zero", "directional_accuracy", "n_oos"} <= set(body["model_skill"])


async def test_size_position_respects_limits():
    async with connect(mcp._mcp_server) as client:
        res, body = await call(client, "size_position", ticker="AAPL", equity=100000)
    assert body["risk_pct_of_equity"] <= 0.01 + 1e-9 and body["position_pct"] <= 0.20 + 1e-9


async def test_invalid_input_is_a_tool_error_not_a_crash():
    async with connect(mcp._mcp_server) as client:
        bad_ticker = await client.call_tool("get_price_summary", {"ticker": "AAPL&x=1"})
        bad_risk = await client.call_tool(
            "size_position", {"ticker": "AAPL", "equity": 1000, "risk_per_trade": 0.5}
        )
        bad_strategy = await client.call_tool("run_backtest", {"ticker": "AAPL", "strategy": "yolo"})
    assert bad_ticker.isError and bad_risk.isError and bad_strategy.isError


async def test_resources_and_prompts():
    async with connect(mcp._mcp_server) as client:
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        prompts = {p.name for p in (await client.list_prompts()).prompts}
        memo = await client.get_prompt("investment_memo", {"ticker": "nvda"})
    assert {"axiom://strategies", "axiom://methodology"} <= uris
    assert {"investment_memo", "risk_review"} <= prompts
    assert "NVDA" in memo.messages[0].content.text and "untrusted_data" in memo.messages[0].content.text


async def test_tool_descriptions_do_not_depend_on_the_interpreter():
    """Python 3.13 strips docstring indentation and 3.12 keeps it. Prompts (and recorded evals) hash the tool
    descriptions, so they must be normalised or replays only pass on the interpreter that recorded them."""
    from axiom.agents.toolbox import McpToolBox

    async with McpToolBox.inprocess() as box:
        for spec in await box.specs():
            desc = spec["function"]["description"]
            assert desc and "\n " not in desc and desc == desc.strip(), spec["function"]["name"]
