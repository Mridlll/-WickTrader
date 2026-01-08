"""Wick-based signal detection for trading strategy."""

import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from strategy.signals import SignalType, Signal, AnchorWave, TriggerWave
from indicators.wick import WickCalculator, WickData, WickResult


@dataclass
class WickSignal:
    """
    Trading signal based on wick analysis.

    Extends the base Signal concept with wick-specific data.
    """
    signal_type: SignalType
    timestamp: datetime
    entry_price: float
    wick_pct: float  # The wick percentage that triggered the signal
    candle_high: float
    candle_low: float
    candle_open: float
    candle_close: float
    confidence: float = 1.0
    timeframe: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_signal(self) -> Signal:
        """
        Convert to standard Signal object for compatibility with existing systems.
        """
        # Create dummy anchor/trigger waves for compatibility
        anchor = AnchorWave(
            timestamp=self.timestamp,
            wt2_value=0.0,  # Not used for wick signals
            bar_index=0,
            signal_type=self.signal_type
        )
        trigger = TriggerWave(
            timestamp=self.timestamp,
            wt2_value=0.0,
            bar_index=0,
            has_cross=True
        )

        return Signal(
            signal_type=self.signal_type,
            timestamp=self.timestamp,
            entry_price=self.entry_price,
            anchor_wave=anchor,
            trigger_wave=trigger,
            wt1=0.0,
            wt2=0.0,
            vwap=0.0,
            mfi=0.0,
            confidence=self.confidence,
            timeframe=self.timeframe,
            metadata={
                **self.metadata,
                "source": "wick",
                "wick_pct": self.wick_pct,
                "candle_high": self.candle_high,
                "candle_low": self.candle_low,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/export."""
        return {
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "entry_price": self.entry_price,
            "wick_pct": self.wick_pct,
            "candle_high": self.candle_high,
            "candle_low": self.candle_low,
            "confidence": self.confidence,
            "timeframe": self.timeframe,
        }


class WickSignalDetector:
    """
    Signal detector based on wick analysis.

    Wick-Based Signal Logic:
    - LONG: Lower wick >= threshold (buyers rejected lower prices)
    - SHORT: Upper wick >= threshold (sellers rejected higher prices)

    The wick percentage is included in the signal for position sizing.
    """

    def __init__(
        self,
        threshold: float = 1.5,
        timeframe: str = "4h",
        require_body_confirmation: bool = False,
        min_candle_range_pct: float = 0.0
    ):
        """
        Initialize wick signal detector.

        Args:
            threshold: Minimum wick percentage to trigger signal (default 1.5%)
            timeframe: Timeframe identifier for logging
            require_body_confirmation: If True, require body to be in signal direction
            min_candle_range_pct: Minimum candle range as % of close (filter out doji)
        """
        self.threshold = threshold
        self.timeframe = timeframe
        self.require_body_confirmation = require_body_confirmation
        self.min_candle_range_pct = min_candle_range_pct

        self.wick_calc = WickCalculator(threshold=threshold)
        self._signals_history: List[WickSignal] = []

    def reset(self) -> None:
        """Reset detector state."""
        self._signals_history = []

    def process_bar(
        self,
        timestamp: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        threshold: Optional[float] = None
    ) -> Optional[WickSignal]:
        """
        Process a single bar and check for wick signals.

        Args:
            timestamp: Bar timestamp
            open_price: Candle open
            high: Candle high
            low: Candle low
            close: Candle close
            threshold: Optional threshold override

        Returns:
            WickSignal if conditions met, None otherwise
        """
        thresh = threshold if threshold is not None else self.threshold

        # Calculate wick data
        wick_data = self.wick_calc.calculate_single(
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            threshold=thresh
        )

        # Check minimum candle range
        if self.min_candle_range_pct > 0:
            range_pct = (wick_data.candle_range / close) * 100 if close > 0 else 0
            if range_pct < self.min_candle_range_pct:
                return None

        # Check for bullish signal (long lower wick)
        if wick_data.is_bullish_wick:
            # Optional body confirmation: close > open (bullish body)
            if self.require_body_confirmation and close <= open_price:
                pass  # Skip if body doesn't confirm
            else:
                signal = WickSignal(
                    signal_type=SignalType.LONG,
                    timestamp=timestamp,
                    entry_price=close,
                    wick_pct=wick_data.lower_wick_pct,
                    candle_high=high,
                    candle_low=low,
                    candle_open=open_price,
                    candle_close=close,
                    confidence=self._calculate_confidence(wick_data.lower_wick_pct, thresh),
                    timeframe=self.timeframe,
                    metadata={
                        "body_pct": wick_data.body_pct,
                        "upper_wick_pct": wick_data.upper_wick_pct,
                        "lower_wick_ratio": wick_data.lower_wick_ratio,
                    }
                )
                self._signals_history.append(signal)
                return signal

        # Check for bearish signal (long upper wick)
        if wick_data.is_bearish_wick:
            # Optional body confirmation: close < open (bearish body)
            if self.require_body_confirmation and close >= open_price:
                pass  # Skip if body doesn't confirm
            else:
                signal = WickSignal(
                    signal_type=SignalType.SHORT,
                    timestamp=timestamp,
                    entry_price=close,
                    wick_pct=wick_data.upper_wick_pct,
                    candle_high=high,
                    candle_low=low,
                    candle_open=open_price,
                    candle_close=close,
                    confidence=self._calculate_confidence(wick_data.upper_wick_pct, thresh),
                    timeframe=self.timeframe,
                    metadata={
                        "body_pct": wick_data.body_pct,
                        "lower_wick_pct": wick_data.lower_wick_pct,
                        "upper_wick_ratio": wick_data.upper_wick_ratio,
                    }
                )
                self._signals_history.append(signal)
                return signal

        return None

    def process_dataframe(
        self,
        df: pd.DataFrame,
        threshold: Optional[float] = None
    ) -> List[WickSignal]:
        """
        Process entire DataFrame and return all signals.

        Args:
            df: DataFrame with OHLC data (must have timestamp index)
            threshold: Optional threshold override

        Returns:
            List of all WickSignals found
        """
        signals = []
        thresh = threshold if threshold is not None else self.threshold

        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = df.index[i]

            signal = self.process_bar(
                timestamp=timestamp,
                open_price=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                threshold=thresh
            )

            if signal:
                signals.append(signal)

        return signals

    def _calculate_confidence(self, wick_pct: float, threshold: float) -> float:
        """
        Calculate confidence score based on wick size.

        Larger wicks (relative to threshold) get higher confidence.

        Args:
            wick_pct: Wick percentage
            threshold: Threshold used

        Returns:
            Confidence score 0.0-1.0
        """
        # Scale: at threshold = 0.5, at 2x threshold = 1.0
        ratio = wick_pct / threshold
        confidence = min(ratio / 2.0, 1.0)
        return max(confidence, 0.5)  # Floor at 0.5 since we triggered

    def get_current_state(self) -> Dict[str, Any]:
        """Get current state of the detector."""
        return {
            "mode": "wick",
            "threshold": self.threshold,
            "timeframe": self.timeframe,
            "signals_count": len(self._signals_history),
            "require_body_confirmation": self.require_body_confirmation,
        }

    @property
    def signals_history(self) -> List[WickSignal]:
        """Get history of all generated signals."""
        return self._signals_history.copy()


class FilteredWickSignalDetector(WickSignalDetector):
    """
    Wick signal detector with additional filters.

    Supports:
    - Volume filter (above N-period SMA)
    - Trend filter (price vs EMA)
    - Combined filters
    """

    def __init__(
        self,
        threshold: float = 1.5,
        timeframe: str = "4h",
        require_body_confirmation: bool = False,
        min_candle_range_pct: float = 0.0,
        # Filter settings
        volume_filter: bool = False,
        volume_sma_period: int = 20,
        trend_filter: bool = False,
        trend_ema_period: int = 50
    ):
        """
        Initialize filtered wick signal detector.

        Args:
            threshold: Minimum wick percentage to trigger signal
            timeframe: Timeframe identifier
            require_body_confirmation: Require body to confirm signal direction
            min_candle_range_pct: Minimum candle range filter
            volume_filter: Enable volume filter
            volume_sma_period: SMA period for volume filter
            trend_filter: Enable trend filter
            trend_ema_period: EMA period for trend filter
        """
        super().__init__(
            threshold=threshold,
            timeframe=timeframe,
            require_body_confirmation=require_body_confirmation,
            min_candle_range_pct=min_candle_range_pct
        )

        self.volume_filter = volume_filter
        self.volume_sma_period = volume_sma_period
        self.trend_filter = trend_filter
        self.trend_ema_period = trend_ema_period

        # Precomputed filter values (set externally)
        self._volume_sma: Optional[pd.Series] = None
        self._trend_ema: Optional[pd.Series] = None

    def precompute_filters(self, df: pd.DataFrame) -> None:
        """
        Precompute filter values for the entire DataFrame.

        Call this before processing bars.

        Args:
            df: DataFrame with OHLC + volume data
        """
        if self.volume_filter and 'volume' in df.columns:
            self._volume_sma = df['volume'].rolling(window=self.volume_sma_period).mean()

        if self.trend_filter:
            self._trend_ema = df['close'].ewm(span=self.trend_ema_period, adjust=False).mean()

    def check_filters(
        self,
        idx: int,
        signal_type: SignalType,
        df: pd.DataFrame
    ) -> bool:
        """
        Check if filters pass for a potential signal.

        Args:
            idx: Current bar index
            signal_type: Type of signal (LONG/SHORT)
            df: DataFrame with OHLC data

        Returns:
            True if all filters pass
        """
        # Volume filter: current volume > SMA
        if self.volume_filter and self._volume_sma is not None:
            if idx >= self.volume_sma_period:
                current_volume = df.iloc[idx]['volume']
                sma_volume = self._volume_sma.iloc[idx]
                if pd.notna(sma_volume) and current_volume <= sma_volume:
                    return False

        # Trend filter: align with EMA direction
        if self.trend_filter and self._trend_ema is not None:
            if idx >= self.trend_ema_period:
                current_price = df.iloc[idx]['close']
                ema_value = self._trend_ema.iloc[idx]
                if pd.notna(ema_value):
                    if signal_type == SignalType.LONG and current_price < ema_value:
                        return False  # Don't go long below EMA
                    if signal_type == SignalType.SHORT and current_price > ema_value:
                        return False  # Don't go short above EMA

        return True

    def get_current_state(self) -> Dict[str, Any]:
        """Get current state of the detector."""
        state = super().get_current_state()
        state.update({
            "volume_filter": self.volume_filter,
            "volume_sma_period": self.volume_sma_period,
            "trend_filter": self.trend_filter,
            "trend_ema_period": self.trend_ema_period,
        })
        return state
