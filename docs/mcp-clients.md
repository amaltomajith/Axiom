# Using Axiom from Claude Desktop / Claude Code

The Axiom MCP server is the same one the web app's agents use, so you can ask any MCP client things like
*"Analyze NVDA with Axiom: backtest the 20/50 cross and tell me honestly whether it beats buy-and-hold."*

## Tools

`get_price_summary`, `get_indicators`, `get_regime`, `get_risk_metrics`, `get_company_news_sentiment`,
`fetch_sec_filing_summary`, `run_backtest`, `run_walk_forward_model`, `get_forecast_cone`, `size_position`,
`get_peer_comparison`. Resources: `axiom://strategies`, `axiom://methodology`. Prompts: `investment_memo`, `risk_review`.

Every result is a compact summary with a `meta` block (tool, ticker, as-of date, provider). Backtest tools return a
verdict (`no_edge`, `unproven`, `edge_detected`, `insufficient_data`); the server's instructions tell the client not to
claim an edge the verdict does not support.

## Claude Code

```bash
claude mcp add axiom -- uv --directory /absolute/path/to/Axiom/backend run python -m axiom.mcp_server
```

## Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "axiom": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/Axiom/backend", "run", "python", "-m", "axiom.mcp_server"],
      "env": { "SEC_USER_AGENT": "Axiom Research you@example.com" }
    }
  }
}
```

## Remote (streamable HTTP)

```bash
uv run python -m axiom.mcp_server --transport streamable-http --host 127.0.0.1 --port 8765
```

The HTTP transport has **no authentication**. Keep it on localhost or put it behind your own auth proxy.

## Debugging

```bash
npx @modelcontextprotocol/inspector uv --directory backend run python -m axiom.mcp_server
```
