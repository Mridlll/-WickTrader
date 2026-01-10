# WickTrader

**Quantitative wick-based trading system for SOL/USDT with heat-based risk management**

[![Variants Tested](https://img.shields.io/badge/Variants%20Tested-864-blue)]()
[![Profitable](https://img.shields.io/badge/Profitable-14.4%25-yellow)]()
[![Best Win Rate](https://img.shields.io/badge/Best%20Win%20Rate-80%25-brightgreen)]()

---

## QUICK START - READ THIS FIRST

### Prerequisites

- **Python 3.10+** installed ([Download Python](https://www.python.org/downloads/))
- **Git** installed ([Download Git](https://git-scm.com/downloads))
- **Binance** or **Bybit** account with API keys

---

## Step-by-Step Setup (Follow EXACTLY)

### STEP 1: Download the Bot

Open **PowerShell** (Windows) or **Terminal** (Mac/Linux) and run:

```bash
git clone https://github.com/Mridlll/-WickTrader.git
cd WickTrader
```

### STEP 2: Install Dependencies (REQUIRED!)

**YOU MUST RUN THIS COMMAND** or you will get errors:

```bash
pip install -r requirements.txt
```

Wait for it to finish. You should see "Successfully installed..." messages.

### STEP 3: Run the Setup Wizard

```bash
python setup_subaccounts.py
```

The wizard will ask you:
1. **Select Exchange**: Choose `1` for Binance or `2` for Bybit
2. **Select Strategies**: Enter numbers like `1,2` or type `all`
3. **Enter API Keys**: Paste your API key and secret

### STEP 4: Run the Bot

```bash
python run_production.py --multi
```

That's it! The bot is now running.

---

## Troubleshooting

### Error: `No module named 'yaml'`
Run: `pip install pyyaml`

### Error: `No module named 'xxx'`
Run: `pip install -r requirements.txt`

### Error: `python is not recognized`
Python is not installed. Download from: https://www.python.org/downloads/

### Error: `git is not recognized`
Git is not installed. Download from: https://git-scm.com/downloads

---

## Supported Exchanges

| Exchange | Testnet | Mainnet |
|----------|---------|---------|
| **Binance Futures** | Yes | Yes |
| **Bybit Perpetuals** | Yes | Yes |

---

## Available Strategies (10 Total)

| Strategy | Direction | Trades/Year | Win Rate | Return | Max DD |
|----------|-----------|-------------|----------|--------|--------|
| backtest-winner | SHORT | 5 | 80% | +49.5% | 10.6% |
| safe | LONG | 8 | 62.5% | +27.7% | 20% |
| aggressive | SHORT | 5 | 80% | +216% | 29.5% |
| degen | SHORT | 5 | 80% | +380% | 39.6% |
| long-aggressive | LONG | 8 | 62.5% | +80% | 56% |
| both-conservative | BOTH | 14 | 50% | +71% | 27.5% |
| both-moderate | BOTH | 14 | 50% | +121% | 40% |
| both-aggressive | BOTH | 14 | 50% | +226% | 63% |
| both-degen | BOTH | 14 | 50% | +266% | 78% |
| active-trader | BOTH | 16 | 50% | +94% | 40% |

---

## Commands Reference

```bash
# Setup wizard (first time)
python setup_subaccounts.py

# Run bot (production mode with auto-restart)
python run_production.py --multi

# View all strategies
python -m bot.run_bot --strategies

# Run single strategy
python -m bot.run_bot --strategy backtest-winner --exchange binance
python -m bot.run_bot --strategy safe --exchange bybit
```

---

## Strategy Presets

Choose a pre-configured strategy based on our **REAL 864-variant backtest** on SOL/USDT 4H data (Dec 2024 - Dec 2025):

| Strategy | Command | Direction | Return | Max DD | Win Rate |
|----------|---------|-----------|--------|--------|----------|
| **Best Risk-Adjusted** | `--strategy backtest-winner` | SHORT | +49.5% | 10.6% | 80% |
| **Safe Long** | `--strategy safe` | LONG | +27.7% | 20.0% | 62.5% |
| **Aggressive** | `--strategy aggressive` | SHORT | +216% | 29.5% | 80% |
| **Degen** | `--strategy degen` | SHORT | +380% | 39.6% | 80% |

```bash
# Examples
python -m bot.run_bot --strategy safe              # Conservative long
python -m bot.run_bot --strategy backtest-winner   # Best risk-adjusted
python -m bot.run_bot --strategy aggressive        # Higher risk short
python -m bot.run_bot --strategy degen             # Maximum risk
```

---

## Performance Summary

**Data**: Real Binance SOL/USDT 4H candles | **Period**: 12 months (2190 candles) | **Variants**: 864 tested

### Signal Frequency by Wick Threshold

| Threshold | Long Signals | Short Signals | Total/Year | Signals/Month |
|-----------|--------------|---------------|------------|---------------|
| 1.5% | 225 | 181 | 406 | 33.5 |
| 2.0% | 120 | 79 | 199 | 16.4 |
| 3.0% | 39 | 21 | 60 | 4.9 |
| 4.0% | 21 | 7 | 28 | 2.3 |
| 5.0% | 10 | 3 | 13 | 1.1 |
| 6.0% | 2 | 1 | 3 | 0.2 |
| 7.0% | 2 | 0 | 2 | 0.2 |

### Results by Risk Profile (Average Across All Configurations)

| Profile | Risk/Trade | Leverage | Avg Return | Profitable | Avg Max DD |
|---------|------------|----------|------------|------------|------------|
| Conservative | 3% | 3X | -19.5% | 18.1% | 40.0% |
| Moderate | 5% | 5X | -29.9% | 17.1% | 55.5% |
| Aggressive | 10% | 7X | -47.4% | 13.4% | 75.7% |
| Degen | 15% | 10X | -56.4% | 8.8% | 84.1% |

**Note**: Most configurations lose money. Only selective high-threshold strategies are profitable.

### Top 10 Configurations by Sharpe Ratio

```
Rank | Wick | Exit     | Direction | Profile      | Trades | Win%  | Return  | Sharpe  | Max DD
-----|------|----------|-----------|--------------|--------|-------|---------|---------|-------
  1  |  4%  | fixed_15 | short     | conservative |   5    | 80.0% | +49.5%  |  17.48  | 10.6%
  2  |  4%  | fixed_15 | short     | moderate     |   5    | 80.0% | +89.7%  |  17.48  | 16.7%
  3  |  4%  | fixed_15 | short     | aggressive   |   5    | 80.0% | +216%   |  17.48  | 29.5%
  4  |  4%  | fixed_15 | short     | degen        |   5    | 80.0% | +380%   |  17.48  | 39.6%
  5  |  4%  | time_40  | short     | conservative |   5    | 80.0% | +42.2%  |  14.73  | 11.2%
  6  |  4%  | time_40  | short     | moderate     |   5    | 80.0% | +75.0%  |  14.73  | 17.3%
  7  |  4%  | time_40  | short     | aggressive   |   5    | 80.0% | +173.6% |  14.73  | 29.8%
  8  |  4%  | time_40  | short     | degen        |   5    | 80.0% | +294.7% |  14.73  | 39.6%
  9  |  4%  | time_30  | short     | conservative |   5    | 80.0% | +28.1%  |  13.23  | 11.5%
 10  |  4%  | time_30  | short     | moderate     |   5    | 80.0% | +48.8%  |  13.23  | 17.8%
```

### Best LONG Configurations

```
Rank | Wick | Exit     | Profile      | Trades | Win%  | Return  | Sharpe | Max DD
-----|------|----------|--------------|--------|-------|---------|--------|-------
  1  |  5%  | fixed_10 | conservative |   8    | 62.5% | +27.7%  |  6.68  | 20.0%
  2  |  5%  | fixed_10 | moderate     |   8    | 62.5% | +45.4%  |  6.68  | 31.8%
  3  |  5%  | fixed_10 | aggressive   |   8    | 62.5% | +80.4%  |  6.68  | 56.1%
  4  |  5%  | fixed_10 | degen        |   8    | 62.5% | +91.0%  |  6.68  | 74.0%
  5  |  5%  | fixed_12 | conservative |   8    | 50.0% | +17.2%  |  4.14  | 20.0%
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
|   [Candle] --> [Wick Calculator] --> [Threshold Check: 4-5%]                |
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

Expected DD        20%           40%            60%           80%
                (stable)      (moderate)    (volatile)    (extreme)
```

---

## Live Trading Bot

### Paper Trading (Safe - No Real Money)

```bash
# Run with any strategy preset
python -m bot.run_bot --strategy backtest-winner

# Or run setup wizard for interactive configuration
python setup_wizard.py
```

### Live Trading (Real Money)

```bash
# Requires mainnet API keys and confirmation
python -m bot.run_bot --strategy safe --live --mainnet
# You will be asked to type "I UNDERSTAND" to confirm
```

### Bot Features

- Multi-exchange support (Binance + Hyperliquid)
- Automatic failover between exchanges
- Heat-based position sizing
- Multiple exit strategies
- Discord notifications (optional)
- Paper trading mode for testing

### Multi-Strategy Mode (Run Multiple Strategies)

Run multiple strategies concurrently on separate Binance subaccounts:

```bash
# 1. Setup subaccounts (interactive wizard)
python setup_subaccounts.py

# 2. Check configuration status
python -m bot.multi_strategy_runner --status

# 3. Run all enabled strategies
python -m bot.multi_strategy_runner

# 4. With time-based scheduler (optional)
python -m bot.multi_strategy_runner --scheduler
```

**Configuration** (`config/strategies.yaml`):
```yaml
strategies:
  backtest-winner:
    enabled: true
    subaccount:
      name: "WickTrader-Short"
      api_key: "YOUR_KEY"
      api_secret: "YOUR_SECRET"
      testnet: true
  safe:
    enabled: true
    subaccount:
      name: "WickTrader-Long"
      api_key: "YOUR_KEY"
      api_secret: "YOUR_SECRET"
      testnet: true
```

See `config/strategies.yaml.sample` for full configuration options including time-based scheduling.

---

## Backtesting

### Run Real Grid Search

```bash
# Generate comprehensive 864-variant analysis
python -m backtest.run_real_grid_search

# View report
cat reports/REAL_BACKTEST_REPORT_*.md
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
|   +-- run_real_grid_search.py     # REAL 864-variant grid search
|
+-- config/
|   +-- wick_strategy.yaml          # Strategy parameters
|   +-- binance_testnet.yaml        # Exchange credentials
|
+-- reports/
|   +-- REAL_BACKTEST_REPORT_*.md   # Verified backtest reports
|   +-- REAL_grid_search_*.csv      # Full results data
|
+-- data/
    +-- sol_4h/                     # Historical data cache
```

---

## Configuration

### Strategy Parameters (config/wick_strategy.yaml)

```yaml
wick:
  threshold: 4.0              # Minimum wick % for signal (4-5% optimal)
  require_body_confirmation: false

risk:
  risk_percent: 3.0           # Risk per trade (conservative)
  leverage: 3.0               # Position leverage
  stop_loss:
    use_wick_stop_loss: true  # Stop below candle low
    buffer_pct: 0.1           # Buffer beyond wick

exit:
  strategy: "fixed_15"        # Fixed 15% take profit
  # Options: fixed_10, fixed_12, fixed_15, rr_2, rr_3,
  #          trailing, time_based, opposite_signal
```

---

## Key Findings (REAL Data)

### What Works

| Finding | Evidence |
|---------|----------|
| 4% wick threshold + SHORT | 80% win rate, +49.5% return, 10.6% DD |
| 5% wick threshold + LONG | 62.5% win rate, +27.7% return |
| Fixed 15% TP for shorts | Best Sharpe ratio (17.48) |
| Fixed 10% TP for longs | Best long Sharpe ratio (6.68) |
| Wick-based stop loss | Critical for edge preservation |
| Conservative profile | Best risk-adjusted returns |

### What Fails

| Configuration | Result | Why |
|---------------|--------|-----|
| 1.5-3% threshold | -35% to -95% | Too many false signals (406 trades/year) |
| R:R based exits | Negative returns | Too ambitious, gets stopped out |
| Aggressive/Degen on longs | High drawdown | 50-75% max DD |
| Both directions at low thresholds | Large losses | Short signals unreliable at <4% |

---

## Realistic Expectations

| Profile | Configuration | Return | Win Rate | Max DD | Trades/Year |
|---------|---------------|--------|----------|--------|-------------|
| **Best Risk-Adjusted** | 4% SHORT, fixed_15 | +49.5% | 80% | 10.6% | 5 |
| **Best Long** | 5% LONG, fixed_10 | +27.7% | 62.5% | 20% | 8 |
| **Aggressive** | 4% SHORT, fixed_15 | +216% | 80% | 29.5% | 5 |
| **Degen** | 4% SHORT, fixed_15 | +380% | 80% | 39.6% | 5 |

**Important**: These are backtest results on 12 months of data. Past performance does not guarantee future results. Trade frequency is low (5-8 trades/year for optimal configs).

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
| reports/REAL_BACKTEST_REPORT_*.md | Full 864-variant analysis with real data |
| reports/REAL_grid_search_*.csv | Complete results for all configurations |

---

## License

MIT
