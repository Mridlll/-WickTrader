"""Binance Futures exchange adapter for WickTrader."""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from loguru import logger

from .base import (
    AccountBalance,
    BaseExchange,
    Candle,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    SymbolInfo,
)


class BinanceExchange(BaseExchange):
    """Binance Futures exchange implementation."""

    # Base URLs
    TESTNET_URL = "https://demo-fapi.binance.com"  # Binance demo trading
    MAINNET_URL = "https://fapi.binance.com"

    # Timeframe mapping
    TIMEFRAME_MAP = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "3d": "3d",
        "1w": "1w",
        "1M": "1M",
    }

    # API rate limit parameters
    RECV_WINDOW = 5000  # milliseconds
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True
    ):
        """
        Initialize Binance Futures client.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet if True, mainnet if False
        """
        super().__init__(api_key, api_secret, testnet)
        self._base_url = self.TESTNET_URL if testnet else self.MAINNET_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._symbol_info_cache: Dict[str, SymbolInfo] = {}
        logger.info(
            f"BinanceExchange initialized - {'Testnet' if testnet else 'Mainnet'}"
        )

    @property
    def name(self) -> str:
        """Exchange name."""
        return "binance"

    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _sign_request(self, params: Dict[str, Any]) -> str:
        """
        Sign request parameters with HMAC SHA256.

        Args:
            params: Request parameters to sign

        Returns:
            Signature string
        """
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key."""
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json"
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Binance API.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint
            params: Query parameters
            signed: Whether request requires signature

        Returns:
            Response data as dictionary

        Raises:
            Exception: On API error
        """
        if self._session is None:
            raise RuntimeError("Exchange not connected. Call connect() first.")

        url = f"{self._base_url}{endpoint}"
        params = params or {}

        if signed:
            params["timestamp"] = self._get_timestamp()
            params["recvWindow"] = self.RECV_WINDOW
            params["signature"] = self._sign_request(params)

        for attempt in range(self.MAX_RETRIES):
            try:
                async with self._session.request(
                    method,
                    url,
                    params=params if method == "GET" else None,
                    data=params if method != "GET" else None,
                    headers=self._get_headers()
                ) as response:
                    data = await response.json()

                    # Handle rate limit
                    if response.status == 429:
                        retry_after = float(
                            response.headers.get("Retry-After", self.RETRY_DELAY)
                        )
                        logger.warning(
                            f"Rate limited, retrying in {retry_after}s "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle other errors
                    if response.status != 200:
                        error_code = data.get("code", response.status)
                        error_msg = data.get("msg", "Unknown error")
                        logger.error(
                            f"Binance API error: {error_code} - {error_msg}"
                        )
                        raise Exception(f"Binance API error: {error_code} - {error_msg}")

                    return data

            except aiohttp.ClientError as e:
                logger.error(f"HTTP request failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    raise

        raise Exception("Max retries exceeded")

    def format_symbol(self, asset: str) -> str:
        """
        Format asset name to Binance Futures symbol.

        Args:
            asset: Asset name (e.g., "BTC", "SOL", "BTCUSDT")

        Returns:
            Formatted symbol (e.g., "BTCUSDT", "SOLUSDT")
        """
        asset = asset.upper()
        if asset.endswith("USDT"):
            return asset
        return f"{asset}USDT"

    def _parse_timeframe(self, timeframe: str) -> str:
        """
        Convert timeframe to Binance format.

        Args:
            timeframe: Timeframe string (e.g., "4h", "1d")

        Returns:
            Binance interval format
        """
        if timeframe in self.TIMEFRAME_MAP:
            return self.TIMEFRAME_MAP[timeframe]
        return timeframe

    # Connection Methods

    async def connect(self) -> bool:
        """
        Establish connection to Binance Futures API.

        Returns:
            True if connection successful
        """
        try:
            self._session = aiohttp.ClientSession()

            # Verify API keys by checking account info
            await self._request("GET", "/fapi/v2/account", signed=True)
            logger.info("Successfully connected to Binance Futures API")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            if self._session:
                await self._session.close()
                self._session = None
            raise

    async def disconnect(self) -> None:
        """Disconnect from Binance API."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("Disconnected from Binance Futures API")

    # Market Data Methods

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Candle]:
        """
        Fetch OHLCV candles for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTC", "SOLUSDT")
            timeframe: Candle timeframe (e.g., "4h", "1d")
            limit: Number of candles to fetch (max 1500)
            start_time: Start time for historical data
            end_time: End time for historical data

        Returns:
            List of Candle objects
        """
        formatted_symbol = self.format_symbol(symbol)
        interval = self._parse_timeframe(timeframe)

        params: Dict[str, Any] = {
            "symbol": formatted_symbol,
            "interval": interval,
            "limit": min(limit, 1500)  # Binance max is 1500
        }

        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)

        data = await self._request("GET", "/fapi/v1/klines", params)

        candles = []
        for item in data:
            candle = Candle(
                timestamp=datetime.fromtimestamp(item[0] / 1000),
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5])
            )
            candles.append(candle)

        logger.debug(
            f"Fetched {len(candles)} candles for {formatted_symbol} {timeframe}"
        )
        return candles

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get current ticker data for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Ticker data including price, volume, etc.
        """
        formatted_symbol = self.format_symbol(symbol)

        data = await self._request(
            "GET",
            "/fapi/v1/ticker/24hr",
            params={"symbol": formatted_symbol}
        )

        return {
            "symbol": data["symbol"],
            "price": float(data["lastPrice"]),
            "bid": float(data["bidPrice"]),
            "ask": float(data["askPrice"]),
            "high_24h": float(data["highPrice"]),
            "low_24h": float(data["lowPrice"]),
            "volume_24h": float(data["volume"]),
            "quote_volume_24h": float(data["quoteVolume"]),
            "price_change_24h": float(data["priceChange"]),
            "price_change_percent_24h": float(data["priceChangePercent"]),
            "timestamp": datetime.fromtimestamp(data["closeTime"] / 1000)
        }

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """
        Get trading symbol information including lot size and tick size.

        Args:
            symbol: Trading pair symbol

        Returns:
            SymbolInfo object
        """
        formatted_symbol = self.format_symbol(symbol)

        # Check cache first
        if formatted_symbol in self._symbol_info_cache:
            return self._symbol_info_cache[formatted_symbol]

        data = await self._request("GET", "/fapi/v1/exchangeInfo")

        for sym_info in data["symbols"]:
            if sym_info["symbol"] == formatted_symbol:
                # Parse filters
                tick_size = 0.0
                lot_size = 0.0
                min_size = 0.0
                max_size = 0.0

                for f in sym_info["filters"]:
                    if f["filterType"] == "PRICE_FILTER":
                        tick_size = float(f["tickSize"])
                    elif f["filterType"] == "LOT_SIZE":
                        lot_size = float(f["stepSize"])
                        min_size = float(f["minQty"])
                        max_size = float(f["maxQty"])

                # Get max leverage from leverage brackets
                max_leverage = 125.0  # Default Binance max
                try:
                    leverage_data = await self._request(
                        "GET",
                        "/fapi/v1/leverageBracket",
                        params={"symbol": formatted_symbol},
                        signed=True
                    )
                    if leverage_data and len(leverage_data) > 0:
                        brackets = leverage_data[0].get("brackets", [])
                        if brackets:
                            max_leverage = float(brackets[0].get("initialLeverage", 125))
                except Exception as e:
                    logger.debug(f"Could not fetch leverage brackets: {e}")

                info = SymbolInfo(
                    symbol=formatted_symbol,
                    base_asset=sym_info["baseAsset"],
                    quote_asset=sym_info["quoteAsset"],
                    tick_size=tick_size,
                    lot_size=lot_size,
                    min_size=min_size,
                    max_size=max_size,
                    max_leverage=max_leverage
                )

                # Cache the result
                self._symbol_info_cache[formatted_symbol] = info
                return info

        raise ValueError(f"Symbol {formatted_symbol} not found on Binance")

    # Account Methods

    async def get_balance(self) -> AccountBalance:
        """
        Get account balance.

        Returns:
            AccountBalance object
        """
        data = await self._request("GET", "/fapi/v2/account", signed=True)

        total_balance = float(data["totalWalletBalance"])
        available_balance = float(data["availableBalance"])
        used_margin = float(data["totalInitialMargin"])
        unrealized_pnl = float(data["totalUnrealizedProfit"])

        return AccountBalance(
            total_balance=total_balance,
            available_balance=available_balance,
            used_margin=used_margin,
            unrealized_pnl=unrealized_pnl,
            currency="USDT"
        )

    async def get_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects
        """
        data = await self._request("GET", "/fapi/v2/positionRisk", signed=True)

        positions = []
        for pos in data:
            size = float(pos["positionAmt"])
            if size == 0:
                continue  # Skip empty positions

            position = Position(
                symbol=pos["symbol"],
                side=PositionSide.LONG if size > 0 else PositionSide.SHORT,
                size=abs(size),
                entry_price=float(pos["entryPrice"]),
                mark_price=float(pos["markPrice"]),
                liquidation_price=float(pos["liquidationPrice"]) if pos["liquidationPrice"] else None,
                unrealized_pnl=float(pos["unRealizedProfit"]),
                realized_pnl=0.0,  # Not available in this endpoint
                leverage=float(pos["leverage"]),
                margin=float(pos["isolatedMargin"]) if pos["marginType"] == "isolated" else 0.0
            )
            positions.append(position)

        return positions

    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position object or None if no position
        """
        formatted_symbol = self.format_symbol(symbol)
        positions = await self.get_positions()

        for pos in positions:
            if pos.symbol == formatted_symbol:
                return pos

        return None

    # Order Methods

    def _map_order_side(self, side: OrderSide) -> str:
        """Map OrderSide enum to Binance side."""
        return "BUY" if side == OrderSide.BUY else "SELL"

    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType enum to Binance type."""
        return "MARKET" if order_type == OrderType.MARKET else "LIMIT"

    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse Binance order status to OrderStatus enum."""
        status_map = {
            "NEW": OrderStatus.OPEN,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.CANCELLED,
        }
        return status_map.get(status, OrderStatus.PENDING)

    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Binance order response to Order object."""
        side = OrderSide.BUY if data["side"] == "BUY" else OrderSide.SELL
        order_type = OrderType.MARKET if data["type"] == "MARKET" else OrderType.LIMIT

        return Order(
            order_id=str(data["orderId"]),
            symbol=data["symbol"],
            side=side,
            order_type=order_type,
            size=float(data["origQty"]),
            price=float(data["price"]) if data.get("price") else None,
            status=self._parse_order_status(data["status"]),
            filled_size=float(data["executedQty"]),
            avg_fill_price=float(data["avgPrice"]) if data.get("avgPrice") else None,
            created_at=datetime.fromtimestamp(data["time"] / 1000) if data.get("time") else None,
            updated_at=datetime.fromtimestamp(data["updateTime"] / 1000) if data.get("updateTime") else None,
            reduce_only=data.get("reduceOnly", False),
            client_order_id=data.get("clientOrderId")
        )

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None
    ) -> Order:
        """
        Place a new order.

        Args:
            symbol: Trading pair symbol
            side: Buy or sell
            order_type: Market or limit
            size: Order size
            price: Limit price (required for limit orders)
            stop_loss: Stop loss price (creates separate SL order)
            take_profit: Take profit price (creates separate TP order)
            reduce_only: Only reduce position
            client_order_id: Custom order ID

        Returns:
            Order object
        """
        formatted_symbol = self.format_symbol(symbol)

        params: Dict[str, Any] = {
            "symbol": formatted_symbol,
            "side": self._map_order_side(side),
            "type": self._map_order_type(order_type),
            "quantity": size
        }

        if order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Price required for limit orders")
            params["price"] = price
            params["timeInForce"] = "GTC"

        if reduce_only:
            params["reduceOnly"] = "true"

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        logger.info(
            f"Placing {order_type.value} {side.value} order: "
            f"{size} {formatted_symbol} @ {price or 'market'}"
        )

        data = await self._request("POST", "/fapi/v1/order", params, signed=True)
        order = self._parse_order(data)

        # Place stop loss order if specified
        if stop_loss and order.status in [OrderStatus.FILLED, OrderStatus.OPEN]:
            await self._place_stop_order(
                formatted_symbol,
                OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
                stop_loss,
                size,
                "STOP_MARKET"
            )

        # Place take profit order if specified
        if take_profit and order.status in [OrderStatus.FILLED, OrderStatus.OPEN]:
            await self._place_stop_order(
                formatted_symbol,
                OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
                take_profit,
                size,
                "TAKE_PROFIT_MARKET"
            )

        return order

    async def _place_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: float,
        size: float,
        order_type: str
    ) -> None:
        """
        Place a stop loss or take profit order.

        Args:
            symbol: Formatted symbol
            side: Order side
            stop_price: Trigger price
            size: Order size
            order_type: STOP_MARKET or TAKE_PROFIT_MARKET
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": self._map_order_side(side),
            "type": order_type,
            "stopPrice": stop_price,
            "quantity": size,
            "reduceOnly": "true"
        }

        try:
            await self._request("POST", "/fapi/v1/order", params, signed=True)
            logger.info(f"Placed {order_type} order at {stop_price}")
        except Exception as e:
            logger.error(f"Failed to place {order_type} order: {e}")

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel
            symbol: Trading pair symbol

        Returns:
            True if cancelled successfully
        """
        formatted_symbol = self.format_symbol(symbol)

        try:
            await self._request(
                "DELETE",
                "/fapi/v1/order",
                params={
                    "symbol": formatted_symbol,
                    "orderId": order_id
                },
                signed=True
            )
            logger.info(f"Cancelled order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order(self, order_id: str, symbol: str) -> Optional[Order]:
        """
        Get order details.

        Args:
            order_id: Order ID
            symbol: Trading pair symbol

        Returns:
            Order object or None
        """
        formatted_symbol = self.format_symbol(symbol)

        try:
            data = await self._request(
                "GET",
                "/fapi/v1/order",
                params={
                    "symbol": formatted_symbol,
                    "orderId": order_id
                },
                signed=True
            )
            return self._parse_order(data)
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of Order objects
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = self.format_symbol(symbol)

        data = await self._request(
            "GET",
            "/fapi/v1/openOrders",
            params if params else None,
            signed=True
        )

        return [self._parse_order(order) for order in data]

    # Position Management

    async def close_position(
        self,
        symbol: str,
        size: Optional[float] = None
    ) -> Order:
        """
        Close a position.

        Args:
            symbol: Trading pair symbol
            size: Size to close (None = close entire position)

        Returns:
            Order object for the closing trade
        """
        position = await self.get_position(symbol)
        if not position:
            raise ValueError(f"No open position for {symbol}")

        close_size = size if size else position.size
        close_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

        return await self.place_order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            size=close_size,
            reduce_only=True
        )

    async def set_leverage(self, symbol: str, leverage: float) -> bool:
        """
        Set leverage for a symbol.

        Args:
            symbol: Trading pair symbol
            leverage: Leverage value (1-125 for most symbols)

        Returns:
            True if successful
        """
        formatted_symbol = self.format_symbol(symbol)

        try:
            await self._request(
                "POST",
                "/fapi/v1/leverage",
                params={
                    "symbol": formatted_symbol,
                    "leverage": int(leverage)
                },
                signed=True
            )
            logger.info(f"Set leverage for {formatted_symbol} to {leverage}x")
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False

    async def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> bool:
        """
        Set margin type for a symbol.

        Args:
            symbol: Trading pair symbol
            margin_type: "CROSSED" or "ISOLATED"

        Returns:
            True if successful
        """
        formatted_symbol = self.format_symbol(symbol)

        try:
            await self._request(
                "POST",
                "/fapi/v1/marginType",
                params={
                    "symbol": formatted_symbol,
                    "marginType": margin_type
                },
                signed=True
            )
            logger.info(f"Set margin type for {formatted_symbol} to {margin_type}")
            return True
        except Exception as e:
            # Error -4046 means margin type is already set
            if "-4046" in str(e):
                return True
            logger.error(f"Failed to set margin type: {e}")
            return False

    # Context manager support

    async def __aenter__(self) -> "BinanceExchange":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
