-- severity: warn
-- description: Traced tool names are among the MCP server's 11 tools. A new name means the server changed or a trace is malformed, not that the data is wrong.
SELECT 'known_tools' AS check_name, 'tool_calls' AS table_name, CAST(COUNT(*) AS FLOAT64) AS observed,
  COUNT(*) = 0 AS passed,
  FORMAT('%d calls to unknown tools: %s', COUNT(*), IFNULL(STRING_AGG(DISTINCT tool, ', '), '-')) AS detail
FROM `${staging}.tool_calls`
WHERE tool IS NULL OR tool NOT IN (
  'get_price_summary', 'get_indicators', 'get_regime', 'get_risk_metrics', 'get_company_news_sentiment',
  'fetch_sec_filing_summary', 'run_backtest', 'run_walk_forward_model', 'get_forecast_cone', 'size_position',
  'get_peer_comparison')
