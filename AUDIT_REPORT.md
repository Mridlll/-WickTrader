# WickTrader Comprehensive Security & Code Audit

**Date:** 2026-01-09
**Auditor:** Senior Quant Engineer Review
**Scope:** Full codebase audit for production readiness

---

## Executive Summary

| Category | Count | Severity Distribution |
|----------|-------|----------------------|
| Critical | 1 | Secrets exposure in committed file |
| High | 3 | Race conditions, missing validation |
| Medium | 5 | Edge cases, error handling gaps |
| Low | 4 | Code quality improvements |
| **Total Issues** | **13** | |

**Overall Assessment:** The codebase is well-structured with solid trading logic, but has **one critical security issue** that must be fixed before any production deployment.

---

## CRITICAL ISSUES

### C-01: API Credentials Committed to Repository

**File:** `config/strategies.yaml`
**Lines:** 18-19, 29-30
**Severity:** CRITICAL

```yaml
api_key: "JBI4RGV9SAAi5HfxQvT0tDeShOs8y5PomOZFVUR6RrKKXFsTx1EeicodGglOw40I"
api_secret: "drBxwaaMkQoieLdESjUAxU8NnKnkOCUIbpwySih04UsVYG6lhyGiiEUyb3E1luka"
```

**Impact:** Anyone with repository access can use these credentials to trade on the associated Binance account. Even testnet credentials should not be committed.

**Remediation:**
1. Immediately rotate these API keys on Binance
2. Remove credentials from the file
3. Add `config/strategies.yaml` to `.gitignore` (currently only `config/*.yaml` is gitignored, but this file was committed before)
4. Use environment variables or a secrets manager
5. Run `git filter-branch` or BFG Repo-Cleaner to remove from git history

**Note:** The `.gitignore` correctly excludes `config/*.yaml` but `!config/wick_strategy.yaml` and the file appears to have been committed before the gitignore was properly configured.

---

## HIGH SEVERITY ISSUES

### H-01: Position Close Race Condition

**File:** `bot/wick_bot.py`
**Lines:** 833-882

**Issue:** When closing a position, if the exchange call fails but the local state is cleared, the position becomes orphaned.

```python
async def _close_position(self, reason: str, exit_price: float) -> None:
    # ...
    if not self.config.paper_trade:
        try:
            await self.exchange.close_position(self.config.symbol)
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            # BUG: Continues to clear local state even on failure

    # State cleared regardless of exchange success
    self.active_trade = None
    self.state = BotState.MONITORING
```

**Impact:** If exchange call fails but local state resets, user loses track of an open position.

**Remediation:** Only clear local state after confirmed exchange close. Add position reconciliation on startup.

---

### H-02: Stop Loss Order Failure Not Blocking

**File:** `src/exchanges/binance.py`
**Lines:** 582-599, 603-634

**Issue:** Stop loss and take profit orders are placed after the main order, but failures only log without blocking.

```python
if stop_loss and order.status in [OrderStatus.FILLED, OrderStatus.OPEN]:
    await self._place_stop_order(...)  # Can fail silently
```

**Impact:** A position can be opened without protective orders, exposing to unlimited downside.

**Remediation:** Either:
1. Make SL/TP failures abort the trade and close the position, OR
2. Implement bracket order functionality if exchange supports it, OR
3. Track missing SL orders and retry with exponential backoff

---

### H-03: No Input Validation on Position Size

**File:** `bot/wick_bot.py`
**Lines:** 636-638

**Issue:** Position size is only checked against lot_size but not against min/max limits.

```python
size = round(size / symbol_info.lot_size) * symbol_info.lot_size
# Missing: check against symbol_info.min_size and symbol_info.max_size
```

**Impact:** Orders could fail at exchange with cryptic errors, or extremely small/large positions could be placed.

**Remediation:**
```python
size = max(symbol_info.min_size, min(size, symbol_info.max_size))
size = round(size / symbol_info.lot_size) * symbol_info.lot_size
```

---

## MEDIUM SEVERITY ISSUES

### M-01: Deprecated datetime.utcnow() Usage

**Files:** `bot/wick_bot.py:479,496`, `bot/strategy_scheduler.py:263,296`

**Issue:** `datetime.utcnow()` is deprecated in Python 3.12+.

**Remediation:** Use `datetime.now(timezone.utc)` instead.

---

### M-02: Division by Zero Possible in Wick Calculation

**File:** `src/indicators/wick.py`
**Lines:** 105-112, 115-119

**Issue:** Close price of 0 is handled, but candle_range of 0 (doji) could cause issues downstream.

```python
if candle_range > 0:
    upper_wick_ratio = upper_wick / candle_range
else:
    upper_wick_ratio = 0.0  # Correct here, but consumers may not check
```

**Impact:** Edge case with perfect doji candles could propagate unexpected ratios.

---

### M-03: Heat Manager State Persistence

**File:** `src/strategy/heat_risk.py`

**Issue:** Heat state (positions, peak equity) is only stored in memory. On bot restart, heat calculation resets to 0%, allowing oversized positions.

**Impact:** After restart, bot doesn't know about existing exchange positions' heat contribution until `_check_existing_positions()` runs, and even then doesn't restore historical peak equity for drawdown calculation.

