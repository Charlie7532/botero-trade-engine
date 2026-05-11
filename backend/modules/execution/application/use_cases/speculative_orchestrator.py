"""
SPECULATIVE ORCHESTRATOR — Seykota Daemon
============================================
Orquestador de ejecución para el departamento SPECULATIVE.

Cadencia: INTRADIARIA (cada 15 minutos en horario de mercado)
Pipeline: SpeculativeScanner → SpeculativeEntryHub → SpeculativeSurveillance
Exit: SpeculativeExitEngine (ATR stops, time stops, RS decay)
Journal: SPECULATIVE journal exclusivo
Broker: SPECULATIVE broker exclusivo

NO USA: moat decay, thesis death, cadencia diaria.
"""
import logging
import asyncio
from datetime import datetime, UTC

from backend.modules.execution.domain.ports.broker_port import BrokerPort
from backend.modules.execution.domain.ports.trade_journal_port import TradeJournalPort
from backend.modules.entry_decision.domain.ports.market_data_port import EntryMarketDataPort
from backend.modules.execution.domain.entities.trade_record import TradeJournalEntry
from backend.modules.portfolio_management.domain.rules.risk_guardian import RiskGuardian
from backend.modules.execution.domain.rules.exit_rules import SpeculativeExitEngine
from backend.modules.execution.domain.entities.exit_context import TradeState, MarketContext

logger = logging.getLogger(__name__)


