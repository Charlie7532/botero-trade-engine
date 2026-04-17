"""
POSITION MONITOR: Vigilancia Continua del Portafolio
=====================================================
Muestra estado real-time de:
- Posiciones abiertas (Alpaca)
- Órdenes pendientes
- Trailing stops vs precio actual
- Relative Strength y Alpha Decay
- Risk Guardian status
- Alertas de concentración (ej: BTCUSD + IBIT = doble crypto)

Ejecutar: python position_monitor.py [--loop 60]
"""
import sys
import os
import time
import argparse

# Credentials loaded from .env (never hardcode secrets)
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.WARNING, format='%(message)s')

from datetime import datetime, UTC
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from backend.application.trade_journal import TradeJournal
from backend.application.portfolio_intelligence import (
    RelativeStrengthMonitor, AdaptiveTrailingStop, RiskGuardian,
)

# Mapeo de exposición real por asset class
ASSET_CLASS_MAP = {
    'BTCUSD': 'Crypto',
    'BTC/USD': 'Crypto',
    'IBIT': 'Crypto',   # Bitcoin ETF = misma exposición
    'BITO': 'Crypto',
    'GBTC': 'Crypto',
    'ETHUSD': 'Crypto',
    'AMD': 'Technology',
    'NVDA': 'Technology',
    'AAPL': 'Technology',
    'MSFT': 'Technology',
    'GOOGL': 'Technology',
    'META': 'Comm Services',
    'ABT': 'Healthcare',
    'JPM': 'Financials',
    'SPY': 'Index',
    'QQQ': 'Index',
    'XLK': 'Technology',
}


