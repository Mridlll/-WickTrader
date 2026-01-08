"""Generate comprehensive backtest report for wick strategy."""

import pandas as pd
import numpy as np
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from indicators.wick import WickCalculator


@dataclass
class Trade:
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    wick_pct: float
    position_size: float
    position_value: float
    entry_fee: float
    exit_fee: float
    total_fees: float
    gross_pnl: float
    net_pnl: float
    exit_reason: str
    bars_held: int
    balance_after: float


def run_backtest(
    df: pd.DataFrame,
    wick_result,
    threshold: float = 5.0,
    tp_pct: float = 10.0,
    risk_pct: float = 2.0,
    leverage: float = 3.0,
    taker_fee: float = 0.05,
    slippage: float = 0.05,
    max_hold: int = 40,
    cooldown: int = 5,
    initial_balance: float = 10000,
    compound: bool = True
) -> Dict[str, Any]:
    """Run a single backtest with given parameters."""

    balance = initial_balance
    trades = []
    last_trade_bar = -cooldown
    peak_balance = initial_balance
    max_drawdown = 0
    equity_curve = [initial_balance]

    for i in range(50, len(df) - 42):
        if i - last_trade_bar < cooldown:
            equity_curve.append(balance)
            continue

        row = df.iloc[i]
        lower_wick = wick_result.lower_wick_pct.iloc[i]

        if lower_wick >= threshold:
            entry_price = row['close'] * (1 + slippage/100)
            entry_time = df.index[i]
            last_trade_bar = i

            future_data = df.iloc[i+1:i+max_hold+1]
            stop_loss = row['low'] * 0.995
            take_profit = entry_price * (1 + tp_pct/100)

            # Position sizing
            current_balance = balance if compound else initial_balance
            risk_amount = current_balance * (risk_pct/100)
            price_risk = entry_price - stop_loss
            position_size = risk_amount / price_risk
            position_value = position_size * entry_price

            max_position_value = current_balance * leverage
            if position_value > max_position_value:
                position_value = max_position_value
                position_size = position_value / entry_price

            entry_fee = position_value * (taker_fee/100)

            # Simulate
            tp_hit = sl_hit = False
            exit_price = 0
            exit_bar = max_hold
            exit_reason = 'TIME'

            for j, (idx, future_row) in enumerate(future_data.iterrows()):
                if future_row['low'] <= stop_loss:
                    sl_hit = True
                    exit_price = stop_loss * (1 - slippage/100)
                    exit_bar = j + 1
                    exit_reason = 'STOP_LOSS'
                    break
                if future_row['high'] >= take_profit:
                    tp_hit = True
                    exit_price = take_profit * (1 - slippage/100)
                    exit_bar = j + 1
                    exit_reason = 'TAKE_PROFIT'
                    break

            if not tp_hit and not sl_hit:
                exit_price = future_data.iloc[-1]['close'] * (1 - slippage/100)

            exit_fee = (position_size * exit_price) * (taker_fee/100)
            total_fees = entry_fee + exit_fee
            gross_pnl = (exit_price - entry_price) * position_size
            net_pnl = gross_pnl - total_fees

            balance += net_pnl

            if balance > peak_balance:
                peak_balance = balance
            current_dd = (peak_balance - balance) / peak_balance * 100
            if current_dd > max_drawdown:
                max_drawdown = current_dd

            trades.append(Trade(
                entry_time=entry_time,
                exit_time=df.index[min(i + exit_bar, len(df)-1)],
                entry_price=entry_price,
                exit_price=exit_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                wick_pct=lower_wick,
                position_size=position_size,
                position_value=position_value,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                total_fees=total_fees,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                exit_reason=exit_reason,
                bars_held=exit_bar,
                balance_after=balance
            ))

        equity_curve.append(balance)

    # Calculate metrics
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    total_trades = len(trades)

    if total_trades == 0:
        return None

    win_rate = 100 * len(wins) / total_trades

    gross_profits = sum(t.gross_pnl for t in wins) if wins else 0
    gross_losses = abs(sum(t.gross_pnl for t in losses)) if losses else 1
    net_profits = sum(t.net_pnl for t in wins) if wins else 0
    net_losses = abs(sum(t.net_pnl for t in losses)) if losses else 1
    total_fees_paid = sum(t.total_fees for t in trades)

    profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')
    net_pf = net_profits / net_losses if net_losses > 0 else float('inf')

    # Sharpe
    returns = [t.net_pnl / (t.balance_after - t.net_pnl) * 100 for t in trades]
    if len(returns) > 1:
        trades_per_year = len(trades) / (len(df) / (365 * 6))
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(trades_per_year) if np.std(returns) > 0 else 0
    else:
        sharpe = 0

    return {
        'threshold': threshold,
        'tp_pct': tp_pct,
        'risk_pct': risk_pct,
        'initial_balance': initial_balance,
        'final_balance': balance,
        'total_pnl': balance - initial_balance,
        'total_pnl_pct': 100 * (balance - initial_balance) / initial_balance,
        'total_trades': total_trades,
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'net_profit_factor': net_pf,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'total_fees': total_fees_paid,
        'avg_win': np.mean([t.net_pnl for t in wins]) if wins else 0,
        'avg_loss': np.mean([t.net_pnl for t in losses]) if losses else 0,
        'largest_win': max([t.net_pnl for t in wins]) if wins else 0,
        'largest_loss': min([t.net_pnl for t in losses]) if losses else 0,
        'avg_bars': np.mean([t.bars_held for t in trades]),
        'trades': trades,
        'equity_curve': equity_curve
    }