**Remediation:** Persist heat state to disk or fetch complete position data on startup.

---

### M-04: Scheduler Timezone Fallback Silent

**File:** `bot/strategy_scheduler.py`
**Lines:** 255-263

**Issue:** Invalid timezone silently falls back to UTC without logging.

```python
try:
    tz = pytz.timezone(timezone)
    return datetime.now(tz)
except Exception:
    pass  # Silent fallback
return datetime.utcnow()
```

**Remediation:** Log a warning when timezone lookup fails.

---

### M-05: No Idempotency in Stop Order Placement

**File:** `src/exchanges/binance.py`
**Lines:** 603-634

**Issue:** If bot restarts mid-trade, it may place duplicate SL/TP orders.

**Remediation:** Check for existing SL/TP orders before placing new ones, or use client_order_id for deduplication.

---

## LOW SEVERITY ISSUES

### L-01: Magic Numbers in Exit Logic

**File:** `bot/wick_bot.py`
**Lines:** 612

```python
tp_distance = signal.entry_price * 0.30  # Magic number for time-based
```

**Recommendation:** Extract to named constant or config.

---

### L-02: Bare Exception Catches

**Files:** Multiple locations

```python
except Exception:
    pass  # Discord not configured
```

**Recommendation:** Catch specific exceptions and log unexpected ones.

---

### L-03: Unused Parameter in Multi-Strategy Reload

**File:** `bot/multi_strategy_runner.py`
**Lines:** 130-145

The `reload_config()` method stores running states but doesn't use them effectively.

---

### L-04: Missing Type Hints on Some Public Methods

**Files:** Various

**Recommendation:** Add return type hints for better IDE support and documentation.

---

## GOOD PRACTICES FOUND

### Architecture

- **Clean Separation of Concerns:** Exchange adapters, strategy logic, and risk management are properly isolated
- **Abstract Base Classes:** `BaseExchange` provides good contract for exchange implementations
- **Dataclasses:** Proper use of dataclasses for configuration and state
- **Async/Await:** Correct use of asyncio for I/O-bound operations

### Risk Management

- **Heat Zone System:** Well-designed multi-tier risk management with configurable thresholds
- **Recovery Mode:** Automatic risk reduction after significant drawdowns
- **Position Scaling:** Heat-adjusted position sizing prevents over-leveraging

### Security

- **HMAC Signing:** Correct implementation of request signing for Binance
- **Mainnet Confirmation:** Requires explicit "I UNDERSTAND" to trade with real money
- **Paper Trading Default:** Safe default configuration

### Trading Logic

- **Wick Calculation:** Mathematically correct wick percentage calculations
- **Stop Loss Options:** Multiple SL methods (swing, ATR, fixed, wick-based)
- **Backtest Integrity:** Grid search uses real market data, not synthetic

### Concurrency

- **Graceful Shutdown:** Signal handlers for SIGINT/SIGTERM
- **Health Checks:** Periodic status monitoring in multi-strategy mode
- **Task Cancellation:** Proper cleanup of asyncio tasks

---

## RECOMMENDATIONS BY PRIORITY

### Immediate (Before Production)

1. **Rotate compromised API keys** and remove from git history
2. **Fix position close race condition** (H-01)
3. **Add SL order failure handling** (H-02)
4. **Validate position size bounds** (H-03)

### Short-Term (Next Release)

5. Replace deprecated `datetime.utcnow()`
6. Add heat state persistence
7. Implement SL/TP idempotency
8. Add timezone fallback logging

### Long-Term (Technical Debt)

9. Extract magic numbers to constants
10. Improve exception handling specificity
11. Add comprehensive type hints
12. Add integration tests for exchange failover scenarios

---

## FILES REVIEWED

| File | Lines | Status |
|------|-------|--------|
| `bot/wick_bot.py` | 916 | Reviewed |
| `bot/run_bot.py` | 396 | Reviewed |
| `bot/multi_strategy_runner.py` | 502 | Reviewed |
| `bot/strategy_scheduler.py` | 332 | Reviewed |
| `src/strategy/wick_signals.py` | 401 | Reviewed |
| `src/strategy/wick_risk.py` | 335 | Reviewed |
| `src/strategy/heat_risk.py` | 610 | Reviewed |
| `src/strategy/risk.py` | 290 | Reviewed |
| `src/indicators/wick.py` | 210 | Reviewed |
| `src/exchanges/binance.py` | 819 | Reviewed |
| `src/exchanges/base.py` | 542 | Reviewed |
| `backtest/engine.py` | 178 | Reviewed |
| `backtest/run_real_grid_search.py` | 448 | Reviewed |
| `.gitignore` | 37 | Reviewed |
| `config/strategies.yaml` | 93 | **CRITICAL** |

---

## CONCLUSION

WickTrader demonstrates solid quantitative trading architecture with well-thought-out risk management. The **critical credential exposure** must be addressed immediately. The high-severity race conditions should be fixed before any live trading. With these fixes, the system would be suitable for production deployment.

**Risk Rating:** HIGH (due to C-01)
**Code Quality:** GOOD
**Production Ready:** NO (pending critical fixes)

---

*Audit completed 2026-01-09*
