"""Comprehensive backtest metrics calculation module.

Provides all standard and advanced trading metrics:
- Risk-adjusted returns (Sharpe, Sortino, Calmar)
- Performance metrics (Profit Factor, Win Rate, Expectancy)
- Drawdown analysis
- Monthly/annual returns
- Statistical measures
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np
from collections import defaultdict


@dataclass
class TradeMetrics:
    """Metrics for a set of trades."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    win_rate: float = 0.0
    loss_rate: float = 0.0

    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_pnl: float = 0.0

    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade: float = 0.0

    largest_win: float = 0.0
    largest_loss: float = 0.0

    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_trade_pct: float = 0.0

    avg_bars_held: float = 0.0
    avg_bars_winning: float = 0.0
    avg_bars_losing: float = 0.0


@dataclass
class RiskMetrics:
    """Risk-adjusted performance metrics."""
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    mar_ratio: float = 0.0  # MAR = CAGR / Max DD

    profit_factor: float = 0.0
    payoff_ratio: float = 0.0  # Avg Win / Avg Loss
    expectancy: float = 0.0    # Expected $ per trade
    expectancy_pct: float = 0.0

    recovery_factor: float = 0.0
    ulcer_index: float = 0.0
    ulcer_performance_index: float = 0.0

    volatility: float = 0.0
    downside_deviation: float = 0.0

    var_95: float = 0.0  # Value at Risk 95%
    var_99: float = 0.0  # Value at Risk 99%
    cvar_95: float = 0.0 # Conditional VaR 95%


@dataclass
class DrawdownMetrics:
    """Drawdown analysis metrics."""
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration: int = 0  # Bars
    avg_drawdown: float = 0.0
    avg_drawdown_pct: float = 0.0
    avg_drawdown_duration: int = 0

    drawdown_count: int = 0
    time_in_drawdown_pct: float = 0.0

    longest_recovery: int = 0  # Bars to recover from max DD
    current_drawdown: float = 0.0
    current_drawdown_pct: float = 0.0


@dataclass
class ReturnsMetrics:
    """Returns analysis metrics."""
    total_return: float = 0.0
    total_return_pct: float = 0.0

    cagr: float = 0.0
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0

    best_trade: float = 0.0
    worst_trade: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0

    skewness: float = 0.0
    kurtosis: float = 0.0

    positive_months: int = 0
    negative_months: int = 0
    best_month: float = 0.0
    worst_month: float = 0.0

    positive_years: int = 0
    negative_years: int = 0
    best_year: float = 0.0
    worst_year: float = 0.0


@dataclass
class ComprehensiveMetrics:
    """All metrics combined."""
    trade_metrics: TradeMetrics = field(default_factory=TradeMetrics)
    risk_metrics: RiskMetrics = field(default_factory=RiskMetrics)
    drawdown_metrics: DrawdownMetrics = field(default_factory=DrawdownMetrics)
    returns_metrics: ReturnsMetrics = field(default_factory=ReturnsMetrics)

    # Summary
    initial_balance: float = 0.0
    final_balance: float = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    trading_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "summary": {
                "initial_balance": self.initial_balance,
                "final_balance": self.final_balance,
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "end_date": self.end_date.isoformat() if self.end_date else None,
                "trading_days": self.trading_days,
            }
        }

        # Add all metrics from dataclasses
        for name in ['trade_metrics', 'risk_metrics', 'drawdown_metrics', 'returns_metrics']:
            obj = getattr(self, name)
            result[name] = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}

        return result


