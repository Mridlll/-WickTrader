"""Bybit exchange adapter for WickTrader.

Implements Bybit V5 Unified Trading API for perpetual futures.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
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


class BybitExchange(BaseExchange):
    """Bybit V5 Unified Trading API implementation."""

    # Base URLs
    TESTNET_URL = "https://api-testnet.bybit.com"
    DEMO_URL = "https://api-demo.bybit.com"
    MAINNET_URL = "https://api.bybit.com"

    # Timeframe mapping (Bybit uses minutes for most)
    TIMEFRAME_MAP = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "6h": "360",
        "12h": "720",
        "1d": "D",
        "1w": "W",
        "1M": "M",
    }

    # API parameters
    RECV_WINDOW = 5000
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        demo: bool = False
    ):
        """
        Initialize Bybit client.

        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            testnet: Use testnet if True, mainnet if False
            demo: Use demo trading account (mainnet data, paper trading)
        """
        super().__init__(api_key, api_secret, testnet)
        self._demo = demo

        # Select URL based on mode
        if demo:
            self._base_url = self.DEMO_URL
        elif testnet:
            self._base_url = self.TESTNET_URL
        else:
            self._base_url = self.MAINNET_URL

        self._session: Optional[aiohttp.ClientSession] = None
        self._symbol_info_cache: Dict[str, SymbolInfo] = {}

        mode = "Demo" if demo else ("Testnet" if testnet else "Mainnet")
        logger.info(f"BybitExchange initialized - {mode}")

    @property
    def name(self) -> str:
        """Exchange name."""
        return "bybit"

    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _sign_request(
        self, timestamp: int, params: Dict[str, Any], method: str = "GET"
    ) -> str:
        """
        Sign request with HMAC SHA256.

        Bybit V5 signature: timestamp + api_key + recv_window + param_string
        - GET: param_string is URL-encoded query string
        - POST: param_string is raw JSON body

        Args:
            timestamp: Request timestamp in milliseconds
            params: Request parameters
            method: HTTP method (GET or POST)

        Returns:
            Signature string
        """
        # Format params based on method
        if method == "POST":
            # POST uses raw JSON
            param_str = json.dumps(params) if params else ""
        else:
            # GET uses URL-encoded sorted params
            param_str = urlencode(sorted(params.items())) if params else ""

        # Bybit signature format: timestamp + api_key + recv_window + param_str
        sign_str = f"{timestamp}{self.api_key}{self.RECV_WINDOW}{param_str}"

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _get_headers(self, timestamp: int, signature: str) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str(self.RECV_WINDOW),
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
        Make HTTP request to Bybit API.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            params: Query/body parameters
            signed: Whether request requires signature

        Returns:
            Response data

        Raises:
            Exception: On API error
        """
        if self._session is None:
            raise RuntimeError("Exchange not connected. Call connect() first.")

        url = f"{self._base_url}{endpoint}"
        params = params or {}

        headers = {"Content-Type": "application/json"}

        if signed:
            timestamp = self._get_timestamp()
            signature = self._sign_request(timestamp, params, method)
            headers = self._get_headers(timestamp, signature)

        for attempt in range(self.MAX_RETRIES):
            try:
                if method == "GET":
                    async with self._session.get(
                        url,
                        params=params if params else None,
                        headers=headers
                    ) as response:
                        status = response.status
                        text = await response.text()
                else:  # POST
                    async with self._session.post(
                        url,
                        json=params if params else None,
                        headers=headers
                    ) as response:
                        status = response.status
                        text = await response.text()

                # Handle HTTP errors
                if status == 401:
                    raise Exception(
                        f"Authentication failed (401): Invalid API credentials or "
                        f"wrong environment (testnet vs mainnet vs demo)"
                    )
                elif status == 403:
                    raise Exception(f"Access forbidden (403): {text[:200]}")
                elif status >= 500:
                    logger.warning(f"Server error {status}, retrying...")
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                        continue
                    raise Exception(f"Server error {status}: {text[:200]}")

                # Parse JSON response
                try:
                    data = json.loads(text) if text else None
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON response: {text[:200]}")
                    data = None

                # Handle None response
                if data is None:
                    logger.error(f"Empty or invalid response from {endpoint}")
                    raise Exception(f"Empty response from Bybit API: {endpoint}")

                # Check Bybit response format
                ret_code = data.get("retCode", -1)

                if ret_code == 0:
                    return data.get("result", data)

                # Handle rate limit
                if ret_code == 10006:  # Rate limit
                    logger.warning(
                        f"Rate limited, retrying in {self.RETRY_DELAY}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue

                # Other errors
                error_msg = data.get("retMsg", "Unknown error")
                logger.error(f"Bybit API error: {ret_code} - {error_msg}")
                raise Exception(f"Bybit API error: {ret_code} - {error_msg}")

            except aiohttp.ClientError as e:
                logger.error(f"HTTP request failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    raise

        raise Exception("Max retries exceeded")

    def format_symbol(self, asset: str) -> str:
        """
        Format asset name to Bybit symbol.

        Args:
            asset: Asset name (e.g., "BTC", "SOL", "SOLUSDT")

        Returns:
            Formatted symbol (e.g., "SOLUSDT")
        """
        asset = asset.upper()
        if asset.endswith("USDT"):
            return asset
        return f"{asset}USDT"

    def _parse_timeframe(self, timeframe: str) -> str:
        """Convert timeframe to Bybit format."""
        if timeframe in self.TIMEFRAME_MAP:
            return self.TIMEFRAME_MAP[timeframe]
        return timeframe

    # Connection Methods

    async def connect(self) -> bool:
        """
        Establish connection to Bybit API.

        Returns:
            True if connection successful
        """
        try:
            self._session = aiohttp.ClientSession()

            # Verify API keys by checking wallet balance
            await self._request(
                "GET",
                "/v5/account/wallet-balance",
                params={"accountType": "UNIFIED"},
                signed=True
            )
            logger.info("Successfully connected to Bybit API")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Bybit: {e}")
            if self._session:
                await self._session.close()
                self._session = None
            raise

    async def disconnect(self) -> None:
        """Disconnect from Bybit API."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("Disconnected from Bybit API")

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
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            limit: Number of candles (max 1000)
            start_time: Start time
            end_time: End time

        Returns:
            List of Candle objects
        """
        formatted_symbol = self.format_symbol(symbol)
        interval = self._parse_timeframe(timeframe)

        params: Dict[str, Any] = {
            "category": "linear",  # USDT perpetual
            "symbol": formatted_symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }

        if start_time:
            params["start"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["end"] = int(end_time.timestamp() * 1000)

        data = await self._request("GET", "/v5/market/kline", params)

        candles = []
        # Bybit returns newest first, we want oldest first
        items = data.get("list", [])
        items.reverse()

        for item in items:
            # Bybit format: [startTime, open, high, low, close, volume, turnover]
            candle = Candle(
                timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc),
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
            Ticker data
        """
        formatted_symbol = self.format_symbol(symbol)

        data = await self._request(
            "GET",
            "/v5/market/tickers",
            params={
                "category": "linear",
                "symbol": formatted_symbol
            }
        )

        ticker = data.get("list", [{}])[0]

        return {
            "symbol": ticker.get("symbol"),
            "price": float(ticker.get("lastPrice", 0)),
            "bid": float(ticker.get("bid1Price", 0)),
            "ask": float(ticker.get("ask1Price", 0)),
            "high_24h": float(ticker.get("highPrice24h", 0)),
            "low_24h": float(ticker.get("lowPrice24h", 0)),
            "volume_24h": float(ticker.get("volume24h", 0)),
            "turnover_24h": float(ticker.get("turnover24h", 0)),
            "price_change_24h": float(ticker.get("price24hPcnt", 0)) * 100,
            "timestamp": datetime.now(timezone.utc)
        }

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """
        Get trading symbol information.

        Args:
            symbol: Trading pair symbol

        Returns:
            SymbolInfo object
        """
        formatted_symbol = self.format_symbol(symbol)

        # Check cache
        if formatted_symbol in self._symbol_info_cache:
            return self._symbol_info_cache[formatted_symbol]

        data = await self._request(
            "GET",
            "/v5/market/instruments-info",
            params={
                "category": "linear",
                "symbol": formatted_symbol
            }
        )

        items = data.get("list", [])
        if not items:
            raise ValueError(f"Symbol {formatted_symbol} not found on Bybit")

        sym_info = items[0]
        lot_filter = sym_info.get("lotSizeFilter", {})
        price_filter = sym_info.get("priceFilter", {})
        leverage_filter = sym_info.get("leverageFilter", {})

        info = SymbolInfo(
            symbol=formatted_symbol,
            base_asset=sym_info.get("baseCoin", ""),
            quote_asset=sym_info.get("quoteCoin", "USDT"),
            tick_size=float(price_filter.get("tickSize", 0.01)),
            lot_size=float(lot_filter.get("qtyStep", 0.001)),
            min_size=float(lot_filter.get("minOrderQty", 0.001)),
            max_size=float(lot_filter.get("maxOrderQty", 10000)),
            max_leverage=float(leverage_filter.get("maxLeverage", 100))
        )

        self._symbol_info_cache[formatted_symbol] = info
        return info

    # Account Methods

    async def get_balance(self) -> AccountBalance:
        """
        Get account balance.

        Returns:
            AccountBalance object
        """
        data = await self._request(
            "GET",
            "/v5/account/wallet-balance",
            params={"accountType": "UNIFIED"},
            signed=True
        )

        # Find USDT balance in unified account
        accounts = data.get("list", [])
        total_balance = 0.0
        available_balance = 0.0
        used_margin = 0.0
        unrealized_pnl = 0.0

        for account in accounts:
            coins = account.get("coin", [])
            for coin in coins:
                if coin.get("coin") == "USDT":
                    total_balance = float(coin.get("walletBalance", 0))
                    available_balance = float(coin.get("availableToWithdraw", 0))
                    unrealized_pnl = float(coin.get("unrealisedPnl", 0))
                    break
            # Also get total equity
            total_balance = float(account.get("totalEquity", total_balance))
            used_margin = float(account.get("totalInitialMargin", 0))

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
        data = await self._request(
            "GET",
            "/v5/position/list",
            params={
                "category": "linear",
                "settleCoin": "USDT"
            },
            signed=True
        )

        positions = []
        for pos in data.get("list", []):
            size = float(pos.get("size", 0))
            if size == 0:
                continue

            side_str = pos.get("side", "").lower()
            position = Position(
                symbol=pos.get("symbol", ""),
                side=PositionSide.LONG if side_str == "buy" else PositionSide.SHORT,
                size=size,
                entry_price=float(pos.get("avgPrice", 0)),
                mark_price=float(pos.get("markPrice", 0)),
                liquidation_price=float(pos.get("liqPrice", 0)) if pos.get("liqPrice") else None,
                unrealized_pnl=float(pos.get("unrealisedPnl", 0)),
                realized_pnl=float(pos.get("cumRealisedPnl", 0)),
                leverage=float(pos.get("leverage", 1)),
                margin=float(pos.get("positionIM", 0))
            )
            positions.append(position)

        return positions

    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position object or None
        """
        formatted_symbol = self.format_symbol(symbol)

        data = await self._request(
            "GET",
            "/v5/position/list",
            params={
                "category": "linear",
                "symbol": formatted_symbol
            },
            signed=True
        )

        for pos in data.get("list", []):
            size = float(pos.get("size", 0))
            if size == 0:
                continue

            side_str = pos.get("side", "").lower()
            return Position(
                symbol=pos.get("symbol", ""),
                side=PositionSide.LONG if side_str == "buy" else PositionSide.SHORT,
                size=size,
                entry_price=float(pos.get("avgPrice", 0)),
                mark_price=float(pos.get("markPrice", 0)),
                liquidation_price=float(pos.get("liqPrice", 0)) if pos.get("liqPrice") else None,
                unrealized_pnl=float(pos.get("unrealisedPnl", 0)),
                realized_pnl=float(pos.get("cumRealisedPnl", 0)),
                leverage=float(pos.get("leverage", 1)),
                margin=float(pos.get("positionIM", 0))
            )

        return None

    # Order Methods

    def _map_order_side(self, side: OrderSide) -> str:
        """Map OrderSide enum to Bybit side."""
        return "Buy" if side == OrderSide.BUY else "Sell"

    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType enum to Bybit type."""
        return "Market" if order_type == OrderType.MARKET else "Limit"

    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse Bybit order status."""
        status_map = {
            "New": OrderStatus.OPEN,
            "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Rejected": OrderStatus.REJECTED,
            "Deactivated": OrderStatus.CANCELLED,
        }
        return status_map.get(status, OrderStatus.PENDING)

    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Bybit order response to Order object."""
        side = OrderSide.BUY if data.get("side") == "Buy" else OrderSide.SELL
        order_type = OrderType.MARKET if data.get("orderType") == "Market" else OrderType.LIMIT

        return Order(
            order_id=data.get("orderId", ""),
            symbol=data.get("symbol", ""),
            side=side,
            order_type=order_type,
            size=float(data.get("qty", 0)),
            price=float(data.get("price", 0)) if data.get("price") else None,
            status=self._parse_order_status(data.get("orderStatus", "")),
            filled_size=float(data.get("cumExecQty", 0)),
            avg_fill_price=float(data.get("avgPrice", 0)) if data.get("avgPrice") else None,
            created_at=datetime.fromtimestamp(
                int(data.get("createdTime", 0)) / 1000, tz=timezone.utc
            ) if data.get("createdTime") else None,
            updated_at=datetime.fromtimestamp(
                int(data.get("updatedTime", 0)) / 1000, tz=timezone.utc
            ) if data.get("updatedTime") else None,
            reduce_only=data.get("reduceOnly", False),
            client_order_id=data.get("orderLinkId")
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
            price: Limit price
            stop_loss: Stop loss price
            take_profit: Take profit price
            reduce_only: Only reduce position
            client_order_id: Custom order ID

        Returns:
            Order object
        """
        formatted_symbol = self.format_symbol(symbol)

        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": formatted_symbol,
            "side": self._map_order_side(side),
            "orderType": self._map_order_type(order_type),
            "qty": str(size),
            "timeInForce": "GTC"
        }

        if order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Price required for limit orders")
            params["price"] = str(price)

        if reduce_only:
            params["reduceOnly"] = True

        if client_order_id:
            params["orderLinkId"] = client_order_id

        # Add SL/TP if specified
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
            params["slTriggerBy"] = "MarkPrice"

        if take_profit:
            params["takeProfit"] = str(take_profit)
            params["tpTriggerBy"] = "MarkPrice"

        logger.info(
            f"Placing {order_type.value} {side.value} order: "
            f"{size} {formatted_symbol} @ {price or 'market'}"
        )

        data = await self._request("POST", "/v5/order/create", params, signed=True)

        # Get order details
        order_id = data.get("orderId", "")

        # Fetch full order info
        order_data = await self._request(
            "GET",
            "/v5/order/realtime",
            params={
                "category": "linear",
                "orderId": order_id
            },
            signed=True
        )

        orders = order_data.get("list", [])
        if orders:
            return self._parse_order(orders[0])

        # Return basic order if can't fetch details
        return Order(
            order_id=order_id,
            symbol=formatted_symbol,
            side=side,
            order_type=order_type,
            size=size,
            price=price,
            status=OrderStatus.OPEN
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID
            symbol: Trading pair symbol

        Returns:
            True if cancelled successfully
        """
        formatted_symbol = self.format_symbol(symbol)

        try:
            await self._request(
                "POST",
                "/v5/order/cancel",
                params={
                    "category": "linear",
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
                "/v5/order/realtime",
                params={
                    "category": "linear",
                    "symbol": formatted_symbol,
                    "orderId": order_id
                },
                signed=True
            )

            orders = data.get("list", [])
            if orders:
                return self._parse_order(orders[0])
            return None
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
        params: Dict[str, Any] = {
            "category": "linear",
            "settleCoin": "USDT"
        }

        if symbol:
            params["symbol"] = self.format_symbol(symbol)

        data = await self._request(
            "GET",
            "/v5/order/realtime",
            params,
            signed=True
        )

        return [self._parse_order(order) for order in data.get("list", [])]

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
            Order object
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
            leverage: Leverage value

        Returns:
            True if successful
        """
        formatted_symbol = self.format_symbol(symbol)

        try:
            await self._request(
                "POST",
                "/v5/position/set-leverage",
                params={
                    "category": "linear",
                    "symbol": formatted_symbol,
                    "buyLeverage": str(int(leverage)),
                    "sellLeverage": str(int(leverage))
                },
                signed=True
            )
            logger.info(f"Set leverage for {formatted_symbol} to {leverage}x")
            return True
        except Exception as e:
            # Bybit returns error if leverage already set
            if "leverage not modified" in str(e).lower() or "110043" in str(e):
                return True
            logger.error(f"Failed to set leverage: {e}")
            return False

    async def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> bool:
        """
        Set margin type for a symbol.

        Note: Bybit V5 unified account handles this differently.
        Cross margin is default in unified trading account.

        Args:
            symbol: Trading pair symbol
            margin_type: "CROSSED" or "ISOLATED"

        Returns:
            True if successful
        """
        # In Bybit unified account, margin mode is set differently
        # For now, just return True as unified account handles this automatically
        logger.info(f"Margin type for Bybit unified account: {margin_type}")
        return True

    # Context manager support

    async def __aenter__(self) -> "BybitExchange":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
