"""Enhanced report generator for backtest results.

Generates comprehensive markdown reports with:
- Executive summary
- Performance metrics tables
- Strategy variant comparison
- Equity curve data
- Drawdown analysis
- Monthly returns
- Trade log
- ASCII architecture diagrams
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np

from backtest.engine import BacktestResult
from backtest.metrics import ComprehensiveMetrics, MetricsCalculator


class ReportGenerator:
    """
    Comprehensive backtest report generator.

    Outputs markdown reports with all metrics, charts (ASCII),
    and detailed trade analysis.
    """

    def __init__(
        self,
        output_dir: str = "reports",
        include_trade_log: bool = True,
        max_trades_in_log: int = 100,
        include_equity_data: bool = True,
        include_ascii_charts: bool = True
    ):
        """
        Initialize report generator.

        Args:
            output_dir: Directory for output files
            include_trade_log: Include full trade log
            max_trades_in_log: Maximum trades to include in log
            include_equity_data: Include equity curve data
            include_ascii_charts: Include ASCII charts
        """
        self.output_dir = Path(output_dir)
        self.include_trade_log = include_trade_log
        self.max_trades_in_log = max_trades_in_log
        self.include_equity_data = include_equity_data
        self.include_ascii_charts = include_ascii_charts

    def generate_report(
        self,
        result: BacktestResult,
        variant_results: Optional[pd.DataFrame] = None,
        analysis: Optional[Dict[str, Any]] = None,
        title: str = "Wick Strategy Backtest Report"
    ) -> str:
        """
        Generate full markdown report.

        Args:
            result: Main backtest result
            variant_results: Optional DataFrame of variant search results
            analysis: Optional variant analysis dictionary
            title: Report title

        Returns:
            Markdown report string
        """
        sections = []

        # Header
        sections.append(self._generate_header(title, result))

        # Executive Summary
        sections.append(self._generate_executive_summary(result))

        # Performance Metrics
        sections.append(self._generate_metrics_table(result))

        # Strategy Parameters
        sections.append(self._generate_parameters_section(result))

        # Variant Comparison (if provided)
        if variant_results is not None:
            sections.append(self._generate_variant_comparison(variant_results, analysis))

        # Drawdown Analysis
        sections.append(self._generate_drawdown_analysis(result))

        # Monthly Returns (if dates available)
        if result.start_date and result.end_date:
            sections.append(self._generate_monthly_returns(result))

        # Trade Log
        if self.include_trade_log and result.trades:
            sections.append(self._generate_trade_log(result))

        # Equity Curve Data
        if self.include_equity_data and result.equity_curve:
            sections.append(self._generate_equity_data(result))

        # Architecture Diagram
        if self.include_ascii_charts:
            sections.append(self._generate_architecture_diagram())

        # Footer
        sections.append(self._generate_footer())

        return "\n\n".join(sections)

    def _generate_header(self, title: str, result: BacktestResult) -> str:
        """Generate report header."""
        lines = [
            f"# {title}",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        if result.start_date and result.end_date:
            lines.extend([
                f"**Backtest Period:** {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}",
                "",
            ])

        return "\n".join(lines)

    def _generate_executive_summary(self, result: BacktestResult) -> str:
        """Generate executive summary section."""
        # Determine performance rating
        if result.total_pnl_percent > 100:
            rating = "Excellent"
        elif result.total_pnl_percent > 50:
            rating = "Very Good"
        elif result.total_pnl_percent > 20:
            rating = "Good"
        elif result.total_pnl_percent > 0:
            rating = "Moderate"
        else:
            rating = "Poor"

        # Risk assessment
        if result.max_drawdown_percent < 15:
            risk_level = "Low"
        elif result.max_drawdown_percent < 30:
            risk_level = "Moderate"
        elif result.max_drawdown_percent < 50:
            risk_level = "High"
        else:
            risk_level = "Very High"

        lines = [
            "## Executive Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| **Initial Balance** | ${result.initial_balance:,.2f} |",
            f"| **Final Balance** | ${result.final_balance:,.2f} |",
            f"| **Net P&L** | ${result.total_pnl:+,.2f} ({result.total_pnl_percent:+.2f}%) |",
            f"| **Total Trades** | {result.total_trades} |",
            f"| **Win Rate** | {result.win_rate:.1f}% |",
            f"| **Profit Factor** | {result.profit_factor:.2f} |",
            f"| **Sharpe Ratio** | {result.sharpe_ratio:.2f} |",
            f"| **Max Drawdown** | {result.max_drawdown_percent:.2f}% |",
            f"| **Performance Rating** | **{rating}** |",
            f"| **Risk Level** | {risk_level} |",
            "",
        ]

        # Key insights
        lines.extend([
            "### Key Insights",
            "",
        ])

        if result.total_pnl > 0:
            lines.append(f"- Strategy generated ${result.total_pnl:,.2f} profit ({result.total_pnl_percent:.1f}% return)")
        else:
            lines.append(f"- Strategy had ${abs(result.total_pnl):,.2f} loss ({result.total_pnl_percent:.1f}% return)")

        lines.append(f"- Won {result.winning_trades} of {result.total_trades} trades ({result.win_rate:.1f}% win rate)")

        if result.profit_factor > 1:
            lines.append(f"- Profit factor of {result.profit_factor:.2f} indicates positive edge")
        else:
            lines.append(f"- Profit factor of {result.profit_factor:.2f} indicates negative edge")

        lines.append(f"- Maximum drawdown was {result.max_drawdown_percent:.1f}% (${result.max_drawdown:,.2f})")

        if result.sharpe_ratio > 1:
            lines.append(f"- Sharpe ratio of {result.sharpe_ratio:.2f} shows good risk-adjusted returns")
        elif result.sharpe_ratio > 0:
            lines.append(f"- Sharpe ratio of {result.sharpe_ratio:.2f} shows moderate risk-adjusted returns")
        else:
            lines.append(f"- Negative Sharpe ratio indicates poor risk-adjusted returns")

        return "\n".join(lines)

    def _generate_metrics_table(self, result: BacktestResult) -> str:
        """Generate comprehensive metrics table."""
        lines = [
            "## Performance Metrics",
            "",
            "### Returns & Profitability",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Return | ${result.total_pnl:+,.2f} |",
            f"| Total Return % | {result.total_pnl_percent:+.2f}% |",
            f"| CAGR | {result.cagr:.2f}% |",
            f"| Profit Factor | {result.profit_factor:.2f} |",
            f"| Expectancy | ${result.expectancy:.2f} |",
            "",
            "### Risk Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Sharpe Ratio | {result.sharpe_ratio:.2f} |",
            f"| Sortino Ratio | {result.sortino_ratio:.2f} |",
            f"| Calmar Ratio | {result.calmar_ratio:.2f} |",
            f"| Max Drawdown | {result.max_drawdown_percent:.2f}% (${result.max_drawdown:,.2f}) |",
            f"| Recovery Factor | {result.recovery_factor:.2f} |",
            f"| Volatility | {result.volatility:.2f}% |",
            "",
            "### Trade Statistics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Trades | {result.total_trades} |",
            f"| Winning Trades | {result.winning_trades} ({result.win_rate:.1f}%) |",
            f"| Losing Trades | {result.losing_trades} ({100-result.win_rate:.1f}%) |",
            f"| Average Win | ${result.avg_win:,.2f} |",
            f"| Average Loss | ${result.avg_loss:,.2f} |",
            f"| Largest Win | ${result.largest_win:,.2f} |",
            f"| Largest Loss | ${result.largest_loss:,.2f} |",
            f"| Avg Trade Duration | {result.avg_trade_duration:.1f} bars |",
        ]

        return "\n".join(lines)

    def _generate_parameters_section(self, result: BacktestResult) -> str:
        """Generate strategy parameters section."""
        lines = [
            "## Strategy Parameters",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
        ]

        if result.parameters:
            for key, value in result.parameters.items():
                if value is not None:
                    lines.append(f"| {key.replace('_', ' ').title()} | {value} |")

        return "\n".join(lines)

    def _generate_variant_comparison(
        self,
        results_df: pd.DataFrame,
        analysis: Optional[Dict[str, Any]]
    ) -> str:
        """Generate variant comparison section."""
        lines = [
            "## Strategy Variant Comparison",
            "",
        ]

        # Top 10 variants
        top_results = results_df.nlargest(10, 'total_pnl')

        lines.extend([
            "### Top 10 Variants by P&L",
            "",
            "| Wick % | Direction | Exit Type | Risk Profile | Trades | Win Rate | P&L | Sharpe | Max DD |",
            "|--------|-----------|-----------|--------------|--------|----------|-----|--------|--------|",
        ])

        for _, row in top_results.iterrows():
            lines.append(
                f"| {row['wick_threshold']:.0f}% | {row['direction']} | {row['exit_type']} | "
                f"{row['risk_profile']} | {row['total_trades']} | {row['win_rate']:.1f}% | "
                f"${row['total_pnl']:,.0f} | {row['sharpe_ratio']:.2f} | {row['max_drawdown_pct']:.1f}% |"
            )

        # Analysis summary
        if analysis:
            lines.extend([
                "",
                "### Summary by Category",
                "",
            ])

            if 'by_risk_profile' in analysis:
                lines.extend([
                    "#### By Risk Profile",
                    "",
                    "| Profile | Variants | Profitable | Avg P&L | Avg Sharpe |",
                    "|---------|----------|------------|---------|------------|",
                ])

                for profile, stats in analysis['by_risk_profile'].items():
                    lines.append(
                        f"| {profile.title()} | {stats['count']} | {stats['profitable']} | "
                        f"${stats['avg_pnl']:,.0f} | {stats['avg_sharpe']:.2f} |"
                    )

            if 'by_exit_type' in analysis:
                lines.extend([
                    "",
                    "#### By Exit Type",
                    "",
                    "| Exit Type | Variants | Profitable | Avg P&L | Avg Win Rate |",
                    "|-----------|----------|------------|---------|--------------|",
                ])

                for exit_type, stats in analysis['by_exit_type'].items():
                    lines.append(
                        f"| {exit_type} | {stats['count']} | {stats['profitable']} | "
                        f"${stats['avg_pnl']:,.0f} | {stats['avg_win_rate']:.1f}% |"
                    )

        return "\n".join(lines)

    def _generate_drawdown_analysis(self, result: BacktestResult) -> str:
        """Generate drawdown analysis section."""
        lines = [
            "## Drawdown Analysis",
            "",
            f"**Maximum Drawdown:** {result.max_drawdown_percent:.2f}% (${result.max_drawdown:,.2f})",
            "",
        ]

        # ASCII drawdown visualization
        if self.include_ascii_charts and result.drawdown_curve:
            lines.extend([
                "### Drawdown Chart",
                "",
                "```",
            ])

            chart = self._create_ascii_chart(
                result.drawdown_curve,
                title="Drawdown %",
                height=10,
                invert=True
            )
            lines.append(chart)

            lines.extend([
                "```",
                "",
            ])

        return "\n".join(lines)

    def _generate_monthly_returns(self, result: BacktestResult) -> str:
        """Generate monthly returns section."""
        lines = [
            "## Monthly Returns",
            "",
            "*Note: Monthly returns calculated from equity curve data.*",
            "",
        ]

        # This would require proper timestamp tracking
        # Placeholder for now
        lines.append("Monthly returns table would be generated here with proper date tracking.")

        return "\n".join(lines)

    def _generate_trade_log(self, result: BacktestResult) -> str:
        """Generate trade log section."""
        trades = result.trades[:self.max_trades_in_log]

        lines = [
            "## Trade Log",
            "",
            f"*Showing {len(trades)} of {len(result.trades)} trades*",
            "",
            "| # | Entry Time | Side | Entry | Exit | P&L | P&L % | Exit Reason | Bars |",
            "|---|------------|------|-------|------|-----|-------|-------------|------|",
        ]

        for i, trade in enumerate(trades, 1):
            entry_time = trade.entry_time.strftime('%Y-%m-%d %H:%M') if hasattr(trade.entry_time, 'strftime') else str(trade.entry_time)[:16]
            side = trade.signal_type.value if hasattr(trade.signal_type, 'value') else str(trade.signal_type)

            lines.append(
                f"| {i} | {entry_time} | {side} | "
                f"${trade.entry_price:,.2f} | ${trade.exit_price:,.2f} | "
                f"${trade.pnl:+,.2f} | {trade.pnl_percent:+.2f}% | "
                f"{trade.exit_reason} | {getattr(trade, 'bars_held', '-')} |"
            )

        return "\n".join(lines)

    def _generate_equity_data(self, result: BacktestResult) -> str:
        """Generate equity curve data section."""
        lines = [
            "## Equity Curve",
            "",
        ]

        # ASCII equity chart
        if self.include_ascii_charts:
            lines.extend([
                "```",
            ])

            chart = self._create_ascii_chart(
                result.equity_curve,
                title="Equity ($)",
                height=15
            )
            lines.append(chart)

            lines.extend([
                "```",
                "",
            ])

        # Summary statistics
        if result.equity_curve:
            equity = np.array(result.equity_curve)
            lines.extend([
                "### Equity Statistics",
                "",
                f"- Starting: ${equity[0]:,.2f}",
                f"- Ending: ${equity[-1]:,.2f}",
                f"- Peak: ${np.max(equity):,.2f}",
                f"- Trough: ${np.min(equity):,.2f}",
                f"- Std Dev: ${np.std(equity):,.2f}",
            ])

        return "\n".join(lines)

    def _generate_architecture_diagram(self) -> str:
        """Generate system architecture diagram."""
        diagram = """
