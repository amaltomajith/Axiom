"""Keep the Autopilot's SQLite store alive across restarts by mirroring it to a private Hugging Face dataset.

A free Render instance has no persistent disk, so on boot `restore` downloads the last saved copy, `loop` saves a consistent
snapshot (SQLite's online backup) every BACKUP_EVERY seconds when it changed, and `once` saves on shutdown.
Needs HF_TOKEN (a secret env var) and DB_REPO (e.g. "user/axiom-autopilot-db"); without them it does
nothing and the service starts with an empty store.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

STATE = Path(os.environ.get("CACHE_DB", "/app/.cache/axiom.db")).with_name("axiom_state.db")
FILE = "axiom_state.db"
REPO = os.environ.get("DB_REPO", "")
TOKEN = os.environ.get("HF_TOKEN", "")
EVERY = int(os.environ.get("BACKUP_EVERY", "300"))
SNAP = STATE.with_name("axiom_state.snapshot.db")


def log(msg: str) -> None:
    print(f"[dbsync] {msg}", flush=True)


def restore() -> None:
    from huggingface_hub import hf_hub_download

    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        got = hf_hub_download(
            REPO, FILE, repo_type="dataset", token=TOKEN, local_dir=STATE.parent / "restore"
        )
    except Exception as e:  # first boot: nothing saved yet
        log(f"no saved store ({type(e).__name__}); starting empty")
        return
    shutil.copyfile(got, STATE)
    log(f"restored {STATE.name} ({STATE.stat().st_size} bytes)")


def snapshot() -> str | None:
    if not STATE.exists():
        return None
    src = sqlite3.connect(STATE, timeout=30)
    dst = sqlite3.connect(SNAP)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return hashlib.sha256(SNAP.read_bytes()).hexdigest()


def save(last: str | None) -> str | None:
    from huggingface_hub import HfApi

    digest = snapshot()
    if digest is None or digest == last:
        return last
    HfApi(token=TOKEN).upload_file(
        path_or_fileobj=str(SNAP),
        path_in_repo=FILE,
        repo_id=REPO,
        repo_type="dataset",
        commit_message="backup",
    )
    log(f"saved {SNAP.stat().st_size} bytes")
    return digest


def main(cmd: str) -> None:
    if not (REPO and TOKEN):
        log("HF_TOKEN or DB_REPO not set; the store will not survive a restart")
        return
    if cmd == "restore":
        restore()
    elif cmd == "once":
        save(None)
    elif cmd == "loop":
        last = None
        time.sleep(EVERY)
        while True:
            try:
                last = save(last)
            except Exception as e:  # a failed upload is retried next round
                log(f"backup failed: {type(e).__name__}: {e}")
            time.sleep(EVERY)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "once")