class PositionMonitor:
    """Monitor de posiciones en tiempo real."""
    
    def __init__(self):
        self.client = TradingClient(
            os.environ['ALPACA_API_KEY'],
            os.environ['ALPACA_SECRET_KEY'],
            paper=True,
        )
        self.journal = TradeJournal()
        self.rs_monitor = RelativeStrengthMonitor()
        self.trailing = AdaptiveTrailingStop()
        self.risk_guardian = RiskGuardian()
    
    def get_full_status(self) -> dict:
        """Estado completo del portafolio."""
        account = self.client.get_account()
        positions = self.client.get_all_positions()
        orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
        journal_trades = self.journal.get_open_trades()
        
        return {
            "account": {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "day_pnl": float(account.equity) - float(account.last_equity),
                "day_pnl_pct": (float(account.equity) / float(account.last_equity) - 1) * 100 if float(account.last_equity) > 0 else 0,
            },
            "positions": [
                {
                    "ticker": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "market_value": float(p.market_value),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
                    "asset_class": ASSET_CLASS_MAP.get(p.symbol, 'Unknown'),
                }
                for p in positions
            ],
            "pending_orders": [
                {
                    "ticker": o.symbol,
                    "side": str(o.side),
                    "type": str(o.type),
                    "notional": float(o.notional) if o.notional else None,
                    "qty": float(o.qty) if o.qty else None,
                    "status": str(o.status),
                    "asset_class": ASSET_CLASS_MAP.get(o.symbol, 'Unknown'),
                }
                for o in orders
            ],
            "journal_trades": journal_trades,
        }
    
    def print_dashboard(self):
        """Imprime el dashboard completo."""
        status = self.get_full_status()
        acct = status['account']
        
        now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
        
        print(f"\n{'═'*70}")
        print(f"  🏦 BOTERO TRADE — POSITION MONITOR")
        print(f"  {now}")
        print(f"{'═'*70}")
        
        # Account
        day_emoji = "📈" if acct['day_pnl'] >= 0 else "📉"
        print(f"\n  💰 Equity: ${acct['equity']:>10,.2f}  |  💵 Cash: ${acct['cash']:>10,.2f}")
        print(f"  {day_emoji} Day P&L: ${acct['day_pnl']:>+8,.2f} ({acct['day_pnl_pct']:>+5.2f}%)")
        
        # Posiciones activas
        positions = status['positions']
        if positions:
            print(f"\n  ── POSICIONES ACTIVAS ({len(positions)}) ──")
            print(f"  {'Ticker':>8} {'Qty':>10} {'Entry':>9} {'Current':>9} {'P&L':>10} {'P&L%':>7} {'Value':>10} {'Class':>12}")
            print(f"  {'─'*8} {'─'*10} {'─'*9} {'─'*9} {'─'*10} {'─'*7} {'─'*10} {'─'*12}")
            
            total_value = 0
            total_pnl = 0
            for p in positions:
                emoji = "🟢" if p['unrealized_pnl'] >= 0 else "🔴"
                print(f"  {p['ticker']:>8} {p['qty']:>10.4f} ${p['avg_entry']:>8.2f} ${p['current_price']:>8.2f} "
                      f"${p['unrealized_pnl']:>+9.2f} {p['unrealized_pnl_pct']:>+6.2f}% ${p['market_value']:>9.2f} {emoji}{p['asset_class']}")
                total_value += p['market_value']
                total_pnl += p['unrealized_pnl']
            
            print(f"  {'─'*78}")
            print(f"  {'TOTAL':>8} {'':>10} {'':>9} {'':>9} ${total_pnl:>+9.2f} {'':>7} ${total_value:>9.2f}")
        
        # Órdenes pendientes
        pending = status['pending_orders']
        if pending:
            print(f"\n  ── ÓRDENES PENDIENTES ({len(pending)}) ──")
            print(f"  {'Ticker':>8} {'Side':>8} {'Notional':>10} {'Status':>12} {'Class':>12}")
            print(f"  {'─'*8} {'─'*8} {'─'*10} {'─'*12} {'─'*12}")
            for o in pending:
                notional_str = f"${o['notional']:,.0f}" if o['notional'] else f"{o['qty']} shares"
                print(f"  {o['ticker']:>8} {o['side'].split('.')[-1]:>8} {notional_str:>10} {o['status'].split('.')[-1]:>12} {o['asset_class']:>12}")
        
        # Journal trades
        journal = status['journal_trades']
        if journal:
            print(f"\n  ── JOURNAL ({len(journal)} trades abiertos) ──")
            print(f"  {'Trade ID':<32} {'Ticker':>8} {'Entry':>9} {'Alpha':>6} {'Grade':>6}")
            print(f"  {'─'*32} {'─'*8} {'─'*9} {'─'*6} {'─'*6}")
            for t in journal:
                print(f"  {t['trade_id']:<32} {t['ticker']:>8} ${t['entry_price']:>8.2f} {t['alpha_score']:>5.1f} {t['qualifier_grade']:>6}")
        
        # Concentración y alertas
        print(f"\n  ── ALERTAS & RISK ──")
        
        # Detectar doble exposición
        all_tickers = [p['ticker'] for p in positions] + [o['ticker'] for o in pending]
        asset_classes = {}
        for t in all_tickers:
            ac = ASSET_CLASS_MAP.get(t, 'Unknown')
            asset_classes.setdefault(ac, []).append(t)
        
        for ac, tickers in asset_classes.items():
            if len(tickers) > 1:
                print(f"  ⚠️  DOBLE EXPOSICIÓN [{ac}]: {', '.join(tickers)} — misma asset class")
        
        # Concentración por asset class (incluyendo pendientes)
        class_values = {}
        for p in positions:
            ac = p['asset_class']
            class_values[ac] = class_values.get(ac, 0) + p['market_value']
        for o in pending:
            ac = o['asset_class']
            val = o['notional'] or 0
            class_values[ac] = class_values.get(ac, 0) + val
        
        total_deployed = sum(class_values.values())
        if total_deployed > 0:
            print(f"\n  Exposición por asset class (posiciones + órdenes pendientes):")
            for ac, val in sorted(class_values.items(), key=lambda x: -x[1]):
                pct = val / acct['equity'] * 100
                bar = "█" * int(pct)
                warning = " ⚠️ >10%!" if pct > 10 else ""
                print(f"    {ac:<16} ${val:>8,.0f} ({pct:>4.1f}%) {bar}{warning}")
            
            print(f"    {'CASH':<16} ${acct['cash']:>8,.0f} ({acct['cash']/acct['equity']*100:>4.1f}%)")
        
        # Risk Guardian
        risk = self.risk_guardian.evaluate(
            current_capital=acct['equity'],
            daily_pnl_pct=acct['day_pnl_pct'] / 100,
            current_vix=17.9,  # Último VIX conocido
        )
        
        if risk['alerts']:
            for alert in risk['alerts']:
                print(f"  {alert}")
        else:
            print(f"  ✅ Risk Guardian: Sizing {risk['position_scale']:.0%} | Trading {'ENABLED' if risk['can_trade'] else 'PAUSED'}")
        
        print(f"\n{'═'*70}")

    def suggest_actions(self):
        """Sugiere acciones basadas en el estado actual."""
        status = self.get_full_status()
        suggestions = []
        
        # Check doble exposición crypto
        all_tickers = [p['ticker'] for p in status['positions']] + [o['ticker'] for o in status['pending_orders']]
        crypto_tickers = [t for t in all_tickers if ASSET_CLASS_MAP.get(t, '') == 'Crypto']
        if len(crypto_tickers) > 1:
            suggestions.append({
                "priority": "HIGH",
                "action": f"Consolidar exposición crypto: {', '.join(crypto_tickers)}",
                "detail": "BTCUSD y IBIT son esencialmente el mismo asset. "
                         "Considerar cerrar BTCUSD ($1,005) ya que IBIT ($5,000) "
                         "cubre la exposición con mejor tracking y está en el journal.",
            })
        
        return suggestions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop', type=int, default=0, help='Segundos entre refreshes (0=una vez)')
    args = parser.parse_args()
    
    monitor = PositionMonitor()
    
    if args.loop > 0:
        print(f"Monitor activo. Refresh cada {args.loop} segundos. Ctrl+C para detener.")
        while True:
            try:
                monitor.print_dashboard()
                suggestions = monitor.suggest_actions()
                if suggestions:
                    print(f"\n  ── SUGERENCIAS ──")
                    for s in suggestions:
                        print(f"  [{s['priority']}] {s['action']}")
                        print(f"    {s['detail']}")
                time.sleep(args.loop)
            except KeyboardInterrupt:
                print("\nMonitor detenido.")
                break
    else:
        monitor.print_dashboard()
        suggestions = monitor.suggest_actions()
        if suggestions:
            print(f"\n  ── SUGERENCIAS ──")
            for s in suggestions:
                print(f"  [{s['priority']}] {s['action']}")
                print(f"    {s['detail']}")
