#!/usr/bin/env python3
"""
Export detailed trade logs from backtests to CSV files.

Usage:
    python -m backtest.export_trade_logs
    python -m backtest.export_trade_logs --strategy backtest-winner
    python -m backtest.export_trade_logs --all
"""

import sys
from pathlib import Path
from datetime import datetime
import argparse

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
from backtest.advanced_engine import AdvancedBacktestEngine, ExitType, RISK_PROFILES

# Strategy presets matching run_bot.py
STRATEGY_CONFIGS = {
    "backtest-winner": {
        "name": "Backtest Winner (Best Sharpe)",
        "wick_threshold": 7.0,
        "exit_type": ExitType.FIXED_PCT,
        "fixed_tp_pct": 12.0,
        "risk_profile": "conservative",
        "direction": "long",
    },
    "safe": {
        "name": "Safe (Low Drawdown)",
        "wick_threshold": 6.0,
        "exit_type": ExitType.RR_RATIO,
        "rr_ratio": 2.0,
        "risk_profile": "conservative",
        "direction": "long",
    },
    "aggressive": {
        "name": "Aggressive (High Returns)",
        "wick_threshold": 6.0,
        "exit_type": ExitType.TIME_BASED,
        "time_exit_bars": 40,
        "risk_profile": "aggressive",
        "direction": "long",
    },
    "degen": {
        "name": "Degen (Maximum Risk)",
        "wick_threshold": 7.0,
        "exit_type": ExitType.RR_RATIO,
        "rr_ratio": 3.0,
        "risk_profile": "degen",
        "direction": "long",
    },
    # Additional configs for more signal visibility
    "5pct-conservative": {
        "name": "5% Wick Conservative",
        "wick_threshold": 5.0,
        "exit_type": ExitType.FIXED_PCT,
        "fixed_tp_pct": 10.0,
        "risk_profile": "conservative",
        "direction": "long",
    },
    "5pct-moderate": {
        "name": "5% Wick Moderate",
        "wick_threshold": 5.0,
        "exit_type": ExitType.RR_RATIO,
        "rr_ratio": 2.0,
        "risk_profile": "moderate",
        "direction": "long",
    },
    "4pct-conservative": {
        "name": "4% Wick Conservative",
        "wick_threshold": 4.0,
        "exit_type": ExitType.FIXED_PCT,
        "fixed_tp_pct": 10.0,
        "risk_profile": "conservative",
        "direction": "long",
    },
}


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
        df.set_index('timestamp', inplace=True)
    else:
        # Fetch from Binance
        print("Fetching data from Binance...")
        from exchanges.binance import BinanceExchange

        exchange = BinanceExchange(testnet=True)
        df = exchange.get_historical_klines(
            symbol="SOLUSDT",
            interval="4h",
            limit=1000
        )

        # Save for future use
        data_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(data_dir / "sol_4h_data.parquet")

    # Ensure proper column names
    if 'open' not in df.columns:
        df.columns = ['open', 'high', 'low', 'close', 'volume']

    return df


def run_backtest_and_export(strategy_name: str, df: pd.DataFrame) -> dict:
    """Run backtest for a strategy and return results."""
    config = STRATEGY_CONFIGS[strategy_name]

    # Build engine params
    engine_params = {
        "wick_threshold": config["wick_threshold"],
        "exit_type": config["exit_type"],
        "risk_profile": config["risk_profile"],
        "direction": config["direction"],
    }

    # Add exit-specific params
    if config["exit_type"] == ExitType.FIXED_PCT:
        engine_params["fixed_tp_pct"] = config.get("fixed_tp_pct", 12.0)
    elif config["exit_type"] == ExitType.RR_RATIO:
        engine_params["rr_ratio"] = config.get("rr_ratio", 2.0)
    elif config["exit_type"] == ExitType.TIME_BASED:
        engine_params["time_exit_bars"] = config.get("time_exit_bars", 30)

    # Run backtest
    engine = AdvancedBacktestEngine(**engine_params)
    result = engine.run(df)

    return {
        "strategy": strategy_name,
        "config_name": config["name"],
        "result": result,
        "trades": result.trades if hasattr(result, 'trades') else []
    }


