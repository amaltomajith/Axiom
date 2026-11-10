-- severity: critical
-- description: Numbers sit in their valid ranges (conviction and Brier in [0,1], prices and horizons positive, latencies and token counts non-negative).
SELECT 'value_ranges' AS check_name, table_name, CAST(n AS FLOAT64) AS observed, n = 0 AS passed,
  FORMAT('%d rows outside %s', n, rule) AS detail
FROM (
  SELECT 'theses' AS table_name, 'conviction in [0,1], price_at_issue > 0, horizon_days > 0, stop_price > 0' AS rule,
    COUNTIF(conviction IS NULL OR conviction NOT BETWEEN 0 AND 1 OR price_at_issue <= 0 OR horizon_days <= 0
      OR stop_price <= 0) AS n
  FROM `${staging}.theses`
  UNION ALL SELECT 'outcomes', 'brier in [0,1], price_at_horizon > 0',
    COUNTIF(brier NOT BETWEEN 0 AND 1 OR price_at_horizon <= 0)
  FROM `${staging}.outcomes`
  UNION ALL SELECT 'tool_calls', 'latency_ms >= 0', COUNTIF(latency_ms IS NULL OR latency_ms < 0)
  FROM `${staging}.tool_calls`
  UNION ALL SELECT 'llm_calls', 'tokens >= 0, latency_ms >= 0',
    COUNTIF(prompt_tokens < 0 OR completion_tokens < 0 OR latency_ms < 0)
  FROM `${staging}.llm_calls`
  UNION ALL SELECT 'paper_trades', 'quantity > 0, prices > 0',
    COUNTIF(quantity <= 0 OR entry_price <= 0 OR exit_price <= 0)
  FROM `${staging}.paper_trades`
)
