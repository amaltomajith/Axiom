# Axiom Autopilot backtest

2023-06-13 to 2026-11-11 (3.41 years, 1248 bars). Universe: BTC/USD, ETH/USD, SPY, QQQ, AAPL, NVDA, MSFT. Starting cash $100,000. Generated 2026-11-11T12:13:37+00:00 by `python -m axiom.trading backtest`.

**Verdict: `no_edge`.** The agent did not beat buy-and-hold on risk-adjusted terms. Sharpe difference -0.728 (95% CI -1.407 to -0.032).

## Agent vs buy-and-hold

| | Agent | Buy-and-hold (equal weight) |
|---|---|---|
| Total return | +2.2% | +120.2% |
| CAGR | +0.6% | +26.0% |
| Volatility (ann.) | 11.3% | 27.1% |
| Sharpe | 0.11 | 0.99 |
| Sortino | 0.16 | 1.45 |
| Max drawdown | -18.8% | -31.3% |
| Calmar | 0.03 | 0.83 |
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

- Entries: 193; closed trades: 190; win rate 42.6%; profit factor 1.08.
- Average win $1,009.81, average loss -$693.47; fees and slippage paid $6,819.23; turnover 18.7x equity per year.

## Risk events

- Stop-losses hit: 56. Daily-loss halts: 9. Tournament leadership changes: 118.
- Entries the risk kernel blocked, by rule: R11 Cooldown after a stop-out: 46, R3 Daily loss limit: 10, R5 Mandatory stop-loss: 1, R9 Max open positions: 23.

## Trade contracts

- 190 contracts graded (grades: A 34, B 47, C 94, D 15). Brier score 0.266 against 0.25 for a coin flip; stated confidence averaged 57% and 43% ended in profit.

## Per symbol

| Symbol | Buy-and-hold | Agent realized P&L | Entries |
|---|---|---|---|
| BTC/USD | +184.9% | $6,298.27 | 31 |
| ETH/USD | +18.0% | -$985.92 | 22 |
| SPY | +79.4% | -$275.01 | 31 |
| QQQ | +89.5% | -$1,634.18 | 30 |
| AAPL | +93.0% | $4,065.44 | 27 |
| NVDA | +313.0% | $4,847.18 | 33 |
| MSFT | +63.6% | -$6,109.33 | 19 |

## Method and caveats

- **The Time Machine is the live engine.** The same `Engine.step`, risk kernel and brain run over history through a simulated broker. Orders fill at the next bar's open, never at the close that triggered them.
- **Costs.** Every fill pays fees plus slippage, in basis points per side: crypto 30, equity 10.
- **Risk limits.** 1.0% of equity at risk per trade, positions capped at 20%, daily loss limit 2%, stops 0.2% to 15% from price.
- **Brain used here: `rule`.** The LLM brain is deliberately excluded from historical backtests: a language model has read about these dates, so replaying it over the past would measure its memory, not its judgement. It is judged forward only, on paper, by its trade contracts.
- **Look-ahead.** Strategies, the tournament and every engine decision are tested for truncation invariance: a decision at bar t is identical whether or not later bars exist.
- **Universe bias.** The symbols were chosen today; companies that failed are not in the list.
- **Annualisation.** Sharpe in the tables uses the observed bars per year; the bootstrap verdict scales both sides alike, so its sign and confidence are unaffected.
- The journal of this run holds 790 hash-chained entries (head `b15d27212c2ffd95`).
