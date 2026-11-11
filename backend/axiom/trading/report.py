"""The backtest report: the agent against buy-and-hold and against each fixed strategy, with an honest verdict.

If the agent did not beat buy-and-hold, the report says so. The verdict is the same paired block-bootstrap
test the research agents use (`quant.backtest.make_verdict`).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from axiom.quant.backtest import apply_strategy, make_verdict

from .replay import ReplayResult
from .risk import RULE_NAMES
from .strategies import DESCRIPTIONS, TRADING_STRATEGIES
from .symbols import parse


def _date(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def metrics(equity: np.ndarray, years: float, periods_per_year: float, exposure: float | None = None) -> dict:
    r = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([0.0])
    total = float(equity[-1] / equity[0] - 1) if len(equity) else 0.0
    cagr = float((equity[-1] / equity[0]) ** (1 / years) - 1) if years > 0 and equity[-1] > 0 else 0.0
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    down = np.sqrt((np.minimum(r, 0) ** 2).mean()) if len(r) else 0.0
    peak = np.maximum.accumulate(equity)
    mdd = float((equity / peak - 1).min()) if len(equity) else 0.0
    ann = np.sqrt(periods_per_year)
    out = {
        "total_return": round(total, 4),
        "cagr": round(cagr, 4),
        "ann_vol": round(float(sd * ann), 4),
        "sharpe": round(float(r.mean() / sd * ann), 3) if sd > 0 else 0.0,
        "sortino": round(float(r.mean() / down * ann), 3) if down > 0 else 0.0,
        "max_drawdown": round(mdd, 4),
        "calmar": round(cagr / abs(mdd), 3) if mdd < 0 else None,
    }
    if exposure is not None:
        out["exposure"] = round(exposure, 4)
    return out


def _strategy_curve(res: ReplayResult, name: str, ts_grid: np.ndarray, cost: dict[str, float]) -> np.ndarray:
    """Equal-weight portfolio of one fixed strategy on every symbol, rebalanced each bar, on the replay grid."""
    rets = []
    for sym, b in res.books.items():
        close = pd.Series(b.close, index=b.ts)
        pos = pd.Series(b.signals[name] if name != "buy_and_hold" else np.ones(len(b)), index=b.ts)
        c = cost[parse(sym).kind]
        r = apply_strategy(close, pos, c / 2, c / 2)
        r = r[(r.index > res.start_ts) & (r.index <= res.end_ts)]
        rets.append(r.reindex(ts_grid[1:], fill_value=0.0).to_numpy())
    port = np.mean(rets, axis=0) if rets else np.zeros(len(ts_grid) - 1)
    return res.start_cash * np.concatenate([[1.0], np.cumprod(1 + port)])


def build_report(res: ReplayResult, *, title: str = "Axiom Autopilot backtest") -> dict:
    eng, led = res.engine, res.ledger
    curve = led.equity_curve(limit=10**7)
    ts = np.array([c["ts"] for c in curve])
    eq = np.array([c["equity"] for c in curve])
    bench = np.array([c["benchmark"] or res.start_cash for c in curve])
    years = max((res.end_ts - res.start_ts) / (365.25 * 86_400), 1e-9)
    ppy = len(ts) / years if years > 0 else 252
    exposure = float(np.mean([c["equity"] - c["cash"] > 1e-6 for c in curve])) if curve else 0.0
    agent_m = metrics(eq, years, ppy, exposure)
    bench_m = metrics(bench, years, ppy, 1.0)
    r_agent = pd.Series(np.diff(eq) / eq[:-1])
    r_bench = pd.Series(np.diff(bench) / bench[:-1])
    verdict = make_verdict(r_agent, r_bench)

    cost = eng.cfg.cost_bps
    fixed = {}
    for name in TRADING_STRATEGIES:
        c = _strategy_curve(res, name, ts, cost)
        fixed[name] = metrics(c, years, ppy)

    orders = led.orders(limit=10**7)
    exits = [o for o in orders if o["side"] == "sell" and o["status"] in ("filled", "partially_filled")]
    entries = [o for o in orders if o["side"] == "buy" and o["status"] in ("filled", "partially_filled")]
    pls = [o["realized_pl"] for o in exits if o.get("realized_pl") is not None]
    wins, losses = [p for p in pls if p > 0], [p for p in pls if p <= 0]
    journal = led.journal_all()
    kinds = Counter(e.kind for e in journal)
    blocked = Counter(e.facts.get("blocked_by") for e in journal if e.kind == "blocked")
    per_symbol = {}
    for sym, b in res.books.items():
        i0 = int(np.searchsorted(b.ts, res.start_ts))
        i1 = int(np.searchsorted(b.ts, res.end_ts, side="right")) - 1
        sym_pl = sum(o.get("realized_pl") or 0 for o in exits if o["symbol"] == sym)
        per_symbol[sym] = {
            "buy_and_hold_return": round(float(b.close[i1] / b.close[i0] - 1), 4) if i1 > i0 else None,
            "agent_realized_pl": round(sym_pl, 2),
            "trades": sum(1 for o in entries if o["symbol"] == sym),
        }
    step = max(1, len(ts) // 400)
    turnover = sum(o["filled_qty"] * (o["filled_avg_price"] or 0) for o in orders if o["filled_qty"]) / max(
        float(np.mean(eq)) if len(eq) else 1.0, 1.0
    )
    return {
        "title": title,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "session": res.session,
        "period": {
            "start": _date(res.start_ts),
            "end": _date(res.end_ts),
            "years": round(years, 2),
            "bars": int(len(ts)),
            "periods_per_year": round(ppy, 1),
        },  # fmt: skip
        "universe": list(res.books),
        "start_cash": res.start_cash,
        "agent": agent_m,
        "benchmark": bench_m,
        "verdict": verdict,
        "fixed_strategies": fixed,
        "trades": {
            "entries": len(entries),
            "closed": len(pls),
            "win_rate": round(len(wins) / len(pls), 3) if pls else None,
            "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses and sum(losses) != 0 else None,
            "avg_win": round(float(np.mean(wins)), 2) if wins else None,
            "avg_loss": round(float(np.mean(losses)), 2) if losses else None,
            "fees_paid": round(res.broker.fees_paid, 2),
            "turnover_x": round(turnover / years, 2),
        },
        "risk_events": {
            "stop_outs": kinds.get("stop", 0),
            "daily_loss_halts": kinds.get("halt", 0),
            "blocked": {k: v for k, v in blocked.items() if k},
            "tournament_changes": kinds.get("tournament", 0),
        },
        "per_symbol": per_symbol,
        "limits": eng.kernel.limits.to_dict(),
        "assumptions": {
            "fills": "market orders fill at the next bar's open; stops fill at the stop or the open if it gapped",
            "costs_bps": {k: v for k, v in cost.items()},
            "brain": eng.brain.name,
        },
        "curve": [
            {"date": _date(t), "agent": round(float(a), 2), "benchmark": round(float(b), 2)}
            for t, a, b in zip(ts[::step], eq[::step], bench[::step], strict=True)
        ],
        "journal_head": journal[-1].hash if journal else None,
        "journal_entries": len(journal),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def _share(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _usd(x: float | None) -> str:
    return "n/a" if x is None else f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def _num(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def render_markdown(rep: dict) -> str:
    a, b, v, p = rep["agent"], rep["benchmark"], rep["verdict"], rep["period"]
    ci = v["sharpe_diff_ci95"]
    headline = {
        "edge_detected": "The agent beat buy-and-hold on risk-adjusted terms with 95% bootstrap confidence.",
        "unproven": "The agent had a higher Sharpe than buy-and-hold, but the difference is not statistically "
        "distinguishable from luck.",
        "no_edge": "The agent did not beat buy-and-hold on risk-adjusted terms.",
        "insufficient_data": "Not enough history for a verdict.",
    }[v["verdict"]]
    lines = [
        f"# {rep['title']}",
        "",
        f"{p['start']} to {p['end']} ({p['years']} years, {p['bars']} bars). Universe: {', '.join(rep['universe'])}. "
        f"Starting cash ${rep['start_cash']:,.0f}. Generated {rep['generated_at']} by "
        "`python -m axiom.trading backtest`.",
        "",
        f"**Verdict: `{v['verdict']}`.** {headline} Sharpe difference {v['sharpe_diff']} "
        f"(95% CI {ci[0]} to {ci[1]}).",
        "",
        "## Agent vs buy-and-hold",
        "",
        "| | Agent | Buy-and-hold (equal weight) |",
        "|---|---|---|",
        f"| Total return | {_pct(a['total_return'])} | {_pct(b['total_return'])} |",
        f"| CAGR | {_pct(a['cagr'])} | {_pct(b['cagr'])} |",
        f"| Volatility (ann.) | {_share(a['ann_vol'])} | {_share(b['ann_vol'])} |",
        f"| Sharpe | {_num(a['sharpe'])} | {_num(b['sharpe'])} |",
        f"| Sortino | {_num(a['sortino'])} | {_num(b['sortino'])} |",
        f"| Max drawdown | {_pct(a['max_drawdown'])} | {_pct(b['max_drawdown'])} |",
        f"| Calmar | {_num(a['calmar'])} | {_num(b['calmar'])} |",
        f"| Time in market | {_share(a['exposure'])} | {_share(b['exposure'])} |",
        "",
        "## Against each fixed strategy (equal weight, same costs, no risk kernel)",
        "",
        "| Strategy | Total return | Sharpe | Max drawdown | What it does |",
        "|---|---|---|---|---|",
    ]
    for name, m in rep["fixed_strategies"].items():
        lines.append(
            f"| {name} | {_pct(m['total_return'])} | {_num(m['sharpe'])} | {_pct(m['max_drawdown'])} | "
            f"{DESCRIPTIONS.get(name, '')} |"
        )
    t, r = rep["trades"], rep["risk_events"]
    blocked = ", ".join(f"{k} {RULE_NAMES.get(k, k)}: {n}" for k, n in sorted(r["blocked"].items())) or "none"
    lines += [
        "",
        "## Trades",
        "",
        f"- Entries: {t['entries']}; closed trades: {t['closed']}; win rate {_share(t['win_rate'])}; "
        f"profit factor {_num(t['profit_factor'])}.",
        f"- Average win {_usd(t['avg_win'])}, average loss {_usd(t['avg_loss'])}; fees and slippage paid "
        f"{_usd(t['fees_paid'])}; turnover {t['turnover_x']}x equity per year.",
        "",
        "## Risk events",
        "",
        f"- Stop-losses hit: {r['stop_outs']}. Daily-loss halts: {r['daily_loss_halts']}. "
        f"Tournament leadership changes: {r['tournament_changes']}.",
        f"- Entries the risk kernel blocked, by rule: {blocked}.",
        "",
        "## Per symbol",
        "",
        "| Symbol | Buy-and-hold | Agent realized P&L | Entries |",
        "|---|---|---|---|",
    ]
    for s, m in rep["per_symbol"].items():
        lines.append(
            f"| {s} | {_pct(m['buy_and_hold_return'])} | {_usd(m['agent_realized_pl'])} | {m['trades']} |"
        )
    lim = rep["limits"]
    lines += [
        "",
        "## Method and caveats",
        "",
        "- **The Time Machine is the live engine.** The same `Engine.step`, risk kernel and brain run over history "
        "through a simulated broker. Orders fill at the next bar's open, never at the close that triggered them.",
        f"- **Costs.** Every fill pays fees plus slippage, in basis points per side: "
        f"{', '.join(f'{k} {v:g}' for k, v in rep['assumptions']['costs_bps'].items())}.",
        f"- **Risk limits.** {lim['risk_per_trade']:.1%} of equity at risk per trade, positions capped at "
        f"{lim['max_position_pct']:.0%}, daily loss limit {lim['daily_loss_limit_pct']:.0%}, stops "
        f"{lim['min_stop_pct']:.1%} to {lim['max_stop_pct']:.0%} from price.",
        f"- **Brain used here: `{rep['assumptions']['brain']}`.** The LLM brain is deliberately excluded from "
        "historical backtests: a language model has read about these dates, so replaying it over the past would "
        "measure its memory, not its judgement. It is judged forward only, on paper, by its trade contracts.",
        "- **Look-ahead.** Strategies, the tournament and every engine decision are tested for truncation "
        "invariance: a decision at bar t is identical whether or not later bars exist.",
        "- **Universe bias.** The symbols were chosen today; companies that failed are not in the list.",
        "- **Annualisation.** Sharpe in the tables uses the observed bars per year; the bootstrap verdict scales "
        "both sides alike, so its sign and confidence are unaffected.",
        f"- The journal of this run holds {rep['journal_entries']} hash-chained entries (head "
        f"`{(rep['journal_head'] or '')[:16]}`).",
        "",
    ]
    return "\n".join(lines)
