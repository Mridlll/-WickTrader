"""Base risk management system."""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class StopLossMethod(str, Enum):
    """Stop loss calculation methods."""
    FIXED = "fixed"          # Fixed percentage
    SWING = "swing"          # Swing high/low based
    ATR = "atr"              # ATR-based
    VOLATILITY = "volatility"


@dataclass
class RiskParams:
    """
    Risk parameters for a trade.

    Contains all risk-related values needed for position management.
    """
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0
    risk_amount: float = 0.0
    risk_reward: float = 0.0

    @property
    def risk_percent(self) -> float:
        """Calculate risk as percentage of entry."""
        if self.entry_price > 0:
            return abs(self.entry_price - self.stop_loss) / self.entry_price * 100
        return 0.0

    @property
    def reward_percent(self) -> float:
        """Calculate reward as percentage of entry."""
        if self.entry_price > 0:
            return abs(self.take_profit - self.entry_price) / self.entry_price * 100
        return 0.0


class RiskManager:
    """
    Base risk manager for position sizing and stop loss calculation.

    Features:
    - Multiple stop loss methods
    - Position sizing based on risk percentage
    - Take profit calculation with R:R ratio
    - Leverage support
    """

    def __init__(
        self,
        default_risk_percent: float = 2.0,
        default_leverage: float = 1.0,
        default_rr: float = 2.0,
        swing_lookback: int = 5,
        swing_buffer_percent: float = 0.5,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        fixed_sl_percent: float = 2.0
    ):
        """
        Initialize risk manager.

        Args:
            default_risk_percent: Default risk per trade (%)
            default_leverage: Default leverage multiplier
            default_rr: Default risk:reward ratio
            swing_lookback: Lookback period for swing detection
            swing_buffer_percent: Buffer beyond swing for SL (%)
            atr_period: ATR period for ATR-based SL
            atr_multiplier: Multiplier for ATR SL
            fixed_sl_percent: Fixed stop loss percentage
        """
        self.default_risk_percent = default_risk_percent
        self.default_leverage = default_leverage
        self.default_rr = default_rr
        self.swing_lookback = swing_lookback
        self.swing_buffer_percent = swing_buffer_percent
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.fixed_sl_percent = fixed_sl_percent

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percent: Optional[float] = None,
        leverage: Optional[float] = None,
        tick_size: float = 0.0001
    ) -> float:
        """
        Calculate position size based on risk amount.

        Args:
            account_balance: Total account balance
            entry_price: Planned entry price
            stop_loss_price: Stop loss price
            risk_percent: Risk percentage (uses default if None)
            leverage: Leverage (uses default if None)
            tick_size: Minimum size increment

        Returns:
            Position size in base currency
        """
        risk = (risk_percent or self.default_risk_percent) / 100
        lev = leverage or self.default_leverage

        risk_amount = account_balance * risk
        sl_distance = abs(entry_price - stop_loss_price)

        if sl_distance == 0:
            return 0.0

        # Position size = risk amount / SL distance
        position_size = risk_amount / sl_distance

        # Cap by leverage
        max_position_value = account_balance * lev
        max_position_size = max_position_value / entry_price

        position_size = min(position_size, max_position_size)

        # Round to tick size
        if tick_size > 0:
            position_size = round(position_size / tick_size) * tick_size

        return position_size

    def calculate_stop_loss(
        self,
        entry_price: float,
        is_long: bool,
        df: Optional[pd.DataFrame] = None,
        method: StopLossMethod = StopLossMethod.FIXED,
        atr_value: Optional[float] = None
    ) -> float:
        """
        Calculate stop loss price using specified method.

        Args:
            entry_price: Entry price
            is_long: True for long positions
            df: DataFrame for swing/ATR calculations
            method: Stop loss method
            atr_value: Pre-calculated ATR value (optional)

        Returns:
            Stop loss price
        """
        if method == StopLossMethod.FIXED:
            sl_distance = entry_price * (self.fixed_sl_percent / 100)
            return entry_price - sl_distance if is_long else entry_price + sl_distance

        elif method == StopLossMethod.SWING:
            if df is None or len(df) < self.swing_lookback:
                # Fallback to fixed
                return self.calculate_stop_loss(entry_price, is_long, method=StopLossMethod.FIXED)

            lookback_data = df.iloc[-self.swing_lookback:]

            if is_long:
                swing_low = lookback_data['low'].min()
                buffer = swing_low * (self.swing_buffer_percent / 100)
                return swing_low - buffer
            else:
                swing_high = lookback_data['high'].max()
                buffer = swing_high * (self.swing_buffer_percent / 100)
                return swing_high + buffer

        elif method == StopLossMethod.ATR:
            if atr_value is None:
                if df is None or len(df) < self.atr_period:
                    return self.calculate_stop_loss(entry_price, is_long, method=StopLossMethod.FIXED)

                # Calculate ATR
                high = df['high']
                low = df['low']
                close = df['close']

                tr1 = high - low
                tr2 = abs(high - close.shift())
                tr3 = abs(low - close.shift())
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr_value = tr.rolling(window=self.atr_period).mean().iloc[-1]

            sl_distance = atr_value * self.atr_multiplier
            return entry_price - sl_distance if is_long else entry_price + sl_distance

        # Default fallback
        sl_distance = entry_price * (self.fixed_sl_percent / 100)
        return entry_price - sl_distance if is_long else entry_price + sl_distance

    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss_price: float,
        is_long: bool,
        risk_reward: Optional[float] = None
    ) -> float:
        """
        Calculate take profit price based on R:R ratio.

        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            is_long: True for long positions
            risk_reward: Risk:reward ratio (uses default if None)

        Returns:
            Take profit price
        """
        rr = risk_reward or self.default_rr
        sl_distance = abs(entry_price - stop_loss_price)
        tp_distance = sl_distance * rr

        if is_long:
            return entry_price + tp_distance
        else:
            return entry_price - tp_distance

    def calculate_risk_params(
        self,
        account_balance: float,
        entry_price: float,
        is_long: bool,
        df: Optional[pd.DataFrame] = None,
        sl_method: StopLossMethod = StopLossMethod.FIXED,
        risk_percent: Optional[float] = None,
        risk_reward: Optional[float] = None,
        tick_size: float = 0.0001
    ) -> RiskParams:
        """
        Calculate all risk parameters for a trade.

        Args:
            account_balance: Account balance
            entry_price: Entry price
            is_long: True for long
            df: DataFrame for swing/ATR SL
            sl_method: Stop loss method
            risk_percent: Risk percentage
            risk_reward: Risk:reward ratio
            tick_size: Minimum size increment

        Returns:
            RiskParams with all calculated values
        """
        stop_loss = self.calculate_stop_loss(
            entry_price=entry_price,
            is_long=is_long,
            df=df,
            method=sl_method
        )

        take_profit = self.calculate_take_profit(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            is_long=is_long,
            risk_reward=risk_reward
        )

        position_size = self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            risk_percent=risk_percent,
            tick_size=tick_size
        )

        risk = (risk_percent or self.default_risk_percent) / 100
        risk_amount = account_balance * risk

        return RiskParams(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            risk_amount=risk_amount,
            risk_reward=risk_reward or self.default_rr
        )
