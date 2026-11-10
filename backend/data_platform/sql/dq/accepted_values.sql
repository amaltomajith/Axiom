-- severity: critical
-- description: Categorical columns hold only values the app can produce (ratings, statuses, 0/1 flags, trade sides).
SELECT 'accepted_values' AS check_name, table_name, CAST(n AS FLOAT64) AS observed, n = 0 AS passed,
  FORMAT('%d rows outside %s', n, allowed) AS detail
FROM (
  SELECT 'theses.rating' AS table_name, 'STRONG_BUY|BUY|HOLD|SELL|STRONG_SELL' AS allowed,
    COUNTIF(rating IS NULL OR rating NOT IN ('STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL')) AS n
  FROM `${staging}.theses`
  UNION ALL SELECT 'theses.status', 'pending|scored', COUNTIF(status IS NULL OR status NOT IN ('pending', 'scored'))
  FROM `${staging}.theses`
  -- PlanStatus in axiom/actions/models.py
  UNION ALL SELECT 'actions.status', 'proposed|executed|partial|failed|rejected',
    COUNTIF(status IS NULL OR status NOT IN ('proposed', 'executed', 'partial', 'failed', 'rejected'))
  FROM `${staging}.actions`
  UNION ALL SELECT 'outcomes.flags', '0|1|NULL',
    COUNTIF(direction_hit NOT IN (0, 1) OR beat_benchmark NOT IN (0, 1) OR stop_hit NOT IN (0, 1))
  FROM `${staging}.outcomes`
  UNION ALL SELECT 'paper_trades.side', 'long|short', COUNTIF(side IS NULL OR side NOT IN ('long', 'short'))
  FROM `${staging}.paper_trades`
  UNION ALL SELECT 'usage.scope', 'ip|global|watch', COUNTIF(scope NOT IN ('ip', 'global', 'watch'))
  FROM `${staging}.usage`
)
