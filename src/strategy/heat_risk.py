"""Heat-based risk management system with dynamic position sizing.

Heat represents total portfolio exposure as a percentage of equity.
Position sizing is dynamically adjusted based on current heat level.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from strategy.risk import RiskManager, RiskParams, StopLossMethod


class HeatZone(str, Enum):
    """Heat zone classifications."""
    GREEN = "green"       # 0-30%: Full position sizing
    YELLOW = "yellow"     # 30-60%: Reduced sizing
    RED = "red"           # 60-80%: Minimal sizing
    CRITICAL = "critical" # >80%: No new positions


@dataclass
class HeatState:
    """Current heat state of the portfolio."""
    current_heat: float = 0.0
    zone: HeatZone = HeatZone.GREEN
    position_scale: float = 1.0
    max_heat: float = 80.0
    available_heat: float = 80.0
    recovery_mode: bool = False
    drawdown_pct: float = 0.0
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_heat": self.current_heat,
            "zone": self.zone.value,
            "position_scale": self.position_scale,
            "max_heat": self.max_heat,
            "available_heat": self.available_heat,
            "recovery_mode": self.recovery_mode,
            "drawdown_pct": self.drawdown_pct,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


@dataclass
class PositionHeat:
    """Heat contribution from a single position."""
    symbol: str = ""
    side: str = ""  # "long" or "short"
    entry_price: float = 0.0
    current_price: float = 0.0
    size: float = 0.0
    stop_loss: float = 0.0
    risk_amount: float = 0.0
    heat_contribution: float = 0.0  # As percentage of equity
    unrealized_pnl: float = 0.0

    @property
    def risk_percent(self) -> float:
        """Risk as percentage of entry."""
        if self.entry_price > 0:
            return abs(self.entry_price - self.stop_loss) / self.entry_price * 100
        return 0.0


@dataclass
class HeatRiskParams(RiskParams):
    """
    Extended risk parameters with heat-based adjustments.

    Inherits from RiskParams and adds:
    - heat_adjusted: Whether position was adjusted for heat
    - original_size: Size before heat adjustment
    - heat_scale: Scale factor applied
    - zone: Current heat zone
    """
    heat_adjusted: bool = False
    original_size: float = 0.0
    heat_scale: float = 1.0
    zone: HeatZone = HeatZone.GREEN


class HeatRiskManager(RiskManager):
    """
    Risk manager with heat-based portfolio risk control.

    Heat Zones:
    - Green (0-30%): Full position sizing allowed (100%)
    - Yellow (30-60%): Reduced position sizing (50%)
    - Red (60-80%): Minimal position sizing (25%)
    - Critical (>80%): No new positions (0%)

    Features:
    - Portfolio-level risk tracking
    - Dynamic position sizing based on heat
    - Recovery mode after significant drawdown
    - Real-time heat monitoring
    """

    # Heat zone boundaries
    ZONE_GREEN_MAX = 30.0
    ZONE_YELLOW_MAX = 60.0
    ZONE_RED_MAX = 80.0

    # Position scale factors by zone
    SCALE_GREEN = 1.0
    SCALE_YELLOW = 0.5
    SCALE_RED = 0.25
    SCALE_CRITICAL = 0.0

    # Recovery mode settings
    RECOVERY_DRAWDOWN_THRESHOLD = 20.0  # % drawdown to trigger recovery
    RECOVERY_HEAT_REDUCTION = 0.5  # Reduce heat limits by 50%

    def __init__(
        self,
        default_risk_percent: float = 3.0,
        default_leverage: float = 3.0,
        default_rr: float = 2.0,
        max_portfolio_heat: float = 80.0,
        # Zone boundaries (configurable)
        green_max: float = 30.0,
        yellow_max: float = 60.0,
        red_max: float = 80.0,
        # Scale factors (configurable)
        scale_green: float = 1.0,
        scale_yellow: float = 0.5,
        scale_red: float = 0.25,
        # Recovery settings
        recovery_drawdown_threshold: float = 20.0,
        recovery_heat_reduction: float = 0.5,
        # Inherited parameters
        swing_lookback: int = 5,
        swing_buffer_percent: float = 0.5,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        fixed_sl_percent: float = 2.0
    ):
        """
        Initialize heat risk manager.

        Args:
            default_risk_percent: Default risk per trade (%)
            default_leverage: Default leverage multiplier
            default_rr: Default risk:reward ratio
            max_portfolio_heat: Maximum allowed portfolio heat (%)
            green_max: Upper bound for green zone (%)
            yellow_max: Upper bound for yellow zone (%)
            red_max: Upper bound for red zone (%)
            scale_green: Position scale in green zone
            scale_yellow: Position scale in yellow zone
            scale_red: Position scale in red zone
            recovery_drawdown_threshold: Drawdown % to trigger recovery mode
            recovery_heat_reduction: Heat limit reduction in recovery mode
            swing_lookback: Candles for swing detection
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

        self.max_portfolio_heat = max_portfolio_heat
        self.green_max = green_max
        self.yellow_max = yellow_max
        self.red_max = red_max
        self.scale_green = scale_green
        self.scale_yellow = scale_yellow
        self.scale_red = scale_red
        self.recovery_drawdown_threshold = recovery_drawdown_threshold
        self.recovery_heat_reduction = recovery_heat_reduction

        # State tracking
        self._positions: List[PositionHeat] = []
        self._equity = 0.0
        self._peak_equity = 0.0
        self._recovery_mode = False

    def reset(self) -> None:
        """Reset all state."""
        self._positions = []
        self._equity = 0.0
        self._peak_equity = 0.0
        self._recovery_mode = False

    def update_equity(self, equity: float) -> None:
        """
        Update current equity and check for recovery mode.

        Args:
            equity: Current portfolio equity
        """
        self._equity = equity

        if equity > self._peak_equity:
            self._peak_equity = equity
            self._recovery_mode = False  # Exit recovery on new highs
        elif self._peak_equity > 0:
            drawdown = (self._peak_equity - equity) / self._peak_equity * 100
            if drawdown >= self.recovery_drawdown_threshold:
                self._recovery_mode = True

    def add_position(self, position: PositionHeat) -> None:
        """Add a position to heat tracking."""
        self._positions.append(position)

    def remove_position(self, symbol: str) -> None:
        """Remove a position from heat tracking."""
        self._positions = [p for p in self._positions if p.symbol != symbol]

    def update_position(
        self,
        symbol: str,
        current_price: float,
        unrealized_pnl: Optional[float] = None
    ) -> None:
        """
        Update position with current market price.

        Args:
            symbol: Position symbol
            current_price: Current market price
            unrealized_pnl: Optional pre-calculated unrealized PnL
        """
        for pos in self._positions:
            if pos.symbol == symbol:
                pos.current_price = current_price
                if unrealized_pnl is not None:
                    pos.unrealized_pnl = unrealized_pnl
                elif pos.side == "long":
                    pos.unrealized_pnl = (current_price - pos.entry_price) * pos.size
                else:
                    pos.unrealized_pnl = (pos.entry_price - current_price) * pos.size
                break

    def calculate_portfolio_heat(self) -> float:
        """
        Calculate total portfolio heat.

        Heat = Sum of individual position risks as % of equity.

        Returns:
            Current portfolio heat percentage
        """
        if self._equity <= 0:
            return 0.0

        total_risk = sum(p.risk_amount for p in self._positions)
        return (total_risk / self._equity) * 100

    def get_heat_zone(self, heat: Optional[float] = None) -> HeatZone:
        """
        Determine heat zone for given heat level.

        Args:
            heat: Heat percentage (uses current if None)

        Returns:
            HeatZone enum value
        """
        if heat is None:
            heat = self.calculate_portfolio_heat()

        # Apply recovery mode adjustment to zone boundaries
        if self._recovery_mode:
            effective_green = self.green_max * self.recovery_heat_reduction
            effective_yellow = self.yellow_max * self.recovery_heat_reduction
            effective_red = self.red_max * self.recovery_heat_reduction
        else:
            effective_green = self.green_max
            effective_yellow = self.yellow_max
            effective_red = self.red_max

        if heat <= effective_green:
            return HeatZone.GREEN
        elif heat <= effective_yellow:
            return HeatZone.YELLOW
        elif heat <= effective_red:
            return HeatZone.RED
        else:
            return HeatZone.CRITICAL

    def get_position_scale(self, heat: Optional[float] = None) -> float:
        """
        Get position scale factor for current heat level.

        Args:
            heat: Heat percentage (uses current if None)

        Returns:
            Scale factor (0.0 to 1.0)
        """
        zone = self.get_heat_zone(heat)

        if zone == HeatZone.GREEN:
            return self.scale_green
        elif zone == HeatZone.YELLOW:
            return self.scale_yellow
        elif zone == HeatZone.RED:
            return self.scale_red
        else:
            return 0.0  # Critical - no new positions

    def get_heat_state(self) -> HeatState:
        """
        Get current heat state snapshot.

        Returns:
            HeatState with all current values
        """
        current_heat = self.calculate_portfolio_heat()
        zone = self.get_heat_zone(current_heat)
        scale = self.get_position_scale(current_heat)

        # Calculate effective max heat
        effective_max = self.max_portfolio_heat
        if self._recovery_mode:
            effective_max *= self.recovery_heat_reduction

        # Calculate drawdown
        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - self._equity) / self._peak_equity * 100

        return HeatState(
            current_heat=current_heat,
            zone=zone,
            position_scale=scale,
            max_heat=effective_max,
            available_heat=max(0, effective_max - current_heat),
            recovery_mode=self._recovery_mode,
            drawdown_pct=drawdown,
            timestamp=datetime.now()
        )

    def can_open_position(self, risk_amount: float) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            risk_amount: Risk amount of proposed position

        Returns:
            Tuple of (can_open, reason)
        """
        if self._equity <= 0:
            return False, "No equity"

        current_heat = self.calculate_portfolio_heat()
        zone = self.get_heat_zone(current_heat)

        if zone == HeatZone.CRITICAL:
            return False, f"Critical heat zone ({current_heat:.1f}%)"

        # Check if adding position would exceed max heat
        new_heat = current_heat + (risk_amount / self._equity * 100)
        effective_max = self.max_portfolio_heat
        if self._recovery_mode:
            effective_max *= self.recovery_heat_reduction

        if new_heat > effective_max:
            return False, f"Would exceed max heat ({new_heat:.1f}% > {effective_max:.1f}%)"

        return True, "OK"

    def calculate_heat_adjusted_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percent: Optional[float] = None,
        leverage: Optional[float] = None,
        tick_size: float = 0.0001
    ) -> Tuple[float, float, HeatZone]:
        """
        Calculate position size with heat adjustment.

        Args:
            account_balance: Total account balance
            entry_price: Planned entry price
            stop_loss_price: Stop loss price
            risk_percent: Risk percentage (uses default if None)
            leverage: Leverage (uses default if None)
            tick_size: Minimum size increment

        Returns:
            Tuple of (adjusted_size, scale_factor, heat_zone)
        """
        # Update equity
        self.update_equity(account_balance)

        # Get base position size
        base_size = self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_percent=risk_percent,
            leverage=leverage,
            tick_size=tick_size
        )

        # Apply heat scaling
        current_heat = self.calculate_portfolio_heat()
        zone = self.get_heat_zone(current_heat)
        scale = self.get_position_scale(current_heat)

        adjusted_size = base_size * scale

        # Round to tick size
        if tick_size > 0:
            adjusted_size = round(adjusted_size / tick_size) * tick_size

        return adjusted_size, scale, zone

    def calculate_heat_risk_params(
        self,
        account_balance: float,
        entry_price: float,
        is_long: bool,
        df=None,
        sl_method: StopLossMethod = StopLossMethod.FIXED,
        risk_percent: Optional[float] = None,
        risk_reward: Optional[float] = None,
        tick_size: float = 0.0001
    ) -> HeatRiskParams:
        """
        Calculate all risk parameters with heat adjustment.

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
            HeatRiskParams with all calculated values
        """
        self.update_equity(account_balance)

        # Calculate stop loss
        stop_loss = self.calculate_stop_loss(
            entry_price=entry_price,
            is_long=is_long,
            df=df,
            method=sl_method
        )

        # Calculate take profit
        rr = risk_reward or self.default_rr
        take_profit = self.calculate_take_profit(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            is_long=is_long,
            risk_reward=rr
        )

        # Calculate base position size
        base_size = self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            risk_percent=risk_percent,
            tick_size=tick_size
        )

        # Apply heat adjustment
        current_heat = self.calculate_portfolio_heat()
        zone = self.get_heat_zone(current_heat)
        scale = self.get_position_scale(current_heat)

        adjusted_size = base_size * scale
        if tick_size > 0:
            adjusted_size = round(adjusted_size / tick_size) * tick_size

        # Calculate risk amount
        risk = (risk_percent or self.default_risk_percent) / 100
        base_risk_amount = account_balance * risk
        adjusted_risk_amount = base_risk_amount * scale

        return HeatRiskParams(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=adjusted_size,
            risk_amount=adjusted_risk_amount,
            risk_reward=rr,
            heat_adjusted=scale < 1.0,
            original_size=base_size,
            heat_scale=scale,
            zone=zone
        )

    def get_positions_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked positions."""
        total_unrealized = sum(p.unrealized_pnl for p in self._positions)
        total_risk = sum(p.risk_amount for p in self._positions)

        return {
            "position_count": len(self._positions),
            "total_risk_amount": total_risk,
            "total_unrealized_pnl": total_unrealized,
            "current_heat": self.calculate_portfolio_heat(),
            "equity": self._equity,
            "peak_equity": self._peak_equity,
            "recovery_mode": self._recovery_mode,
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "size": p.size,
                    "risk_amount": p.risk_amount,
                    "heat_contribution": p.heat_contribution,
                    "unrealized_pnl": p.unrealized_pnl
                }
                for p in self._positions
            ]
        }

    def save_state(self, filepath: str) -> bool:
        """
        Save heat state to file for persistence across restarts.

        Args:
            filepath: Path to save state file

        Returns:
            True if saved successfully
        """
        try:
            state = {
                "equity": self._equity,
                "peak_equity": self._peak_equity,
                "recovery_mode": self._recovery_mode,
                "positions": [
                    {
                        "symbol": p.symbol,
                        "side": p.side,
                        "entry_price": p.entry_price,
                        "current_price": p.current_price,
                        "size": p.size,
                        "stop_loss": p.stop_loss,
                        "risk_amount": p.risk_amount,
                        "heat_contribution": p.heat_contribution,
                        "unrealized_pnl": p.unrealized_pnl
                    }
                    for p in self._positions
                ],
                "saved_at": datetime.now().isoformat()
            }

            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w') as f:
                json.dump(state, f, indent=2)

            return True
        except Exception as e:
            # Log error but don't fail - persistence is optional
            return False

    def load_state(self, filepath: str) -> bool:
        """
        Load heat state from file.

        Args:
            filepath: Path to state file

        Returns:
            True if loaded successfully
        """
        try:
            path = Path(filepath)
            if not path.exists():
                return False

            with open(path, 'r') as f:
                state = json.load(f)

            self._equity = state.get("equity", 0.0)
            self._peak_equity = state.get("peak_equity", 0.0)
            self._recovery_mode = state.get("recovery_mode", False)

            # Restore positions
            self._positions = []
            for p in state.get("positions", []):
                self._positions.append(PositionHeat(
                    symbol=p.get("symbol", ""),
                    side=p.get("side", ""),
                    entry_price=p.get("entry_price", 0.0),
                    current_price=p.get("current_price", 0.0),
                    size=p.get("size", 0.0),
                    stop_loss=p.get("stop_loss", 0.0),
                    risk_amount=p.get("risk_amount", 0.0),
                    heat_contribution=p.get("heat_contribution", 0.0),
                    unrealized_pnl=p.get("unrealized_pnl", 0.0)
                ))

            return True
        except Exception as e:
            # Log error but don't fail - will start fresh
            return False


