-- severity: critical
-- description: Children point at existing parents. Every outcome has a thesis, every thesis a run, a trade's thesis (when set) exists, and every action has a run unless it is a daily briefing (run_id 'briefing-YYYY-MM-DD', made by the cron rather than an analysis).
SELECT 'referential_integrity' AS check_name, table_name, CAST(n AS FLOAT64) AS observed, n = 0 AS passed,
  FORMAT('%d orphan rows (%s)', n, rule) AS detail
FROM (
  SELECT 'outcomes' AS table_name, 'outcomes.thesis_id -> theses.id' AS rule, COUNT(*) AS n
  FROM `${staging}.outcomes` AS o LEFT JOIN `${staging}.theses` AS t ON t.id = o.thesis_id
  WHERE t.id IS NULL
  UNION ALL
  SELECT 'theses', 'theses.run_id -> runs.run_id', COUNT(*)
  FROM `${staging}.theses` AS t LEFT JOIN `${staging}.runs` AS r ON r.run_id = t.run_id
  WHERE r.run_id IS NULL
  UNION ALL
  SELECT 'actions', 'actions.run_id -> runs.run_id unless a briefing', COUNT(*)
  FROM `${staging}.actions` AS a LEFT JOIN `${staging}.runs` AS r ON r.run_id = a.run_id
  WHERE r.run_id IS NULL AND NOT STARTS_WITH(a.run_id, 'briefing-')
  UNION ALL
  SELECT 'paper_trades', 'paper_trades.thesis_id -> theses.id when set', COUNT(*)
  FROM `${staging}.paper_trades` AS p LEFT JOIN `${staging}.theses` AS t ON t.id = p.thesis_id
  WHERE p.thesis_id IS NOT NULL AND t.id IS NULL
)
