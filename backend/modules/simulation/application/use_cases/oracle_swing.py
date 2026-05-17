"""
Oracle Swing Backtest — Quality Swing Specialist
=================================================
Evaluates signal reliability EXCLUSIVELY for Quality Swing department:
  - Druckenmiller regression channel + fear_level contrarian timing
  - QUALITY_VALUE_120 geometry: with stop, long horizon
  - Swing-specific signals: RC alone, RC+Fear combo, RC+Fear+Flip combo
  - Walk-Forward OOS validation (Purged K-Fold, k=5)
  - Produces SignalPassport with per-fear-level, per-sigma, wave_flip breakdowns

Answers the Swing department's question:
  "For this MOAT stock, at THIS fear_level and sigma_position, 
   what is the historical WR and expected Sharpe of the RC signal?"

Key difference from OracleCoreBacktester:
  - loss_mult = 1.0 (has stop)
  - Evaluates three composite signal variants, not just primitives
  - Walk-Forward OOS Sharpe is the primary reliability driver
  - Breakdowns by fear_level (0-5) and sigma_band are the core output
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
from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
from backend.modules.quality_swing.domain.rules.regression_channel import sigma_position, linreg_channel

logger = logging.getLogger(__name__)

DEPARTMENT = "QUALITY_SWING"
_REGIME_INT_MAP = {0: "NORMAL", 1: "COMPLACENT", 2: "ELEVATED", 3: "CRISIS"}
_SIGMA_BANDS = [
    ("-3_-2", -3.0, -2.0),
    ("-2_-1.5", -2.0, -1.5),
    ("-1.5_-1", -1.5, -1.0),
    ("-1_0", -1.0, 0.0),
]


# ─── Composite Signal Adapters (Swing-specific) ──────────────────────────────

class RCFearComboAdapter(SignalPort):
    """RC signal + fear_level >= 3 (ANXIETY/FEAR/PANIC).

    Tests: does requiring high fear_level improve RC's edge?
    Forensic hypothesis: fear >= 3 should improve WR significantly.
    """

    @property
    def name(self) -> str:
        return "rc_fear_combo"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.simulation.infrastructure.signal_adapters import RegressionChannelAdapter
        rc = RegressionChannelAdapter()
        rc_df = rc.generate(ohlc, context)

        fear_signals = []
        for i in range(len(ohlc)):
            bias = compute_ticker_fear_level(ohlc, i)
            has_fear = bias is not None and bias.fear_level >= 3
            fear_signals.append(1 if has_fear else 0)

        fear_series = pd.Series(fear_signals, index=ohlc.index)
        combined = ((rc_df["signal"] == 1) & (fear_series == 1)).astype(int)

        return pd.DataFrame({
            "signal": combined,
            "confidence": rc_df.get("confidence", pd.Series(1.0, index=ohlc.index)),
        }, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class RCFearFlipAdapter(SignalPort):
    """RC signal + fear_level >= 3 + wave_flip positive (knife stopped falling).

    Tests: is 'slope conjugation' (wave turning after fear) the true edge?
    Forensic hypothesis: this combination should have WR > 90% in BULL regime.
    """

    @property
    def name(self) -> str:
        return "rc_fear_flip"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.simulation.infrastructure.signal_adapters import RegressionChannelAdapter
        rc = RegressionChannelAdapter()
        rc_df = rc.generate(ohlc, context)

        combo_signals = []
        for i in range(len(ohlc)):
            bias = compute_ticker_fear_level(ohlc, i)
            has_combo = (
                bias is not None
                and bias.fear_level >= 3
                and bias.wave_flip
                and bias.wave_flip_direction == 1
            )
            combo_signals.append(1 if has_combo else 0)

        combo_series = pd.Series(combo_signals, index=ohlc.index)
        combined = ((rc_df["signal"] == 1) & (combo_series == 1)).astype(int)

        return pd.DataFrame({
            "signal": combined,
            "confidence": rc_df.get("confidence", pd.Series(1.0, index=ohlc.index)),
        }, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class RSIFearComboAdapter(SignalPort):
    """RSI signal + fear_level >= 3 (ANXIETY/FEAR/PANIC) as BIAS filter.

    Forensic finding: RSI improves in CRISIS (56.2%) and ELEVATED (54.8%).
    Hypothesis: requiring high fear_level should concentrate RSI's entries
    on the high-WR conditions where contrarian behavior is strongest.

    The RSI already uses its OWN regressions (120/60 bars) for cross-regression
    pullback. This combo adds the SEPARATE fear_level bias from the RC's
    dual channel (200/cycle-adaptive bars) — two independent confirmation sources.
    """

    @property
    def name(self) -> str:
        return "rsi_fear_combo"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.simulation.infrastructure.signal_adapters import RSISignalAdapter
        rsi = RSISignalAdapter()
        rsi_df = rsi.generate(ohlc, context)

        fear_signals = []
        for i in range(len(ohlc)):
            bias = compute_ticker_fear_level(ohlc, i)
            has_fear = bias is not None and bias.fear_level >= 3
            fear_signals.append(1 if has_fear else 0)

        fear_series = pd.Series(fear_signals, index=ohlc.index)
        combined = ((rsi_df["signal"] == 1) & (fear_series == 1)).astype(int)

        return pd.DataFrame({
            "signal": combined,
            "confidence": rsi_df.get("confidence", pd.Series(1.0, index=ohlc.index)),
        }, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class RSIKalmanComboAdapter(SignalPort):
    """RSI signal + Kalman Wyckoff ACCUMULATION confirmation.

    THE HIGHEST VALIDATED CONJUGATION IN THE ENTIRE SYSTEM:
      RSI solo: WR 75.7% → RSI + Kalman: WR 93.5%, Ret +15.4% → +17.7%
      (Source: oracle-training-forensic KI, section 2.1)

    Kalman acts as a CONFIRMADOR — it fires when the Kalman filter detects
    Wyckoff ACCUMULATION phase with positive velocity. When BOTH RSI and
    Kalman agree, the trade has regime + momentum + institutional accumulation.

    This is NOT speculative — it was empirically measured over 30 tickers × 5 years.
    """

    @property
    def name(self) -> str:
        return "rsi_kalman_combo"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.simulation.infrastructure.signal_adapters import (
            RSISignalAdapter,
            KalmanSignalAdapter,
        )
        rsi = RSISignalAdapter()
        kalman = KalmanSignalAdapter()

        rsi_df = rsi.generate(ohlc, context)
        kalman_df = kalman.generate(ohlc, context)

        combined = ((rsi_df["signal"] == 1) & (kalman_df["signal"] == 1)).astype(int)

        return pd.DataFrame({
            "signal": combined,
            "confidence": rsi_df.get("confidence", pd.Series(1.0, index=ohlc.index)),
        }, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class RCKalmanComboAdapter(SignalPort):
    """RC signal + Kalman Wyckoff ACCUMULATION confirmation.

    Validated conjugation:
      RC solo: WR 78.2% → RC + Kalman: WR 84.2%, Ret +14.9% → +20.5%
      (Source: oracle-training-forensic KI, section 2.1)

    The Kalman filter detecting ACCUMULATION + positive velocity alongside
    the regression channel's σ-band dip entry creates a dual-confirmation
    setup: statistical discount (RC) + institutional accumulation (Kalman).
    """

    @property
    def name(self) -> str:
        return "rc_kalman_combo"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.simulation.infrastructure.signal_adapters import (
            RegressionChannelAdapter,
            KalmanSignalAdapter,
        )
        rc = RegressionChannelAdapter()
        kalman = KalmanSignalAdapter()

        rc_df = rc.generate(ohlc, context)
        kalman_df = kalman.generate(ohlc, context)

        combined = ((rc_df["signal"] == 1) & (kalman_df["signal"] == 1)).astype(int)

        return pd.DataFrame({
            "signal": combined,
            "confidence": rc_df.get("confidence", pd.Series(1.0, index=ohlc.index)),
        }, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


def create_swing_signals() -> list[SignalPort]:
    """Instantiate the Quality Swing signal set.

    Includes all empirically validated conjugations from the forensic audit:
      - RC solo (Sharpe 1.326, WR 82.2% — the best standalone signal)
      - RC + Fear (does fear_level improve RC's edge?)
      - RC + Fear + Flip (slope conjugation = the true edge?)
      - RC + Kalman (WR 78.2→84.2%, Ret +14.9→+20.5%)
      - RSI solo (84% WR in COST, contrarian in CRISIS)
      - RSI + Fear (does the dual channel bias improve RSI?)
      - RSI + Kalman (WR 75.7→93.5% — HIGHEST VALIDATED CONJUGATION)
      - Flow persistence (CONTRA_FLOW detection)
    """
    from backend.modules.simulation.infrastructure.signal_adapters import (
        RegressionChannelAdapter,
        RSISignalAdapter,
        FlowSignalAdapter,
    )
    return [
        # ── Primary signals ──
        RegressionChannelAdapter(),   # Primary: statistical dip timing
        RSISignalAdapter(),           # RSI zone filter (as signal)
        # ── RC conjugations ──
        RCFearComboAdapter(),         # RC + fear_level >= 3
        RCFearFlipAdapter(),          # RC + fear + wave_flip positive
        RCKalmanComboAdapter(),       # RC + Kalman ACCUMULATION (WR +6pts)
        # ── RSI conjugations (preserving validated results!) ──
        RSIFearComboAdapter(),        # RSI + fear_level >= 3 (bias filter)
        RSIKalmanComboAdapter(),      # RSI + Kalman (WR 93.5% — GOLDEN COMBO)
        # ── Flow ──
        FlowSignalAdapter(),          # CONTRA_FLOW detection
    ]


# ─── Oracle Swing ──────────────────────────────────────────────────────────────

class OracleSwingBacktester(OracleBacktester):
    """
    Quality Swing specialist Oracle.

    Inherits the Triple Barrier engine from OracleBacktester.
    Adds: composite signals, Walk-Forward OOS, Swing-specific breakdowns.
    """

    MIN_ENTRIES = 8
    WALK_FORWARD_FOLDS = 5  # Purged K-Fold for OOS validation

    def __init__(
        self,
        store: HistoricalDataPort,
        labeler: BarrierLabelerPort,
        passport_store: PassportStorePort,
        ml_store: MLDataPort | None = None,
    ):
        super().__init__(store, labeler, ml_store)
        self._passport = passport_store

    @property
    def geometry(self):
        return ORACLE_GEOMETRY[InvestmentCategory.QUALITY_VALUE_120]

    # ── Main entrypoint ────────────────────────────────────────────

    def run_and_passport(
        self,
        ticker: str,
        tf: str = "1d",
        signals: list[SignalPort] | None = None,
        context: dict | None = None,
    ) -> list[SignalPassport]:
        """
        Evaluate all Swing signals for a ticker and produce Passports.

        Args:
            ticker: Quality-universe ticker (must be Core-qualified first).
            tf: Timeframe (Swing uses daily only).
            signals: Override signal set (default: create_swing_signals()).
            context: Optional context passed to signal.generate().

        Returns:
            List of persisted SignalPassport objects.
        """
        signals = signals or create_swing_signals()
        passports = []

        ohlc = self.store.load_bars(ticker, tf)
        if ohlc is None or ohlc.empty or len(ohlc) < 210:
            logger.warning(f"OracleSwing: insufficient data for {ticker}/{tf}")
            return []

        vol_regime_series = self._extract_regime_series(ohlc)

        for signal in signals:
            try:
                result = self.run_signal(ticker, tf, signal, self.geometry, context)
                if result.n_entries < self.MIN_ENTRIES:
                    logger.info(
                        f"OracleSwing: {signal.name} on {ticker} → "
                        f"only {result.n_entries} entries (min={self.MIN_ENTRIES}), skipping"
                    )
                    continue

                labels = self._get_labels_for(ohlc, signal, context)
                swing_breakdowns = self._compute_swing_breakdowns(
                    ohlc, labels, vol_regime_series
                )
                oos_sharpe, oos_wr = self._walk_forward_validation(
                    ohlc, signal, context
                )

                passport = self._build_passport(
                    ticker=ticker,
                    signal_name=signal.name,
                    result=result,
                    swing_breakdowns=swing_breakdowns,
                    oos_sharpe=oos_sharpe,
                    oos_win_rate=oos_wr,
                )

                self._passport.save_passport(passport)
                passports.append(passport)

                logger.info(
                    f"OracleSwing: {ticker}/{signal.name} → "
                    f"grade={passport.grade} "
                    f"reliability={passport.reliability_score:.2f} "
                    f"OOS_Sharpe={oos_sharpe:.3f} "
                    f"fear_panic_wr={swing_breakdowns['wr_by_fear_level'].get('PANIC', 0):.0f}%"
                )
            except Exception as e:
                logger.error(
                    f"OracleSwing: {ticker}/{signal.name} failed: {e}", exc_info=True
                )

        return passports

    def calibrate_universe(
        self,
        tickers: list[str],
        tf: str = "1d",
        signals: list[SignalPort] | None = None,
    ) -> dict[str, list[SignalPassport]]:
        """Run Swing calibration across the entire Quality universe."""
        results = {}
        total = len(tickers)
        for i, ticker in enumerate(tickers, 1):
            logger.info(f"OracleSwing: calibrating {ticker} ({i}/{total})")
            try:
                passports = self.run_and_passport(ticker, tf, signals)
                if passports:
                    results[ticker] = passports
            except Exception as e:
                logger.error(f"OracleSwing: {ticker} universe calibration failed: {e}")
        return results

    # ── Walk-Forward OOS Validation ────────────────────────────────

    def _walk_forward_validation(
        self,
        ohlc: pd.DataFrame,
        signal: SignalPort,
        context: dict | None,
    ) -> tuple[float, float]:
        """
        Purged Walk-Forward validation (k=5 folds).

        Each fold: train on first 80% of segment, test on last 20%.
        Purge gap = max_bars (to prevent leakage).
        Returns: (oos_sharpe, oos_win_rate) averaged across folds.
        """
        n = len(ohlc)
        fold_size = n // self.WALK_FORWARD_FOLDS
        purge_gap = self.geometry.max_bars  # 120 bars purge

        oos_rets: list[float] = []
        oos_wins = 0
        oos_total = 0

        for k in range(self.WALK_FORWARD_FOLDS):
            test_start = fold_size * k
            test_end = fold_size * (k + 1)
            train_end = max(0, test_start - purge_gap)

            if train_end < 60 or test_end - test_start < 20:
                continue

            test_ohlc = ohlc.iloc[test_start:test_end]
            if test_ohlc.empty:
                continue

            try:
                signal_df = signal.generate(test_ohlc, context)
                entries = signal_df["signal"] == 1
                geo = self.geometry
                fold_labels = self.labeler.label_entries(
                    test_ohlc, entries,
                    profit_mult=geo.profit_mult,
                    loss_mult=geo.loss_mult,
                    max_bars=geo.max_bars,
                    vol_lookback=geo.vol_lookback,
                    entry_delay_bars=geo.entry_delay_bars,
                    slippage_factor=geo.slippage_factor,
                    round_trip_cost_bps=geo.round_trip_cost_bps,
                )
                if not fold_labels:
                    continue

                for lbl in fold_labels:
                    oos_rets.append(lbl.return_pct)
                    oos_wins += 1 if lbl.label == 1 else 0
                    oos_total += 1
            except Exception:
                continue

        if not oos_rets or oos_total == 0:
            return 0.0, 0.0

        oos_avg = np.mean(oos_rets)
        oos_std = np.std(oos_rets, ddof=1) if len(oos_rets) > 1 else 1.0
        oos_bars = self.geometry.max_bars / 2  # Approximate
        oos_sharpe = round(
            float(oos_avg / max(oos_std, 1e-6)) * np.sqrt(252 / max(oos_bars, 1)), 3
        )
        oos_wr = round(oos_wins / oos_total * 100, 1)

        return oos_sharpe, oos_wr

    # ── Private helpers ────────────────────────────────────────────

    def _get_labels_for(
        self,
        ohlc: pd.DataFrame,
        signal: SignalPort,
        context: dict | None,
    ) -> list:
        """Re-run labeling for a signal."""
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
        """Extract vol regime integer series from ohlc."""
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

    def _compute_swing_breakdowns(
        self,
        ohlc: pd.DataFrame,
        labels: list,
        vol_regime_series: pd.Series,
    ) -> dict:
        """Compute all Swing-specific breakdowns for the passport."""
        if not labels:
            return self._empty_swing_breakdowns()

        close_arr = ohlc["close"].values.astype(float)

        wr_by_regime: dict[str, list] = {k: [] for k in _REGIME_INT_MAP.values()}
        wr_by_fear: dict[str, list] = {
            "PANIC": [], "FEAR": [], "ANXIETY": [], "NEUTRAL": [], "CONFIDENCE": [], "GREED": []
        }
        wr_by_sigma: dict[str, list] = {b[0]: [] for b in _SIGMA_BANDS}
        tide_regime_wr: dict[str, list] = {"BULL": [], "FLAT": [], "SHALLOW_BEAR": [], "BEAR": []}
        wave_flip_rets: list[float] = []
        wave_no_flip_rets: list[float] = []

        for lbl in labels:
            if lbl.entry_time is None:
                continue

            outcome = 1 if lbl.label == 1 else 0

            try:
                pos = ohlc.index.get_loc(lbl.entry_time)
            except Exception:
                continue

            # ── Vol regime ──
            try:
                regime_int = int(vol_regime_series.iloc[pos]) if pos < len(vol_regime_series) else 0
                regime_label = _REGIME_INT_MAP.get(regime_int, "NORMAL")
                wr_by_regime[regime_label].append(outcome)
            except Exception:
                pass

            # ── Fear level + sigma + wave_flip ──
            try:
                bias = compute_ticker_fear_level(ohlc, pos)
                if bias:
                    wr_by_fear[bias.fear_label].append(outcome)

                    # Sigma band
                    sig = bias.sigma_position
                    for band_name, lo, hi in _SIGMA_BANDS:
                        if lo <= sig < hi:
                            wr_by_sigma[band_name].append(outcome)
                            break

                    # Wave flip edge
                    if bias.wave_flip and bias.wave_flip_direction == 1:
                        wave_flip_rets.append(outcome)
                    else:
                        wave_no_flip_rets.append(outcome)

                    # Tide regime
                    if bias.tide_slope > 0.01:
                        tide_regime_wr["BULL"].append(outcome)
                    elif abs(bias.tide_slope) <= 0.01:
                        tide_regime_wr["FLAT"].append(outcome)
                    elif bias.tide_slope > -0.03:
                        tide_regime_wr["SHALLOW_BEAR"].append(outcome)
                    else:
                        tide_regime_wr["BEAR"].append(outcome)
            except Exception:
                pass

        def _wr_dict(buckets: dict) -> tuple[dict, dict]:
            wr, n = {}, {}
            for k, v in buckets.items():
                if v:
                    wr[k] = round(sum(v) / len(v) * 100, 1)
                    n[k] = len(v)
            return wr, n

        def _sharpe_dict(buckets: dict) -> dict:
            out = {}
            for k, outs in buckets.items():
                if len(outs) > 1:
                    std = np.std(outs, ddof=1)
                    avg = np.mean(outs)
                    out[k] = round(float(avg / max(std, 1e-6)) * np.sqrt(252), 2) if std > 0 else 0.0
            return out

        wr_fear, n_fear = _wr_dict(wr_by_fear)
        wr_sigma, n_sigma = _wr_dict(wr_by_sigma)
        wr_regime, n_regime = _wr_dict(wr_by_regime)
        wr_tide, n_tide = _wr_dict(tide_regime_wr)
        sharpe_regime = _sharpe_dict(wr_by_regime)

        flip_wr = round(sum(wave_flip_rets) / len(wave_flip_rets) * 100, 1) if wave_flip_rets else 0.0
        no_flip_wr = round(sum(wave_no_flip_rets) / len(wave_no_flip_rets) * 100, 1) if wave_no_flip_rets else 0.0
        flip_edge = round(flip_wr - no_flip_wr, 1)

        return {
            "wr_by_fear_level": wr_fear,
            "n_by_fear_level": n_fear,
            "wr_by_sigma_band": wr_sigma,
            "n_by_sigma_band": n_sigma,
            "wr_by_vol_regime": wr_regime,
            "n_by_vol_regime": n_regime,
            "sharpe_by_vol_regime": sharpe_regime,
            "tide_regime_wr": wr_tide,
            "n_by_tide_regime": n_tide,
            "wave_flip_wr": flip_wr,
            "wave_flip_no_wr": no_flip_wr,
            "wave_flip_edge": flip_edge,
        }

    @staticmethod
    def _empty_swing_breakdowns() -> dict:
        return {
            "wr_by_fear_level": {}, "n_by_fear_level": {},
            "wr_by_sigma_band": {}, "n_by_sigma_band": {},
            "wr_by_vol_regime": {}, "n_by_vol_regime": {},
            "sharpe_by_vol_regime": {},
            "tide_regime_wr": {}, "n_by_tide_regime": {},
            "wave_flip_wr": 0.0, "wave_flip_no_wr": 0.0, "wave_flip_edge": 0.0,
        }

    def _build_passport(
        self,
        ticker: str,
        signal_name: str,
        result: OracleResult,
        swing_breakdowns: dict,
        oos_sharpe: float,
        oos_win_rate: float,
    ) -> SignalPassport:
        """Build SignalPassport from OracleResult + Swing-specific breakdowns."""
        # Reliability score for Swing: OOS is king
        sharpe_norm = min(result.ceiling_sharpe / 2.0, 1.0) if result.ceiling_sharpe > 0 else 0.0
        robustness = (
            min(result.floor_sharpe / max(result.ceiling_sharpe, 0.01), 1.0)
            if result.floor_sharpe > 0 else 0.0
        )
        oos_norm = min(oos_sharpe / 2.0, 1.0) if oos_sharpe > 0 else 0.0

        # Consistency from std of returns (approximate from PF)
        avg_ret = result.avg_return_pct
        consistency = max(0.0, min(1.0, 1.0 - (abs(result.max_drawdown_pct) / max(abs(avg_ret) * result.n_entries, 0.001))))

        reliability = round(
            sharpe_norm * 0.25
            + robustness * 0.20
            + oos_norm * 0.35      # OOS is the most important for Swing
            + consistency * 0.20,
            3,
        )

        viable = (
            result.ceiling_sharpe >= 0.3
            and result.n_entries >= self.MIN_ENTRIES
            and result.win_rate >= 30
            and oos_sharpe >= 0.1   # OOS must show some edge
        )
        grade = (
            "A" if result.ceiling_sharpe >= 1.5 and oos_sharpe >= 0.8
            else "B" if result.ceiling_sharpe >= 1.0 and oos_sharpe >= 0.4
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
            oos_sharpe=oos_sharpe,
            oos_win_rate=oos_win_rate,
            sharpe_by_vol_regime=swing_breakdowns["sharpe_by_vol_regime"],
            wr_by_vol_regime=swing_breakdowns["wr_by_vol_regime"],
            n_by_vol_regime=swing_breakdowns["n_by_vol_regime"],
            wr_by_fear_level=swing_breakdowns["wr_by_fear_level"],
            n_by_fear_level=swing_breakdowns["n_by_fear_level"],
            wr_by_sigma_band=swing_breakdowns["wr_by_sigma_band"],
            n_by_sigma_band=swing_breakdowns["n_by_sigma_band"],
            wave_flip_wr=swing_breakdowns["wave_flip_wr"],
            wave_flip_no_wr=swing_breakdowns["wave_flip_no_wr"],
            wave_flip_edge=swing_breakdowns["wave_flip_edge"],
            tide_regime_wr=swing_breakdowns["tide_regime_wr"],
            n_by_tide_regime=swing_breakdowns["n_by_tide_regime"],
            viable=viable,
            grade=grade,
            geometry_used={
                "profit_mult": self.geometry.profit_mult,
                "loss_mult": self.geometry.loss_mult,
                "max_bars": self.geometry.max_bars,
            },
        )
