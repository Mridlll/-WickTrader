#!/usr/bin/env python3
"""
WickTrader - Production Runner

A production-grade wrapper that provides:
- Automatic restart on crash with exponential backoff
- Watchdog to detect frozen bot
- Graceful shutdown on SIGTERM/SIGINT
- Discord notifications for all events
- State persistence across restarts
- Heartbeat monitoring

Usage:
    python run_production.py --strategy backtest-winner
    python run_production.py --strategy safe --max-restarts 5
"""

import asyncio
import signal
import sys
import os
import time
import json
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import yaml
from bot.wick_bot import WickTraderBot, BotConfig
from bot.run_bot import STRATEGY_PRESETS, apply_strategy_preset, create_default_config
from utils.logger import setup_logger, get_logger

# Setup logging
Path("logs").mkdir(exist_ok=True)
setup_logger(log_level="INFO", log_file="logs/production.log")
logger = get_logger("production")


@dataclass
class RunnerState:
    """Persistent state for the production runner."""
    started_at: str
    restart_count: int
    last_crash_at: Optional[str]
    last_crash_reason: Optional[str]
    total_uptime_seconds: float
    successful_restarts: int
    signals_detected: int
    trades_taken: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RunnerState':
        return cls(**data)

    @classmethod
    def new(cls) -> 'RunnerState':
        return cls(
            started_at=datetime.now(timezone.utc).isoformat(),
            restart_count=0,
            last_crash_at=None,
            last_crash_reason=None,
            total_uptime_seconds=0,
            successful_restarts=0,
            signals_detected=0,
            trades_taken=0
        )


