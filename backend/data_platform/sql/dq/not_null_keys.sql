-- severity: critical
-- description: No primary-key column is NULL in any staging table.
SELECT 'not_null_keys' AS check_name, table_name, CAST(n AS FLOAT64) AS observed, n = 0 AS passed,
  FORMAT('%d rows with a NULL key', n) AS detail
FROM (
  SELECT 'runs' AS table_name, COUNTIF(run_id IS NULL) AS n FROM `${staging}.runs`
  UNION ALL SELECT 'theses', COUNTIF(id IS NULL) FROM `${staging}.theses`
  UNION ALL SELECT 'outcomes', COUNTIF(thesis_id IS NULL) FROM `${staging}.outcomes`
  UNION ALL SELECT 'actions', COUNTIF(id IS NULL) FROM `${staging}.actions`
  UNION ALL SELECT 'action_keys', COUNTIF(key IS NULL) FROM `${staging}.action_keys`
  UNION ALL SELECT 'watchlist', COUNTIF(ticker IS NULL) FROM `${staging}.watchlist`
  UNION ALL SELECT 'paper_trades', COUNTIF(id IS NULL) FROM `${staging}.paper_trades`
  UNION ALL SELECT 'usage', COUNTIF(scope IS NULL OR bucket IS NULL) FROM `${staging}.usage`
  UNION ALL SELECT 'tool_calls', COUNTIF(run_id IS NULL OR seq IS NULL) FROM `${staging}.tool_calls`
  UNION ALL SELECT 'llm_calls', COUNTIF(run_id IS NULL OR seq IS NULL) FROM `${staging}.llm_calls`
)
