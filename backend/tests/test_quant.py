import numpy as np
import pandas as pd
import pytest

from axiom.quant import backtest as bt
from axiom.quant import forecast, regime, risk
from axiom.quant import indicators as ind

from .conftest import make_ohlcv

# Wilder's classic RSI(14) worked example (closes) and the published values.
WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
    45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45,
    45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13,
]  # fmt: skip


def test_rsi_matches_wilder_reference():
    r = ind.rsi(pd.Series(WILDER_CLOSES))
    assert r.iloc[:14].isna().all()
    assert r.iloc[14] == pytest.approx(70.53, abs=0.1)
    assert r.iloc[15] == pytest.approx(66.32, abs=0.1)
    assert r.iloc[16] == pytest.approx(66.55, abs=0.1)


def test_rsi_bounds_and_degenerate_cases():
    assert ind.rsi(pd.Series(np.arange(1.0, 40.0))).dropna().eq(100).all()  # only gains
    assert ind.rsi(pd.Series(np.full(40, 5.0))).dropna().eq(50).all()  # flat
    r = ind.rsi(make_ohlcv()["close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_ema_seed_and_recursion():
    s = pd.Series([1.0, 2, 3, 4, 5, 6])
    e = ind.ema(s, 3)
    assert e.iloc[:2].isna().all()
    assert e.iloc[2] == pytest.approx(2.0)  # SMA seed
    assert e.iloc[3] == pytest.approx(0.5 * 4 + 0.5 * 2.0)  # alpha = 2/(3+1)


def test_macd_identity(ohlcv):
    m = ind.macd(ohlcv["close"])
    assert (m["hist"] - (m["macd"] - m["signal"])).abs().dropna().max() < 1e-12
    assert m["signal"].first_valid_index() == ohlcv.index[25 + 8]  # slow(26) + signal(9) - 2


def test_bollinger_uses_population_std():
    s = pd.Series([1.0, 2, 3, 4, 5])
    b = ind.bollinger(s, period=5, num_std=2)
    assert b["mid"].iloc[-1] == 3.0
    assert b["upper"].iloc[-1] == pytest.approx(3 + 2 * np.sqrt(2))  # std(ddof=0) = sqrt(2)


def test_atr_constant_range():
    n = 40
    high, low = pd.Series(np.full(n, 11.0)), pd.Series(np.full(n, 9.0))
    close = pd.Series(np.full(n, 10.0))
    assert ind.atr(high, low, close).dropna().iloc[-1] == pytest.approx(2.0)


def test_snapshot_keys(ohlcv):
    snap = ind.indicator_snapshot(ohlcv)
    assert snap["rsi14"] is not None and 0 <= snap["rsi14"] <= 100
    assert snap["sma200"] is not None


def test_regime_detects_trend_direction():
    up = make_ohlcv(400, seed=3, drift=0.004, vol=0.004)["close"]
    down = make_ohlcv(400, seed=3, drift=-0.004, vol=0.004)["close"]
    assert regime.classify(up)["trend"] == "uptrend"
    assert regime.classify(down)["trend"] == "downtrend"
    assert regime.classify(up.iloc[:20])["trend"] == "insufficient_data"


# --------------------------------------------------------------------------- backtest engine


@pytest.mark.parametrize("name", ["sma_cross", "macd_trend", "rsi_reversion"])
def test_strategies_are_causal(ohlcv, name):
    """Position at t must not change if data after t is removed (no lookahead)."""
    fn = bt.STRATEGIES[name]
    full = fn(ohlcv)
    for cut in (300, 450, 600):
        truncated = fn(ohlcv.iloc[:cut])
        pd.testing.assert_series_equal(full.iloc[:cut], truncated, check_names=False)


def test_position_is_executed_next_bar():
    close = pd.Series([100.0, 110.0, 99.0, 99.0], index=pd.bdate_range("2024-01-01", periods=4))
    pos = pd.Series([1.0, 0.0, 0.0, 0.0], index=close.index)  # long decided at close of day 0
    r = bt.apply_strategy(close, pos, cost_bps=0, slippage_bps=0)
    assert r.iloc[0] == 0.0
    assert r.iloc[1] == pytest.approx(0.10)  # earns day0 -> day1
    assert r.iloc[2] == 0.0  # flat after exit at close of day 1


def test_costs_reduce_returns(ohlcv):
    pos = bt.sma_cross(ohlcv)
    free = bt.apply_strategy(ohlcv["close"], pos, 0, 0)
    paid = bt.apply_strategy(ohlcv["close"], pos, 25, 25)
    assert paid.sum() < free.sum()


def test_metrics_known_values():
    r = pd.Series([0.1, -0.1, 0.1, -0.1])
    m = bt.compute_metrics(r)
    assert m.total_return == pytest.approx(1.1 * 0.9 * 1.1 * 0.9 - 1)
    assert m.max_drawdown == pytest.approx(0.9801 / 1.1 - 1)  # peak 1.1 -> trough 0.9801
    assert m.hit_rate == 0.5


def test_buy_and_hold_vs_itself_is_not_an_edge(ohlcv):
    out = bt.run_backtest(ohlcv, "buy_and_hold")
    assert out["verdict"] in {"no_edge", "unproven"}
    assert out["sharpe_diff"] == pytest.approx(0.0, abs=1e-9)


def test_verdict_requires_enough_data():
    out = bt.run_backtest(make_ohlcv(120), "sma_cross")
    assert out["verdict"] == "insufficient_data"


def test_random_walk_rules_do_not_show_edge():
    """On pure noise, the rule-based strategies should not be declared edges (multiple seeds)."""
    edges = 0
    for seed in range(8):
        df = make_ohlcv(1000, seed=seed + 100, drift=0.0)
        for name in ("sma_cross", "macd_trend", "rsi_reversion"):
            edges += bt.run_backtest(df, name)["verdict"] == "edge_detected"
    assert edges <= 2  # 24 trials at ~2.5% one-sided FPR; allow slack, flag gross leakage


def test_walk_forward_has_no_lookahead(ohlcv):
    """Mutating prices after row k must not change any prediction made at or before row k."""
    base, _ = bt.walk_forward_predictions(ohlcv)
    k = 600
    mutated = ohlcv.copy()
    rng = np.random.default_rng(0)
    shock = rng.uniform(0.5, 1.5, len(ohlcv) - k - 1)
    mutated.iloc[k + 1 :, mutated.columns.get_loc("close")] *= shock
    alt, _ = bt.walk_forward_predictions(mutated)
    # predictions for rows <= k use a model fit on rows < refit start <= k; features use data <= row
    pd.testing.assert_series_equal(base.iloc[: k + 1], alt.iloc[: k + 1])
    assert base.iloc[: k + 1].notna().sum() > 0


def test_walk_forward_on_noise_reports_no_skill():
    df = make_ohlcv(1200, seed=11, drift=0.0)
    out = bt.walk_forward_ridge(df)
    assert out["model_skill"]["oos_r2_vs_zero"] < 0.01  # cannot predict a random walk
    assert out["verdict"] != "edge_detected"


# --------------------------------------------------------------------------- forecast & risk


def test_cone_is_ordered_and_widens(ohlcv):
    c = forecast.forecast_cone(ohlcv["close"], horizon=10)
    for step in c["cone"]:
        assert step["p10"] <= step["p25"] <= step["p50"] <= step["p75"] <= step["p90"]
    assert c["cone"][-1]["p90"] - c["cone"][-1]["p10"] > c["cone"][0]["p90"] - c["cone"][0]["p10"]


def test_cone_coverage_is_calibrated_on_iid_returns():
    df = make_ohlcv(1500, seed=21)
    cov = forecast.coverage_check(df["close"], horizon=10)
    assert cov["n_checks"] >= 30
    assert abs(cov["empirical_coverage"] - 0.8) < 0.1


def test_var_cvar_ordering(ohlcv):
    out = risk.historical_var_cvar(ohlcv["close"].pct_change())
    assert out["cvar_1d"] >= out["var_1d"] > 0


def test_position_sizing_respects_constraints():
    s = risk.size_position(equity=100_000, price=50, atr=2, risk_per_trade=0.01, stop_atr_mult=2)
    assert s["shares"] == 250  # risk: 1000 / 4
    assert s["risk_pct_of_equity"] <= 0.01 + 1e-9
    assert s["binding_constraint"] == "risk_per_trade"
    capped = risk.size_position(100_000, 100, 0.1, 0.01, 2, max_position_pct=0.2)
    assert capped["position_pct"] <= 0.2 and capped["binding_constraint"] == "max_position_pct"
    with pytest.raises(ValueError):
        risk.size_position(0, 100, 2)


def test_limit_checker():
    issues = risk.check_limits({"AAPL": 30_000, "TSLA": 10_000}, 100_000, 0.2, 1.0)
    assert len(issues) == 1 and "AAPL" in issues[0]


def test_directional_skill_is_judged_against_majority_baseline():
    """In a strong uptrend 'always up' is right most of the time; that must not read as skill."""
    df = make_ohlcv(1200, seed=5, drift=0.002, vol=0.006)
    skill = bt.walk_forward_ridge(df)["model_skill"]
    assert skill["naive_majority_accuracy"] > 0.55
    assert (
        skill["interpretation"]
        != "some out-of-sample skill; defer to the bootstrap verdict before trusting it"
    )


def test_cone_widens_with_current_volatility():
    calm = make_ohlcv(600, seed=9, vol=0.005)["close"]
    shock = calm.copy()
    shock.iloc[-15:] = calm.iloc[-16] * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.04, 15)))
    width = lambda s: (lambda c: c["cone"][-1]["p90"] / c["cone"][-1]["p10"])(forecast.forecast_cone(s, 10))  # noqa: E731
    assert width(shock) > width(calm)
