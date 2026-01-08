#!/usr/bin/env python3
"""Demo trading test on Hyperliquid testnet.

Places a small market order to verify the full trading flow works.
"""

import asyncio
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

import yaml
from src.exchanges.hyperliquid import HyperliquidExchange
from src.exchanges.base import OrderSide, OrderType


async def demo_trade():
    """Execute a demo trade on Hyperliquid testnet."""
    print("=" * 60)
    print("  HYPERLIQUID DEMO TRADING TEST")
    print("=" * 60)
    print("  WARNING: This will place a REAL order on TESTNET")
    print("=" * 60)

    # Load config
    config_path = Path(__file__).parent / "config" / "hyperliquid.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not config.get('testnet', True):
        print("\n  [ABORT] This test is for TESTNET only!")
        print("  Set testnet: true in config/hyperliquid.yaml")
        return False

    print(f"\n  Main Wallet:  {config['account_address'][:10]}...{config['account_address'][-6:]}")
    print(f"  API Wallet:   {config['wallet_address'][:10]}...{config['wallet_address'][-6:]}")
    print(f"  Network:      TESTNET")

    # Create exchange
    exchange = HyperliquidExchange(
        api_key="",
        api_secret=config['private_key'],
        wallet_address=config['wallet_address'],
        account_address=config['account_address'],
        testnet=True
    )

    try:
        # Connect
        print("\n  Connecting...")
        connected = await exchange.connect()
        if not connected:
            print("  [ERROR] Connection failed!")
            return False
        print("  [OK] Connected to Hyperliquid testnet")

        # Get initial balance
        print("\n  Fetching initial balance...")
        balance = await exchange.get_balance()
        print(f"  Initial Balance: ${balance.total_balance:,.2f}")
        print(f"  Available:       ${balance.available_balance:,.2f}")

        # Get SOL price
        ticker = await exchange.get_ticker("SOL")
        sol_price = ticker['price']
        print(f"\n  SOL Price: ${sol_price:.2f}")

        # Calculate small position size (~$15-20 notional)
        # Minimum notional on Hyperliquid is $10, we use $15-20 to be safe
        target_notional = 15.0
        size = round(target_notional / sol_price, 2)  # Round to 2 decimals for SOL
        actual_notional = size * sol_price

        print(f"\n  Placing test LONG order:")
        print(f"  +--------------------------+")
        print(f"  | Symbol     | SOL")
        print(f"  | Side       | BUY (LONG)")
        print(f"  | Size       | {size}")
        print(f"  | Notional   | ${actual_notional:.2f}")
        print(f"  | Type       | MARKET")
        print(f"  +--------------------------+")

        # Place market buy order
        print("\n  Placing order...")
        order = await exchange.place_order(
            symbol="SOL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=size
        )

        print(f"\n  ORDER RESULT:")
        print(f"  +--------------------------+")
        print(f"  | Order ID   | {order.order_id}")
        print(f"  | Status     | {order.status.value}")
        print(f"  | Fill Price | ${order.avg_fill_price:.2f}" if order.avg_fill_price else "  | Fill Price | pending")
        print(f"  +--------------------------+")

        # Wait a moment for order to settle
        await asyncio.sleep(2)

        # Check position
        print("\n  Checking position...")
        position = await exchange.get_position("SOL")
        if position:
            print(f"\n  POSITION OPENED:")
            print(f"  +--------------------------+")
            print(f"  | Symbol     | {position.symbol}")
            print(f"  | Side       | {position.side.value}")
            print(f"  | Size       | {position.size}")
            print(f"  | Entry      | ${position.entry_price:.2f}")
            print(f"  | PnL        | ${position.unrealized_pnl:+.2f}")
            print(f"  +--------------------------+")

            # Close the position immediately
            print("\n  Closing position (market sell)...")
            close_order = await exchange.place_order(
                symbol="SOL",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                size=position.size,
                reduce_only=True
            )

            print(f"\n  CLOSE ORDER RESULT:")
            print(f"  +--------------------------+")
            print(f"  | Order ID   | {close_order.order_id}")
            print(f"  | Status     | {close_order.status.value}")
            print(f"  | Fill Price | ${close_order.avg_fill_price:.2f}" if close_order.avg_fill_price else "  | Fill Price | pending")
            print(f"  +--------------------------+")

            # Wait for close to settle
            await asyncio.sleep(2)

        # Final balance check
        print("\n  Checking final balance...")
        final_balance = await exchange.get_balance()
        pnl = final_balance.total_balance - balance.total_balance

        print(f"\n  FINAL SUMMARY:")
        print(f"  +--------------------------+")
        print(f"  | Initial    | ${balance.total_balance:,.2f}")
        print(f"  | Final      | ${final_balance.total_balance:,.2f}")
        print(f"  | PnL        | ${pnl:+.2f}")
        print(f"  +--------------------------+")

        # Verify no open positions remain
        final_positions = await exchange.get_positions()
        if final_positions:
            print(f"\n  [WARNING] {len(final_positions)} positions still open")
        else:
            print("\n  [OK] All positions closed")

        print("\n" + "=" * 60)
        print("  DEMO TRADE TEST COMPLETE - SUCCESS")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await exchange.disconnect()


if __name__ == "__main__":
    success = asyncio.run(demo_trade())
    sys.exit(0 if success else 1)
