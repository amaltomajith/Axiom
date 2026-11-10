-- description: MCP tool latency percentiles and error rate per tool per day (APPROX_QUANTILES, 1% resolution).
SELECT
  DATE(called_at) AS day,
  tool,
  COUNT(*) AS calls,
  COUNTIF(NOT ok) AS errors,
  SAFE_DIVIDE(COUNTIF(NOT ok), COUNT(*)) AS error_rate,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(50)] AS p50_ms,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(90)] AS p90_ms,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(99)] AS p99_ms,
  MAX(latency_ms) AS max_ms
FROM `${staging}.tool_calls`
GROUP BY day, tool
