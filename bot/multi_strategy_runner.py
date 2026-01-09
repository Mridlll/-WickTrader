#!/usr/bin/env python3
"""Multi-Strategy Runner for WickTrader.

Run multiple strategies concurrently on separate Binance subaccounts.

Usage:
    python -m bot.multi_strategy_runner                    # Run all enabled strategies
    python -m bot.multi_strategy_runner --status           # Show status
    python -m bot.multi_strategy_runner --start safe       # Start specific strategy
    python -m bot.multi_strategy_runner --stop aggressive  # Stop specific strategy
"""

import asyncio
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

import yaml

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from bot.wick_bot import WickTraderBot, BotConfig
from bot.run_bot import STRATEGY_PRESETS, apply_strategy_preset, create_default_config
from utils.logger import get_logger, setup_logger

setup_logger(log_level="INFO")
logger = get_logger("multi_strategy")


class StrategyStatus(str, Enum):
    """Strategy instance status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class StrategyInstance:
    """Represents a running strategy instance."""
    name: str
    config: BotConfig
    api_key: str
    api_secret: str
    testnet: bool
    enabled: bool
    bot: Optional[WickTraderBot] = None
    task: Optional[asyncio.Task] = None
    status: StrategyStatus = StrategyStatus.STOPPED
    error_message: str = ""
    started_at: Optional[datetime] = None
    stats: Dict[str, Any] = field(default_factory=dict)


class MultiStrategyRunner:
    """Run multiple strategies concurrently on separate subaccounts."""

    def __init__(self, config_path: str = None):
        """Initialize multi-strategy runner.

        Args:
            config_path: Path to strategies.yaml config file
        """
        if config_path is None:
            config_path = str(project_root / "config" / "strategies.yaml")

        self.config_path = config_path
        self.strategies: Dict[str, StrategyInstance] = {}
        self.global_config: Dict[str, Any] = {}
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None

        self._load_config()

    def _load_config(self) -> None:
        """Load strategy configurations from YAML."""
        config_path = Path(self.config_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Strategy config not found: {config_path}\n"
                "Run 'python setup_subaccounts.py' to create configuration."
            )

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Load global settings
        self.global_config = config.get('global', {})

        # Load strategy configurations
        strategies_config = config.get('strategies', {})

        for name, strategy_config in strategies_config.items():
            if name not in STRATEGY_PRESETS:
                logger.warning(f"Unknown strategy preset: {name}, skipping")
                continue

            subaccount = strategy_config.get('subaccount', {})

            # Create bot config for this strategy
            bot_config = create_default_config()
            bot_config = apply_strategy_preset(bot_config, name)
            bot_config.paper_trade = True  # Always paper until explicitly set

            # Create strategy instance
            instance = StrategyInstance(
                name=name,
                config=bot_config,
                api_key=subaccount.get('api_key', ''),
                api_secret=subaccount.get('api_secret', ''),
                testnet=subaccount.get('testnet', True),
                enabled=strategy_config.get('enabled', False)
            )

            self.strategies[name] = instance

        logger.info(f"Loaded {len(self.strategies)} strategy configurations")
        enabled_count = sum(1 for s in self.strategies.values() if s.enabled)
        logger.info(f"  Enabled: {enabled_count}")

    def reload_config(self) -> None:
        """Reload configuration from file."""
        # Store running states
        running_strategies = {
            name: inst.status == StrategyStatus.RUNNING
            for name, inst in self.strategies.items()
        }

        self._load_config()

        # Restore running states for strategies that were running
        for name, was_running in running_strategies.items():
            if name in self.strategies and was_running:
                # Keep the existing bot instance if still running
                pass

    async def start_all(self) -> None:
        """Start all enabled strategies concurrently."""
        self._running = True

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # Start all enabled strategies
        tasks = []
        for name, instance in self.strategies.items():
            if instance.enabled:
                if not instance.api_key or not instance.api_secret:
                    logger.warning(f"[{name}] Skipping - no API credentials configured")
                    continue

                task = asyncio.create_task(self._run_strategy(instance))
                instance.task = task
                tasks.append(task)
                logger.info(f"[{name}] Starting strategy...")

        if not tasks:
            logger.warning("No strategies to start. Check config/strategies.yaml")
            return

        logger.info(f"Started {len(tasks)} strategies")

        # Wait for all strategies
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("Multi-strategy runner cancelled")

    async def start_strategy(self, name: str) -> bool:
        """Start a specific strategy.

        Args:
            name: Strategy preset name

        Returns:
            True if started successfully
        """
        if name not in self.strategies:
            logger.error(f"Unknown strategy: {name}")
            return False

        instance = self.strategies[name]

        if instance.status == StrategyStatus.RUNNING:
            logger.warning(f"[{name}] Already running")
            return True

        if not instance.api_key or not instance.api_secret:
            logger.error(f"[{name}] No API credentials configured")
            return False

        task = asyncio.create_task(self._run_strategy(instance))
        instance.task = task
        logger.info(f"[{name}] Started")
        return True

    async def stop_strategy(self, name: str) -> bool:
        """Stop a specific strategy gracefully.

        Args:
            name: Strategy preset name

        Returns:
            True if stopped successfully
        """
        if name not in self.strategies:
            logger.error(f"Unknown strategy: {name}")
            return False

        instance = self.strategies[name]

        if instance.status != StrategyStatus.RUNNING:
            logger.warning(f"[{name}] Not running")
            return True

        instance.status = StrategyStatus.STOPPING

        # Stop the bot
        if instance.bot:
            try:
                await instance.bot.stop()
            except Exception as e:
                logger.error(f"[{name}] Error stopping bot: {e}")

        # Cancel the task
        if instance.task and not instance.task.done():
            instance.task.cancel()
            try:
                await instance.task
            except asyncio.CancelledError:
                pass

        instance.status = StrategyStatus.STOPPED
        instance.bot = None
        instance.task = None
        logger.info(f"[{name}] Stopped")
        return True

    async def stop_all(self) -> None:
        """Stop all running strategies."""
        self._running = False

        # Cancel health check
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all strategies
        for name in list(self.strategies.keys()):
            if self.strategies[name].status == StrategyStatus.RUNNING:
                await self.stop_strategy(name)

        logger.info("All strategies stopped")

    async def _run_strategy(self, instance: StrategyInstance) -> None:
        """Run a single strategy instance.

        Args:
            instance: Strategy instance to run
        """
        instance.status = StrategyStatus.STARTING
        instance.started_at = datetime.now()

        try:
            # Create bot
            bot = WickTraderBot(
                config=instance.config,
                api_key=instance.api_key,
                api_secret=instance.api_secret,
                testnet=instance.testnet
            )
            instance.bot = bot
            instance.status = StrategyStatus.RUNNING

            logger.info(f"[{instance.name}] Bot initialized")
            logger.info(f"[{instance.name}]   Direction: {instance.config.direction}")
            logger.info(f"[{instance.name}]   Threshold: {instance.config.wick_threshold}%")
            logger.info(f"[{instance.name}]   Profile: {instance.config.risk_profile}")

            # Run bot
            await bot.start()

        except asyncio.CancelledError:
            logger.info(f"[{instance.name}] Cancelled")
            raise

        except Exception as e:
            instance.status = StrategyStatus.ERROR
            instance.error_message = str(e)
            logger.error(f"[{instance.name}] Error: {e}")

        finally:
            # Capture final stats
            if instance.bot:
                try:
                    instance.stats = instance.bot.get_status().get('stats', {})
                except:
                    pass

            if instance.status != StrategyStatus.ERROR:
                instance.status = StrategyStatus.STOPPED

    async def _health_check_loop(self) -> None:
        """Periodic health check for all strategies."""
        interval = self.global_config.get('health_check_interval', 60)

        while self._running:
            try:
                await asyncio.sleep(interval)

                for name, instance in self.strategies.items():
                    if instance.status == StrategyStatus.RUNNING:
                        if instance.bot:
                            status = instance.bot.get_status()
                            instance.stats = status.get('stats', {})
                            logger.debug(f"[{name}] Health: OK - {status['state']}")
                        else:
                            logger.warning(f"[{name}] Health: Bot instance missing")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all strategies.

        Returns:
            Dictionary with strategy statuses
        """
        result = {
            "running": self._running,
            "strategies": {}
        }

        for name, instance in self.strategies.items():
            preset = STRATEGY_PRESETS.get(name, {})

            strategy_status = {
                "status": instance.status.value,
                "enabled": instance.enabled,
                "has_credentials": bool(instance.api_key and instance.api_secret),
                "testnet": instance.testnet,
                "preset": {
                    "direction": preset.get('settings', {}).get('direction', 'unknown'),
                    "expected_return": preset.get('return', 'N/A'),
                    "max_dd": preset.get('max_dd', 'N/A'),
                },
            }

            if instance.status == StrategyStatus.RUNNING:
                strategy_status["started_at"] = instance.started_at.isoformat() if instance.started_at else None
                strategy_status["stats"] = instance.stats

            if instance.status == StrategyStatus.ERROR:
                strategy_status["error"] = instance.error_message

            result["strategies"][name] = strategy_status

        return result

    def print_status(self) -> None:
        """Print formatted status of all strategies."""
        status = self.get_status()

        print("\n" + "=" * 70)
        print("  WICKTRADER MULTI-STRATEGY STATUS")
        print("=" * 70)

        for name, info in status["strategies"].items():
            status_emoji = {
                "stopped": "[OFF]",
                "running": "[ON] ",
                "starting": "[...]",
                "stopping": "[...]",
                "error": "[ERR]"
            }.get(info["status"], "[???]")

            creds = "API OK" if info["has_credentials"] else "NO API"
            network = "Testnet" if info["testnet"] else "MAINNET"

            print(f"\n  {status_emoji} {name}")
            print(f"       Direction: {info['preset']['direction'].upper()}")
            print(f"       Expected: {info['preset']['expected_return']} return, {info['preset']['max_dd']} DD")
            print(f"       Credentials: {creds} | Network: {network}")

            if info["status"] == "running" and info.get("stats"):
                stats = info["stats"]
                print(f"       Signals: {stats.get('signals_detected', 0)} | Trades: {stats.get('trades_taken', 0)}")

            if info["status"] == "error":
                print(f"       Error: {info.get('error', 'Unknown')}")

        print("\n" + "=" * 70)


