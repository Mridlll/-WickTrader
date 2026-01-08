"""Strategy variant grid search for wick-based trading.

Runs systematic tests across all parameter combinations:
- Entry variants (wick thresholds, direction)
- Exit variants (fixed TP, time-based, trailing, R:R)
- Risk variants (conservative, moderate, aggressive, degen)

Outputs ranked results with comprehensive metrics.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import itertools
import time

# Add project root and src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np

from backtest.advanced_engine import (
    AdvancedBacktestEngine, ExitType, RiskProfile, RISK_PROFILES
)
from backtest.engine import BacktestResult
from utils.logger import get_logger

logger = get_logger("variant_search")


@dataclass
class VariantConfig:
    """Single variant configuration."""
    # Entry parameters
    wick_threshold: float = 4.0
    direction: str = "both"

    # Exit parameters
    exit_type: ExitType = ExitType.RR_RATIO
    fixed_tp_pct: float = 10.0
    time_exit_bars: int = 30
    trailing_activation_pct: float = 8.0
    trailing_distance_pct: float = 4.0
    rr_ratio: float = 2.0

    # Risk parameters
    risk_profile: str = "moderate"
    max_heat: float = 50.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "wick_threshold": self.wick_threshold,
            "direction": self.direction,
            "exit_type": self.exit_type.value,
            "fixed_tp_pct": self.fixed_tp_pct,
            "time_exit_bars": self.time_exit_bars,
            "trailing_activation_pct": self.trailing_activation_pct,
            "rr_ratio": self.rr_ratio,
            "risk_profile": self.risk_profile,
            "max_heat": self.max_heat
        }

    def to_key(self) -> str:
        """Generate unique key for this configuration."""
        return f"{self.wick_threshold}_{self.direction}_{self.exit_type.value}_{self.risk_profile}"


@dataclass
class VariantResult:
    """Result from a single variant test."""
    config: VariantConfig
    result: BacktestResult
    runtime_seconds: float = 0.0

    @property
    def is_profitable(self) -> bool:
        return self.result.total_pnl > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to flat dictionary for DataFrame."""
        return {
            # Config
            "wick_threshold": self.config.wick_threshold,
            "direction": self.config.direction,
            "exit_type": self.config.exit_type.value,
            "fixed_tp_pct": self.config.fixed_tp_pct,
            "time_exit_bars": self.config.time_exit_bars,
            "trailing_pct": self.config.trailing_activation_pct,
            "rr_ratio": self.config.rr_ratio,
            "risk_profile": self.config.risk_profile,
            "max_heat": self.config.max_heat,

            # Results
            "total_trades": self.result.total_trades,
            "win_rate": round(self.result.win_rate, 2),
            "total_pnl": round(self.result.total_pnl, 2),
            "total_pnl_pct": round(self.result.total_pnl_percent, 2),
            "profit_factor": round(self.result.profit_factor, 2) if self.result.profit_factor != float('inf') else 99.99,
            "sharpe_ratio": round(self.result.sharpe_ratio, 2),
            "sortino_ratio": round(self.result.sortino_ratio, 2),
            "calmar_ratio": round(self.result.calmar_ratio, 2),
            "max_drawdown_pct": round(self.result.max_drawdown_percent, 2),
            "expectancy": round(self.result.expectancy, 2),
            "recovery_factor": round(self.result.recovery_factor, 2),
            "cagr": round(self.result.cagr, 2),
            "avg_win": round(self.result.avg_win, 2),
            "avg_loss": round(self.result.avg_loss, 2),
            "avg_bars": round(self.result.avg_trade_duration, 1),
            "final_balance": round(self.result.final_balance, 2),
            "runtime_sec": round(self.runtime_seconds, 2)
        }


