#!/usr/bin/env python3
"""Test Hyperliquid connection and display account info."""

import asyncio
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

import yaml
from src.exchanges.hyperliquid import HyperliquidExchange


async def test_connection():
    """Test Hyperliquid connection."""
    print("=" * 60)
    print("  HYPERLIQUID CONNECTION TEST")
    print("=" * 60)

    # Load config
    config_path = Path(__file__).parent / "config" / "hyperliquid.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    print(f"\n  Main Wallet:  {config['account_address'][:10]}...{config['account_address'][-6:]}")
    print(f"  API Wallet:   {config['wallet_address'][:10]}...{config['wallet_address'][-6:]}")
    print(f"  Network:      {'TESTNET' if config['testnet'] else 'MAINNET'}")

    # Create exchange
    exchange = HyperliquidExchange(
        api_key="",
        api_secret=config['private_key'],
        wallet_address=config['wallet_address'],
        account_address=config['account_address'],
        testnet=config['testnet']
    )

    try:
        print("\n  Connecting...")
        connected = await exchange.connect()

        if not connected:
            print("  [ERROR] Connection failed!")
            return False

        print("  [OK] Connected to Hyperliquid")

        # Get balance
        print("\n  Fetching account balance...")
        balance = await exchange.get_balance()

        print(f"\n  ACCOUNT BALANCE:")
        print(f"  +--------------------------+")
        print(f"  | Total Balance | ${balance.total_balance:,.2f}")
        print(f"  | Available     | ${balance.available_balance:,.2f}")
        print(f"  | Used Margin   | ${balance.used_margin:,.2f}")
        print(f"  | Unrealized PnL| ${balance.unrealized_pnl:+,.2f}")
        print(f"  +--------------------------+")

        # Get positions
        print("\n  Fetching positions...")
        positions = await exchange.get_positions()

        if positions:
            print(f"\n  OPEN POSITIONS ({len(positions)}):")
            for pos in positions:
                print(f"  | {pos.symbol} | {pos.side.value} | Size: {pos.size} | Entry: ${pos.entry_price:.2f} | PnL: ${pos.unrealized_pnl:+,.2f}")
        else:
            print("  No open positions")

        # Get SOL price
        print("\n  Fetching SOL price...")
        ticker = await exchange.get_ticker("SOL")
        print(f"  SOL/USD: ${ticker['price']:.2f}")

        # Get recent candles
        print("\n  Fetching recent 4H candles...")
        candles = await exchange.get_candles("SOL", "4h", limit=5)

        print(f"\n  RECENT SOL 4H CANDLES:")
        print(f"  {'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}")
        print(f"  {'-'*62}")
        for c in candles[-5:]:
            print(f"  {str(c.timestamp):<20} {c.open:>10.2f} {c.high:>10.2f} {c.low:>10.2f} {c.close:>10.2f}")

        # Check for wick signals in recent candles
        print("\n  Checking for wick signals (5% threshold)...")
        for c in candles[-5:]:
            candle_range = c.high - c.low
            if candle_range > 0:
                lower_wick = (min(c.open, c.close) - c.low) / candle_range * 100
                upper_wick = (c.high - max(c.open, c.close)) / candle_range * 100

                if lower_wick >= 5:
                    print(f"  [SIGNAL] {c.timestamp} - Lower wick: {lower_wick:.1f}% (LONG)")
                elif upper_wick >= 5:
                    print(f"  [SIGNAL] {c.timestamp} - Upper wick: {upper_wick:.1f}% (SHORT)")

        print("\n" + "=" * 60)
        print("  CONNECTION TEST COMPLETE")
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
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
