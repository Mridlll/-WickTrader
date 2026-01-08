#!/usr/bin/env python3
"""
Wick-Based Trading Strategy Backtest Runner

Runs a grid search over wick strategy parameters for SOL 4H data.
Outputs comparison tables and exports results to CSV.

Usage:
    python backtest/run_wick_backtest.py
    python backtest/run_wick_backtest.py --quick  # Run with reduced parameter grid
    python backtest/run_wick_backtest.py --threshold 2.0 --exit rr_3 --filter trend
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional
import itertools

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np

from backtest.wick_engine import WickBacktestEngine, ExitStrategy, FilterType
from utils.logger import get_logger, setup_logger

# Setup logger
setup_logger(log_level="INFO")
logger = get_logger("wick_runner")


def load_data(filepath: str) -> pd.DataFrame:
    """
    Load and prepare OHLCV data from CSV.

    Args:
        filepath: Path to CSV file

    Returns:
        DataFrame with datetime index
    """
    logger.info(f"Loading data from {filepath}")

    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)

    # Ensure required columns
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    logger.info(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")

    return df


def run_single_backtest(
    df: pd.DataFrame,
    wick_threshold: float,
    exit_strategy: ExitStrategy,
    filter_type: FilterType,
    initial_balance: float = 10000.0,
    risk_percent: float = 3.0,
    leverage: float = 3.0
) -> Dict[str, Any]:
    """
    Run a single backtest with specified parameters.

    Returns:
        Dictionary with parameters and results
    """
    engine = WickBacktestEngine(
        initial_balance=initial_balance,
        risk_percent=risk_percent,
        leverage=leverage,
        wick_threshold=wick_threshold,
        exit_strategy=exit_strategy,
        filter_type=filter_type
    )

    result = engine.run(df)

    return {
        "wick_threshold": wick_threshold,
        "exit_strategy": exit_strategy.value,
        "filter": filter_type.value,
        "total_trades": result.total_trades,
        "win_rate": round(result.win_rate, 2),
        "total_pnl": round(result.total_pnl, 2),
        "total_pnl_pct": round(result.total_pnl_percent, 2),
        "profit_factor": round(result.profit_factor, 2) if result.profit_factor != float('inf') else "inf",
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "max_drawdown_pct": round(result.max_drawdown_percent, 2),
        "avg_win": round(result.avg_win, 2),
        "avg_loss": round(result.avg_loss, 2),
        "largest_win": round(result.largest_win, 2),
        "largest_loss": round(result.largest_loss, 2),
        "final_balance": round(result.final_balance, 2)
    }


def run_grid_search(
    df: pd.DataFrame,
    thresholds: List[float],
    exit_strategies: List[ExitStrategy],
    filters: List[FilterType],
    initial_balance: float = 10000.0,
    risk_percent: float = 3.0,
    leverage: float = 3.0
) -> pd.DataFrame:
    """
    Run grid search over all parameter combinations.

    Returns:
        DataFrame with all results
    """
    total_combinations = len(thresholds) * len(exit_strategies) * len(filters)
    logger.info(f"Running grid search: {total_combinations} combinations")
    logger.info(f"  Thresholds: {thresholds}")
    logger.info(f"  Exit strategies: {[e.value for e in exit_strategies]}")
    logger.info(f"  Filters: {[f.value for f in filters]}")

    results = []
    completed = 0

    for threshold, exit_strat, filt in itertools.product(thresholds, exit_strategies, filters):
        try:
            result = run_single_backtest(
                df=df,
                wick_threshold=threshold,
                exit_strategy=exit_strat,
                filter_type=filt,
                initial_balance=initial_balance,
                risk_percent=risk_percent,
                leverage=leverage
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Error with threshold={threshold}, exit={exit_strat.value}, filter={filt.value}: {e}")
            results.append({
                "wick_threshold": threshold,
                "exit_strategy": exit_strat.value,
                "filter": filt.value,
                "error": str(e)
            })

        completed += 1
        if completed % 10 == 0 or completed == total_combinations:
            logger.info(f"Progress: {completed}/{total_combinations} ({completed/total_combinations*100:.1f}%)")

    return pd.DataFrame(results)


def print_results_table(results_df: pd.DataFrame) -> None:
    """Print formatted results table to console."""
    print("\n" + "=" * 120)
    print("WICK STRATEGY BACKTEST RESULTS")
    print("=" * 120)

    # Sort by total PnL
    if 'total_pnl' in results_df.columns:
        sorted_df = results_df.sort_values('total_pnl', ascending=False)
    else:
        sorted_df = results_df

    # Select columns for display
    display_cols = [
        'wick_threshold', 'exit_strategy', 'filter', 'total_trades',
        'win_rate', 'total_pnl', 'profit_factor', 'sharpe_ratio', 'max_drawdown_pct'
    ]

    # Filter to existing columns
    display_cols = [c for c in display_cols if c in sorted_df.columns]

    # Print header
    header = " | ".join([f"{col:>15}" for col in display_cols])
    print(header)
    print("-" * len(header))

    # Print rows
    for _, row in sorted_df.head(30).iterrows():
        values = []
        for col in display_cols:
            val = row[col]
            if isinstance(val, float):
                values.append(f"{val:>15.2f}")
            else:
                values.append(f"{str(val):>15}")
        print(" | ".join(values))

    print("=" * 120)


def identify_optimal_params(results_df: pd.DataFrame) -> Dict[str, Any]:
    """Identify optimal parameter combination based on multiple criteria."""
    print("\n" + "=" * 80)
    print("OPTIMAL PARAMETER IDENTIFICATION")
    print("=" * 80)

    # Filter out error rows
    valid_df = results_df[~results_df.get('error', pd.Series([False]*len(results_df))).astype(bool)]

    if len(valid_df) == 0:
        print("No valid results to analyze")
        return {}

    # Best by PnL
    if 'total_pnl' in valid_df.columns:
        best_pnl = valid_df.loc[valid_df['total_pnl'].idxmax()]
        print(f"\nBest by Total PnL:")
        print(f"  Threshold: {best_pnl['wick_threshold']}")
        print(f"  Exit Strategy: {best_pnl['exit_strategy']}")
        print(f"  Filter: {best_pnl['filter']}")
        print(f"  Total PnL: ${best_pnl['total_pnl']:.2f} ({best_pnl['total_pnl_pct']:.2f}%)")
        print(f"  Win Rate: {best_pnl['win_rate']:.2f}%")
        print(f"  Profit Factor: {best_pnl['profit_factor']}")

    # Best by Sharpe
    if 'sharpe_ratio' in valid_df.columns:
        best_sharpe = valid_df.loc[valid_df['sharpe_ratio'].idxmax()]
        print(f"\nBest by Sharpe Ratio:")
        print(f"  Threshold: {best_sharpe['wick_threshold']}")
        print(f"  Exit Strategy: {best_sharpe['exit_strategy']}")
        print(f"  Filter: {best_sharpe['filter']}")
        print(f"  Sharpe Ratio: {best_sharpe['sharpe_ratio']:.2f}")
        print(f"  Total PnL: ${best_sharpe['total_pnl']:.2f}")

    # Best by Win Rate (with minimum trades)
    if 'win_rate' in valid_df.columns:
        min_trades = 10
        filtered = valid_df[valid_df['total_trades'] >= min_trades]
        if len(filtered) > 0:
            best_wr = filtered.loc[filtered['win_rate'].idxmax()]
            print(f"\nBest by Win Rate (min {min_trades} trades):")
            print(f"  Threshold: {best_wr['wick_threshold']}")
            print(f"  Exit Strategy: {best_wr['exit_strategy']}")
            print(f"  Filter: {best_wr['filter']}")
            print(f"  Win Rate: {best_wr['win_rate']:.2f}%")
            print(f"  Total Trades: {best_wr['total_trades']}")

    # Best Risk-Adjusted (PnL / Max DD)
    if 'total_pnl' in valid_df.columns and 'max_drawdown_pct' in valid_df.columns:
        valid_df_copy = valid_df.copy()
        valid_df_copy['risk_adjusted'] = valid_df_copy['total_pnl'] / (valid_df_copy['max_drawdown_pct'] + 0.01)
        best_ra = valid_df_copy.loc[valid_df_copy['risk_adjusted'].idxmax()]
        print(f"\nBest Risk-Adjusted (PnL / MaxDD):")
        print(f"  Threshold: {best_ra['wick_threshold']}")
        print(f"  Exit Strategy: {best_ra['exit_strategy']}")
        print(f"  Filter: {best_ra['filter']}")
        print(f"  Total PnL: ${best_ra['total_pnl']:.2f}")
        print(f"  Max Drawdown: {best_ra['max_drawdown_pct']:.2f}%")

    print("=" * 80)

    return {
        "best_pnl": best_pnl.to_dict() if 'total_pnl' in valid_df.columns else {},
        "best_sharpe": best_sharpe.to_dict() if 'sharpe_ratio' in valid_df.columns else {},
    }


def export_results(
    results_df: pd.DataFrame,
    output_dir: str = "data",
    prefix: str = "wick_backtest"
) -> str:
    """
    Export results to CSV file.

    Returns:
        Path to exported file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_results_{timestamp}.csv"
    filepath = output_path / filename

    results_df.to_csv(filepath, index=False)
    logger.info(f"Results exported to: {filepath}")

    return str(filepath)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run wick-based trading strategy backtest")

    parser.add_argument(
        "--data", "-d",
        default="data/binance_cache_1year/sol_4h.csv",
        help="Path to OHLCV data CSV (default: data/binance_cache_1year/sol_4h.csv)"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Run with reduced parameter grid for quick testing"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        help="Run single backtest with specific threshold"
    )
    parser.add_argument(
        "--exit", "-e",
        type=str,
        help="Run single backtest with specific exit strategy"
    )
    parser.add_argument(
        "--filter", "-f",
        type=str,
        help="Run single backtest with specific filter"
    )
    parser.add_argument(
        "--output", "-o",
        default="data",
        help="Output directory for results CSV (default: data)"
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=10000.0,
        help="Initial balance (default: 10000)"
    )
    parser.add_argument(
        "--risk",
        type=float,
        default=3.0,
        help="Risk percent per trade (default: 3.0)"
    )
    parser.add_argument(
        "--leverage",
        type=float,
        default=3.0,
        help="Leverage multiplier (default: 3.0)"
    )

    args = parser.parse_args()

    # Resolve data path
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = project_root / data_path

    if not data_path.exists():
        logger.error(f"Data file not found: {data_path}")
        sys.exit(1)

    # Load data
    df = load_data(str(data_path))

    # Single backtest mode
    if args.threshold and args.exit and args.filter:
        exit_strat = ExitStrategy(args.exit)
        filt = FilterType(args.filter)

        result = run_single_backtest(
            df=df,
            wick_threshold=args.threshold,
            exit_strategy=exit_strat,
            filter_type=filt,
            initial_balance=args.balance,
            risk_percent=args.risk,
            leverage=args.leverage
        )

        print("\n" + "=" * 60)
        print("SINGLE BACKTEST RESULT")
        print("=" * 60)
        for key, value in result.items():
            print(f"  {key}: {value}")
        print("=" * 60)

        return

    # Grid search mode
    if args.quick:
        # Reduced grid for quick testing
        thresholds = [1.5, 2.5]
        exit_strategies = [ExitStrategy.RR_2, ExitStrategy.FIXED_15, ExitStrategy.TRAILING]
        filters = [FilterType.NONE, FilterType.TREND]
    else:
        # Full grid
        thresholds = [1.5, 2.0, 2.5, 3.0]
        exit_strategies = list(ExitStrategy)
        filters = list(FilterType)

    # Run grid search
    results_df = run_grid_search(
        df=df,
        thresholds=thresholds,
        exit_strategies=exit_strategies,
        filters=filters,
        initial_balance=args.balance,
        risk_percent=args.risk,
        leverage=args.leverage
    )

    # Print results
    print_results_table(results_df)

    # Identify optimal params
    identify_optimal_params(results_df)

    # Export results
    output_path = args.output
    if not Path(output_path).is_absolute():
        output_path = str(project_root / output_path)

    export_path = export_results(results_df, output_dir=output_path)

    print(f"\nResults exported to: {export_path}")

    # Summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Data: {data_path}")
    print(f"Period: {df.index[0]} to {df.index[-1]}")
    print(f"Total candles: {len(df)}")
    print(f"Total combinations tested: {len(results_df)}")

    if 'total_pnl' in results_df.columns:
        profitable = (results_df['total_pnl'] > 0).sum()
        print(f"Profitable combinations: {profitable}/{len(results_df)} ({profitable/len(results_df)*100:.1f}%)")

    print("=" * 60)


if __name__ == "__main__":
    main()
