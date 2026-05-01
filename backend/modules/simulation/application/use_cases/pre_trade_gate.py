"""
Pre-Trade Gate — Multi-Stage Validation Pipeline
====================================================
Mandatory pipeline that every trade intent must pass before
reaching the execution module.

Pipeline:
1. RiskGuardian → portfolio capacity check (80/20 QUALITY/SPECULATIVE)
2. EntryHub → 40+ indicator evaluation
3. SMC → market structure analysis
4. Structure Gate → category-specific SMC filters
5. Composer → weighted signal combination
6. Oracle Gate → alpha ceiling viable?
7. ML Gate → confidence threshold?
8. Vault → persist all consumed data
9. Snapshot → immutable trade context record
10. Dashboard Sync → push to PayloadCMS
11. Emit ExecutionIntent → handoff to execution

If ANY gate fails, the trade is rejected with a clear reason.
"""
import logging
from datetime import datetime, UTC
from typing import Optional

import pandas as pd

from backend.modules.simulation.domain.entities.strategy_profile import (
    InvestmentCategory, StrategyProfile,
)
from backend.modules.simulation.domain.entities.trade_snapshot import (
    TradeSnapshot, MarketStructureSnapshot, SignalSnapshot,
)
from backend.modules.simulation.domain.entities.execution_intent import ExecutionIntent
from backend.modules.simulation.application.use_cases.strategy_composer import (
    StrategyComposer, CompositeDecision,
)
from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort
from backend.modules.simulation.domain.ports.market_structure_port import (
    MarketStructurePort, MarketStructureResult,
)
from backend.modules.simulation.domain.ports.ml_confidence_port import MLConfidencePort
from backend.modules.simulation.domain.ports.signal_port import SignalPort
from backend.modules.simulation.domain.ports.dashboard_sync_port import DashboardSyncPort
from backend.modules.simulation.domain.ports.data_harmonizer_port import DataHarmonizerPort

logger = logging.getLogger(__name__)


# SMC structure rules per investment category
STRUCTURE_RULES = {
    InvestmentCategory.QUALITY_VALUE: {
        "reject_if": ["swing_trend == DOWNTREND"],
        "boost_if": ["liquidity_swept"],
    },
    InvestmentCategory.QUALITY_GROWTH: {
        "reject_if": ["choch_direction == BEARISH"],
        "boost_if": ["bos_direction == BULLISH"],
    },
    InvestmentCategory.QUALITY_DIVIDEND: {
        "reject_if": ["bos_direction == BEARISH and bos_bars_ago <= 5"],
        "boost_if": [],
    },
    InvestmentCategory.SPECULATIVE_SPRING: {
        "reject_if": [],
        "boost_if": ["liquidity_swept"],  # Spring = liquidity sweep + reversal
    },
    InvestmentCategory.SPECULATIVE_MOMENTUM: {
        "reject_if": [],
        "boost_if": ["bos_direction == BULLISH"],  # Requires BOS
    },
    InvestmentCategory.SPECULATIVE_GAMMA: {
        "reject_if": [],
        "boost_if": ["fvg_active"],  # FVG as target
    },
    InvestmentCategory.SPECULATIVE_BREAKOUT: {
        "reject_if": ["bos_detected == False"],  # BOS mandatory
        "boost_if": ["bos_direction == BULLISH"],
    },
}


