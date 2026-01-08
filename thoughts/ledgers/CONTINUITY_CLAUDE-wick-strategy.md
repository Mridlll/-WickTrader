# Continuity Ledger: Wick-Based SOL Trading Strategy

## Goal
Implement and backtest a wick-based trading strategy for SOL on 4H per client spec.

## FINAL OPTIMAL CONFIGURATION
```
Asset:           SOL/USDT
Timeframe:       4H only (1H failed)
Entry:           5.0%+ lower wick
Direction:       Long only
Exit:            Max 30 bars OR 15% TP (whichever first)
Stop Loss:       Wick low (below candle low)
Leverage:        3X (optimal risk-adjusted)
Risk per Trade:  10% of portfolio
```

## COMPREHENSIVE GRID SEARCH RESULTS (192 combinations tested)

### Top 10 Entry/Exit Combinations
```
 Entry | Exit Strategy    | SL Type      | Trades |  Win% |   Return |  MaxDD
---------------------------------------------------------------------------------
  5.0% | Max 30 bars      | Wick SL      |      8 | 62.5% |   +39.7% |  27.6%
  5.0% | Fixed 10% TP     | Wick SL      |      8 | 62.5% |   +36.2% |  27.6%
  5.0% | Trail @10%       | Wick SL      |      8 | 62.5% |   +30.4% |  27.6%
  5.0% | Fixed 12% TP     | Wick SL      |      8 | 62.5% |   +29.7% |  27.6%
  5.0% | Max 40 bars      | Wick SL      |      8 | 50.0% |   +26.0% |  27.6%
  4.5% | Max 30 bars      | Wick SL      |      9 | 55.6% |   +25.3% |  35.0%
  4.5% | Fixed 10% TP     | Wick SL      |      9 | 55.6% |   +22.2% |  35.0%
  5.0% | Fixed 8% TP      | Wick SL      |      8 | 62.5% |   +20.7% |  27.6%
  5.0% | Max 20 bars      | Wick SL      |      8 | 62.5% |   +20.4% |  21.6%
  4.5% | Trail @10%       | Wick SL      |      9 | 55.6% |   +17.0% |  35.0%
```

### Worst Configurations (AVOID)
```
  3.5% | ANY exit         | Fixed 3% SL  |     18 |  5.6% |   -77.1% |  81.5%
```
**Fixed 3% SL destroys the strategy** - Wick-based SL is critical.

### Exit Strategy Comparison (5% threshold)
| Exit Type | Return | Notes |
|-----------|--------|-------|
| Max 30 bars | +39.7% | **BEST** - lets winners run |
| Fixed 10% TP | +36.2% | Good, reliable |
| Trail @10% | +30.4% | Decent |
| Fixed 12% TP | +29.7% | Good |
| Fixed 8% TP | +20.7% | Too early exit |
| R:R 2:1 | +13.5% | Underperforms |
| R:R 3:1+ | Negative | Too ambitious |

### Stop Loss Comparison
| SL Type | Avg Return | Avg Win% |
|---------|------------|----------|
| Wick SL | -17.1% | 40.2% |
| Fixed 3% SL | **-46.3%** | **10.7%** |
**Wick-based SL is mandatory** - Fixed % SL kills the edge.

## LEVERAGE TESTING (Full Position Sizing)

| Leverage | Return | Max DD | Verdict |
|----------|--------|--------|---------|
| 2X | +42.2% | 38.4% | Safe |
| **3X** | **+55.0%** | **53.3%** | **OPTIMAL** |
| 5X | +54.2% | 75.7% | Same return, more risk |
| 7X | -80.8% | 98.3% | Nearly blown |
| 10X | -98.3% | 99.9% | **REKT** |

**3X is optimal** - 5X gives same return but 75% drawdown vs 53%.

## TRADE-BY-TRADE LOG (3X, 10% Risk, 5% Wick)
```
2025-01-18: wick=5.1%, PnL=+$2,653 (+26.5%) WIN
2025-01-19: wick=5.9%, PnL=-$1,294 (-10.2%) LOSS - immediate reversal
2025-02-02: wick=5.7%, PnL=-$1,163 (-10.2%) LOSS - Feb crash
2025-03-04: wick=5.6%, PnL=-$1,036 (-10.2%) LOSS - March bottom
2025-03-11: wick=5.4%, PnL=+$1,615 (+17.6%) WIN - caught the bounce
2025-10-10: wick=24.7%, PnL=+$132 (+1.2%) WIN - huge wick, small move
2025-11-04: wick=5.7%, PnL=+$1,004 (+9.2%) WIN
2025-11-21: wick=5.0%, PnL=+$2,056 (+17.3%) WIN

Final: $10,000 -> $13,969 (+39.7%)
Max Drawdown: 27.6% (during Feb-Mar 2025 crash)
```

