"""
PAPER TRADING ORCHESTRATOR
============================
El director de orquesta que conecta TODOS los subsistemas:

Scanner → Qualifier → Journal(PRE) → Execution → Monitor → Journal(POST)

Cada decisión queda documentada. Cada error es una lección.
"""
import logging
import os
import uuid
import sys

import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, UTC

from application.trade_journal import TradeJournal, TradeJournalEntry
from application.portfolio_intelligence import (
    RelativeStrengthMonitor, AdaptiveTrailingStop,
    PortfolioOptimizer, RiskGuardian,
)
from application.execution_engine import (
    InstitutionalExecutionEngine, TradeContext, PositionState,
)
from application.entry_intelligence_hub import EntryIntelligenceHub

logger = logging.getLogger(__name__)


class PaperTradingOrchestrator:
    """
    Orquestador de Paper Trading con Alpaca.
    
    Flujo:
    1. scan() → Encontrar candidatos
    2. evaluate() → Fitness test + Journal PRE-TRADE
    3. execute() → Enviar orden a Alpaca Paper
    4. monitor() → Trailing stop + RS monitoring
    5. close() → Cerrar + Journal POST-TRADE + Lecciones
    6. learn() → Analizar patrones + ajustar parámetros
    """
    
    def __init__(self):
        self.journal = TradeJournal()
        self.rs_monitor = RelativeStrengthMonitor()
        self.trailing = AdaptiveTrailingStop()
        self.optimizer = PortfolioOptimizer()
        self.risk_guardian = RiskGuardian()
        self.execution = InstitutionalExecutionEngine()
        self.entry_hub = EntryIntelligenceHub()
        self._alpaca = None
        self._freeze_state = {}  # {ticker: freeze_start_time}
    
    def _get_alpaca(self):
        """Lazy init del cliente Alpaca."""
        if self._alpaca is None:
            from alpaca.trading.client import TradingClient
            api_key = os.getenv('ALPACA_API_KEY', '')
            secret = os.getenv('ALPACA_SECRET_KEY', '')
            if api_key and secret:
                self._alpaca = TradingClient(api_key, secret, paper=True)
                logger.info("Alpaca Paper Trading conectado.")
            else:
                logger.error("Alpaca credentials no configuradas.")
        return self._alpaca
    
    def get_account_status(self) -> dict:
        """Estado actual de la cuenta de Paper Trading y Exposición Estratégica."""
        client = self._get_alpaca()
        if not client:
            return {"error": "Alpaca no conectado"}
        
        try:
            account = client.get_account()
            positions = client.get_all_positions()
            
            # Recuperar tags de strategy_type del Journal para las posiciones abiertas
            open_trades = self.journal.get_open_trades()
            strategy_map = {t['ticker']: t.get('strategy_bucket', 'UNKNOWN') for t in open_trades}
            
            core_exposure = 0.0
            tactical_exposure = 0.0
            
            mapped_positions = []
            for p in positions:
                strategy = strategy_map.get(p.symbol, 'CORE')  # Default CORE si no hay tag
                market_val = float(p.market_value)
                
                if strategy == 'CORE':
                    core_exposure += market_val
                elif strategy == 'TACTICAL':
                    tactical_exposure += market_val
                
                mapped_positions.append({
                    "ticker": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
                    "market_value": market_val,
                    "strategy": strategy,
                })
            
            return {
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "equity": float(account.equity),
                "core_exposure": core_exposure,
                "tactical_exposure": tactical_exposure,
                "positions": mapped_positions,
                "num_positions": len(positions),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def create_trade_snapshot(self, ticker: str) -> dict:
        """Captura un snapshot completo del mercado para el journal."""
        try:
            # Datos del ticker
            data = yf.download(ticker, period='3mo', interval='1d', progress=False)
            spy = yf.download('SPY', period='3mo', interval='1d', progress=False)
            vix_data = yf.download('^VIX', period='5d', interval='1d', progress=False)
            
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            if isinstance(vix_data.columns, pd.MultiIndex):
                vix_data.columns = vix_data.columns.get_level_values(0)
            
            close = float(data['Close'].iloc[-1])
            prev_close = float(data['Close'].iloc[-2]) if len(data) > 1 else close
            sma20 = float(data['Close'].rolling(20).mean().iloc[-1])
            high_52w = float(data['High'].rolling(252).max().iloc[-1]) if len(data) >= 252 else float(data['High'].max())
            atr = float((data['High'] - data['Low']).rolling(14).mean().iloc[-1])
            avg_vol = float(data['Volume'].rolling(20).mean().iloc[-1])
            curr_vol = float(data['Volume'].iloc[-1])
            
            spy_close = float(spy['Close'].iloc[-1])
            spy_prev = float(spy['Close'].iloc[-2]) if len(spy) > 1 else spy_close
            
            vix = float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 17.0
            
            # RS
            stock_ret_20d = close / float(data['Close'].iloc[-20]) - 1 if len(data) >= 20 else 0
            spy_ret_20d = spy_close / float(spy['Close'].iloc[-20]) - 1 if len(spy) >= 20 else 0
            rs = (1 + stock_ret_20d) / (1 + spy_ret_20d) if spy_ret_20d != -1 else 1.0
            
            # RSI 14
            delta = data['Close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi_val = float(100 - (100 / (1 + gain.iloc[-1] / loss.iloc[-1]))) if loss.iloc[-1] != 0 else 50
            
            # Bollinger
            bb_sma = float(data['Close'].rolling(20).mean().iloc[-1])
            bb_std = float(data['Close'].rolling(20).std().iloc[-1])
            bb_upper = bb_sma + 2 * bb_std
            bb_lower = bb_sma - 2 * bb_std
            if close > bb_upper:
                bb_pos = "above_upper"
            elif close < bb_lower:
                bb_pos = "below_lower"
            elif close > bb_sma:
                bb_pos = "upper_half"
            else:
                bb_pos = "lower_half"
            
            # Info del ticker
            info = yf.Ticker(ticker).info
            sector = info.get('sector', 'Unknown')
            
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "price": close,
                "daily_change_pct": round((close / prev_close - 1) * 100, 2),
                "distance_from_20sma_pct": round((close / sma20 - 1) * 100, 2),
                "distance_from_52w_high_pct": round((close / high_52w - 1) * 100, 2),
                "volume": curr_vol,
                "relative_volume": round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0,
                "volume_trend": "accumulation" if curr_vol > avg_vol * 1.5 else "distribution" if curr_vol < avg_vol * 0.5 else "neutral",
                "atr": round(atr, 2),
                "atr_pct": round(atr / close * 100, 2),
                "rsi_14": round(rsi_val, 1),
                "bollinger_position": bb_pos,
                "vix": round(vix, 1),
                "spy_daily_change_pct": round((spy_close / spy_prev - 1) * 100, 2),
                "rs_vs_spy_20d": round(rs, 4),
                "stock_return_20d_pct": round(stock_ret_20d * 100, 2),
                "spy_return_20d_pct": round(spy_ret_20d * 100, 2),
                "sector": sector,
            }
        except Exception as e:
            logger.error(f"Error creating snapshot for {ticker}: {e}")
            return {"timestamp": datetime.now(UTC).isoformat(), "error": str(e)}
    
    def inject_whale_data(
        self,
        spy_ticks: list = None,
        flow_alerts: list = None,
        tide_data: list = None,
    ):
        """
        Inyecta datos de Unusual Whales pre-obtenidos via MCP.
        Llamar ANTES de run_core_scan() o run_tactical_scan().
        """
        self.entry_hub.inject_uw_data(
            spy_ticks=spy_ticks or [],
            flow_alerts=flow_alerts or [],
            tide_data=tide_data or [],
        )
        logger.info("🐋 Datos de ballenas inyectados en EntryHub")

    def open_position(
        self,
        ticker: str,
        thesis: str,
        strategy_type: str = "CORE",
        alpha_score: float = 0,
        qualifier_grade: str = "",
        insider_signal: str = "",
        sector_alignment: str = "",
        notional: float = 5000.0,
        pattern_tags: list = None,
        skip_intelligence: bool = False,
    ) -> dict:
        """
        Abre una posición en Paper Trading con journal completo.
        
        V2: Ejecuta el EntryIntelligenceHub ANTES de enviar la orden.
        El hub conecta OptionsAwareness, Kalman Wyckoff, UW Intelligence,
        EventFlowIntelligence y PricePhaseIntelligence para decidir.
        """
        trade_id = f"BT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{ticker}"
        
        # ═══ V2: Entry Intelligence Pipeline ═══════════════════
        if not skip_intelligence:
            intel = self.entry_hub.evaluate(ticker)
            
            if intel.final_verdict == "BLOCK":
                logger.warning(
                    f"⛔ {ticker} BLOQUEADO por EntryHub: {intel.final_reason}"
                )
                return {
                    "action": "BLOCKED",
                    "reason": f"EntryHub: {intel.final_reason}",
                    "whale_verdict": intel.whale_verdict,
                    "phase": intel.phase,
                    "intelligence": intel.to_dict(),
                }
            
            if intel.final_verdict == "STALK":
                logger.info(
                    f"⏳ {ticker} en STALK: {intel.final_reason}"
                )
                return {
                    "action": "STALKING",
                    "reason": f"EntryHub: {intel.final_reason}",
                    "whale_verdict": intel.whale_verdict,
                    "phase": intel.phase,
                    "risk_reward": intel.risk_reward,
                    "intelligence": intel.to_dict(),
                }
            
            # EXECUTE: adjust sizing by whale scale
            notional *= intel.final_scale
            logger.info(
                f"✅ {ticker} APROBADO: {intel.final_verdict} "
                f"(whale={intel.whale_verdict}, phase={intel.phase}, "
                f"R:R={intel.risk_reward}:1, scale={intel.final_scale:.0%})"
            )
        
        # 1. Snapshot pre-trade
        logger.info(f"Capturando snapshot para {ticker}...")
        snapshot = self.create_trade_snapshot(ticker)
        
        # 2. Risk Guardian check
        account = self.get_account_status()
        if 'error' in account:
            return {"error": account['error']}
        
        risk_check = self.risk_guardian.evaluate(
            current_capital=account.get('equity', 100000),
            daily_pnl_pct=0,
            strategy_type=strategy_type,
            core_exposure=account.get('core_exposure', 0),
            tactical_exposure=account.get('tactical_exposure', 0),
            current_vix=snapshot.get('vix', 17),
        )
        
        if not risk_check['can_trade']:
            return {
                "action": "BLOCKED",
                "reason": f"Risk Guardian: {risk_check['alerts']}",
            }
        
        # Ajustar sizing por risk guardian
        adjusted_notional = notional * risk_check['position_scale']
        
        # 3. Journal PRE-TRADE (incluye strategy bucket pseudo-inyectado en pattern_tags por compatibilidad)
        tags = pattern_tags or []
        tags.append(f"bucket_{strategy_type.lower()}")
        
        entry = TradeJournalEntry(
            trade_id=trade_id,
            ticker=ticker,
            direction="LONG",
            entry_thesis=f"[{strategy_type}] {thesis}",
            alpha_score=alpha_score,
            qualifier_grade=qualifier_grade,
            insider_signal=insider_signal,
            sector_alignment=sector_alignment,
            entry_snapshot=snapshot,
            entry_price=snapshot.get('price', 0),
            entry_time=datetime.now(UTC).isoformat(),
            entry_notional=adjusted_notional,
            rs_vs_spy=snapshot.get('rs_vs_spy_20d', 1.0),
            pattern_tags=tags,
            # V2: Capture full intelligence report for ML & post-mortem
            entry_intelligence=intel.to_dict() if (not skip_intelligence and intel) else None,
        )
        
        # 4. Smart Entry — Pre-Market Validation + Limit Order
        client = self._get_alpaca()
        if not client:
            return {"error": "Alpaca no conectado"}
        
        try:
            from backend.application.smart_entry import SmartEntryEngine
            
            smart = SmartEntryEngine()
            analysis_price = snapshot.get('price', 0)
            atr = snapshot.get('atr', 1.0)
            
            # Get current/premarket price from Alpaca
            current_price = analysis_price
            bid, ask = None, None
            try:
                from alpaca.data.requests import StockLatestQuoteRequest
                from alpaca.data import StockHistoricalDataClient
                
                data_client = StockHistoricalDataClient(
                    os.getenv('ALPACA_API_KEY'),
                    os.getenv('ALPACA_SECRET_KEY'),
                )
                quote = data_client.get_stock_latest_quote(
                    StockLatestQuoteRequest(symbol_or_symbols=ticker)
                )
                if ticker in quote:
                    q = quote[ticker]
                    bid = float(q.bid_price) if q.bid_price else None
                    ask = float(q.ask_price) if q.ask_price else None
                    current_price = float(q.ask_price) if q.ask_price else analysis_price
            except Exception as e:
                logger.warning(f"No se pudo obtener quote premarket para {ticker}: {e}")
            
            # Validate entry
            vix = snapshot.get('vix', 17)
            if vix > 25:
                smart = SmartEntryEngine(rules=smart.adaptive_rules(vix=vix))
            
            check = smart.validate_entry(
                ticker=ticker,
                analysis_price=analysis_price,
                current_price=current_price,
                bid=bid,
                ask=ask,
                atr=atr,
            )
            
            if not check.is_valid:
                logger.warning(f"❌ ENTRADA RECHAZADA: {ticker} — {check.rejection_reason}")
                return {
                    "action": "REJECTED",
                    "reason": check.rejection_reason,
                    "gap_pct": check.gap_pct,
                    "analysis_price": analysis_price,
                    "current_price": current_price,
                }
            
            # Submit LIMIT order (replaces MarketOrderRequest)
            order = smart.submit_alpaca_limit_order(
                client=client,
                check=check,
                notional=adjusted_notional,
            )
            
            entry.entry_order_id = str(order.id)
            entry.status = "OPEN"
            entry.entry_price = check.recommended_limit  # Limit price, not market
            
            # V2: Prefer gamma-anchored stop from EntryHub if available
            rs = snapshot.get('rs_vs_spy_20d', 1.0)
            if not skip_intelligence and intel and intel.stop_price > 0:
                # Hub calculated stop using Put Wall + VIX + phase awareness
                stop = intel.stop_price
                logger.info(f"   🛡️ Using gamma-anchored stop: ${stop:.2f} (Put Wall: ${intel.put_wall:.2f})")
            else:
                stop = check.recommended_stop
            entry.initial_stop_price = stop
            entry.current_stop_price = stop
            entry.highest_price = current_price
            
            # Registrar RS al entrar
            self.rs_monitor.register_entry(ticker, rs)
            
            # Guardar en journal
            self.journal.open_trade(entry)
            
            logger.info(
                f"✅ LIMIT ORDEN ENVIADA: {ticker} ${adjusted_notional:,.0f} "
                f"Limit=${check.recommended_limit:.2f} "
                f"(Gap={check.gap_pct:+.1f}%, Stop=${stop:.2f}) "
                f"Order ID: {order.id}"
            )
            
            return {
                "action": "BUY",
                "trade_id": trade_id,
                "ticker": ticker,
                "order_type": "LIMIT",
                "limit_price": check.recommended_limit,
                "notional": adjusted_notional,
                "order_id": str(order.id),
                "initial_stop": stop,
                "gap_pct": check.gap_pct,
                "analysis_price": analysis_price,
                "current_price": current_price,
                "snapshot": snapshot,
                "risk_scale": risk_check['position_scale'],
            }
            
        except Exception as e:
            logger.error(f"Error ejecutando orden {ticker}: {e}")
            return {"error": str(e)}
    
    def check_positions(self) -> list[dict]:
        """
        Revisa todas las posiciones abiertas y evalúa exits.
        
        V2: Auto-activates Event Freeze when FOMC/CPI/NFP is < 4 hours away.
        Uses EventFlowIntelligence to detect macro events.
        """
        account = self.get_account_status()
        if 'error' in account:
            return [{'error': account['error']}]
        
        # ═══ V2: Auto-activate Event Freeze ═══════════════════
        try:
            from backend.infrastructure.data_providers.event_flow_intelligence import EventFlowIntelligence
            event_flow = self.entry_hub.event_flow if hasattr(self.entry_hub, 'event_flow') else EventFlowIntelligence()
            # Assess current macro environment (no ticker-specific data needed)
            whale_check = event_flow.assess(
                spy_cumulative_delta=0,
                spy_signal="NEUTRAL",
                tide_direction="NEUTRAL",
                tide_accelerating=False,
                sweeps_count=0,
                calls_pct=50,
                am_pm_divergence=False,
            )
            if whale_check.freeze_stops:
                for pos in account.get('positions', []):
                    t = pos['ticker']
                    if t not in self._freeze_state:
                        self._freeze_state[t] = datetime.now(UTC)
                        logger.warning(
                            f"🧊 Event Freeze ACTIVADO para {t}: "
                            f"{whale_check.nearest_event} en {whale_check.hours_to_event:.0f}h"
                        )
        except Exception as e:
            logger.debug(f"Event freeze check skipped: {e}")
        
        evaluations = []
        for pos in account.get('positions', []):
            ticker = pos['ticker']
            current_price = pos['current_price']
            
            # RS actual
            snapshot = self.create_trade_snapshot(ticker)
            current_rs = snapshot.get('rs_vs_spy_20d', 1.0)
            
            # Alpha Decay Evaluator (Solo influye fuerte si es CORE)
            decay = self.rs_monitor.calculate_alpha_decay(ticker, current_rs)
            exit_eval = self.rs_monitor.should_exit(ticker, current_rs)
            
            # ═══ V2: Gamma-Aware Trailing Stop ═══════════════
            atr = snapshot.get('atr', 1.0)
            vix = snapshot.get('vix', 17.0)
            strategy = pos.get('strategy', 'CORE')
            
            # Check freeze state (event storm protection)
            if ticker in self._freeze_state:
                is_frozen = self.trailing.should_freeze(
                    freeze_stops=True,
                    freeze_start_time=self._freeze_state[ticker],
                )
                if is_frozen:
                    evaluations.append({
                        "ticker": ticker,
                        "strategy": strategy,
                        "current_price": current_price,
                        "unrealized_pnl_pct": pos['unrealized_pnl_pct'],
                        "rs_vs_spy": current_rs,
                        "alpha_decay": decay,
                        "trailing_stop": 0,
                        "exit_signal": {"should_exit": False},
                        "vix": vix,
                        "stop_frozen": True,
                        "freeze_reason": "Event storm protection — stop congelado",
                    })
                    logger.info(
                        f"🧊 {ticker}: Stop CONGELADO (evento macro en curso)"
                    )
                    continue
                else:
                    # Freeze expired
                    del self._freeze_state[ticker]
            
            # Fetch Put Wall for gamma anchoring (if available)
            put_wall = 0.0
            try:
                opts_data = self.entry_hub._fetch_options_data(ticker)
                put_wall = opts_data.get('put_wall', 0.0)
            except Exception:
                pass
            
            # Calculate stop with all 3 defenses:
            # 1. Put Wall anchoring (institutional floor)
            # 2. VIX dynamic scaling (wider in high vol)
            # 3. RS-based multiplier (original logic preserved)
            stop = self.trailing.calculate_stop(
                current_price, atr, current_rs,
                put_wall=put_wall,
                vix_current=vix,
            )
            
            # Ajuste adicional según Mente (Seykota vs Druckenmiller)
            if strategy == 'TACTICAL':
                # SEYKOTA MODE: Muy ajustado pero respetando Put Wall
                seykota_stop = current_price - (atr * 2.0)
                stop = max(stop, seykota_stop)
            else:
                # DRUCKENMILLER MODE: Más espacio al ruido.
                drucks_stop = current_price - (atr * 3.5)
                stop = min(stop, drucks_stop)
            
            evaluations.append({
                "ticker": ticker,
                "strategy": strategy,
                "current_price": current_price,
                "unrealized_pnl_pct": pos['unrealized_pnl_pct'],
                "rs_vs_spy": current_rs,
                "alpha_decay": decay,
                "trailing_stop": stop,
                "exit_signal": exit_eval,
                "vix": snapshot.get('vix', 17),
            })
        
        return evaluations
    
    def close_position(
        self,
        ticker: str,
        exit_reason: str,
        lesson: str = "",
        grade: str = "",
        what_right: str = "",
        what_wrong: str = "",
    ) -> dict:
        """
        Cierra una posición con journal POST-TRADE completo.
        """
        client = self._get_alpaca()
        if not client:
            return {"error": "Alpaca no conectado"}
        
        try:
            # Cerrar en Alpaca
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            
            positions = client.get_all_positions()
            pos = next((p for p in positions if p.symbol == ticker), None)
            
            if not pos:
                return {"error": f"No hay posición abierta en {ticker}"}
            
            qty = float(pos.qty)
            order = client.submit_order(MarketOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            
            # Snapshot de salida
            exit_snapshot = self.create_trade_snapshot(ticker)
            
            # Buscar trade en journal
            open_trades = self.journal.get_open_trades()
            trade_entry = next(
                (t for t in open_trades if t['ticker'] == ticker), None
            )
            
            if trade_entry:
                # Reconstruir entry para actualizar
                import json
                entry_data = self.journal.get_trade_full_data(trade_entry['trade_id'])
                
                if entry_data:
                    entry = TradeJournalEntry(**{
                        k: v for k, v in entry_data.items()
                        if k in TradeJournalEntry.__dataclass_fields__
                    })
                else:
                    entry = TradeJournalEntry(
                        trade_id=trade_entry['trade_id'],
                        ticker=ticker,
                        direction="LONG",
                    )
                
                # Actualizar con datos de cierre
                entry.exit_price = float(pos.current_price)
                entry.exit_time = datetime.now(UTC).isoformat()
                entry.exit_reason = exit_reason
                entry.exit_order_id = str(order.id)
                entry.exit_snapshot = exit_snapshot
                entry.pnl_dollars = float(pos.unrealized_pl)
                entry.pnl_pct = float(pos.unrealized_plpc) * 100
                entry.was_winner = float(pos.unrealized_pl) > 0
                entry.what_went_right = what_right
                entry.what_went_wrong = what_wrong
                entry.lesson_learned = lesson
                entry.grade = grade
                entry.status = "CLOSED"
                
                # R-multiple
                if entry.entry_price > 0 and entry.initial_stop_price > 0:
                    risk_per_share = abs(entry.entry_price - entry.initial_stop_price)
                    if risk_per_share > 0:
                        entry.pnl_r_multiple = (entry.exit_price - entry.entry_price) / risk_per_share
                
                self.journal.close_trade(entry)
            
            emoji = "✅" if float(pos.unrealized_pl) > 0 else "❌"
            logger.info(
                f"{emoji} POSICIÓN CERRADA: {ticker} "
                f"PnL: {float(pos.unrealized_plpc)*100:+.2f}% "
                f"(${float(pos.unrealized_pl):+,.0f}) "
                f"Reason: {exit_reason}"
            )
            
            return {
                "action": "SELL",
                "ticker": ticker,
                "qty": qty,
                "pnl_pct": float(pos.unrealized_plpc) * 100,
                "pnl_dollars": float(pos.unrealized_pl),
                "exit_reason": exit_reason,
                "order_id": str(order.id),
            }
            
        except Exception as e:
            logger.error(f"Error cerrando {ticker}: {e}")
            return {"error": str(e)}
    
    def generate_learning_report(self) -> dict:
        """
        Genera un reporte de aprendizaje a partir de todos los trades.
        """
        summary = self.journal.get_performance_summary()
        patterns = self.journal.get_pattern_stats()
        exit_stats = self.journal.get_exit_reason_stats()
        
        return {
            "performance": summary,
            "patterns": patterns,
            "exit_analysis": exit_stats,
            "recommendations": self._generate_recommendations(summary, patterns, exit_stats),
        }
    
    def _generate_recommendations(self, summary, patterns, exit_stats) -> list[str]:
        """Genera recomendaciones de ajuste basadas en los datos."""
        recs = []
        
        if summary.get('total_trades', 0) < 5:
            recs.append("Datos insuficientes: necesitamos mínimo 20 trades para conclusiones válidas.")
            return recs
        
        wr = summary.get('win_rate', 0)
        pf = summary.get('profit_factor', 0)
        
        if wr < 45:
            recs.append(f"Win Rate {wr:.0f}% < 45%. Considerar: tightear criterio de entrada o ampliar trailing stop.")
        
        if pf < 1.5:
            recs.append(f"Profit Factor {pf:.2f} < 1.5. El edge es delgado. Verificar que los stops no son demasiado tight.")
        
        # Análisis de exit reasons
        for er in exit_stats:
            if er['total'] >= 3 and er['win_rate'] < 30:
                recs.append(
                    f"Exit '{er['exit_reason']}' tiene WR de {er['win_rate']:.0f}% en {er['total']} trades. "
                    f"Revisar este trigger de salida."
                )
        
        # Análisis de patrones
        for p in patterns:
            if p['total'] >= 3:
                if p['win_rate'] > 70:
                    recs.append(f"Patrón '{p['pattern']}' tiene WR de {p['win_rate']:.0f}%. Buscar más de estos.")
                elif p['win_rate'] < 30:
                    recs.append(f"Patrón '{p['pattern']}' tiene WR de {p['win_rate']:.0f}%. Evitar o ajustar.")
        
        return recs

    def get_sp500_universe(self) -> list[str]:
        """Extrae el universo completo del S&P500 desde Wikipedia (o fallback amplio)."""
        try:
            import pandas as pd
            # Intento dinámico de obtener las 500
            table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
            tickers = table[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
            return tickers
        except Exception as e:
            logger.warning(f"No se pudo descargar S&P500 de Wikipedia: {e}. Usando fallback.")
            return ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','BRK-B','TSLA','LLY','JPM',
                    'UNH','V','XOM','JNJ','MA','PG','COST','HD','AVGO','ABBV',
                    'MRK','CVX','CRM','AMD','PEP','KO','ADBE','WMT','TMO','MCD',
                    'ACN','ORCL','LIN','CSCO','PM','ABT','IBM','GE','CAT','ISRG',
                    'NOW','TXN','QCOM','INTU','BKNG','SPGI','HON','AXP','COP','BA']

    def extract_guru_gems(self, guru_mcp_data: dict) -> list[str]:
        """Extrae mid/large caps fuera del SP500 fuertemente acumuladas por Gurús."""
        if not guru_mcp_data: return []
        gems = []
        for ticker, data in guru_mcp_data.items():
            holders = data if isinstance(data, list) else data.get("data", [])
            net_buys = sum(1 for h in holders if "buy" in str(h.get("action","")).lower() or "add" in str(h.get("action","")).lower())
            net_sells = sum(1 for h in holders if "sell" in str(h.get("action","")).lower() or "reduce" in str(h.get("action","")).lower())
            if net_buys > net_sells:
                gems.append(ticker)
        return gems

    def run_core_scan(
        self,
        max_positions: int = 5,
        notional_per_trade: float = 8000.0,
        guru_mcp_data: dict = None,
        macro_mcp_data: dict = None,
        sector_mcp_data: dict = None,
    ) -> dict:
        """
        ===================================================================
        MODO CHRISTOPHER HOHN (80% DEL CAPITAL)
        ===================================================================
        1. Obtiene S&P500 + Joyas de GuruFocus.
        2. Consulta la caché fundamental (MongoDB) antes de golpear APIs.
        3. UniverseFilter evalúa la CALIDAD SUPREMA con datos frescos.
        4. Pasa los ganadores estrictos al AlphaScanner para timing de entrada.
        5. Compra con Strategy: CORE.
        """
        from backend.application.universe_filter import UniverseFilter, UniverseCandidate
        from backend.application.alpha_scanner import AlphaScanner

        session_start = datetime.now(UTC).isoformat()
        logger.info(f"🏛️ INICIANDO ESCANEO CORE (Hohn Modo) — {session_start}")

        # 1. Chequeo de Account
        account = self.get_account_status()
        if 'error' in account: return {"error": account['error']}

        # Validamos si cabe otro core trade ($8000 en 80%) o si excedemos límite
        if account.get("core_exposure", 0) / max(account.get("equity", 1), 1) >= 0.80:
            logger.warning("🚫 Escaneo Core Anulado: Bucket CORE Lleno al 80%.")
            return {"status": "BUCKET_FULL"}

        current_positions = len(account.get('positions', []))
        slots_available = max(0, max_positions - current_positions)
        if slots_available == 0: return {"status": "PORTFOLIO_FULL"}

        # 2. Reclutar Candidatos (S&P500 + Guru Gems)
        sp500 = self.get_sp500_universe()
        guru_gems = self.extract_guru_gems(guru_mcp_data)
        raw_tickers = list(set(sp500 + guru_gems))
        logger.info(f"🔍 Evaluando Universo ESTRUCTURAL: {len(raw_tickers)} activos (SP500 + Guru).")

        # 2.5. Inicializar caché fundamental (MongoDB)
        cache = None
        cache_hits = 0
        cache_misses = 0
        try:
            from backend.infrastructure.data_providers.fundamental_cache import FundamentalCache
            cache = FundamentalCache()
        except Exception as e:
            logger.warning(f"Caché fundamental no disponible: {e}. Continuando sin caché.")

        # 3. Flujo HOHN: Primero filtramos la CALIDAD ESTRUCTURAL
        uf = UniverseFilter()
        if macro_mcp_data: uf.update_macro_regime(macro_mcp_data)
        
        # Filtraremos simulando Candidates, etiquetando Gemas
        # y enriqueciendo con datos de la caché si están disponibles
        base_candidates = []
        sp500_set = set(sp500)
        for t in raw_tickers:
            is_gem = t not in sp500_set
            candidate = UniverseCandidate(ticker=t, sector="Unknown", is_emerging_gem=is_gem)
            
            # Intentar enriquecer desde la caché
            if cache:
                cached = cache.get_cached_data(t)
                if cached and cached.get("status") == "fresh":
                    data = cached.get("data", {})
                    candidate.qgarp_score = data.get("qgarp_score", 0.0)
                    candidate.piotroski_f_score = data.get("piotroski_f_score", 0)
                    candidate.altman_z_score = data.get("altman_z_score", 0.0)
                    candidate.guru_conviction_score = data.get("guru_conviction_score", 0.0)
                    candidate.insider_conviction_score = data.get("insider_conviction_score", 0.0)
                    candidate.fcf_margin = data.get("fcf_margin", 0.0)
                    candidate.price_to_gf_value = data.get("price_to_gf_value", 0.0)
                    candidate.beneish_m_score = data.get("beneish_m_score", -3.0)
                    candidate.guru_accumulation = data.get("guru_accumulation", False)
                    cache_hits += 1
                else:
                    cache_misses += 1
            
            base_candidates.append(candidate)
        
        if cache:
            logger.info(f"💾 Caché: {cache_hits} hits, {cache_misses} misses de {len(raw_tickers)} tickers.")
        
        strong_candidates = uf.filter_and_rank(
            base_candidates,
            sector_mcp_data=sector_mcp_data,
            max_results=slots_available * 3, # Nos quedamos con la crema de la crema
        )

        if not strong_candidates:
            return {"status": "NO_CORE_CANDIDATES"}

        # 4. AlphaScanner (Tactical Entry sobre los fuertes fundamentales)
        strong_tickers = [c.ticker for c in strong_candidates]
        logger.info(f"🏢 Hohn seleccionó The Elite {len(strong_tickers)}. Buscando táctica con Eifert...")

        scanner = AlphaScanner()
        alpha_results = scanner.scan(
            tickers=strong_tickers,
            max_results=slots_available,
            include_qualifier=False,
            # No usamos finviz_movers porque Hohn no requiere explosión hoy
        )

        trades_attempted = []
        for result in alpha_results:
            ticker = result['ticker']
            score = result['alpha_score']
            logger.info(f"📝 Orden CORE para {ticker} (Alpha={score})")
            res = self.open_position(
                ticker=ticker,
                thesis=f"Moat Confirmado. Alpha Timing Score: {score}",
                strategy_type="CORE",
                alpha_score=score,
                notional=notional_per_trade,
            )
            trades_attempted.append(res)
            
        return {"status": "CORE_SCAN_COMPLETE", "trades": trades_attempted}

    def run_tactical_scan(
        self,
        max_positions: int = 5,
        notional_per_trade: float = 2000.0, 
        finviz_movers_data: dict = None,
        macro_mcp_data: dict = None,
    ) -> dict:
        """
        ===================================================================
        MODO TACTICAL EIFERT/TUDOR JONES (20% DEL CAPITAL)
        ===================================================================
        Busca momentum direccional puro y asimetrías de opciones.
        Ignora calidades profundas, busca la acción del mercado de hoy.
        """
        from backend.application.alpha_scanner import AlphaScanner
        from backend.application.universe_filter import UniverseFilter, UniverseCandidate

        logger.info(f"🔥 INICIANDO ESCANEO TÁCTICO (Eifert Modo)")
        
        account = self.get_account_status()
        if 'error' in account: return {"error": account['error']}

        if account.get("tactical_exposure", 0) / max(account.get("equity", 1), 1) >= 0.20:
            logger.warning("🚫 Escaneo Táctico Anulado: Bucket TACTICAL Lleno al 20%.")
            return {"status": "BUCKET_FULL"}

        current_positions = len(account.get('positions', []))
        slots_available = max(0, max_positions - current_positions)
        if slots_available == 0: return {"status": "PORTFOLIO_FULL"}

        scanner = AlphaScanner()
        # Escanea FinViz movers (si tickers=None)
        alpha_results = scanner.scan(
            tickers=None, 
            max_results=slots_available * 2,
            finviz_movers_data=finviz_movers_data,
        )

        if not alpha_results: return {"status": "NO_MOVERS"}
        
        # Filtro muy leve (UniverseFilter solo para evitar basuras extremas)
        uf = UniverseFilter()
        if macro_mcp_data: uf.update_macro_regime(macro_mcp_data)
        
        candidates = [UniverseCandidate(ticker=r['ticker'], alpha_score=r['alpha_score']) for r in alpha_results]
        approved = uf.filter_and_rank(candidates, max_results=slots_available) # Podríamos relajar filtros aquí luego

        trades_attempted = []
        for candidate in approved:
            ticker = candidate.ticker
            score = candidate.alpha_score
            logger.info(f"📝 Orden TACTICAL para {ticker} (Alpha={score})")
            res = self.open_position(
                ticker=ticker,
                thesis=f"Gamma Squeeze/ Momentum Surge hoy. Alpha: {score}",
                strategy_type="TACTICAL",
                alpha_score=score,
                notional=notional_per_trade,
            )
            trades_attempted.append(res)
            
        return {"status": "TACTICAL_SCAN_COMPLETE", "trades": trades_attempted}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')

    # ─── DEMO: Conectar y verificar estado ───
    # Credentials loaded from .env (never hardcode secrets)
    from dotenv import load_dotenv
    load_dotenv()

    orch = PaperTradingOrchestrator()

    print(f"\n{'='*60}")
    print(f"  BOTERO TRADE: Paper Trading Status")
    print(f"{'='*60}")

    status = orch.get_account_status()
    if 'error' not in status:
        print(f"\n  💰 Capital: ${status['equity']:,.2f}")
        print(f"  💵 Cash: ${status['cash']:,.2f}")
        print(f"  📊 Posiciones abiertas: {status['num_positions']}")

        for p in status.get('positions', []):
            emoji = "📈" if p['unrealized_pnl'] > 0 else "📉"
            print(f"    {emoji} {p['ticker']}: {p['qty']} shares @ ${p['avg_entry']:.2f} "
                  f"→ ${p['current_price']:.2f} ({p['unrealized_pnl_pct']:+.2f}%)")

        print(f"\n  Journal: {len(orch.journal.get_open_trades())} trades registrados")
    else:
        print(f"\n  ❌ Error: {status['error']}")

    print(f"\n{'='*60}")
