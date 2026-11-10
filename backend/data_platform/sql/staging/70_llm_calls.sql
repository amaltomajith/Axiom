-- description: One row per LLM request, unpacked from run traces (llm_call events). Token counts are as reported by the provider.
SELECT
  r.run_id,
  r.ticker,
  LAX_INT64(e.seq) AS seq,
  TIMESTAMP_MICROS(CAST(ROUND(LAX_FLOAT64(e.ts) * 1e6) AS INT64)) AS called_at,
  LAX_STRING(e.agent) AS agent,
  LAX_STRING(e.data.label) AS label,
  LAX_STRING(e.data.provider) AS provider,
  LAX_STRING(e.data.model) AS model,
  LAX_INT64(e.data.prompt_tokens) AS prompt_tokens,
  LAX_INT64(e.data.completion_tokens) AS completion_tokens,
  LAX_INT64(e.data.latency_ms) AS latency_ms,
  LAX_BOOL(e.data.cached) AS cached
FROM `${staging}.runs` AS r, UNNEST(JSON_QUERY_ARRAY(r.events)) AS e
WHERE LAX_STRING(e.type) = 'llm_call'