class MetricsCalculator:
    """
    Comprehensive metrics calculator.

    Calculates all standard and advanced trading metrics from
    equity curve, trades, and portfolio data.
    """

    # Risk-free rate for Sharpe/Sortino (annualized)
    RISK_FREE_RATE = 0.04  # 4%

    # Trading days per year
    TRADING_DAYS_YEAR = 252

    def __init__(
        self,
        risk_free_rate: float = 0.04,
        trading_days_year: int = 252
    ):
        """
        Initialize metrics calculator.

        Args:
            risk_free_rate: Annual risk-free rate
            trading_days_year: Trading days per year
        """
        self.risk_free_rate = risk_free_rate
        self.trading_days_year = trading_days_year

    def calculate_all(
        self,
        equity_curve: List[float],
        trades: List[Dict[str, Any]],
        initial_balance: float,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bars_per_day: float = 6.0  # e.g., 4H candles = 6 per day
    ) -> ComprehensiveMetrics:
        """
        Calculate all metrics.

        Args:
            equity_curve: List of equity values
            trades: List of trade dictionaries with pnl, pnl_percent, bars_held
            initial_balance: Starting balance
            start_date: Start date
            end_date: End date
            bars_per_day: Bars per trading day (for duration calculations)

        Returns:
            ComprehensiveMetrics with all calculated values
        """
        # Convert to numpy for calculations
        equity = np.array(equity_curve, dtype=float)

        # Calculate individual metric groups
        trade_metrics = self.calculate_trade_metrics(trades)
        drawdown_metrics = self.calculate_drawdown_metrics(equity, initial_balance)
        returns_metrics = self.calculate_returns_metrics(
            equity, trades, initial_balance, bars_per_day
        )
        risk_metrics = self.calculate_risk_metrics(
            equity, trades, initial_balance, drawdown_metrics, bars_per_day
        )

        # Calculate trading days
        trading_days = int(len(equity_curve) / bars_per_day)

        return ComprehensiveMetrics(
            trade_metrics=trade_metrics,
            risk_metrics=risk_metrics,
            drawdown_metrics=drawdown_metrics,
            returns_metrics=returns_metrics,
            initial_balance=initial_balance,
            final_balance=equity[-1] if len(equity) > 0 else initial_balance,
            start_date=start_date,
            end_date=end_date,
            trading_days=trading_days
        )

    def calculate_trade_metrics(self, trades: List[Dict[str, Any]]) -> TradeMetrics:
        """Calculate trade-based metrics."""
        if not trades:
            return TradeMetrics()

        # Separate winners and losers
        winners = [t for t in trades if t.get('pnl', 0) > 0]
        losers = [t for t in trades if t.get('pnl', 0) < 0]
        breakeven = [t for t in trades if t.get('pnl', 0) == 0]

        total = len(trades)
        n_winners = len(winners)
        n_losers = len(losers)
        n_breakeven = len(breakeven)

        # PnL calculations
        gross_profit = sum(t.get('pnl', 0) for t in winners)
        gross_loss = abs(sum(t.get('pnl', 0) for t in losers))
        total_pnl = gross_profit - gross_loss

        # Averages
        avg_win = gross_profit / n_winners if n_winners > 0 else 0
        avg_loss = gross_loss / n_losers if n_losers > 0 else 0
        avg_trade = total_pnl / total if total > 0 else 0

        # Extremes
        all_pnls = [t.get('pnl', 0) for t in trades]
        largest_win = max(all_pnls) if all_pnls else 0
        largest_loss = min(all_pnls) if all_pnls else 0

        # Consecutive streaks
        max_consec_wins, max_consec_losses = self._calculate_streaks(trades)

        # Percentage returns
        win_pcts = [t.get('pnl_percent', 0) for t in winners]
        loss_pcts = [t.get('pnl_percent', 0) for t in losers]
        all_pcts = [t.get('pnl_percent', 0) for t in trades]

        avg_win_pct = np.mean(win_pcts) if win_pcts else 0
        avg_loss_pct = np.mean(loss_pcts) if loss_pcts else 0
        avg_trade_pct = np.mean(all_pcts) if all_pcts else 0

        # Bars held
        all_bars = [t.get('bars_held', 0) for t in trades]
        win_bars = [t.get('bars_held', 0) for t in winners]
        loss_bars = [t.get('bars_held', 0) for t in losers]

        return TradeMetrics(
            total_trades=total,
            winning_trades=n_winners,
            losing_trades=n_losers,
            breakeven_trades=n_breakeven,
            win_rate=n_winners / total * 100 if total > 0 else 0,
            loss_rate=n_losers / total * 100 if total > 0 else 0,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            total_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            avg_trade_pct=avg_trade_pct,
            avg_bars_held=np.mean(all_bars) if all_bars else 0,
            avg_bars_winning=np.mean(win_bars) if win_bars else 0,
            avg_bars_losing=np.mean(loss_bars) if loss_bars else 0
        )

    def _calculate_streaks(self, trades: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Calculate maximum consecutive winning and losing streaks."""
        if not trades:
            return 0, 0

        max_wins = max_losses = 0
        current_wins = current_losses = 0

        for trade in trades:
            pnl = trade.get('pnl', 0)
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0

        return max_wins, max_losses

    def calculate_drawdown_metrics(
        self,
        equity: np.ndarray,
        initial_balance: float
    ) -> DrawdownMetrics:
        """Calculate drawdown metrics from equity curve."""
        if len(equity) == 0:
            return DrawdownMetrics()

        # Calculate running maximum and drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = peak - equity
        drawdown_pct = drawdown / peak * 100

        # Maximum drawdown
        max_dd_idx = np.argmax(drawdown)
        max_dd = drawdown[max_dd_idx]
        max_dd_pct = drawdown_pct[max_dd_idx]

        # Find when max drawdown started (peak before max_dd_idx)
        peak_before_max_dd = np.argmax(peak[:max_dd_idx+1] == peak[max_dd_idx]) if max_dd_idx > 0 else 0
        max_dd_duration = max_dd_idx - peak_before_max_dd

        # Find recovery time (if recovered)
        recovery_idx = None
        for i in range(max_dd_idx, len(equity)):
            if equity[i] >= peak[max_dd_idx]:
                recovery_idx = i
                break
        longest_recovery = (recovery_idx - max_dd_idx) if recovery_idx else len(equity) - max_dd_idx

        # Identify individual drawdown periods
        in_drawdown = drawdown > 0
        dd_starts = []
        dd_ends = []

        for i in range(1, len(in_drawdown)):
            if in_drawdown[i] and not in_drawdown[i-1]:
                dd_starts.append(i)
            elif not in_drawdown[i] and in_drawdown[i-1]:
                dd_ends.append(i)

        if in_drawdown[-1] and len(dd_starts) > len(dd_ends):
            dd_ends.append(len(equity) - 1)

        dd_count = len(dd_starts)

        # Average drawdown
        if dd_count > 0:
            dd_values = []
            dd_durations = []
            for start, end in zip(dd_starts, dd_ends):
                dd_max = np.max(drawdown[start:end+1])
                dd_values.append(dd_max)
                dd_durations.append(end - start)

            avg_dd = np.mean(dd_values) if dd_values else 0
            avg_dd_pct = avg_dd / initial_balance * 100 if initial_balance > 0 else 0
            avg_dd_duration = int(np.mean(dd_durations)) if dd_durations else 0
        else:
            avg_dd = avg_dd_pct = avg_dd_duration = 0

        # Time in drawdown
        time_in_dd = np.sum(in_drawdown) / len(equity) * 100 if len(equity) > 0 else 0

        # Current drawdown
        current_dd = drawdown[-1] if len(drawdown) > 0 else 0
        current_dd_pct = drawdown_pct[-1] if len(drawdown_pct) > 0 else 0

        return DrawdownMetrics(
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_duration=max_dd_duration,
            avg_drawdown=avg_dd,
            avg_drawdown_pct=avg_dd_pct,
            avg_drawdown_duration=avg_dd_duration,
            drawdown_count=dd_count,
            time_in_drawdown_pct=time_in_dd,
            longest_recovery=longest_recovery,
            current_drawdown=current_dd,
            current_drawdown_pct=current_dd_pct
        )

    def calculate_returns_metrics(
        self,
        equity: np.ndarray,
        trades: List[Dict[str, Any]],
        initial_balance: float,
        bars_per_day: float
    ) -> ReturnsMetrics:
        """Calculate returns-based metrics."""
        if len(equity) == 0:
            return ReturnsMetrics()

        final_balance = equity[-1]
        total_return = final_balance - initial_balance
        total_return_pct = total_return / initial_balance * 100 if initial_balance > 0 else 0

        # Period returns
        returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])

        # Annualized metrics
        trading_days = len(equity) / bars_per_day
        years = trading_days / self.trading_days_year

        if years > 0:
            cagr = ((final_balance / initial_balance) ** (1 / years) - 1) * 100
            annualized_return = cagr
        else:
            cagr = annualized_return = 0

        if len(returns) > 1:
            daily_returns = self._aggregate_returns_to_daily(returns, bars_per_day)
            annualized_volatility = np.std(daily_returns) * np.sqrt(self.trading_days_year) * 100
        else:
            annualized_volatility = 0

        # Trade-based extremes
        if trades:
            pnls = [t.get('pnl', 0) for t in trades]
            pnl_pcts = [t.get('pnl_percent', 0) for t in trades]

            best_trade = max(pnls)
            worst_trade = min(pnls)
            best_trade_pct = max(pnl_pcts)
            worst_trade_pct = min(pnl_pcts)
        else:
            best_trade = worst_trade = best_trade_pct = worst_trade_pct = 0

        # Statistical measures
        if len(returns) > 2:
            skewness = float(pd.Series(returns).skew())
            kurtosis = float(pd.Series(returns).kurtosis())
        else:
            skewness = kurtosis = 0

        # Monthly/yearly returns (placeholder - would need timestamps)
        # These would require proper date indexing
        positive_months = negative_months = 0
        best_month = worst_month = 0
        positive_years = negative_years = 0
        best_year = worst_year = 0

        return ReturnsMetrics(
            total_return=total_return,
            total_return_pct=total_return_pct,
            cagr=cagr,
            annualized_return=annualized_return,
            annualized_volatility=annualized_volatility,
            best_trade=best_trade,
            worst_trade=worst_trade,
            best_trade_pct=best_trade_pct,
            worst_trade_pct=worst_trade_pct,
            skewness=skewness,
            kurtosis=kurtosis,
            positive_months=positive_months,
            negative_months=negative_months,
            best_month=best_month,
            worst_month=worst_month,
            positive_years=positive_years,
            negative_years=negative_years,
            best_year=best_year,
            worst_year=worst_year
        )

    def _aggregate_returns_to_daily(
        self,
        bar_returns: np.ndarray,
        bars_per_day: float
    ) -> np.ndarray:
        """Aggregate bar returns to daily returns."""
        bars_per_day = int(bars_per_day)
        if bars_per_day <= 0:
            return bar_returns

        n_days = len(bar_returns) // bars_per_day
        if n_days == 0:
            return bar_returns

        daily_returns = []
        for i in range(n_days):
            start = i * bars_per_day
            end = start + bars_per_day
            # Compound the returns
            day_return = np.prod(1 + bar_returns[start:end]) - 1
            daily_returns.append(day_return)

        return np.array(daily_returns)

    def calculate_risk_metrics(
        self,
        equity: np.ndarray,
        trades: List[Dict[str, Any]],
        initial_balance: float,
        drawdown_metrics: DrawdownMetrics,
        bars_per_day: float
    ) -> RiskMetrics:
        """Calculate risk-adjusted metrics."""
        if len(equity) < 2:
            return RiskMetrics()

        # Period returns
        returns = np.diff(equity) / equity[:-1]

        # Aggregate to daily for better Sharpe calculation
        daily_returns = self._aggregate_returns_to_daily(returns, bars_per_day)

        if len(daily_returns) < 2:
            return RiskMetrics()

        # Daily risk-free rate
        daily_rf = self.risk_free_rate / self.trading_days_year

        # Excess returns
        excess_returns = daily_returns - daily_rf

        # Sharpe Ratio
        avg_excess = np.mean(excess_returns)
        std_returns = np.std(daily_returns)
        sharpe = (avg_excess / std_returns * np.sqrt(self.trading_days_year)) if std_returns > 0 else 0

        # Sortino Ratio (downside deviation)
        negative_returns = daily_returns[daily_returns < 0]
        downside_std = np.std(negative_returns) if len(negative_returns) > 0 else 0
        sortino = (avg_excess / downside_std * np.sqrt(self.trading_days_year)) if downside_std > 0 else 0

        # Calmar Ratio
        total_return_pct = (equity[-1] - initial_balance) / initial_balance * 100
        trading_days = len(equity) / bars_per_day
        years = trading_days / self.trading_days_year
        cagr = ((equity[-1] / initial_balance) ** (1 / years) - 1) * 100 if years > 0 else 0

        max_dd_pct = drawdown_metrics.max_drawdown_pct
        calmar = cagr / max_dd_pct if max_dd_pct > 0 else 0
        mar = calmar  # MAR is same as Calmar when using CAGR

        # Trade-based metrics
        if trades:
            winners = [t for t in trades if t.get('pnl', 0) > 0]
            losers = [t for t in trades if t.get('pnl', 0) < 0]

            gross_profit = sum(t.get('pnl', 0) for t in winners)
            gross_loss = abs(sum(t.get('pnl', 0) for t in losers))

            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

            avg_win = gross_profit / len(winners) if winners else 0
            avg_loss = gross_loss / len(losers) if losers else 0
            payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

            win_rate = len(winners) / len(trades) if trades else 0
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
            expectancy_pct = expectancy / initial_balance * 100 if initial_balance > 0 else 0
        else:
            profit_factor = payoff_ratio = expectancy = expectancy_pct = 0

        # Recovery Factor
        total_pnl = equity[-1] - initial_balance
        max_dd = drawdown_metrics.max_drawdown
        recovery_factor = total_pnl / max_dd if max_dd > 0 else 0

        # Ulcer Index
        peak = np.maximum.accumulate(equity)
        drawdown_pct = (peak - equity) / peak * 100
        ulcer_index = np.sqrt(np.mean(drawdown_pct ** 2))

        # Ulcer Performance Index
        avg_return = np.mean(daily_returns) * self.trading_days_year * 100
        upi = (avg_return - self.risk_free_rate * 100) / ulcer_index if ulcer_index > 0 else 0

        # Volatility
        volatility = std_returns * np.sqrt(self.trading_days_year) * 100
        downside_deviation = downside_std * np.sqrt(self.trading_days_year) * 100

        # Value at Risk
        var_95 = np.percentile(daily_returns, 5) * initial_balance
        var_99 = np.percentile(daily_returns, 1) * initial_balance

        # Conditional VaR (Expected Shortfall)
        returns_below_var = daily_returns[daily_returns <= np.percentile(daily_returns, 5)]
        cvar_95 = np.mean(returns_below_var) * initial_balance if len(returns_below_var) > 0 else 0

        return RiskMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            mar_ratio=mar,
            profit_factor=profit_factor,
            payoff_ratio=payoff_ratio,
            expectancy=expectancy,
            expectancy_pct=expectancy_pct,
            recovery_factor=recovery_factor,
            ulcer_index=ulcer_index,
            ulcer_performance_index=upi,
            volatility=volatility,
            downside_deviation=downside_deviation,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95
        )

    def calculate_monthly_returns(
        self,
        equity_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate monthly returns from equity DataFrame.

        Args:
            equity_df: DataFrame with datetime index and 'equity' column

        Returns:
            DataFrame with monthly returns
        """
        if equity_df.empty:
            return pd.DataFrame()

        # Resample to monthly
        monthly = equity_df['equity'].resample('M').last()
        monthly_returns = monthly.pct_change() * 100

        # Create pivot table
        monthly_returns.index = pd.MultiIndex.from_arrays([
            monthly_returns.index.year,
            monthly_returns.index.month
        ])

        return monthly_returns

    def calculate_annual_returns(
        self,
        equity_df: pd.DataFrame
    ) -> pd.Series:
        """
        Calculate annual returns from equity DataFrame.

        Args:
            equity_df: DataFrame with datetime index and 'equity' column

        Returns:
            Series with annual returns
        """
        if equity_df.empty:
            return pd.Series()

        # Resample to yearly
        yearly = equity_df['equity'].resample('Y').last()
        yearly_returns = yearly.pct_change() * 100

        return yearly_returns


def calculate_metrics(
    equity_curve: List[float],
    trades: List[Dict[str, Any]],
    initial_balance: float,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bars_per_day: float = 6.0
) -> ComprehensiveMetrics:
    """
    Convenience function to calculate all metrics.

    Args:
        equity_curve: List of equity values
        trades: List of trade dictionaries
        initial_balance: Starting balance
        start_date: Start date
        end_date: End date
        bars_per_day: Bars per trading day

    Returns:
        ComprehensiveMetrics with all calculated values
    """
    calculator = MetricsCalculator()
    return calculator.calculate_all(
        equity_curve=equity_curve,
        trades=trades,
        initial_balance=initial_balance,
        start_date=start_date,
        end_date=end_date,
        bars_per_day=bars_per_day
    )
