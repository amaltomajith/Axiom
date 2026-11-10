-- severity: critical
-- description: Each non-NULL primary key appears once in each staging table (catches dedup bugs and duplicated trace events). NULL keys are not_null_keys' job.
SELECT 'unique_keys' AS check_name, table_name, CAST(n - d AS FLOAT64) AS observed, n = d AS passed,
  FORMAT('%d keyed rows, %d distinct keys', n, d) AS detail
FROM (
  SELECT 'runs' AS table_name, COUNT(run_id) AS n, COUNT(DISTINCT run_id) AS d FROM `${staging}.runs`
  UNION ALL SELECT 'theses', COUNT(id), COUNT(DISTINCT id) FROM `${staging}.theses`
  UNION ALL SELECT 'outcomes', COUNT(thesis_id), COUNT(DISTINCT thesis_id) FROM `${staging}.outcomes`
  UNION ALL SELECT 'actions', COUNT(id), COUNT(DISTINCT id) FROM `${staging}.actions`
  UNION ALL SELECT 'action_keys', COUNT(key), COUNT(DISTINCT key) FROM `${staging}.action_keys`
  UNION ALL SELECT 'watchlist', COUNT(ticker), COUNT(DISTINCT ticker) FROM `${staging}.watchlist`
  UNION ALL SELECT 'paper_trades', COUNT(id), COUNT(DISTINCT id) FROM `${staging}.paper_trades`
  UNION ALL SELECT 'usage', COUNT(*), COUNT(DISTINCT TO_JSON_STRING(STRUCT(scope, bucket))) FROM `${staging}.usage`
  UNION ALL SELECT 'tool_calls', COUNT(*), COUNT(DISTINCT TO_JSON_STRING(STRUCT(run_id, seq))) FROM `${staging}.tool_calls`
  UNION ALL SELECT 'llm_calls', COUNT(*), COUNT(DISTINCT TO_JSON_STRING(STRUCT(run_id, seq))) FROM `${staging}.llm_calls`
)
