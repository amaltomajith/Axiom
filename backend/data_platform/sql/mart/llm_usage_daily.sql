-- description: LLM calls and tokens per calendar day with a 7-day moving average. Free tiers: tokens are the cost measure, there is no dollar figure.
WITH daily AS (
  SELECT
    DATE(called_at) AS day,
    COUNT(DISTINCT run_id) AS runs,
    COUNT(*) AS llm_calls,
    COUNTIF(cached) AS cached_calls,
    SUM(prompt_tokens) AS prompt_tokens,
    SUM(completion_tokens) AS completion_tokens
  FROM `${staging}.llm_calls`
  GROUP BY day
),
calendar AS (
  SELECT day
  FROM (SELECT MIN(day) AS lo, MAX(day) AS hi FROM daily), UNNEST(GENERATE_DATE_ARRAY(lo, hi)) AS day
),
filled AS (
  SELECT
    c.day,
    COALESCE(d.runs, 0) AS runs,
    COALESCE(d.llm_calls, 0) AS llm_calls,
    COALESCE(d.cached_calls, 0) AS cached_calls,
    COALESCE(d.prompt_tokens, 0) AS prompt_tokens,
    COALESCE(d.completion_tokens, 0) AS completion_tokens,
    COALESCE(d.prompt_tokens + d.completion_tokens, 0) AS total_tokens
  FROM calendar AS c
  LEFT JOIN daily AS d USING (day)
)
SELECT
  *,
  SAFE_DIVIDE(total_tokens, runs) AS tokens_per_run,
  AVG(total_tokens) OVER last7 AS total_tokens_7d_avg,
  SUM(runs) OVER last7 AS runs_7d
FROM filled
WINDOW last7 AS (ORDER BY UNIX_DATE(day) RANGE BETWEEN 6 PRECEDING AND CURRENT ROW)
