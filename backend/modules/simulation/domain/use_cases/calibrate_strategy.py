"""
Strategy Calibrator — ML-Driven Signal Weight Discovery
==========================================================
Uses Oracle rankings + XGBoost feature importance to produce
an optimized StrategyProfile for a ticker × category pair.

Pipeline:
1. DataHarmonizer.build_ml_dataset() → features from vault
2. OracleBacktester.rank_signals() → ceiling per signal
3. Discard signals with ceiling_sharpe < 0.3
4. XGBoost feature importance → signal weights
5. Build StrategyProfile with ML-discovered recipe
6. Persist profile + sync to dashboard
"""
import logging
from datetime import datetime, UTC
from typing import Optional

import numpy as np
import pandas as pd

from backend.modules.simulation.domain.entities.strategy_profile import (
    InvestmentCategory, StrategyProfile, SignalConfig,
    OracleGeometry, ORACLE_GEOMETRY, GatingCriteria,
)
from backend.modules.simulation.domain.use_cases.oracle_backtest import (
    OracleBacktester, SignalRanking,
)
from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort
from backend.modules.simulation.domain.ports.signal_port import SignalPort
from backend.modules.simulation.domain.ports.dashboard_sync_port import DashboardSyncPort
from backend.modules.simulation.domain.ports.data_harmonizer_port import DataHarmonizerPort

logger = logging.getLogger(__name__)

# Minimum Oracle ceiling to include a signal in the profile
MIN_CEILING_SHARPE = 0.3