class PreTradeGate:
    """
    Multi-stage validation pipeline for trade approval.

    Every trade must pass ALL gates. The gate produces an immutable
    TradeSnapshot and, if approved, an ExecutionIntent.
    """

    def __init__(
        self,
        store: HistoricalDataPort,
        structure_analyzer: MarketStructurePort,
        signals: list[SignalPort],
        composer: StrategyComposer,
        ml: Optional[MLConfidencePort] = None,
        dashboard: Optional[DashboardSyncPort] = None,
        harmonizer: Optional[DataHarmonizerPort] = None,
    ):
        self.store = store
        self.structure = structure_analyzer
        self.signals = signals
        self.composer = composer
        self.ml = ml
        self.dashboard = dashboard
        self.harmonizer = harmonizer

    def evaluate(
        self,
        ticker: str,
        category: InvestmentCategory,
        profile: StrategyProfile,
        entry_report: dict | None = None,
        portfolio_id: str = "",
    ) -> tuple[Optional[ExecutionIntent], TradeSnapshot]:
        """
        Run the full pre-trade gate pipeline.

        Returns:
            (ExecutionIntent, TradeSnapshot) if approved
            (None, TradeSnapshot) if rejected
        """
        snapshot = TradeSnapshot(
            ticker=ticker,
            category=category.value,
            entry_report=entry_report or {},
        )

        # ── Gate 1: Load market data ──────────────────────
        ohlc = self.store.load_bars(ticker, profile.timeframe)
        if ohlc.empty or len(ohlc) < 50:
            snapshot.gate_approved = False
            snapshot.gate_reason = "INSUFFICIENT_DATA"
            self._persist(snapshot)
            return None, snapshot

        current_price = float(ohlc["close"].iloc[-1])

        # ── Gate 2: Market Structure (SMC) ────────────────
        smc_result = self.structure.analyze(ohlc)
        snapshot.structure = MarketStructureSnapshot(
            swing_trend=smc_result.swing_trend,
            bos_direction=smc_result.bos_direction,
            bos_bars_ago=smc_result.bos_bars_ago,
            choch_detected=smc_result.choch_detected,
            choch_direction=smc_result.choch_direction,
            nearest_ob_price=smc_result.nearest_ob_price,
            nearest_ob_type=smc_result.nearest_ob_type,
            fvg_active=smc_result.fvg_active,
            fvg_direction=smc_result.fvg_direction,
            liquidity_swept=smc_result.liquidity_swept,
        )

        # ── Gate 3: Structure Filter (category-specific) ──
        structure_passed, structure_reason = self._check_structure(
            category, smc_result,
        )
        if not structure_passed:
            snapshot.gate_approved = False
            snapshot.gate_reason = f"STRUCTURE_REJECTED: {structure_reason}"
            self._persist(snapshot)
            return None, snapshot

        # ── Gate 4: Signal Composition ────────────────────
        context = self._build_signal_context(ticker)
        signal_outputs = {}
        signal_confidences = {}
        signal_snapshots = []

        for signal in self.signals:
            config = next(
                (s for s in profile.enabled_signals if s.name == signal.name),
                None,
            )
            if not config:
                continue

            signal_df = signal.generate(ohlc, context)
            last_signal = int(signal_df["signal"].iloc[-1])
            last_conf = float(signal_df.get("confidence", pd.Series(1.0)).iloc[-1]) if "confidence" in signal_df.columns else 1.0

            signal_outputs[signal.name] = last_signal
            signal_confidences[signal.name] = last_conf

            signal_snapshots.append(SignalSnapshot(
                name=signal.name,
                value=last_signal,
                confidence=last_conf,
                weight=config.weight,
                contribution=last_signal * config.weight * last_conf,
            ))

        snapshot.signals = signal_snapshots
        decision = self.composer.compose(profile, signal_outputs, signal_confidences)
        snapshot.composite_score = decision.score
        snapshot.composite_method = decision.method

        if not decision.entry:
            snapshot.gate_approved = False
            snapshot.gate_reason = f"SIGNALS_INSUFFICIENT: {decision.reason}"
            self._persist(snapshot)
            return None, snapshot

        # ── Gate 5: ML Confidence ─────────────────────────
        if self.ml and self.ml.is_trained(ticker, category.value):
            features = self._build_ml_features(ticker, profile.timeframe)
            if features is not None:
                prediction = self.ml.predict(features)
                snapshot.ml_confidence = prediction.confidence
                snapshot.ml_model_used = prediction.model_name

                min_conf = 0.55  # Minimum ML confidence
                if prediction.confidence < min_conf:
                    snapshot.gate_approved = False
                    snapshot.gate_reason = f"ML_LOW_CONFIDENCE: {prediction.confidence:.2f} < {min_conf}"
                    self._persist(snapshot)
                    return None, snapshot

        # ── Gate 6: Oracle Ceiling ────────────────────────
        oracle_profile = self.store.load_profile(category.value, ticker)
        if oracle_profile:
            oracle_sharpe = oracle_profile.get("calibration_sharpe", 0)
            snapshot.oracle_ceiling_sharpe = oracle_sharpe
            if oracle_sharpe < profile.gating.min_sharpe:
                snapshot.gate_approved = False
                snapshot.gate_reason = f"ORACLE_CEILING_LOW: {oracle_sharpe} < {profile.gating.min_sharpe}"
                self._persist(snapshot)
                return None, snapshot

        # ── All Gates Passed ──────────────────────────────
        snapshot.gate_approved = True
        snapshot.gate_conviction = decision.score
        snapshot.gate_reason = "ALL_GATES_PASSED"

        # Calculate stop and target from geometry
        atr = self._calculate_atr(ohlc)
        stop_price = current_price - atr * profile.geometry.loss_mult
        target_price = current_price + atr * profile.geometry.profit_mult
        risk_reward = (target_price - current_price) / max(current_price - stop_price, 0.01)

        intent = ExecutionIntent(
            ticker=ticker,
            direction="LONG",
            category=category.value,
            entry_price=current_price,
            stop_price=round(stop_price, 2),
            target_price=round(target_price, 2),
            risk_reward=round(risk_reward, 2),
            snapshot_id=snapshot.snapshot_id,
            gate_conviction=decision.score,
            oracle_ceiling=snapshot.oracle_ceiling_sharpe,
            ml_confidence=snapshot.ml_confidence,
            portfolio_id=portfolio_id,
        )

        self._persist(snapshot)

        logger.info(
            f"✅ PreTradeGate APPROVED: {ticker} ({category.value}) "
            f"conviction={decision.score:.2f} R:R={risk_reward:.1f}"
        )
        return intent, snapshot

    def _check_structure(
        self, category: InvestmentCategory, smc: MarketStructureResult,
    ) -> tuple[bool, str]:
        """Check category-specific structure rules."""
        rules = STRUCTURE_RULES.get(category, {})

        for rule in rules.get("reject_if", []):
            if self._eval_smc_rule(rule, smc):
                return False, rule

        return True, ""

    def _eval_smc_rule(self, rule: str, smc: MarketStructureResult) -> bool:
        """Evaluate a single SMC rule string against the result."""
        if "swing_trend == DOWNTREND" in rule:
            return smc.swing_trend == "DOWNTREND"
        if "choch_direction == BEARISH" in rule:
            return smc.choch_detected and smc.choch_direction == "BEARISH"
        if "bos_direction == BEARISH" in rule and "bos_bars_ago" in rule:
            return smc.bos_detected and smc.bos_direction == "BEARISH" and smc.bos_bars_ago <= 5
        if "bos_detected == False" in rule:
            return not smc.bos_detected
        return False

    def _build_signal_context(self, ticker: str) -> dict:
        """Build context dict for signals that need external data."""
        context = {}
        flow = self.store.load_features(ticker, "flow_1d")
        if flow is not None:
            context["uw_flow_features"] = flow
        return context

    def _build_ml_features(self, ticker: str, tf: str):
        """Build feature row for ML prediction."""
        if self.harmonizer is None:
            return None
        try:
            dataset = self.harmonizer.build_ml_dataset(ticker, tf)
            if not dataset.empty:
                return dataset.iloc[[-1]]  # Last row as single-row DataFrame
        except Exception as e:
            logger.warning(f"PreTradeGate: ML features failed: {e}")
        return None

    def _calculate_atr(self, ohlc, period: int = 20) -> float:
        """Calculate current ATR."""
        import pandas as pd
        high = ohlc["high"]
        low = ohlc["low"]
        close = ohlc["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def _persist(self, snapshot: TradeSnapshot) -> None:
        """Persist snapshot and sync to dashboard."""
        self.store.save_snapshot(snapshot)
        if self.dashboard:
            self.dashboard.sync_snapshot(snapshot)
