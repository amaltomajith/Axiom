-- description: One row per scored thesis (newest score).
SELECT
  thesis_id,
  TIMESTAMP_MICROS(CAST(ROUND(scored_at * 1e6) AS INT64)) AS scored_at,
  SAFE.PARSE_DATE('%Y-%m-%d', horizon_date) AS horizon_date,
  price_at_horizon,
  ret_pct,
  benchmark_ret_pct,
  excess_ret_pct,
  direction_hit,
  beat_benchmark,
  stop_hit,
  brier,
  SAFE.PARSE_JSON(detail_json) AS detail,
  _loaded_at
FROM `${raw}.outcomes`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY thesis_id ORDER BY _wm DESC, _loaded_at DESC) = 1
