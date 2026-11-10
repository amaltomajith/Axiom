-- description: One row per proposed action (newest version: pending, approved, executed or rejected).
SELECT
  id,
  run_id,
  ticker,
  TIMESTAMP_MICROS(CAST(ROUND(created_at * 1e6) AS INT64)) AS created_at,
  status,
  SAFE.PARSE_JSON(plan_json) AS plan,
  TIMESTAMP_MICROS(CAST(ROUND(decided_at * 1e6) AS INT64)) AS decided_at,
  SAFE.PARSE_JSON(result_json) AS result,
  _loaded_at
FROM `${raw}.actions`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _wm DESC, _loaded_at DESC) = 1
