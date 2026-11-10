-- description: One row per thesis. `status` is re-derived from outcomes because the source flips it without a timestamp.
WITH latest AS (
  SELECT *
  FROM `${raw}.theses`
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _wm DESC, _loaded_at DESC) = 1
),
scored AS (SELECT DISTINCT thesis_id FROM `${raw}.outcomes`)
SELECT
  t.id,
  t.run_id,
  t.ticker,
  TIMESTAMP_MICROS(CAST(ROUND(t.created_at * 1e6) AS INT64)) AS created_at,
  SAFE.PARSE_DATE('%Y-%m-%d', t.issue_date) AS issue_date,
  t.horizon_days,
  t.price_at_issue,
  t.rating,
  -- same mapping as memory/scorer.py direction_of(): HOLD and anything unknown is non-directional
  CASE t.rating WHEN 'STRONG_BUY' THEN 1 WHEN 'BUY' THEN 1 WHEN 'SELL' THEN -1 WHEN 'STRONG_SELL' THEN -1 ELSE 0 END
    AS direction,
  t.conviction,
  t.stop_price,
  IF(s.thesis_id IS NOT NULL, 'scored', t.status) AS status,
  SAFE.PARSE_JSON(t.memo_json) AS memo,
  SAFE.PARSE_JSON(t.findings_json) AS findings,
  t._loaded_at
FROM latest t
LEFT JOIN scored s ON s.thesis_id = t.id
