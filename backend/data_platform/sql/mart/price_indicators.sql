-- description: Rolling indicators per ticker and day. SMA and volatility match axiom/quant/indicators.py; RSI here is Cutler's (simple means), because Axiom's Wilder RSI is recursive and a window frame cannot express it.
-- requires: ${staging}.price_bars
-- partition_by: date
-- cluster_by: ticker
WITH bars AS (
  SELECT
    ticker,
    date,
    close,
    close - LAG(close) OVER by_ticker AS delta,
    LN(SAFE_DIVIDE(close, LAG(close) OVER by_ticker)) AS log_ret
  FROM `${staging}.price_bars`
  WINDOW by_ticker AS (PARTITION BY ticker ORDER BY date)
)
SELECT
  ticker,
  date,
  close,
  IF(COUNT(close) OVER w20 = 20, AVG(close) OVER w20, NULL) AS sma20,
  IF(COUNT(close) OVER w50 = 50, AVG(close) OVER w50, NULL) AS sma50,
  IF(COUNT(close) OVER w200 = 200, AVG(close) OVER w200, NULL) AS sma200,
  CASE
    WHEN COUNT(delta) OVER w14 < 14 THEN NULL
    WHEN AVG(GREATEST(-delta, 0)) OVER w14 = 0 THEN IF(AVG(GREATEST(delta, 0)) OVER w14 = 0, 50.0, 100.0)
    ELSE 100 - 100 / (1 + AVG(GREATEST(delta, 0)) OVER w14 / AVG(GREATEST(-delta, 0)) OVER w14)
  END AS rsi14_cutler,
  IF(COUNT(log_ret) OVER w20 = 20, STDDEV_SAMP(log_ret) OVER w20 * SQRT(252), NULL) AS vol20_annualized
FROM bars
WINDOW
  by_date AS (PARTITION BY ticker ORDER BY date),
  w14 AS (by_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW),
  w20 AS (by_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
  w50 AS (by_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
  w200 AS (by_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW)