class VariantSearchEngine:
    """
    Comprehensive variant search engine.

    Runs grid search across all parameter combinations and
    ranks results by various metrics.
    """

    # Default search spaces
    DEFAULT_WICK_THRESHOLDS = [3.0, 4.0, 5.0, 6.0, 7.0]
    DEFAULT_DIRECTIONS = ["long", "both"]

    DEFAULT_FIXED_TP_PCTS = [8.0, 10.0, 12.0, 15.0]
    DEFAULT_TIME_BARS = [20, 30, 40]
    DEFAULT_TRAILING_PCTS = [8.0, 10.0, 12.0]
    DEFAULT_RR_RATIOS = [2.0, 3.0]

    DEFAULT_RISK_PROFILES = ["conservative", "moderate", "aggressive", "degen"]
    DEFAULT_HEAT_LIMITS = [30.0, 50.0, 70.0, 90.0]

    def __init__(
        self,
        initial_balance: float = 10000.0,
        commission_rate: float = 0.0006,
        # Search space customization
        wick_thresholds: Optional[List[float]] = None,
        directions: Optional[List[str]] = None,
        fixed_tp_pcts: Optional[List[float]] = None,
        time_bars: Optional[List[int]] = None,
        trailing_pcts: Optional[List[float]] = None,
        rr_ratios: Optional[List[float]] = None,
        risk_profiles: Optional[List[str]] = None,
        heat_limits: Optional[List[float]] = None,
        # Run settings
        parallel: bool = False,
        verbose: bool = True
    ):
        """
        Initialize variant search engine.

        Args:
            initial_balance: Starting balance
            commission_rate: Commission rate
            wick_thresholds: Wick threshold values to test
            directions: Trade directions to test
            fixed_tp_pcts: Fixed TP percentages to test
            time_bars: Time-based exit bars to test
            trailing_pcts: Trailing activation percentages to test
            rr_ratios: R:R ratios to test
            risk_profiles: Risk profiles to test
            heat_limits: Heat limits to test
            parallel: Run tests in parallel (not implemented)
            verbose: Print progress
        """
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.parallel = parallel
        self.verbose = verbose

        # Search spaces
        self.wick_thresholds = wick_thresholds or self.DEFAULT_WICK_THRESHOLDS
        self.directions = directions or self.DEFAULT_DIRECTIONS
        self.fixed_tp_pcts = fixed_tp_pcts or self.DEFAULT_FIXED_TP_PCTS
        self.time_bars = time_bars or self.DEFAULT_TIME_BARS
        self.trailing_pcts = trailing_pcts or self.DEFAULT_TRAILING_PCTS
        self.rr_ratios = rr_ratios or self.DEFAULT_RR_RATIOS
        self.risk_profiles = risk_profiles or self.DEFAULT_RISK_PROFILES
        self.heat_limits = heat_limits or self.DEFAULT_HEAT_LIMITS

        # Results storage
        self.results: List[VariantResult] = []

    def generate_configurations(self) -> List[VariantConfig]:
        """
        Generate all variant configurations.

        Returns:
            List of VariantConfig objects
        """
        configs = []

        # Entry variants x Exit variants x Risk variants
        for wick_threshold in self.wick_thresholds:
            for direction in self.directions:
                for risk_profile in self.risk_profiles:
                    # Get corresponding heat limit
                    profile_idx = self.risk_profiles.index(risk_profile)
                    max_heat = self.heat_limits[min(profile_idx, len(self.heat_limits) - 1)]

                    # Fixed TP exits
                    for fixed_tp in self.fixed_tp_pcts:
                        configs.append(VariantConfig(
                            wick_threshold=wick_threshold,
                            direction=direction,
                            exit_type=ExitType.FIXED_PCT,
                            fixed_tp_pct=fixed_tp,
                            risk_profile=risk_profile,
                            max_heat=max_heat
                        ))

                    # Time-based exits
                    for time_bar in self.time_bars:
                        configs.append(VariantConfig(
                            wick_threshold=wick_threshold,
                            direction=direction,
                            exit_type=ExitType.TIME_BASED,
                            time_exit_bars=time_bar,
                            risk_profile=risk_profile,
                            max_heat=max_heat
                        ))

                    # Trailing exits
                    for trailing_pct in self.trailing_pcts:
                        configs.append(VariantConfig(
                            wick_threshold=wick_threshold,
                            direction=direction,
                            exit_type=ExitType.TRAILING,
                            trailing_activation_pct=trailing_pct,
                            risk_profile=risk_profile,
                            max_heat=max_heat
                        ))

                    # R:R exits
                    for rr_ratio in self.rr_ratios:
                        configs.append(VariantConfig(
                            wick_threshold=wick_threshold,
                            direction=direction,
                            exit_type=ExitType.RR_RATIO,
                            rr_ratio=rr_ratio,
                            risk_profile=risk_profile,
                            max_heat=max_heat
                        ))

        return configs

    def run_single_variant(
        self,
        df: pd.DataFrame,
        config: VariantConfig
    ) -> VariantResult:
        """
        Run single variant backtest.

        Args:
            df: OHLCV DataFrame
            config: Variant configuration

        Returns:
            VariantResult
        """
        # Create custom risk profile if heat limit differs from default
        if config.risk_profile in RISK_PROFILES:
            base_profile = RISK_PROFILES[config.risk_profile]
            custom_profile = RiskProfile(
                name=config.risk_profile,
                risk_percent=base_profile.risk_percent,
                leverage=base_profile.leverage,
                max_heat=config.max_heat,
                green_max=config.max_heat * 0.5,
                yellow_max=config.max_heat * 0.8,
                red_max=config.max_heat
            )
        else:
            custom_profile = None

        # Create engine with config
        engine = AdvancedBacktestEngine(
            initial_balance=self.initial_balance,
            risk_profile=config.risk_profile,
            commission_rate=self.commission_rate,
            wick_threshold=config.wick_threshold,
            direction=config.direction,
            exit_type=config.exit_type,
            fixed_tp_pct=config.fixed_tp_pct,
            rr_ratio=config.rr_ratio,
            trailing_activation_pct=config.trailing_activation_pct,
            time_exit_bars=config.time_exit_bars,
            custom_risk_profile=custom_profile
        )

        # Run backtest
        start_time = time.time()
        result = engine.run(df)
        runtime = time.time() - start_time

        return VariantResult(
            config=config,
            result=result,
            runtime_seconds=runtime
        )

    def run_search(
        self,
        df: pd.DataFrame,
        configs: Optional[List[VariantConfig]] = None
    ) -> pd.DataFrame:
        """
        Run full variant search.

        Args:
            df: OHLCV DataFrame
            configs: Optional list of configs (generates if None)

        Returns:
            DataFrame with all results
        """
        if configs is None:
            configs = self.generate_configurations()

        total = len(configs)
        if self.verbose:
            logger.info(f"Running variant search: {total} configurations")

        self.results = []
        completed = 0

        for config in configs:
            try:
                result = self.run_single_variant(df, config)
                self.results.append(result)
            except Exception as e:
                logger.error(f"Error running variant {config.to_key()}: {e}")

            completed += 1
            if self.verbose and completed % 10 == 0:
                logger.info(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")

        # Convert to DataFrame
        results_df = pd.DataFrame([r.to_dict() for r in self.results])

        if self.verbose:
            logger.info(f"Completed {len(self.results)} variants")

        return results_df

    def get_top_results(
        self,
        results_df: pd.DataFrame,
        sort_by: str = "total_pnl",
        n: int = 20,
        min_trades: int = 5
    ) -> pd.DataFrame:
        """
        Get top N results by specified metric.

        Args:
            results_df: Results DataFrame
            sort_by: Column to sort by
            n: Number of results to return
            min_trades: Minimum trades required

        Returns:
            Top N results DataFrame
        """
        filtered = results_df[results_df['total_trades'] >= min_trades].copy()

        # Handle infinity values
        if sort_by in ['profit_factor', 'sharpe_ratio', 'sortino_ratio']:
            filtered[sort_by] = filtered[sort_by].replace([np.inf, -np.inf], np.nan)

        sorted_df = filtered.sort_values(sort_by, ascending=False)
        return sorted_df.head(n)

    def get_best_by_risk_profile(
        self,
        results_df: pd.DataFrame,
        sort_by: str = "total_pnl",
        min_trades: int = 5
    ) -> Dict[str, pd.Series]:
        """
        Get best result for each risk profile.

        Args:
            results_df: Results DataFrame
            sort_by: Column to sort by
            min_trades: Minimum trades required

        Returns:
            Dictionary of risk profile -> best result
        """
        filtered = results_df[results_df['total_trades'] >= min_trades]
        best = {}

        for profile in self.risk_profiles:
            profile_results = filtered[filtered['risk_profile'] == profile]
            if len(profile_results) > 0:
                best_idx = profile_results[sort_by].idxmax()
                best[profile] = profile_results.loc[best_idx]

        return best

    def get_best_by_exit_type(
        self,
        results_df: pd.DataFrame,
        sort_by: str = "total_pnl",
        min_trades: int = 5
    ) -> Dict[str, pd.Series]:
        """
        Get best result for each exit type.

        Args:
            results_df: Results DataFrame
            sort_by: Column to sort by
            min_trades: Minimum trades required

        Returns:
            Dictionary of exit type -> best result
        """
        filtered = results_df[results_df['total_trades'] >= min_trades]
        best = {}

        for exit_type in ExitType:
            exit_results = filtered[filtered['exit_type'] == exit_type.value]
            if len(exit_results) > 0:
                best_idx = exit_results[sort_by].idxmax()
                best[exit_type.value] = exit_results.loc[best_idx]

        return best

    def analyze_results(
        self,
        results_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Comprehensive analysis of results.

        Args:
            results_df: Results DataFrame

        Returns:
            Analysis dictionary
        """
        analysis = {}

        # Overall statistics
        analysis['total_variants'] = len(results_df)
        analysis['profitable_variants'] = (results_df['total_pnl'] > 0).sum()
        analysis['profitable_pct'] = analysis['profitable_variants'] / len(results_df) * 100

        # Best overall
        best_idx = results_df['total_pnl'].idxmax()
        analysis['best_overall'] = results_df.loc[best_idx].to_dict()

        # Best by Sharpe
        valid_sharpe = results_df[results_df['sharpe_ratio'].notna() & (results_df['sharpe_ratio'] < 100)]
        if len(valid_sharpe) > 0:
            best_sharpe_idx = valid_sharpe['sharpe_ratio'].idxmax()
            analysis['best_sharpe'] = valid_sharpe.loc[best_sharpe_idx].to_dict()

        # Best by Calmar
        valid_calmar = results_df[results_df['calmar_ratio'].notna() & (results_df['calmar_ratio'] < 100)]
        if len(valid_calmar) > 0:
            best_calmar_idx = valid_calmar['calmar_ratio'].idxmax()
            analysis['best_calmar'] = valid_calmar.loc[best_calmar_idx].to_dict()

        # By risk profile
        analysis['by_risk_profile'] = {}
        for profile in results_df['risk_profile'].unique():
            profile_df = results_df[results_df['risk_profile'] == profile]
            analysis['by_risk_profile'][profile] = {
                'count': len(profile_df),
                'profitable': (profile_df['total_pnl'] > 0).sum(),
                'avg_pnl': profile_df['total_pnl'].mean(),
                'avg_sharpe': profile_df['sharpe_ratio'].mean(),
                'avg_max_dd': profile_df['max_drawdown_pct'].mean()
            }

        # By exit type
        analysis['by_exit_type'] = {}
        for exit_type in results_df['exit_type'].unique():
            exit_df = results_df[results_df['exit_type'] == exit_type]
            analysis['by_exit_type'][exit_type] = {
                'count': len(exit_df),
                'profitable': (exit_df['total_pnl'] > 0).sum(),
                'avg_pnl': exit_df['total_pnl'].mean(),
                'avg_sharpe': exit_df['sharpe_ratio'].mean(),
                'avg_win_rate': exit_df['win_rate'].mean()
            }

        # By wick threshold
        analysis['by_wick_threshold'] = {}
        for threshold in sorted(results_df['wick_threshold'].unique()):
            thresh_df = results_df[results_df['wick_threshold'] == threshold]
            analysis['by_wick_threshold'][threshold] = {
                'count': len(thresh_df),
                'profitable': (thresh_df['total_pnl'] > 0).sum(),
                'avg_pnl': thresh_df['total_pnl'].mean(),
                'avg_trades': thresh_df['total_trades'].mean()
            }

        return analysis

    def print_results_table(
        self,
        results_df: pd.DataFrame,
        top_n: int = 30,
        sort_by: str = "total_pnl"
    ) -> None:
        """Print formatted results table."""
        top_results = self.get_top_results(results_df, sort_by=sort_by, n=top_n)

        print("\n" + "=" * 140)
        print("VARIANT SEARCH RESULTS")
        print("=" * 140)

        # Header
        cols = ['wick_threshold', 'direction', 'exit_type', 'risk_profile',
                'total_trades', 'win_rate', 'total_pnl', 'profit_factor',
                'sharpe_ratio', 'max_drawdown_pct', 'cagr']

        header = " | ".join([f"{col:>15}" for col in cols])
        print(header)
        print("-" * 140)

        # Rows
        for _, row in top_results.iterrows():
            values = []
            for col in cols:
                val = row[col]
                if isinstance(val, float):
                    if col in ['wick_threshold', 'win_rate', 'max_drawdown_pct', 'cagr']:
                        values.append(f"{val:>15.1f}")
                    else:
                        values.append(f"{val:>15.2f}")
                else:
                    values.append(f"{str(val):>15}")
            print(" | ".join(values))

        print("=" * 140)


def run_variant_search(
    df: pd.DataFrame,
    quick: bool = False,
    output_path: Optional[str] = None,
    **kwargs
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Convenience function to run variant search.

    Args:
        df: OHLCV DataFrame
        quick: Run with reduced parameter space
        output_path: Path to save results CSV
        **kwargs: Additional engine parameters

    Returns:
        Tuple of (results_df, analysis)
    """
    if quick:
        # Reduced search space for quick testing
        engine = VariantSearchEngine(
            wick_thresholds=[4.0, 5.0],
            directions=["both"],
            fixed_tp_pcts=[10.0],
            time_bars=[30],
            trailing_pcts=[10.0],
            rr_ratios=[2.0, 3.0],
            risk_profiles=["moderate", "aggressive"],
            heat_limits=[50.0, 70.0],
            **kwargs
        )
    else:
        engine = VariantSearchEngine(**kwargs)

    # Run search
    results_df = engine.run_search(df)

    # Analyze
    analysis = engine.analyze_results(results_df)

    # Print results
    engine.print_results_table(results_df)

    # Save if path provided
    if output_path:
        results_df.to_csv(output_path, index=False)
        logger.info(f"Results saved to: {output_path}")

    return results_df, analysis


# Main entry point for command-line usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run variant search for wick strategy")
    parser.add_argument("--data", "-d", required=True, help="Path to OHLCV CSV")
    parser.add_argument("--output", "-o", help="Output CSV path")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick test mode")
    parser.add_argument("--balance", type=float, default=10000, help="Initial balance")

    args = parser.parse_args()

    # Load data
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        sys.exit(1)

    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)

    print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")

    # Run search
    results_df, analysis = run_variant_search(
        df=df,
        quick=args.quick,
        output_path=args.output,
        initial_balance=args.balance
    )

    # Print analysis summary
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Total variants tested: {analysis['total_variants']}")
    print(f"Profitable variants: {analysis['profitable_variants']} ({analysis['profitable_pct']:.1f}%)")
    print()
    print("Best overall:")
    best = analysis['best_overall']
    print(f"  Wick: {best['wick_threshold']}%, Exit: {best['exit_type']}, Risk: {best['risk_profile']}")
    print(f"  P&L: ${best['total_pnl']:,.2f} ({best['total_pnl_pct']:.1f}%)")
    print(f"  Sharpe: {best['sharpe_ratio']:.2f}, Max DD: {best['max_drawdown_pct']:.1f}%")
