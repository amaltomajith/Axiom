# Axiom Autopilot backtest

2023-06-13 to 2026-11-11 (3.41 years, 1248 bars). Universe: BTC/USD, ETH/USD, SPY, QQQ, AAPL, NVDA, MSFT. Starting cash $100,000. Generated 2026-11-11T11:47:29+00:00 by `python -m axiom.trading backtest`.

**Verdict: `no_edge`.** The agent did not beat buy-and-hold on risk-adjusted terms. Sharpe difference -0.471 (95% CI -1.078 to 0.161).

## Agent vs buy-and-hold

| | Agent | Buy-and-hold (equal weight) |
|---|---|---|
| Total return | +15.4% | +120.2% |
| CAGR | +4.3% | +26.0% |
| Volatility (ann.) | 11.5% | 27.1% |
| Sharpe | 0.42 | 0.99 |
| Sortino | 0.62 | 1.45 |
| Max drawdown | -18.0% | -31.3% |
| Calmar | 0.24 | 0.83 |
| Time in market | 93.7% | 100.0% |

## Against each fixed strategy (equal weight, same costs, no risk kernel)

| Strategy | Total return | Sharpe | Max drawdown | What it does |
|---|---|---|---|---|
| sma_cross | +80.6% | 1.22 | -14.8% | trend following: long while the 20-bar average is above the 50-bar average |
| macd_trend | +24.7% | 0.55 | -26.0% | momentum: long while MACD is above its signal line |
| rsi_reversion | +12.8% | 0.35 | -14.8% | mean reversion: buy when RSI(14) drops below 30, sell when it recovers above 55 |
| donchian_breakout | +34.0% | 0.76 | -21.5% | breakout: buy a close above the 20-bar high, sell a close below the 10-bar low |
| bollinger_reversion | +22.2% | 0.50 | -14.3% | mean reversion: buy a close below the lower Bollinger band, sell above the middle |

## Trades

- Entries: 177; closed trades: 174; win rate 46.6%; profit factor 1.27.
- Average win $1,120.28, average loss -$765.66; fees and slippage paid $6,928.33; turnover 17.21x equity per year.

## Risk events

- Stop-losses hit: 49. Daily-loss halts: 8. Tournament leadership changes: 101.
- Entries the risk kernel blocked, by rule: R11 Cooldown after a stop-out: 37, R3 Daily loss limit: 11, R5 Mandatory stop-loss: 1, R9 Max open positions: 28.

## Per symbol

| Symbol | Buy-and-hold | Agent realized P&L | Entries |
|---|---|---|---|
| BTC/USD | +185.3% | $9,379.65 | 29 |
| ETH/USD | +18.1% | $33.18 | 22 |
| SPY | +79.4% | $2,641.30 | 26 |
| QQQ | +89.5% | -$1,113.72 | 28 |
| AAPL | +93.0% | $4,288.40 | 21 |
| NVDA | +313.0% | $9,870.83 | 32 |
| MSFT | +63.6% | -$5,563.49 | 19 |

## Method and caveats

- **The Time Machine is the live engine.** The same `Engine.step`, risk kernel and brain run over history through a simulated broker. Orders fill at the next bar's open, never at the close that triggered them.
- **Costs.** Every fill pays fees plus slippage, in basis points per side: crypto 30, equity 10.
- **Risk limits.** 1.0% of equity at risk per trade, positions capped at 20%, daily loss limit 2%, stops 0.2% to 15% from price.
- **Brain used here: `rule`.** The LLM brain is deliberately excluded from historical backtests: a language model has read about these dates, so replaying it over the past would measure its memory, not its judgement. It is judged forward only, on paper, by its trade contracts.
- **Look-ahead.** Strategies, the tournament and every engine decision are tested for truncation invariance: a decision at bar t is identical whether or not later bars exist.
- **Universe bias.** The symbols were chosen today; companies that failed are not in the list.
- **Annualisation.** Sharpe in the tables uses the observed bars per year; the bootstrap verdict scales both sides alike, so its sign and confidence are unaffected.
- The journal of this run holds 545 hash-chained entries (head `3b5634444fe27243`).