## KEY FINDINGS

### What Works
- 5%+ wick threshold (filters noise)
- Long-only (bearish wicks unreliable)
- Wick-based SL (below candle low)
- 30-bar max hold (lets winners run)
- 3X leverage (optimal risk/reward)
- 10% risk per trade (8 trades/year needs size)

### What Fails
- 1.5-3.5% threshold (too many false signals)
- Fixed % stop loss (destroys edge)
- 1H timeframe (40% win rate, -16% return)
- R:R based exits (too ambitious)
- 7X+ leverage (account blowup risk)
- Both directions (shorts underperform)

### Client Spec Adjustments
| Client Asked | Our Finding |
|--------------|-------------|
| 1.5% threshold | 5.0% optimal |
| 10-20% target | 10-15% or time-based |
| Both directions | Long only |
| Position scaling | Fixed 10% risk, 3X leverage |

## FILES CREATED
```
D:\Crypto Bot\WickTrader\
├── src/indicators/wick.py
├── src/strategy/wick_signals.py
├── src/strategy/wick_risk.py
├── src/exchanges/binance.py
├── src/exchanges/hyperliquid.py
├── backtest/wick_engine.py
├── backtest/run_wick_backtest.py
├── backtest/generate_report.py
├── backtest/full_grid_search.py
├── config/wick_strategy.yaml
└── config/binance_testnet.yaml (API keys)
```

## State
- Done:
  - [x] Implement wick indicator and signal detection
  - [x] Create backtest engine with fee/slippage
  - [x] Run comprehensive grid search (192 combos)
  - [x] Test leverage scenarios (2X-10X)
  - [x] Update README with accurate results (+39.7%)
  - [x] Commit to local git
  - [x] Push to GitHub
  - [x] **Heat-based risk management system**
  - [x] **Cross-margin portfolio engine**
  - [x] **Advanced backtest with 4 risk profiles**
  - [x] **480-variant grid search**
  - [x] **Professional report generator with methodology docs**
  - [x] **Live trading bot with multi-exchange support**
  - [x] **Interactive setup wizard**
  - [x] **Discord notifications system**
  - [x] **Comprehensive audit and testing (38/38 tests passed)**
  - [x] **Fixed critical issues from audit**
- Now: [→] Ready for paper trading
- Next: Deploy to production

## GitHub
https://github.com/Mridlll/-WickTrader

## LATEST REPORT
`reports/backtest_report_20260108_170119.md`

## ADVANCED BACKTEST SYSTEM (Added 2026-01-08)

### New Components
| Component | File | Purpose |
|-----------|------|---------|
| Heat Risk Manager | `src/strategy/heat_risk.py` | Portfolio heat tracking, zone-based sizing |
| Cross-Margin Engine | `backtest/portfolio_engine.py` | Unified margin pool, real-time PnL |
| Advanced Engine | `backtest/advanced_engine.py` | 4 risk profiles, integrated heat |
| Metrics Calculator | `backtest/metrics.py` | Sharpe, Sortino, Calmar, PF |
| Variant Search | `backtest/variant_search.py` | 480-combo grid search |
| Report Generator | `backtest/enhanced_report_generator.py` | Professional markdown reports |
| Full Analysis | `backtest/run_full_analysis.py` | One-click comprehensive analysis |

### Risk Profiles Tested
| Profile | Risk/Trade | Leverage | Max Heat |
|---------|------------|----------|----------|
| Conservative | 3% | 3X | 30% |
| Moderate | 5% | 5X | 50% |
| Aggressive | 10% | 7X | 70% |
| Degen | 15% | 10X | 90% |

### Heat Zone System
| Zone | Heat Level | Sizing Allowed |
|------|------------|----------------|
| GREEN | 0-30% | 100% |
| YELLOW | 30-60% | 50% |
| RED | 60-80% | 25% |
| CRITICAL | >80% | 0% |