class SpeculativeOrchestrator:
    """
    Daemon de ejecución SPECULATIVE.

    Seykota: "Cut losses. Cut losses. Cut losses."
    PTJ: "I'm always thinking about losing money."

    Cadencia intradiaria (15min). Posiciones de horas a días.
    """

    def __init__(
        self,
        broker: BrokerPort,
        journal: TradeJournalPort,
        market_data: EntryMarketDataPort,
        entry_hub=None,
        surveillance=None,
    ):
        self.broker = broker
        self.journal = journal
        self.market_data = market_data
        self.entry_hub = entry_hub  # SpeculativeEntryHub
        self.surveillance = surveillance  # SpeculativeSurveillance
        self.exit_engine = SpeculativeExitEngine()
        self.risk_guardian = RiskGuardian()



    def get_portfolio_status(self) -> dict:
        """Estado actual de la cartera SPECULATIVE."""
        try:
            try:
                portfolio = asyncio.get_event_loop().run_until_complete(self.broker.get_portfolio())
            except RuntimeError:
                portfolio = asyncio.run(self.broker.get_portfolio())

            positions = []
            total_exposure = 0.0
            for p in portfolio.positions:
                mv = p.market_price * p.quantity
                total_exposure += mv
                positions.append({
                    "ticker": p.symbol, "qty": p.quantity,
                    "avg_entry": p.avg_cost, "current_price": p.market_price,
                    "unrealized_pnl": (p.market_price - p.avg_cost) * p.quantity,
                    "unrealized_pnl_pct": ((p.market_price / p.avg_cost) - 1) * 100 if p.avg_cost > 0 else 0,
                    "market_value": mv,
                })
            return {
                "department": "SPECULATIVE",
                "cash": portfolio.cash, "equity": portfolio.cash + total_exposure,
                "exposure": total_exposure, "positions": positions,
                "num_positions": len(positions),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}

    def open_position(
        self,
        ticker: str,
        thesis: str,
        notional: float = 2000.0,  # Smaller default for SPECULATIVE
        alpha_score: float = 0,
        pattern_tags: list = None,
        skip_intelligence: bool = False,
    ) -> dict:
        """
        Abre posición SPECULATIVE con evaluación rápida.
        """
        trade_id = f"BT-S-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{ticker}"

        # Entry Intelligence Pipeline (SpeculativeEntryHub)
        intel = None
        if not skip_intelligence and self.entry_hub:
            intel = self.entry_hub.evaluate(ticker)

            if intel.final_verdict == "BLOCK":
                logger.warning(f"⛔ SPEC {ticker} BLOCKED: {intel.final_reason}")
                return {"action": "BLOCKED", "reason": intel.final_reason, "intelligence": intel.to_dict()}

            if intel.final_verdict == "STALK":
                logger.info(f"⏳ SPEC {ticker} STALK: {intel.final_reason}")
                return {"action": "STALKING", "reason": intel.final_reason, "intelligence": intel.to_dict()}

            notional *= intel.final_scale
            logger.info(f"✅ SPEC {ticker} APPROVED: {intel.final_verdict}")

        # Risk Guardian check
        account = self.get_portfolio_status()
        if 'error' in account:
            return {"error": account['error']}

        risk_check = self.risk_guardian.evaluate(
            current_capital=account.get('equity', 100000),
            daily_pnl_pct=0,
            strategy_type="SPECULATIVE",
            quality_exposure=0,
            speculative_exposure=account.get('exposure', 0),
            current_vix=intel.vix if intel else 17,
        )

        if not risk_check['can_trade']:
            return {"action": "BLOCKED", "reason": f"Risk Guardian: {risk_check['alerts']}"}

        adjusted_notional = notional * risk_check['position_scale']

        # Smart Entry
        try:
            from backend.modules.execution.application.use_cases.smart_entry import SmartEntryEngine
            smart = SmartEntryEngine()
            snapshot = self._create_snapshot(ticker)
            analysis_price = snapshot.get('price', 0)
            atr = snapshot.get('atr', 1.0)

            current_price = analysis_price
            try:
                try:
                    current_price = asyncio.get_event_loop().run_until_complete(self.broker.get_price(ticker))
                except RuntimeError:
                    current_price = asyncio.run(self.broker.get_price(ticker))
            except Exception:
                pass

            vix = snapshot.get('vix', 17)
            if vix > 25:
                smart = SmartEntryEngine(rules=smart.adaptive_rules(vix=vix))

            check = smart.validate_entry(ticker=ticker, analysis_price=analysis_price, current_price=current_price, atr=atr)

            if not check.is_valid:
                return {"action": "REJECTED", "reason": check.rejection_reason}

            order = smart.submit_alpaca_limit_order(client=None, check=check, notional=adjusted_notional)

            # SPECULATIVE: Gamma-anchored stop preferred, else ATR-based
            stop = intel.stop_price if (intel and intel.stop_price > 0) else check.recommended_stop

            tags = pattern_tags or []
            tags.append("bucket_speculative")

            entry = TradeJournalEntry(
                trade_id=trade_id, ticker=ticker, direction="LONG",
                entry_thesis=f"[SPECULATIVE] {thesis}",
                alpha_score=alpha_score,
                entry_snapshot=snapshot, entry_price=check.recommended_limit,
                entry_time=datetime.now(UTC).isoformat(),
                entry_notional=adjusted_notional, strategy_bucket="SPECULATIVE",
                initial_stop_price=stop, current_stop_price=stop,
                highest_price=current_price, pattern_tags=tags,
                entry_intelligence=intel.to_dict() if intel else None,
                entry_order_id=str(order.id), status="OPEN",
            )
            self.journal.open_trade(entry)

            return {
                "action": "BUY", "trade_id": trade_id, "ticker": ticker,
                "order_type": "LIMIT", "limit_price": check.recommended_limit,
                "notional": adjusted_notional, "order_id": str(order.id),
                "initial_stop": stop,
                "gamma_regime": intel.gamma_regime if intel else "UNKNOWN",
                "flow_persistence": intel.flow_persistence_grade if intel else "UNKNOWN",
            }
        except Exception as e:
            logger.error(f"SPECULATIVE order error {ticker}: {e}")
            return {"error": str(e)}

    def run_surveillance(self) -> list[dict]:
        """Ejecuta la vigilancia Seykota sobre posiciones SPECULATIVE."""
        if self.surveillance:
            return self.surveillance.run_surveillance()
        return []

    def check_positions(self) -> list[dict]:
        """Evalúa exits mecánicos para todas las posiciones SPECULATIVE."""
        account = self.get_portfolio_status()
        if 'error' in account:
            return [{'error': account['error']}]

        evaluations = []
        for pos in account.get('positions', []):
            ticker = pos['ticker']
            snapshot = self._create_snapshot(ticker)
            trade_data = self.journal.get_trade_full_data(pos.get('trade_id', ''))

            trade_state = TradeState(
                ticker=ticker,
                entry_price=pos.get('avg_entry', pos['current_price']),
                highest_price=trade_data.get('highest_price', pos['current_price']) if trade_data else pos['current_price'],
                current_stop=trade_data.get('current_stop_price', 0.0) if trade_data else 0.0,
                bars_held=int(trade_data.get('bars_held', 0)) if trade_data else 0,
                entry_rs=trade_data.get('rs_vs_spy', 1.0) if trade_data else 1.0,
            )

            intel = trade_data.get('entry_intelligence', {}) if trade_data else {}
            market_context = MarketContext(
                current_price=pos['current_price'],
                current_atr=snapshot.get('atr', 1.0),
                ma20=pos['current_price'],
                rs_vs_spy=snapshot.get('rs_vs_spy_20d', 1.0),
                wyckoff_state="UNKNOWN",
                put_wall=0.0,
                vix_current=snapshot.get('vix', 17.0),
                flow_persistence_grade=intel.get('flow_persistence_grade', 'UNKNOWN'),
                gex_regime=intel.get('gamma_regime', 'UNKNOWN'),
            )

            decision = self.exit_engine.evaluate_exit(trade_state, market_context)

            evaluations.append({
                "ticker": ticker, "strategy": "SPECULATIVE",
                "current_price": pos['current_price'],
                "unrealized_pnl_pct": pos.get('unrealized_pnl_pct', 0.0),
                "trailing_stop": decision.new_stop_price,
                "exit_signal": {"should_exit": decision.should_exit, "reason": decision.reason, "urgency": decision.urgency},
            })

        return evaluations

    def _create_snapshot(self, ticker: str) -> dict:
        """Snapshot rápido del mercado."""
        try:
            data = self.market_data.fetch_prices(ticker)
            if data is None or data.empty:
                return {"error": "No price data"}
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            import pandas as pd
            close = float(data['Close'].iloc[-1])
            atr = float((data['High'] - data['Low']).rolling(14).mean().iloc[-1])
            vix = self.market_data.fetch_vix()
            return {"timestamp": datetime.now(UTC).isoformat(), "price": close, "atr": round(atr, 2), "vix": round(vix, 1)}
        except Exception as e:
            return {"timestamp": datetime.now(UTC).isoformat(), "error": str(e)}
