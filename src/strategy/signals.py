"""Base signal types for trading strategies."""

from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class SignalType(str, Enum):
    """Trading signal types."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class AnchorWave:
    """
    Anchor wave data for signal generation.

    Used for wave-based signal systems.
    """
    timestamp: datetime
    wt2_value: float = 0.0
    bar_index: int = 0
    signal_type: SignalType = SignalType.FLAT


@dataclass
class TriggerWave:
    """
    Trigger wave data for signal confirmation.
    """
    timestamp: datetime
    wt2_value: float = 0.0
    bar_index: int = 0
    has_cross: bool = False


@dataclass
class Signal:
    """
    Base trading signal with full context.

    Contains all information needed to execute a trade.
    """
    signal_type: SignalType
    timestamp: datetime
    entry_price: float
    anchor_wave: Optional[AnchorWave] = None
    trigger_wave: Optional[TriggerWave] = None
    wt1: float = 0.0
    wt2: float = 0.0
    vwap: float = 0.0
    mfi: float = 0.0
    confidence: float = 1.0
    timeframe: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "entry_price": self.entry_price,
            "confidence": self.confidence,
            "timeframe": self.timeframe,
            "wt1": self.wt1,
            "wt2": self.wt2,
            "vwap": self.vwap,
            "mfi": self.mfi,
            "metadata": self.metadata
        }

    @property
    def is_long(self) -> bool:
        """Check if signal is long."""
        return self.signal_type == SignalType.LONG

    @property
    def is_short(self) -> bool:
        """Check if signal is short."""
        return self.signal_type == SignalType.SHORT
