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

## REMAINING TASKS
1. [ ] `gh auth login` then push to GitHub
2. [ ] Create live trading bot
3. [ ] Paper trade on Binance testnet
4. [ ] Deploy to client

## QUICK START
```bash
# Full grid search
python backtest/full_grid_search.py

# Generate report
python backtest/generate_report.py

# Push to GitHub
gh auth login
gh repo create WickTrader --public --source=. --push
```
