#!/usr/bin/env python3
"""
REAL Grid Search Backtest - Verified Results Only

This script runs ACTUAL backtests on real SOL/USDT 4H price data.
No simulated or fake results. Every number is calculated from real trades.

Usage:
    python -m backtest.run_real_grid_search
    python -m backtest.run_real_grid_search --quick  # Reduced parameter space
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
import time
import argparse

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np

from backtest.advanced_engine import AdvancedBacktestEngine, ExitType, RISK_PROFILES
from indicators.wick import WickCalculator


# =============================================================================
# GRID SEARCH PARAMETERS - Per Client Spec
# =============================================================================

# Client specified 1.5% threshold, 10-20% targets
WICK_THRESHOLDS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0]

DIRECTIONS = ["long", "short", "both"]

# Exit configurations
EXIT_CONFIGS = [
    {"type": ExitType.FIXED_PCT, "fixed_tp_pct": 10.0, "name": "fixed_10"},
    {"type": ExitType.FIXED_PCT, "fixed_tp_pct": 12.0, "name": "fixed_12"},
    {"type": ExitType.FIXED_PCT, "fixed_tp_pct": 15.0, "name": "fixed_15"},
    {"type": ExitType.FIXED_PCT, "fixed_tp_pct": 20.0, "name": "fixed_20"},
    {"type": ExitType.TIME_BASED, "time_exit_bars": 20, "name": "time_20"},
    {"type": ExitType.TIME_BASED, "time_exit_bars": 30, "name": "time_30"},
    {"type": ExitType.TIME_BASED, "time_exit_bars": 40, "name": "time_40"},
    {"type": ExitType.RR_RATIO, "rr_ratio": 2.0, "name": "rr_2"},
    {"type": ExitType.RR_RATIO, "rr_ratio": 3.0, "name": "rr_3"},
]

RISK_PROFILE_NAMES = ["conservative", "moderate", "aggressive", "degen"]


def load_data() -> pd.DataFrame:
    """Load historical SOL 4H data."""
    data_dir = project_root / "data" / "sol_4h"

    # Try to find cached data
    parquet_files = list(data_dir.glob("*.parquet"))
    csv_files = list(data_dir.glob("*.csv"))

    if parquet_files:
        df = pd.read_parquet(parquet_files[0])
    elif csv_files:
        df = pd.read_csv(csv_files[0], parse_dates=['timestamp'])
        if 'timestamp' in df.columns:
            df.set_index('timestamp', inplace=True)
    else:
        # Fetch from Binance
        print("Fetching data from Binance...")
        from exchanges.binance import BinanceExchange

        exchange = BinanceExchange(testnet=True)
        df = exchange.get_historical_klines(
            symbol="SOLUSDT",
            interval="4h",
            limit=2000
        )

        # Save for future use
        data_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(data_dir / "sol_4h_data.parquet")

    # Ensure proper column names
    if 'open' not in df.columns:
        df.columns = ['open', 'high', 'low', 'close', 'volume']

    return df


def count_signals_by_threshold(df: pd.DataFrame) -> Dict[float, Dict[str, int]]:
    """Count actual signals at each threshold."""
    results = {}

    for thresh in WICK_THRESHOLDS:
        calc = WickCalculator(threshold=thresh)
        long_count = 0
        short_count = 0

        for i in range(len(df)):
            row = df.iloc[i]
            wick_data = calc.calculate_single(
                row['open'], row['high'], row['low'], row['close']
            )
            if wick_data.lower_wick_pct >= thresh:
                long_count += 1
            if wick_data.upper_wick_pct >= thresh:
                short_count += 1

        results[thresh] = {
            "long": long_count,
            "short": short_count,
            "total": long_count + short_count
        }

    return results


def run_single_backtest(
    df: pd.DataFrame,
    wick_threshold: float,
    direction: str,
    exit_config: Dict,
    risk_profile: str
) -> Dict[str, Any]:
    """Run a single backtest configuration."""

    # Build engine params
    engine_params = {
        "wick_threshold": wick_threshold,
        "direction": direction,
        "exit_type": exit_config["type"],
        "risk_profile": risk_profile,
    }

    # Add exit-specific params
    if exit_config["type"] == ExitType.FIXED_PCT:
        engine_params["fixed_tp_pct"] = exit_config["fixed_tp_pct"]
    elif exit_config["type"] == ExitType.TIME_BASED:
        engine_params["time_exit_bars"] = exit_config["time_exit_bars"]
    elif exit_config["type"] == ExitType.RR_RATIO:
        engine_params["rr_ratio"] = exit_config["rr_ratio"]

    # Run backtest
    try:
        engine = AdvancedBacktestEngine(**engine_params)
        result = engine.run(df)

        # Extract trades for detailed logging
        trades = result.trades if hasattr(result, 'trades') else []

        return {
            "wick_threshold": wick_threshold,
            "direction": direction,
            "exit_type": exit_config["name"],
            "risk_profile": risk_profile,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": round(result.win_rate, 2),
            "total_pnl": round(result.total_pnl, 2),
            "total_return_pct": round(result.total_pnl_percent, 2),
            "max_drawdown_pct": round(result.max_drawdown_percent, 2),
            "sharpe_ratio": round(result.sharpe_ratio, 3) if not np.isnan(result.sharpe_ratio) else 0,
            "sortino_ratio": round(result.sortino_ratio, 3) if hasattr(result, 'sortino_ratio') and not np.isnan(result.sortino_ratio) else 0,
            "profit_factor": round(min(result.profit_factor, 99.99), 2) if result.profit_factor != float('inf') else 99.99,
            "expectancy": round(result.expectancy, 2) if hasattr(result, 'expectancy') else 0,
            "avg_win": round(result.avg_win, 2) if hasattr(result, 'avg_win') else 0,
            "avg_loss": round(result.avg_loss, 2) if hasattr(result, 'avg_loss') else 0,
            "final_balance": round(result.final_balance, 2),
            "trades": trades,
        }
    except Exception as e:
        print(f"  Error: {e}")
        return None


def run_full_grid_search(df: pd.DataFrame, quick: bool = False) -> pd.DataFrame:
    """Run full grid search across all parameter combinations."""

    # Use reduced params for quick mode
    if quick:
        thresholds = [3.0, 5.0]
        directions = ["long", "both"]
        exits = [e for e in EXIT_CONFIGS if e["name"] in ["fixed_12", "rr_2"]]
        profiles = ["conservative", "moderate"]
    else:
        thresholds = WICK_THRESHOLDS
        directions = DIRECTIONS
        exits = EXIT_CONFIGS
        profiles = RISK_PROFILE_NAMES

    # Calculate total combinations
    total = len(thresholds) * len(directions) * len(exits) * len(profiles)
    print(f"\nRunning {total} backtest combinations...")

    results = []
    completed = 0
    start_time = time.time()

    for thresh in thresholds:
        for direction in directions:
            for exit_config in exits:
                for profile in profiles:
                    result = run_single_backtest(
                        df, thresh, direction, exit_config, profile
                    )

                    if result:
                        # Store without trades for summary
                        result_summary = {k: v for k, v in result.items() if k != 'trades'}
                        results.append(result_summary)

                    completed += 1
                    if completed % 20 == 0:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed
                        remaining = (total - completed) / rate
                        print(f"  Progress: {completed}/{total} ({completed/total*100:.1f}%) - "
                              f"ETA: {remaining/60:.1f}min")

    return pd.DataFrame(results)


def generate_real_report(
    df: pd.DataFrame,
    results_df: pd.DataFrame,
    signal_counts: Dict[float, Dict[str, int]],
    output_dir: Path
) -> str:
    """Generate honest backtest report with real numbers."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_start = df.index[0].strftime("%Y-%m-%d")
    data_end = df.index[-1].strftime("%Y-%m-%d")
    data_days = (df.index[-1] - df.index[0]).days

    lines = [
        "# WickTrader REAL Backtest Report",
        "",
        f"**Generated:** {timestamp}",
        f"**Data Period:** {data_start} to {data_end} ({data_days} days)",
        f"**Candles:** {len(df)} (4H timeframe)",
        f"**Variants Tested:** {len(results_df)}",
        "",
        "---",
        "",
        "## Signal Frequency by Threshold",
        "",
        "| Threshold | Long Signals | Short Signals | Total | Signals/Month |",
        "|-----------|--------------|---------------|-------|---------------|",
    ]

    for thresh in sorted(signal_counts.keys()):
        counts = signal_counts[thresh]
        per_month = counts["total"] / (data_days / 30)
        lines.append(
            f"| {thresh}% | {counts['long']} | {counts['short']} | "
            f"{counts['total']} | {per_month:.1f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Top 20 Configurations by Sharpe Ratio",
        "",
    ])

    # Filter for minimum trades
    min_trades = 3
    filtered = results_df[results_df['total_trades'] >= min_trades].copy()

    if len(filtered) > 0:
        top_20 = filtered.nlargest(20, 'sharpe_ratio')

        lines.append("| Rank | Wick | Exit | Direction | Profile | Trades | Win% | Return | Sharpe | MaxDD | PF |")
        lines.append("|------|------|------|-----------|---------|--------|------|--------|--------|-------|-----|")

        for i, (_, row) in enumerate(top_20.iterrows(), 1):
            lines.append(
                f"| {i} | {row['wick_threshold']}% | {row['exit_type']} | "
                f"{row['direction']} | {row['risk_profile']} | {row['total_trades']} | "
                f"{row['win_rate']:.1f}% | {row['total_return_pct']:+.1f}% | "
                f"{row['sharpe_ratio']:.3f} | {row['max_drawdown_pct']:.1f}% | "
                f"{row['profit_factor']:.2f} |"
            )
    else:
        lines.append("*No configurations with >= 3 trades*")

    lines.extend([
        "",
        "---",
        "",
        "## Results by Risk Profile",
        "",
    ])

    for profile in RISK_PROFILE_NAMES:
        profile_results = results_df[results_df['risk_profile'] == profile]
        if len(profile_results) == 0:
            continue

        profitable = len(profile_results[profile_results['total_pnl'] > 0])
        avg_return = profile_results['total_return_pct'].mean()
        avg_trades = profile_results['total_trades'].mean()
        avg_dd = profile_results['max_drawdown_pct'].mean()

        lines.extend([
            f"### {profile.title()}",
            f"- Variants tested: {len(profile_results)}",
            f"- Profitable: {profitable} ({profitable/len(profile_results)*100:.1f}%)",
            f"- Average return: {avg_return:+.1f}%",
            f"- Average trades: {avg_trades:.1f}",
            f"- Average max DD: {avg_dd:.1f}%",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Recommended Configurations",
        "",
        "Based on REAL backtest results:",
        "",
    ])

    # Find best by different metrics
    if len(filtered) > 0:
        best_sharpe = filtered.loc[filtered['sharpe_ratio'].idxmax()]
        best_return = filtered.loc[filtered['total_return_pct'].idxmax()]
        lowest_dd = filtered.loc[filtered['max_drawdown_pct'].idxmin()]

        lines.extend([
            "### Best Risk-Adjusted (Sharpe)",
            f"- **Config:** {best_sharpe['wick_threshold']}% wick, {best_sharpe['exit_type']}, {best_sharpe['direction']}, {best_sharpe['risk_profile']}",
            f"- **Return:** {best_sharpe['total_return_pct']:+.1f}%",
            f"- **Sharpe:** {best_sharpe['sharpe_ratio']:.3f}",
            f"- **Max DD:** {best_sharpe['max_drawdown_pct']:.1f}%",
            f"- **Trades:** {best_sharpe['total_trades']}",
            "",
            "### Highest Return",
            f"- **Config:** {best_return['wick_threshold']}% wick, {best_return['exit_type']}, {best_return['direction']}, {best_return['risk_profile']}",
            f"- **Return:** {best_return['total_return_pct']:+.1f}%",
            f"- **Sharpe:** {best_return['sharpe_ratio']:.3f}",
            f"- **Max DD:** {best_return['max_drawdown_pct']:.1f}%",
            f"- **Trades:** {best_return['total_trades']}",
            "",
            "### Lowest Drawdown",
            f"- **Config:** {lowest_dd['wick_threshold']}% wick, {lowest_dd['exit_type']}, {lowest_dd['direction']}, {lowest_dd['risk_profile']}",
            f"- **Return:** {lowest_dd['total_return_pct']:+.1f}%",
            f"- **Sharpe:** {lowest_dd['sharpe_ratio']:.3f}",
            f"- **Max DD:** {lowest_dd['max_drawdown_pct']:.1f}%",
            f"- **Trades:** {lowest_dd['total_trades']}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Important Notes",
        "",
        "1. **Signal frequency varies with market conditions.** Volatile periods produce more signals.",
        "2. **Lower thresholds (1.5-3%) generate more trades** but may have lower win rates.",
        "3. **Higher thresholds (5-7%) are more selective** but produce very few signals.",
        "4. **Past performance does not guarantee future results.**",
        "5. **All numbers are from REAL backtests on actual price data.**",
        "",
        "---",
        "",
        f"*Report generated by WickTrader Real Backtest System*",
        f"*{timestamp}*",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Run REAL grid search backtest')
    parser.add_argument('--quick', '-q', action='store_true', help='Quick mode with reduced parameters')
    parser.add_argument('--output', '-o', type=str, default='reports', help='Output directory')

    args = parser.parse_args()

    print("=" * 70)
    print("WickTrader REAL Grid Search Backtest")
    print("=" * 70)
    print("\nThis runs ACTUAL backtests on real price data.")
    print("No simulated or fake results.\n")

    # Load data
    print("Loading historical data...")
    df = load_data()
    print(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")

    # Count signals
    print("\nCounting signals by threshold...")
    signal_counts = count_signals_by_threshold(df)
    print("\nSignal counts:")
    for thresh, counts in sorted(signal_counts.items()):
        print(f"  {thresh}%: {counts['long']} long, {counts['short']} short = {counts['total']} total")

    # Run grid search
    results_df = run_full_grid_search(df, quick=args.quick)

    # Setup output
    output_dir = project_root / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save results CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"REAL_grid_search_{timestamp}.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"\nResults saved to: {csv_path}")

    # Generate report
    report = generate_real_report(df, results_df, signal_counts, output_dir)
    report_path = output_dir / f"REAL_BACKTEST_REPORT_{timestamp}.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Report saved to: {report_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    profitable = len(results_df[results_df['total_pnl'] > 0])
    print(f"Total variants tested: {len(results_df)}")
    print(f"Profitable variants: {profitable} ({profitable/len(results_df)*100:.1f}%)")

    if len(results_df) > 0:
        best = results_df.loc[results_df['sharpe_ratio'].idxmax()]
        print(f"\nBest configuration (by Sharpe):")
        print(f"  Wick: {best['wick_threshold']}%, Exit: {best['exit_type']}, "
              f"Direction: {best['direction']}, Profile: {best['risk_profile']}")
        print(f"  Return: {best['total_return_pct']:+.1f}%, Sharpe: {best['sharpe_ratio']:.3f}, "
              f"Trades: {best['total_trades']}")

    print("=" * 70)


if __name__ == "__main__":
    main()