class Watchdog:
    """
    Watchdog to detect stuck/frozen bot and trigger restart.

    For 4H timeframe, we need longer thresholds since signals are rare.
    """

    HEARTBEAT_FILE = Path("data/heartbeat.txt")

    def __init__(
        self,
        stale_threshold_seconds: int = 900,  # 15 minutes
        check_interval_seconds: int = 60,     # Check every minute
        startup_grace_seconds: int = 120,     # 2 minute grace period
        on_stale_callback=None
    ):
        self.stale_threshold = stale_threshold_seconds
        self.check_interval = check_interval_seconds
        self.startup_grace = startup_grace_seconds
        self.on_stale_callback = on_stale_callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None

    def start(self):
        """Start the watchdog monitor thread."""
        self._running = True
        self._start_time = time.time()
        # Clear stale heartbeat file on startup
        if self.HEARTBEAT_FILE.exists():
            self.HEARTBEAT_FILE.unlink()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"Watchdog started (stale threshold: {self.stale_threshold}s)")

    def stop(self):
        """Stop the watchdog."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Watchdog stopped")

    def _monitor_loop(self):
        """Monitor loop running in background thread."""
        while self._running:
            try:
                if self._is_heartbeat_stale():
                    logger.warning("WATCHDOG: Heartbeat is stale - bot appears frozen!")
                    if self.on_stale_callback:
                        self.on_stale_callback()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")

            time.sleep(self.check_interval)

    def _is_heartbeat_stale(self) -> bool:
        """Check if heartbeat file is stale."""
        # Check grace period
        if self._start_time and (time.time() - self._start_time) < self.startup_grace:
            return False

        if not self.HEARTBEAT_FILE.exists():
            return False

        try:
            content = self.HEARTBEAT_FILE.read_text()
            lines = content.strip().split('\n')
            if not lines:
                return True

            timestamp_str = lines[0]
            heartbeat_time = datetime.fromisoformat(timestamp_str)

            now = datetime.now(timezone.utc)
            if heartbeat_time.tzinfo is None:
                heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)

            age_seconds = (now - heartbeat_time).total_seconds()

            if age_seconds > self.stale_threshold:
                logger.warning(f"Heartbeat age: {age_seconds:.0f}s (threshold: {self.stale_threshold}s)")
                return True

            return False

        except Exception as e:
            logger.warning(f"Error reading heartbeat: {e}")
            return False


class ProductionRunner:
    """
    Production-grade wrapper for WickTrader Bot.

    Features:
    - Auto-restart on crash with exponential backoff
    - Watchdog for detecting frozen bot
    - State persistence
    - Discord notifications
    """

    # Backoff schedule (seconds): 30s, 1m, 2m, 5m, 10m
    BACKOFF_SCHEDULE = [30, 60, 120, 300, 600]

    STATE_FILE = "data/runner_state.json"

    def __init__(
        self,
        strategy: str = "backtest-winner",
        max_restarts: int = 10,
        testnet: bool = True
    ):
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.testnet = testnet

        # Bot instance
        self.bot: Optional[WickTraderBot] = None
        self.config: Optional[BotConfig] = None

        # Discord notifier
        self.discord = None
        try:
            from notifications.discord import DiscordNotifier
            self.discord = DiscordNotifier()
        except Exception:
            pass

        # State
        self.state = self._load_state()
        self.shutdown_requested = False
        self.is_crashed = False
        self.start_time: Optional[float] = None

        # Watchdog
        self.watchdog = Watchdog(
            stale_threshold_seconds=900,  # 15 minutes
            check_interval_seconds=60,
            on_stale_callback=self._handle_watchdog_timeout
        )

        # Setup signal handlers
        self._setup_signals()

    def _setup_signals(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

        if sys.platform == 'win32':
            try:
                signal.signal(signal.SIGBREAK, self._handle_shutdown_signal)
            except (AttributeError, ValueError):
                pass

        logger.info("Signal handlers configured")

    def _handle_shutdown_signal(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} - initiating graceful shutdown")
        self.shutdown_requested = True

        if self.bot:
            self.bot.state = "stopped"

    def _handle_watchdog_timeout(self):
        """Handle watchdog timeout - bot appears frozen."""
        logger.error("WATCHDOG TIMEOUT: Bot is frozen, forcing restart...")
        self.state.last_crash_reason = "Watchdog timeout - bot frozen"
        self.state.last_crash_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        self.is_crashed = True

        # Notify
        if self.discord:
            asyncio.run(self.discord.send_message(
                title="Bot Frozen - Restarting",
                message="Watchdog detected frozen bot. Forcing restart...",
                color=0xFF0000
            ))

        # Force exit
        logger.error("Forcing process exit for restart...")
        os._exit(1)

    def _load_state(self) -> RunnerState:
        """Load state from file or create new."""
        state_path = Path(self.STATE_FILE)
        if state_path.exists():
            try:
                with open(state_path, 'r') as f:
                    data = json.load(f)
                    state = RunnerState.from_dict(data)
                    logger.info(f"Loaded state: {state.restart_count} previous restarts")
                    return state
            except Exception as e:
                logger.warning(f"Could not load state: {e}")

        return RunnerState.new()

    def _save_state(self):
        """Save state to file."""
        state_path = Path(self.STATE_FILE)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(state_path, 'w') as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save state: {e}")

    def _load_credentials(self) -> tuple:
        """Load API credentials from config."""
        config_path = project_root / "config" / "binance_testnet.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {config_path}")

        with open(config_path, 'r') as f:
            creds = yaml.safe_load(f)

        if 'exchange' in creds:
            exchange = creds['exchange']
            return exchange.get('api_key', ''), exchange.get('api_secret', '')
        return creds.get('api_key', ''), creds.get('api_secret', '')

    async def _run_bot_instance(self) -> bool:
        """
        Run a single bot instance.

        Returns:
            True if shutdown was graceful, False if crashed
        """
        self.start_time = time.time()

        try:
            # Load credentials
            api_key, api_secret = self._load_credentials()
            if not api_key or not api_secret:
                raise ValueError("API credentials not configured")

            # Create config with strategy preset
            self.config = create_default_config()
            self.config = apply_strategy_preset(self.config, self.strategy)
            self.config.paper_trade = True  # Always paper trade in production runner for safety

            # Create bot
            self.bot = WickTraderBot(
                config=self.config,
                api_key=api_key,
                api_secret=api_secret,
                testnet=self.testnet
            )

            # Add heartbeat to bot
            self.bot._heartbeat_file = Path("data/heartbeat.txt")
            self.bot._update_heartbeat = lambda: self._update_heartbeat()

            # Notify startup
            if self.discord:
                await self.discord.send_message(
                    title="WickTrader Production Started",
                    message=f"**Strategy:** {self.strategy}\n"
                            f"**Restart count:** {self.state.restart_count}\n"
                            f"**Testnet:** {self.testnet}",
                    color=0x00FF00
                )

            # Start bot
            await self.bot.start()

            return True

        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
            return True

        except Exception as e:
            logger.error(f"Bot crashed: {e}", exc_info=True)
            self.state.last_crash_at = datetime.now(timezone.utc).isoformat()
            self.state.last_crash_reason = str(e)
            self.is_crashed = True
            return False

        finally:
            if self.start_time:
                self.state.total_uptime_seconds += time.time() - self.start_time

            if self.bot:
                self.state.signals_detected += self.bot.stats.get("signals_detected", 0)
                self.state.trades_taken += self.bot.stats.get("trades_taken", 0)
                await self.bot.stop()

    def _update_heartbeat(self):
        """Update heartbeat file."""
        heartbeat_file = Path("data/heartbeat.txt")
        try:
            heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            heartbeat_file.write_text(
                f"{now.isoformat()}\n"
                f"strategy={self.strategy}\n"
                f"restarts={self.state.restart_count}\n"
            )
        except Exception as e:
            logger.warning(f"Failed to update heartbeat: {e}")

    async def run(self):
        """Run the production wrapper with auto-restart."""
        logger.info("=" * 60)
        logger.info("WickTrader - Production Runner")
        logger.info("=" * 60)
        logger.info(f"Strategy: {self.strategy}")
        logger.info(f"Max restarts: {self.max_restarts}")
        logger.info(f"Testnet: {self.testnet}")
        logger.info("=" * 60)

        # Start watchdog
        self.watchdog.start()

        while not self.shutdown_requested:
            # Check restart limit
            if self.state.restart_count >= self.max_restarts:
                logger.error(f"Max restarts ({self.max_restarts}) exceeded. Giving up.")
                if self.discord:
                    await self.discord.send_message(
                        title="Bot Stopped - Max Restarts",
                        message=f"Exceeded {self.max_restarts} restarts. Manual intervention required.",
                        color=0xFF0000
                    )
                break

            # Run bot
            self.is_crashed = False
            graceful = await self._run_bot_instance()

            if self.shutdown_requested:
                logger.info("Graceful shutdown completed.")
                break

            if not graceful:
                # Crash handling
                self.state.restart_count += 1
                self._save_state()

                # Calculate backoff
                backoff_idx = min(self.state.restart_count - 1, len(self.BACKOFF_SCHEDULE) - 1)
                backoff = self.BACKOFF_SCHEDULE[backoff_idx]

                logger.warning(f"Crash #{self.state.restart_count}. Restarting in {backoff}s...")

                if self.discord:
                    await self.discord.send_message(
                        title="Bot Crashed - Restarting",
                        message=f"**Crash #{self.state.restart_count}**\n"
                                f"**Reason:** {self.state.last_crash_reason}\n"
                                f"**Restart in:** {backoff}s",
                        color=0xFFA500
                    )

                await asyncio.sleep(backoff)

                if not self.shutdown_requested:
                    self.state.successful_restarts += 1
                    self._save_state()
                    logger.info(f"Restarting bot (attempt {self.state.restart_count + 1})...")

        # Stop watchdog
        self.watchdog.stop()

        # Final state save
        self._save_state()

        logger.info("=" * 60)
        logger.info("Production Runner Shutdown Summary")
        logger.info(f"  Total uptime: {self.state.total_uptime_seconds:.0f}s")
        logger.info(f"  Restart count: {self.state.restart_count}")
        logger.info(f"  Signals detected: {self.state.signals_detected}")
        logger.info(f"  Trades taken: {self.state.trades_taken}")
        logger.info("=" * 60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='WickTrader - Production Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategy Presets:
  backtest-winner  Best Sharpe (1.289), +211%, 14.9% DD
  safe             Conservative, +150%, 8.6% DD
  aggressive       High returns, +717%, 31.6% DD
  degen            Max risk, +1919%, 40.7% DD

Examples:
  python run_production.py --strategy backtest-winner
  python run_production.py --strategy safe --max-restarts 5
        """
    )
    parser.add_argument(
        '--strategy', '-s',
        default='backtest-winner',
        choices=list(STRATEGY_PRESETS.keys()),
        help='Strategy preset (default: backtest-winner)'
    )
    parser.add_argument(
        '--max-restarts', '-m',
        type=int,
        default=10,
        help='Maximum automatic restarts (default: 10)'
    )
    parser.add_argument(
        '--mainnet',
        action='store_true',
        help='Use mainnet (default: testnet)'
    )
    parser.add_argument(
        '--reset-state',
        action='store_true',
        help='Reset runner state'
    )

    args = parser.parse_args()

    # Create runner
    runner = ProductionRunner(
        strategy=args.strategy,
        max_restarts=args.max_restarts,
        testnet=not args.mainnet
    )

    if args.reset_state:
        runner.state = RunnerState.new()
        runner._save_state()
        logger.info("Runner state reset")

    # Run
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    sys.exit(0)


if __name__ == "__main__":
    main()
