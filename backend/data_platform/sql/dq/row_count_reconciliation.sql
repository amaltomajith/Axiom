-- severity: critical
-- description: Each table holds as many rows as the source counted at extraction. Catches lost loads, and source deletes that an incremental load cannot see. Usage is compared in raw, because staging sums it per scope.
WITH source AS (SELECT * FROM UNNEST(${source_counts})),
warehouse AS (
  SELECT 'runs' AS table_name, COUNT(*) AS n FROM `${staging}.runs`
  UNION ALL SELECT 'theses', COUNT(*) FROM `${staging}.theses`
  UNION ALL SELECT 'outcomes', COUNT(*) FROM `${staging}.outcomes`
  UNION ALL SELECT 'actions', COUNT(*) FROM `${staging}.actions`
  UNION ALL SELECT 'action_keys', COUNT(*) FROM `${staging}.action_keys`
  UNION ALL SELECT 'watchlist', COUNT(*) FROM `${staging}.watchlist`
  UNION ALL SELECT 'paper_trades', COUNT(*) FROM `${staging}.paper_trades`
  UNION ALL SELECT 'usage', COUNT(*) FROM `${raw}.usage`
)
SELECT 'row_count_reconciliation' AS check_name, s.table_name,
  CAST(IFNULL(w.n, 0) - s.n AS FLOAT64) AS observed,
  IFNULL(w.n, 0) = s.n AS passed,
  FORMAT('source %d, warehouse %d', s.n, IFNULL(w.n, 0)) AS detail
FROM source AS s LEFT JOIN warehouse AS w USING (table_name)
