#!/usr/bin/env python3
"""WickTrader Bot Runner.

Entry point for running the WickTrader live trading bot.

Usage:
    python -m bot.run_bot --strategy backtest-winner  # Best tested config
    python -m bot.run_bot --strategy safe             # Conservative
    python -m bot.run_bot --strategy aggressive       # Higher risk
    python -m bot.run_bot --strategy degen            # Maximum risk
"""

import asyncio
import argparse
import signal
import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import yaml
from bot.wick_bot import WickTraderBot, BotConfig
from utils.logger import get_logger, setup_logger

# Initialize logging
setup_logger(log_level="INFO")
logger = get_logger("bot_runner")


# =============================================================================
# CURATED STRATEGY PRESETS (Based on REAL 864-variant backtest)
# =============================================================================
# Source: reports/REAL_BACKTEST_REPORT_20260109_013435.md
# Data: SOL/USDT 4H, 2190 candles (Dec 2024 - Dec 2025)
# =============================================================================
STRATEGY_PRESETS = {
    "backtest-winner": {
        "name": "Backtest Winner (Best Risk-Adjusted)",
        "description": "Rank #1 by Sharpe - 4% wick SHORT, 80% win rate, 5 trades/year",
        "return": "+49.5%",
        "max_dd": "10.6%",
        "sharpe": "17.48",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "fixed_tp",    # Fixed take profit
            "fixed_tp_pct": 15.0,       # 15% TP
            "risk_profile": "conservative",
            "direction": "short",
        }
    },
    "safe": {
        "name": "Safe Long Mode",
        "description": "Best long-only config - 5% wick, 62.5% win rate, 8 trades/year",
        "return": "+27.7%",
        "max_dd": "20.0%",
        "sharpe": "6.68",
        "settings": {
            "wick_threshold": 5.0,      # 5% wick threshold
            "exit_type": "fixed_tp",    # Fixed take profit
            "fixed_tp_pct": 10.0,       # 10% TP
            "risk_profile": "conservative",
            "direction": "long",
        }
    },
    "aggressive": {
        "name": "Aggressive Short Mode",
        "description": "High returns - 4% wick SHORT, 80% win rate, higher leverage",
        "return": "+216%",
        "max_dd": "29.5%",
        "sharpe": "17.48",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "fixed_tp",    # Fixed take profit
            "fixed_tp_pct": 15.0,       # 15% TP
            "risk_profile": "aggressive",
            "direction": "short",
        }
    },
    "degen": {
        "name": "Degen Short Mode",
        "description": "Maximum risk SHORT - 80% win rate but high drawdown risk",
        "return": "+380%",
        "max_dd": "39.6%",
        "sharpe": "17.48",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "fixed_tp",    # Fixed take profit
            "fixed_tp_pct": 15.0,       # 15% TP
            "risk_profile": "degen",
            "direction": "short",
        }
    },
    "long-aggressive": {
        "name": "Aggressive Long Mode",
        "description": "Best aggressive long - 5% wick, 62.5% win rate",
        "return": "+80.4%",
        "max_dd": "56.1%",
        "sharpe": "6.68",
        "settings": {
            "wick_threshold": 5.0,      # 5% wick threshold
            "exit_type": "fixed_tp",    # Fixed take profit
            "fixed_tp_pct": 10.0,       # 10% TP
            "risk_profile": "aggressive",
            "direction": "long",
        }
    },

    # =========================================================================
    # BOTH DIRECTION STRATEGIES (Higher Trade Volume - 14-16 trades/year)
    # Trades LONG on lower wicks, SHORT on upper wicks
    # =========================================================================
    "both-conservative": {
        "name": "Both Directions Conservative",
        "description": "Long+Short on wicks - 14 trades/year, 50% win rate, low risk",
        "return": "+71.4%",
        "max_dd": "27.5%",
        "sharpe": "5.41",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "time_based",  # Time-based exit
            "time_exit_bars": 40,       # 40 bars (~7 days)
            "risk_profile": "conservative",
            "direction": "both",
        }
    },
    "both-moderate": {
        "name": "Both Directions Moderate",
        "description": "Long+Short on wicks - 14 trades/year, 50% win rate, balanced",
        "return": "+121.1%",
        "max_dd": "40.3%",
        "sharpe": "5.41",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "time_based",  # Time-based exit
            "time_exit_bars": 40,       # 40 bars (~7 days)
            "risk_profile": "moderate",
            "direction": "both",
        }
    },
    "both-aggressive": {
        "name": "Both Directions Aggressive",
        "description": "Long+Short on wicks - 14 trades/year, 50% win rate, high returns",
        "return": "+225.9%",
        "max_dd": "63.3%",
        "sharpe": "5.41",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "time_based",  # Time-based exit
            "time_exit_bars": 40,       # 40 bars (~7 days)
            "risk_profile": "aggressive",
            "direction": "both",
        }
    },
    "both-degen": {
        "name": "Both Directions Degen",
        "description": "Long+Short on wicks - 14 trades/year, 50% win rate, max leverage",
        "return": "+265.8%",
        "max_dd": "78.4%",
        "sharpe": "5.41",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "time_based",  # Time-based exit
            "time_exit_bars": 40,       # 40 bars (~7 days)
            "risk_profile": "degen",
            "direction": "both",
        }
    },
    "active-trader": {
        "name": "Active Trader (Most Trades)",
        "description": "Long+Short - 16 trades/year, 50% win rate, time_30 exit",
        "return": "+93.7%",
        "max_dd": "39.5%",
        "sharpe": "4.50",
        "settings": {
            "wick_threshold": 4.0,      # 4% wick threshold
            "exit_type": "time_based",  # Time-based exit
            "time_exit_bars": 30,       # 30 bars (~5 days)
            "risk_profile": "moderate",
            "direction": "both",
        }
    },
}


