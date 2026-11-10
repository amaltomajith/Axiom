"""Input data for the Spark benchmark.

Real data: the Federal Reserve Board's H.10 daily exchange rates (noon buying rates in New York), from the
Board's own site, https://www.federalreserve.gov/releases/h10/hist/ . The Board's website disclaimer says that,
unless otherwise indicated, information on its site "is in the public domain and may be copied and distributed
without permission", and asks to be cited as the source. Citation: Board of Governors of the Federal Reserve
System (US), H.10 Foreign Exchange Rates.

Synthetic data (for scale only, labelled as such): geometric Brownian motion with a fixed seed.
"""

from __future__ import annotations

import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

URL = "https://www.federalreserve.gov/releases/h10/hist/dat00_{code}.htm"
# Every currency listed on the H.10 historical-data index page (checked 2026-11-10).
CODES = ("al bz ca ch dn eu gr hk in ja ko ma mx no nz sd sf si sl sz ta th uk ve").split()
_ROW = re.compile(
    r'<th[^>]*headers="a1"[^>]*>\s*(\d{1,2}-[A-Z]{3}-\d{2})\s*</th>\s*<td[^>]*>\s*([^<]*?)\s*</td>'
)
USER_AGENT = "axiom-data-platform/0.1 (research benchmark)"


def parse_h10(html: str) -> list[tuple[str, float]]:
    """(ISO date, rate) pairs from one H.10 history page. 'ND' (no data: a holiday) rows are skipped."""
    out = []
    for day, value in _ROW.findall(html):
        try:
            rate = float(value)
        except ValueError:
            continue
        out.append((datetime.strptime(day.title(), "%d-%b-%y").date().isoformat(), rate))
    return out


def download_h10(cache: Path, *, pause: float = 1.0) -> pd.DataFrame:
    """All H.10 currencies since 2000 as long rows (series, date, close). Raw pages are cached locally."""
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for code in CODES:
        page = cache / f"dat00_{code}.htm"
        if not page.exists():
            req = urllib.request.Request(URL.format(code=code), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                page.write_bytes(r.read())
            time.sleep(pause)  # be polite to the Board's site
        rows = parse_h10(page.read_text(encoding="utf-8", errors="replace"))
        frames.append(pd.DataFrame(rows, columns=["date", "close"]).assign(series=f"h10_{code}"))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["series", "date", "close"]].sort_values(["series", "date"], ignore_index=True)


def synthetic(n_series: int, n_days: int, seed: int = 7) -> pd.DataFrame:
    """GBM closes on business days from 2000-01-03, annual drift 5% and volatility 20%."""
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    shocks = rng.standard_normal((n_series, n_days)) * 0.2 * np.sqrt(dt) + (0.05 - 0.02) * dt
    closes = 100 * np.exp(np.cumsum(shocks, axis=1))
    dates = pd.bdate_range("2000-01-03", periods=n_days).date
    return pd.DataFrame(
        {
            "series": np.repeat([f"syn_{i:05d}" for i in range(n_series)], n_days),
            "date": np.tile(dates, n_series),
            "close": closes.ravel(),
        }
    )
