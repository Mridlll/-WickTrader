#!/usr/bin/env python3
"""WickTrader Bot Runner.

Entry point for running the WickTrader live trading bot.

Usage:
    python -m bot.run_bot --config config/bot.yaml
    python -m bot.run_bot --paper  # Paper trading mode (default)
    python -m bot.run_bot --live   # Live trading mode (caution!)
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
from utils.logger import get_logger

logger = get_logger("bot_runner")


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
Examples:
  python -m bot.run_bot --paper           # Paper trading (safe)
  python -m bot.run_bot --paper --profile conservative
  python -m bot.run_bot --live --profile moderate  # Real trading

Risk Profiles:
  conservative: 3% risk, 3x leverage, 30% max heat
  moderate:     5% risk, 5x leverage, 50% max heat
  aggressive:  10% risk, 7x leverage, 70% max heat
  degen:       15% risk, 10x leverage, 90% max heat
        """
    )

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
    parser.add_argument(
        "--profile", type=str, default="moderate",
        choices=["conservative", "moderate", "aggressive", "degen"],
        help="Risk profile (default: moderate)"
    )
    parser.add_argument(
        "--threshold", type=float, default=5.0,
        help="Wick threshold percentage (default: 5.0)"
    )
    parser.add_argument(
        "--exit", type=str, default="time_based",
        choices=["fixed_tp", "rr_ratio", "time_based", "trailing"],
        help="Exit strategy (default: time_based)"
    )
    parser.add_argument(
        "--config", type=str,
        help="Path to YAML config file"
    )

    args = parser.parse_args()

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

    # Override with CLI args
    config.paper_trade = paper_trade
    config.risk_profile = args.profile
    config.wick_threshold = args.threshold
    config.exit_type = args.exit

    # Print config
    print("\n" + "=" * 60)
    print("WickTrader Bot Configuration")
    print("=" * 60)
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
