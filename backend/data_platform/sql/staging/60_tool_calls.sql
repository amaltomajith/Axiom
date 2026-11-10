-- description: One row per MCP tool call, unpacked from run traces (tool_result events).
SELECT
  r.run_id,
  r.ticker,
  LAX_INT64(e.seq) AS seq,
  TIMESTAMP_MICROS(CAST(ROUND(LAX_FLOAT64(e.ts) * 1e6) AS INT64)) AS called_at,
  LAX_STRING(e.agent) AS agent,
  LAX_STRING(e.data.tool) AS tool,
  LAX_BOOL(e.data.ok) AS ok,
  LAX_INT64(e.data.latency_ms) AS latency_ms,
  LAX_INT64(e.data.chars) AS result_chars
FROM `${staging}.runs` AS r, UNNEST(JSON_QUERY_ARRAY(r.events)) AS e
WHERE LAX_STRING(e.type) = 'tool_result'
