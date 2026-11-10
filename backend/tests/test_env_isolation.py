"""Tests and evals must never reach the production database through backend/.env or the environment.

Each guard is paired with a positive control that shows the leak is real without it.
"""

import subprocess
import sys
from pathlib import Path

from axiom.config import Settings

BACKEND = Path(__file__).resolve().parent.parent
PROD = "postgresql://user:pw@prod.example.invalid/neondb"
_PRINT_URL = "from axiom.config import get_settings; print(repr(get_settings().database_url))"


def test_positive_control_a_dotenv_file_is_read(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"DATABASE_URL={PROD}\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env)
    assert Settings().database_url == PROD


def test_guard_ignores_dotenv():
    # the autouse fixture in conftest.py is active here
    assert Settings.model_config["env_file"] is None
    assert Settings().database_url is None


def _run(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=120,
        env={**__import__("os").environ, "DATABASE_URL": PROD, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return proc.stdout.strip().splitlines()[-1]


def test_positive_control_env_var_reaches_settings():
    assert _run(_PRINT_URL) == repr(PROD)


def test_eval_runner_forces_sqlite():
    assert _run("import evals.run; " + _PRINT_URL) == repr("")