def main():
    # Load data
    data_path = project_root / "data" / "sol_4h" / "sol_4h.csv"
    if not data_path.exists():
        # Try alternative path
        data_path = Path("D:/Crypto Bot/AlgoBotVMC/data/binance_cache_1year/sol_4h.csv")

    df = pd.read_csv(data_path, parse_dates=['timestamp'], index_col='timestamp')
    calc = WickCalculator()
    wick_result = calc.calculate(df)

    print("=" * 100)
    print("COMPREHENSIVE WICK STRATEGY BACKTEST REPORT")
    print("=" * 100)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Data Period: {df.index[0]} to {df.index[-1]}")
    print(f"Total Candles: {len(df)}")
    print()

    # Test multiple variants
    variants = [
        {'threshold': 3.5, 'tp_pct': 10.0, 'name': '3.5% threshold, 10% TP'},
        {'threshold': 5.0, 'tp_pct': 10.0, 'name': '5.0% threshold, 10% TP (Conservative)'},
        {'threshold': 5.0, 'tp_pct': 15.0, 'name': '5.0% threshold, 15% TP'},
        {'threshold': 5.0, 'tp_pct': 20.0, 'name': '5.0% threshold, 20% TP'},
        {'threshold': 4.0, 'tp_pct': 10.0, 'name': '4.0% threshold, 10% TP'},
        {'threshold': 6.0, 'tp_pct': 10.0, 'name': '6.0% threshold, 10% TP'},
    ]

    results = []
    for v in variants:
        r = run_backtest(
            df, wick_result,
            threshold=v['threshold'],
            tp_pct=v['tp_pct'],
            risk_pct=2.0,
            leverage=3.0,
            taker_fee=0.05,
            slippage=0.05,
            max_hold=40,
            cooldown=5,
            compound=True
        )
        if r:
            r['name'] = v['name']
            results.append(r)

    # Print comparison table
    print("STRATEGY VARIANT COMPARISON")
    print("=" * 100)
    print(f"{'Variant':<40} | {'Trades':>6} | {'Win%':>6} | {'PnL':>10} | {'PnL%':>8} | {'PF':>6} | {'Sharpe':>7} | {'MaxDD':>7}")
    print("-" * 100)

    for r in results:
        print(f"{r['name']:<40} | {r['total_trades']:>6} | {r['win_rate']:>5.1f}% | ${r['total_pnl']:>+9.2f} | {r['total_pnl_pct']:>+7.2f}% | {r['net_profit_factor']:>6.2f} | {r['sharpe']:>7.2f} | {r['max_drawdown']:>6.2f}%")

    print()

    # Best variant details
    best = max(results, key=lambda x: x['total_pnl'])
    print("=" * 100)
    print(f"BEST VARIANT: {best['name']}")
    print("=" * 100)
    print()

    print("PERFORMANCE METRICS")
    print("-" * 50)
    print(f"Initial Balance:     ${best['initial_balance']:>12,.2f}")
    print(f"Final Balance:       ${best['final_balance']:>12,.2f}")
    print(f"Net P&L:             ${best['total_pnl']:>+12,.2f} ({best['total_pnl_pct']:+.2f}%)")
    print(f"Total Fees Paid:     ${best['total_fees']:>12,.2f}")
    print()
    print(f"Total Trades:        {best['total_trades']:>12}")
    print(f"Winning Trades:      {best['wins']:>12} ({best['win_rate']:.1f}%)")
    print(f"Losing Trades:       {best['losses']:>12}")
    print()
    print(f"Gross Profit Factor: {best['profit_factor']:>12.2f}")
    print(f"Net Profit Factor:   {best['net_profit_factor']:>12.2f}")
    print(f"Sharpe Ratio:        {best['sharpe']:>12.2f}")
    print(f"Max Drawdown:        {best['max_drawdown']:>11.2f}%")
    print()
    print(f"Avg Win:             ${best['avg_win']:>+12,.2f}")
    print(f"Avg Loss:            ${best['avg_loss']:>+12,.2f}")
    print(f"Largest Win:         ${best['largest_win']:>+12,.2f}")
    print(f"Largest Loss:        ${best['largest_loss']:>+12,.2f}")
    print(f"Avg Bars Held:       {best['avg_bars']:>12.1f}")
    print()

    print("DETAILED TRADE LOG")
    print("=" * 100)
    print(f"{'#':>3} | {'Entry Date':>12} | {'Wick%':>6} | {'Entry':>8} | {'Exit':>8} | {'Gross':>10} | {'Fees':>7} | {'Net':>10} | {'Result':>6} | {'Bars':>4} | {'Balance':>10}")
    print("-" * 110)

    for i, t in enumerate(best['trades'], 1):
        result = 'WIN' if t.net_pnl > 0 else 'LOSS'
        print(f"{i:>3} | {t.entry_time.strftime('%Y-%m-%d'):>12} | {t.wick_pct:>5.1f}% | {t.entry_price:>8.2f} | {t.exit_price:>8.2f} | {t.gross_pnl:>+10.2f} | {t.total_fees:>7.2f} | {t.net_pnl:>+10.2f} | {result:>6} | {t.bars_held:>4} | {t.balance_after:>10.2f}")

    print()

    # Fee impact
    print("FEE & SLIPPAGE IMPACT")
    print("=" * 100)
    total_gross = sum(t.gross_pnl for t in best['trades'])
    print(f"Total Gross P&L:     ${total_gross:>+12,.2f}")
    print(f"Total Fees:          ${best['total_fees']:>12,.2f}")
    print(f"Net P&L:             ${best['total_pnl']:>+12,.2f}")
    print(f"Fee Impact:          {100*best['total_fees']/abs(total_gross) if total_gross != 0 else 0:>11.2f}% of gross")
    print()
    print("Fee Structure:")
    print("  - Taker Fee: 0.05% per side (entry + exit)")
    print("  - Slippage: 0.05% per side (entry + exit)")
    print("  - Total Cost: ~0.20% round trip")
    print()

    # Monte Carlo
    print("MONTE CARLO SIMULATION (1000 runs)")
    print("=" * 100)
    np.random.seed(42)
    trade_returns = [t.net_pnl for t in best['trades']]
    mc_results = []

    for _ in range(1000):
        shuffled = np.random.permutation(trade_returns)
        mc_balance = best['initial_balance']
        for ret in shuffled:
            mc_balance += ret * (mc_balance / best['initial_balance'])
        mc_results.append(mc_balance)

    mc_results = np.array(mc_results)
    print(f"Mean Final Balance:  ${np.mean(mc_results):>12,.2f}")
    print(f"Median:              ${np.median(mc_results):>12,.2f}")
    print(f"5th Percentile:      ${np.percentile(mc_results, 5):>12,.2f}")
    print(f"95th Percentile:     ${np.percentile(mc_results, 95):>12,.2f}")
    print(f"Worst Case:          ${np.min(mc_results):>12,.2f}")
    print(f"Best Case:           ${np.max(mc_results):>12,.2f}")
    print(f"Probability of Profit: {100*np.sum(mc_results > best['initial_balance'])/len(mc_results):.1f}%")
    print()

    # Compounding comparison
    print("COMPOUNDING EFFECT")
    print("=" * 100)
    r_no_compound = run_backtest(
        df, wick_result,
        threshold=best['threshold'],
        tp_pct=best['tp_pct'],
        compound=False
    )
    if r_no_compound:
        print(f"With Compounding:    ${best['final_balance']:>12,.2f} ({best['total_pnl_pct']:+.2f}%)")
        print(f"Without Compounding: ${r_no_compound['final_balance']:>12,.2f} ({r_no_compound['total_pnl_pct']:+.2f}%)")
        print(f"Compounding Boost:   ${best['final_balance'] - r_no_compound['final_balance']:>+12,.2f}")
    print()

    print("=" * 100)
    print("END OF REPORT")
    print("=" * 100)


if __name__ == "__main__":
    main()
