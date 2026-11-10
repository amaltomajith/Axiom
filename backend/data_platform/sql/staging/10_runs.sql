-- description: One row per analysis run (newest version), typed. Traces stay as JSON here; tool_calls and llm_calls unpack them.
SELECT
  run_id,
  ticker,
  TIMESTAMP_MICROS(CAST(ROUND(created_at * 1e6) AS INT64)) AS created_at,
  SAFE.PARSE_JSON(result_json) AS result,
  SAFE.PARSE_JSON(events_json) AS events,
  _loaded_at
FROM `${raw}.runs`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY _wm DESC, _loaded_at DESC) = 1
