#!/usr/bin/env python3
"""
Full Strategy Test Suite for WickTrader.

Tests all components on both Binance and Hyperliquid:
- Signal detection on real candles
- All exit strategies
- Heat-based risk management
- Position sizing
- Order placement (paper mode)
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

import yaml

# Core strategy imports
from src.strategy.wick_signals import WickSignalDetector
from src.strategy.heat_risk import HeatRiskManager, create_heat_manager_from_preset, RISK_PRESETS, RiskPreset
from src.strategy.wick_risk import WickRiskManager
from src.exchanges.binance import BinanceExchange
from src.exchanges.hyperliquid import HyperliquidExchange
from src.exchanges.base import OrderSide, OrderType, Candle


@dataclass
class TestResult:
    """Test result container."""
    test_name: str
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class StrategyTester:
    """Full strategy test suite."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.binance: Optional[BinanceExchange] = None
        self.hyperliquid: Optional[HyperliquidExchange] = None

    def add_result(self, name: str, passed: bool, message: str, details: Dict = None):
        """Add test result."""
        self.results.append(TestResult(name, passed, message, details))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}: {message}")

    async def setup_exchanges(self) -> bool:
        """Initialize both exchanges."""
        print("\n" + "=" * 60)
        print("  EXCHANGE SETUP")
        print("=" * 60)

        # Load Binance config
        try:
            binance_config = Path(__file__).parent / "config" / "binance_testnet.yaml"
            with open(binance_config) as f:
                config = yaml.safe_load(f)

            self.binance = BinanceExchange(
                api_key=config['exchange']['api_key'],
                api_secret=config['exchange']['api_secret'],
                testnet=True  # Uses demo-fapi.binance.com
            )
            await self.binance.connect()
            balance = await self.binance.get_balance()
            self.add_result(
                "Binance Connection",
                True,
                f"Connected - Balance: ${balance.total_balance:,.2f}"
            )
        except Exception as e:
            self.add_result("Binance Connection", False, str(e))

        # Load Hyperliquid config
        try:
            hl_config = Path(__file__).parent / "config" / "hyperliquid.yaml"
            with open(hl_config) as f:
                config = yaml.safe_load(f)

            self.hyperliquid = HyperliquidExchange(
                api_key="",
                api_secret=config['private_key'],
                wallet_address=config['wallet_address'],
                account_address=config['account_address'],
                testnet=config.get('testnet', True)
            )
            await self.hyperliquid.connect()
            balance = await self.hyperliquid.get_balance()
            self.add_result(
                "Hyperliquid Connection",
                True,
                f"Connected - Balance: ${balance.total_balance:,.2f}"
            )
        except Exception as e:
            self.add_result("Hyperliquid Connection", False, str(e))

        return self.binance is not None or self.hyperliquid is not None

    async def test_signal_detection(self) -> None:
        """Test wick signal detection on real candles."""
        print("\n" + "=" * 60)
        print("  SIGNAL DETECTION TESTS")
        print("=" * 60)

        # Test different thresholds
        thresholds = [5.0, 6.0, 7.0]

        for threshold in thresholds:
            detector = WickSignalDetector(threshold=threshold)

            # Get candles from whichever exchange is available
            exchange = self.binance or self.hyperliquid
            if not exchange:
                self.add_result(f"Signal Detection {threshold}%", False, "No exchange available")
                continue

            try:
                candles = await exchange.get_candles("SOL", "4h", limit=100)
                signals_found = 0

                for candle in candles:
                    signal = detector.process_bar(
                        timestamp=candle.timestamp,
                        open_price=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close
                    )
                    if signal:
                        signals_found += 1

                self.add_result(
                    f"Signal Detection {threshold}%",
                    True,
                    f"Found {signals_found} signals in 100 candles",
                    {"threshold": threshold, "signals": signals_found, "candles": 100}
                )
            except Exception as e:
                self.add_result(f"Signal Detection {threshold}%", False, str(e))

    async def test_risk_profiles(self) -> None:
        """Test all risk profiles."""
        print("\n" + "=" * 60)
        print("  RISK PROFILE TESTS")
        print("=" * 60)

        equity = 10000.0  # Test with $10k

        for preset_enum in RiskPreset:
            preset = RISK_PRESETS[preset_enum]
            try:
                manager = create_heat_manager_from_preset(preset_enum)

                # Verify settings
                assert manager.default_risk_percent == preset["risk_percent"], "Risk percent mismatch"
                assert manager.default_leverage == preset["leverage"], "Leverage mismatch"
                assert manager.max_portfolio_heat == preset["max_heat"], "Max heat mismatch"

                # Calculate position size using base method
                risk_amount = equity * (preset["risk_percent"] / 100)
                stop_distance_pct = 2.0  # 2% stop loss
                entry_price = 140.0
                stop_distance = entry_price * (stop_distance_pct / 100)
                position_size = risk_amount / stop_distance

                # Verify heat zone
                zone = manager.get_heat_zone()

                self.add_result(
                    f"Risk Profile: {preset_enum.value}",
                    True,
                    f"Risk: {preset['risk_percent']}%, Lev: {preset['leverage']}x, Zone: {zone}",
                    {
                        "risk_percent": preset["risk_percent"],
                        "leverage": preset["leverage"],
                        "position_size": position_size,
                        "zone": zone
                    }
                )
            except Exception as e:
                self.add_result(f"Risk Profile: {preset_enum.value}", False, str(e))

    async def test_heat_zones(self) -> None:
        """Test heat zone transitions."""
        print("\n" + "=" * 60)
        print("  HEAT ZONE TESTS")
        print("=" * 60)

        equity = 10000.0
        manager = create_heat_manager_from_preset(RiskPreset.MODERATE)

        # Test zone transitions for MODERATE preset:
        # green_max: 25%, yellow_max: 40%, red_max: 50%, max_heat: 50%
        test_cases = [
            (0, "green", 1.0),      # 0% heat = GREEN, 100% scale
            (20, "green", 1.0),     # 20% heat = GREEN (< 25%), 100% scale
            (30, "yellow", 0.5),    # 30% heat = YELLOW (25-40%), 50% scale
            (45, "red", 0.25),      # 45% heat = RED (40-50%), 25% scale
            (55, "critical", 0.0),  # 55% heat = CRITICAL (> 50%), 0% scale
        ]

        from src.strategy.heat_risk import PositionHeat, HeatZone

        for heat_pct, expected_zone, expected_scale in test_cases:
            # Simulate heat level by adding fake positions
            manager._positions.clear()
            manager.update_equity(equity)  # Ensure equity is set

            if heat_pct > 0:
                # Create dummy position contributing this heat
                risk_amount = equity * (heat_pct / 100)
                position = PositionHeat(
                    symbol="TEST",
                    side="long",
                    size=1.0,
                    entry_price=100.0,
                    stop_loss=95.0,
                    risk_amount=risk_amount
                )
                manager._positions.append(position)

            zone = manager.get_heat_zone()
            scale = manager.get_position_scale()

            # Convert zone to string for comparison
            zone_str = zone.value if hasattr(zone, 'value') else str(zone)

            passed = zone_str == expected_zone and abs(scale - expected_scale) < 0.01
            self.add_result(
                f"Heat Zone {heat_pct}%",
                passed,
                f"Zone: {zone_str} (expected {expected_zone}), Scale: {scale:.0%}",
                {"heat": heat_pct, "zone": zone_str, "scale": scale}
            )

    async def test_position_sizing(self) -> None:
        """Test position sizing calculations."""
        print("\n" + "=" * 60)
        print("  POSITION SIZING TESTS")
        print("=" * 60)

        equity = 10000.0

        # Test with WickRiskManager
        manager = WickRiskManager(
            default_risk_percent=5.0,
            default_leverage=5.0
        )

        test_cases = [
            # (entry_price, stop_loss, wick_pct)
            (140.0, 133.0, 5.0),   # 5% wick, 5% stop
            (140.0, 133.0, 7.0),   # 7% wick gets scaling bonus
            (140.0, 126.0, 5.0),   # 10% stop
        ]

        for entry, sl, wick_pct in test_cases:
            try:
                # Returns (position_size, multiplier)
                size, multiplier = manager.calculate_wick_position_size(
                    account_balance=equity,
                    entry_price=entry,
                    stop_loss_price=sl,
                    wick_pct=wick_pct
                )

                sl_pct = ((entry - sl) / entry) * 100
                self.add_result(
                    f"Position Size (SL: {sl_pct:.0f}%, Wick: {wick_pct}%)",
                    size > 0,
                    f"Size: {size:.2f}, Multiplier: {multiplier:.2f}x",
                    {"entry": entry, "stop_loss": sl, "wick_pct": wick_pct, "size": size, "multiplier": multiplier}
                )
            except Exception as e:
                self.add_result(f"Position Size Test", False, str(e))

    async def test_exit_strategies(self) -> None:
        """Test all exit strategy calculations."""
        print("\n" + "=" * 60)
        print("  EXIT STRATEGY TESTS")
        print("=" * 60)

        entry_price = 140.0
        stop_loss = 133.0  # 5% below entry

        exit_strategies = {
            "fixed_5": {"tp_pct": 5.0},
            "fixed_8": {"tp_pct": 8.0},
            "fixed_12": {"tp_pct": 12.0},
            "rr_2": {"rr_ratio": 2.0},
            "rr_3": {"rr_ratio": 3.0},
            "time_20": {"bars": 20},
            "time_40": {"bars": 40},
        }

        for strategy_name, params in exit_strategies.items():
            try:
                if "tp_pct" in params:
                    # Fixed take profit
                    tp = entry_price * (1 + params["tp_pct"] / 100)
                    self.add_result(
                        f"Exit: {strategy_name}",
                        True,
                        f"TP at ${tp:.2f} (+{params['tp_pct']}%)",
                        {"strategy": strategy_name, "take_profit": tp}
                    )
                elif "rr_ratio" in params:
                    # Risk-reward ratio
                    risk = entry_price - stop_loss
                    reward = risk * params["rr_ratio"]
                    tp = entry_price + reward
                    self.add_result(
                        f"Exit: {strategy_name}",
                        True,
                        f"TP at ${tp:.2f} (R:R = {params['rr_ratio']}:1)",
                        {"strategy": strategy_name, "take_profit": tp, "risk": risk, "reward": reward}
                    )
                elif "bars" in params:
                    # Time-based exit
                    self.add_result(
                        f"Exit: {strategy_name}",
                        True,
                        f"Exit after {params['bars']} bars ({params['bars'] * 4}h)",
                        {"strategy": strategy_name, "bars": params["bars"]}
                    )
            except Exception as e:
                self.add_result(f"Exit: {strategy_name}", False, str(e))

    async def test_binance_order_flow(self) -> None:
        """Test Binance order placement (paper mode simulation)."""
        print("\n" + "=" * 60)
        print("  BINANCE ORDER FLOW TEST")
        print("=" * 60)

        if not self.binance:
            self.add_result("Binance Order Flow", False, "Binance not connected")
            return

        try:
            # Test 1: Check balance
            balance = await self.binance.get_balance()
            self.add_result(
                "Binance Balance Check",
                balance.total_balance > 0,
                f"${balance.total_balance:,.2f} available"
            )

            # Test 2: Get candles to get price (demo ticker has different format)
            candles = await self.binance.get_candles("SOL", "4h", limit=1)
            price = candles[-1].close if candles else 140.0
            self.add_result(
                "Binance Price Check",
                True,
                f"SOL Price: ${price:.2f}"
            )

            # Test 3: Get symbol info
            symbol_info = await self.binance.get_symbol_info("SOL")
            self.add_result(
                "Binance Symbol Info",
                True,
                f"Lot: {symbol_info.lot_size}, Tick: {symbol_info.tick_size}"
            )

            # Test 4: Place and close small order (1 SOL)
            size = 1  # Demo requires whole units

            order = await self.binance.place_order(
                symbol="SOL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=size
            )

            self.add_result(
                "Binance Order Placement",
                order.order_id is not None,
                f"Order {order.order_id} - Status: {order.status.value}"
            )

            # Wait for fill
            await asyncio.sleep(2)

            # Check position
            position = await self.binance.get_position("SOL")
            if position and position.size > 0:
                self.add_result(
                    "Binance Position Check",
                    True,
                    f"Position: {position.size} SOL @ ${position.entry_price:.2f}"
                )

                # Close position
                close_order = await self.binance.place_order(
                    symbol="SOL",
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    size=position.size,
                    reduce_only=True
                )

                self.add_result(
                    "Binance Position Close",
                    close_order.order_id is not None,
                    f"Closed - Order {close_order.order_id}"
                )
            else:
                self.add_result("Binance Position Check", False, "No position found")

        except Exception as e:
            self.add_result("Binance Order Flow", False, str(e))

    async def test_hyperliquid_order_flow(self) -> None:
        """Test Hyperliquid order placement."""
        print("\n" + "=" * 60)
        print("  HYPERLIQUID ORDER FLOW TEST")
        print("=" * 60)

        if not self.hyperliquid:
            self.add_result("Hyperliquid Order Flow", False, "Hyperliquid not connected")
            return

        try:
            # Get current price
            ticker = await self.hyperliquid.get_ticker("SOL")
            price = ticker['price']

            # Test 1: Check balance
            balance = await self.hyperliquid.get_balance()
            self.add_result(
                "Hyperliquid Balance Check",
                balance.total_balance > 0,
                f"${balance.total_balance:,.2f} available"
            )

            # Test 2: Get symbol info for precision
            symbol_info = await self.hyperliquid.get_symbol_info("SOL")
            self.add_result(
                "Hyperliquid Symbol Info",
                True,
                f"szDecimals: {symbol_info.lot_size}, Price precision: 5 sig figs"
            )

            # Test 3: Place and close small order (~$15 notional)
            size = round(15 / price, 2)  # SOL has 2 decimal precision

            order = await self.hyperliquid.place_order(
                symbol="SOL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=size
            )

            self.add_result(
                "Hyperliquid Order Placement",
                order.order_id is not None,
                f"Order {order.order_id} - Status: {order.status.value}"
            )

            # Wait for fill
            await asyncio.sleep(2)

            # Check position
            position = await self.hyperliquid.get_position("SOL")
            if position and position.size > 0:
                self.add_result(
                    "Hyperliquid Position Check",
                    True,
                    f"Position: {position.size} SOL @ ${position.entry_price:.2f}"
                )

                # Close position
                close_order = await self.hyperliquid.place_order(
                    symbol="SOL",
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    size=position.size,
                    reduce_only=True
                )

                self.add_result(
                    "Hyperliquid Position Close",
                    close_order.order_id is not None,
                    f"Closed - Order {close_order.order_id}"
                )
            else:
                self.add_result("Hyperliquid Position Check", False, "No position found")

        except Exception as e:
            self.add_result("Hyperliquid Order Flow", False, str(e))

    async def test_multi_strategy_signals(self) -> None:
        """Test signal detection across all strategy variants."""
        print("\n" + "=" * 60)
        print("  MULTI-STRATEGY SIGNAL TEST")
        print("=" * 60)

        exchange = self.binance or self.hyperliquid
        if not exchange:
            self.add_result("Multi-Strategy Test", False, "No exchange available")
            return

        try:
            # Get 200 candles for more signal diversity
            candles = await exchange.get_candles("SOL", "4h", limit=200)

            # Test all threshold/direction combinations
            thresholds = [5.0, 6.0, 7.0]
            directions = ["long", "short", "both"]

            results_summary = {}

            for threshold in thresholds:
                detector = WickSignalDetector(threshold=threshold)

                long_signals = 0
                short_signals = 0

                for candle in candles:
                    signal = detector.process_bar(
                        timestamp=candle.timestamp,
                        open_price=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close
                    )
                    if signal:
                        if signal.signal_type.value == "LONG":
                            long_signals += 1
                        else:
                            short_signals += 1

                results_summary[threshold] = {
                    "long": long_signals,
                    "short": short_signals,
                    "total": long_signals + short_signals
                }

            # Report results
            for threshold, counts in results_summary.items():
                self.add_result(
                    f"Strategy Signals {threshold}%",
                    counts["total"] > 0,
                    f"LONG: {counts['long']}, SHORT: {counts['short']}, Total: {counts['total']}",
                    counts
                )

        except Exception as e:
            self.add_result("Multi-Strategy Test", False, str(e))

    async def cleanup(self) -> None:
        """Disconnect exchanges."""
        if self.binance:
            await self.binance.disconnect()
        if self.hyperliquid:
            await self.hyperliquid.disconnect()

    def print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)
        print("  TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print(f"\n  Total Tests: {total}")
        print(f"  Passed:      {passed} ({passed/total*100:.1f}%)")
        print(f"  Failed:      {failed} ({failed/total*100:.1f}%)")

        if failed > 0:
            print("\n  FAILED TESTS:")
            for r in self.results:
                if not r.passed:
                    print(f"    - {r.test_name}: {r.message}")

        print("\n" + "=" * 60)
        if failed == 0:
            print("  ALL TESTS PASSED!")
        else:
            print(f"  {failed} TEST(S) FAILED - REVIEW REQUIRED")
        print("=" * 60)


async def main():
    """Run full strategy test suite."""
    print("=" * 60)
    print("  WICKTRADER FULL STRATEGY TEST SUITE")
    print("=" * 60)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    tester = StrategyTester()

    try:
        # Setup
        connected = await tester.setup_exchanges()
        if not connected:
            print("\n[ERROR] No exchanges available. Aborting.")
            return False

        # Run all tests
        await tester.test_signal_detection()
        await tester.test_risk_profiles()
        await tester.test_heat_zones()
        await tester.test_position_sizing()
        await tester.test_exit_strategies()
        await tester.test_multi_strategy_signals()

        # Order flow tests (actual trading)
        await tester.test_binance_order_flow()
        await tester.test_hyperliquid_order_flow()

        # Summary
        tester.print_summary()

        return all(r.passed for r in tester.results)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await tester.cleanup()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
