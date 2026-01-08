# WickTrader

**Quantitative wick-based trading system for SOL/USDT with heat-based risk management**

[![Variants Tested](https://img.shields.io/badge/Variants%20Tested-480-blue)]()
[![Profitable](https://img.shields.io/badge/Profitable-91.7%25-brightgreen)]()
[![Best Sharpe](https://img.shields.io/badge/Best%20Sharpe-1.289-yellow)]()

---

## Performance Summary

**Data**: Real Binance SOL/USDT 4H candles | **Period**: 12 months | **Variants**: 480 tested

### Results by Risk Profile

| Profile | Risk/Trade | Leverage | Avg Return | Best Return | Profitable |
|---------|------------|----------|------------|-------------|------------|
| Conservative | 3% | 3X | +123% | +211% | 91.7% |
| Moderate | 5% | 5X | +204% | +314% | 90.8% |
| Aggressive | 10% | 7X | +408% | +717% | 90.0% |
| Degen | 15% | 10X | +934% | +1,920% | 94.2% |

### Top 10 Configurations by Sharpe Ratio

```
Rank | Wick | Exit     | Direction | Profile      | Return  | Sharpe | Max DD
-----|------|----------|-----------|--------------|---------|--------|-------
  1  |  7%  | fixed_12 | long      | conservative | +211.3% |  1.289 | 14.9%
  2  |  7%  | fixed_12 | both      | moderate     | +313.6% |  1.248 | 25.6%
  3  |  7%  | rr_3     | long      | degen        | +1919%  |  1.224 | 40.7%
  4  |  7%  | fixed_12 | both      | conservative | +267.2% |  1.185 |  7.5%
  5  |  6%  | time_40  | long      | aggressive   | +717.1% |  1.093 | 31.6%
  6  |  6%  | rr_3     | both      | aggressive   | +1335%  |  1.052 | 26.4%
  7  |  7%  | time_20  | long      | moderate     | +319.3% |  1.039 | 16.2%
  8  |  7%  | trail_8  | long      | aggressive   | +265.6% |  1.002 | 44.5%
  9  |  6%  | rr_2     | long      | conservative | +150.5% |  1.001 |  8.6%
 10  |  6%  | rr_3     | long      | aggressive   | +1221%  |  1.001 | 33.2%
```

---

## Architecture

### Signal Flow

```
                              [OHLCV Data Stream]
                                      |
                                      v
+==============================================================================+
|                           SIGNAL DETECTION                                    |
+==============================================================================+
|                                                                              |
|   [Candle] --> [Wick Calculator] --> [Threshold Check: 3-7%]                |
|                      |                        |                              |
|                      v                        v                              |
|              Lower Wick >= X%?         Upper Wick >= X%?                     |
|                      |                        |                              |
|                      v                        v                              |
|               LONG SIGNAL              SHORT SIGNAL                          |
|                                                                              |
+==============================================================================+
                                      |
                                      v
+==============================================================================+
|                           RISK MANAGEMENT                                     |
+==============================================================================+
|                                                                              |
|   [Heat Zone Check]                                                          |
|         |                                                                    |
|         +---> GREEN (0-30%):    100% position size                          |
|         +---> YELLOW (30-60%):   50% position size                          |
|         +---> RED (60-80%):      25% position size                          |
|         +---> CRITICAL (>80%):    0% (blocked)                              |
|         |                                                                    |
|         v                                                                    |
|   [Position Sizing]                                                          |
|         |                                                                    |
|         +---> Size = (Balance x Risk%) / (Entry x Stop%)                    |
|         +---> Notional = Size x Entry x Leverage                            |
|         +---> Margin = Notional / Leverage                                  |
|                                                                              |
+==============================================================================+
                                      |
                                      v
+==============================================================================+
|                           EXIT CONDITIONS                                     |
+==============================================================================+
|                                                                              |
|   fixed_X  : Take profit at X% from entry                                   |
|   time_X   : Exit after X bars (4H candles)                                 |
|   trail_X  : Trailing stop activated at X%                                  |
|   rr_X     : Risk-reward ratio target of X:1                                |
|   stop     : Hit stop loss (always active)                                  |
|                                                                              |
+==============================================================================+
```

### Heat Zone System

```
PORTFOLIO HEAT MANAGEMENT
=========================

    0%                30%               60%              80%              100%
    |                  |                 |                |                |
    +------------------+-----------------+----------------+----------------+
    |      GREEN       |     YELLOW      |      RED       |   CRITICAL    |
    |    Full Size     |    Half Size    |  Quarter Size  |   No Trading  |
    +------------------+-----------------+----------------+----------------+

    Heat = Sum(Position Margins) / Account Balance x 100%

    Example ($10,000 account):
    - Position 1: $1,000 margin  -->  10% heat
    - Position 2: $1,500 margin  -->  15% heat
    - Position 3: $2,000 margin  -->  20% heat
    - Total Heat: 45% = YELLOW ZONE (new trades get 50% size)
```

### Risk Profile Comparison

```
                Conservative    Moderate      Aggressive      Degen
                ============    ========      ==========      =====

Risk/Trade          3%            5%            10%           15%
                [===       ]  [=====     ]  [==========]  [===============]

Leverage            3X            5X             7X           10X
                [===]         [=====]       [=======]     [==========]

Max Heat           30%           50%            70%           90%
                [===       ]  [=====     ]  [=======   ]  [=========  ]

Expected DD        15%           25%            35%           55%
                (stable)      (moderate)    (volatile)    (extreme)
```

---

## Quick Start

### Installation

```bash
git clone https://github.com/Mridlll/-WickTrader.git
cd WickTrader
pip install -r requirements.txt
```

### Run Full Analysis

```bash
# Generate comprehensive 480-variant analysis
python -m backtest.run_full_analysis

# View report
cat reports/backtest_report_*.md
```

### Run Quick Backtest

```bash
# Single configuration test
python -m backtest.run_wick_backtest --threshold 5.0 --profile moderate
```

---

## Project Structure

```
WickTrader/
|
+-- src/
|   +-- indicators/
|   |   +-- wick.py                 # Wick ratio calculator
|   +-- strategy/
|   |   +-- wick_signals.py         # Signal detection
|   |   +-- wick_risk.py            # Position sizing
|   |   +-- heat_risk.py            # Heat-based risk management
|   +-- exchanges/
|       +-- binance.py              # Binance Futures adapter
|       +-- hyperliquid.py          # Hyperliquid adapter
|
+-- backtest/
|   +-- engine.py                   # Core backtest engine
|   +-- advanced_engine.py          # Heat-integrated engine
|   +-- portfolio_engine.py         # Cross-margin accounting
|   +-- metrics.py                  # Sharpe, Sortino, Calmar
|   +-- variant_search.py           # 480-combo grid search
|   +-- enhanced_report_generator.py# Professional reports
|   +-- run_full_analysis.py        # One-click analysis
|
+-- config/
|   +-- wick_strategy.yaml          # Strategy parameters
|   +-- binance_testnet.yaml        # Exchange credentials
|
+-- reports/
|   +-- backtest_report_*.md        # Generated reports
|   +-- DEGEN_MODE_AUDIT.md         # Risk analysis
|
+-- data/
    +-- sol_4h/                     # Historical data cache
```

---

## Configuration

### Strategy Parameters (config/wick_strategy.yaml)

```yaml
wick:
  threshold: 5.0              # Minimum wick % for signal
  require_body_confirmation: false

risk:
  risk_percent: 5.0           # Risk per trade
  leverage: 5.0               # Position leverage
  stop_loss:
    use_wick_stop_loss: true  # Stop below candle low
    buffer_pct: 0.1           # Buffer beyond wick

exit:
  strategy: "rr_2"            # Risk:Reward 2:1
  # Options: fixed_10, fixed_12, fixed_15, rr_2, rr_3,
  #          trailing, time_based, opposite_signal
```

---

## Key Findings

### What Works

| Finding | Evidence |
|---------|----------|
| 5-7% wick threshold | Filters noise, 91%+ profitable variants |
| Wick-based stop loss | +211% vs -46% with fixed % SL |
| Long-only direction | 53%+ win rate vs 44% for shorts |
| 3X leverage | Same returns as 5X, half the drawdown |
| Time-based exits | Lets winners run, +40% vs +20% fixed TP |

### What Fails

| Configuration | Result | Why |
|---------------|--------|-----|
| 1.5-3% threshold | -25% to -77% | Too many false signals |
| Fixed 3% stop loss | -46% average | Gets stopped out before reversal |
| 1H timeframe | -16% return | Too much noise |
| 7X+ leverage | -80% to -98% | Account blowup on drawdowns |
| R:R 4:1+ exits | Negative | Targets too ambitious |

---

## Realistic Expectations

> **Important**: Grid search shows *best-case scenarios*. See reports/DEGEN_MODE_AUDIT.md for Monte Carlo analysis.

| Profile | Median Annual | Best Case | Worst Case |
|---------|--------------|-----------|------------|
| Conservative | +12% | +33% | -6% |
| Moderate | +19% | +60% | -11% |
| Aggressive | +36% | +142% | -23% |
| Degen | +49% | +249% | -36% |

---

## Exchanges

| Exchange | Data | Execution | Status |
|----------|------|-----------|--------|
| Binance Futures | Yes | Yes | Ready |
| Hyperliquid | No | Yes | Ready |

---

## Reports

| Report | Description |
|--------|-------------|
| reports/backtest_report_*.md | Full 480-variant analysis with methodology |
| reports/DEGEN_MODE_AUDIT.md | Risk analysis of high-leverage configurations |

---

## License

MIT
