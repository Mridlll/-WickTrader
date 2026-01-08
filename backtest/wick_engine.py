"""Backtesting engine for wick-based trading strategy."""

import sys
from pathlib import Path
from enum import Enum

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from strategy.signals import SignalType
from strategy.wick_signals import WickSignalDetector, WickSignal, FilteredWickSignalDetector
from strategy.wick_risk import WickRiskManager
from indicators.wick import WickCalculator
from backtest.engine import BacktestTrade, BacktestResult
from utils.logger import get_logger

logger = get_logger("wick_backtest")


class ExitStrategy(str, Enum):
    """Exit strategy types for wick backtesting."""
    FIXED_10 = "fixed_10"      # 10% fixed target
    FIXED_15 = "fixed_15"      # 15% fixed target
    FIXED_20 = "fixed_20"      # 20% fixed target
    SCALED = "scaled"          # 33% at 10%, 33% at 15%, 34% at 20%
    RR_2 = "rr_2"              # 2:1 risk:reward
    RR_3 = "rr_3"              # 3:1 risk:reward
    RR_4 = "rr_4"              # 4:1 risk:reward
    TRAILING = "trailing"      # Trail after 10% profit
    OPPOSITE_SIGNAL = "opposite_signal"  # Exit on opposite wick signal
    TIME_BASED = "time_based"  # Exit after N bars


class FilterType(str, Enum):
    """Filter types for signal filtering."""
    NONE = "none"
    VOLUME = "volume"          # Volume > 20-day SMA
    TREND = "trend"            # Price vs 50 EMA
    COMBINED = "combined"      # Both volume and trend


@dataclass
class WickBacktestTrade(BacktestTrade):
    """Extended trade info with wick-specific data."""
    wick_pct: float = 0.0
    wick_multiplier: float = 1.0
    wick_stop_loss: float = 0.0
    partial_exits: int = 0
    scaled_pnl_breakdown: Dict[str, float] = field(default_factory=dict)


