-- severity: critical
-- requires: ${staging}.price_bars
-- description: Price bars are physically possible: close > 0, low <= open and close <= high, volume >= 0.
SELECT 'price_bars_valid' AS check_name, 'price_bars' AS table_name, CAST(n AS FLOAT64) AS observed,
  n = 0 AS passed, FORMAT('%d impossible bars', n) AS detail
FROM (
  SELECT COUNTIF(close <= 0 OR low > high OR close > high OR close < low OR open > high OR open < low
    OR volume < 0) AS n
  FROM `${staging}.price_bars`
)
