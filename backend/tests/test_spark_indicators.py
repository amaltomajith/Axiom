"""The Spark job's pieces that run without Spark: the H.10 parser and the independent Wilder RSI.
The full Spark-vs-Axiom comparison on real and synthetic data is `python -m data_platform.spark.bench`."""

import numpy as np
import pandas as pd

from axiom.quant.indicators import rsi
from data_platform.spark.fx_data import parse_h10, synthetic
from data_platform.spark.indicators_job import wilder_rsi_values

# Shape copied from https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm (2026-11-10)
PAGE = """
<tr><th scope=col>Date</th><th scope=col>Rate</th></tr>
<tr><th id="r1" headers="a1"> 3-JAN-00 </th>
<td headers="a2 a1 r1">              1.0155                                                  </td></tr>
<tr><th id="r1" headers="a1"> 17-JAN-00 </th>
<td headers="a2 a1 r1">              ND                                                  </td></tr>
<tr><th id="r1" headers="a1"> 6-NOV-26 </th>
<td headers="a2 a1 r1">              1.1154                                                  </td></tr>
"""


def test_h10_parser_reads_rates_and_skips_holidays():
    assert parse_h10(PAGE) == [("2000-01-03", 1.0155), ("2026-11-06", 1.1154)]


def test_spark_rsi_matches_axiom_rsi():
    rng = np.random.default_rng(0)
    for close in (
        100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600))),
        np.r_[np.full(20, 5.0), np.linspace(5, 9, 30)],  # flat then only gains: the 50 and 100 branches
        np.linspace(10, 1, 40),  # only losses
        np.arange(10.0),  # shorter than the period
    ):
        expected = rsi(pd.Series(close), 14).to_numpy()
        got = wilder_rsi_values(close)
        assert np.array_equal(np.isnan(expected), np.isnan(got))
        assert np.nanmax(np.abs(expected - got), initial=0.0) < 1e-9


def test_synthetic_set_is_deterministic():
    a, b = synthetic(3, 50), synthetic(3, 50)
    assert len(a) == 150 and a.equals(b) and (a["close"] > 0).all()
