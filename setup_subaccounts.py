#!/usr/bin/env python3
"""Interactive Setup Wizard for WickTrader Multi-Strategy Subaccounts.

This wizard helps configure multiple exchange subaccounts to run different
strategies concurrently. Supports both Binance and Bybit exchanges.

Usage:
    python setup_subaccounts.py
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

import yaml

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from bot.run_bot import STRATEGY_PRESETS


def print_header():
    """Print wizard header."""
    print("\n" + "=" * 70)
    print("  WICKTRADER MULTI-STRATEGY SUBACCOUNT SETUP")
    print("=" * 70)
    print("\n  This wizard will help you configure multiple strategies")
    print("  to run concurrently on separate exchange subaccounts.\n")


def get_exchange_selection() -> str:
    """Get exchange selection at the start."""
    print("  " + "=" * 50)
    print("  STEP 1: SELECT YOUR EXCHANGE")
    print("  " + "=" * 50)
    print("\n  Which exchange do you want to use?\n")
    print("    1. Binance Futures")
    print("    2. Bybit Perpetuals")
    print()

    while True:
        choice = input("  Enter 1 or 2: ").strip()
        if choice == '1':
            print("\n  Selected: BINANCE\n")
            return 'binance'
        elif choice == '2':
            print("\n  Selected: BYBIT\n")
            return 'bybit'
        else:
            print("  Please enter 1 or 2\n")


def print_strategies():
    """Print available strategies with performance data."""
    print("  AVAILABLE STRATEGIES (from REAL 864-variant backtest)")
    print("  " + "-" * 60)

    for i, (key, preset) in enumerate(STRATEGY_PRESETS.items(), 1):
        settings = preset['settings']
        direction = settings['direction'].upper()

        print(f"\n  {i}. [{key}]")
        print(f"     {preset['name']}")
        print(f"     Direction: {direction} | Return: {preset['return']} | Max DD: {preset['max_dd']}")
        print(f"     Win Rate: ~{80 if direction == 'SHORT' else 62.5}% | Trades/Year: ~{5 if direction == 'SHORT' else 8}")

    print()


def get_strategy_selection() -> List[str]:
    """Get user's strategy selection."""
    print("  Which strategies do you want to run?")
    print("  Enter numbers separated by commas (e.g., 1,2) or 'all'\n")

    strategy_names = list(STRATEGY_PRESETS.keys())

    while True:
        selection = input("  Your selection: ").strip().lower()

        if selection == 'all':
            return strategy_names

        try:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
            selected = [strategy_names[i] for i in indices if 0 <= i < len(strategy_names)]

            if selected:
                return selected
            else:
                print("  Invalid selection. Try again.\n")
        except (ValueError, IndexError):
            print("  Invalid input. Enter numbers like '1,2,3' or 'all'\n")


def get_subaccount_credentials(strategy_name: str, preset: Dict, exchange: str) -> Dict[str, Any]:
    """Get subaccount credentials for a strategy."""
    direction = preset['settings']['direction'].upper()

    print(f"\n  " + "-" * 50)
    print(f"  Configure [{strategy_name}] - {direction}")
    print(f"  Exchange: {exchange.upper()}")
    print(f"  Expected: {preset['return']} return, {preset['max_dd']} max DD")
    print(f"  " + "-" * 50)

    # Show exchange-specific instructions
    if exchange == 'binance':
        print(f"\n  Steps to create subaccount on Binance:")
        print(f"  1. Log in to Binance")
        print(f"  2. Go to: Wallet -> Subaccounts")
        print(f"  3. Create subaccount named: WickTrader-{strategy_name}")
        print(f"  4. Enable Futures trading for the subaccount")
        print(f"  5. Generate API keys with Futures permission")
        print(f"  6. Transfer funds to the subaccount\n")
    else:
        print(f"\n  Steps to create subaccount on Bybit:")
        print(f"  1. Log in to Bybit")
        print(f"  2. Go to: Assets -> Sub Account")
        print(f"  3. Create subaccount named: WickTrader-{strategy_name}")
        print(f"  4. Generate API keys with Contract permission")
        print(f"  5. Transfer funds to the subaccount\n")

    api_key = input("  API Key (or 'skip' to configure later): ").strip()

    if api_key.lower() == 'skip':
        return {
            "name": f"WickTrader-{strategy_name}",
            "exchange": exchange,
            "api_key": "",
            "api_secret": "",
            "testnet": True
        }

    api_secret = input("  API Secret: ").strip()

    # Ask about testnet
    use_testnet = input("  Use testnet (demo)? [Y/n]: ").strip().lower()
    testnet = use_testnet != 'n'

    if not testnet:
        print("\n  WARNING: You selected MAINNET (real money)")
        confirm = input("  Type 'MAINNET' to confirm: ").strip()
        if confirm != 'MAINNET':
            print("  Defaulting to testnet for safety.")
            testnet = True

    return {
        "name": f"WickTrader-{strategy_name}",
        "exchange": exchange,
        "api_key": api_key,
        "api_secret": api_secret,
        "testnet": testnet
    }


