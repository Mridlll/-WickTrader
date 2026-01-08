"""Full grid search of all entry/exit strategy combinations."""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from indicators.wick import WickCalculator


def backtest(df, wick_result, threshold, exit_type, exit_param, sl_type='wick', cooldown=5):
    """Run single backtest with given parameters."""
    balance = 10000
    peak = 10000
    max_dd = 0
    wins = losses = 0
    last_bar = -cooldown

    for i in range(50, len(df) - 50):
        if i - last_bar < cooldown:
            continue

        row = df.iloc[i]
        lower_wick = wick_result.lower_wick_pct.iloc[i]

        if lower_wick >= threshold:
            entry = row['close'] * 1.0005
            last_bar = i

            # Stop loss calculation
            if sl_type == 'wick':
                stop = row['low'] * 0.995
            elif sl_type == 'atr':
                atr = df.iloc[i-14:i]['high'].max() - df.iloc[i-14:i]['low'].min()
                stop = entry - (atr * 1.5)
            elif sl_type == 'fixed':
                stop = entry * 0.97  # 3% fixed SL

            risk_amt = balance * 0.10
            pos_size = min(risk_amt / max(entry - stop, 0.01), balance * 3 / entry)

            future = df.iloc[i+1:i+51]
            if len(future) < 10:
                continue

            exit_price = None

            # EXIT STRATEGIES
            if exit_type == 'fixed_pct':
                tp = entry * (1 + exit_param/100)
                for j, (idx, fut) in enumerate(future.iterrows()):
                    if fut['low'] <= stop:
                        exit_price = stop * 0.9995
                        break
                    if fut['high'] >= tp:
                        exit_price = tp * 0.9995
                        break
                if exit_price is None:
                    exit_price = future.iloc[-1]['close']

            elif exit_type == 'rr':
                risk_dist = entry - stop
                tp = entry + (risk_dist * exit_param)
                for j, (idx, fut) in enumerate(future.iterrows()):
                    if fut['low'] <= stop:
                        exit_price = stop * 0.9995
                        break
                    if fut['high'] >= tp:
                        exit_price = tp * 0.9995
                        break
                if exit_price is None:
                    exit_price = future.iloc[-1]['close']

            elif exit_type == 'trailing':
                activated = False
                trail_stop = stop
                activation_pct = exit_param
                trail_pct = 0.03

                for j, (idx, fut) in enumerate(future.iterrows()):
                    if fut['low'] <= trail_stop:
                        exit_price = trail_stop * 0.9995
                        break
                    if fut['high'] >= entry * (1 + activation_pct/100):
                        activated = True
                    if activated:
                        new_trail = fut['high'] * (1 - trail_pct)
                        if new_trail > trail_stop:
                            trail_stop = new_trail
                if exit_price is None:
                    exit_price = future.iloc[-1]['close']

            elif exit_type == 'time_bars':
                max_bars = int(exit_param)
                tp = entry * 1.15
                for j, (idx, fut) in enumerate(future.iloc[:max_bars].iterrows()):
                    if fut['low'] <= stop:
                        exit_price = stop * 0.9995
                        break
                    if fut['high'] >= tp:
                        exit_price = tp * 0.9995
                        break
                if exit_price is None:
                    exit_price = future.iloc[min(max_bars-1, len(future)-1)]['close']

            elif exit_type == 'opposite_wick':
                for j, (idx, fut) in enumerate(future.iterrows()):
                    if fut['low'] <= stop:
                        exit_price = stop * 0.9995
                        break
                    upper_wick = (fut['high'] - max(fut['open'], fut['close'])) / fut['close'] * 100
                    if upper_wick >= exit_param:
                        exit_price = fut['close'] * 0.9995
                        break
                if exit_price is None:
                    exit_price = future.iloc[-1]['close']

            if exit_price is None:
                continue

            pnl = (exit_price - entry) * pos_size
            fees = pos_size * entry * 0.001
            net_pnl = pnl - fees

            balance += net_pnl
            if net_pnl > 0:
                wins += 1
            else:
                losses += 1

            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            if dd > max_dd:
                max_dd = dd

    total = wins + losses
    if total == 0:
        return None
    return {
        'trades': total,
        'win_rate': 100*wins/total,
        'return': 100*(balance-10000)/10000,
        'max_dd': max_dd,
        'balance': balance
    }


