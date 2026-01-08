"""Strategy package for WickTrader.

Provides:
- Base signal types (SignalType, Signal)
- Base risk management (RiskManager, RiskParams)
- Wick-based signal detection
- Wick-based risk management
- Heat-based portfolio risk management
"""

from .signals import SignalType, Signal, AnchorWave, TriggerWave
from .risk import RiskManager, RiskParams, StopLossMethod
from .wick_signals import WickSignalDetector, WickSignal, FilteredWickSignalDetector
from .wick_risk import WickRiskManager, WickRiskParams
from .heat_risk import (
    HeatRiskManager, HeatZone, HeatState, PositionHeat, HeatRiskParams,
    RiskPreset, RISK_PRESETS, create_heat_manager_from_preset
)

__all__ = [
    # Base signals
    'SignalType',
    'Signal',
    'AnchorWave',
    'TriggerWave',

    # Base risk
    'RiskManager',
    'RiskParams',
    'StopLossMethod',

    # Wick signals
    'WickSignalDetector',
    'WickSignal',
    'FilteredWickSignalDetector',

    # Wick risk
    'WickRiskManager',
    'WickRiskParams',

    # Heat risk
    'HeatRiskManager',
    'HeatZone',
    'HeatState',
    'PositionHeat',
    'HeatRiskParams',
    'RiskPreset',
    'RISK_PRESETS',
    'create_heat_manager_from_preset',
]
