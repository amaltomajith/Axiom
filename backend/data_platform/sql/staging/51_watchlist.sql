-- description: Watched tickers (current snapshot).
SELECT ticker, TIMESTAMP_MICROS(CAST(ROUND(added_at * 1e6) AS INT64)) AS added_at, _loaded_at
FROM `${raw}.watchlist`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY _loaded_at DESC) = 1
