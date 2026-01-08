#!/usr/bin/env python3
"""
WickTrader - Interactive Setup Wizard

Guides you through complete configuration:
- Exchange setup (Binance / Hyperliquid)
- Risk profile selection
- Strategy parameters
- Paper/Live mode

Usage:
    python setup_wizard.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def clear_screen():
    """Clear terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    """Print welcome banner."""
    banner = r"""
================================================================================

    __          ___      _   _______            _
    \ \        / (_)    | | |__   __|          | |
     \ \  /\  / / _  ___| | __ | |_ __ __ _  __| | ___ _ __
      \ \/  \/ / | |/ __| |/ / | | '__/ _` |/ _` |/ _ \ '__|
       \  /\  /  | | (__|   <  | | | | (_| | (_| |  __/ |
        \/  \/   |_|\___|_|\_\ |_|_|  \__,_|\__,_|\___|_|

                    WICK-BASED SOL TRADING SYSTEM
                         INTERACTIVE SETUP

================================================================================

    BACKTEST RESULTS (480 Variants Tested):

    +------------------+--------+--------+---------+
    | Risk Profile     | Return | Sharpe | Win %   |
    +------------------+--------+--------+---------+
    | Conservative     | +211%  | 1.289  | 91.7%   |
    | Moderate         | +314%  | 1.248  | 90.8%   |
    | Aggressive       | +717%  | 1.093  | 90.0%   |
    | Degen            | +1920% | 1.224  | 94.2%   |
    +------------------+--------+--------+---------+

    Multi-Exchange Support: Binance Futures + Hyperliquid

================================================================================
"""
    print(banner)


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70 + "\n")


def print_info(msg: str):
    print(f"  [*] {msg}")


def print_warning(msg: str):
    print(f"  [!] {msg}")


def print_error(msg: str):
    print(f"  [ERROR] {msg}")


def print_success(msg: str):
    print(f"  [OK] {msg}")


def get_input(prompt: str, default: str = None, required: bool = True) -> str:
    """Get user input with optional default."""
    if default:
        display = f"  {prompt} [{default}]: "
    else:
        display = f"  {prompt}: "

    while True:
        value = input(display).strip()
        if not value and default:
            return default
        if not value and required:
            print_warning("This field is required.")
            continue
        return value


def get_hidden_input(prompt: str) -> str:
    """Get password input."""
    try:
        import getpass
        return getpass.getpass(f"  {prompt}: ")
    except:
        print_warning("Hidden input not supported.")
        return input(f"  {prompt}: ").strip()


def get_float(prompt: str, default: float = None, min_val: float = None, max_val: float = None) -> float:
    """Get float input with validation."""
    while True:
        default_str = str(default) if default is not None else None
        value_str = get_input(prompt, default_str, required=True)
        try:
            value = float(value_str)
            if min_val is not None and value < min_val:
                print_warning(f"Must be at least {min_val}")
                continue
            if max_val is not None and value > max_val:
                print_warning(f"Must be at most {max_val}")
                continue
            return value
        except ValueError:
            print_warning("Enter a valid number.")


def get_int(prompt: str, default: int = None, min_val: int = None, max_val: int = None) -> int:
    """Get integer input."""
    return int(get_float(prompt, default, min_val, max_val))


def get_yes_no(prompt: str, default: bool = True) -> bool:
    """Get yes/no input."""
    default_str = "Y" if default else "N"
    while True:
        value = get_input(f"{prompt} (Y/N)", default_str).upper()
        if value in ['Y', 'YES']:
            return True
        if value in ['N', 'NO']:
            return False
        print_warning("Enter Y or N.")


def get_choice(prompt: str, options: list, default: int = 0) -> int:
    """Get choice from list."""
    print(f"\n  {prompt}")
    for i, opt in enumerate(options):
        marker = "(default)" if i == default else ""
        print(f"    [{i+1}] {opt} {marker}")
    print()

    while True:
        value = get_input("Enter choice", str(default + 1))
        try:
            choice = int(value) - 1
            if 0 <= choice < len(options):
                return choice
            print_warning(f"Enter 1-{len(options)}")
        except ValueError:
            print_warning("Enter a number.")


def validate_eth_address(address: str) -> bool:
    """Validate Ethereum address."""
    if not address or not address.startswith('0x') or len(address) != 42:
        return False
    try:
        int(address[2:], 16)
        return True
    except:
        return False


def validate_private_key(key: str) -> bool:
    """Validate private key."""
    if not key:
        return False
    clean = key[2:] if key.startswith('0x') else key
    if len(clean) != 64:
        return False
    try:
        int(clean, 16)
        return True
    except:
        return False


