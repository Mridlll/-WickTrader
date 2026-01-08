"""Wick-based indicator for detecting rejection candles."""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class WickData:
    """
    Wick analysis data for a single candle.

    Attributes:
        upper_wick_pct: Upper wick as percentage of close price
        lower_wick_pct: Lower wick as percentage of close price
        body_pct: Body size as percentage of close price
        is_bullish_wick: True if lower wick >= threshold (buyers rejected lower prices)
        is_bearish_wick: True if upper wick >= threshold (sellers rejected higher prices)
        candle_range: Total candle range (high - low)
        upper_wick_ratio: Upper wick as ratio of total range
        lower_wick_ratio: Lower wick as ratio of total range
    """
    upper_wick_pct: float
    lower_wick_pct: float
    body_pct: float
    is_bullish_wick: bool
    is_bearish_wick: bool
    candle_range: float
    upper_wick_ratio: float
    lower_wick_ratio: float


@dataclass
class WickResult:
    """
    Result of wick calculations for an entire DataFrame.

    Attributes:
        upper_wick_pct: Series of upper wick percentages
        lower_wick_pct: Series of lower wick percentages
        body_pct: Series of body percentages
        is_bullish_wick: Series of bullish wick flags
        is_bearish_wick: Series of bearish wick flags
    """
    upper_wick_pct: pd.Series
    lower_wick_pct: pd.Series
    body_pct: pd.Series
    is_bullish_wick: pd.Series
    is_bearish_wick: pd.Series


class WickCalculator:
    """
    Calculator for wick-based trading signals.

    Wick analysis helps identify rejection candles:
    - Long lower wick = buyers rejected lower prices (bullish)
    - Long upper wick = sellers rejected higher prices (bearish)
    """

    def __init__(self, threshold: float = 1.5):
        """
        Initialize wick calculator.

        Args:
            threshold: Minimum wick percentage to be considered significant (default 1.5%)
        """
        self.threshold = threshold

    def calculate_single(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float,
        threshold: Optional[float] = None
    ) -> WickData:
        """
        Calculate wick data for a single candle.

        Args:
            open_price: Candle open price
            high: Candle high price
            low: Candle low price
            close: Candle close price
            threshold: Optional threshold override

        Returns:
            WickData with all wick metrics
        """
        thresh = threshold if threshold is not None else self.threshold

        # Calculate body boundaries
        body_high = max(open_price, close)
        body_low = min(open_price, close)

        # Calculate wick lengths
        upper_wick = high - body_high
        lower_wick = body_low - low
        body = body_high - body_low
        candle_range = high - low

        # Calculate percentages (relative to close price)
        if close > 0:
            upper_wick_pct = (upper_wick / close) * 100
            lower_wick_pct = (lower_wick / close) * 100
            body_pct = (body / close) * 100
        else:
            upper_wick_pct = 0.0
            lower_wick_pct = 0.0
            body_pct = 0.0

        # Calculate ratios (relative to total range)
        if candle_range > 0:
            upper_wick_ratio = upper_wick / candle_range
            lower_wick_ratio = lower_wick / candle_range
        else:
            upper_wick_ratio = 0.0
            lower_wick_ratio = 0.0

        # Determine wick significance
        is_bullish_wick = lower_wick_pct >= thresh
        is_bearish_wick = upper_wick_pct >= thresh

        return WickData(
            upper_wick_pct=upper_wick_pct,
            lower_wick_pct=lower_wick_pct,
            body_pct=body_pct,
            is_bullish_wick=is_bullish_wick,
            is_bearish_wick=is_bearish_wick,
            candle_range=candle_range,
            upper_wick_ratio=upper_wick_ratio,
            lower_wick_ratio=lower_wick_ratio
        )

    def calculate(
        self,
        df: pd.DataFrame,
        threshold: Optional[float] = None
    ) -> WickResult:
        """
        Calculate wick data for entire DataFrame.

        Args:
            df: DataFrame with OHLC columns (open, high, low, close)
            threshold: Optional threshold override

        Returns:
            WickResult with all wick series
        """
        thresh = threshold if threshold is not None else self.threshold

        open_col = df['open']
        high_col = df['high']
        low_col = df['low']
        close_col = df['close']

        # Calculate body boundaries
        body_high = np.maximum(open_col, close_col)
        body_low = np.minimum(open_col, close_col)

        # Calculate wick lengths
        upper_wick = high_col - body_high
        lower_wick = body_low - low_col
        body = body_high - body_low

        # Calculate percentages (relative to close)
        upper_wick_pct = (upper_wick / close_col) * 100
        lower_wick_pct = (lower_wick / close_col) * 100
        body_pct = (body / close_col) * 100

        # Determine wick significance
        is_bullish_wick = lower_wick_pct >= thresh
        is_bearish_wick = upper_wick_pct >= thresh

        return WickResult(
            upper_wick_pct=upper_wick_pct,
            lower_wick_pct=lower_wick_pct,
            body_pct=body_pct,
            is_bullish_wick=is_bullish_wick,
            is_bearish_wick=is_bearish_wick
        )

    def get_wick_at_index(
        self,
        df: pd.DataFrame,
        idx: int,
        threshold: Optional[float] = None
    ) -> WickData:
        """
        Get wick data for a specific candle index.

        Args:
            df: DataFrame with OHLC columns
            idx: Index of the candle
            threshold: Optional threshold override

        Returns:
            WickData for the specified candle
        """
        row = df.iloc[idx]
        return self.calculate_single(
            open_price=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            threshold=threshold
        )
