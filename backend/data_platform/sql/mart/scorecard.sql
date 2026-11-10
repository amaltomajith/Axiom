-- description: Hit rate and calibration of scored calls by rating, horizon and conviction. Empty until at least 30 directional (non-HOLD) calls are scored, the same rule as memory/scorer.py (MIN_SAMPLE).
WITH scored AS (
  SELECT
    t.rating,
    t.horizon_days,
    CASE WHEN t.conviction < 0.4 THEN 'low (<0.4)' WHEN t.conviction < 0.7 THEN 'mid (0.4-0.7)' ELSE 'high (>=0.7)' END
      AS conviction_bucket,
    t.direction,
    o.direction_hit,
    o.beat_benchmark,
    o.brier,
    o.ret_pct,
    -- probability of "up" the call implied (same mapping scorer.py uses for the Brier score)
    IF(t.direction = 0, NULL, LEAST(0.99, GREATEST(0.01, 0.5 + t.direction * 0.5 * t.conviction))) AS p_up
  FROM `${staging}.theses` AS t
  JOIN `${staging}.outcomes` AS o ON o.thesis_id = t.id
),
gate AS (SELECT COUNTIF(direction_hit IS NOT NULL) AS n_directional_total FROM scored)
SELECT
  CASE
    WHEN GROUPING(rating) = 0 THEN 'rating'
    WHEN GROUPING(horizon_days) = 0 THEN 'horizon_days'
    ELSE 'conviction'
  END AS dimension,
  COALESCE(rating, CAST(horizon_days AS STRING), conviction_bucket) AS bucket,
  COUNT(*) AS n_scored,
  COUNTIF(direction_hit IS NOT NULL) AS n_directional,
  SAFE_DIVIDE(COUNTIF(direction_hit = 1), COUNTIF(direction_hit IS NOT NULL)) AS hit_rate,
  SAFE_DIVIDE(COUNTIF(beat_benchmark = 1), COUNTIF(beat_benchmark IS NOT NULL)) AS beat_benchmark_rate,
  -- calibration: what the calls implied vs how often the price actually went up
  AVG(p_up) AS mean_implied_p_up,
  SAFE_DIVIDE(COUNTIF(p_up IS NOT NULL AND ret_pct > 0), COUNTIF(p_up IS NOT NULL)) AS realized_up_rate,
  AVG(brier) AS mean_brier,
  1 - SAFE_DIVIDE(AVG(brier), 0.25) AS brier_skill_vs_coinflip,
  ANY_VALUE(gate.n_directional_total) AS n_directional_total
FROM scored
CROSS JOIN gate
WHERE gate.n_directional_total >= 30
GROUP BY GROUPING SETS ((rating), (horizon_days), (conviction_bucket))