# ============================================================================
# Setup Steps
# ============================================================================

def step_exchange_selection() -> Dict[str, Any]:
    """Step 1: Select exchanges."""
    print_section("STEP 1: EXCHANGE SELECTION")

    print("""
    WickTrader supports multiple exchanges with automatic failover:

    BINANCE FUTURES
      - Most liquid SOL perpetual market
      - Testnet available for practice
      - Requires API key/secret

    HYPERLIQUID
      - Decentralized perpetuals (on-chain)
      - No KYC required
      - Wallet-based authentication

    You can enable both for redundancy (recommended).
    """)

    exchanges = {}

    # Binance
    exchanges['binance_enabled'] = get_yes_no("Enable Binance Futures?", default=True)

    # Hyperliquid
    exchanges['hyperliquid_enabled'] = get_yes_no("Enable Hyperliquid?", default=True)

    if not exchanges['binance_enabled'] and not exchanges['hyperliquid_enabled']:
        print_error("At least one exchange must be enabled!")
        exchanges['binance_enabled'] = True

    # Priority
    if exchanges['binance_enabled'] and exchanges['hyperliquid_enabled']:
        print()
        choice = get_choice(
            "Primary exchange for order routing:",
            ["Binance (recommended - better liquidity)", "Hyperliquid"],
            default=0
        )
        exchanges['primary'] = "binance" if choice == 0 else "hyperliquid"
        exchanges['enable_fallback'] = get_yes_no("Enable automatic failover?", default=True)
    else:
        exchanges['primary'] = "binance" if exchanges['binance_enabled'] else "hyperliquid"
        exchanges['enable_fallback'] = False

    return exchanges


def step_binance_setup() -> Dict[str, Any]:
    """Step 2a: Binance configuration."""
    print_section("STEP 2A: BINANCE FUTURES SETUP")

    print("""
    TO GET API CREDENTIALS:
    1. Go to https://www.binance.com/en/my/settings/api-management
    2. Create new API key (enable Futures trading)
    3. For testnet: https://testnet.binancefuture.com

    SECURITY:
    - Enable IP whitelist if possible
    - Only enable Futures permissions (not withdrawal)
    """)

    input("  Press ENTER when ready...")
    print()

    api_key = get_input("Binance API Key")
    api_secret = get_hidden_input("Binance API Secret")
    testnet = get_yes_no("Use Binance TESTNET? (Recommended for first run)", default=True)

    if testnet:
        print_info("Testnet mode - no real funds at risk")
    else:
        print_warning("MAINNET mode - real funds will be used!")
        if not get_yes_no("Confirm MAINNET trading?", default=False):
            testnet = True
            print_info("Switched to testnet")

    return {
        'api_key': api_key,
        'api_secret': api_secret,
        'testnet': testnet
    }


def step_hyperliquid_setup() -> Dict[str, Any]:
    """Step 2b: Hyperliquid configuration."""
    print_section("STEP 2B: HYPERLIQUID SETUP")

    print("""
    Hyperliquid uses wallet-based authentication:

    SETUP STEPS:
    1. Go to https://app.hyperliquid.xyz
    2. Connect your wallet and deposit USDC
    3. Go to API page: https://app.hyperliquid.xyz/API
    4. Generate API Wallet
    5. SAVE THE PRIVATE KEY (shown only once!)
    6. Authorize the API wallet

    The API wallet can trade but cannot withdraw funds.
    """)

    input("  Press ENTER when ready...")
    print()

    # Main wallet (for balance queries)
    while True:
        main_address = get_input("Your MAIN wallet address (0x...)")
        if validate_eth_address(main_address):
            break
        print_error("Invalid address format")

    # API wallet
    while True:
        api_address = get_input("Your API wallet address (0x...)")
        if validate_eth_address(api_address):
            break
        print_error("Invalid address format")

    # Private key
    print()
    print_warning("SECURITY: Private key will be stored locally")
    print()

    while True:
        private_key = get_hidden_input("API wallet PRIVATE KEY")
        if validate_private_key(private_key):
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            break
        print_error("Invalid private key format (64 hex chars)")

    testnet = get_yes_no("Use Hyperliquid TESTNET?", default=True)

    return {
        'main_address': main_address,
        'api_address': api_address,
        'private_key': private_key,
        'testnet': testnet
    }


