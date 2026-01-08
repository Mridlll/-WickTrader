#!/usr/bin/env python3
"""Demo trading test on Binance Futures Demo."""

import asyncio
import time
import hmac
import hashlib
from urllib.parse import urlencode
from datetime import datetime

import aiohttp
import yaml
from pathlib import Path


def load_credentials():
    """Load API credentials from config file."""
    config_path = Path(__file__).parent / "config" / "binance_testnet.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config['exchange']['api_key'], config['exchange']['api_secret']


API_KEY, API_SECRET = load_credentials()
URL = 'https://demo-fapi.binance.com'


def sign(params: dict) -> dict:
    """Sign request parameters."""
    query = urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    return params


async def demo_trade():
    """Execute a demo trade on Binance Futures Demo."""
    print("=" * 60)
    print("  BINANCE FUTURES DEMO TRADING TEST")
    print("=" * 60)
    print(f"  URL: {URL}")
    print("=" * 60)

    headers = {'X-MBX-APIKEY': API_KEY}

    async with aiohttp.ClientSession() as session:
        # Get server time
        async with session.get(f'{URL}/fapi/v1/time') as r:
            server_time = (await r.json())['serverTime']

        # Get account balance
        print("\n  Fetching account balance...")
        params = sign({'timestamp': server_time, 'recvWindow': 10000})
        async with session.get(f'{URL}/fapi/v2/account', params=params, headers=headers) as r:
            account = await r.json()
            initial_balance = float(account['totalWalletBalance'])
            available = float(account['availableBalance'])
            print(f"  Total Balance:     ${initial_balance:,.2f}")
            print(f"  Available Balance: ${available:,.2f}")

        # Get SOL price
        print("\n  Fetching SOL price...")
        async with session.get(f'{URL}/fapi/v1/ticker/24hr', params={'symbol': 'SOLUSDT'}) as r:
            ticker = await r.json()
            sol_price = float(ticker['lastPrice'])
            print(f"  SOL/USDT: ${sol_price:.2f}")

        # Calculate position size (demo requires whole units, min 1 SOL)
        size = 1  # 1 SOL = ~$138 notional
        actual_notional = size * sol_price

        print(f"\n  Placing test LONG order:")
        print(f"  +--------------------------+")
        print(f"  | Symbol     | SOLUSDT")
        print(f"  | Side       | BUY (LONG)")
        print(f"  | Size       | {size}")
        print(f"  | Notional   | ${actual_notional:.2f}")
        print(f"  | Type       | MARKET")
        print(f"  +--------------------------+")

        # Place market buy order
        print("\n  Placing order...")
        server_time += 100
        order_params = {
            'symbol': 'SOLUSDT',
            'side': 'BUY',
            'type': 'MARKET',
            'quantity': size,
            'timestamp': server_time,
            'recvWindow': 10000
        }
        order_params = sign(order_params)

        async with session.post(f'{URL}/fapi/v1/order', data=order_params, headers=headers) as r:
            order = await r.json()
            if r.status == 200:
                print(f"\n  ORDER RESULT:")
                print(f"  +--------------------------+")
                print(f"  | Order ID   | {order.get('orderId', 'N/A')}")
                print(f"  | Status     | {order.get('status', 'N/A')}")
                print(f"  | Fill Price | ${float(order.get('avgPrice', 0)):.2f}")
                print(f"  +--------------------------+")
            else:
                print(f"  [ERROR] Order failed: {order}")
                return False

        # Wait for settlement
        await asyncio.sleep(2)

        # Check position
        print("\n  Checking position...")
        server_time += 100
        params = sign({'timestamp': server_time, 'recvWindow': 10000})
        async with session.get(f'{URL}/fapi/v2/positionRisk', params=params, headers=headers) as r:
            positions = await r.json()
            sol_pos = next((p for p in positions if p['symbol'] == 'SOLUSDT' and float(p['positionAmt']) != 0), None)

            if sol_pos:
                pos_size = float(sol_pos['positionAmt'])
                entry = float(sol_pos['entryPrice'])
                pnl = float(sol_pos['unRealizedProfit'])
                print(f"\n  POSITION OPENED:")
                print(f"  +--------------------------+")
                print(f"  | Symbol     | SOLUSDT")
                print(f"  | Side       | {'LONG' if pos_size > 0 else 'SHORT'}")
                print(f"  | Size       | {abs(pos_size)}")
                print(f"  | Entry      | ${entry:.2f}")
                print(f"  | PnL        | ${pnl:+.2f}")
                print(f"  +--------------------------+")

                # Close position
                print("\n  Closing position (market sell)...")
                server_time += 100
                close_params = {
                    'symbol': 'SOLUSDT',
                    'side': 'SELL',
                    'type': 'MARKET',
                    'quantity': abs(pos_size),
                    'reduceOnly': 'true',
                    'timestamp': server_time,
                    'recvWindow': 10000
                }
                close_params = sign(close_params)

                async with session.post(f'{URL}/fapi/v1/order', data=close_params, headers=headers) as r:
                    close_order = await r.json()
                    if r.status == 200:
                        print(f"\n  CLOSE ORDER RESULT:")
                        print(f"  +--------------------------+")
                        print(f"  | Order ID   | {close_order.get('orderId', 'N/A')}")
                        print(f"  | Status     | {close_order.get('status', 'N/A')}")
                        print(f"  | Fill Price | ${float(close_order.get('avgPrice', 0)):.2f}")
                        print(f"  +--------------------------+")
                    else:
                        print(f"  [ERROR] Close failed: {close_order}")
            else:
                print("  No position found (order may not have filled)")

        # Wait for settlement
        await asyncio.sleep(2)

        # Final balance
        print("\n  Checking final balance...")
        server_time += 100
        params = sign({'timestamp': server_time, 'recvWindow': 10000})
        async with session.get(f'{URL}/fapi/v2/account', params=params, headers=headers) as r:
            account = await r.json()
            final_balance = float(account['totalWalletBalance'])
            pnl = final_balance - initial_balance

            print(f"\n  FINAL SUMMARY:")
            print(f"  +--------------------------+")
            print(f"  | Initial    | ${initial_balance:,.2f}")
            print(f"  | Final      | ${final_balance:,.2f}")
            print(f"  | PnL        | ${pnl:+.2f}")
            print(f"  +--------------------------+")

        print("\n" + "=" * 60)
        print("  DEMO TRADE TEST COMPLETE - SUCCESS")
        print("=" * 60)

        return True


if __name__ == "__main__":
    success = asyncio.run(demo_trade())
    exit(0 if success else 1)