class WickBacktestEngine:
    """
    Backtesting engine for wick-based trading strategy.

    Features:
    - Multiple exit strategies (fixed %, R:R, scaled, trailing, opposite signal, time-based)
    - Multiple filters (none, volume, trend, combined)
    - Position scaling based on wick size
    - 3x leverage support
    - Comprehensive metrics tracking
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        risk_percent: float = 3.0,
        leverage: float = 3.0,
        commission_percent: float = 0.06,
        wick_threshold: float = 1.5,
        max_wick_multiplier: float = 2.0,
        exit_strategy: ExitStrategy = ExitStrategy.RR_2,
        filter_type: FilterType = FilterType.NONE,
        # Filter settings
        volume_sma_period: int = 20,
        trend_ema_period: int = 50,
        # Time-based exit
        time_based_bars: int = 10,
        # Trailing settings
        trailing_activation_pct: float = 10.0,
        trailing_distance_pct: float = 5.0,
        # Scaled exit settings
        scaled_targets: List[Tuple[float, float]] = None,  # [(pct_exit, pct_target), ...]
        # Stop loss
        use_wick_stop_loss: bool = True,
        wick_sl_buffer_pct: float = 0.1
    ):
        """
        Initialize wick backtest engine.

        Args:
            initial_balance: Starting balance
            risk_percent: Risk per trade (%)
            leverage: Leverage multiplier (default 3x)
            commission_percent: Commission per trade (%)
            wick_threshold: Minimum wick percentage for signals
            max_wick_multiplier: Max position scaling from wick
            exit_strategy: Exit strategy to use
            filter_type: Signal filter type
            volume_sma_period: Period for volume SMA filter
            trend_ema_period: Period for trend EMA filter
            time_based_bars: Bars to hold for time-based exit
            trailing_activation_pct: % profit to activate trailing
            trailing_distance_pct: % distance for trailing stop
            scaled_targets: Custom scaled exit targets
            use_wick_stop_loss: Use wick extreme for SL
            wick_sl_buffer_pct: Buffer beyond wick for SL
        """
        self.initial_balance = initial_balance
        self.risk_percent = risk_percent
        self.leverage = leverage
        self.commission_percent = commission_percent
        self.wick_threshold = wick_threshold
        self.max_wick_multiplier = max_wick_multiplier
        self.exit_strategy = exit_strategy
        self.filter_type = filter_type
        self.volume_sma_period = volume_sma_period
        self.trend_ema_period = trend_ema_period
        self.time_based_bars = time_based_bars
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_distance_pct = trailing_distance_pct
        self.use_wick_stop_loss = use_wick_stop_loss
        self.wick_sl_buffer_pct = wick_sl_buffer_pct

        # Default scaled targets: 33% at 10%, 33% at 15%, 34% at 20%
        self.scaled_targets = scaled_targets or [
            (0.33, 10.0),
            (0.33, 15.0),
            (0.34, 20.0)
        ]

        # Initialize components
        self.wick_calc = WickCalculator(threshold=wick_threshold)
        self.risk_manager = WickRiskManager(
            default_risk_percent=risk_percent,
            default_leverage=leverage,
            wick_threshold=wick_threshold,
            max_wick_multiplier=max_wick_multiplier,
            use_wick_stop_loss=use_wick_stop_loss,
            wick_sl_buffer_pct=wick_sl_buffer_pct
        )

    def run(
        self,
        df: pd.DataFrame,
        wick_threshold: Optional[float] = None,
        exit_strategy: Optional[ExitStrategy] = None,
        filter_type: Optional[FilterType] = None
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            wick_threshold: Override wick threshold
            exit_strategy: Override exit strategy
            filter_type: Override filter type

        Returns:
            BacktestResult with performance metrics
        """
        threshold = wick_threshold if wick_threshold is not None else self.wick_threshold
        exit_strat = exit_strategy if exit_strategy is not None else self.exit_strategy
        filt = filter_type if filter_type is not None else self.filter_type

        logger.info(f"Running wick backtest: threshold={threshold}, exit={exit_strat.value}, filter={filt.value}")

        # Initialize signal detector based on filter type
        if filt == FilterType.NONE:
            detector = WickSignalDetector(threshold=threshold)
        else:
            detector = FilteredWickSignalDetector(
                threshold=threshold,
                volume_filter=(filt in [FilterType.VOLUME, FilterType.COMBINED]),
                volume_sma_period=self.volume_sma_period,
                trend_filter=(filt in [FilterType.TREND, FilterType.COMBINED]),
                trend_ema_period=self.trend_ema_period
            )
            detector.precompute_filters(df)

        # Precompute filter values if needed
        volume_sma = None
        trend_ema = None
        if filt in [FilterType.VOLUME, FilterType.COMBINED]:
            volume_sma = df['volume'].rolling(window=self.volume_sma_period).mean()
        if filt in [FilterType.TREND, FilterType.COMBINED]:
            trend_ema = df['close'].ewm(span=self.trend_ema_period, adjust=False).mean()

        # Trading state
        balance = self.initial_balance
        equity_curve = [balance]
        trades: List[WickBacktestTrade] = []
        active_trade: Optional[WickBacktestTrade] = None
        entry_bar_idx: int = 0
        trailing_stop: Optional[float] = None
        remaining_size: float = 0.0
        partial_exit_idx: int = 0

        # Warmup period
        warmup = max(self.volume_sma_period, self.trend_ema_period, 50)

        # Process each bar
        for i in range(warmup, len(df)):
            row = df.iloc[i]
            current_time = df.index[i]
            current_price = row['close']
            current_high = row['high']
            current_low = row['low']
            current_open = row['open']

            # Check active trade exit conditions
            if active_trade:
                exit_reason = None
                exit_price = None

                is_long = active_trade.signal_type == SignalType.LONG

                # Check stop loss first
                if is_long:
                    if current_low <= active_trade.stop_loss:
                        exit_reason = "stop_loss"
                        exit_price = active_trade.stop_loss
                else:
                    if current_high >= active_trade.stop_loss:
                        exit_reason = "stop_loss"
                        exit_price = active_trade.stop_loss

                # Check exit strategy
                if not exit_reason:
                    exit_result = self._check_exit_strategy(
                        trade=active_trade,
                        current_price=current_price,
                        current_high=current_high,
                        current_low=current_low,
                        current_open=current_open,
                        bar_idx=i,
                        entry_bar_idx=entry_bar_idx,
                        exit_strat=exit_strat,
                        trailing_stop=trailing_stop,
                        remaining_size=remaining_size,
                        partial_exit_idx=partial_exit_idx,
                        df=df,
                        detector=detector if exit_strat == ExitStrategy.OPPOSITE_SIGNAL else None
                    )

                    if exit_result:
                        exit_reason, exit_price, new_trailing, new_remaining, new_partial_idx = exit_result

                        # Handle partial exits
                        if exit_reason == "partial_exit":
                            # Calculate partial PnL
                            partial_size = remaining_size * self.scaled_targets[partial_exit_idx][0]
                            if is_long:
                                partial_pnl = (exit_price - active_trade.entry_price) * partial_size
                            else:
                                partial_pnl = (active_trade.entry_price - exit_price) * partial_size

                            active_trade.partial_exits += 1
                            active_trade.scaled_pnl_breakdown[f"partial_{partial_exit_idx}"] = partial_pnl
                            remaining_size = new_remaining
                            partial_exit_idx = new_partial_idx
                            exit_reason = None  # Don't close trade yet

                        if new_trailing is not None:
                            trailing_stop = new_trailing
                            active_trade.stop_loss = trailing_stop

                # Check trailing stop
                if not exit_reason and trailing_stop is not None:
                    if is_long:
                        if current_low <= trailing_stop:
                            exit_reason = "trailing_stop"
                            exit_price = trailing_stop
                    else:
                        if current_high >= trailing_stop:
                            exit_reason = "trailing_stop"
                            exit_price = trailing_stop

                # Close trade if exit triggered
                if exit_reason:
                    active_trade = self._close_trade(
                        active_trade,
                        exit_price or current_price,
                        current_time,
                        exit_reason,
                        remaining_size
                    )

                    # Apply commission
                    commission = (active_trade.exit_price * active_trade.size) * (self.commission_percent / 100)
                    active_trade.pnl -= commission

                    balance += active_trade.pnl
                    trades.append(active_trade)
                    active_trade = None
                    trailing_stop = None
                    remaining_size = 0.0
                    partial_exit_idx = 0

            # Check for new signals (only if no active trade)
            if not active_trade:
                signal = detector.process_bar(
                    timestamp=current_time,
                    open_price=current_open,
                    high=current_high,
                    low=current_low,
                    close=current_price,
                    threshold=threshold
                )

                # Apply filter
                if signal and filt != FilterType.NONE:
                    if not self._passes_filter(
                        signal.signal_type, i, df, volume_sma, trend_ema, filt
                    ):
                        signal = None

                if signal:
                    # Open new trade
                    active_trade = self._open_trade(
                        signal, balance, current_time, df.iloc[:i+1],
                        exit_strat
                    )

                    entry_bar_idx = i
                    remaining_size = active_trade.size
                    partial_exit_idx = 0
                    trailing_stop = None

                    # Apply entry commission
                    commission = (active_trade.entry_price * active_trade.size) * (self.commission_percent / 100)
                    balance -= commission

            # Update equity curve
            if active_trade:
                unrealized_pnl = self._calculate_unrealized_pnl(active_trade, current_price, remaining_size)
                equity_curve.append(balance + unrealized_pnl)
            else:
                equity_curve.append(balance)

        # Close any remaining trade
        if active_trade:
            last_price = df.iloc[-1]['close']
            last_time = df.index[-1]
            active_trade = self._close_trade(
                active_trade, last_price, last_time, "end_of_data", remaining_size
            )
            balance += active_trade.pnl
            trades.append(active_trade)

        return self._calculate_results(trades, equity_curve)

    def _passes_filter(
        self,
        signal_type: SignalType,
        idx: int,
        df: pd.DataFrame,
        volume_sma: Optional[pd.Series],
        trend_ema: Optional[pd.Series],
        filt: FilterType
    ) -> bool:
        """Check if signal passes the configured filters."""
        # Volume filter
        if filt in [FilterType.VOLUME, FilterType.COMBINED]:
            if volume_sma is not None and idx < len(volume_sma):
                current_volume = df.iloc[idx]['volume']
                sma_vol = volume_sma.iloc[idx]
                if pd.notna(sma_vol) and current_volume <= sma_vol:
                    return False

        # Trend filter
        if filt in [FilterType.TREND, FilterType.COMBINED]:
            if trend_ema is not None and idx < len(trend_ema):
                current_price = df.iloc[idx]['close']
                ema_val = trend_ema.iloc[idx]
                if pd.notna(ema_val):
                    if signal_type == SignalType.LONG and current_price < ema_val:
                        return False
                    if signal_type == SignalType.SHORT and current_price > ema_val:
                        return False

        return True

    def _open_trade(
        self,
        signal: WickSignal,
        balance: float,
        current_time: datetime,
        df: pd.DataFrame,
        exit_strat: ExitStrategy
    ) -> WickBacktestTrade:
        """Open a new trade based on wick signal."""
        is_long = signal.signal_type == SignalType.LONG

        # Calculate risk params with wick scaling
        risk_params = self.risk_manager.calculate_wick_risk_params(
            account_balance=balance,
            entry_price=signal.entry_price,
            is_long=is_long,
            candle_high=signal.candle_high,
            candle_low=signal.candle_low,
            wick_pct=signal.wick_pct,
            df=df,
            risk_percent=self.risk_percent
        )

        # Adjust take profit based on exit strategy
        take_profit = self._calculate_take_profit(
            entry_price=signal.entry_price,
            stop_loss=risk_params.stop_loss,
            is_long=is_long,
            exit_strat=exit_strat
        )

        return WickBacktestTrade(
            entry_time=current_time,
            exit_time=None,
            signal_type=signal.signal_type,
            entry_price=signal.entry_price,
            exit_price=None,
            size=risk_params.position_size,
            stop_loss=risk_params.stop_loss,
            take_profit=take_profit,
            wick_pct=signal.wick_pct,
            wick_multiplier=risk_params.wick_multiplier,
            wick_stop_loss=risk_params.wick_stop_loss
        )

    def _calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        is_long: bool,
        exit_strat: ExitStrategy
    ) -> float:
        """Calculate take profit based on exit strategy."""
        sl_distance = abs(entry_price - stop_loss)

        if exit_strat == ExitStrategy.FIXED_10:
            tp_distance = entry_price * 0.10
        elif exit_strat == ExitStrategy.FIXED_15:
            tp_distance = entry_price * 0.15
        elif exit_strat == ExitStrategy.FIXED_20:
            tp_distance = entry_price * 0.20
        elif exit_strat == ExitStrategy.SCALED:
            # For scaled, use highest target (20%)
            tp_distance = entry_price * 0.20
        elif exit_strat == ExitStrategy.RR_2:
            tp_distance = sl_distance * 2
        elif exit_strat == ExitStrategy.RR_3:
            tp_distance = sl_distance * 3
        elif exit_strat == ExitStrategy.RR_4:
            tp_distance = sl_distance * 4
        elif exit_strat == ExitStrategy.TRAILING:
            # No fixed TP for trailing
            tp_distance = entry_price * 1.0  # Large value, won't hit
        elif exit_strat == ExitStrategy.OPPOSITE_SIGNAL:
            # No fixed TP
            tp_distance = entry_price * 1.0
        elif exit_strat == ExitStrategy.TIME_BASED:
            # No fixed TP
            tp_distance = entry_price * 1.0
        else:
            tp_distance = sl_distance * 2  # Default 2:1

        if is_long:
            return entry_price + tp_distance
        else:
            return entry_price - tp_distance

    def _check_exit_strategy(
        self,
        trade: WickBacktestTrade,
        current_price: float,
        current_high: float,
        current_low: float,
        current_open: float,
        bar_idx: int,
        entry_bar_idx: int,
        exit_strat: ExitStrategy,
        trailing_stop: Optional[float],
        remaining_size: float,
        partial_exit_idx: int,
        df: pd.DataFrame,
        detector: Optional[WickSignalDetector]
    ) -> Optional[Tuple[str, float, Optional[float], float, int]]:
        """
        Check exit strategy conditions.

        Returns:
            Tuple of (exit_reason, exit_price, new_trailing_stop, new_remaining_size, new_partial_idx)
            or None if no exit
        """
        is_long = trade.signal_type == SignalType.LONG

        # Fixed percentage exits
        if exit_strat in [ExitStrategy.FIXED_10, ExitStrategy.FIXED_15, ExitStrategy.FIXED_20]:
            pct = {
                ExitStrategy.FIXED_10: 10.0,
                ExitStrategy.FIXED_15: 15.0,
                ExitStrategy.FIXED_20: 20.0
            }[exit_strat]

            target = trade.entry_price * (1 + pct/100) if is_long else trade.entry_price * (1 - pct/100)

            if is_long and current_high >= target:
                return ("take_profit", target, None, remaining_size, partial_exit_idx)
            elif not is_long and current_low <= target:
                return ("take_profit", target, None, remaining_size, partial_exit_idx)

        # R:R based exits
        elif exit_strat in [ExitStrategy.RR_2, ExitStrategy.RR_3, ExitStrategy.RR_4]:
            if is_long and current_high >= trade.take_profit:
                return ("take_profit", trade.take_profit, None, remaining_size, partial_exit_idx)
            elif not is_long and current_low <= trade.take_profit:
                return ("take_profit", trade.take_profit, None, remaining_size, partial_exit_idx)

        # Scaled exit (partial TPs)
        elif exit_strat == ExitStrategy.SCALED:
            if partial_exit_idx < len(self.scaled_targets):
                _, target_pct = self.scaled_targets[partial_exit_idx]
                target = trade.entry_price * (1 + target_pct/100) if is_long else trade.entry_price * (1 - target_pct/100)

                if is_long and current_high >= target:
                    exit_pct = self.scaled_targets[partial_exit_idx][0]
                    new_remaining = remaining_size * (1 - exit_pct)

                    if partial_exit_idx == len(self.scaled_targets) - 1:
                        # Final exit
                        return ("take_profit", target, None, 0.0, partial_exit_idx + 1)
                    else:
                        # Partial exit
                        return ("partial_exit", target, None, new_remaining, partial_exit_idx + 1)

                elif not is_long and current_low <= target:
                    exit_pct = self.scaled_targets[partial_exit_idx][0]
                    new_remaining = remaining_size * (1 - exit_pct)

                    if partial_exit_idx == len(self.scaled_targets) - 1:
                        return ("take_profit", target, None, 0.0, partial_exit_idx + 1)
                    else:
                        return ("partial_exit", target, None, new_remaining, partial_exit_idx + 1)

        # Trailing stop
        elif exit_strat == ExitStrategy.TRAILING:
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price * 100) if is_long else \
                        ((trade.entry_price - current_price) / trade.entry_price * 100)

            if profit_pct >= self.trailing_activation_pct:
                # Activate or update trailing stop
                new_trail = current_price * (1 - self.trailing_distance_pct/100) if is_long else \
                           current_price * (1 + self.trailing_distance_pct/100)

                if trailing_stop is None:
                    return (None, None, new_trail, remaining_size, partial_exit_idx)
                elif is_long and new_trail > trailing_stop:
                    return (None, None, new_trail, remaining_size, partial_exit_idx)
                elif not is_long and new_trail < trailing_stop:
                    return (None, None, new_trail, remaining_size, partial_exit_idx)

        # Opposite signal exit
        elif exit_strat == ExitStrategy.OPPOSITE_SIGNAL:
            if detector:
                current_time = df.index[bar_idx]
                opp_signal = detector.process_bar(
                    timestamp=current_time,
                    open_price=current_open,
                    high=current_high,
                    low=current_low,
                    close=current_price
                )

                if opp_signal:
                    if is_long and opp_signal.signal_type == SignalType.SHORT:
                        return ("opposite_signal", current_price, None, remaining_size, partial_exit_idx)
                    elif not is_long and opp_signal.signal_type == SignalType.LONG:
                        return ("opposite_signal", current_price, None, remaining_size, partial_exit_idx)

        # Time-based exit
        elif exit_strat == ExitStrategy.TIME_BASED:
            bars_held = bar_idx - entry_bar_idx
            if bars_held >= self.time_based_bars:
                return ("time_exit", current_price, None, remaining_size, partial_exit_idx)

        return None

    def _close_trade(
        self,
        trade: WickBacktestTrade,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        remaining_size: float
    ) -> WickBacktestTrade:
        """Close a trade and calculate PnL."""
        is_long = trade.signal_type == SignalType.LONG

        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = reason

        # Calculate PnL on remaining size
        if is_long:
            trade.pnl = (trade.exit_price - trade.entry_price) * remaining_size
        else:
            trade.pnl = (trade.entry_price - trade.exit_price) * remaining_size

        # Add any partial exit PnL
        if trade.scaled_pnl_breakdown:
            trade.pnl += sum(trade.scaled_pnl_breakdown.values())

        trade.pnl_percent = (trade.pnl / (trade.entry_price * trade.size)) * 100

        # Apply leverage to PnL (already reflected in position sizing, but PnL% should show levered return)
        trade.pnl_percent *= self.leverage

        return trade

    def _calculate_unrealized_pnl(
        self,
        trade: WickBacktestTrade,
        current_price: float,
        remaining_size: float
    ) -> float:
        """Calculate unrealized PnL for open trade."""
        if trade.signal_type == SignalType.LONG:
            unrealized = (current_price - trade.entry_price) * remaining_size
        else:
            unrealized = (trade.entry_price - current_price) * remaining_size

        # Add realized partial PnL
        if trade.scaled_pnl_breakdown:
            unrealized += sum(trade.scaled_pnl_breakdown.values())

        return unrealized

    def _calculate_results(
        self,
        trades: List[WickBacktestTrade],
        equity_curve: List[float]
    ) -> BacktestResult:
        """Calculate backtest performance metrics."""
        if not trades:
            return BacktestResult(
                initial_balance=self.initial_balance,
                final_balance=self.initial_balance,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0,
                total_pnl=0,
                total_pnl_percent=0,
                max_drawdown=0,
                max_drawdown_percent=0,
                sharpe_ratio=0,
                profit_factor=0,
                avg_win=0,
                avg_loss=0,
                largest_win=0,
                largest_loss=0,
                avg_trade_duration=0,
                trades=[],
                equity_curve=equity_curve
            )

        # Basic stats
        total_trades = len(trades)
        winners = [t for t in trades if t.pnl > 0]
        losers = [t for t in trades if t.pnl <= 0]

        winning_trades = len(winners)
        losing_trades = len(losers)
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0

        # PnL stats
        total_pnl = sum(t.pnl for t in trades)
        total_pnl_percent = (total_pnl / self.initial_balance) * 100
        final_balance = self.initial_balance + total_pnl

        # Win/Loss stats
        gross_profit = sum(t.pnl for t in winners) if winners else 0
        gross_loss = abs(sum(t.pnl for t in losers)) if losers else 0

        avg_win = gross_profit / len(winners) if winners else 0
        avg_loss = gross_loss / len(losers) if losers else 0
        largest_win = max((t.pnl for t in winners), default=0)
        largest_loss = min((t.pnl for t in losers), default=0)

        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Drawdown
        max_dd, max_dd_pct = self._calculate_max_drawdown(equity_curve)

        # Sharpe ratio (per-trade returns)
        if len(trades) > 1:
            trade_returns = [t.pnl_percent for t in trades]
            returns_std = np.std(trade_returns)
            sharpe = (np.mean(trade_returns) / returns_std * np.sqrt(252)) if returns_std > 0 else 0
        else:
            sharpe = 0

        return BacktestResult(
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            max_drawdown=max_dd,
            max_drawdown_percent=max_dd_pct,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_trade_duration=0,
            trades=trades,
            equity_curve=equity_curve
        )

    def _calculate_max_drawdown(
        self,
        equity_curve: List[float]
    ) -> Tuple[float, float]:
        """Calculate maximum drawdown."""
        peak = equity_curve[0]
        max_dd = 0
        max_dd_pct = 0

        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak) * 100 if peak > 0 else 0

            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        return max_dd, max_dd_pct
