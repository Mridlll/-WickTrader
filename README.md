# WickTrader - Wick-Based SOL Trading Strategy

A quantitative trading strategy that identifies high-probability reversal opportunities based on candlestick lower wick patterns on SOL/USDT 4H timeframe.

## Strategy Performance

**Backtest Period**: January 2025 - January 2026 (1 year)

| Metric | Value |
|--------|-------|
| Total Return | **+39.7%** |
| Win Rate | 62.5% |
| Total Trades | 8 |
| Max Drawdown | 27.6% |
| Starting Capital | $10,000 |
| Final Capital | $13,969 |

## Optimal Configuration

Based on comprehensive grid search (192 parameter combinations tested):

| Parameter | Value | Notes |
|-----------|-------|-------|
| Asset | SOL/USDT | Solana perpetual futures |
| Timeframe | 4H | 4-hour candles only |
| Wick Threshold | **5.0%** | Lower wick >= 5% of candle height |
| Direction | **Long Only** | Bearish wicks unreliable |
| Exit Strategy | **Max 30 bars** OR 15% TP | Time-based exit outperforms |
| Stop Loss | **Wick Low** | Below candle low (0.5% buffer) |
| Leverage | **3X** | Optimal risk/reward |
| Risk Per Trade | **10%** | 8 trades/year needs position size |

## What Works vs What Fails

### Works
- 5%+ wick threshold (filters noise)
- Long-only direction (bearish wicks unreliable)
- Wick-based stop loss (below candle low)
- 30-bar max hold (lets winners run)
- 3X leverage (optimal risk/reward)

### Fails
- 1.5-3.5% threshold (too many false signals, ~25% win rate)
- Fixed % stop loss (destroys edge - tested -46% avg return)
- 1H timeframe (40% win rate, -16% return)
- R:R based exits (too ambitious targets)
- 7X+ leverage (account blowup risk - tested -80% to -98%)
- Both directions (shorts underperform)

## Grid Search Results

### Top Entry/Exit Combinations
\`\`\`
 Entry | Exit Strategy    | SL Type      | Trades |  Win% |   Return
-------------------------------------------------------------------------
  5.0% | Max 30 bars      | Wick SL      |      8 | 62.5% |   +39.7%
  5.0% | Fixed 10% TP     | Wick SL      |      8 | 62.5% |   +36.2%
  5.0% | Trail @10%       | Wick SL      |      8 | 62.5% |   +30.4%
  5.0% | Fixed 12% TP     | Wick SL      |      8 | 62.5% |   +29.7%
  4.5% | Max 30 bars      | Wick SL      |      9 | 55.6% |   +25.3%
\`\`\`

### Leverage Testing
| Leverage | Return | Max DD | Verdict |
|----------|--------|--------|---------|
| 2X | +42.2% | 38.4% | Safe |
| **3X** | **+55.0%** | **53.3%** | **Optimal** |
| 5X | +54.2% | 75.7% | Same return, more risk |
| 7X | -80.8% | 98.3% | Nearly blown |
| 10X | -98.3% | 99.9% | Account destroyed |

## Trade-by-Trade Log

\`\`\`
Date       | Wick% | Result | PnL       | Notes
--------------------------------------------------
2025-01-18 |  5.1% | WIN    | +\$2,653   | +26.5%
2025-01-19 |  5.9% | LOSS   | -\$1,294   | Immediate reversal
2025-02-02 |  5.7% | LOSS   | -\$1,163   | Feb crash
2025-03-04 |  5.6% | LOSS   | -\$1,036   | March bottom
2025-03-11 |  5.4% | WIN    | +\$1,615   | Caught the bounce
2025-10-10 | 24.7% | WIN    | +\$132     | Huge wick, small move
2025-11-04 |  5.7% | WIN    | +\$1,004   |
2025-11-21 |  5.0% | WIN    | +\$2,056   |
\`\`\`

## Installation

\`\`\`bash
# Clone repository
git clone https://github.com/Mridlll/-WickTrader.git
cd WickTrader

# Install dependencies
pip install -r requirements.txt
\`\`\`

## Usage

### Run Backtest

\`\`\`bash
# Full grid search (192 combinations)
python backtest/full_grid_search.py

# Generate detailed report
python backtest/generate_report.py

# Single configuration test
python backtest/run_wick_backtest.py
\`\`\`

### Configuration

Edit \`config/wick_strategy.yaml\`:

\`\`\`yaml
strategy:
  wick_threshold: 0.05      # 5% minimum wick
  direction: long_only
  exit_strategy: max_bars   # or: fixed_tp, trailing
  max_hold_bars: 30
  take_profit: 0.15         # 15% TP

risk:
  leverage: 3
  risk_per_trade: 0.10      # 10% of portfolio
  stop_loss_type: wick      # wick-based, not fixed %
\`\`\`

## Project Structure

\`\`\`
WickTrader/
├── src/
│   ├── indicators/
│   │   └── wick.py              # Wick calculation
│   ├── strategy/
│   │   ├── wick_signals.py      # Signal detection
│   │   └── wick_risk.py         # Position sizing
│   └── exchanges/
│       ├── binance.py           # Binance adapter
│       └── hyperliquid.py       # Hyperliquid adapter
├── backtest/
│   ├── wick_engine.py           # Backtest engine
│   ├── run_wick_backtest.py     # Quick backtest runner
│   ├── full_grid_search.py      # 192-combo optimizer
│   └── generate_report.py       # Report generator
├── config/
│   └── wick_strategy.yaml       # Strategy configuration
└── data/
    └── sol_4h/                  # Historical data cache
\`\`\`

## Exchanges Supported

- **Binance Futures** - Data fetching + execution
- **Hyperliquid** - Execution only

## Key Insights

1. **Wick-based SL is mandatory** - Fixed % stop loss (-46% avg) destroys the edge vs wick-based (+39.7%)

2. **5% threshold filters noise** - Lower thresholds (1.5-3.5%) catch too many false signals

3. **Let winners run** - Time-based exit (30 bars) outperforms fixed TP targets

4. **3X leverage is the sweet spot** - Same returns as 5X but half the drawdown

5. **Long only** - Bullish wick signals have much better follow-through than bearish

## License

MIT

## Disclaimer

This software is for educational and research purposes only. Trading cryptocurrencies involves substantial risk of loss. Past backtest performance does not guarantee future results. Never trade with money you cannot afford to lose.
