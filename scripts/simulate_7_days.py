#!/usr/bin/env python3
"""
SIMULADOR HISTÓRICO WALK-FORWARD (V9 — Strategy-Aware)
=======================================================
Simula 7 días de trading institucionales de forma secuencial.
- Extrae la fecha virtual 't'.
- Trunca los datos históricos (Precios, VIX, Flujo) para que no haya look-ahead bias.
- Ejecuta el EntryIntelligenceHub para el universo completo.
- NUEVO V9: Detecta top movers como TACTICAL y evalúa con reglas diferentes.
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
    pattern: str = "NONE"
    strategy_bucket: str = "CORE"
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
            
        # Tomar solo los últimos 5 días como nuestra ventana de simulación
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

    def identify_daily_movers(self, universe: list, date_str: str, prev_date: str, top_n: int = 15) -> list:
        """
        Identify the top movers for the day by gap and volume.
        These are TACTICAL candidates (high momentum, potential short squeeze, etc.)
        """
        movers = []
        for ticker in universe:
            prices = self.cache.get("prices", {}).get(ticker, {})
            today = prices.get(date_str)
            yesterday = prices.get(prev_date)
            
            if not today or not yesterday:
                continue
            
            # Gap% = (today's open - yesterday's close) / yesterday's close
            gap_pct = (today['Open'] / yesterday['Close'] - 1) * 100 if yesterday['Close'] > 0 else 0
            
            # RVOL = today's volume / avg 20d volume (approximated from yesterday's volume)
            rvol = today['Volume'] / yesterday['Volume'] if yesterday['Volume'] > 0 else 1.0
            
            # Intraday move
            intraday_pct = (today['Close'] / today['Open'] - 1) * 100 if today['Open'] > 0 else 0
            
            # Momentum score: combine gap + intraday + volume
            momentum_score = abs(gap_pct) * 0.4 + abs(intraday_pct) * 0.3 + min(rvol, 5.0) * 0.3
            
            movers.append({
                'ticker': ticker,
                'gap_pct': gap_pct,
                'intraday_pct': intraday_pct,
                'rvol': rvol,
                'momentum_score': momentum_score,
            })
        
        # Sort by momentum score descending and take top N
        movers.sort(key=lambda x: x['momentum_score'], reverse=True)
        return movers[:top_n]


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

    print_header(f"SIMULACIÓN WALK-FORWARD V9 (Strategy-Aware): {proxy.sim_dates[0]} → {proxy.sim_dates[-1]}")
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
        "Core_Evaluations": 0,
        "Tactical_Evaluations": 0,
        "Blocked_DEAD_SIGNAL": 0,
        "Blocked_CONTRA_FLOW": 0,
        "Blocked_OTHER": 0,
        "STALK": 0,
        "EXECUTE_CORE": 0,
        "EXECUTE_TACTICAL": 0,
    }
    
    # ═══════════════════════════════════════════════════════════════
    # BUCLE DE SIMULACIÓN DIARIO
    # ═══════════════════════════════════════════════════════════════
    
    for day_idx, current_date in enumerate(proxy.sim_dates):
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
                sma20 = float(prices_df['Close'].rolling(20).mean().iloc[-1])
                
                # Update Tracking
                pos.prices_since_entry.append(current_price)
                if high_price > pos.highest_price:
                    pos.highest_price = high_price
                
                pnl_pct = (current_price / pos.entry_price - 1) * 100
                mfe_pct = (pos.highest_price / pos.entry_price - 1) * 100
                days_held = len(pos.prices_since_entry) - 1
                
                # ── INTELLIGENT EXIT LOGIC (Forensic V9) ──────────────
                exit_triggered = False
                exit_reason = ""
                exit_price = current_price
                
                # EXIT 1: Stop Loss Hit (standard)
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
                    
                if low_price <= pos.current_stop:
                    exit_triggered = True
                    exit_reason = "STOP_HIT|tool=AdaptiveTrailingStop"
                    exit_price = pos.current_stop
                
                # EXIT 2: TACTICAL Profit Target (forensic: most profit on D0-D1)
                # Take profit when high reaches 2×ATR gain
                if not exit_triggered and pos.strategy_bucket == "TACTICAL":
                    profit_target_pct = (2.0 * atr / pos.entry_price) * 100
                    if mfe_pct >= max(profit_target_pct, 2.0):
                        # High hit our target — exit at target price
                        target_price = pos.entry_price * (1 + max(profit_target_pct, 2.0) / 100)
                        if high_price >= target_price:
                            exit_triggered = True
                            exit_reason = f"PROFIT_TARGET_{max(profit_target_pct, 2.0):.0f}%|tool=ATR_Target"
                            exit_price = target_price
                
                # EXIT 3: TACTICAL Time Stop (max 3 days)
                if not exit_triggered and pos.strategy_bucket == "TACTICAL" and days_held >= 3:
                    exit_triggered = True
                    exit_reason = "TIME_STOP_3D|tool=TimeStop"
                    exit_price = current_price
                
                # EXIT 4: Mean-Reversion Target (CONTRARIAN_DIP: exit when reclaims SMA20)
                if not exit_triggered and pos.strategy_bucket == "TACTICAL" and current_price >= sma20 and pos.entry_price < sma20:
                    exit_triggered = True
                    exit_reason = "SMA20_RECLAIM|tool=MeanReversion"
                    exit_price = current_price
                
                # EXIT 5: Trailing stop tightening after MFE > 3%
                if not exit_triggered and mfe_pct > 3.0:
                    # Lock in 40% of MFE
                    lock_price = pos.entry_price * (1 + mfe_pct * 0.4 / 100)
                    if current_price <= lock_price and pos.current_stop < lock_price:
                        pos.current_stop = lock_price
                
                if exit_triggered:
                    pos.status = "CLOSED"
                    pos.exit_date = current_date
                    pos.exit_price = exit_price
                    pos.exit_reason = exit_reason
                    exit_pnl = (exit_price / pos.entry_price - 1) * 100
                    emoji = "🟢" if exit_pnl > 0 else "🔴"
                    logger.info(f"  {emoji} [EXIT] {pos.ticker} ({pos.strategy_bucket}) @ ${exit_price:.2f} ({exit_reason}) PnL={exit_pnl:+.1f}%")
                    open_positions.remove(pos)
                    closed_positions.append(pos)
                else:
                    logger.info(f"  🟢 [HOLD] {pos.ticker} ({pos.strategy_bucket}) | PnL: {pnl_pct:+.2f}% | MFE: {mfe_pct:+.1f}% | D{days_held} | Stop: ${pos.current_stop:.2f}")

        # 2. IDENTIFY TACTICAL MOVERS (V9: Strategy-Aware)
        tactical_tickers = set()
        if day_idx > 0:
            prev_date = proxy.sim_dates[day_idx - 1]
            movers = proxy.identify_daily_movers(universe, current_date, prev_date, top_n=15)
            tactical_tickers = {m['ticker'] for m in movers}
            if movers:
                logger.info(f"\n🔥 Top {len(movers)} Movers del Día (TACTICAL candidates):")
                for m in movers[:5]:
                    logger.info(f"   {m['ticker']}: Gap={m['gap_pct']:+.1f}%, Intraday={m['intraday_pct']:+.1f}%, RVOL={m['rvol']:.1f}x")

        # 3. ESCANEAR NUEVAS OPORTUNIDADES
        logger.info("\n🔍 Escaneando Universo para Entradas...")
        
        # Inject macro flow
        macro_spy = cache.get("macro", {}).get("spy_ticks", [])
        macro_tide = cache.get("macro", {}).get("tide", [])
        
        # Mute internal hub logging
        logging.getLogger("application.entry_intelligence_hub").setLevel(logging.ERROR)
        logging.getLogger("application.options_awareness").setLevel(logging.ERROR)
        logging.getLogger("application.price_phase_intelligence").setLevel(logging.ERROR)
        logging.getLogger("application.event_flow_intelligence").setLevel(logging.ERROR)
        logging.getLogger("infrastructure.data_providers.event_flow_intelligence").setLevel(logging.ERROR)
        logging.getLogger("infrastructure.data_providers.uw_intelligence").setLevel(logging.ERROR)
        logging.getLogger("infrastructure.data_providers.flow_persistence").setLevel(logging.ERROR)
        
        for ticker in universe:
            # Skip if already holding
            if any(p.ticker == ticker for p in open_positions):
                continue
                
            prices_df = proxy.get_prices_up_to(ticker, current_date)
            if prices_df is None or len(prices_df) < 20:
                continue
                
            recent_flow = proxy.get_flow_up_to(ticker, current_date)
            dp_prints = proxy.get_darkpool_up_to(ticker, current_date)
            
            # Inject truncated flow
            hub.inject_uw_data(
                spy_ticks=macro_spy,
                tide_data=macro_tide,
                flow_alerts=recent_flow,
                recent_flow=recent_flow,
                darkpool_prints=dp_prints
            )
            
            # Fix #5: ATR-aware Options mock (replaces flat ±5%)
            atr_sim = float((prices_df['High'] - prices_df['Low']).rolling(14).mean().iloc[-1]) if len(prices_df) >= 14 else prices_df['Close'].iloc[-1] * 0.02
            close_for_opts = float(prices_df['Close'].iloc[-1])
            hub._fetch_options_data = lambda t, c=close_for_opts, a=atr_sim: {
                "put_wall": round(c - 2.0 * a, 2),    # Support ~2×ATR below
                "call_wall": round(c + 3.0 * a, 2),   # Resistance ~3×ATR above
                "gamma_regime": "POSITIVE" if vix < 20 else "NEGATIVE",
                "max_pain": round(c, 2),
            }
            
            # V9: Determine strategy bucket
            strategy = "TACTICAL" if ticker in tactical_tickers else "CORE"
            
            ref_date = date.fromisoformat(current_date)
            report = hub.evaluate(
                ticker, 
                reference_date=ref_date, 
                prices_df=prices_df, 
                vix_override=vix,
                strategy_bucket=strategy,
            )
            
            if strategy == "CORE":
                funnel["Core_Evaluations"] += 1
            else:
                funnel["Tactical_Evaluations"] += 1
            
            if report.final_verdict == "EXECUTE":
                bucket_key = f"EXECUTE_{strategy}"
                funnel[bucket_key] = funnel.get(bucket_key, 0) + 1
                entry_price = prices_df['Close'].iloc[-1]
                pattern = getattr(report, 'candlestick_pattern', 'NONE')
                emoji = "🎯" if strategy == "CORE" else "🔥"
                logger.info(f"  {emoji} [EXECUTE {strategy}] {ticker} @ ${entry_price:.2f} | R:R={report.risk_reward}:1 | {report.flow_persistence_grade} | Pat: {pattern}")
                
                pos = VirtualPosition(
                    ticker=ticker,
                    entry_date=current_date,
                    entry_price=entry_price,
                    current_stop=report.stop_price,
                    highest_price=entry_price,
                    flow_grade=report.flow_persistence_grade,
                    pattern=pattern,
                    strategy_bucket=strategy,
                    prices_since_entry=[entry_price]
                )
                open_positions.append(pos)
            elif report.final_verdict == "STALK":
                funnel["STALK"] += 1
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
    
    print_header("RESULTADOS DE LA SIMULACIÓN V9 (Strategy-Aware, S&P 500)")
    logger.info(f"Evaluaciones CORE: {funnel['Core_Evaluations']}")
    logger.info(f"Evaluaciones TACTICAL: {funnel['Tactical_Evaluations']}")
    logger.info(f"  Bloqueados por DEAD_SIGNAL: {funnel['Blocked_DEAD_SIGNAL']}")
    logger.info(f"  Bloqueados por CONTRA_FLOW: {funnel['Blocked_CONTRA_FLOW']}")
    logger.info(f"  Bloqueados por OTROS: {funnel['Blocked_OTHER']}")
    logger.info(f"  En Observación (STALK): {funnel['STALK']}")
    logger.info(f"  Ejecutados CORE: {funnel['EXECUTE_CORE']}")
    logger.info(f"  Ejecutados TACTICAL: {funnel['EXECUTE_TACTICAL']}")
    
    logger.info(f"\nTrades Completados: {len(closed_positions)}")
    logger.info(f"Trades Abiertos al final: {len(open_positions)}")
    
    total_pnl = 0.0
    winners = 0
    core_pnl = 0.0
    tactical_pnl = 0.0
    
    for pos in closed_positions:
        pnl = (pos.exit_price / pos.entry_price) - 1.0
        pnl_dollars = pos.notional * pnl
        total_pnl += pnl_dollars
        if pos.strategy_bucket == "TACTICAL":
            tactical_pnl += pnl_dollars
        else:
            core_pnl += pnl_dollars
        if pnl > 0:
            winners += 1
            
        emoji = "✅" if pnl > 0 else "❌"
        logger.info(f"  {emoji} {pos.ticker} ({pos.strategy_bucket}): {pnl*100:+.2f}% (${pnl_dollars:+.2f}) | {pos.flow_grade} | Salida: {pos.exit_reason}")
        
    for pos in open_positions:
        prices_df = proxy.get_prices_up_to(pos.ticker, proxy.sim_dates[-1])
        if prices_df.empty:
            continue
        current_price = prices_df['Close'].iloc[-1]
        pnl = (current_price / pos.entry_price) - 1.0
        pnl_dollars = pos.notional * pnl
        total_pnl += pnl_dollars
        if pos.strategy_bucket == "TACTICAL":
            tactical_pnl += pnl_dollars
        else:
            core_pnl += pnl_dollars
        if pnl > 0:
            winners += 1
        
        emoji = "📈" if pnl > 0 else "📉"
        logger.info(f"  {emoji} {pos.ticker} ({pos.strategy_bucket}) [OPEN]: {pnl*100:+.2f}% (${pnl_dollars:+.2f}) | {pos.flow_grade}")
        
    total_trades = len(closed_positions) + len(open_positions)
    win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
    
    print_header("RESUMEN FINANCIERO")
    logger.info(f"💰 PnL Total: ${total_pnl:+.2f}")
    logger.info(f"   PnL CORE (80%): ${core_pnl:+.2f}")
    logger.info(f"   PnL TACTICAL (20%): ${tactical_pnl:+.2f}")
    logger.info(f"🎯 Win Rate: {win_rate:.1f}% ({winners}/{total_trades})")

if __name__ == "__main__":
    run_simulation()
