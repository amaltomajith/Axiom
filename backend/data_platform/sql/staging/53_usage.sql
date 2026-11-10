-- description: Rate-limit counters per scope (ip = all per-client analysis caps summed, global = site-wide cap, watch = per-client visitor watchlist writes) and time bucket. Client IPs are redacted at extraction.
SELECT key AS scope, bucket, SUM(n) AS n, ANY_VALUE(_loaded_at) AS _loaded_at
FROM `${raw}.usage`
WHERE _batch_id = (SELECT MAX(_batch_id) FROM `${raw}.usage`)
GROUP BY scope, bucket
