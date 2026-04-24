#!/usr/bin/env python3
"""
SIMULADOR HISTÓRICO WALK-FORWARD (V8)
======================================
Simula 7 días de trading institucionales de forma secuencial.
- Extrae la fecha virtual 't'.
- Trunca los datos históricos (Precios, VIX, Flujo) para que no haya look-ahead bias.
- Ejecuta el EntryIntelligenceHub para las 50 acciones.
- Abre posiciones, mueve el tiempo a 't+1', ajusta trailing stops, cierra posiciones.
- Imprime resultados diarios y un reporte forense final.
"""
import sys
import os
import json
import logging
import pandas as pd
from datetime import datetime, UTC, date
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from application.entry_intelligence_hub import EntryIntelligenceHub
from application.portfolio_intelligence import AdaptiveTrailingStop
from application.trade_autopsy import TradeAutopsy
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "sim_7d_cache.json")

# ═══════════════════════════════════════════════════════════════
# SIMULATION CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class VirtualPosition:
    ticker: str
    entry_date: str
    entry_price: float
    current_stop: float
    highest_price: float
    flow_grade: str
    notional: float = 5000.0
    status: str = "OPEN"
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    prices_since_entry: list = None

class HistoricalDataProxy:
    def __init__(self, cache: dict):
        self.cache = cache
        
        # Encontrar todas las fechas disponibles usando cualquier ticker en el caché
        all_prices = cache.get("prices", {})
        if not all_prices:
            raise ValueError("No se encontraron precios en el caché.")
            
        first_ticker = list(all_prices.keys())[0]
        self.all_dates = sorted(list(all_prices[first_ticker].keys()))
        if not self.all_dates:
            raise ValueError("No se encontraron fechas en el caché.")
            
        # Tomar solo los últimos 5 días como nuestra ventana de simulación (para asegurar data UW)
        self.sim_dates = self.all_dates[-5:]
        
    def get_prices_up_to(self, ticker: str, date_str: str) -> pd.DataFrame:
        """Retorna DataFrame truncado hasta la fecha virtual."""
        prices = self.cache.get("prices", {}).get(ticker, {})
        # Filtrar fechas <= date_str
        valid_dates = sorted([d for d in prices.keys() if d <= date_str])
        
        if not valid_dates:
            return pd.DataFrame()
            
        rows = []
        for d in valid_dates:
            row = prices[d].copy()
            row["Date"] = pd.to_datetime(d)
            rows.append(row)
            
        df = pd.DataFrame(rows).set_index("Date")
        return df

    def get_vix_up_to(self, date_str: str) -> float:
        vix_dict = self.cache.get("prices", {}).get("^VIX", {})
        valid_dates = sorted([d for d in vix_dict.keys() if d <= date_str])
        if not valid_dates:
            return 17.0
        return vix_dict[valid_dates[-1]]

    def get_flow_up_to(self, ticker: str, date_str: str) -> list:
        flow = self.cache.get("flow", {}).get(ticker, [])
        valid_flow = []
        for f in flow:
            ts = f.get('timestamp') or f.get('created_at') or f.get('date', '')
            if ts[:10] <= date_str:
                valid_flow.append(f)
        return valid_flow

    def get_darkpool_up_to(self, ticker: str, date_str: str) -> list:
        dp = self.cache.get("darkpool", {}).get(ticker, [])
        valid_dp = []
        for p in dp:
            ts = p.get('executed_at') or p.get('timestamp', '')
            if ts[:10] <= date_str:
                valid_dp.append(p)
        return valid_dp


def print_header(text):
    print(f"\n{'═'*72}")
    print(f"  {text}")
    print(f"{'═'*72}")


