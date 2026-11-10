"""Axiom data platform: ELT from the operational database into BigQuery, plus data-quality checks.

Sits beside the agent pipeline: it reads Axiom's tables and reuses its market-data and indicator code,
but never calls an LLM, never changes agent prompts or tools, and never writes to the source database.
"""

from __future__ import annotations

import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PKG_DIR.parent
SQL_DIR = PKG_DIR / "sql"


def isolate_from_app_env() -> None:
    """Call before importing anything from `axiom`.

    backend/.env holds the production DATABASE_URL with write access. Axiom's settings would pick it up
    and route the market-data cache to production. The source database is passed explicitly instead
    (AXIOM_SOURCE_DATABASE_URL, a read-only role), and Axiom's own cache stays on local SQLite.
    """
    os.environ["DATABASE_URL"] = ""
    os.environ.setdefault("CACHE_DB", str(BACKEND_DIR / ".cache" / "data_platform_cache.db"))
    env_data = BACKEND_DIR / ".env.data"
    if env_data.exists():
        for line in env_data.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