## System Architecture

```
+--------------------------------------------------+
|                  BACKTEST ENGINE                  |
+--------------------------------------------------+
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
+---------------+ +---------------+ +---------------+
|    SIGNALS    | |     RISK      | |   PORTFOLIO   |
|   (Wick       | |   (Heat       | |   (Cross      |
|   Detection)  | |   Manager)    | |   Margin)     |
+---------------+ +---------------+ +---------------+
        |               |               |
        v               v               v
+--------------------------------------------------+
|                   DATA FLOW                       |
+--------------------------------------------------+
|                                                  |
|  [OHLCV Data] --> [Signal Detection]             |
|       |                |                         |
|       v                v                         |
|  [Wick Analysis] --> [Trade Signal]              |
|                        |                         |
|                        v                         |
|  [Heat Check] <-- [Position Sizing]              |
|       |                |                         |
|       v                v                         |
|  [Zone Check] --> [Scaled Position]              |
|                        |                         |
|                        v                         |
|  [Portfolio] <-- [Execute Trade]                 |
|       |                |                         |
|       v                v                         |
|  [PnL Update] --> [Exit Check]                   |
|       |                |                         |
|       v                v                         |
|  [Metrics] <-- [Trade Close]                     |
|                                                  |
+--------------------------------------------------+

HEAT ZONES:
+--------+--------+--------+--------+
| GREEN  | YELLOW |  RED   |CRITICAL|
| 0-30%  | 30-60% | 60-80% |  >80%  |
| 100%   |  50%   |  25%   |   0%   |
| sizing | sizing | sizing | sizing |
+--------+--------+--------+--------+

RISK PROFILES:
+-------------+---------+---------+----------+
|   PROFILE   |  RISK   | LEVERAGE| MAX HEAT |
+-------------+---------+---------+----------+
| Conservative|   3%    |   3x    |   30%    |
| Moderate    |   5%    |   5x    |   50%    |
| Aggressive  |  10%    |   7x    |   70%    |
| Degen       |  15%    |  10x    |   90%    |
+-------------+---------+---------+----------+
```
"""
        return diagram

    def _generate_footer(self) -> str:
        """Generate report footer."""
        lines = [
            "---",
            "",
            "*Report generated by WickTrader Enhanced Backtest System*",
            "",
            f"*Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]

        return "\n".join(lines)

    def _create_ascii_chart(
        self,
        data: List[float],
        title: str = "",
        height: int = 10,
        width: int = 60,
        invert: bool = False
    ) -> str:
        """
        Create ASCII chart from data.

        Args:
            data: List of values to chart
            title: Chart title
            height: Chart height in rows
            width: Chart width in columns
            invert: Invert Y axis (for drawdown)

        Returns:
            ASCII chart string
        """
        if not data:
            return "No data"

        # Sample data to fit width
        if len(data) > width:
            step = len(data) // width
            sampled = [data[i] for i in range(0, len(data), step)][:width]
        else:
            sampled = data

        # Normalize to height
        min_val = min(sampled)
        max_val = max(sampled)
        range_val = max_val - min_val if max_val != min_val else 1

        # Build chart
        lines = []

        if title:
            lines.append(f"  {title}")
            lines.append("")

        # Y-axis labels
        y_labels = []
        for i in range(height + 1):
            if invert:
                val = min_val + (range_val * i / height)
            else:
                val = max_val - (range_val * i / height)
            y_labels.append(f"{val:>10.2f}")

        # Create rows
        for row in range(height):
            threshold = 1 - (row / height) if not invert else (row / height)

            line_chars = []
            for val in sampled:
                normalized = (val - min_val) / range_val
                if invert:
                    normalized = 1 - normalized

                if normalized >= threshold:
                    line_chars.append('#')
                else:
                    line_chars.append(' ')

            lines.append(f"{y_labels[row]} |{''.join(line_chars)}|")

        # Bottom axis
        lines.append(f"{y_labels[-1]} +{'-' * len(sampled)}+")

        return "\n".join(lines)

    def save_report(
        self,
        report: str,
        filename: str = "backtest_report.md"
    ) -> Path:
        """
        Save report to file.

        Args:
            report: Report markdown string
            filename: Output filename

        Returns:
            Path to saved file
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)

        return output_path


def generate_backtest_report(
    result: BacktestResult,
    variant_results: Optional[pd.DataFrame] = None,
    analysis: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    title: str = "Wick Strategy Backtest Report"
) -> str:
    """
    Convenience function to generate and optionally save report.

    Args:
        result: Backtest result
        variant_results: Optional variant search results
        analysis: Optional analysis dictionary
        output_path: Optional path to save report
        title: Report title

    Returns:
        Report markdown string
    """
    generator = ReportGenerator()
    report = generator.generate_report(
        result=result,
        variant_results=variant_results,
        analysis=analysis,
        title=title
    )

    if output_path:
        output_dir = Path(output_path).parent
        filename = Path(output_path).name
        generator.output_dir = output_dir
        generator.save_report(report, filename)

    return report


if __name__ == "__main__":
    # Example usage
    print("Report generator module loaded. Use generate_backtest_report() to create reports.")