def step_risk_profile() -> Dict[str, Any]:
    """Step 3: Risk profile selection."""
    print_section("STEP 3: RISK PROFILE")

    print("""
    Select your risk tolerance:

    CONSERVATIVE (Recommended for beginners)
      Risk: 3% per trade | Leverage: 3X | Max Heat: 30%
      Expected: +12% median, +33% best case, -6% worst

    MODERATE (Balanced)
      Risk: 5% per trade | Leverage: 5X | Max Heat: 50%
      Expected: +19% median, +60% best case, -11% worst

    AGGRESSIVE (Experienced traders)
      Risk: 10% per trade | Leverage: 7X | Max Heat: 70%
      Expected: +36% median, +142% best case, -23% worst

    DEGEN (Maximum risk - not recommended)
      Risk: 15% per trade | Leverage: 10X | Max Heat: 90%
      Expected: +49% median, +249% best case, -36% worst
    """)

    choice = get_choice(
        "Select risk profile:",
        ["Conservative (safest)", "Moderate (balanced)", "Aggressive", "Degen (max risk)"],
        default=0
    )

    profiles = ["conservative", "moderate", "aggressive", "degen"]
    profile = profiles[choice]

    if profile == "degen":
        print()
        print_warning("DEGEN mode has high drawdown risk!")
        print_warning("5 consecutive losses = 56% drawdown")
        if not get_yes_no("Are you SURE about Degen mode?", default=False):
            profile = "aggressive"
            print_info("Switched to Aggressive profile")

    return {'risk_profile': profile}


def step_strategy_params() -> Dict[str, Any]:
    """Step 4: Strategy parameters."""
    print_section("STEP 4: STRATEGY PARAMETERS")

    print("""
    The wick strategy has been optimized through 480 backtests.
    Default values are optimal but can be customized.
    """)

    use_defaults = get_yes_no("Use optimal defaults? (Recommended)", default=True)

    if use_defaults:
        return {
            'wick_threshold': 5.0,
            'exit_type': 'time_based',
            'time_exit_bars': 30,
            'fixed_tp_pct': 15.0,
            'direction': 'long'
        }

    print()
    wick_threshold = get_float("Wick threshold (%)", default=5.0, min_val=3.0, max_val=10.0)

    exit_choice = get_choice(
        "Exit strategy:",
        ["Time-based (30 bars)", "Fixed Take Profit (15%)", "Risk:Reward (2:1)", "Trailing Stop"],
        default=0
    )

    exit_types = ['time_based', 'fixed_tp', 'rr_ratio', 'trailing']
    exit_type = exit_types[exit_choice]

    time_bars = 30
    fixed_tp = 15.0

    if exit_type == 'time_based':
        time_bars = get_int("Max hold bars", default=30, min_val=10, max_val=100)
    elif exit_type == 'fixed_tp':
        fixed_tp = get_float("Take profit (%)", default=15.0, min_val=5.0, max_val=50.0)

    dir_choice = get_choice("Direction:", ["Long only (recommended)", "Both directions"], default=0)
    direction = 'long' if dir_choice == 0 else 'both'

    return {
        'wick_threshold': wick_threshold,
        'exit_type': exit_type,
        'time_exit_bars': time_bars,
        'fixed_tp_pct': fixed_tp,
        'direction': direction
    }


def step_trading_mode() -> Dict[str, Any]:
    """Step 5: Trading mode."""
    print_section("STEP 5: TRADING MODE")

    print("""
    PAPER TRADING (Recommended first)
      - Simulates trades without real orders
      - Test the strategy risk-free
      - All signals logged for review

    LIVE TRADING
      - Real orders on the exchange
      - Real money at risk
      - Start with small amounts
    """)

    paper_trade = get_yes_no("Start with PAPER trading?", default=True)

    if not paper_trade:
        print()
        print_warning("LIVE TRADING selected!")
        print_warning("Real money will be at risk!")
        if not get_yes_no("Confirm LIVE trading?", default=False):
            paper_trade = True
            print_info("Switched to paper trading")

    return {'paper_trade': paper_trade}


def generate_config(
    exchanges: Dict,
    binance: Optional[Dict],
    hyperliquid: Optional[Dict],
    risk: Dict,
    strategy: Dict,
    mode: Dict
) -> str:
    """Generate YAML configuration."""

    config = f"""# WickTrader Configuration
# Generated by setup wizard

# Trading Symbol
symbol: SOL
timeframe: 4h

# Wick Strategy
wick:
  threshold: {strategy['wick_threshold']}
  direction: {strategy['direction']}

# Risk Profile
risk:
  profile: {risk['risk_profile']}

# Exit Strategy
exit:
  strategy: {strategy['exit_type']}
  fixed_tp_pct: {strategy['fixed_tp_pct']}
  time_bars: {strategy['time_exit_bars']}
  rr_ratio: 2.0
  trailing_activation: 10.0
  trailing_distance: 5.0

# Bot Mode
bot:
  paper_trade: {str(mode['paper_trade']).lower()}
  check_interval: 60

# Exchange Configuration
exchanges:
  primary: {exchanges['primary']}
  enable_fallback: {str(exchanges['enable_fallback']).lower()}

"""

    if binance:
        config += f"""
  binance:
    enabled: {str(exchanges['binance_enabled']).lower()}
    api_key: "{binance['api_key']}"
    api_secret: "{binance['api_secret']}"
    testnet: {str(binance['testnet']).lower()}
"""

    if hyperliquid:
        config += f"""
  hyperliquid:
    enabled: {str(exchanges['hyperliquid_enabled']).lower()}
    private_key: "{hyperliquid['private_key']}"
    wallet_address: "{hyperliquid['api_address']}"
    account_address: "{hyperliquid['main_address']}"
    testnet: {str(hyperliquid['testnet']).lower()}
"""

    return config


