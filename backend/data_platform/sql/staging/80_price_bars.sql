-- description: Daily OHLCV, one row per ticker and date. Private: provider terms do not allow redistribution.
-- requires: ${raw}.price_bars
-- partition_by: date
-- cluster_by: ticker
SELECT ticker, date, open, high, low, close, volume, provider, _loaded_at
FROM `${raw}.price_bars`
WHERE close IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker, date ORDER BY _loaded_at DESC) = 1
