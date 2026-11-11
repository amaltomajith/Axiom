# Axiom Autopilot backtest

2023-06-13 to 2026-11-11 (3.41 years, 1248 bars). Universe: BTC/USD, ETH/USD, SPY, QQQ, AAPL, NVDA, MSFT. Starting cash $100,000. Generated 2026-11-11T16:57:01+00:00 by `python -m axiom.trading backtest`.

**Verdict: `no_edge`.** The agent did not beat buy-and-hold on risk-adjusted terms. Sharpe difference -0.69 (95% CI -1.321 to -0.057).

## Agent vs buy-and-hold

| | Agent | Buy-and-hold (equal weight) |
|---|---|---|
| Total return | +4.9% | +123.8% |
| CAGR | +1.4% | +26.6% |
| Volatility (ann.) | 12.3% | 27.1% |
| Sharpe | 0.18 | 1.01 |
| Sortino | 0.25 | 1.48 |
| Max drawdown | -23.4% | -31.3% |
| Calmar | 0.06 | 0.85 |
| Time in market | 94.2% | 100.0% |

## Against each fixed strategy (equal weight, same costs, no risk kernel)

| Strategy | Total return | Sharpe | Max drawdown | What it does |
|---|---|---|---|---|
| sma_cross | +80.4% | 1.22 | -14.8% | trend following: long while the 20-bar average is above the 50-bar average |
| macd_trend | +24.7% | 0.55 | -26.0% | momentum: long while MACD is above its signal line |
| rsi_reversion | +14.0% | 0.38 | -14.8% | mean reversion: buy when RSI(14) drops below 30, sell when it recovers above 55 |
| donchian_breakout | +33.5% | 0.76 | -21.5% | breakout: buy a close above the 20-bar high, sell a close below the 10-bar low |
| bollinger_reversion | +23.8% | 0.52 | -14.3% | mean reversion: buy a close below the lower Bollinger band, sell above the middle |

## Trades

- Entries: 182; closed trades: 178; win rate 42.7%; profit factor 1.12.
- Average win $1,006.00, average loss -$667.79; fees and slippage paid $6,455.28; turnover 17.74x equity per year.

## Risk events

- Stop-losses hit: 53. Daily-loss halts: 5. Tournament leadership changes: 118.
- Entries the risk kernel blocked, by rule: R11 Cooldown after a stop-out: 42, R3 Daily loss limit: 5, R5 Mandatory stop-loss: 1, R9 Max open positions: 24.

## Trade contracts

- 178 contracts graded (grades: A 35, B 41, C 93, D 9). Brier score 0.266 against 0.25 for a coin flip; stated confidence averaged 57% and 43% ended in profit.

## Per symbol

| Symbol | Buy-and-hold | Agent realized P&L | Entries |
|---|---|---|---|
| BTC/USD | +185.9% | $6,641.80 | 28 |
| ETH/USD | +19.2% | -$2,090.45 | 21 |
| SPY | +81.7% | -$566.52 | 30 |
| QQQ | +94.5% | $672.51 | 29 |
| AAPL | +96.2% | $4,424.34 | 24 |
| NVDA | +329.7% | $4,061.38 | 31 |
| MSFT | +59.7% | -$4,801.52 | 19 |

## Method and caveats

- **The Time Machine is the live engine.** The same `Engine.step`, risk kernel and brain run over history through a simulated broker. Orders fill at the next bar's open, never at the close that triggered them.
- **Costs.** Every fill pays fees plus slippage, in basis points per side: crypto 30, equity 10.
- **Risk limits.** 1.0% of equity at risk per trade, positions capped at 20%, daily loss limit 2%, stops 0.2% to 15% from price.
- **Brain used here: `rule`.** The LLM brain is deliberately excluded from historical backtests: a language model has read about these dates, so replaying it over the past would measure its memory, not its judgement. It is judged forward only, on paper, by its trade contracts.
- **Look-ahead.** Strategies, the tournament and every engine decision are tested for truncation invariance: a decision at bar t is identical whether or not later bars exist.
- **Universe bias.** The symbols were chosen today; companies that failed are not in the list.
- **Annualisation.** Sharpe in the tables uses the observed bars per year; the bootstrap verdict scales both sides alike, so its sign and confidence are unaffected.
- The journal of this run holds 738 hash-chained entries (head `906fe4c701eb2375`).
