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
# CURATED STRATEGY PRESETS (Based on 480-variant backtest)
# =============================================================================
# Source: README.md Top 10 Configurations by Sharpe Ratio
# =============================================================================
STRATEGY_PRESETS = {
    "backtest-winner": {
        "name": "Backtest Winner (Best Sharpe)",
        "description": "Rank #1 from 480-variant grid search - highest Sharpe ratio",
        "return": "+211%",
        "max_dd": "14.9%",
        "sharpe": "1.289",
        "settings": {
            "wick_threshold": 7.0,      # 7% wick threshold
            "exit_type": "fixed_tp",    # Fixed take profit
            "fixed_tp_pct": 12.0,       # 12% TP
            "risk_profile": "conservative",
            "direction": "long",
        }
    },
    "safe": {
        "name": "Safe Mode",
        "description": "Conservative risk with solid returns - Rank #9",
        "return": "+150%",
        "max_dd": "8.6%",
        "sharpe": "1.001",
        "settings": {
            "wick_threshold": 6.0,      # 6% wick threshold
            "exit_type": "rr_ratio",    # Risk:Reward exit
            "rr_ratio": 2.0,            # 2:1 R:R
            "risk_profile": "conservative",
            "direction": "long",
        }
    },
    "aggressive": {
        "name": "Aggressive Mode",
        "description": "High returns for experienced traders - Rank #5",
        "return": "+717%",
        "max_dd": "31.6%",
        "sharpe": "1.093",
        "settings": {
            "wick_threshold": 6.0,      # 6% wick threshold
            "exit_type": "time_based",  # Time-based exit
            "time_exit_bars": 40,       # 40 bars (160 hours)
            "risk_profile": "aggressive",
            "direction": "long",
        }
    },
    "degen": {
        "name": "Degen Mode",
        "description": "Maximum risk - Rank #3 (can 20x or lose 70%+)",
        "return": "+1,919%",
        "max_dd": "40.7%",
        "sharpe": "1.224",
        "settings": {
            "wick_threshold": 7.0,      # 7% wick threshold
            "exit_type": "rr_ratio",    # Risk:Reward exit
            "rr_ratio": 3.0,            # 3:1 R:R
            "risk_profile": "degen",
            "direction": "long",
        }
    },
}


def print_strategy_menu():
    """Print available strategy presets."""
    print("\n" + "=" * 70)
    print("  AVAILABLE STRATEGY PRESETS (from 480-variant backtest)")
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


def load_credentials(testnet: bool = True) -> tuple:
    """Load API credentials from config."""
    config_path = project_root / "config" / "binance_testnet.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {config_path}\n"
            "Create config/binance_testnet.yaml with:\n"
            "  api_key: your_api_key\n"
            "  api_secret: your_api_secret"
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


async def run_bot(config: BotConfig, testnet: bool = True) -> None:
    """Run the trading bot."""
    # Load credentials
    api_key, api_secret = load_credentials(testnet)

    if not api_key or not api_secret:
        raise ValueError("API credentials not configured")

    # Create and start bot
    bot = WickTraderBot(
        config=config,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet
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
  --strategy backtest-winner  Best Sharpe (1.289), +211%, 14.9% DD
  --strategy safe             Conservative, +150%, 8.6% DD
  --strategy aggressive       High returns, +717%, 31.6% DD
  --strategy degen            Max risk, +1919%, 40.7% DD

Examples:
  python -m bot.run_bot --strategy backtest-winner     # Best tested config
  python -m bot.run_bot --strategy safe                # Conservative
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
        help="Use Binance testnet (default)"
    )
    parser.add_argument(
        "--mainnet", action="store_true",
        help="Use Binance mainnet"
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

    # Print config
    print("=" * 60)
    print("WickTrader Bot Configuration")
    print("=" * 60)
    if strategy_name:
        print(f"  Strategy:      {strategy_name}")
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
    asyncio.run(run_bot(config, testnet=testnet))


if __name__ == "__main__":
    main()
