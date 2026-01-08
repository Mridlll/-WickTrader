"""WickTrader Multi-Exchange Bot with Fallback Support.

Supports Binance Futures and Hyperliquid with automatic failover.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from exchanges.base import BaseExchange, Candle, OrderSide, OrderType
from exchanges.binance import BinanceExchange
from exchanges.hyperliquid import HyperliquidExchange
from strategy.wick_signals import WickSignalDetector, WickSignal
from strategy.heat_risk import HeatRiskManager, HeatZone, RISK_PRESETS, RiskPreset
from backtest.engine import SignalType
from utils.logger import get_logger

logger = get_logger("multi_exchange_bot")


class ExchangePriority(str, Enum):
    """Exchange priority for order routing."""
    BINANCE_PRIMARY = "binance_primary"
    HYPERLIQUID_PRIMARY = "hyperliquid_primary"
    ROUND_ROBIN = "round_robin"


@dataclass
class ExchangeConfig:
    """Configuration for an exchange."""
    name: str
    enabled: bool = True
    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True
    # Hyperliquid
    hl_private_key: str = ""
    hl_wallet_address: str = ""
    hl_account_address: str = ""
    hl_testnet: bool = True


@dataclass
class MultiExchangeConfig:
    """Multi-exchange bot configuration."""
    # Trading
    symbol: str = "SOL"
    timeframe: str = "4h"

    # Wick strategy
    wick_threshold: float = 5.0
    direction: str = "long"

    # Exit
    exit_type: str = "time_based"
    fixed_tp_pct: float = 15.0
    rr_ratio: float = 2.0
    time_exit_bars: int = 30

    # Risk
    risk_profile: str = "moderate"

    # Exchange routing
    priority: ExchangePriority = ExchangePriority.BINANCE_PRIMARY
    enable_fallback: bool = True

    # Mode
    paper_trade: bool = True


class MultiExchangeBot:
    """
    Multi-exchange trading bot with automatic failover.

    Features:
    - Primary/secondary exchange routing
    - Automatic failover on errors
    - Unified position tracking across exchanges
    - Heat-based risk management
    """

    def __init__(
        self,
        config: MultiExchangeConfig,
        binance_config: Optional[ExchangeConfig] = None,
        hyperliquid_config: Optional[ExchangeConfig] = None
    ):
        self.config = config
        self.binance_config = binance_config
        self.hyperliquid_config = hyperliquid_config

        # Exchanges
        self.binance: Optional[BinanceExchange] = None
        self.hyperliquid: Optional[HyperliquidExchange] = None
        self.primary_exchange: Optional[BaseExchange] = None
        self.fallback_exchange: Optional[BaseExchange] = None

        # Signal detector
        self.signal_detector = WickSignalDetector(threshold=config.wick_threshold)

        # Risk manager
        risk_preset = RiskPreset(config.risk_profile)
        self.risk_profile = RISK_PRESETS[risk_preset]
        self.risk_manager = HeatRiskManager(
            default_risk_percent=self.risk_profile["risk_percent"],
            default_leverage=self.risk_profile["leverage"],
            max_portfolio_heat=self.risk_profile["max_heat"]
        )

        # State
        self._running = False
        self._current_exchange = None
        self._failover_count = 0

        # Stats
        self.stats = {
            "binance_orders": 0,
            "hyperliquid_orders": 0,
            "failovers": 0,
            "signals_detected": 0,
            "trades_taken": 0,
            "start_time": None
        }

        logger.info("MultiExchangeBot initialized")
        logger.info(f"  Symbol: {config.symbol}")
        logger.info(f"  Priority: {config.priority.value}")
        logger.info(f"  Fallback: {config.enable_fallback}")

    async def connect(self) -> bool:
        """Connect to all configured exchanges."""
        connected = []

        # Connect Binance
        if self.binance_config and self.binance_config.enabled:
            try:
                self.binance = BinanceExchange(
                    api_key=self.binance_config.binance_api_key,
                    api_secret=self.binance_config.binance_api_secret,
                    testnet=self.binance_config.binance_testnet
                )
                if await self.binance.connect():
                    connected.append("binance")
                    logger.info("Connected to Binance")
            except Exception as e:
                logger.error(f"Binance connection failed: {e}")

        # Connect Hyperliquid
        if self.hyperliquid_config and self.hyperliquid_config.enabled:
            try:
                self.hyperliquid = HyperliquidExchange(
                    api_key="",  # Not used
                    api_secret=self.hyperliquid_config.hl_private_key,
                    wallet_address=self.hyperliquid_config.hl_wallet_address,
                    account_address=self.hyperliquid_config.hl_account_address,
                    testnet=self.hyperliquid_config.hl_testnet
                )
                if await self.hyperliquid.connect():
                    connected.append("hyperliquid")
                    logger.info("Connected to Hyperliquid")
            except Exception as e:
                logger.error(f"Hyperliquid connection failed: {e}")

        if not connected:
            logger.error("No exchanges connected!")
            return False

        # Set primary/fallback based on priority
        self._setup_exchange_priority()

        logger.info(f"Connected exchanges: {connected}")
        logger.info(f"Primary: {self._current_exchange}")
        return True

    def _setup_exchange_priority(self) -> None:
        """Setup primary and fallback exchanges based on config."""
        if self.config.priority == ExchangePriority.BINANCE_PRIMARY:
            if self.binance:
                self.primary_exchange = self.binance
                self.fallback_exchange = self.hyperliquid
                self._current_exchange = "binance"
            else:
                self.primary_exchange = self.hyperliquid
                self.fallback_exchange = None
                self._current_exchange = "hyperliquid"

        elif self.config.priority == ExchangePriority.HYPERLIQUID_PRIMARY:
            if self.hyperliquid:
                self.primary_exchange = self.hyperliquid
                self.fallback_exchange = self.binance
                self._current_exchange = "hyperliquid"
            else:
                self.primary_exchange = self.binance
                self.fallback_exchange = None
                self._current_exchange = "binance"

        logger.info(f"Primary exchange: {self._current_exchange}")
        if self.fallback_exchange:
            fallback_name = "binance" if self.fallback_exchange == self.binance else "hyperliquid"
            logger.info(f"Fallback exchange: {fallback_name}")

    async def disconnect(self) -> None:
        """Disconnect from all exchanges."""
        if self.binance:
            await self.binance.disconnect()
        if self.hyperliquid:
            await self.hyperliquid.disconnect()
        logger.info("Disconnected from all exchanges")

    async def get_active_exchange(self) -> BaseExchange:
        """Get the currently active exchange, with failover if needed."""
        if self._current_exchange == "binance" and self.binance:
            return self.binance
        elif self._current_exchange == "hyperliquid" and self.hyperliquid:
            return self.hyperliquid
        elif self.primary_exchange:
            return self.primary_exchange
        else:
            raise RuntimeError("No exchange available")

    async def _failover(self) -> bool:
        """Switch to fallback exchange."""
        if not self.config.enable_fallback or not self.fallback_exchange:
            logger.warning("Failover not available")
            return False

        self._failover_count += 1
        self.stats["failovers"] += 1

        if self._current_exchange == "binance":
            self._current_exchange = "hyperliquid"
            logger.warning("FAILOVER: Switched from Binance to Hyperliquid")
        else:
            self._current_exchange = "binance"
            logger.warning("FAILOVER: Switched from Hyperliquid to Binance")

        # Swap primary/fallback
        self.primary_exchange, self.fallback_exchange = self.fallback_exchange, self.primary_exchange

        return True

    async def place_order_with_fallback(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        stop_loss: float,
        take_profit: float
    ) -> Tuple[bool, str, Any]:
        """
        Place order with automatic failover.

        Returns:
            Tuple of (success, exchange_name, order_or_error)
        """
        exchange = await self.get_active_exchange()
        exchange_name = self._current_exchange

        try:
            order = await exchange.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                size=size,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            # Update stats
            if exchange_name == "binance":
                self.stats["binance_orders"] += 1
            else:
                self.stats["hyperliquid_orders"] += 1

            return True, exchange_name, order

        except Exception as e:
            logger.error(f"Order failed on {exchange_name}: {e}")

            # Try failover
            if await self._failover():
                logger.info("Retrying order on fallback exchange...")
                return await self.place_order_with_fallback(
                    symbol, side, size, stop_loss, take_profit
                )

            return False, exchange_name, str(e)

    async def get_combined_balance(self) -> Dict[str, float]:
        """Get combined balance across all exchanges."""
        total = 0.0
        balances = {}

        if self.binance:
            try:
                bal = await self.binance.get_balance()
                balances["binance"] = bal.total_balance
                total += bal.total_balance
            except:
                balances["binance"] = 0.0

        if self.hyperliquid:
            try:
                bal = await self.hyperliquid.get_balance()
                balances["hyperliquid"] = bal.total_balance
                total += bal.total_balance
            except:
                balances["hyperliquid"] = 0.0

        balances["total"] = total
        return balances

    async def get_all_positions(self) -> Dict[str, List]:
        """Get positions from all exchanges."""
        positions = {"binance": [], "hyperliquid": []}

        if self.binance:
            try:
                positions["binance"] = await self.binance.get_positions()
            except:
                pass

        if self.hyperliquid:
            try:
                positions["hyperliquid"] = await self.hyperliquid.get_positions()
            except:
                pass

        return positions

    def get_status(self) -> Dict[str, Any]:
        """Get bot status."""
        return {
            "running": self._running,
            "current_exchange": self._current_exchange,
            "failover_count": self._failover_count,
            "config": {
                "symbol": self.config.symbol,
                "priority": self.config.priority.value,
                "risk_profile": self.config.risk_profile,
                "paper_trade": self.config.paper_trade
            },
            "stats": self.stats,
            "exchanges": {
                "binance": self.binance is not None,
                "hyperliquid": self.hyperliquid is not None
            }
        }
