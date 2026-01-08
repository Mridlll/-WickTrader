"""Base backtest types and engine foundation."""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))


class SignalType(str, Enum):
    """Trading signal types."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class BacktestTrade:
    """
    Base trade information for backtesting.

    Contains all essential data about a single trade.
    """
    entry_time: datetime
    exit_time: Optional[datetime] = None
    signal_type: SignalType = SignalType.FLAT
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    size: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    exit_reason: str = ""
    commission: float = 0.0
    slippage: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0

    @property
    def duration_bars(self) -> int:
        """Get trade duration in bars (if metadata available)."""
        return self.metadata.get("bars_held", 0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert trade to dictionary."""
        return {
            "entry_time": self.entry_time.isoformat() if isinstance(self.entry_time, datetime) else str(self.entry_time),
            "exit_time": self.exit_time.isoformat() if isinstance(self.exit_time, datetime) else str(self.exit_time),
            "signal_type": self.signal_type.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "exit_reason": self.exit_reason,
            "commission": self.commission,
            "slippage": self.slippage,
            "metadata": self.metadata
        }


@dataclass
class BacktestResult:
    """
    Comprehensive backtest result container.

    Holds all metrics and data from a backtest run.
    """
    # Balance
    initial_balance: float = 0.0
    final_balance: float = 0.0

    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Win/Loss metrics
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0

    # Trade statistics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade_duration: float = 0.0

    # Extended metrics (optional)
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    expectancy: float = 0.0
    recovery_factor: float = 0.0
    cagr: float = 0.0
    volatility: float = 0.0

    # Data
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)

    # Metadata
    parameters: Dict[str, Any] = field(default_factory=dict)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "total_pnl_percent": self.total_pnl_percent,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_percent": self.max_drawdown_percent,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "recovery_factor": self.recovery_factor,
            "cagr": self.cagr,
            "volatility": self.volatility,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "avg_trade_duration": self.avg_trade_duration,
            "parameters": self.parameters,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }

    def summary(self) -> str:
        """Generate summary string."""
        return f"""
Backtest Summary
================
Initial Balance: ${self.initial_balance:,.2f}
Final Balance:   ${self.final_balance:,.2f}
Total P&L:       ${self.total_pnl:+,.2f} ({self.total_pnl_percent:+.2f}%)

Trades: {self.total_trades} ({self.winning_trades}W / {self.losing_trades}L)
Win Rate: {self.win_rate:.1f}%
Profit Factor: {self.profit_factor:.2f}

Sharpe Ratio: {self.sharpe_ratio:.2f}
Sortino Ratio: {self.sortino_ratio:.2f}
Calmar Ratio: {self.calmar_ratio:.2f}

Max Drawdown: ${self.max_drawdown:,.2f} ({self.max_drawdown_percent:.2f}%)
Expectancy: ${self.expectancy:.2f}
"""
