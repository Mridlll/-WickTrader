"""Cross-margin portfolio engine for backtesting.

Handles unified margin pool where all positions share collateral.
Real-time PnL affects available margin and liquidation price.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from backtest.engine import SignalType


class MarginMode(str, Enum):
    """Margin mode types."""
    CROSS = "cross"       # Unified margin pool
    ISOLATED = "isolated" # Separate margin per position


class PositionStatus(str, Enum):
    """Position status types."""
    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


@dataclass
class CrossMarginPosition:
    """
    Position in cross-margin portfolio.

    All positions share the unified margin pool.
    """
    symbol: str = ""
    side: SignalType = SignalType.FLAT
    entry_price: float = 0.0
    current_price: float = 0.0
    size: float = 0.0
    leverage: float = 1.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    entry_time: Optional[datetime] = None
    status: PositionStatus = PositionStatus.OPEN

    # Calculated fields
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    notional_value: float = 0.0
    initial_margin: float = 0.0
    maintenance_margin: float = 0.0
    margin_ratio: float = 0.0

    # Fees
    entry_fee: float = 0.0
    total_fees: float = 0.0

    def update_pnl(self, current_price: float) -> None:
        """
        Update unrealized PnL with current market price.

        Args:
            current_price: Current market price
        """
        self.current_price = current_price
        self.notional_value = self.size * current_price

        if self.side == SignalType.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        elif self.side == SignalType.SHORT:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size

        if self.entry_price > 0:
            self.unrealized_pnl_pct = self.unrealized_pnl / (self.entry_price * self.size) * 100

    def is_stop_hit(self, low: float, high: float) -> bool:
        """Check if stop loss was hit."""
        if self.stop_loss <= 0:
            return False
        if self.side == SignalType.LONG:
            return low <= self.stop_loss
        elif self.side == SignalType.SHORT:
            return high >= self.stop_loss
        return False

    def is_tp_hit(self, low: float, high: float) -> bool:
        """Check if take profit was hit."""
        if self.take_profit <= 0:
            return False
        if self.side == SignalType.LONG:
            return high >= self.take_profit
        elif self.side == SignalType.SHORT:
            return low <= self.take_profit
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary."""
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "size": self.size,
            "leverage": self.leverage,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "notional_value": self.notional_value,
            "initial_margin": self.initial_margin,
            "maintenance_margin": self.maintenance_margin,
            "status": self.status.value,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
        }


@dataclass
class PortfolioState:
    """Snapshot of portfolio state."""
    timestamp: datetime
    equity: float = 0.0
    balance: float = 0.0  # Wallet balance (realized)
    unrealized_pnl: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    margin_utilization: float = 0.0  # Percentage
    total_notional: float = 0.0
    liquidation_price: Optional[float] = None
    position_count: int = 0
    heat_percent: float = 0.0


@dataclass
class ClosedTrade:
    """Record of a closed trade."""
    symbol: str = ""
    side: SignalType = SignalType.FLAT
    entry_price: float = 0.0
    exit_price: float = 0.0
    size: float = 0.0
    leverage: float = 1.0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    exit_reason: str = ""
    gross_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    pnl_percent: float = 0.0
    bars_held: int = 0
    initial_margin: float = 0.0