def run_simulation():
    if not os.path.exists(CACHE_FILE):
        logger.error(f"❌ Archivo caché {CACHE_FILE} no encontrado.")
        logger.error("Ejecute primero: python3 scripts/extract_7d_history.py")
        return
        
    logger.info("Cargando caché de datos históricos...")
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
        
    proxy = HistoricalDataProxy(cache)
    universe = cache.get("metadata", {}).get("tickers", [])
    
    if len(proxy.sim_dates) < 2:
        logger.error("No hay suficientes días en el caché para simular.")
        return

    print_header(f"SIMULACIÓN WALK-FORWARD 7 DÍAS: {proxy.sim_dates[0]} → {proxy.sim_dates[-1]}")
    logger.info(f"Universo: {len(universe)} acciones")
    
    hub = EntryIntelligenceHub()
    trailing_stop = AdaptiveTrailingStop()
    open_positions = []
    closed_positions = []
    
    # Simular que el Vector Search está vacío para la simulación
    mock_journal = type('obj', (object,), {'find_similar_trades': lambda self, vec, limit: []})
    hub.journal = mock_journal()
    
    # Funnel Tracking
    funnel = {
        "Evaluations": 0,
        "Blocked_DEAD_SIGNAL": 0,
        "Blocked_CONTRA_FLOW": 0,
        "Blocked_OTHER": 0,
        "STALK": 0,
        "EXECUTE": 0
    }
    
    # ═══════════════════════════════════════════════════════════════
    # BUCLE DE SIMULACIÓN DIARIO
    # ═══════════════════════════════════════════════════════════════
    
    for current_date in proxy.sim_dates:
        print_header(f"📅 DÍA VIRTUAL: {current_date}")
        
        vix = proxy.get_vix_up_to(current_date)
        logger.info(f"VIX del día: {vix:.2f}")
        
        # 1. GESTIONAR POSICIONES ABIERTAS (Mover trailing stop, checkear salidas)
        if open_positions:
            logger.info("\n🛡️  Gestionando Posiciones Abiertas...")
            for pos in list(open_positions):
                prices_df = proxy.get_prices_up_to(pos.ticker, current_date)
                if prices_df.empty:
                    continue
                    
                current_price = prices_df['Close'].iloc[-1]
                low_price = prices_df['Low'].iloc[-1]
                high_price = prices_df['High'].iloc[-1]
                atr = float((prices_df['High'] - prices_df['Low']).rolling(14).mean().iloc[-1])
                
                # Update Tracking
                pos.prices_since_entry.append(current_price)
                if high_price > pos.highest_price:
                    pos.highest_price = high_price
                    
                # Recalculate Stop
                new_stop = trailing_stop.calculate_stop(
                    highest_since_entry=pos.highest_price,
                    current_atr=atr,
                    rs_vs_spy=1.0,
                    put_wall=0.0,
                    vix_current=vix,
                    flow_persistence_grade=pos.flow_grade
                )
                
                if new_stop > pos.current_stop:
                    pos.current_stop = new_stop
                    
                # Check Stop Hit (si el Low del día tocó el stop)
                if low_price <= pos.current_stop:
                    pos.status = "CLOSED"
                    pos.exit_date = current_date
                    pos.exit_price = pos.current_stop  # Slippage aproximado = ejecutado exacto en stop
                    pos.exit_reason = "STOP_HIT"
                    logger.info(f"  🔴 [EXIT] {pos.ticker} @ ${pos.exit_price:.2f} (STOP_HIT)")
                    open_positions.remove(pos)
                    closed_positions.append(pos)
                else:
                    pnl_pct = (current_price / pos.entry_price - 1) * 100
                    logger.info(f"  🟢 [HOLD] {pos.ticker} | PnL: {pnl_pct:+.2f}% | Stop: ${pos.current_stop:.2f}")

        # 2. ESCANEAR NUEVAS OPORTUNIDADES
        logger.info("\n🔍 Escaneando Universo para Entradas...")
        
        # Inject macro flow
        macro_spy = cache.get("macro", {}).get("spy_ticks", [])
        macro_tide = cache.get("macro", {}).get("tide", [])
        
        for ticker in universe:
            # Skip if already holding
            if any(p.ticker == ticker for p in open_positions):
                continue
                
            prices_df = proxy.get_prices_up_to(ticker, current_date)
            if prices_df is None or len(prices_df) < 20:
                continue
                
            recent_flow = proxy.get_flow_up_to(ticker, current_date)
            dp_prints = proxy.get_darkpool_up_to(ticker, current_date)
            
            # Mute internal hub logging for the simulation to avoid 2500 lines of spam
            logging.getLogger("application.entry_intelligence_hub").setLevel(logging.ERROR)
            logging.getLogger("application.options_awareness").setLevel(logging.ERROR)
            logging.getLogger("application.price_phase_intelligence").setLevel(logging.ERROR)
            logging.getLogger("application.event_flow_intelligence").setLevel(logging.ERROR)
            
            # Inject truncated flow
            hub.inject_uw_data(
                spy_ticks=macro_spy,  # Aproximación
                tide_data=macro_tide, # Aproximación
                flow_alerts=recent_flow,
                recent_flow=recent_flow,
                darkpool_prints=dp_prints
            )
            
            # Monkeypatch OptionsAwareness para la simulación
            hub._fetch_options_data = lambda t: {
                "put_wall": prices_df['Close'].iloc[-1] * 0.95, # Mock 5% OTM
                "call_wall": prices_df['Close'].iloc[-1] * 1.05,
                "gamma_regime": "POSITIVE" if vix < 20 else "NEGATIVE",
                "max_pain": prices_df['Close'].iloc[-1]
            }
            
            ref_date = date.fromisoformat(current_date)
            report = hub.evaluate(ticker, reference_date=ref_date, prices_df=prices_df, vix_override=vix)
            
            funnel["Evaluations"] += 1
            
            if report.final_verdict == "EXECUTE":
                funnel["EXECUTE"] += 1
                entry_price = prices_df['Close'].iloc[-1]
                logger.info(f"  🎯 [EXECUTE] {ticker} @ ${entry_price:.2f} | R:R={report.risk_reward}:1 | {report.flow_persistence_grade}")
                
                pos = VirtualPosition(
                    ticker=ticker,
                    entry_date=current_date,
                    entry_price=entry_price,
                    current_stop=report.stop_price,
                    highest_price=entry_price,
                    flow_grade=report.flow_persistence_grade,
                    prices_since_entry=[entry_price]
                )
                open_positions.append(pos)
            elif report.final_verdict == "STALK":
                funnel["STALK"] += 1
                # Demasiado ruido para imprimir todos los stalk
            elif report.final_verdict == "BLOCK":
                if "DEAD_SIGNAL" in report.final_reason:
                    funnel["Blocked_DEAD_SIGNAL"] += 1
                elif "CONTRA_FLOW" in report.final_reason:
                    funnel["Blocked_CONTRA_FLOW"] += 1
                else:
                    funnel["Blocked_OTHER"] += 1
                
    # ═══════════════════════════════════════════════════════════════
    # FIN DE LA SIMULACIÓN
    # ═══════════════════════════════════════════════════════════════
    
    print_header("RESULTADOS DE LA SIMULACIÓN DE 7 DÍAS (S&P 500)")
    logger.info(f"Evaluaciones Totales: {funnel['Evaluations']}")
    logger.info(f"  Bloqueados por DEAD_SIGNAL: {funnel['Blocked_DEAD_SIGNAL']}")
    logger.info(f"  Bloqueados por CONTRA_FLOW: {funnel['Blocked_CONTRA_FLOW']}")
    logger.info(f"  Bloqueados por OTROS: {funnel['Blocked_OTHER']}")
    logger.info(f"  En Observación (STALK): {funnel['STALK']}")
    logger.info(f"  Ejecutados (EXECUTE): {funnel['EXECUTE']}")
    
    logger.info(f"\nTrades Completados: {len(closed_positions)}")
    logger.info(f"Trades Abiertos al final: {len(open_positions)}")
    
    total_pnl = 0.0
    winners = 0
    
    for pos in closed_positions:
        pnl = (pos.exit_price / pos.entry_price) - 1.0
        pnl_dollars = pos.notional * pnl
        total_pnl += pnl_dollars
        if pnl > 0:
            winners += 1
            
        logger.info(f"  {pos.ticker}: {pnl*100:+.2f}% (${pnl_dollars:+.2f}) | {pos.flow_grade} | Salida: {pos.exit_reason}")
        
    for pos in open_positions:
        prices_df = proxy.get_prices_up_to(pos.ticker, proxy.sim_dates[-1])
        current_price = prices_df['Close'].iloc[-1]
        pnl = (current_price / pos.entry_price) - 1.0
        pnl_dollars = pos.notional * pnl
        total_pnl += pnl_dollars
        if pnl > 0:
            winners += 1
        
        logger.info(f"  {pos.ticker} [OPEN]: {pnl*100:+.2f}% (${pnl_dollars:+.2f}) | {pos.flow_grade}")
        
    total_trades = len(closed_positions) + len(open_positions)
    win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
    
    logger.info(f"\n💰 PnL Total Estimado: ${total_pnl:+.2f}")
    logger.info(f"🎯 Win Rate: {win_rate:.1f}%")

if __name__ == "__main__":
    run_simulation()
