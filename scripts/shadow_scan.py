#!/usr/bin/env python3
"""
SHADOW SPRING: Scanner Diario
==============================
Ejecutar diariamente (después de market close) para:
1. Calentar los Kalmans con datos recientes
2. Escanear los 3 tickers aprobados
3. Registrar señales en la base de datos
4. Mostrar señales y performance acumulado

Uso:
    python scripts/shadow_scan.py [--warmup] [--tickers XLE USO EFA]

El primer uso DEBE incluir --warmup para calentar los Kalmans.
"""
import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _legacy.shadow_spring import ShadowSpringScanner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('shadow_scan')


def main():
    parser = argparse.ArgumentParser(description='Shadow Spring Scanner')
    parser.add_argument('--warmup', action='store_true',
                        help='Warm up Kalman trackers with 60 days of historical data')
    parser.add_argument('--tickers', nargs='+', default=None,
                        help='Override default approved tickers')
    parser.add_argument('--summary', action='store_true',
                        help='Only show performance summary, no scan')
    args = parser.parse_args()

    # Initialize scanner
    scanner = ShadowSpringScanner(tickers=args.tickers)

    print()
    print('=' * 70)
    print('  SHADOW SPRING SCANNER')
    print(f'  Tickers: {scanner.tickers}')
    print('=' * 70)

    # Warmup if requested
    if args.warmup:
        print('\n📊 Calentando Kalman trackers...')
        warmup_results = scanner.warmup_all()
        for ticker, result in warmup_results.items():
            status = result['status']
            emoji = '✅' if status == 'WARMED_UP' else '❌'
            print(f'  {emoji} {ticker}: {status} ({result.get("bars", 0)} barras)')
        print()

    # Summary mode
    if args.summary:
        perf = scanner.get_performance_summary()
        print('\n📈 Performance Shadow Mode:')
        if perf['total_trades'] == 0:
            print('  No hay trades cerrados aún.')
        else:
            print(f'  Trades: {perf["total_trades"]} (W:{perf["winners"]} L:{perf["losers"]})')
            print(f'  Win Rate: {perf["win_rate"]:.1f}%')
            print(f'  Avg PnL: {perf["avg_pnl"]:+.3f}%')
            print(f'  Total Return: {perf["total_return"]:+.2f}%')
            print(f'  Best/Worst: {perf["best_trade"]:+.2f}% / {perf["worst_trade"]:+.2f}%')
            print(f'  Avg Holding: {perf["avg_bars"]:.1f} days')
            print(f'\n  By ticker:')
            for tk, stats in perf.get('by_ticker', {}).items():
                print(f'    {tk}: {stats["trades"]} trades | PnL: {stats["pnl"]:+.2f}%')
        print()
        return

    # Scan all tickers
    print('\n🔍 Escaneando...\n')
    signals = scanner.scan_all()

    for sig in signals:
        if sig.signal_type == 'ENTRY':
            emoji = '🔵'
        elif sig.signal_type == 'EXIT':
            emoji = '🟢' if 'MA20' in sig.exit_reason else '🔴'
        elif sig.signal_type == 'HOLD':
            emoji = '⏳'
        elif sig.signal_type == 'ERROR':
            emoji = '❌'
        else:
            emoji = '⚪'

        print(f'  {emoji} {sig.ticker:>5} | {sig.signal_type:>10} | {sig.notes}')

    # Show open positions
    open_pos = scanner.get_open_positions()
    if open_pos:
        print(f'\n📋 Posiciones Shadow abiertas: {len(open_pos)}')
        for p in open_pos:
            print(f'  • {p["ticker"]}: Entry@{p["entry_price"]:.2f} '
                  f'| Stop={p["stop_price"]:.2f} '
                  f'| Target MA20={p["ma20_target"]:.2f} '
                  f'| Day {p["bars_held"]}/{scanner.MAX_BARS}')

    # Performance summary
    perf = scanner.get_performance_summary()
    if perf['total_trades'] > 0:
        print(f'\n📈 Performance acumulada: {perf["total_trades"]}T | '
              f'WR:{perf["win_rate"]:.0f}% | Return:{perf["total_return"]:+.2f}%')

    print(f'\n{"=" * 70}\n')


if __name__ == '__main__':
    main()