### Grid Search Results (480 variants)
- **91.7% profitable** (440/480)
- **Best Sharpe:** 1.289 (Conservative, 7% wick, fixed_12)
- **Best Return:** +2815% (Degen mode)

## REMAINING TASKS
1. [x] Push to GitHub
2. [x] Add heat-based risk management
3. [x] Create professional backtest report
4. [x] **Degen Mode Audit** - audited +1920% return claim
5. [x] Create live trading bot
6. [→] Paper trade on Binance testnet
7. [ ] Deploy to client

## LIVE TRADING BOT (Added 2026-01-08)

**Files Created:**
- `bot/wick_bot.py` - Main trading bot class (Binance)
- `bot/multi_exchange_bot.py` - Multi-exchange with failover
- `bot/run_bot.py` - Entry point with CLI
- `setup_wizard.py` - Interactive setup wizard

**Quick Start:**
```bash
# Run setup wizard (recommended)
python setup_wizard.py

# Or run directly
python -m bot.run_bot --paper --profile moderate
```

**Features:**
- Multi-exchange support (Binance + Hyperliquid)
- Automatic failover between exchanges
- Interactive setup wizard (like VMC)
- Heat-based position sizing
- Multiple exit strategies
- Paper trading mode

## DEGEN MODE AUDIT (2026-01-08)

**Finding:** The +1,919.49% return is mathematically accurate but represents top 3% of outcomes.

| What Grid Search Showed | Reality |
|------------------------|---------|
| +1,919% return | +49% median expected |
| 40.7% max drawdown | 50-70% likely |
| 94 trades @ 48% WR | Accurate |

**Why it's possible:** Compounding with 15% risk + 3:1 R:R = +13.8% expectancy/trade.
Consecutive wins at high balances create exponential growth.

**Why it's misleading:** Sequence matters. Same trades in different order:
- Lucky: +1,920%
- Average: +49%
- Unlucky: -68%

**5 consecutive losses = 56% drawdown** (87% probability over 94 trades)

**Audit Report:** `reports/DEGEN_MODE_AUDIT.md`

## CODE AUDIT (2026-01-09)

### Issues Found & Fixed
| Issue | Severity | Status | Fix |
|-------|----------|--------|-----|
| Hardcoded API keys in test files | CRITICAL | FIXED | Load from config file |
| Heat manager disconnected from bot | CRITICAL | FIXED | Added add_position/remove_position calls |
| Missing size zero check (Hyperliquid) | HIGH | FIXED | Added validation after rounding |
| Position state not tracked | HIGH | N/A | Already implemented (bars_held incremented) |
| _peak_equity initialization | HIGH | N/A | Already correct (first call sets it) |
| Missing config validation | MEDIUM | FIXED | Added validate() method |

### Test Results (38/38 PASSED)
- Exchange Setup: 2 tests (Binance + Hyperliquid connected)
- Signal Detection: 3 tests (5%: 13 signals, 6%: 12, 7%: 11)
- Risk Profiles: 4 tests (all 4 presets validated)
- Heat Zones: 5 tests (GREEN→YELLOW→RED→CRITICAL working)
- Position Sizing: 3 tests (wick-scaled sizing correct)
- Exit Strategies: 7 tests (fixed/rr/time all correct)
- Multi-Strategy: 3 tests (19-26 signals per threshold)
- Order Flow: 11 tests (full cycle on both exchanges)

### Verified Balances
- Binance Demo: $4,999.65
- Hyperliquid Testnet: $1,014.66

## COMMITS THIS SESSION
| Commit | Description |
|--------|-------------|
| `878624d` | docs: Add architecture diagrams, Degen mode audit, improved README |
| `cd40a7d` | feat: Add heat-based risk management, cross-margin engine, comprehensive backtest |
| `a41cc42` | docs: Fix clone URL and comprehensive testing documentation |
| `6362530` | docs: Update ledger - GitHub push complete |
| `131a47f` | docs: Update README with accurate grid search results |
| `7a106ce` | Complete strategy analysis: 192 combinations, leverage testing |

## QUICK START
```bash
# Run full analysis (generates report)
python -m backtest.run_full_analysis

# View latest report
cat reports/backtest_report_*.md
```