def main():
    # Load data
    data_path = Path("D:/Crypto Bot/AlgoBotVMC/data/binance_cache_1year/sol_4h.csv")
    df = pd.read_csv(data_path, parse_dates=['timestamp'], index_col='timestamp')
    calc = WickCalculator()
    wick_result = calc.calculate(df)

    print('='*100)
    print('COMPREHENSIVE ENTRY/EXIT STRATEGY GRID SEARCH')
    print('='*100)
    print(f'Data: {df.index[0].strftime("%Y-%m-%d")} to {df.index[-1].strftime("%Y-%m-%d")}')
    print(f'Risk: 10% per trade | Leverage cap: 3x')
    print()

    # Entry thresholds
    thresholds = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0]

    # Exit strategies
    exits = [
        ('fixed_pct', 8, 'Fixed 8% TP'),
        ('fixed_pct', 10, 'Fixed 10% TP'),
        ('fixed_pct', 12, 'Fixed 12% TP'),
        ('fixed_pct', 15, 'Fixed 15% TP'),
        ('fixed_pct', 20, 'Fixed 20% TP'),
        ('rr', 2, 'R:R 2:1'),
        ('rr', 3, 'R:R 3:1'),
        ('rr', 4, 'R:R 4:1'),
        ('trailing', 5, 'Trail @5%'),
        ('trailing', 8, 'Trail @8%'),
        ('trailing', 10, 'Trail @10%'),
        ('time_bars', 20, 'Max 20 bars'),
        ('time_bars', 30, 'Max 30 bars'),
        ('time_bars', 40, 'Max 40 bars'),
        ('opposite_wick', 3, 'Opp wick 3%'),
        ('opposite_wick', 5, 'Opp wick 5%'),
    ]

    # Stop loss types
    sl_types = [('wick', 'Wick SL'), ('fixed', 'Fixed 3% SL')]

    results = []
    total_tests = len(thresholds) * len(exits) * len(sl_types)
    tested = 0

    for thresh in thresholds:
        for exit_type, exit_param, exit_name in exits:
            for sl_type, sl_name in sl_types:
                r = backtest(df, wick_result, thresh, exit_type, exit_param, sl_type)
                tested += 1
                if r and r['trades'] >= 3:
                    results.append({
                        'threshold': thresh,
                        'exit': exit_name,
                        'sl': sl_name,
                        **r
                    })

    print(f'Tested {tested} combinations, {len(results)} valid results')
    print()

    # Sort by return
    results.sort(key=lambda x: x['return'], reverse=True)

    print('TOP 20 CONFIGURATIONS (by return)')
    print('='*100)
    print(f"{'Entry':>6} | {'Exit Strategy':<16} | {'SL Type':<12} | {'Trades':>6} | {'Win%':>6} | {'Return':>10} | {'MaxDD':>7}")
    print('-'*100)

    for r in results[:20]:
        print(f"{r['threshold']:>5.1f}% | {r['exit']:<16} | {r['sl']:<12} | {r['trades']:>6} | {r['win_rate']:>5.1f}% | {r['return']:>+9.1f}% | {r['max_dd']:>6.1f}%")

    print()
    print('WORST 10 (to avoid)')
    print('-'*100)
    for r in results[-10:]:
        print(f"{r['threshold']:>5.1f}% | {r['exit']:<16} | {r['sl']:<12} | {r['trades']:>6} | {r['win_rate']:>5.1f}% | {r['return']:>+9.1f}% | {r['max_dd']:>6.1f}%")

    # Best config
    best = results[0]
    print()
    print('='*100)
    print('BEST CONFIGURATION')
    print('='*100)
    print(f"Entry Threshold: {best['threshold']}% wick")
    print(f"Exit Strategy: {best['exit']}")
    print(f"Stop Loss: {best['sl']}")
    print(f"Trades: {best['trades']}")
    print(f"Win Rate: {best['win_rate']:.1f}%")
    print(f"Return: {best['return']:+.1f}%")
    print(f"Max Drawdown: {best['max_dd']:.1f}%")
    print(f"Final Balance: ${best['balance']:,.2f}")

    # Analysis by category
    print()
    print('='*100)
    print('ANALYSIS BY CATEGORY')
    print('='*100)

    # Best by threshold
    print('\nBest exit for each threshold:')
    for thresh in thresholds:
        thresh_results = [r for r in results if r['threshold'] == thresh]
        if thresh_results:
            best_t = max(thresh_results, key=lambda x: x['return'])
            print(f"  {thresh}%: {best_t['exit']:<16} -> {best_t['return']:+.1f}% ({best_t['win_rate']:.0f}% win)")

    # Best by exit type
    print('\nBest threshold for each exit strategy:')
    exit_names = set(r['exit'] for r in results)
    for exit_name in sorted(exit_names):
        exit_results = [r for r in results if r['exit'] == exit_name]
        if exit_results:
            best_e = max(exit_results, key=lambda x: x['return'])
            print(f"  {exit_name:<16}: {best_e['threshold']}% -> {best_e['return']:+.1f}%")

    # SL comparison
    print('\nStop Loss comparison (averaged):')
    for sl_type, sl_name in sl_types:
        sl_results = [r for r in results if r['sl'] == sl_name]
        if sl_results:
            avg_ret = np.mean([r['return'] for r in sl_results])
            avg_wr = np.mean([r['win_rate'] for r in sl_results])
            print(f"  {sl_name}: avg return {avg_ret:+.1f}%, avg win rate {avg_wr:.1f}%")

    return results


if __name__ == "__main__":
    results = main()
