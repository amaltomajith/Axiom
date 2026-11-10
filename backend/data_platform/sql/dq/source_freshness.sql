-- severity: warn
-- description: The app is still producing data. The newest analysis run or action (the cron writes a briefing action every weekday) is at most 96 hours old, which allows a weekend.
SELECT 'source_freshness' AS check_name, 'runs+actions' AS table_name,
  CAST(TIMESTAMP_DIFF(${now}, newest, HOUR) AS FLOAT64) AS observed,
  IFNULL(TIMESTAMP_DIFF(${now}, newest, HOUR) <= 96, FALSE) AS passed,
  FORMAT('newest source row %t, limit 96 hours', newest) AS detail
FROM (
  SELECT MAX(t) AS newest
  FROM (SELECT created_at AS t FROM `${staging}.runs` UNION ALL SELECT created_at FROM `${staging}.actions`)
)