# Preset configurations for different risk profiles
class RiskPreset(str, Enum):
    """Pre-defined risk profiles."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    DEGEN = "degen"


RISK_PRESETS: Dict[RiskPreset, Dict[str, Any]] = {
    RiskPreset.CONSERVATIVE: {
        "risk_percent": 3.0,
        "leverage": 3.0,
        "max_heat": 30.0,
        "green_max": 15.0,
        "yellow_max": 25.0,
        "red_max": 30.0,
    },
    RiskPreset.MODERATE: {
        "risk_percent": 5.0,
        "leverage": 5.0,
        "max_heat": 50.0,
        "green_max": 25.0,
        "yellow_max": 40.0,
        "red_max": 50.0,
    },
    RiskPreset.AGGRESSIVE: {
        "risk_percent": 10.0,
        "leverage": 7.0,
        "max_heat": 70.0,
        "green_max": 35.0,
        "yellow_max": 55.0,
        "red_max": 70.0,
    },
    RiskPreset.DEGEN: {
        "risk_percent": 15.0,
        "leverage": 10.0,
        "max_heat": 90.0,
        "green_max": 45.0,
        "yellow_max": 70.0,
        "red_max": 90.0,
    },
}


def create_heat_manager_from_preset(preset: RiskPreset) -> HeatRiskManager:
    """
    Create a HeatRiskManager with preset configuration.

    Args:
        preset: RiskPreset enum value

    Returns:
        Configured HeatRiskManager
    """
    config = RISK_PRESETS[preset]
    return HeatRiskManager(
        default_risk_percent=config["risk_percent"],
        default_leverage=config["leverage"],
        max_portfolio_heat=config["max_heat"],
        green_max=config["green_max"],
        yellow_max=config["yellow_max"],
        red_max=config["red_max"],
    )
