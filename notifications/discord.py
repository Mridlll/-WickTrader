"""Discord webhook notifications for WickTrader."""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import aiohttp

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.logger import get_logger

logger = get_logger("discord")


class DiscordNotifier:
    """
    Discord webhook notification sender for WickTrader.

    Sends formatted messages for:
    - Wick signals detected
    - Trades opened/closed
    - Daily summaries
    - Errors and warnings
    """

    # Embed colors
    COLOR_SUCCESS = 0x00FF00   # Green
    COLOR_ERROR = 0xFF0000     # Red
    COLOR_WARNING = 0xFFA500   # Orange
    COLOR_INFO = 0x0099FF      # Blue
    COLOR_LONG = 0x00FF00      # Green
    COLOR_SHORT = 0xFF0000     # Red
    COLOR_WICK = 0x9B59B6      # Purple (for wick signals)

    def __init__(
        self,
        webhook_url: str,
        bot_name: str = "WickTrader",
        notify_signals: bool = True,
        notify_trades: bool = True,
        notify_errors: bool = True,
        notify_daily: bool = True
    ):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
            bot_name: Bot display name
            notify_signals: Send wick signal notifications
            notify_trades: Send trade open/close notifications
            notify_errors: Send error notifications
            notify_daily: Send daily summary notifications
        """
        self.webhook_url = webhook_url
        self.bot_name = bot_name
        self.notify_signals = notify_signals
        self.notify_trades = notify_trades
        self.notify_errors = notify_errors
        self.notify_daily = notify_daily
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_message(
        self,
        content: Optional[str] = None,
        embeds: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send message to Discord webhook.

        Args:
            content: Text content
            embeds: List of embed objects

        Returns:
            True if sent successfully
        """
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return False

        try:
            session = await self._get_session()

            payload = {"username": self.bot_name}
            if content:
                payload["content"] = content
            if embeds:
                payload["embeds"] = embeds

            async with session.post(self.webhook_url, json=payload) as response:
                if response.status == 204:
                    logger.debug("Discord notification sent")
                    return True
                else:
                    logger.warning(f"Discord webhook returned {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Discord notification failed: {e}")
            return False

    async def notify(self, event_type: str, data: Dict[str, Any]) -> bool:
        """
        Send notification for an event.

        Args:
            event_type: Type of event
            data: Event data

        Returns:
            True if notification sent
        """
        handlers = {
            "wick_signal": self._notify_wick_signal,
            "trade_opened": self._notify_trade_opened,
            "trade_closed": self._notify_trade_closed,
            "error": self._notify_error,
            "bot_started": self._notify_bot_started,
            "bot_stopped": self._notify_bot_stopped,
            "daily_summary": self._notify_daily_summary,
            "heat_warning": self._notify_heat_warning,
            "failover": self._notify_failover,
        }

        handler = handlers.get(event_type)
        if handler:
            return await handler(data)

        logger.warning(f"Unknown event type: {event_type}")
        return False

    async def _notify_wick_signal(self, data: Dict[str, Any]) -> bool:
        """Send wick signal notification."""
        if not self.notify_signals:
            return False

        signal_type = data.get("signal_type", "LONG").upper()
        is_long = signal_type == "LONG"
        wick_pct = data.get("wick_pct", 0)

        embed = {
            "title": f"{'📈' if is_long else '📉'} Wick Signal: {signal_type}",
            "color": self.COLOR_WICK,
            "fields": [
                {"name": "Symbol", "value": data.get("symbol", "SOL"), "inline": True},
                {"name": "Wick Size", "value": f"{wick_pct:.1f}%", "inline": True},
                {"name": "Entry Price", "value": f"${data.get('entry_price', 0):,.2f}", "inline": True},
                {"name": "Stop Loss", "value": f"${data.get('stop_loss', 0):,.2f}", "inline": True},
                {"name": "Take Profit", "value": f"${data.get('take_profit', 0):,.2f}", "inline": True},
                {"name": "Heat Zone", "value": data.get("heat_zone", "GREEN"), "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": f"{self.bot_name} | Wick Strategy"}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_trade_opened(self, data: Dict[str, Any]) -> bool:
        """Send trade opened notification."""
        if not self.notify_trades:
            return False

        signal_type = data.get("signal_type", "LONG").upper()
        is_long = signal_type == "LONG"

        embed = {
            "title": f"{'🟢' if is_long else '🔴'} Trade Opened - {signal_type}",
            "color": self.COLOR_LONG if is_long else self.COLOR_SHORT,
            "fields": [
                {"name": "Symbol", "value": data.get("symbol", "SOL"), "inline": True},
                {"name": "Entry", "value": f"${data.get('entry_price', 0):,.2f}", "inline": True},
                {"name": "Size", "value": f"{data.get('size', 0):.4f}", "inline": True},
                {"name": "Stop Loss", "value": f"${data.get('stop_loss', 0):,.2f}", "inline": True},
                {"name": "Take Profit", "value": f"${data.get('take_profit', 0):,.2f}", "inline": True},
                {"name": "Exchange", "value": data.get("exchange", "N/A"), "inline": True},
                {"name": "Wick Size", "value": f"{data.get('wick_pct', 0):.1f}%", "inline": True},
                {"name": "Heat Zone", "value": data.get("heat_zone", "GREEN"), "inline": True},
                {"name": "Leverage", "value": f"{data.get('leverage', 1)}x", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_trade_closed(self, data: Dict[str, Any]) -> bool:
        """Send trade closed notification."""
        if not self.notify_trades:
            return False

        pnl = data.get("pnl", 0)
        pnl_pct = data.get("pnl_percent", 0)
        is_win = pnl >= 0

        embed = {
            "title": f"{'💰' if is_win else '💸'} Trade Closed - {'WIN' if is_win else 'LOSS'}",
            "color": self.COLOR_SUCCESS if is_win else self.COLOR_ERROR,
            "fields": [
                {"name": "Symbol", "value": data.get("symbol", "SOL"), "inline": True},
                {"name": "Exit Reason", "value": data.get("exit_reason", "N/A"), "inline": True},
                {"name": "Bars Held", "value": str(data.get("bars_held", 0)), "inline": True},
                {"name": "Entry", "value": f"${data.get('entry_price', 0):,.2f}", "inline": True},
                {"name": "Exit", "value": f"${data.get('exit_price', 0):,.2f}", "inline": True},
                {"name": "PnL", "value": f"${pnl:+,.2f}", "inline": True},
                {"name": "PnL %", "value": f"{pnl_pct:+.2f}%", "inline": True},
                {"name": "Exchange", "value": data.get("exchange", "N/A"), "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_error(self, data: Dict[str, Any]) -> bool:
        """Send error notification."""
        if not self.notify_errors:
            return False

        embed = {
            "title": "⚠️ Error Occurred",
            "color": self.COLOR_ERROR,
            "description": data.get("message", "Unknown error"),
            "fields": [
                {"name": "Component", "value": data.get("component", "Unknown"), "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_bot_started(self, data: Dict[str, Any]) -> bool:
        """Send bot started notification."""
        embed = {
            "title": "🚀 WickTrader Started",
            "color": self.COLOR_SUCCESS,
            "fields": [
                {"name": "Symbol", "value": data.get("symbol", "SOL"), "inline": True},
                {"name": "Timeframe", "value": data.get("timeframe", "4h"), "inline": True},
                {"name": "Risk Profile", "value": data.get("risk_profile", "moderate"), "inline": True},
                {"name": "Wick Threshold", "value": f"{data.get('wick_threshold', 5)}%", "inline": True},
                {"name": "Exchange", "value": data.get("exchange", "N/A"), "inline": True},
                {"name": "Mode", "value": "PAPER" if data.get("paper_trade") else "LIVE", "inline": True},
                {"name": "Balance", "value": f"${data.get('balance', 0):,.2f}", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_bot_stopped(self, data: Dict[str, Any]) -> bool:
        """Send bot stopped notification."""
        embed = {
            "title": "🛑 WickTrader Stopped",
            "color": self.COLOR_WARNING,
            "fields": [
                {"name": "Reason", "value": data.get("reason", "Manual stop"), "inline": True},
                {"name": "Signals", "value": str(data.get("signals_detected", 0)), "inline": True},
                {"name": "Trades", "value": str(data.get("trades_taken", 0)), "inline": True},
                {"name": "Total PnL", "value": f"${data.get('total_pnl', 0):+,.2f}", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_daily_summary(self, data: Dict[str, Any]) -> bool:
        """Send daily summary notification."""
        if not self.notify_daily:
            return False

        pnl = data.get("total_pnl", 0)
        is_profit = pnl >= 0

        embed = {
            "title": f"📊 Daily Summary - {'Profit' if is_profit else 'Loss'}",
            "color": self.COLOR_SUCCESS if is_profit else self.COLOR_ERROR,
            "fields": [
                {"name": "Date", "value": data.get("date", "N/A"), "inline": True},
                {"name": "Signals", "value": str(data.get("signals", 0)), "inline": True},
                {"name": "Trades", "value": str(data.get("trades", 0)), "inline": True},
                {"name": "Win Rate", "value": f"{data.get('win_rate', 0):.1f}%", "inline": True},
                {"name": "Total PnL", "value": f"${pnl:+,.2f}", "inline": True},
                {"name": "Balance", "value": f"${data.get('balance', 0):,.2f}", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_heat_warning(self, data: Dict[str, Any]) -> bool:
        """Send heat zone warning notification."""
        zone = data.get("zone", "YELLOW")
        zone_colors = {
            "GREEN": 0x00FF00,
            "YELLOW": 0xFFFF00,
            "RED": 0xFF0000,
            "CRITICAL": 0x8B0000
        }

        embed = {
            "title": f"🔥 Heat Zone: {zone}",
            "color": zone_colors.get(zone, self.COLOR_WARNING),
            "fields": [
                {"name": "Current Heat", "value": f"{data.get('heat', 0):.1f}%", "inline": True},
                {"name": "Max Heat", "value": f"{data.get('max_heat', 100):.1f}%", "inline": True},
                {"name": "Position Scale", "value": f"{data.get('scale', 100):.0f}%", "inline": True},
            ],
            "description": data.get("message", "Heat level changed"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])

    async def _notify_failover(self, data: Dict[str, Any]) -> bool:
        """Send exchange failover notification."""
        embed = {
            "title": "🔄 Exchange Failover",
            "color": self.COLOR_WARNING,
            "fields": [
                {"name": "From", "value": data.get("from_exchange", "N/A"), "inline": True},
                {"name": "To", "value": data.get("to_exchange", "N/A"), "inline": True},
                {"name": "Reason", "value": data.get("reason", "Error"), "inline": False},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.bot_name}
        }

        return await self.send_message(embeds=[embed])