def get_scheduler_config(selected_strategies: List[str]) -> Dict[str, Any]:
    """Get scheduler configuration."""
    print("\n  " + "=" * 50)
    print("  STRATEGY SCHEDULER (Optional)")
    print("  " + "=" * 50)
    print("\n  The scheduler can automatically start/stop strategies")
    print("  based on time of day (e.g., only trade during market hours).\n")

    use_scheduler = input("  Enable time-based scheduler? [y/N]: ").strip().lower()

    if use_scheduler != 'y':
        return {"enabled": False}

    scheduler_config = {
        "enabled": True,
        "mode": "time_based",
        "timezone": "UTC",
        "time_schedules": {}
    }

    for strategy in selected_strategies:
        print(f"\n  Schedule for [{strategy}]:")

        always_on = input("    Run 24/7? [Y/n]: ").strip().lower()

        if always_on != 'n':
            scheduler_config["time_schedules"][strategy] = {
                "always_on": True
            }
        else:
            hours = input("    Active hours (e.g., 08:00-20:00): ").strip()
            days_input = input("    Active days (e.g., mon,tue,wed,thu,fri): ").strip()
            days = [d.strip() for d in days_input.split(',')]

            scheduler_config["time_schedules"][strategy] = {
                "hours": hours,
                "days": days
            }

    return scheduler_config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    config_path = project_root / "config" / "strategies.yaml"

    # Ensure config directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Add header comment
    header = """# Multi-Strategy Configuration for WickTrader
# Generated by setup_subaccounts.py
#
# WARNING: This file contains API credentials!
# Add to .gitignore if not already present.
#
# Run with: python -m bot.run_bot --multi

"""

    with open(config_path, 'w') as f:
        f.write(header)
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Configuration saved to: {config_path}")


def main():
    """Main wizard entry point."""
    print_header()

    # STEP 1: Get exchange selection FIRST
    exchange = get_exchange_selection()

    # Check for existing config
    config_path = project_root / "config" / "strategies.yaml"
    if config_path.exists():
        print(f"  Existing config found: {config_path}")
        overwrite = input("  Overwrite? [y/N]: ").strip().lower()
        if overwrite != 'y':
            print("\n  Keeping existing configuration.")
            print("  Edit config/strategies.yaml manually if needed.\n")
            return

    # STEP 2: Show available strategies
    print("  " + "=" * 50)
    print("  STEP 2: SELECT STRATEGIES")
    print("  " + "=" * 50)
    print_strategies()

    # Get strategy selection
    selected = get_strategy_selection()
    print(f"\n  Selected: {', '.join(selected)}")
    print(f"  Exchange: {exchange.upper()}")

    # Build configuration
    config = {
        "strategies": {},
        "global": {
            "max_concurrent_strategies": 5,
            "health_check_interval": 60,
            "discord_webhook": ""
        }
    }

    # STEP 3: Get credentials for each strategy
    print("\n  " + "=" * 50)
    print("  STEP 3: ENTER API CREDENTIALS")
    print("  " + "=" * 50)

    for strategy_name in selected:
        preset = STRATEGY_PRESETS[strategy_name]
        subaccount = get_subaccount_credentials(strategy_name, preset, exchange)

        config["strategies"][strategy_name] = {
            "enabled": bool(subaccount["api_key"]),  # Enable if credentials provided
            "subaccount": subaccount
        }

    # Add all other strategies as disabled (using selected exchange)
    for name in STRATEGY_PRESETS:
        if name not in config["strategies"]:
            config["strategies"][name] = {
                "enabled": False,
                "subaccount": {
                    "name": f"WickTrader-{name}",
                    "exchange": exchange,
                    "api_key": "",
                    "api_secret": "",
                    "testnet": True
                }
            }

    # Get scheduler config
    scheduler_config = get_scheduler_config(selected)
    config["scheduler"] = scheduler_config

    # Save configuration
    save_config(config)

    # Print summary
    print("\n" + "=" * 70)
    print("  SETUP COMPLETE")
    print("=" * 70)

    enabled_count = sum(1 for s in config["strategies"].values() if s["enabled"])
    print(f"\n  Strategies configured: {len(selected)}")
    print(f"  Strategies enabled: {enabled_count}")

    if scheduler_config.get("enabled"):
        print(f"  Scheduler: ENABLED")
    else:
        print(f"  Scheduler: DISABLED")

    print("\n  NEXT STEPS:")
    print("  " + "-" * 40)

    if enabled_count == 0:
        print("  1. Edit config/strategies.yaml to add API credentials")
        print("  2. Set 'enabled: true' for strategies you want to run")

    print(f"  {'1' if enabled_count > 0 else '3'}. Run: python -m bot.run_bot --multi")
    print(f"  {'2' if enabled_count > 0 else '4'}. Or run with scheduler: python -m bot.run_bot --multi --scheduler")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
