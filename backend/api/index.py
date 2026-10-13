"""Vercel entrypoint: exposes the FastAPI app as an ASGI function (every path is rewritten here).

The deployed bundle is read-only and has no always-on process, so run storage must be Postgres
(DATABASE_URL) and scheduled work comes from Vercel Cron hitting /api/cron/daily.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from axiom.api.app import app  # noqa: E402,F401  (Vercel looks for a module-level `app`)