async def main():
    """Main entry point for multi-strategy runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="WickTrader Multi-Strategy Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m bot.multi_strategy_runner                    # Run all enabled
  python -m bot.multi_strategy_runner --status           # Show status
  python -m bot.multi_strategy_runner --start safe       # Start one
  python -m bot.multi_strategy_runner --stop aggressive  # Stop one
        """
    )

    parser.add_argument(
        "--status", action="store_true",
        help="Show status of all strategies and exit"
    )
    parser.add_argument(
        "--start", type=str, metavar="STRATEGY",
        help="Start a specific strategy"
    )
    parser.add_argument(
        "--stop", type=str, metavar="STRATEGY",
        help="Stop a specific strategy"
    )
    parser.add_argument(
        "--config", type=str,
        help="Path to strategies.yaml config file"
    )

    args = parser.parse_args()

    # Create runner
    try:
        runner = MultiStrategyRunner(config_path=args.config)
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("\nRun 'python setup_subaccounts.py' to configure strategies.")
        return

    # Status mode
    if args.status:
        runner.print_status()
        return

    # Setup shutdown handler
    def shutdown():
        logger.info("Shutdown signal received")
        asyncio.create_task(runner.stop_all())

    # Handle signals (Unix)
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            pass  # Windows

    # Run
    try:
        if args.start:
            await runner.start_strategy(args.start)
            # Keep running
            while runner.strategies[args.start].status == StrategyStatus.RUNNING:
                await asyncio.sleep(1)
        elif args.stop:
            await runner.stop_strategy(args.stop)
        else:
            # Run all enabled strategies
            print("\n" + "=" * 60)
            print("  WICKTRADER MULTI-STRATEGY MODE")
            print("=" * 60)
            runner.print_status()
            print("\nStarting enabled strategies...")
            await runner.start_all()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt")
    finally:
        await runner.stop_all()

        # Print final stats
        print("\n" + "=" * 60)
        print("  FINAL STATUS")
        print("=" * 60)
        runner.print_status()


if __name__ == "__main__":
    asyncio.run(main())