class CrossMarginPortfolio:
    """
    Cross-margin portfolio engine.

    Features:
    - Unified margin pool for all positions
    - Real-time PnL affects available margin
    - Portfolio-level liquidation price calculation
    - Margin utilization tracking
    - Multi-position support
    """

    # Margin rates (configurable)
    DEFAULT_INITIAL_MARGIN_RATE = 0.10  # 10% = 10x max leverage
    DEFAULT_MAINTENANCE_MARGIN_RATE = 0.05  # 5%

    def __init__(
        self,
        initial_balance: float = 10000.0,
        max_leverage: float = 10.0,
        commission_rate: float = 0.0006,  # 0.06%
        funding_rate: float = 0.0001,  # 0.01% per 8 hours (not used in backtest)
        initial_margin_rate: float = 0.10,
        maintenance_margin_rate: float = 0.05,
        liquidation_buffer: float = 0.005,  # 0.5% buffer before liquidation
    ):
        """
        Initialize cross-margin portfolio.

        Args:
            initial_balance: Starting wallet balance
            max_leverage: Maximum allowed leverage
            commission_rate: Trading fee rate (both sides)
            funding_rate: Funding rate (not used in simple backtest)
            initial_margin_rate: Initial margin requirement
            maintenance_margin_rate: Maintenance margin requirement
            liquidation_buffer: Buffer before liquidation trigger
        """
        self.initial_balance = initial_balance
        self.max_leverage = max_leverage
        self.commission_rate = commission_rate
        self.funding_rate = funding_rate
        self.initial_margin_rate = initial_margin_rate
        self.maintenance_margin_rate = maintenance_margin_rate
        self.liquidation_buffer = liquidation_buffer

        # State
        self._balance = initial_balance  # Wallet balance (realized)
        self._positions: Dict[str, CrossMarginPosition] = {}
        self._closed_trades: List[ClosedTrade] = []
        self._equity_curve: List[float] = [initial_balance]
        self._drawdown_curve: List[float] = [0.0]
        self._peak_equity = initial_balance
        self._current_bar = 0

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self._balance = self.initial_balance
        self._positions = {}
        self._closed_trades = []
        self._equity_curve = [self.initial_balance]
        self._drawdown_curve = [0.0]
        self._peak_equity = self.initial_balance
        self._current_bar = 0

    @property
    def balance(self) -> float:
        """Get wallet balance (realized P&L only)."""
        return self._balance

    @property
    def equity(self) -> float:
        """Get total equity (balance + unrealized P&L)."""
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        return self._balance + unrealized

    @property
    def unrealized_pnl(self) -> float:
        """Get total unrealized P&L."""
        return sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def margin_used(self) -> float:
        """Get total margin used by open positions."""
        return sum(p.initial_margin for p in self._positions.values())

    @property
    def margin_available(self) -> float:
        """Get available margin for new positions."""
        return max(0, self.equity - self.margin_used)

    @property
    def margin_utilization(self) -> float:
        """Get margin utilization percentage."""
        if self.equity <= 0:
            return 100.0
        return (self.margin_used / self.equity) * 100

    @property
    def total_notional(self) -> float:
        """Get total notional value of all positions."""
        return sum(p.notional_value for p in self._positions.values())

    @property
    def position_count(self) -> int:
        """Get number of open positions."""
        return len(self._positions)

    def get_position(self, symbol: str) -> Optional[CrossMarginPosition]:
        """Get position by symbol."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> List[CrossMarginPosition]:
        """Get all open positions."""
        return list(self._positions.values())

    def calculate_position_margin(
        self,
        size: float,
        entry_price: float,
        leverage: float
    ) -> Tuple[float, float]:
        """
        Calculate initial and maintenance margin for a position.

        Args:
            size: Position size
            entry_price: Entry price
            leverage: Position leverage

        Returns:
            Tuple of (initial_margin, maintenance_margin)
        """
        notional = size * entry_price

        # Initial margin based on leverage
        initial_margin = notional / leverage

        # Maintenance margin
        maintenance_margin = notional * self.maintenance_margin_rate

        return initial_margin, maintenance_margin

    def can_open_position(
        self,
        size: float,
        entry_price: float,
        leverage: float
    ) -> Tuple[bool, str]:
        """
        Check if position can be opened.

        Args:
            size: Proposed position size
            entry_price: Entry price
            leverage: Leverage

        Returns:
            Tuple of (can_open, reason)
        """
        if leverage > self.max_leverage:
            return False, f"Leverage {leverage}x exceeds max {self.max_leverage}x"

        initial_margin, _ = self.calculate_position_margin(size, entry_price, leverage)
        entry_fee = size * entry_price * self.commission_rate

        required_margin = initial_margin + entry_fee

        if required_margin > self.margin_available:
            return False, f"Insufficient margin: need ${required_margin:.2f}, have ${self.margin_available:.2f}"

        return True, "OK"

    def open_position(
        self,
        symbol: str,
        side: SignalType,
        size: float,
        entry_price: float,
        leverage: float = 3.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        entry_time: Optional[datetime] = None
    ) -> Optional[CrossMarginPosition]:
        """
        Open a new position.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            size: Position size
            entry_price: Entry price
            leverage: Position leverage
            stop_loss: Stop loss price
            take_profit: Take profit price
            entry_time: Entry timestamp

        Returns:
            CrossMarginPosition if successful, None otherwise
        """
        # Check if position already exists
        if symbol in self._positions:
            return None

        # Validate
        can_open, reason = self.can_open_position(size, entry_price, leverage)
        if not can_open:
            return None

        # Calculate margin
        initial_margin, maintenance_margin = self.calculate_position_margin(
            size, entry_price, leverage
        )

        # Calculate entry fee
        entry_fee = size * entry_price * self.commission_rate
        self._balance -= entry_fee

        # Create position
        position = CrossMarginPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=entry_price,
            size=size,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=entry_time,
            status=PositionStatus.OPEN,
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            notional_value=size * entry_price,
            entry_fee=entry_fee,
            total_fees=entry_fee
        )

        self._positions[symbol] = position
        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_time: Optional[datetime] = None,
        exit_reason: str = "manual",
        bars_held: int = 0
    ) -> Optional[ClosedTrade]:
        """
        Close an existing position.

        Args:
            symbol: Trading symbol
            exit_price: Exit price
            exit_time: Exit timestamp
            exit_reason: Reason for exit
            bars_held: Number of bars position was held

        Returns:
            ClosedTrade record if successful, None otherwise
        """
        if symbol not in self._positions:
            return None

        position = self._positions[symbol]

        # Calculate final PnL
        if position.side == SignalType.LONG:
            gross_pnl = (exit_price - position.entry_price) * position.size
        else:
            gross_pnl = (position.entry_price - exit_price) * position.size

        # Exit fee
        exit_fee = position.size * exit_price * self.commission_rate
        total_fees = position.entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees

        # Update balance
        self._balance += net_pnl

        # Create closed trade record
        trade = ClosedTrade(
            symbol=symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            leverage=position.leverage,
            entry_time=position.entry_time,
            exit_time=exit_time,
            exit_reason=exit_reason,
            gross_pnl=gross_pnl,
            total_fees=total_fees,
            net_pnl=net_pnl,
            pnl_percent=(net_pnl / position.initial_margin * 100) if position.initial_margin > 0 else 0,
            bars_held=bars_held,
            initial_margin=position.initial_margin
        )

        self._closed_trades.append(trade)

        # Remove position
        del self._positions[symbol]

        return trade

    def update_positions(self, prices: Dict[str, float]) -> List[str]:
        """
        Update all positions with current prices.

        Args:
            prices: Dict of symbol -> current price

        Returns:
            List of symbols that were liquidated
        """
        liquidated = []

        for symbol, position in list(self._positions.items()):
            if symbol in prices:
                position.update_pnl(prices[symbol])

                # Update maintenance margin ratio
                if self.equity > 0:
                    position.margin_ratio = position.maintenance_margin / self.equity

        # Check for liquidation
        if self._should_liquidate():
            liquidated = self._liquidate_all()

        return liquidated

    def update_single_position(
        self,
        symbol: str,
        current_price: float,
        current_low: float,
        current_high: float
    ) -> Tuple[Optional[str], float]:
        """
        Update a single position and check exit conditions.

        Args:
            symbol: Position symbol
            current_price: Current close price
            current_low: Current bar low
            current_high: Current bar high

        Returns:
            Tuple of (exit_reason or None, exit_price)
        """
        if symbol not in self._positions:
            return None, 0.0

        position = self._positions[symbol]
        position.update_pnl(current_price)

        # Check stop loss
        if position.is_stop_hit(current_low, current_high):
            return "stop_loss", position.stop_loss

        # Check take profit
        if position.is_tp_hit(current_low, current_high):
            return "take_profit", position.take_profit

        return None, 0.0

    def _should_liquidate(self) -> bool:
        """Check if portfolio should be liquidated."""
        if not self._positions:
            return False

        total_maintenance = sum(p.maintenance_margin for p in self._positions.values())

        # Liquidation when equity < maintenance margin + buffer
        liquidation_threshold = total_maintenance * (1 + self.liquidation_buffer)

        return self.equity < liquidation_threshold

    def _liquidate_all(self) -> List[str]:
        """
        Liquidate all positions.

        Returns:
            List of liquidated symbols
        """
        liquidated = []

        for symbol in list(self._positions.keys()):
            position = self._positions[symbol]

            # Close at current price (liquidation)
            trade = self.close_position(
                symbol=symbol,
                exit_price=position.current_price,
                exit_reason="liquidation"
            )

            if trade:
                trade.exit_reason = "liquidation"
                liquidated.append(symbol)

        return liquidated

    def calculate_liquidation_price(self, symbol: str) -> Optional[float]:
        """
        Calculate liquidation price for a specific position.

        For cross-margin, this is an approximation as other positions
        affect the liquidation level.

        Args:
            symbol: Position symbol

        Returns:
            Estimated liquidation price or None
        """
        if symbol not in self._positions:
            return None

        position = self._positions[symbol]

        # Total maintenance margin needed
        total_maintenance = sum(p.maintenance_margin for p in self._positions.values())
        liquidation_equity = total_maintenance * (1 + self.liquidation_buffer)

        # How much can this position lose before liquidation
        other_unrealized = sum(
            p.unrealized_pnl for s, p in self._positions.items() if s != symbol
        )

        max_loss = self._balance + other_unrealized - liquidation_equity

        if position.side == SignalType.LONG:
            liquidation_price = position.entry_price - (max_loss / position.size)
        else:
            liquidation_price = position.entry_price + (max_loss / position.size)

        return max(0, liquidation_price)

    def calculate_portfolio_liquidation_price(self) -> Optional[float]:
        """
        Calculate portfolio-level liquidation price.

        This is an estimate based on the average position.

        Returns:
            Estimated portfolio liquidation price or None
        """
        if not self._positions:
            return None

        total_maintenance = sum(p.maintenance_margin for p in self._positions.values())
        liquidation_equity = total_maintenance * (1 + self.liquidation_buffer)

        # Calculate weighted average entry and total size
        total_size = 0.0
        weighted_entry = 0.0
        net_direction = 0  # +1 for net long, -1 for net short

        for position in self._positions.values():
            size_sign = 1 if position.side == SignalType.LONG else -1
            total_size += position.size * size_sign
            weighted_entry += position.entry_price * position.size * size_sign

        if abs(total_size) < 1e-10:
            return None

        avg_entry = weighted_entry / total_size
        max_loss = self._balance - liquidation_equity

        if total_size > 0:  # Net long
            return avg_entry - (max_loss / total_size)
        else:  # Net short
            return avg_entry + (max_loss / abs(total_size))

    def get_state(self, timestamp: Optional[datetime] = None) -> PortfolioState:
        """Get current portfolio state snapshot."""
        return PortfolioState(
            timestamp=timestamp or datetime.now(),
            equity=self.equity,
            balance=self._balance,
            unrealized_pnl=self.unrealized_pnl,
            margin_used=self.margin_used,
            margin_available=self.margin_available,
            margin_utilization=self.margin_utilization,
            total_notional=self.total_notional,
            liquidation_price=self.calculate_portfolio_liquidation_price(),
            position_count=self.position_count,
            heat_percent=self.margin_utilization  # Simplified heat = margin utilization
        )

    def record_equity(self) -> None:
        """Record current equity for curve tracking."""
        current_equity = self.equity

        self._equity_curve.append(current_equity)

        # Update peak and drawdown
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
            self._drawdown_curve.append(0.0)
        else:
            drawdown = (self._peak_equity - current_equity) / self._peak_equity * 100
            self._drawdown_curve.append(drawdown)

        self._current_bar += 1

    @property
    def closed_trades(self) -> List[ClosedTrade]:
        """Get all closed trades."""
        return self._closed_trades

    @property
    def equity_curve(self) -> List[float]:
        """Get equity curve."""
        return self._equity_curve

    @property
    def drawdown_curve(self) -> List[float]:
        """Get drawdown curve."""
        return self._drawdown_curve

    @property
    def max_drawdown(self) -> float:
        """Get maximum drawdown percentage."""
        if not self._drawdown_curve:
            return 0.0
        return max(self._drawdown_curve)

    def get_summary(self) -> Dict[str, Any]:
        """Get portfolio summary statistics."""
        trades = self._closed_trades
        if not trades:
            return {
                "initial_balance": self.initial_balance,
                "final_balance": self._balance,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
            }

        winners = [t for t in trades if t.net_pnl > 0]
        losers = [t for t in trades if t.net_pnl <= 0]

        gross_profit = sum(t.net_pnl for t in winners) if winners else 0
        gross_loss = abs(sum(t.net_pnl for t in losers)) if losers else 0

        return {
            "initial_balance": self.initial_balance,
            "final_balance": self._balance,
            "total_pnl": self._balance - self.initial_balance,
            "total_pnl_pct": (self._balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": len(trades),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": len(winners) / len(trades) * 100 if trades else 0,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            "avg_win": gross_profit / len(winners) if winners else 0,
            "avg_loss": gross_loss / len(losers) if losers else 0,
            "largest_win": max((t.net_pnl for t in winners), default=0),
            "largest_loss": min((t.net_pnl for t in losers), default=0),
            "max_drawdown": self.max_drawdown,
            "total_fees": sum(t.total_fees for t in trades),
            "liquidations": sum(1 for t in trades if t.exit_reason == "liquidation"),
        }
