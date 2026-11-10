"""CLI.

    python -m data_platform seed                                  # synthetic SQLite for development
    python -m data_platform run --env dev                         # synthetic SQLite -> axiomdev_* datasets
    python -m data_platform run --env prod                        # Neon (read-only role) -> axiom_* datasets
    python -m data_platform dryrun --env prod                     # bytes each staging/mart/dq query would scan

Project: --project or AXIOM_GCP_PROJECT. --impersonate <service-account email> runs as that account
(least-privilege check; needs roles/iam.serviceAccountTokenCreator on it). Prod source: AXIOM_SOURCE_DATABASE_URL (backend/.env.data).
Exit codes: 0 ok (warnings allowed), 3 a critical data-quality check failed and the marts were not rebuilt.
"""

from __future__ import annotations

from data_platform import BACKEND_DIR, isolate_from_app_env

isolate_from_app_env()  # before anything imports axiom.config

import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from axiom.db import Db  # noqa: E402

from .config import Layout, load_config  # noqa: E402

SYNTHETIC_DB = BACKEND_DIR / ".cache" / "synthetic_state.db"


def _source(env: str) -> tuple[Db, str]:
    if env == "prod":
        url = os.environ.get("AXIOM_SOURCE_DATABASE_URL")
        if not url:
            sys.exit("AXIOM_SOURCE_DATABASE_URL is not set (put the read-only Neon URL in backend/.env.data)")
        return Db(url=url), "neon"
    if not SYNTHETIC_DB.exists():
        sys.exit(f"{SYNTHETIC_DB} missing: run `python -m data_platform seed` first")
    return Db(path=SYNTHETIC_DB), "sqlite:synthetic"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="data_platform")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--runs", type=int, default=80)
    for name in ("run", "dryrun"):
        p = sub.add_parser(name)
        p.add_argument("--env", choices=["dev", "prod"], default="dev")
        p.add_argument("--project", default=os.environ.get("AXIOM_GCP_PROJECT"))
        p.add_argument("--location", default="US")
        p.add_argument("--impersonate", metavar="SA_EMAIL", default=os.environ.get("AXIOM_IMPERSONATE"))
        if name == "run":
            p.add_argument("--no-prices", action="store_true")
            p.add_argument("--report", type=Path, help="write the run report as JSON here")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    if a.cmd == "seed":
        from .seed import seed

        counts = seed(SYNTHETIC_DB, n_runs=a.runs)
        print(json.dumps({"seeded": str(SYNTHETIC_DB), "rows": counts}))
        return 0

    if not a.project:
        sys.exit("--project or AXIOM_GCP_PROJECT is required")
    from .access import impersonated
    from .warehouse import BigQueryWarehouse

    creds = impersonated(a.impersonate) if a.impersonate else None
    wh, layout = BigQueryWarehouse(a.project, a.location, creds), Layout(a.project, a.env)

    if a.cmd == "dryrun":
        from . import dq
        from .models import models

        counts = {t: 0 for t in load_config().tables}
        out = {}
        for lr in ("staging", "mart", "dq"):
            for m in models(lr):
                if any(not wh.table_exists(layout.render(r)) for r in m.requires):
                    continue
                sql = dq.render(m, layout, counts) if lr == "dq" else layout.render(m.sql)
                out[f"{lr}.{m.name}"] = wh.dry_run_bytes(sql)
        print(json.dumps({"dry_run_bytes": out}, indent=2))
        return 0

    from dataclasses import asdict

    from .pipeline import run

    db, label = _source(a.env)
    rep = run(wh, layout, load_config(), db, source_label=label, with_prices=not a.no_prices)
    if a.report:
        a.report.write_text(
            json.dumps({**asdict(rep), "ok": rep.ok, "reconciled": rep.reconciled}, indent=2, default=str),
            "utf-8",
        )
    if not rep.ok:
        print(
            "PIPELINE STOPPED: critical data-quality checks failed; marts were not rebuilt:", file=sys.stderr
        )
        for f in rep.dq_failed_critical:
            print(f"  - {f}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
