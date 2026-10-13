from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Serverless hosts (Vercel, Lambda) have a read-only bundle; only /tmp is writable (and per-instance).
ON_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
_DEFAULT_CACHE_DB = Path("/tmp/axiom/axiom.db") if ON_SERVERLESS else BACKEND_DIR / ".cache" / "axiom.db"


class Settings(BaseSettings):
    """Runtime configuration. Values come from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore", populate_by_name=True)

    # --- market data (all optional: yfinance + SEC EDGAR work without keys)
    twelvedata_api_key: str | None = None
    finnhub_api_key: str | None = None
    # SEC requires a descriptive User-Agent with contact info: https://www.sec.gov/os/accessing-edgar-data
    sec_user_agent: str = "Axiom Research axiom-dev@example.com"

    # --- storage
    cache_db: Path = _DEFAULT_CACHE_DB
    # Postgres (Neon etc.) for runs, theses, approvals AND the shared response cache. Unset = local SQLite.
    # Use the pooled connection string on serverless hosts.
    database_url: str | None = None

    # --- LLM providers (OpenAI-compatible endpoints; all have free tiers or run locally)
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    cerebras_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    # model ids change often: override via env (GROQ_MODEL=..., etc.)
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.5-flash"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    cerebras_model: str = "gpt-oss-120b"
    ollama_model: str = "qwen3:8b"
    # Qwen3 etc. burn tokens on hidden reasoning; "none" disables it on Ollama ("" leaves the model default)
    ollama_reasoning_effort: str = "none"
    openrouter_reasoning_effort: str = "low"  # "" sends nothing
    llm_chain: str = "groq,gemini,openrouter,ollama"  # fallback order; unconfigured ones are skipped
    llm_cache: str = "readwrite"  # off | readwrite | replay (replay = never call a provider; evals/CI)
    llm_cache_ttl_days: int = 7
    run_token_budget: int = 60_000  # hard cap per analysis run
    run_max_llm_calls: int = 24
    agent_concurrency: int = 2

    # --- actions (Composio). Without a key the executor runs in dry-run mode and nothing leaves the machine.
    composio_api_key: str | None = None
    composio_user_id: str = "axiom-default"
    composio_notion_slug: str = "NOTION_CREATE_NOTION_PAGE"
    composio_sheets_slug: str = "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND"
    composio_slack_slug: str = "SLACK_SEND_MESSAGE"
    notion_parent_page_id: str | None = None
    sheets_spreadsheet_id: str | None = None
    sheets_range: str = "Sheet1!A:I"
    slack_channel: str | None = None
    action_min_conviction: float = 0.5

    # --- server
    # Bearer token for mutating endpoints; REQUIRED when real actions are enabled.
    # Read from AXIOM_API_TOKEN (not API_TOKEN) so it cannot collide with unrelated env vars.
    api_token: str | None = Field(default=None, validation_alias="AXIOM_API_TOKEN")
    analyze_per_hour: int = 12  # per-client cap to protect free-tier quotas on a public deployment
    analyze_per_day: int = 0  # global cap across all visitors (0 = unlimited); free LLM quotas are shared
    run_deadline_seconds: int = 0  # abort a run cleanly after this long (0 = off); set < the host's limit
    trust_proxy: bool = ON_SERVERLESS  # take the client IP from X-Forwarded-For (only behind a trusted proxy)
    cron_secret: str | None = None  # Bearer secret for /api/cron/* (Vercel Cron sends CRON_SECRET)
    max_concurrent_runs: int = 1
    scheduler_enabled: bool = False
    scheduler_cron: str = "0 8 * * 1-5"  # weekdays 08:00 (server time)
    cors_origins: str = "http://localhost:8080,http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
