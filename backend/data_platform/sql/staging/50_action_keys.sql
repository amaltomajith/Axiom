-- description: Idempotency keys of executed action steps (current snapshot).
SELECT key, action_id, TIMESTAMP_MICROS(CAST(ROUND(done_at * 1e6) AS INT64)) AS done_at, _loaded_at
FROM `${raw}.action_keys`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY key ORDER BY _loaded_at DESC) = 1
