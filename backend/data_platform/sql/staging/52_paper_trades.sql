-- description: Paper trades (current snapshot). Dates are trading dates.
SELECT
  id,
  ticker,
  side,
  quantity,
  entry_price,
  SAFE.PARSE_DATE('%Y-%m-%d', entry_date) AS entry_date,
  thesis_id,
  exit_price,
  SAFE.PARSE_DATE('%Y-%m-%d', exit_date) AS exit_date,
  _loaded_at
FROM `${raw}.paper_trades`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _loaded_at DESC) = 1
