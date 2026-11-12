"""Print the Render environment variables for the Autopilot, ready for Environment > "Add from .env".

Run it yourself and send the output straight to the clipboard, so the values never land in a terminal log:

    python deploy/render/env_for_render.py | clip

Only credentials are copied from backend/.env (names ending in API_KEY, SECRET_KEY or TOKEN), plus the Hugging Face
token you logged in with (`hf auth login`), which the service uses to back up its store to a private dataset.
DATABASE_URL is never copied: the service keeps its own SQLite store, not the production database. Settings
(broker, brain, symbols, CORS) are fixed in deploy/render/Dockerfile. The key names go to stderr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET = re.compile(r"^[A-Z0-9_]*(API_KEY|SECRET_KEY|TOKEN)$")
SKIP = {"DATABASE_URL", "HF_TOKEN"}


def pairs(path: Path) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if v and SECRET.match(k) and k not in SKIP:
            out.append((k, v))
    return out


if __name__ == "__main__":
    from huggingface_hub import get_token

    found = pairs(ROOT / "backend" / ".env")
    token = get_token()
    if token:
        found.append(("HF_TOKEN", token))
    for k, v in found:
        print(f"{k}={v}")
    print("copied: " + ", ".join(k for k, _ in found), file=sys.stderr)
    if not token:
        print(
            "no Hugging Face login found: run `hf auth login` first, or the store will not survive restarts",
            file=sys.stderr,
        )
