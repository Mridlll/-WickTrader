# WickTrader - Wick-Based SOL Trading Bot

A quantitative trading bot that identifies high-probability reversal opportunities based on candlestick wick patterns on SOL/USDT 4H timeframe.

## Strategy Overview

**Core Signal**: Long lower wicks (>5% of candle) indicate buyer rejection of lower prices, signaling potential bullish reversals.

### Optimized Parameters (Backtested)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Asset | SOL/USDT | Solana perpetual futures |
| Timeframe | 4H | 4-hour candles |
| Wick Threshold | 5.0% | Lower wick >= 5% triggers signal |
| Direction | Long Only | Only bullish wick signals |
| Take Profit | 10% | Fixed percentage target |
| Stop Loss | Wick Low | Below the candle low (0.5% buffer) |
| Max Hold | 40 bars | ~7 days max holding period |
| Risk Per Trade | 2% | Position sized by risk |

### Backtest Results (1 Year SOL 4H Data)

```
Win Rate: 62.5%
Total PnL: +7.9%
Trades: 8
Profit Factor: 1.8
```

## Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/WickTrader.git
cd WickTrader

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Run Backtest

```bash
# Quick test with default parameters
python backtest/run_wick_backtest.py --quick

# Full grid search optimization
python backtest/run_wick_backtest.py

# Single parameter test
python backtest/run_wick_backtest.py --threshold 5.0 --exit fixed_10 --filter none
```

### Configuration

Edit `config/wick_strategy.yaml` to customize:
- Wick threshold (1.5% - 10%)
- Exit strategies (fixed %, R:R, trailing, time-based)
- Filters (volume, trend, combined)
- Risk parameters

## Project Structure

```
WickTrader/
├── src/
│   ├── indicators/
│   │   └── wick.py          # Wick calculation
│   ├── strategy/
│   │   ├── wick_signals.py  # Signal detection
│   │   └── wick_risk.py     # Position sizing
│   └── exchanges/
│       └── base.py          # Exchange interface
├── backtest/
│   ├── wick_engine.py       # Backtest engine
│   └── run_wick_backtest.py # CLI runner
├── config/
│   └── wick_strategy.yaml   # Configuration
├── data/
│   └── sol_4h/              # Historical data
└── thoughts/
    └── ledgers/             # Session continuity
```

## Key Findings from Backtesting

1. **Threshold matters**: 1.5% threshold = ~25% win rate (unprofitable). 5%+ threshold = 62.5% win rate.

2. **Long-only outperforms**: Lower wicks (bullish) have better follow-through than upper wicks.

3. **Time-based exit works best**: Fixed 10% TP with max 40-bar holding beats R:R and trailing stops.

4. **Position scaling**: Linear scaling with wick size (bigger wick = bigger position) improves risk-adjusted returns.

## Exchanges Supported

- Binance Futures (data + execution)
- Hyperliquid (execution)

## License

MIT

## Disclaimer

This software is for educational purposes only. Trading cryptocurrencies involves substantial risk of loss. Past performance does not guarantee future results.