def print_strategy_menu():
    """Print available strategy presets."""
    print("\n" + "=" * 70)
    print("  AVAILABLE STRATEGY PRESETS (from REAL 864-variant backtest)")
    print("=" * 70)

    for key, preset in STRATEGY_PRESETS.items():
        print(f"\n  [{key}]")
        print(f"    {preset['name']}")
        print(f"    {preset['description']}")
        print(f"    Return: {preset['return']} | Max DD: {preset['max_dd']} | Sharpe: {preset['sharpe']}")
        s = preset['settings']
        exit_desc = f"{s['exit_type']}"
        if s['exit_type'] == 'fixed_tp':
            exit_desc = f"fixed {s.get('fixed_tp_pct', 12)}% TP"
        elif s['exit_type'] == 'rr_ratio':
            exit_desc = f"R:R {s.get('rr_ratio', 2)}:1"
        elif s['exit_type'] == 'time_based':
            exit_desc = f"time {s.get('time_exit_bars', 30)} bars"
        print(f"    Config: {s['wick_threshold']}% wick | {exit_desc} | {s['risk_profile']}")

    print("\n" + "=" * 70)
    print("  Usage: python -m bot.run_bot --strategy backtest-winner")
    print("         python -m bot.run_bot --strategy safe")
    print("         python -m bot.run_bot --strategy aggressive")
    print("         python -m bot.run_bot --strategy degen")
    print("=" * 70 + "\n")


def apply_strategy_preset(config: BotConfig, preset_name: str) -> BotConfig:
    """Apply a strategy preset to the config."""
    if preset_name not in STRATEGY_PRESETS:
        print(f"Unknown strategy: {preset_name}")
        print_strategy_menu()
        raise ValueError(f"Unknown strategy preset: {preset_name}")

    logger.info(f"Applying strategy preset: {preset_name} (overrides YAML config values)")

    preset = STRATEGY_PRESETS[preset_name]
    settings = preset['settings']

    config.wick_threshold = settings['wick_threshold']
    config.exit_type = settings['exit_type']
    config.risk_profile = settings['risk_profile']
    config.direction = settings['direction']

    # Apply exit-specific settings
    if 'fixed_tp_pct' in settings:
        config.fixed_tp_pct = settings['fixed_tp_pct']
    if 'rr_ratio' in settings:
        config.rr_ratio = settings['rr_ratio']
    if 'time_exit_bars' in settings:
        config.time_exit_bars = settings['time_exit_bars']

    return config