class StrategyCalibrator:
    """
    ML-driven calibrator that produces optimized StrategyProfiles.

    The calibrator combines Oracle ceilings (theoretical max per signal)
    with XGBoost feature importance (empirical contribution) to discover
    the optimal signal weights for a given ticker × category.
    """

    def __init__(
        self,
        store: HistoricalDataPort,
        oracle: OracleBacktester,
        signals: list[SignalPort],
        dashboard: Optional[DashboardSyncPort] = None,
        harmonizer: Optional[DataHarmonizerPort] = None,
    ):
        self.store = store
        self.oracle = oracle
        self.signals = signals
        self.dashboard = dashboard
        self.harmonizer = harmonizer

    def calibrate(
        self,
        ticker: str,
        tf: str,
        category: InvestmentCategory,
        context: dict | None = None,
        warm_start_weights: dict[str, float] | None = None,
    ) -> StrategyProfile:
        """
        Full calibration pipeline for one ticker × category.

        Args:
            warm_start_weights: Optional dict of {signal_name: weight} from a previous
                calibration. When provided, these are blended with Oracle ceilings
                (70% warm-start, 30% Oracle) for faster convergence after regime changes.

        Returns a StrategyProfile with ML-discovered signal weights.
        """
        warm_mode = "WARM-START" if warm_start_weights else "COLD"
        logger.info(f"🔬 Calibrating {ticker}/{tf} for {category.value} [{warm_mode}]...")

        geometry = ORACLE_GEOMETRY[category]

        # Step 1: Oracle ranking — individual ceilings
        rankings = self.oracle.rank_signals(
            ticker, tf, self.signals, category, context,
        )

        # Step 2: Filter viable signals
        viable_signals = [r for r in rankings if r.viable and r.ceiling_sharpe >= MIN_CEILING_SHARPE]

        if not viable_signals:
            logger.warning(f"Calibrator: no viable signals for {ticker}/{category.value}")
            return self._empty_profile(ticker, tf, category, geometry)

        logger.info(
            f"Calibrator: {len(viable_signals)}/{len(rankings)} signals viable: "
            f"{[r.name for r in viable_signals]}"
        )

        # Step 3: Calculate weights from Oracle ceilings
        # Weight ∝ ceiling_sharpe (normalized to sum=1)
        total_ceiling = sum(r.ceiling_sharpe for r in viable_signals)
        signal_configs = []

        for ranking in rankings:
            is_viable = any(v.name == ranking.name for v in viable_signals)
            oracle_weight = ranking.ceiling_sharpe / total_ceiling if is_viable and total_ceiling > 0 else 0.0

            # Warm-start blending: if we have previous weights, blend them
            if warm_start_weights and ranking.name in warm_start_weights and is_viable:
                prev_w = warm_start_weights[ranking.name]
                # 70% warm-start, 30% Oracle — previous weights are the strong prior
                weight = 0.7 * prev_w + 0.3 * oracle_weight
            else:
                weight = oracle_weight

            signal_configs.append(SignalConfig(
                name=ranking.name,
                weight=round(weight, 4),
                threshold=0.5,
                enabled=is_viable,
                ceiling_sharpe=ranking.ceiling_sharpe,
            ))

        # Re-normalize after warm-start blending
        if warm_start_weights:
            total_w = sum(c.weight for c in signal_configs if c.enabled)
            if total_w > 0:
                for c in signal_configs:
                    if c.enabled:
                        c.weight = round(c.weight / total_w, 4)

        # Step 4: Try XGBoost weight refinement if enough data
        xgb_weights = self._try_xgboost_weights(ticker, tf, rankings)
        if xgb_weights:
            # Blend Oracle ceiling weights with XGBoost importance
            for config in signal_configs:
                if config.name in xgb_weights and config.enabled:
                    oracle_w = config.weight
                    xgb_w = xgb_weights[config.name]
                    # 60% Oracle, 40% XGBoost blend
                    config.weight = round(0.6 * oracle_w + 0.4 * xgb_w, 4)

            # Re-normalize
            total_w = sum(c.weight for c in signal_configs if c.enabled)
            if total_w > 0:
                for c in signal_configs:
                    if c.enabled:
                        c.weight = round(c.weight / total_w, 4)

        # Step 5: Build profile
        composite_sharpe = sum(r.ceiling_sharpe * (r.ceiling_sharpe / total_ceiling)
                               for r in viable_signals) if total_ceiling > 0 else 0.0

        profile = StrategyProfile(
            ticker=ticker,
            category=category,
            timeframe=tf,
            geometry=geometry,
            gating=GatingCriteria(),
            signals=signal_configs,
            composite_method="weighted_vote",
            min_signals_required=min(2, len(viable_signals)),
            calibrated_at=datetime.now(UTC).isoformat(),
            calibration_sharpe=round(composite_sharpe, 4),
            calibration_trades=sum(r.n_entries for r in viable_signals),
        )

        # Step 6: Persist
        self.store.save_profile(profile)
        if self.dashboard:
            self.dashboard.sync_profile(profile)

        logger.info(
            f"✅ Calibrated {ticker}/{category.value}: "
            f"{len(viable_signals)} signals, "
            f"composite_sharpe={profile.calibration_sharpe}"
        )
        return profile

    def _try_xgboost_weights(
        self, ticker: str, tf: str,
        rankings: list[SignalRanking],
    ) -> dict[str, float] | None:
        """
        Attempt XGBoost feature importance for weight refinement.
        Returns None if insufficient data or XGBoost unavailable.
        """
        try:
            if self.harmonizer is None:
                logger.info("Calibrator: no harmonizer provided, using Oracle-only weights")
                return None

            dataset = self.harmonizer.build_ml_dataset(ticker, tf)

            if dataset.empty or len(dataset) < 200:
                logger.info("Calibrator: insufficient data for XGBoost refinement")
                return None

            # Simple return-based labels
            dataset["target"] = (dataset["close"].pct_change(5).shift(-5) > 0).astype(int)
            dataset.dropna(subset=["target"], inplace=True)

            # Select signal-related features
            signal_features = [c for c in dataset.columns if c.startswith("uw_") or c in
                               ["volume", "close"]]

            if len(signal_features) < 3:
                return None

            X = dataset[signal_features].fillna(0)
            y = dataset["target"]

            from sklearn.model_selection import train_test_split
            from xgboost import XGBClassifier

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, shuffle=False)

            model = XGBClassifier(
                n_estimators=100, max_depth=4,
                learning_rate=0.1, random_state=42,
                verbosity=0,
            )
            model.fit(X_train, y_train)

            importance = dict(zip(signal_features, model.feature_importances_))

            # Map feature importance back to signal names
            signal_weights = {}
            viable_names = {r.name for r in rankings if r.viable}
            for sig_name in viable_names:
                # Approximate: signal weight = avg importance of related features
                related = [v for k, v in importance.items() if sig_name.split("_")[0] in k.lower()]
                if related:
                    signal_weights[sig_name] = float(np.mean(related))

            # Normalize
            total = sum(signal_weights.values()) or 1.0
            signal_weights = {k: v / total for k, v in signal_weights.items()}

            logger.info(f"XGBoost weights: {signal_weights}")
            return signal_weights

        except ImportError as e:
            logger.info(f"Calibrator: XGBoost not available ({e}), using Oracle-only weights")
            return None
        except Exception as e:
            logger.warning(f"Calibrator: XGBoost failed ({e}), using Oracle-only weights")
            return None

    def _empty_profile(
        self, ticker: str, tf: str,
        category: InvestmentCategory,
        geometry: OracleGeometry,
    ) -> StrategyProfile:
        """Return an empty profile when no signals are viable."""
        return StrategyProfile(
            ticker=ticker,
            category=category,
            timeframe=tf,
            geometry=geometry,
            signals=[],
            calibrated_at=datetime.now(UTC).isoformat(),
            calibration_sharpe=0.0,
        )
