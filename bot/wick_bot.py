"""WickTrader Live Trading Bot.

Main trading bot that monitors SOL/USDT 4H candles for wick signals
and executes trades using heat-based risk management.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import yaml

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from exchanges.binance import BinanceExchange
from exchanges.bybit import BybitExchange
from exchanges.base import BaseExchange, OrderSide, OrderType, Position, PositionSide
from strategy.wick_signals import WickSignalDetector, WickSignal
from strategy.heat_risk import (
    HeatRiskManager, HeatZone, PositionHeat,
    RiskPreset, RISK_PRESETS, create_heat_manager_from_preset
)
from backtest.engine import SignalType
from utils.logger import get_logger

logger = get_logger("wick_bot")


class BotState(str, Enum):
    """Bot operational states."""
    IDLE = "idle"
    MONITORING = "monitoring"
    IN_POSITION = "in_position"
    COOLDOWN = "cooldown"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class BotConfig:
    """Bot configuration."""
    # Trading parameters
    symbol: str = "SOL"
    timeframe: str = "4h"

    # Strategy parameters
    wick_threshold: float = 5.0
    direction: str = "long"  # "long", "short", "both"

    # Exit parameters
    exit_type: str = "time_based"  # "fixed_tp", "rr_ratio", "time_based", "trailing"
    fixed_tp_pct: float = 15.0
    rr_ratio: float = 2.0
    time_exit_bars: int = 30
    time_exit_tp_pct: float = 30.0  # Large TP for time-based exits (let time decide, not price)
    trailing_activation_pct: float = 10.0
    trailing_distance_pct: float = 5.0

    # Risk parameters
    risk_profile: str = "moderate"  # conservative, moderate, aggressive, degen
    use_wick_sl: bool = True
    sl_buffer_pct: float = 0.1

    # Operational parameters
    cooldown_bars: int = 1
    check_interval_seconds: int = 60  # Check every minute
    paper_trade: bool = True  # Paper trade mode (no real orders)

    @classmethod
    def from_yaml(cls, path: str) -> "BotConfig":
        """Load config from YAML file with validation."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        config = cls()

        # Map YAML fields to config
        if 'wick' in data:
            config.wick_threshold = data['wick'].get('threshold', config.wick_threshold)

        if 'risk' in data:
            config.risk_profile = data['risk'].get('profile', config.risk_profile)

        if 'exit' in data:
            config.exit_type = data['exit'].get('strategy', config.exit_type)
            config.fixed_tp_pct = data['exit'].get('fixed_tp_pct', config.fixed_tp_pct)
            config.rr_ratio = data['exit'].get('rr_ratio', config.rr_ratio)
            config.time_exit_bars = data['exit'].get('time_bars', config.time_exit_bars)

        if 'bot' in data:
            config.paper_trade = data['bot'].get('paper_trade', config.paper_trade)
            config.check_interval_seconds = data['bot'].get('check_interval', config.check_interval_seconds)

        # Validate configuration
        config.validate()

        return config

    def validate(self) -> None:
        """Validate configuration parameters."""
        # Validate wick threshold (1.5% - 10%)
        if not 1.5 <= self.wick_threshold <= 10.0:
            raise ValueError(f"wick_threshold must be between 1.5 and 10.0, got {self.wick_threshold}")

        # Validate risk profile
        valid_profiles = ["conservative", "moderate", "aggressive", "degen"]
        if self.risk_profile not in valid_profiles:
            raise ValueError(f"risk_profile must be one of {valid_profiles}, got '{self.risk_profile}'")

        # Validate exit type
        valid_exits = ["fixed_tp", "rr_ratio", "time_based", "trailing"]
        if self.exit_type not in valid_exits:
            raise ValueError(f"exit_type must be one of {valid_exits}, got '{self.exit_type}'")

        # Validate direction
        valid_directions = ["long", "short", "both"]
        if self.direction not in valid_directions:
            raise ValueError(f"direction must be one of {valid_directions}, got '{self.direction}'")

        # Validate numeric ranges
        if self.fixed_tp_pct <= 0 or self.fixed_tp_pct > 50:
            raise ValueError(f"fixed_tp_pct must be between 0 and 50, got {self.fixed_tp_pct}")

        if self.rr_ratio <= 0 or self.rr_ratio > 10:
            raise ValueError(f"rr_ratio must be between 0 and 10, got {self.rr_ratio}")

        if self.time_exit_bars <= 0 or self.time_exit_bars > 100:
            raise ValueError(f"time_exit_bars must be between 1 and 100, got {self.time_exit_bars}")

        if self.check_interval_seconds < 10:
            raise ValueError(f"check_interval_seconds must be at least 10, got {self.check_interval_seconds}")


