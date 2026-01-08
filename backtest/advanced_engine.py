"""Advanced backtesting engine with heat-based risk and cross-margin support.

Integrates:
- Heat-based risk management
- Cross-margin portfolio accounting
- Multiple risk profiles (Conservative, Moderate, Aggressive, Degen)
- Comprehensive metrics tracking
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np

from backtest.engine import BacktestTrade, BacktestResult, SignalType
from backtest.portfolio_engine import CrossMarginPortfolio, CrossMarginPosition, ClosedTrade
from strategy.heat_risk import (
    HeatRiskManager, HeatZone, HeatState, PositionHeat,
    RiskPreset, RISK_PRESETS, create_heat_manager_from_preset
)
from strategy.wick_signals import WickSignalDetector, WickSignal, FilteredWickSignalDetector
from indicators.wick import WickCalculator
from utils.logger import get_logger

logger = get_logger("advanced_backtest")


class ExitType(str, Enum):
    """Exit strategy types."""
    FIXED_PCT = "fixed_pct"      # Fixed percentage target
    RR_RATIO = "rr_ratio"        # Risk:Reward ratio
    TRAILING = "trailing"        # Trailing stop
    TIME_BASED = "time_based"    # Exit after N bars
    OPPOSITE_SIGNAL = "opposite" # Exit on opposite signal


@dataclass
class AdvancedTradeRecord(BacktestTrade):
    """Extended trade record with advanced metrics."""
    # Heat information
    heat_at_entry: float = 0.0
    heat_zone: HeatZone = HeatZone.GREEN
    position_scale: float = 1.0

    # Wick information
    wick_pct: float = 0.0
    wick_multiplier: float = 1.0

    # Cross-margin information
    initial_margin: float = 0.0
    leverage_used: float = 1.0
    margin_utilization: float = 0.0

    # Bars held
    bars_held: int = 0


@dataclass
class RiskProfile:
    """Risk profile configuration."""
    name: str
    risk_percent: float
    leverage: float
    max_heat: float
    green_max: float
    yellow_max: float
    red_max: float

    @classmethod
    def from_preset(cls, preset: RiskPreset) -> "RiskProfile":
        """Create from preset."""
        config = RISK_PRESETS[preset]
        return cls(
            name=preset.value,
            risk_percent=config["risk_percent"],
            leverage=config["leverage"],
            max_heat=config["max_heat"],
            green_max=config["green_max"],
            yellow_max=config["yellow_max"],
            red_max=config["red_max"]
        )


# Pre-defined risk profiles
RISK_PROFILES = {
    "conservative": RiskProfile(
        name="conservative",
        risk_percent=3.0,
        leverage=3.0,
        max_heat=30.0,
        green_max=15.0,
        yellow_max=25.0,
        red_max=30.0
    ),
    "moderate": RiskProfile(
        name="moderate",
        risk_percent=5.0,
        leverage=5.0,
        max_heat=50.0,
        green_max=25.0,
        yellow_max=40.0,
        red_max=50.0
    ),
    "aggressive": RiskProfile(
        name="aggressive",
        risk_percent=10.0,
        leverage=7.0,
        max_heat=70.0,
        green_max=35.0,
        yellow_max=55.0,
        red_max=70.0
    ),
    "degen": RiskProfile(
        name="degen",
        risk_percent=15.0,
        leverage=10.0,
        max_heat=90.0,
        green_max=45.0,
        yellow_max=70.0,
        red_max=90.0
    )
}


class AdvancedBacktestEngine:
    """
    Advanced backtesting engine with heat-based risk management.

    Features:
    - Heat-based position sizing with dynamic scaling
    - Cross-margin portfolio accounting
    - Multiple risk profiles (degen mode support)
    - Comprehensive trade and equity tracking
    - Recovery mode after drawdowns
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        risk_profile: str = "moderate",
        commission_rate: float = 0.0006,
        slippage_pct: float = 0.05,
        # Signal parameters
        wick_threshold: float = 4.0,
        direction: str = "both",  # "long", "short", "both"
        # Exit parameters
        exit_type: ExitType = ExitType.RR_RATIO,
        fixed_tp_pct: float = 10.0,
        rr_ratio: float = 2.0,
        trailing_activation_pct: float = 8.0,
        trailing_distance_pct: float = 4.0,
        time_exit_bars: int = 30,
        # Stop loss
        use_wick_sl: bool = True,
        fixed_sl_pct: float = 3.0,
        # Cooldown
        cooldown_bars: int = 3,
        # Custom risk profile (overrides preset)
        custom_risk_profile: Optional[RiskProfile] = None
    ):
        """
        Initialize advanced backtest engine.

        Args:
            initial_balance: Starting balance
            risk_profile: Risk profile name or "custom"
            commission_rate: Commission rate per side
            slippage_pct: Slippage percentage
            wick_threshold: Minimum wick percentage for signals
            direction: Trade direction ("long", "short", "both")
            exit_type: Exit strategy type
            fixed_tp_pct: Fixed take profit percentage
            rr_ratio: Risk:Reward ratio
            trailing_activation_pct: Trailing activation percentage
            trailing_distance_pct: Trailing distance percentage
            time_exit_bars: Max bars for time-based exit
            use_wick_sl: Use wick extreme for stop loss
            fixed_sl_pct: Fixed stop loss percentage
            cooldown_bars: Cooldown between trades
            custom_risk_profile: Custom risk profile configuration
        """
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.slippage_pct = slippage_pct
        self.wick_threshold = wick_threshold
        self.direction = direction
        self.exit_type = exit_type
        self.fixed_tp_pct = fixed_tp_pct
        self.rr_ratio = rr_ratio
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_distance_pct = trailing_distance_pct
        self.time_exit_bars = time_exit_bars
        self.use_wick_sl = use_wick_sl
        self.fixed_sl_pct = fixed_sl_pct
        self.cooldown_bars = cooldown_bars

        # Set risk profile
        if custom_risk_profile:
            self.risk_profile = custom_risk_profile
        elif risk_profile in RISK_PROFILES:
            self.risk_profile = RISK_PROFILES[risk_profile]
        else:
            self.risk_profile = RISK_PROFILES["moderate"]

        # Initialize components
        self._init_components()

    def _init_components(self) -> None:
        """Initialize trading components."""
        # Heat risk manager
        self.heat_manager = HeatRiskManager(
            default_risk_percent=self.risk_profile.risk_percent,
            default_leverage=self.risk_profile.leverage,
            max_portfolio_heat=self.risk_profile.max_heat,
            green_max=self.risk_profile.green_max,
            yellow_max=self.risk_profile.yellow_max,
            red_max=self.risk_profile.red_max,
            fixed_sl_percent=self.fixed_sl_pct
        )

        # Cross-margin portfolio
        self.portfolio = CrossMarginPortfolio(
            initial_balance=self.initial_balance,
            max_leverage=self.risk_profile.leverage,
            commission_rate=self.commission_rate
        )

        # Signal detector
        self.signal_detector = WickSignalDetector(
            threshold=self.wick_threshold
        )

        # Wick calculator
        self.wick_calc = WickCalculator(threshold=self.wick_threshold)

    def reset(self) -> None:
        """Reset engine state."""
        self._init_components()

    def run(
        self,
        df: pd.DataFrame,
        warmup_bars: int = 50
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            df: DataFrame with OHLCV data
            warmup_bars: Number of warmup bars before trading

        Returns:
            BacktestResult with performance metrics
        """
        self.reset()

        logger.info(f"Running advanced backtest with {self.risk_profile.name} profile")
        logger.info(f"  Risk: {self.risk_profile.risk_percent}%, Leverage: {self.risk_profile.leverage}x, Max Heat: {self.risk_profile.max_heat}%")
        logger.info(f"  Wick threshold: {self.wick_threshold}%, Direction: {self.direction}, Exit: {self.exit_type.value}")

        # Trading state
        trades: List[AdvancedTradeRecord] = []
        active_position: Optional[CrossMarginPosition] = None
        entry_bar_idx: int = 0
        trailing_stop: Optional[float] = None
        last_trade_bar: int = -self.cooldown_bars

        # Process each bar
        for i in range(warmup_bars, len(df)):
            row = df.iloc[i]
            timestamp = df.index[i]
            current_price = row['close']
            current_high = row['high']
            current_low = row['low']
            current_open = row['open']

            # Update portfolio with current prices
            if active_position:
                # Check exit conditions
                exit_result = self._check_exit(
                    position=active_position,
                    current_price=current_price,
                    current_high=current_high,
                    current_low=current_low,
                    current_open=current_open,
                    bar_idx=i,
                    entry_bar_idx=entry_bar_idx,
                    trailing_stop=trailing_stop,
                    df=df
                )

                if exit_result:
                    exit_reason, exit_price, new_trailing = exit_result

                    if exit_reason:
                        # Close position
                        bars_held = i - entry_bar_idx
                        trade_record = self._close_position(
                            position=active_position,
                            exit_price=exit_price,
                            exit_time=timestamp,
                            exit_reason=exit_reason,
                            bars_held=bars_held
                        )

                        if trade_record:
                            trades.append(trade_record)

                        active_position = None
                        trailing_stop = None
                        last_trade_bar = i
                    elif new_trailing is not None:
                        trailing_stop = new_trailing

            # Check for new signals (only if no active position and cooldown passed)
            if active_position is None and (i - last_trade_bar) >= self.cooldown_bars:
                signal = self._check_signal(
                    timestamp=timestamp,
                    open_price=current_open,
                    high=current_high,
                    low=current_low,
                    close=current_price
                )

                if signal:
                    # Check if we can open position
                    position, trade_meta = self._open_position(
                        signal=signal,
                        timestamp=timestamp,
                        df=df.iloc[:i+1]
                    )

                    if position:
                        active_position = position
                        entry_bar_idx = i
                        trailing_stop = None
                        trades.append(trade_meta)  # Store trade metadata

            # Update heat manager with current equity
            self.heat_manager.update_equity(self.portfolio.equity)

            # Record equity
            self.portfolio.record_equity()

        # Close any remaining position at end of data
        if active_position:
            last_price = df.iloc[-1]['close']
            last_time = df.index[-1]
            bars_held = len(df) - entry_bar_idx

            trade_record = self._close_position(
                position=active_position,
                exit_price=last_price,
                exit_time=last_time,
                exit_reason="end_of_data",
                bars_held=bars_held
            )

            if trade_record:
                trades.append(trade_record)

        # Calculate results
        return self._calculate_results(trades, df)

    def _check_signal(
        self,
        timestamp: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float
    ) -> Optional[WickSignal]:
        """Check for wick signal."""
        signal = self.signal_detector.process_bar(
            timestamp=timestamp,
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            threshold=self.wick_threshold
        )

        if signal:
            # Filter by direction
            if self.direction == "long" and signal.signal_type != SignalType.LONG:
                return None
            if self.direction == "short" and signal.signal_type != SignalType.SHORT:
                return None

        return signal

    def _open_position(
        self,
        signal: WickSignal,
        timestamp: datetime,
        df: pd.DataFrame
    ) -> Tuple[Optional[CrossMarginPosition], Optional[AdvancedTradeRecord]]:
        """
        Open a new position based on signal.

        Returns:
            Tuple of (position, trade_record)
        """
        is_long = signal.signal_type == SignalType.LONG

        # Calculate stop loss
        if self.use_wick_sl:
            if is_long:
                stop_loss = signal.candle_low * (1 - 0.001)  # Small buffer
            else:
                stop_loss = signal.candle_high * (1 + 0.001)
        else:
            sl_pct = self.fixed_sl_pct / 100
            if is_long:
                stop_loss = signal.entry_price * (1 - sl_pct)
            else:
                stop_loss = signal.entry_price * (1 + sl_pct)

        # Calculate take profit
        sl_distance = abs(signal.entry_price - stop_loss)

        if self.exit_type == ExitType.FIXED_PCT:
            tp_distance = signal.entry_price * (self.fixed_tp_pct / 100)
        elif self.exit_type == ExitType.RR_RATIO:
            tp_distance = sl_distance * self.rr_ratio
        else:
            tp_distance = signal.entry_price * 0.20  # Large value for trailing/time

        if is_long:
            take_profit = signal.entry_price + tp_distance
        else:
            take_profit = signal.entry_price - tp_distance

        # Get heat-adjusted position size
        heat_state = self.heat_manager.get_heat_state()

        # Check if we can open
        if heat_state.zone == HeatZone.CRITICAL:
            logger.debug(f"Cannot open position - critical heat zone ({heat_state.current_heat:.1f}%)")
            return None, None

        # Calculate risk params with heat adjustment
        heat_params = self.heat_manager.calculate_heat_risk_params(
            account_balance=self.portfolio.equity,
            entry_price=signal.entry_price,
            is_long=is_long,
            df=df
        )

        # Apply slippage to entry
        slippage_mult = 1 + self.slippage_pct / 100
        if is_long:
            entry_price = signal.entry_price * slippage_mult
        else:
            entry_price = signal.entry_price / slippage_mult

        # Calculate position size
        position_size = heat_params.position_size

        if position_size <= 0:
            return None, None

        # Open position in portfolio
        position = self.portfolio.open_position(
            symbol="SYMBOL",
            side=signal.signal_type,
            size=position_size,
            entry_price=entry_price,
            leverage=self.risk_profile.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=timestamp
        )

        if not position:
            return None, None

        # Track position in heat manager
        pos_heat = PositionHeat(
            symbol="SYMBOL",
            side="long" if is_long else "short",
            entry_price=entry_price,
            current_price=entry_price,
            size=position_size,
            stop_loss=stop_loss,
            risk_amount=heat_params.risk_amount,
            heat_contribution=(heat_params.risk_amount / self.portfolio.equity * 100)
        )
        self.heat_manager.add_position(pos_heat)

        # Create trade record (will be updated on close)
        trade_record = AdvancedTradeRecord(
            entry_time=timestamp,
            signal_type=signal.signal_type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=position_size,
            heat_at_entry=heat_state.current_heat,
            heat_zone=heat_state.zone,
            position_scale=heat_params.heat_scale,
            wick_pct=signal.wick_pct,
            initial_margin=position.initial_margin,
            leverage_used=self.risk_profile.leverage,
            margin_utilization=self.portfolio.margin_utilization
        )

        return position, trade_record

    def _check_exit(
        self,
        position: CrossMarginPosition,
        current_price: float,
        current_high: float,
        current_low: float,
        current_open: float,
        bar_idx: int,
        entry_bar_idx: int,
        trailing_stop: Optional[float],
        df: pd.DataFrame
    ) -> Optional[Tuple[Optional[str], float, Optional[float]]]:
        """
        Check exit conditions.

        Returns:
            Tuple of (exit_reason, exit_price, new_trailing_stop) or None
        """
        is_long = position.side == SignalType.LONG
        bars_held = bar_idx - entry_bar_idx

        # Update position PnL
        position.update_pnl(current_price)

        # Check stop loss
        if is_long:
            if current_low <= position.stop_loss:
                return ("stop_loss", position.stop_loss, None)
        else:
            if current_high >= position.stop_loss:
                return ("stop_loss", position.stop_loss, None)

        # Check trailing stop
        if trailing_stop is not None:
            if is_long:
                if current_low <= trailing_stop:
                    return ("trailing_stop", trailing_stop, None)
            else:
                if current_high >= trailing_stop:
                    return ("trailing_stop", trailing_stop, None)

        # Exit type specific checks
        if self.exit_type == ExitType.FIXED_PCT or self.exit_type == ExitType.RR_RATIO:
            # Check take profit
            if is_long:
                if current_high >= position.take_profit:
                    return ("take_profit", position.take_profit, None)
            else:
                if current_low <= position.take_profit:
                    return ("take_profit", position.take_profit, None)

        elif self.exit_type == ExitType.TRAILING:
            # Calculate profit percentage
            if is_long:
                profit_pct = (current_price - position.entry_price) / position.entry_price * 100
            else:
                profit_pct = (position.entry_price - current_price) / position.entry_price * 100

            if profit_pct >= self.trailing_activation_pct:
                # Activate or update trailing stop
                if is_long:
                    new_trail = current_price * (1 - self.trailing_distance_pct / 100)
                    if trailing_stop is None or new_trail > trailing_stop:
                        return (None, 0, new_trail)
                else:
                    new_trail = current_price * (1 + self.trailing_distance_pct / 100)
                    if trailing_stop is None or new_trail < trailing_stop:
                        return (None, 0, new_trail)

        elif self.exit_type == ExitType.TIME_BASED:
            if bars_held >= self.time_exit_bars:
                return ("time_exit", current_price, None)

        elif self.exit_type == ExitType.OPPOSITE_SIGNAL:
            # Check for opposite signal
            opp_signal = self.signal_detector.process_bar(
                timestamp=df.index[bar_idx],
                open_price=current_open,
                high=current_high,
                low=current_low,
                close=current_price,
                threshold=self.wick_threshold
            )

            if opp_signal:
                if is_long and opp_signal.signal_type == SignalType.SHORT:
                    return ("opposite_signal", current_price, None)
                elif not is_long and opp_signal.signal_type == SignalType.LONG:
                    return ("opposite_signal", current_price, None)

        return None

    def _close_position(
        self,
        position: CrossMarginPosition,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        bars_held: int
    ) -> Optional[AdvancedTradeRecord]:
        """Close position and create trade record."""
        # Apply slippage to exit
        is_long = position.side == SignalType.LONG
        slippage_mult = 1 - self.slippage_pct / 100

        if is_long:
            exit_price = exit_price * slippage_mult
        else:
            exit_price = exit_price / slippage_mult

        # Close in portfolio
        closed_trade = self.portfolio.close_position(
            symbol=position.symbol,
            exit_price=exit_price,
            exit_time=exit_time,
            exit_reason=exit_reason,
            bars_held=bars_held
        )

        if not closed_trade:
            return None

        # Remove from heat manager
        self.heat_manager.remove_position(position.symbol)

        # Get current heat state
        heat_state = self.heat_manager.get_heat_state()

        # Create comprehensive trade record
        trade_record = AdvancedTradeRecord(
            entry_time=position.entry_time,
            exit_time=exit_time,
            signal_type=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            size=position.size,
            pnl=closed_trade.net_pnl,
            pnl_percent=closed_trade.pnl_percent,
            exit_reason=exit_reason,
            commission=closed_trade.total_fees,
            heat_at_entry=0,  # Would need to track from open
            heat_zone=heat_state.zone,
            position_scale=1.0,
            initial_margin=position.initial_margin,
            leverage_used=position.leverage,
            margin_utilization=self.portfolio.margin_utilization,
            bars_held=bars_held
        )

        return trade_record

    def _calculate_results(
        self,
        trades: List[AdvancedTradeRecord],
        df: pd.DataFrame
    ) -> BacktestResult:
        """Calculate comprehensive backtest results."""
        # Get portfolio summary
        summary = self.portfolio.get_summary()

        # Filter to only closed trades (have exit prices)
        closed_trades = [t for t in trades if t.exit_price is not None]

        if not closed_trades:
            return BacktestResult(
                initial_balance=self.initial_balance,
                final_balance=self.portfolio.balance,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                total_pnl_percent=0.0,
                max_drawdown=0.0,
                max_drawdown_percent=0.0,
                sharpe_ratio=0.0,
                profit_factor=0.0,
                equity_curve=self.portfolio.equity_curve,
                drawdown_curve=self.portfolio.drawdown_curve,
                parameters={
                    "risk_profile": self.risk_profile.name,
                    "wick_threshold": self.wick_threshold,
                    "exit_type": self.exit_type.value,
                    "direction": self.direction,
                }
            )

        # Calculate metrics
        winners = [t for t in closed_trades if t.pnl > 0]
        losers = [t for t in closed_trades if t.pnl <= 0]

        gross_profit = sum(t.pnl for t in winners) if winners else 0
        gross_loss = abs(sum(t.pnl for t in losers)) if losers else 0

        total_pnl = sum(t.pnl for t in closed_trades)
        total_pnl_pct = total_pnl / self.initial_balance * 100

        # Risk metrics
        pnl_returns = [t.pnl_percent for t in closed_trades]
        if len(pnl_returns) > 1:
            avg_return = np.mean(pnl_returns)
            std_return = np.std(pnl_returns)
            sharpe = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0

            downside_returns = [r for r in pnl_returns if r < 0]
            downside_std = np.std(downside_returns) if downside_returns else 0
            sortino = (avg_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0
        else:
            sharpe = 0
            sortino = 0

        # Max drawdown
        max_dd_pct = max(self.portfolio.drawdown_curve) if self.portfolio.drawdown_curve else 0
        max_dd = self.initial_balance * max_dd_pct / 100

        # Calmar ratio
        calmar = (total_pnl_pct / max_dd_pct) if max_dd_pct > 0 else 0

        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Expectancy
        win_rate = len(winners) / len(closed_trades) if closed_trades else 0
        avg_win = gross_profit / len(winners) if winners else 0
        avg_loss = gross_loss / len(losers) if losers else 0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        # Recovery factor
        recovery_factor = total_pnl / max_dd if max_dd > 0 else 0

        # CAGR (approximate)
        trading_days = len(df) / 6  # Assuming 4H candles, ~6 per day
        years = trading_days / 365
        if years > 0:
            cagr = ((self.portfolio.balance / self.initial_balance) ** (1/years) - 1) * 100
        else:
            cagr = 0

        # Volatility
        if len(pnl_returns) > 1:
            volatility = np.std(pnl_returns) * np.sqrt(252)
        else:
            volatility = 0

        return BacktestResult(
            initial_balance=self.initial_balance,
            final_balance=self.portfolio.balance,
            total_trades=len(closed_trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=win_rate * 100,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_pct,
            max_drawdown=max_dd,
            max_drawdown_percent=max_dd_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            profit_factor=profit_factor,
            expectancy=expectancy,
            recovery_factor=recovery_factor,
            cagr=cagr,
            volatility=volatility,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=max((t.pnl for t in winners), default=0),
            largest_loss=min((t.pnl for t in losers), default=0),
            avg_trade_duration=np.mean([t.bars_held for t in closed_trades]) if closed_trades else 0,
            trades=closed_trades,
            equity_curve=self.portfolio.equity_curve,
            drawdown_curve=self.portfolio.drawdown_curve,
            start_date=df.index[0],
            end_date=df.index[-1],
            parameters={
                "risk_profile": self.risk_profile.name,
                "risk_percent": self.risk_profile.risk_percent,
                "leverage": self.risk_profile.leverage,
                "max_heat": self.risk_profile.max_heat,
                "wick_threshold": self.wick_threshold,
                "exit_type": self.exit_type.value,
                "direction": self.direction,
                "fixed_tp_pct": self.fixed_tp_pct if self.exit_type == ExitType.FIXED_PCT else None,
                "rr_ratio": self.rr_ratio if self.exit_type == ExitType.RR_RATIO else None,
            }
        )


def run_advanced_backtest(
    df: pd.DataFrame,
    risk_profile: str = "moderate",
    wick_threshold: float = 4.0,
    exit_type: str = "rr_ratio",
    direction: str = "both",
    **kwargs
) -> BacktestResult:
    """
    Convenience function to run advanced backtest.

    Args:
        df: DataFrame with OHLCV data
        risk_profile: Risk profile name
        wick_threshold: Wick threshold percentage
        exit_type: Exit type string
        direction: Trade direction
        **kwargs: Additional engine parameters

    Returns:
        BacktestResult
    """
    engine = AdvancedBacktestEngine(
        risk_profile=risk_profile,
        wick_threshold=wick_threshold,
        exit_type=ExitType(exit_type),
        direction=direction,
        **kwargs
    )

    return engine.run(df)
