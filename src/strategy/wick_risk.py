"""Wick-based risk management with position scaling."""

import pandas as pd
from typing import Optional, Tuple
from dataclasses import dataclass

from strategy.risk import RiskManager, StopLossMethod, RiskParams
from strategy.signals import SignalType


@dataclass
class WickRiskParams(RiskParams):
    """
    Extended risk parameters with wick-specific data.

    Inherits from RiskParams and adds:
    - wick_multiplier: Position size multiplier based on wick size
    - wick_stop_loss: Stop loss at wick extreme
    """
    wick_multiplier: float = 1.0
    wick_stop_loss: float = 0.0


class WickRiskManager(RiskManager):
    """
    Risk manager with wick-based position scaling and stop loss placement.

    Features:
    - Linear position scaling based on wick percentage
    - Stop loss placement at wick extreme
    - Support for position scaling (add-on sizing)
    """

    def __init__(
        self,
        default_risk_percent: float = 3.0,
        default_leverage: float = 3.0,
        default_rr: float = 2.0,
        # Wick-specific parameters
        wick_threshold: float = 1.5,
        max_wick_multiplier: float = 2.0,
        use_wick_stop_loss: bool = True,
        wick_sl_buffer_pct: float = 0.1,
        # Inherited parameters
        swing_lookback: int = 5,
        swing_buffer_percent: float = 0.5,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        fixed_sl_percent: float = 2.0
    ):
        """
        Initialize wick risk manager.

        Args:
            default_risk_percent: Default risk per trade (%)
            default_leverage: Default leverage (3x for wick strategy)
            default_rr: Default risk:reward ratio
            wick_threshold: Baseline wick threshold for scaling
            max_wick_multiplier: Maximum position multiplier from wick size
            use_wick_stop_loss: Use wick extreme for stop loss
            wick_sl_buffer_pct: Buffer beyond wick extreme (%)
            swing_lookback: Candles for swing detection (fallback)
            swing_buffer_percent: Buffer for swing SL (%)
            atr_period: ATR period
            atr_multiplier: ATR multiplier
            fixed_sl_percent: Fixed SL percentage
        """
        super().__init__(
            default_risk_percent=default_risk_percent,
            default_leverage=default_leverage,
            default_rr=default_rr,
            swing_lookback=swing_lookback,
            swing_buffer_percent=swing_buffer_percent,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            fixed_sl_percent=fixed_sl_percent
        )

        self.wick_threshold = wick_threshold
        self.max_wick_multiplier = max_wick_multiplier
        self.use_wick_stop_loss = use_wick_stop_loss
        self.wick_sl_buffer_pct = wick_sl_buffer_pct

    def calculate_wick_multiplier(self, wick_pct: float) -> float:
        """
        Calculate position size multiplier based on wick percentage.

        Linear scaling: multiplier = wick_pct / threshold
        Capped at max_wick_multiplier.

        Args:
            wick_pct: Wick percentage from signal

        Returns:
            Position size multiplier (1.0 to max_wick_multiplier)
        """
        if wick_pct < self.wick_threshold:
            return 1.0

        multiplier = wick_pct / self.wick_threshold
        return min(multiplier, self.max_wick_multiplier)

    def calculate_wick_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        wick_pct: float,
        risk_percent: Optional[float] = None,
        leverage: Optional[float] = None,
        tick_size: float = 0.0001,
        existing_position_size: float = 0.0
    ) -> Tuple[float, float]:
        """
        Calculate position size with wick-based scaling.

        Args:
            account_balance: Total account balance
            entry_price: Planned entry price
            stop_loss_price: Stop loss price
            wick_pct: Wick percentage for scaling
            risk_percent: Risk percentage (uses default if None)
            leverage: Leverage (uses default if None)
            tick_size: Minimum size increment
            existing_position_size: Existing position size for add-ons

        Returns:
            Tuple of (new_position_size, wick_multiplier)
        """
        # Calculate base position size
        base_size = self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_percent=risk_percent,
            leverage=leverage,
            tick_size=tick_size
        )

        # Apply wick multiplier
        wick_multiplier = self.calculate_wick_multiplier(wick_pct)
        scaled_size = base_size * wick_multiplier

        # For add-ons: calculate how much more to add
        if existing_position_size > 0:
            # Scale the add-on by the same multiplier
            addon_size = scaled_size - existing_position_size
            # Don't add if multiplier doesn't warrant it
            if addon_size <= 0:
                return 0.0, wick_multiplier
            return addon_size, wick_multiplier

        return scaled_size, wick_multiplier

    def calculate_wick_stop_loss(
        self,
        candle_high: float,
        candle_low: float,
        is_long: bool,
        buffer_pct: Optional[float] = None
    ) -> float:
        """
        Calculate stop loss at wick extreme.

        For LONG: Stop below the candle low (where buyers stepped in)
        For SHORT: Stop above the candle high (where sellers stepped in)

        Args:
            candle_high: Candle high price
            candle_low: Candle low price
            is_long: True for long positions
            buffer_pct: Buffer percentage beyond wick (optional)

        Returns:
            Stop loss price
        """
        buffer = (buffer_pct if buffer_pct is not None else self.wick_sl_buffer_pct) / 100

        if is_long:
            # Stop below the low
            return candle_low * (1 - buffer)
        else:
            # Stop above the high
            return candle_high * (1 + buffer)

    def calculate_wick_risk_params(
        self,
        account_balance: float,
        entry_price: float,
        is_long: bool,
        candle_high: float,
        candle_low: float,
        wick_pct: float,
        df: Optional[pd.DataFrame] = None,
        risk_percent: Optional[float] = None,
        risk_reward: Optional[float] = None,
        tick_size: float = 0.0001,
        use_wick_sl: Optional[bool] = None
    ) -> WickRiskParams:
        """
        Calculate all risk parameters for a wick-based trade.

        Args:
            account_balance: Account balance
            entry_price: Entry price
            is_long: True for long
            candle_high: Signal candle high
            candle_low: Signal candle low
            wick_pct: Wick percentage for scaling
            df: DataFrame for swing SL (optional, used as fallback)
            risk_percent: Risk percentage
            risk_reward: Risk:reward ratio
            tick_size: Minimum size increment
            use_wick_sl: Override use_wick_stop_loss setting

        Returns:
            WickRiskParams with all calculated values
        """
        use_wick = use_wick_sl if use_wick_sl is not None else self.use_wick_stop_loss

        # Calculate stop loss
        if use_wick:
            stop_loss = self.calculate_wick_stop_loss(
                candle_high=candle_high,
                candle_low=candle_low,
                is_long=is_long
            )
            wick_stop = stop_loss
        else:
            # Fallback to swing or fixed SL
            if df is not None and len(df) > 0:
                stop_loss = self.calculate_stop_loss(
                    entry_price=entry_price,
                    is_long=is_long,
                    df=df,
                    method=StopLossMethod.SWING
                )
            else:
                # Fixed percentage fallback
                sl_distance = entry_price * (self.fixed_sl_percent / 100)
                stop_loss = entry_price - sl_distance if is_long else entry_price + sl_distance
            wick_stop = self.calculate_wick_stop_loss(candle_high, candle_low, is_long)

        # Calculate take profit
        rr = risk_reward or self.default_rr
        take_profit = self.calculate_take_profit(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            is_long=is_long,
            risk_reward=rr
        )

        # Calculate position size with wick scaling
        position_size, wick_multiplier = self.calculate_wick_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            wick_pct=wick_pct,
            risk_percent=risk_percent,
            tick_size=tick_size
        )

        # Calculate risk amount
        risk = (risk_percent or self.default_risk_percent) / 100
        risk_amount = account_balance * risk * wick_multiplier

        return WickRiskParams(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            risk_amount=risk_amount,
            risk_reward=rr,
            wick_multiplier=wick_multiplier,
            wick_stop_loss=wick_stop
        )

    def calculate_addon_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        wick_pct: float,
        existing_size: float,
        original_wick_pct: float,
        risk_percent: Optional[float] = None,
        tick_size: float = 0.0001
    ) -> float:
        """
        Calculate add-on position size when scaling into existing position.

        Only adds more if new wick is stronger than original.

        Args:
            account_balance: Total account balance
            entry_price: Add-on entry price
            stop_loss_price: Current stop loss price
            wick_pct: New wick percentage
            existing_size: Current position size
            original_wick_pct: Original wick percentage that opened position
            risk_percent: Risk percentage
            tick_size: Minimum size increment

        Returns:
            Add-on position size (0 if no add-on warranted)
        """
        # Only add if new wick is stronger than original
        if wick_pct <= original_wick_pct:
            return 0.0

        # Calculate what total position size should be
        new_multiplier = self.calculate_wick_multiplier(wick_pct)
        original_multiplier = self.calculate_wick_multiplier(original_wick_pct)

        # If new multiplier isn't higher, no add-on
        if new_multiplier <= original_multiplier:
            return 0.0

        # Calculate base position size at current conditions
        base_size = self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_percent=risk_percent,
            tick_size=tick_size
        )

        # Target total size with new multiplier
        target_size = base_size * new_multiplier

        # Add-on is difference (capped at 50% of target to limit risk)
        addon = min(target_size - existing_size, target_size * 0.5)

        return max(addon, 0.0)
