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

from backend.application.trade_journal import TradeJournal, TradeJournalEntry
from backend.application.portfolio_intelligence import (
    RelativeStrengthMonitor, AdaptiveTrailingStop,
    PortfolioOptimizer, RiskGuardian,
)
from backend.application.execution_engine import (
    InstitutionalExecutionEngine, TradeContext, PositionState,
)

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
        self._alpaca = None
    
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
        """Estado actual de la cuenta de Paper Trading."""
        client = self._get_alpaca()
        if not client:
            return {"error": "Alpaca no conectado"}
        
        try:
            account = client.get_account()
            positions = client.get_all_positions()
            
            return {
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "equity": float(account.equity),
                "positions": [
                    {
                        "ticker": p.symbol,
                        "qty": float(p.qty),
                        "avg_entry": float(p.avg_entry_price),
                        "current_price": float(p.current_price),
                        "unrealized_pnl": float(p.unrealized_pl),
                        "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
                        "market_value": float(p.market_value),
                    }
                    for p in positions
                ],
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
    
    def open_position(
        self,
        ticker: str,
        thesis: str,
        alpha_score: float = 0,
        qualifier_grade: str = "",
        insider_signal: str = "",
        sector_alignment: str = "",
        notional: float = 5000.0,
        pattern_tags: list = None,
    ) -> dict:
        """
        Abre una posición en Paper Trading con journal completo.
        """
        trade_id = f"BT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{ticker}"
        
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
            current_vix=snapshot.get('vix', 17),
        )
        
        if not risk_check['can_trade']:
            return {
                "action": "BLOCKED",
                "reason": f"Risk Guardian: {risk_check['alerts']}",
            }
        
        # Ajustar sizing por risk guardian
        adjusted_notional = notional * risk_check['position_scale']
        
        # 3. Journal PRE-TRADE
        entry = TradeJournalEntry(
            trade_id=trade_id,
            ticker=ticker,
            direction="LONG",
            entry_thesis=thesis,
            alpha_score=alpha_score,
            qualifier_grade=qualifier_grade,
            insider_signal=insider_signal,
            sector_alignment=sector_alignment,
            entry_snapshot=snapshot,
            entry_price=snapshot.get('price', 0),
            entry_time=datetime.now(UTC).isoformat(),
            entry_notional=adjusted_notional,
            rs_vs_spy=snapshot.get('rs_vs_spy_20d', 1.0),
            pattern_tags=pattern_tags or [],
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
            
            # Stop from SmartEntry (ATR-based)
            rs = snapshot.get('rs_vs_spy_20d', 1.0)
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
        """
        account = self.get_account_status()
        if 'error' in account:
            return [{"error": account['error']}]
        
        evaluations = []
        for pos in account.get('positions', []):
            ticker = pos['ticker']
            current_price = pos['current_price']
            
            # RS actual
            snapshot = self.create_trade_snapshot(ticker)
            current_rs = snapshot.get('rs_vs_spy_20d', 1.0)
            
            # Alpha Decay
            decay = self.rs_monitor.calculate_alpha_decay(ticker, current_rs)
            exit_eval = self.rs_monitor.should_exit(ticker, current_rs)
            
            # Trailing stop
            atr = snapshot.get('atr', 1.0)
            stop = self.trailing.calculate_stop(current_price, atr, current_rs)
            
            evaluations.append({
                "ticker": ticker,
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
                conn = __import__('sqlite3').connect(self.journal.db_path)
                cursor = conn.execute(
                    "SELECT full_data FROM trades WHERE trade_id = ?",
                    (trade_entry['trade_id'],)
                )
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    entry_data = json.loads(row[0])
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

    def run_daily_scan(
        self,
        candidate_tickers: list[str] = None,
        max_positions: int = 5,
        notional_per_trade: float = 5000.0,
        macro_mcp_data: dict = None,
        sector_mcp_data: dict = None,
        guru_mcp_data: dict = None,
        finviz_movers_data: dict = None,
    ) -> dict:
        """
        Pipeline completo de selección y ejecución diaria.

        Invoca en secuencia:
        1. AlphaScanner → genera ranking de candidatos
        2. UniverseFilter → aplica scoring Guru + macro
        3. SmartEntryEngine → valida y limita la entrada

        Args:
            candidate_tickers: Lista de tickers a evaluar. Si None, usa Finviz movers.
            max_positions: Máximo de posiciones a abrir en la sesión.
            notional_per_trade: Capital nominal por trade ($).
            macro_mcp_data: Datos macro pre-fetched del MCP de FRED.
            sector_mcp_data: Datos sectoriales pre-fetched de Finviz MCP.
            guru_mcp_data: Datos GuruFocus pre-fetched por ticker.
            finviz_movers_data: Respuesta del MCP volume_surge_screener.

        Returns:
            Resumen de la sesión de scanning con trades intentados.
        """
        from backend.application.alpha_scanner import AlphaScanner
        from backend.application.universe_filter import UniverseFilter, UniverseCandidate

        session_start = datetime.now(UTC).isoformat()
        logger.info(f"🚀 run_daily_scan() iniciado — {session_start}")

        # ── 1. Account check ────────────────────────────────────────
        account = self.get_account_status()
        if 'error' in account:
            return {"error": account['error'], "session_start": session_start}

        current_positions = len(account.get('positions', []))
        slots_available = max(0, max_positions - current_positions)
        if slots_available == 0:
            logger.info(f"🛑 Portfolio lleno ({current_positions}/{max_positions} posiciones). No se escanea.")
            return {
                "status": "PORTFOLIO_FULL",
                "positions": current_positions,
                "session_start": session_start,
            }

        logger.info(f"📊 Slots disponibles: {slots_available} | Equity: ${account['equity']:,.0f}")

        # ── 2. Alpha Scanner ─────────────────────────────────────────
        scanner = AlphaScanner()
        alpha_results = scanner.scan(
            tickers=candidate_tickers,
            max_results=slots_available * 3,  # Buffer 3x para que el filtro elija
            include_qualifier=False,
            finviz_movers_data=finviz_movers_data,
            guru_mcp_data=guru_mcp_data,
        )

        if not alpha_results:
            logger.warning("⚠️  AlphaScanner no retornó candidatos. Sesión terminada.")
            return {"status": "NO_CANDIDATES", "session_start": session_start}

        logger.info(f"🔍 AlphaScanner: {len(alpha_results)} candidatos rankeados")

        # ── 3. Universe Filter (scoring Guru + macro) ────────────────
        uf = UniverseFilter()
        existing_tickers = [p['ticker'] for p in account.get('positions', [])]

        candidates = []
        for result in alpha_results:
            ticker = result.get('ticker', '')
            if not ticker or ticker in existing_tickers:
                continue
            candidates.append(UniverseCandidate(
                ticker=ticker,
                alpha_score=result.get('alpha_score', 0),
                sector=result.get('sector', 'Unknown'),
                rs_vs_spy=result.get('rs_vs_spy', 1.0),
                insider_signal=result.get('insider_signal', 'neutral'),
                sector_alignment=result.get('sector_alignment', 'NEUTRAL'),
                # Guru metrics populated if mcp data provided
            ))

        if macro_mcp_data:
            uf.update_macro_regime(macro_mcp_data)

        top_candidates = uf.filter_and_rank(
            candidates,
            sector_mcp_data=sector_mcp_data,
            max_results=slots_available,
        )

        if not top_candidates:
            logger.info("ℹ️  UniverseFilter descartó todos los candidatos. Nada aprobado.")
            return {"status": "ALL_FILTERED", "candidates_scanned": len(candidates), "session_start": session_start}

        logger.info(f"✅ UniverseFilter aprobó {len(top_candidates)} tickers: {[c.ticker for c in top_candidates]}")

        # ── 4. Ejecutar trades aprobados ─────────────────────────────
        trades_attempted = []
        for candidate in top_candidates:
            logger.info(f"📝 Intentando entrada: {candidate.ticker} (score={candidate.alpha_score:.1f})")
            result = self.open_position(
                ticker=candidate.ticker,
                thesis=f"Alpha={candidate.alpha_score:.1f} | Sector={candidate.sector} | RS={candidate.rs_vs_spy:.3f} | {candidate.sector_alignment}",
                alpha_score=candidate.alpha_score,
                insider_signal=candidate.insider_signal,
                sector_alignment=candidate.sector_alignment,
                notional=notional_per_trade,
            )
            trades_attempted.append({
                "ticker": candidate.ticker,
                "action": result.get('action', 'ERROR'),
                "reason": result.get('reason', result.get('error', '')),
                "limit_price": result.get('limit_price'),
                "order_id": result.get('order_id'),
            })

        executed = [t for t in trades_attempted if t['action'] == 'BUY']
        rejected = [t for t in trades_attempted if t['action'] == 'REJECTED']
        errors = [t for t in trades_attempted if t['action'] == 'ERROR']

        session_summary = {
            "status": "COMPLETED",
            "session_start": session_start,
            "session_end": datetime.now(UTC).isoformat(),
            "slots_available": slots_available,
            "candidates_scanned": len(alpha_results),
            "candidates_approved": len(top_candidates),
            "trades_executed": len(executed),
            "trades_rejected": len(rejected),
            "trades_errored": len(errors),
            "trades": trades_attempted,
        }

        logger.info(
            f"📈 Sesión completada: {len(executed)} ejecutados, "
            f"{len(rejected)} rechazados, {len(errors)} errores"
        )
        return session_summary


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
