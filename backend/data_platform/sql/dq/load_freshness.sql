-- severity: critical
-- description: This run's load really landed: the newest raw load is at most 120 minutes old when the checks run.
SELECT 'load_freshness' AS check_name, 'raw.runs' AS table_name,
  CAST(TIMESTAMP_DIFF(${now}, newest, MINUTE) AS FLOAT64) AS observed,
  IFNULL(TIMESTAMP_DIFF(${now}, newest, MINUTE) <= 120, FALSE) AS passed,
  FORMAT('newest load %t, limit 120 minutes', newest) AS detail
FROM (SELECT MAX(_loaded_at) AS newest FROM `${raw}.runs`)