def save_config(content: str) -> Path:
    """Save configuration file."""
    config_dir = Path(__file__).parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "bot_config.yaml"

    # Backup existing
    if config_path.exists():
        backup = config_dir / "bot_config.yaml.backup"
        config_path.rename(backup)
        print_info(f"Backed up existing config to {backup.name}")

    with open(config_path, 'w') as f:
        f.write(content)

    return config_path


def print_summary(exchanges: Dict, risk: Dict, strategy: Dict, mode: Dict):
    """Print configuration summary."""
    print_section("CONFIGURATION SUMMARY")

    primary = exchanges['primary'].upper()
    fallback = "Enabled" if exchanges['enable_fallback'] else "Disabled"
    mode_str = "PAPER (safe)" if mode['paper_trade'] else "LIVE (real funds!)"

    print(f"""
    EXCHANGES:
      Primary:       {primary}
      Fallback:      {fallback}
      Binance:       {'Enabled' if exchanges['binance_enabled'] else 'Disabled'}
      Hyperliquid:   {'Enabled' if exchanges['hyperliquid_enabled'] else 'Disabled'}

    RISK PROFILE:
      Profile:       {risk['risk_profile'].upper()}

    STRATEGY:
      Wick threshold: {strategy['wick_threshold']}%
      Exit:          {strategy['exit_type']}
      Direction:     {strategy['direction']}

    MODE:
      Trading:       {mode_str}
    """)


def print_next_steps(config_path: Path, paper_trade: bool):
    """Print next steps."""
    print_section("SETUP COMPLETE!")

    if paper_trade:
        print("""
    NEXT STEPS:

    1. START THE BOT:
       python -m bot.run_bot --config config/bot_config.yaml

    2. MONITOR:
       - Watch the console for signals
       - Check logs/ directory for detailed logs

    3. GO LIVE:
       When ready, edit config/bot_config.yaml:
       Change 'paper_trade: true' to 'paper_trade: false'

    """)
    else:
        print("""
    NEXT STEPS:

    1. START THE BOT:
       python -m bot.run_bot --config config/bot_config.yaml

    2. MONITOR:
       - Watch the console for signals
       - Check your exchange for positions
       - Monitor your balance

    *** WARNING: LIVE TRADING MODE - REAL FUNDS AT RISK ***

    """)

    print(f"    Configuration saved to: {config_path}")
    print()
    print("    To reconfigure: python setup_wizard.py")
    print()


def main():
    """Main wizard flow."""
    try:
        clear_screen()
        print_banner()

        print("  This wizard will guide you through setup.")
        print("  Press ENTER to start...")
        input()

        # Step 1: Exchange selection
        exchanges = step_exchange_selection()

        # Step 2a: Binance setup (if enabled)
        binance = None
        if exchanges['binance_enabled']:
            binance = step_binance_setup()

        # Step 2b: Hyperliquid setup (if enabled)
        hyperliquid = None
        if exchanges['hyperliquid_enabled']:
            hyperliquid = step_hyperliquid_setup()

        # Step 3: Risk profile
        risk = step_risk_profile()

        # Step 4: Strategy params
        strategy = step_strategy_params()

        # Step 5: Trading mode
        mode = step_trading_mode()

        # Summary
        clear_screen()
        print_banner()
        print_summary(exchanges, risk, strategy, mode)

        # Save
        if get_yes_no("Save this configuration?", default=True):
            content = generate_config(exchanges, binance, hyperliquid, risk, strategy, mode)
            config_path = save_config(content)
            print_success(f"Configuration saved!")
            print_next_steps(config_path, mode['paper_trade'])
        else:
            print()
            print_info("Setup cancelled. No changes made.")

    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.")
        sys.exit(0)
    except Exception as e:
        print_error(f"Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