def load_credentials(exchange_type: str = "binance", testnet: bool = True) -> tuple:
    """Load API credentials from config.

    Args:
        exchange_type: Exchange name ('binance' or 'bybit')
        testnet: Whether to use testnet config

    Returns:
        Tuple of (api_key, api_secret)
    """
    # Determine config file based on exchange
    config_name = f"{exchange_type}_testnet.yaml" if testnet else f"{exchange_type}_mainnet.yaml"
    config_path = project_root / "config" / config_name

    if not config_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {config_path}\n"
            f"Create config/{config_name} with:\n"
            "  exchange:\n"
            "    api_key: your_api_key\n"
            "    api_secret: your_api_secret"
        )

    with open(config_path, 'r') as f:
        creds = yaml.safe_load(f)

    # Handle nested structure (under 'exchange' key) or flat structure
    if 'exchange' in creds:
        exchange = creds['exchange']
        return exchange.get('api_key', ''), exchange.get('api_secret', '')
    return creds.get('api_key', ''), creds.get('api_secret', '')


def create_default_config() -> BotConfig:
    """Create default bot configuration."""
    return BotConfig(
        symbol="SOL",
        timeframe="4h",
        wick_threshold=5.0,
        direction="long",
        exit_type="time_based",
        time_exit_bars=30,
        fixed_tp_pct=15.0,
        rr_ratio=2.0,
        risk_profile="moderate",
        use_wick_sl=True,
        sl_buffer_pct=0.1,
        cooldown_bars=1,
        check_interval_seconds=60,
        paper_trade=True
    )


