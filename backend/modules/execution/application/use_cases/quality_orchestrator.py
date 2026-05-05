"""
QUALITY ORCHESTRATOR — Druckenmiller Daemon
=============================================
Orquestador de ejecución para el departamento QUALITY.

Cadencia: DIARIA (un escaneo por día de mercado)
Pipeline: QualityResearchPipeline → QualityEntryGate → SurveillanceLoop
Exit: QualityExitEngine (thesis death, moat decay)
Journal: QUALITY journal exclusivo
Broker: QUALITY broker exclusivo

NO USA: cadencia intradiaria, Memory Guard, time stops.
"""
import logging
import asyncio
from datetime import datetime, UTC

from backend.modules.execution.domain.ports.broker_port import BrokerPort
from backend.modules.execution.domain.ports.trade_journal_port import TradeJournalPort
from backend.modules.entry_decision.domain.ports.market_data_port import EntryMarketDataPort
from backend.modules.execution.domain.entities.trade_record import TradeJournalEntry
from backend.modules.portfolio_management.domain.rules.risk_guardian import RiskGuardian
from backend.modules.execution.domain.rules.exit_rules import QualityExitEngine
from backend.modules.execution.domain.entities.exit_context import TradeState, MarketContext

logger = logging.getLogger(__name__)


class QualityOrchestrator:
    """
    Daemon de ejecución QUALITY.

    Druckenmiller: "The way to build long-term returns is through
    preservation of capital and home runs."

    Cadencia diaria. Posiciones de semanas a meses.
    """

    def __init__(
        self,
        broker: BrokerPort,
        journal: TradeJournalPort,
        market_data: EntryMarketDataPort,
        entry_gate=None,
        surveillance=None,
    ):
        self.broker = broker
        self.journal = journal
        self.market_data = market_data
        self.entry_gate = entry_gate  # QualityEntryGate
        self.surveillance = surveillance  # SurveillanceLoop
        self.exit_engine = QualityExitEngine()
        self.risk_guardian = RiskGuardian()

    def get_portfolio_status(self) -> dict:
        """Estado actual de la cartera QUALITY."""
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
                "department": "QUALITY",
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
        notional: float = 5000.0,
        alpha_score: float = 0,
        qualifier_grade: str = "",
        skip_intelligence: bool = False,
    ) -> dict:
        """
        Abre posición QUALITY con evaluación profunda.
        """
        trade_id = f"BT-Q-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{ticker}"

        # Entry Intelligence Pipeline (QualityEntryGate)
        intel = None
        if not skip_intelligence and self.entry_gate:
            intel = self.entry_gate.evaluate(ticker)

            if intel.final_verdict == "BLOCK":
                logger.warning(f"⛔ QUALITY {ticker} BLOCKED: {intel.final_reason}")
                return {"action": "BLOCKED", "reason": intel.final_reason, "intelligence": intel.to_dict()}

            if intel.final_verdict == "STALK":
                logger.info(f"⏳ QUALITY {ticker} STALK: {intel.final_reason}")
                return {"action": "STALKING", "reason": intel.final_reason, "intelligence": intel.to_dict()}

            notional *= intel.final_scale
            logger.info(f"✅ QUALITY {ticker} APPROVED: {intel.final_verdict}")

        # Risk Guardian check
        account = self.get_portfolio_status()
        if 'error' in account:
            return {"error": account['error']}

        risk_check = self.risk_guardian.evaluate(
            current_capital=account.get('equity', 100000),
            daily_pnl_pct=0,
            strategy_type="QUALITY",
            quality_exposure=account.get('exposure', 0),
            speculative_exposure=0,
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

            stop = intel.stop_price if (intel and intel.stop_price > 0) else check.recommended_stop

            entry = TradeJournalEntry(
                trade_id=trade_id, ticker=ticker, direction="LONG",
                entry_thesis=f"[QUALITY] {thesis}", alpha_score=alpha_score,
                qualifier_grade=qualifier_grade,
                entry_snapshot=snapshot, entry_price=check.recommended_limit,
                entry_time=datetime.now(UTC).isoformat(),
                entry_notional=adjusted_notional, strategy_bucket="QUALITY",
                initial_stop_price=stop, current_stop_price=stop,
                highest_price=current_price,
                entry_intelligence=intel.to_dict() if intel else None,
                entry_order_id=str(order.id), status="OPEN",
            )
            self.journal.open_trade(entry)

            return {
                "action": "BUY", "trade_id": trade_id, "ticker": ticker,
                "order_type": "LIMIT", "limit_price": check.recommended_limit,
                "notional": adjusted_notional, "order_id": str(order.id),
                "initial_stop": stop,
            }
        except Exception as e:
            logger.error(f"QUALITY order error {ticker}: {e}")
            return {"error": str(e)}

    def run_surveillance(self) -> list[dict]:
        """Ejecuta la vigilancia Druckenmiller sobre posiciones QUALITY."""
        if self.surveillance:
            return self.surveillance.run_surveillance()
        return []

    def check_positions(self) -> list[dict]:
        """Evalúa exits para todas las posiciones QUALITY."""
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

            market_context = MarketContext(
                current_price=pos['current_price'],
                current_atr=snapshot.get('atr', 1.0),
                ma20=pos['current_price'],  # Approximation
                rs_vs_spy=snapshot.get('rs_vs_spy_20d', 1.0),
                wyckoff_state="UNKNOWN",
                put_wall=0.0,
                vix_current=snapshot.get('vix', 17.0),
                thesis_death_flag=trade_data.get('thesis_death_flag', False) if trade_data else False,
            )

            decision = self.exit_engine.evaluate_exit(trade_state, market_context)

            evaluations.append({
                "ticker": ticker, "strategy": "QUALITY",
                "current_price": pos['current_price'],
                "unrealized_pnl_pct": pos.get('unrealized_pnl_pct', 0.0),
                "trailing_stop": decision.new_stop_price,
                "exit_signal": {"should_exit": decision.should_exit, "reason": decision.reason, "urgency": decision.urgency},
            })

        return evaluations

    def _create_snapshot(self, ticker: str) -> dict:
        """Snapshot rápido del mercado para journal."""
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
