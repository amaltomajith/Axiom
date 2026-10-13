import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n: int = 800, seed: int = 1, drift: float = 0.0003, vol: float = 0.012) -> pd.DataFrame:
    """Seeded geometric random walk with plausible OHLCV structure."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, n))
    volume = rng.integers(1_000_000, 5_000_000, n)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return make_ohlcv()


# One long fixed series that every fake data call slices, so all tools in a run agree on the price history.
FIXED_WORLD = make_ohlcv(1400, seed=7, drift=0.0004)


def world_slice(bars: int):
    return FIXED_WORLD.iloc[-bars:]
