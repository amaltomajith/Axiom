-- severity: critical
-- description: This run's load really landed: the newest load across the raw tables is at most 120 minutes old when the checks run. Snapshot tables are reloaded every run, so a quiet day with no new analysis runs still passes (the first version looked only at raw.runs and stopped a healthy run).
SELECT 'load_freshness' AS check_name, 'raw.*' AS table_name,
  CAST(TIMESTAMP_DIFF(${now}, newest, MINUTE) AS FLOAT64) AS observed,
  IFNULL(TIMESTAMP_DIFF(${now}, newest, MINUTE) <= 120, FALSE) AS passed,
  FORMAT('newest load %t, limit 120 minutes', newest) AS detail
FROM (
  SELECT MAX(t) AS newest FROM (
    SELECT MAX(_loaded_at) AS t FROM `${raw}.runs`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.theses`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.outcomes`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.actions`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.action_keys`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.watchlist`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.paper_trades`
    UNION ALL SELECT MAX(_loaded_at) FROM `${raw}.usage`
  )
)