def trades_to_dataframe(trades: list, strategy_name: str) -> pd.DataFrame:
    """Convert trade records to DataFrame."""
    if not trades:
        return pd.DataFrame()

    records = []
    for i, trade in enumerate(trades, 1):
        # Skip incomplete trades (no exit)
        if trade.exit_price is None:
            continue

        record = {
            "trade_num": i,
            "strategy": strategy_name,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "direction": trade.signal_type.value if hasattr(trade.signal_type, 'value') else str(trade.signal_type),
            "entry_price": round(trade.entry_price, 4),
            "exit_price": round(trade.exit_price, 4),
            "stop_loss": round(trade.stop_loss, 4),
            "take_profit": round(trade.take_profit, 4) if trade.take_profit else None,
            "size": round(trade.size, 4),
            "pnl": round(trade.pnl, 2),
            "pnl_percent": round(trade.pnl_percent, 2),
            "exit_reason": trade.exit_reason,
            "bars_held": trade.bars_held,
            "leverage": trade.leverage_used if hasattr(trade, 'leverage_used') else None,
            "wick_pct": round(trade.wick_pct, 2) if hasattr(trade, 'wick_pct') else None,
            "heat_zone": trade.heat_zone.value if hasattr(trade, 'heat_zone') and hasattr(trade.heat_zone, 'value') else None,
            "commission": round(trade.commission, 2) if trade.commission else 0,
        }
        records.append(record)

    return pd.DataFrame(records)


def export_strategy(strategy_name: str, df: pd.DataFrame, output_dir: Path) -> dict:
    """Export trade logs for a strategy."""
    print(f"\n{'='*60}")
    print(f"Running backtest: {strategy_name}")
    print(f"{'='*60}")

    result_data = run_backtest_and_export(strategy_name, df)
    result = result_data["result"]
    trades = result_data["trades"]

    # Print summary
    print(f"  Config: {result_data['config_name']}")
    print(f"  Total Trades: {result.total_trades}")
    print(f"  Win Rate: {result.win_rate:.1f}%")
    print(f"  Return: {result.total_pnl_percent:+.1f}%")
    print(f"  Max Drawdown: {result.max_drawdown_percent:.1f}%")
    print(f"  Sharpe Ratio: {result.sharpe_ratio:.3f}")

    # Convert to DataFrame and export
    trades_df = trades_to_dataframe(trades, strategy_name)

    if not trades_df.empty:
        # Export to CSV
        csv_path = output_dir / f"trades_{strategy_name}.csv"
        trades_df.to_csv(csv_path, index=False)
        print(f"  Exported: {csv_path}")

        # Show trade frequency
        if result.total_trades > 0:
            data_days = (df.index[-1] - df.index[0]).days
            trades_per_month = result.total_trades / (data_days / 30)
            print(f"  Trade Frequency: ~{trades_per_month:.1f} trades/month")
    else:
        print(f"  No trades to export")

    return {
        "strategy": strategy_name,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "return_pct": result.total_pnl_percent,
        "max_dd": result.max_drawdown_percent,
        "sharpe": result.sharpe_ratio,
        "trades_df": trades_df
    }


def main():
    parser = argparse.ArgumentParser(description='Export backtest trade logs to CSV')
    parser.add_argument('--strategy', '-s', choices=list(STRATEGY_CONFIGS.keys()),
                        help='Strategy to export (default: all)')
    parser.add_argument('--all', '-a', action='store_true',
                        help='Export all strategies')
    parser.add_argument('--output', '-o', type=str, default='reports',
                        help='Output directory (default: reports)')

    args = parser.parse_args()

    # Load data
    print("Loading historical data...")
    df = load_data()
    print(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")

    # Setup output directory
    output_dir = project_root / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which strategies to run
    if args.strategy:
        strategies = [args.strategy]
    else:
        strategies = list(STRATEGY_CONFIGS.keys())

    # Run backtests and export
    all_results = []
    all_trades = []

    for strategy in strategies:
        result = export_strategy(strategy, df, output_dir)
        all_results.append(result)
        if not result["trades_df"].empty:
            all_trades.append(result["trades_df"])

    # Create combined CSV with all trades
    if all_trades:
        combined_df = pd.concat(all_trades, ignore_index=True)
        combined_path = output_dir / "trades_all_strategies.csv"
        combined_df.to_csv(combined_path, index=False)
        print(f"\n{'='*60}")
        print(f"Combined trade log: {combined_path}")
        print(f"Total trades across all strategies: {len(combined_df)}")

    # Summary table
    print(f"\n{'='*60}")
    print("SUMMARY: Expected Trades Per Strategy")
    print(f"{'='*60}")
    print(f"{'Strategy':<20} {'Trades':<10} {'Win%':<10} {'Return':<12} {'MaxDD':<10} {'Sharpe':<10}")
    print("-" * 72)

    for r in all_results:
        print(f"{r['strategy']:<20} {r['total_trades']:<10} {r['win_rate']:.1f}%{'':4} "
              f"{r['return_pct']:+.1f}%{'':4} {r['max_dd']:.1f}%{'':4} {r['sharpe']:.3f}")

    print(f"\nCSV files exported to: {output_dir}")


if __name__ == "__main__":
    main()