@dataclass
class ActiveTrade:
    """Active trade tracking."""
    symbol: str
    side: SignalType
    entry_price: float
    entry_time: datetime
    size: float
    stop_loss: float
    take_profit: float
    entry_bar_idx: int
    trailing_stop: Optional[float] = None
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    bars_held: int = 0


class WickTraderBot:
    """
    Live trading bot for wick-based SOL strategy.

    Features:
    - Real-time 4H candle monitoring
    - Heat-based risk management
    - Multiple exit strategies
    - Paper trading mode
    - Comprehensive logging
    """

    def __init__(
        self,
        config: BotConfig,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        exchange_type: str = "binance"
    ):
        """
        Initialize the trading bot.

        Args:
            config: Bot configuration
            api_key: Exchange API key
            api_secret: Exchange API secret
            testnet: Use testnet if True
            exchange_type: Exchange to use ('binance' or 'bybit')
        """
        self.config = config
        self.testnet = testnet
        self.exchange_type = exchange_type

        # Initialize exchange based on type
        if exchange_type == "bybit":
            self.exchange: BaseExchange = BybitExchange(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet
            )
        else:
            self.exchange: BaseExchange = BinanceExchange(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet
            )

        # Initialize signal detector
        self.signal_detector = WickSignalDetector(
            threshold=config.wick_threshold
        )

        # Initialize risk manager based on profile
        risk_preset = RiskPreset(config.risk_profile)
        self.risk_manager = create_heat_manager_from_preset(risk_preset)
        self.risk_profile = RISK_PRESETS[risk_preset]

        # State tracking
        self.state = BotState.IDLE
        self.active_trade: Optional[ActiveTrade] = None
        self.last_signal_bar: int = -100
        self.current_bar_idx: int = 0
        self.candle_history: List[Dict[str, Any]] = []

        # Statistics
        self.stats = {
            "signals_detected": 0,
            "trades_taken": 0,
            "trades_won": 0,
            "trades_lost": 0,
            "total_pnl": 0.0,
            "start_time": None,
            "last_update": None,
            "last_heartbeat": None,
            "missed_signals_checked": False
        }

        # Circuit breaker
        self._consecutive_losses = 0
        self._daily_loss = 0.0
        self._daily_loss_reset_date = datetime.now(timezone.utc).date()
        self._circuit_breaker_tripped = False
        self._max_consecutive_losses = 5
        self._max_daily_loss_pct = 10.0  # % of starting balance
        self._starting_balance = 0.0

        # Thread safety lock for trade operations
        self._trade_lock = asyncio.Lock()

        # Discord notifier (optional)
        self.discord = None
        try:
            from notifications.discord import DiscordNotifier
            self.discord = DiscordNotifier()
            if self.discord.webhook_url:
                logger.info("Discord notifications enabled")
        except Exception:
            pass  # Discord not configured

        # Heartbeat for watchdog monitoring
        self._heartbeat_file = Path("data/heartbeat.txt")
        self._last_heartbeat = datetime.now()

        logger.info(f"WickTraderBot initialized")
        logger.info(f"  Symbol: {config.symbol}")
        logger.info(f"  Timeframe: {config.timeframe}")
        logger.info(f"  Wick threshold: {config.wick_threshold}%")
        logger.info(f"  Risk profile: {config.risk_profile}")
        logger.info(f"  Paper trade: {config.paper_trade}")
        logger.info(f"  Testnet: {testnet}")

    async def start(self) -> None:
        """Start the trading bot."""
        logger.info("Starting WickTraderBot...")

        try:
            # Connect to exchange
            await self.exchange.connect()
            logger.info("Connected to Binance")

            # Get initial balance
            balance = await self.exchange.get_balance()
            logger.info(f"Account balance: ${balance.total_balance:,.2f}")
            self._starting_balance = balance.total_balance

            # Set leverage
            await self.exchange.set_leverage(
                self.config.symbol,
                self.risk_profile["leverage"]
            )
            logger.info(f"Leverage set to {self.risk_profile['leverage']}x")

            # Set margin type to cross
            await self.exchange.set_margin_type(self.config.symbol, "CROSSED")

            # Update heat manager with initial equity
            self.risk_manager.update_equity(balance.total_balance)

            # Load persisted heat state if available
            heat_state_path = project_root / "data" / "heat_state.json"
            if self.risk_manager.load_state(str(heat_state_path)):
                logger.info("Loaded persisted heat state")
            else:
                logger.info("No persisted heat state found - starting fresh")

            # Check for existing positions
            await self._check_existing_positions()

            # Load recent candle history
            await self._load_candle_history()

            # Check for missed signals (if bot was down during a signal)
            await self._check_missed_signals()

            self.stats["start_time"] = datetime.now()
            self.state = BotState.MONITORING

            logger.info("Bot started - monitoring for signals...")

            # Send startup notification
            await self._notify_startup(balance.total_balance)

            # Main loop
            await self._run_loop()

        except Exception as e:
            logger.error(f"Bot error: {e}")
            self.state = BotState.ERROR
            raise
        finally:
            await self.exchange.disconnect()
            logger.info("Bot stopped")

    async def stop(self) -> None:
        """Stop the trading bot."""
        logger.info("Stopping bot...")
        self.state = BotState.STOPPED

    async def _run_loop(self) -> None:
        """Main trading loop."""
        last_candle_time = None

        while self.state not in [BotState.STOPPED, BotState.ERROR]:
            try:
                # Get latest candle
                candles = await self.exchange.get_candles(
                    self.config.symbol,
                    self.config.timeframe,
                    limit=2  # Current + previous
                )

                if not candles:
                    logger.warning("No candles received")
                    await asyncio.sleep(self.config.check_interval_seconds)
                    continue

                current_candle = candles[-1]
                candle_time = current_candle.timestamp

                # Check if new candle closed
                if last_candle_time and candle_time != last_candle_time:
                    # Previous candle just closed - analyze it
                    closed_candle = candles[-2] if len(candles) > 1 else None

                    if closed_candle:
                        self.current_bar_idx += 1
                        await self._process_closed_candle(closed_candle)

                # Update position if we have one
                if self.active_trade:
                    await self._update_position(current_candle)

                last_candle_time = candle_time
                self.stats["last_update"] = datetime.now()

                # Update heartbeat for watchdog
                self._update_heartbeat()

                # Wait before next check - smart sleep aligned to candle boundaries
                secs_until_close = self._seconds_until_candle_close()
                if secs_until_close <= 300:  # Within 5 minutes of candle close
                    await asyncio.sleep(5)  # Poll every 5s near close
                else:
                    # Sleep most of the way, but wake up 5 min before next close
                    sleep_time = min(self.config.check_interval_seconds, secs_until_close - 300)
                    await asyncio.sleep(max(5, sleep_time))

            except asyncio.CancelledError:
                logger.info("Bot loop cancelled")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(self.config.check_interval_seconds * 2)

    async def _load_candle_history(self) -> None:
        """Load recent candle history for warmup."""
        logger.info("Loading candle history...")

        candles = await self.exchange.get_candles(
            self.config.symbol,
            self.config.timeframe,
            limit=100
        )

        self.candle_history = [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume
            }
            for c in candles
        ]

        self.current_bar_idx = len(self.candle_history)
        logger.info(f"Loaded {len(self.candle_history)} historical candles")

    async def _check_existing_positions(self) -> None:
        """Check for existing open positions."""
        position = await self.exchange.get_position(self.config.symbol)

        if position and abs(position.size) > 0:
            logger.warning(f"Found existing position: {position.size} @ {position.entry_price}")

            # Create active trade from existing position
            self.active_trade = ActiveTrade(
                symbol=position.symbol,
                side=SignalType.LONG if position.side.value == "long" else SignalType.SHORT,
                entry_price=position.entry_price,
                entry_time=datetime.now(),
                size=position.size,
                stop_loss=position.liquidation_price or (
                    position.entry_price * 0.95 if position.side == PositionSide.LONG
                    else position.entry_price * 1.05
                ),
                take_profit=position.entry_price * (1 + self.config.fixed_tp_pct / 100) if position.side == PositionSide.LONG else position.entry_price * (1 - self.config.fixed_tp_pct / 100),
                entry_bar_idx=self.current_bar_idx
            )

            self.state = BotState.IN_POSITION
            logger.info("Resuming with existing position")

    async def _check_missed_signals(self) -> None:
        """Check last few candles for any missed signals (bot was down)."""
        if self.active_trade:
            return  # Already in a position

        logger.info("Checking for missed signals...")

        # Use a temporary detector to avoid polluting the main signal history
        temp_detector = WickSignalDetector(threshold=self.config.wick_threshold)

        # Check last 3 closed candles for signals we might have missed
        recent_candles = self.candle_history[-4:-1]  # Last 3 closed (not current)

        for i, candle in enumerate(recent_candles):
            signal = temp_detector.process_bar(
                timestamp=candle["timestamp"],
                open_price=candle["open"],
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
                threshold=self.config.wick_threshold
            )

            if signal:
                hours_ago = (len(recent_candles) - i) * 4
                logger.warning(f"MISSED SIGNAL DETECTED from {hours_ago}h ago!")
                logger.warning(f"  Type: {signal.signal_type.value}")
                logger.warning(f"  Wick: {signal.wick_pct:.2f}%")
                logger.warning(f"  Entry would have been: ${signal.entry_price:.2f}")

                # Notify about missed signal
                if self.discord:
                    await self.discord.send_message(
                        title="Missed Signal Alert",
                        message=f"Bot was down during a {signal.wick_pct:.1f}% wick signal {hours_ago}h ago.\n"
                                f"Entry would have been ${signal.entry_price:.2f}.\n"
                                f"Bot is now online and monitoring.",
                        color=0xFFA500  # Orange
                    )

        self.stats["missed_signals_checked"] = True
        logger.info("Missed signal check complete")

    async def _notify_startup(self, balance: float) -> None:
        """Send startup notification."""
        if self.discord:
            await self.discord.send_message(
                title="WickTrader Bot Started",
                message=f"**Strategy:** {self.config.risk_profile}\n"
                        f"**Wick Threshold:** {self.config.wick_threshold}%\n"
                        f"**Balance:** ${balance:,.2f}\n"
                        f"**Mode:** {'Paper' if self.config.paper_trade else 'LIVE'}\n"
                        f"Monitoring SOL/USDT 4H for signals...",
                color=0x00FF00  # Green
            )

    async def _notify_signal(self, signal, action: str = "detected") -> None:
        """Send signal notification."""
        if self.discord:
            color = 0x00FF00 if action == "executed" else 0x0099FF
            stop_loss = getattr(signal, 'stop_loss', signal.candle_low)
            await self.discord.send_message(
                title=f"Wick Signal {action.title()}",
                message=f"**Type:** {signal.signal_type.value.upper()}\n"
                        f"**Wick:** {signal.wick_pct:.2f}%\n"
                        f"**Entry:** ${signal.entry_price:.2f}\n"
                        f"**Stop Loss:** ${stop_loss:.2f}",
                color=color
            )

    async def _notify_error(self, error: str) -> None:
        """Send error notification."""
        if self.discord:
            await self.discord.send_message(
                title="Bot Error",
                message=f"**Error:** {error}\n\nBot will attempt to continue.",
                color=0xFF0000  # Red
            )

    def _get_next_candle_close(self) -> datetime:
        """Calculate when the next 4H candle closes."""
        now = datetime.now(timezone.utc)

        # 4H candles close at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
        current_hour = now.hour
        next_close_hour = ((current_hour // 4) + 1) * 4

        if next_close_hour >= 24:
            next_close_hour = 0
            next_close = now.replace(hour=0, minute=0, second=5, microsecond=0) + timedelta(days=1)
        else:
            next_close = now.replace(hour=next_close_hour, minute=0, second=5, microsecond=0)

        return next_close

    def _seconds_until_candle_close(self) -> int:
        """Get seconds until next candle close."""
        next_close = self._get_next_candle_close()
        delta = (next_close - datetime.now(timezone.utc)).total_seconds()
        return max(5, int(delta))  # Minimum 5 seconds

    def _update_heartbeat(self) -> None:
        """Update heartbeat file for watchdog monitoring."""
        try:
            self._heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            self._last_heartbeat = now

            # Calculate time until next 4H candle
            next_candle = self._get_next_candle_close()
            time_until = (next_candle - datetime.now(timezone.utc)).total_seconds()

            self._heartbeat_file.write_text(
                f"{now.isoformat()}\n"
                f"state={self.state.value}\n"
                f"signals={self.stats['signals_detected']}\n"
                f"trades={self.stats['trades_taken']}\n"
                f"next_candle_in={int(time_until)}s\n"
            )
            self.stats["last_heartbeat"] = now
        except Exception as e:
            logger.warning(f"Failed to update heartbeat: {e}")

    async def _process_closed_candle(self, candle) -> None:
        """Process a newly closed candle."""
        logger.debug(
            f"Processing candle: O={candle.open:.2f} H={candle.high:.2f} "
            f"L={candle.low:.2f} C={candle.close:.2f}"
        )

        # Validate candle data
        if any(v is None or v != v for v in [candle.open, candle.high, candle.low, candle.close]):
            logger.warning("Invalid candle data (NaN/None) - skipping")
            return
        if candle.close <= 0 or candle.high <= 0 or candle.low <= 0:
            logger.warning(f"Invalid candle prices (zero/negative) - skipping")
            return

        # Add to history
        self.candle_history.append({
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume
        })

        # Keep history bounded
        if len(self.candle_history) > 500:
            self.candle_history = self.candle_history[-500:]

        # Check for exit if in position
        if self.active_trade:
            await self._check_exit_conditions(candle)
            if self.active_trade:  # Still in position (wasn't closed by exit check)
                self.active_trade.bars_held += 1
                # Check for opposite signal - close position if detected
                signal = self.signal_detector.process_bar(
                    timestamp=candle.timestamp,
                    open_price=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    threshold=self.config.wick_threshold
                )
                if signal and signal.signal_type != self.active_trade.side:
                    logger.info(f"Opposite signal detected ({signal.signal_type.value}) - closing position")
                    await self._close_position("opposite_signal", candle.close)
            return

        # Check cooldown
        bars_since_last = self.current_bar_idx - self.last_signal_bar
        if bars_since_last < self.config.cooldown_bars:
            logger.debug(f"In cooldown: {bars_since_last}/{self.config.cooldown_bars}")
            return

        # Check for entry signal
        signal = self.signal_detector.process_bar(
            timestamp=candle.timestamp,
            open_price=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            threshold=self.config.wick_threshold
        )

        if signal:
            await self._process_signal(signal, candle)

    async def _process_signal(self, signal: WickSignal, candle) -> None:
        """Process a detected wick signal."""
        # Filter by direction
        if self.config.direction == "long" and signal.signal_type != SignalType.LONG:
            return
        if self.config.direction == "short" and signal.signal_type != SignalType.SHORT:
            return

        self.stats["signals_detected"] += 1
        logger.info(
            f"SIGNAL DETECTED: {signal.signal_type.value} | "
            f"Wick: {signal.wick_pct:.2f}% | Entry: ${signal.entry_price:.2f}"
        )

        # Circuit breaker check
        if self._circuit_breaker_tripped:
            logger.warning("Signal blocked - circuit breaker is tripped (excessive losses)")
            return

        # Check heat zone
        heat_state = self.risk_manager.get_heat_state()

        if heat_state.zone == HeatZone.CRITICAL:
            logger.warning(f"Signal blocked - critical heat zone ({heat_state.current_heat:.1f}%)")
            return

        # Calculate position parameters
        is_long = signal.signal_type == SignalType.LONG

        # Stop loss
        if self.config.use_wick_sl:
            if is_long:
                stop_loss = candle.low * (1 - self.config.sl_buffer_pct / 100)
            else:
                stop_loss = candle.high * (1 + self.config.sl_buffer_pct / 100)
        else:
            sl_pct = 3.0 / 100
            if is_long:
                stop_loss = signal.entry_price * (1 - sl_pct)
            else:
                stop_loss = signal.entry_price * (1 + sl_pct)

        # Take profit
        sl_distance = abs(signal.entry_price - stop_loss)

        if self.config.exit_type == "fixed_tp":
            tp_distance = signal.entry_price * (self.config.fixed_tp_pct / 100)
        elif self.config.exit_type == "rr_ratio":
            tp_distance = sl_distance * self.config.rr_ratio
        else:
            tp_distance = signal.entry_price * (self.config.time_exit_tp_pct / 100)

        if is_long:
            take_profit = signal.entry_price + tp_distance
        else:
            take_profit = signal.entry_price - tp_distance

        # Get account balance
        balance = await self.exchange.get_balance()
        if balance.total_balance <= 0:
            logger.warning(f"Invalid balance: ${balance.total_balance} - skipping trade")
            return
        self.risk_manager.update_equity(balance.total_balance)

        # Calculate heat-adjusted position size
        size, scale, zone = self.risk_manager.calculate_heat_adjusted_size(
            account_balance=balance.total_balance,
            entry_price=signal.entry_price,
            stop_loss_price=stop_loss,
            risk_percent=self.risk_profile["risk_percent"],
            leverage=self.risk_profile["leverage"]
        )

        if size <= 0:
            logger.warning("Position size is 0 - skipping trade")
            return

        # Get symbol info for lot size
        symbol_info = await self.exchange.get_symbol_info(self.config.symbol)

        # Round to lot size and enforce min/max bounds
        size = round(size / symbol_info.lot_size) * symbol_info.lot_size
        size = max(symbol_info.min_size, min(size, symbol_info.max_size))

        # Check minimum notional value
        notional = size * signal.entry_price
        if notional < 5.0:  # Binance minimum notional ~$5
            logger.warning(f"Notional value ${notional:.2f} below minimum $5 - skipping trade")
            return

        # Verify position size is valid
        if size < symbol_info.min_size:
            logger.warning(
                f"Position size {size} below minimum {symbol_info.min_size} - skipping trade"
            )
            return

        logger.info(
            f"Trade setup: {signal.signal_type.value} {size:.4f} {self.config.symbol} | "
            f"Entry: ${signal.entry_price:.2f} | SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}"
        )
        logger.info(f"Heat zone: {zone.value} | Scale: {scale:.0%}")

        # Execute trade
        async with self._trade_lock:
            if self.config.paper_trade:
                logger.info("[PAPER] Trade would be executed")

                # Create paper trade
                self.active_trade = ActiveTrade(
                    symbol=self.config.symbol,
                    side=signal.signal_type,
                    entry_price=signal.entry_price,
                    entry_time=datetime.now(),
                    size=size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    entry_bar_idx=self.current_bar_idx,
                    highest_price=signal.entry_price,
                    lowest_price=signal.entry_price
                )

                # Track position in heat manager
                risk_amount = abs(signal.entry_price - stop_loss) * size
                position_heat = PositionHeat(
                    symbol=self.config.symbol,
                    side="long" if is_long else "short",
                    size=size,
                    entry_price=signal.entry_price,
                    stop_loss=stop_loss,
                    risk_amount=risk_amount,
                    heat_contribution=(risk_amount / balance.total_balance) * 100 if balance.total_balance > 0 else 0
                )
                self.risk_manager.add_position(position_heat)
                logger.debug(f"Added position to heat tracker: {risk_amount:.2f} risk, {position_heat.heat_contribution:.1f}% heat")

                # Persist heat state
                heat_state_path = project_root / "data" / "heat_state.json"
                self.risk_manager.save_state(str(heat_state_path))

                self.state = BotState.IN_POSITION
                self.stats["trades_taken"] += 1
                self.last_signal_bar = self.current_bar_idx

            else:
                # Live trade
                try:
                    order_side = OrderSide.BUY if is_long else OrderSide.SELL

                    order = await self.exchange.place_order(
                        symbol=self.config.symbol,
                        side=order_side,
                        order_type=OrderType.MARKET,
                        size=size,
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )

                    logger.info(f"Order placed: {order.order_id}")

                    actual_entry = order.avg_fill_price or signal.entry_price
                    self.active_trade = ActiveTrade(
                        symbol=self.config.symbol,
                        side=signal.signal_type,
                        entry_price=actual_entry,
                        entry_time=datetime.now(),
                        size=size,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        entry_bar_idx=self.current_bar_idx,
                        highest_price=actual_entry,
                        lowest_price=actual_entry
                    )

                    # Track position in heat manager
                    risk_amount = abs(actual_entry - stop_loss) * size
                    position_heat = PositionHeat(
                        symbol=self.config.symbol,
                        side="long" if is_long else "short",
                        size=size,
                        entry_price=actual_entry,
                        stop_loss=stop_loss,
                        risk_amount=risk_amount,
                        heat_contribution=(risk_amount / balance.total_balance) * 100 if balance.total_balance > 0 else 0
                    )
                    self.risk_manager.add_position(position_heat)
                    logger.debug(f"Added position to heat tracker: {risk_amount:.2f} risk, {position_heat.heat_contribution:.1f}% heat")

                    # Persist heat state
                    heat_state_path = project_root / "data" / "heat_state.json"
                    self.risk_manager.save_state(str(heat_state_path))

                    self.state = BotState.IN_POSITION
                    self.stats["trades_taken"] += 1
                    self.last_signal_bar = self.current_bar_idx

                except Exception as e:
                    logger.error(f"Order failed: {e}")
                    await self._notify_error(f"Order placement failed: {e}")

    async def _update_position(self, current_candle) -> None:
        """Update active position with current price."""
        if not self.active_trade:
            return

        # Update high/low tracking
        self.active_trade.highest_price = max(
            self.active_trade.highest_price,
            current_candle.high
        )
        self.active_trade.lowest_price = min(
            self.active_trade.lowest_price,
            current_candle.low
        )

        # Update trailing stop if enabled
        if self.config.exit_type == "trailing":
            await self._update_trailing_stop(current_candle.close)

    async def _update_trailing_stop(self, current_price: float) -> None:
        """Update trailing stop if conditions met."""
        if not self.active_trade:
            return

        is_long = self.active_trade.side == SignalType.LONG
        entry = self.active_trade.entry_price

        # Calculate current profit
        if is_long:
            profit_pct = (current_price - entry) / entry * 100
        else:
            profit_pct = (entry - current_price) / entry * 100

        # Check if activation threshold reached
        if profit_pct >= self.config.trailing_activation_pct:
            if is_long:
                new_trail = current_price * (1 - self.config.trailing_distance_pct / 100)
                if self.active_trade.trailing_stop is None or new_trail > self.active_trade.trailing_stop:
                    self.active_trade.trailing_stop = new_trail
                    logger.info(f"Trailing stop updated to ${new_trail:.2f}")
            else:
                new_trail = current_price * (1 + self.config.trailing_distance_pct / 100)
                if self.active_trade.trailing_stop is None or new_trail < self.active_trade.trailing_stop:
                    self.active_trade.trailing_stop = new_trail
                    logger.info(f"Trailing stop updated to ${new_trail:.2f}")

    async def _check_exit_conditions(self, candle) -> None:
        """Check exit conditions for active trade."""
        if not self.active_trade:
            return

        trade = self.active_trade
        is_long = trade.side == SignalType.LONG
        current_price = candle.close

        exit_reason = None
        exit_price = current_price

        # Check stop loss
        if is_long:
            if candle.low <= trade.stop_loss:
                exit_reason = "stop_loss"
                exit_price = trade.stop_loss
        else:
            if candle.high >= trade.stop_loss:
                exit_reason = "stop_loss"
                exit_price = trade.stop_loss

        # Check take profit (for fixed/rr exits)
        if not exit_reason and self.config.exit_type in ["fixed_tp", "rr_ratio"]:
            if is_long:
                if candle.high >= trade.take_profit:
                    exit_reason = "take_profit"
                    exit_price = trade.take_profit
            else:
                if candle.low <= trade.take_profit:
                    exit_reason = "take_profit"
                    exit_price = trade.take_profit

        # Check trailing stop
        if not exit_reason and trade.trailing_stop is not None:
            if is_long:
                if candle.low <= trade.trailing_stop:
                    exit_reason = "trailing_stop"
                    exit_price = trade.trailing_stop
            else:
                if candle.high >= trade.trailing_stop:
                    exit_reason = "trailing_stop"
                    exit_price = trade.trailing_stop

        # Check time-based exit
        if not exit_reason and self.config.exit_type == "time_based":
            if trade.bars_held >= self.config.time_exit_bars:
                exit_reason = "time_exit"
                exit_price = current_price

        # Execute exit if condition met
        if exit_reason:
            await self._close_position(exit_reason, exit_price)

    async def _close_position(self, reason: str, exit_price: float) -> None:
        """Close the active position."""
        if not self.active_trade:
            return

        async with self._trade_lock:
            trade = self.active_trade
            if not trade:
                return
            is_long = trade.side == SignalType.LONG

            # Calculate PnL
            if is_long:
                pnl = (exit_price - trade.entry_price) * trade.size
                pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
            else:
                pnl = (trade.entry_price - exit_price) * trade.size
                pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100

            # Apply leverage to PnL percentage
            pnl_pct_leveraged = pnl_pct * self.risk_profile["leverage"]

            is_win = pnl > 0

            logger.info(
                f"CLOSING POSITION: {reason} | "
                f"Exit: ${exit_price:.2f} | PnL: ${pnl:+.2f} ({pnl_pct_leveraged:+.2f}%) | "
                f"{'WIN' if is_win else 'LOSS'}"
            )

            # Execute close
            exchange_close_success = True
            if not self.config.paper_trade:
                try:
                    await self.exchange.close_position(self.config.symbol)
                    logger.info("Position closed on exchange")
                except Exception as e:
                    logger.error(f"Failed to close position on exchange: {e}")
                    logger.error("Position state preserved - manual intervention may be required")
                    exchange_close_success = False
                    # Notify about failed close
                    if self.discord:
                        await self.discord.send_message(
                            title="CRITICAL: Position Close Failed",
                            message=f"Failed to close {self.config.symbol} position.\n"
                                    f"Error: {e}\n"
                                    f"Manual intervention required!",
                            color=0xFF0000
                        )

            # Only update local state if exchange close succeeded (or paper trading)
            if exchange_close_success:
                # Update stats
                if is_win:
                    self.stats["trades_won"] += 1
                else:
                    self.stats["trades_lost"] += 1

                self.stats["total_pnl"] += pnl

                # Circuit breaker tracking
                if is_win:
                    self._consecutive_losses = 0
                else:
                    self._consecutive_losses += 1
                    # Reset daily loss tracker if new day
                    today = datetime.now(timezone.utc).date()
                    if today != self._daily_loss_reset_date:
                        self._daily_loss = 0.0
                        self._daily_loss_reset_date = today
                    self._daily_loss += abs(pnl)

                    # Check circuit breaker conditions
                    if self._consecutive_losses >= self._max_consecutive_losses:
                        self._circuit_breaker_tripped = True
                        logger.error(f"CIRCUIT BREAKER: {self._consecutive_losses} consecutive losses - trading halted")
                        if self.discord:
                            await self.discord.send_message(
                                title="Circuit Breaker Tripped",
                                message=f"Trading halted after {self._consecutive_losses} consecutive losses.\n"
                                        f"Manual reset required.",
                                color=0xFF0000
                            )
                    elif self._starting_balance > 0 and (self._daily_loss / self._starting_balance * 100) >= self._max_daily_loss_pct:
                        self._circuit_breaker_tripped = True
                        logger.error(f"CIRCUIT BREAKER: Daily loss ${self._daily_loss:.2f} exceeds {self._max_daily_loss_pct}% - trading halted")
                        if self.discord:
                            await self.discord.send_message(
                                title="Circuit Breaker Tripped",
                                message=f"Trading halted - daily loss ${self._daily_loss:.2f} "
                                        f"exceeds {self._max_daily_loss_pct}% limit.\n"
                                        f"Manual reset required.",
                                color=0xFF0000
                            )

                # Remove position from heat tracker
                self.risk_manager.remove_position(self.config.symbol)
                logger.debug(f"Removed position from heat tracker: {self.config.symbol}")

                # Persist heat state
                heat_state_path = project_root / "data" / "heat_state.json"
                self.risk_manager.save_state(str(heat_state_path))

                # Clear active trade
                self.active_trade = None
                self.state = BotState.MONITORING
            else:
                # Keep position tracked, will retry on next check cycle
                logger.warning("Keeping position in local state - will retry close on next cycle")

            logger.info(
                f"Stats: {self.stats['trades_won']}W/{self.stats['trades_lost']}L | "
                f"Total PnL: ${self.stats['total_pnl']:+.2f}"
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        status = {
            "state": self.state.value,
            "config": {
                "symbol": self.config.symbol,
                "timeframe": self.config.timeframe,
                "wick_threshold": self.config.wick_threshold,
                "risk_profile": self.config.risk_profile,
                "paper_trade": self.config.paper_trade
            },
            "stats": self.stats.copy(),
            "active_trade": None
        }

        if self.active_trade:
            status["active_trade"] = {
                "symbol": self.active_trade.symbol,
                "side": self.active_trade.side.value,
                "entry_price": self.active_trade.entry_price,
                "size": self.active_trade.size,
                "stop_loss": self.active_trade.stop_loss,
                "take_profit": self.active_trade.take_profit,
                "bars_held": self.active_trade.bars_held
            }

        return status
