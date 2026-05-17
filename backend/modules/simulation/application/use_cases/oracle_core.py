"""
Oracle Core Backtest — Quality Core Specialist
================================================
Evaluates signal reliability EXCLUSIVELY for Quality Core department:
  - Hohn/Munger MOAT universe (large-cap tollkeepers)
  - QUALITY_THESIS geometry: no mechanical stop, long horizon
  - Core-specific signals: RSI zone, Kalman Wyckoff, Pattern, Flow
  - Produces SignalPassport with drawdown_recovery and thesis_survival metrics

Answers the Core department's question:
  "For this MOAT stock, does this signal add edge BEYOND just holding?"
  "When this signal fires, does the price recover within 120 bars?"

Key difference from OracleSwingBacktester:
  - loss_mult = 0.0 (no mechanical stop — thesis geometry)
  - The "loss" label in Triple Barrier = time exit (thesis didn't resolve)
  - Core metric = thesis_survival_rate (recovery within time limit)
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.modules.simulation.application.use_cases.oracle_backtest import (
    OracleBacktester,
    OracleResult,
)
from backend.modules.simulation.domain.entities.signal_passport import SignalPassport
from backend.modules.simulation.domain.entities.strategy_profile import (
    InvestmentCategory, ORACLE_GEOMETRY,
)
from backend.modules.simulation.domain.ports.barrier_labeler_port import BarrierLabelerPort
from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort
from backend.modules.simulation.domain.ports.ml_data_port import MLDataPort
from backend.modules.simulation.domain.ports.signal_port import SignalPort
from backend.modules.simulation.domain.ports.passport_store_port import PassportStorePort

logger = logging.getLogger(__name__)

DEPARTMENT = "QUALITY_CORE"

# Core signal set — defined here, not in create_all_signals()
def create_core_signals() -> list[SignalPort]:
    """Instantiate the Quality Core signal set.

    Includes primitives AND validated conjugations:
      - Kalman Wyckoff ACCUMULATION (primary confirmation)
      - RSI zone filter (hostile zones = don't enter)
      - Pattern recognition (bullish reversal confirmation)
      - RC + Kalman (WR 78.2→84.2% — validated conjugation)
      - RSI + Kalman (WR 75.7→93.5% — GOLDEN COMBO)
      - Flow persistence (CONTRA_FLOW detection)
    """
    from backend.modules.simulation.infrastructure.signal_adapters import (
        RSISignalAdapter,
        KalmanSignalAdapter,
        PatternSignalAdapter,
        FlowSignalAdapter,
    )
    from backend.modules.simulation.application.use_cases.oracle_swing import (
        RCKalmanComboAdapter,
        RSIKalmanComboAdapter,
    )
    return [
        KalmanSignalAdapter(),    # Wyckoff ACCUMULATION — primary confirmation
        RSISignalAdapter(),       # Zone filter (hostile zones = don't enter)
        PatternSignalAdapter(),   # Bullish reversal confirmation
        RCKalmanComboAdapter(),   # RC + Kalman ACCUMULATION (WR +6pts)
        RSIKalmanComboAdapter(),  # RSI + Kalman (WR 93.5% — GOLDEN COMBO)
        FlowSignalAdapter(),      # CONTRA_FLOW detection
    ]

# Vol regime labels → integer mapping (must match engineer_features encoding)
_REGIME_INT_MAP = {0: "NORMAL", 1: "COMPLACENT", 2: "ELEVATED", 3: "CRISIS"}


class OracleCoreBacktester(OracleBacktester):
    """
    Quality Core specialist Oracle.

    Inherits the Triple Barrier engine from OracleBacktester.
    Overrides geometry, signal set, and adds Core-specific passport generation.
    """

    # Minimum entries for statistical significance (lower for Quality — fewer trades)
    MIN_ENTRIES = 8

    def __init__(
        self,
        store: HistoricalDataPort,
        labeler: BarrierLabelerPort,
        passport_store: PassportStorePort,
        ml_store: MLDataPort | None = None,
    ):
        super().__init__(store, labeler, ml_store)
        self._passport = passport_store

    # ── Core geometry ──────────────────────────────────────────────

    @property
    def geometry(self):
        return ORACLE_GEOMETRY[InvestmentCategory.QUALITY_THESIS]

    # ── Main entrypoint ────────────────────────────────────────────

    def run_and_passport(
        self,
        ticker: str,
        tf: str = "1d",
        signals: list[SignalPort] | None = None,
        context: dict | None = None,
    ) -> list[SignalPassport]:
        """
        Evaluate all Core signals for a ticker and produce Passports.

        Args:
            ticker: Quality-universe ticker (pre-qualified by Core).
            tf: Timeframe (Core uses daily only).
            signals: Override signal set (default: create_core_signals()).
            context: Optional context passed to signal.generate().

        Returns:
            List of persisted SignalPassport objects (one per signal).
        """
        signals = signals or create_core_signals()
        passports = []

        # Load contextual data once (shared across signals)
        ohlc = self.store.load_bars(ticker, tf)
        if ohlc is None or ohlc.empty or len(ohlc) < 210:
            logger.warning(f"OracleCore: insufficient data for {ticker}/{tf}")
            return []

        vol_regime_series = self._extract_regime_series(ohlc)

        for signal in signals:
            try:
                result = self.run_signal(ticker, tf, signal, self.geometry, context)
                if result.n_entries < self.MIN_ENTRIES:
                    logger.info(
                        f"OracleCore: {signal.name} on {ticker} → "
                        f"only {result.n_entries} entries (min={self.MIN_ENTRIES}), skipping"
                    )
                    continue

                # Compute Core-specific breakdowns
                labels = self._get_labels_for(ohlc, signal, context)
                core_breakdowns = self._compute_core_breakdowns(
                    ohlc, labels, vol_regime_series
                )

                passport = self._build_passport(
                    ticker=ticker,
                    signal_name=signal.name,
                    result=result,
                    core_breakdowns=core_breakdowns,
                )

                self._passport.save_passport(passport)
                passports.append(passport)

                logger.info(
                    f"OracleCore: {ticker}/{signal.name} → "
                    f"grade={passport.grade} "
                    f"reliability={passport.reliability_score:.2f} "
                    f"survival={core_breakdowns['thesis_survival_rate']:.1f}%"
                )
            except Exception as e:
                logger.error(f"OracleCore: {ticker}/{signal.name} failed: {e}", exc_info=True)

        return passports

    def calibrate_universe(
        self,
        tickers: list[str],
        tf: str = "1d",
        signals: list[SignalPort] | None = None,
    ) -> dict[str, list[SignalPassport]]:
        """
        Run Core calibration across the entire Quality universe.

        Args:
            tickers: Quality-universe ticker list.
            tf: Timeframe (daily).
            signals: Signal set override.

        Returns:
            Dict {ticker: [passports]} for all successful calibrations.
        """
        results = {}
        total = len(tickers)
        for i, ticker in enumerate(tickers, 1):
            logger.info(f"OracleCore: calibrating {ticker} ({i}/{total})")
            try:
                passports = self.run_and_passport(ticker, tf, signals)
                if passports:
                    results[ticker] = passports
            except Exception as e:
                logger.error(f"OracleCore: {ticker} universe calibration failed: {e}")
        return results

    # ── Private helpers ────────────────────────────────────────────

    def _get_labels_for(
        self,
        ohlc: pd.DataFrame,
        signal: SignalPort,
        context: dict | None,
    ) -> list:
        """Re-run labeling for a signal (needed for breakdown computation)."""
        try:
            signal_df = signal.generate(ohlc, context)
            entries = signal_df["signal"] == 1
            geo = self.geometry
            labels = self.labeler.label_entries(
                ohlc, entries,
                profit_mult=geo.profit_mult,
                loss_mult=geo.loss_mult,
                max_bars=geo.max_bars,
                vol_lookback=geo.vol_lookback,
                entry_delay_bars=geo.entry_delay_bars,
                slippage_factor=geo.slippage_factor,
                round_trip_cost_bps=geo.round_trip_cost_bps,
            )
            return labels or []
        except Exception:
            return []

    def _extract_regime_series(self, ohlc: pd.DataFrame) -> pd.Series:
        """Extract vol regime integer series from ohlc features (if available)."""
        try:
            from backend.modules.simulation.application.use_cases.engineer_features import (
                QuantFeatureEngineer,
            )
            eng = QuantFeatureEngineer(ohlc, timeframe_minutes=1440)
            eng.extract_regime_features()
            col = "RG_VolRegime_Quality"
            if col in eng.df.columns:
                return eng.df[col].fillna(0).astype(int)
        except Exception:
            pass
        return pd.Series(0, index=ohlc.index)

    def _compute_core_breakdowns(
        self,
        ohlc: pd.DataFrame,
        labels: list,
        vol_regime_series: pd.Series,
    ) -> dict:
        """Compute Core-specific breakdowns: regime, recovery, survival."""
        if not labels:
            return {
                "wr_by_vol_regime": {},
                "sharpe_by_vol_regime": {},
                "n_by_vol_regime": {},
                "drawdown_recovery_avg_bars": 0.0,
                "thesis_survival_rate": 0.0,
            }

        # ── Vol regime breakdown ──
        regime_buckets: dict[str, list[float]] = {
            "NORMAL": [], "COMPLACENT": [], "ELEVATED": [], "CRISIS": []
        }
        for lbl in labels:
            if lbl.entry_time is None:
                continue
            try:
                pos = ohlc.index.get_loc(lbl.entry_time)
                regime_int = int(vol_regime_series.iloc[pos]) if pos < len(vol_regime_series) else 0
                regime_label = _REGIME_INT_MAP.get(regime_int, "NORMAL")
                regime_buckets[regime_label].append(lbl.return_pct)
            except Exception:
                pass

        wr_by_regime, sharpe_by_regime, n_by_regime = {}, {}, {}
        for reg, rets in regime_buckets.items():
            if rets:
                n_by_regime[reg] = len(rets)
                wr_by_regime[reg] = round(
                    sum(1 for r in rets if r > 0) / len(rets) * 100, 1
                )
                if len(rets) > 1:
                    std = np.std(rets, ddof=1)
                    avg = np.mean(rets)
                    sharpe_by_regime[reg] = round(
                        (avg / max(std, 1e-6)) * np.sqrt(252), 2
                    ) if std > 0 else 0.0
                else:
                    sharpe_by_regime[reg] = 0.0

        # ── Thesis survival rate ──
        # In QUALITY_THESIS (loss_mult=0.0): time exit (label=0) = thesis NOT resolved.
        # Profit exit (label=1) = price recovered = thesis SURVIVED.
        total = len(labels)
        survived = sum(1 for l in labels if l.label == 1)
        thesis_survival = round(survived / total * 100, 1) if total > 0 else 0.0

        # ── Drawdown recovery bars ──
        # For entries that eventually profited, how many bars did they need?
        recovery_bars = [l.bars_held for l in labels if l.label == 1]
        avg_recovery = round(float(np.mean(recovery_bars)), 1) if recovery_bars else 0.0

        return {
            "wr_by_vol_regime": wr_by_regime,
            "sharpe_by_vol_regime": sharpe_by_regime,
            "n_by_vol_regime": n_by_regime,
            "drawdown_recovery_avg_bars": avg_recovery,
            "thesis_survival_rate": thesis_survival,
        }

    def _build_passport(
        self,
        ticker: str,
        signal_name: str,
        result: OracleResult,
        core_breakdowns: dict,
    ) -> SignalPassport:
        """Build SignalPassport from OracleResult + Core-specific breakdowns."""
        # Reliability score: weighted composite
        # - ceiling_sharpe normalized to 0-1 (cap at 2.0)
        # - floor_sharpe normalized (robustness)
        # - thesis_survival_rate normalized
        sharpe_norm = min(result.ceiling_sharpe / 2.0, 1.0) if result.ceiling_sharpe > 0 else 0.0
        robustness = min(result.floor_sharpe / max(result.ceiling_sharpe, 0.01), 1.0) if result.floor_sharpe > 0 else 0.0
        survival_norm = core_breakdowns["thesis_survival_rate"] / 100.0

        # Consistency: 1 - CoV of returns
        rets_std = (result.max_drawdown_pct / -result.n_entries) if result.n_entries > 0 else 0
        consistency = max(0.0, 1.0 - abs(rets_std / max(abs(result.avg_return_pct), 0.001)))
        consistency = min(consistency, 1.0)

        reliability = round(
            sharpe_norm * 0.35
            + robustness * 0.25
            + survival_norm * 0.25
            + consistency * 0.15,
            3,
        )

        viable = (
            result.ceiling_sharpe >= 0.3
            and result.n_entries >= self.MIN_ENTRIES
            and result.win_rate >= 30
        )
        grade = (
            "A" if result.ceiling_sharpe >= 1.5
            else "B" if result.ceiling_sharpe >= 1.0
            else "C" if result.ceiling_sharpe >= 0.5
            else "D"
        )

        return SignalPassport(
            ticker=ticker,
            department=DEPARTMENT,
            signal_name=signal_name,
            ceiling_sharpe=result.ceiling_sharpe,
            floor_sharpe=result.floor_sharpe,
            win_rate=result.win_rate,
            profit_factor=result.profit_factor,
            n_entries=result.n_entries,
            avg_return_pct=result.avg_return_pct,
            total_return_pct=result.total_return_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            avg_bars_held=result.avg_bars_held,
            avg_bars_to_loss=result.avg_bars_to_loss,
            pct_loss_hit=result.pct_loss_hit,
            pct_time_hit=result.pct_time_hit,
            reliability_score=reliability,
            consistency_score=round(consistency, 3),
            oos_sharpe=0.0,    # Walk-Forward not yet implemented for Core
            oos_win_rate=0.0,
            sharpe_by_vol_regime=core_breakdowns["sharpe_by_vol_regime"],
            wr_by_vol_regime=core_breakdowns["wr_by_vol_regime"],
            n_by_vol_regime=core_breakdowns["n_by_vol_regime"],
            drawdown_recovery_avg_bars=core_breakdowns["drawdown_recovery_avg_bars"],
            thesis_survival_rate=core_breakdowns["thesis_survival_rate"],
            viable=viable,
            grade=grade,
            geometry_used={
                "profit_mult": self.geometry.profit_mult,
                "loss_mult": self.geometry.loss_mult,
                "max_bars": self.geometry.max_bars,
            },
        )