async def run_bot(config: BotConfig, testnet: bool = True, exchange_type: str = "binance") -> None:
    """Run the trading bot.

    Args:
        config: Bot configuration
        testnet: Use testnet if True
        exchange_type: Exchange to use ('binance' or 'bybit')
    """
    # Load credentials
    api_key, api_secret = load_credentials(exchange_type, testnet)

    if not api_key or not api_secret:
        raise ValueError("API credentials not configured")

    # Create and start bot
    bot = WickTraderBot(
        config=config,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        exchange_type=exchange_type
    )

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(bot.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt - shutting down")
        await bot.stop()
    finally:
        status = bot.get_status()
        logger.info("Final status:")
        logger.info(f"  Signals detected: {status['stats']['signals_detected']}")
        logger.info(f"  Trades taken: {status['stats']['trades_taken']}")
        logger.info(f"  Win/Loss: {status['stats']['trades_won']}/{status['stats']['trades_lost']}")
        logger.info(f"  Total PnL: ${status['stats']['total_pnl']:+.2f}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WickTrader Live Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategy Presets (recommended):
  --strategy backtest-winner  Best Sharpe SHORT, +49.5%, 10.6% DD
  --strategy safe             Conservative LONG, +27.7%, 20% DD
  --strategy aggressive       Aggressive SHORT, +216%, 29.5% DD
  --strategy degen            Max risk SHORT, +380%, 39.6% DD

Exchanges:
  --exchange binance          Use Binance Futures (default)
  --exchange bybit            Use Bybit Perpetuals

Examples:
  python -m bot.run_bot --strategy backtest-winner     # Binance (default)
  python -m bot.run_bot --strategy safe --exchange bybit  # Bybit
  python -m bot.run_bot --strategies                   # Show all presets

Manual override (advanced):
  python -m bot.run_bot --threshold 6.0 --exit rr_ratio --profile moderate
        """
    )

    # Strategy presets (recommended)
    parser.add_argument(
        "--strategy", "-s", type=str,
        choices=list(STRATEGY_PRESETS.keys()),
        help="Use a tested strategy preset (recommended)"
    )
    parser.add_argument(
        "--strategies", action="store_true",
        help="Show available strategy presets and exit"
    )

    # Exchange selection
    parser.add_argument(
        "--exchange", "-e", type=str,
        choices=["binance", "bybit"],
        default="binance",
        help="Exchange to use (default: binance)"
    )

    # Trading mode
    parser.add_argument(
        "--paper", action="store_true", default=True,
        help="Paper trading mode (default)"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Live trading mode (REAL MONEY)"
    )
    parser.add_argument(
        "--testnet", action="store_true", default=True,
        help="Use testnet (default)"
    )
    parser.add_argument(
        "--mainnet", action="store_true",
        help="Use mainnet"
    )

    # Manual overrides (advanced)
    parser.add_argument(
        "--profile", type=str,
        choices=["conservative", "moderate", "aggressive", "degen"],
        help="Risk profile (overrides strategy preset)"
    )
    parser.add_argument(
        "--threshold", type=float,
        help="Wick threshold percentage (overrides strategy preset)"
    )
    parser.add_argument(
        "--exit", type=str,
        choices=["fixed_tp", "rr_ratio", "time_based", "trailing"],
        help="Exit strategy (overrides strategy preset)"
    )
    parser.add_argument(
        "--config", type=str,
        help="Path to YAML config file"
    )

    args = parser.parse_args()

    # Show strategies menu if requested
    if args.strategies:
        print_strategy_menu()
        return

    # Determine trading mode
    paper_trade = not args.live
    testnet = not args.mainnet

    if args.live and not args.mainnet:
        logger.warning("Live trading on testnet - no real money at risk")

    if args.live and args.mainnet:
        logger.warning("=" * 60)
        logger.warning("LIVE TRADING ON MAINNET - REAL MONEY AT RISK!")
        logger.warning("=" * 60)

        confirm = input("Type 'I UNDERSTAND' to continue: ")
        if confirm != "I UNDERSTAND":
            logger.info("Aborted")
            return

    # Create config
    if args.config:
        config = BotConfig.from_yaml(args.config)
    else:
        config = create_default_config()

    # Apply strategy preset if specified
    strategy_name = None
    if args.strategy:
        config = apply_strategy_preset(config, args.strategy)
        strategy_name = args.strategy
        preset = STRATEGY_PRESETS[args.strategy]
        print(f"\n  Using strategy preset: [{args.strategy}]")
        print(f"  {preset['name']}")
        print(f"  Expected: {preset['return']} return, {preset['max_dd']} max DD\n")

    # Manual overrides (only apply if explicitly set)
    config.paper_trade = paper_trade
    if args.profile:
        config.risk_profile = args.profile
    if args.threshold:
        config.wick_threshold = args.threshold
    if args.exit:
        config.exit_type = args.exit

    # Get exchange type
    exchange_type = args.exchange

    # Print config
    print("=" * 60)
    print("WickTrader Bot Configuration")
    print("=" * 60)
    if strategy_name:
        print(f"  Strategy:      {strategy_name}")
    print(f"  Exchange:      {exchange_type.upper()}")
    print(f"  Mode:          {'PAPER' if paper_trade else 'LIVE'}")
    print(f"  Network:       {'Testnet' if testnet else 'MAINNET'}")
    print(f"  Symbol:        {config.symbol}/USDT")
    print(f"  Timeframe:     {config.timeframe}")
    print(f"  Wick threshold: {config.wick_threshold}%")
    print(f"  Risk profile:  {config.risk_profile}")
    print(f"  Exit strategy: {config.exit_type}")
    print(f"  Direction:     {config.direction}")
    print("=" * 60 + "\n")

    # Run bot
    asyncio.run(run_bot(config, testnet=testnet, exchange_type=exchange_type))


if __name__ == "__main__":
    main()
