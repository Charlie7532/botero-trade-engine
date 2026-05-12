"""
Oracle Backtest — Individual & Composite Signal Evaluation
=============================================================
Measures the Alpha Ceiling of each SignalPort in isolation using
Triple Barrier labeling, then ranks signals by performance.

This is the core calibration tool: it answers "what is the maximum
possible Sharpe if this signal were perfect?"

Usage:
    oracle = OracleBacktester(store, labeler)
    ranking = oracle.rank_signals("SPY", "1d", create_all_signals())
    # → [SignalRanking(name='kalman', ceiling_sharpe=1.42, ...), ...]
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backend.modules.simulation.domain.entities.strategy_profile import (
    InvestmentCategory, OracleGeometry, ORACLE_GEOMETRY,
)
from backend.modules.simulation.domain.ports.barrier_labeler_port import BarrierLabelerPort
from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort
from backend.modules.simulation.domain.ports.signal_port import SignalPort
from backend.modules.simulation.domain.ports.ml_data_port import MLDataPort

logger = logging.getLogger(__name__)


@dataclass
class OracleResult:
    """Result of Oracle evaluation for a single signal × geometry."""
    signal_name: str
    ticker: str
    timeframe: str

    # Performance
    n_entries: int = 0
    n_profitable: int = 0
    n_loss: int = 0
    n_time_exit: int = 0
    win_rate: float = 0.0
    avg_return_pct: float = 0.0
    total_return_pct: float = 0.0
    ceiling_sharpe: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_bars_held: float = 0.0
    
    # Forensic metrics
    avg_bars_to_loss: float = 0.0
    pct_loss_hit: float = 0.0
    pct_time_hit: float = 0.0

    # Geometry used
    profit_mult: float = 0.0
    loss_mult: float = 0.0
    max_bars: int = 0


@dataclass
class SignalRanking:
    """Ranked signal with Oracle ceiling and viability assessment."""
    name: str
    ceiling_sharpe: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    n_entries: int = 0
    avg_return_pct: float = 0.0
    viable: bool = False       # Meets minimum criteria
    rank: int = 0

    @property
    def grade(self) -> str:
        if self.ceiling_sharpe >= 1.5:
            return "A"
        elif self.ceiling_sharpe >= 1.0:
            return "B"
        elif self.ceiling_sharpe >= 0.5:
            return "C"
        else:
            return "D"


class OracleBacktester:
    """
    Measures Alpha Ceilings for individual and composite signals.

    The Oracle answers: "If this signal were perfect, what is the
    maximum Sharpe it could achieve?" This establishes the theoretical
    ceiling for each module before ML weight optimization.
    """

    # Minimum entries for statistical significance
    MIN_ENTRIES = 10

    def __init__(
        self,
        store: HistoricalDataPort,
        labeler: BarrierLabelerPort,
        ml_store: MLDataPort | None = None,
    ):
        self.store = store
        self.labeler = labeler
        self.ml_store = ml_store

    def run_signal(
        self,
        ticker: str,
        tf: str,
        signal: SignalPort,
        geometry: OracleGeometry,
        context: dict | None = None,
    ) -> OracleResult:
        """
        Evaluate a single signal's Alpha Ceiling.

        1. Load OHLCV from vault
        2. Generate signal entries
        3. Label with Triple Barrier
        4. Calculate performance metrics
        """
        # Load data
        ohlc = self.store.load_bars(ticker, tf)
        if ohlc.empty or len(ohlc) < 100:
            logger.warning(f"Oracle: insufficient data for {ticker}/{tf}")
            return OracleResult(signal_name=signal.name, ticker=ticker, timeframe=tf)

        # Generate signals
        signal_df = signal.generate(ohlc, context)
        entries = signal_df["signal"] == 1  # Only long entries for now

        n_entries = entries.sum()
        if n_entries < self.MIN_ENTRIES:
            logger.info(f"Oracle: {signal.name} → only {n_entries} entries (min={self.MIN_ENTRIES})")
            return OracleResult(
                signal_name=signal.name, ticker=ticker, timeframe=tf,
                n_entries=int(n_entries),
            )

        # Label with Triple Barrier
        labels = self.labeler.label_entries(
            ohlc, entries,
            profit_mult=geometry.profit_mult,
            loss_mult=geometry.loss_mult,
            max_bars=geometry.max_bars,
            vol_lookback=geometry.vol_lookback,
        )

        if not labels:
            return OracleResult(signal_name=signal.name, ticker=ticker, timeframe=tf)

        # ====== SAVE TO ML DATA LAKE (Stationary Features via QuantFeatureEngineer) ======
        import uuid
        if self.ml_store:
            from backend.modules.simulation.application.use_cases.engineer_features import QuantFeatureEngineer

            # Determine timeframe in minutes for QuantFeatureEngineer
            tf_minutes_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
            tf_mins = tf_minutes_map.get(tf, 1440)

            # Compute full stationary feature matrix ONCE per signal run
            eng = QuantFeatureEngineer(ohlc, timeframe_minutes=tf_mins)
            eng.extract_fractional_features()
            eng.extract_microstructure_features()
            eng.extract_temporal_features()
            eng.extract_volume_flow_features()
            eng.extract_calendar_features()
            feat_df = eng.df
            feat_cols = eng.get_feature_columns()

            # Accumulate records for batch insertion
            batch_features = []
            batch_labels = []

            for label in labels:
                if label.entry_time is None:
                    continue

                if label.entry_time not in feat_df.index:
                    continue

                pos = feat_df.index.get_loc(label.entry_time)
                if pos < 60:
                    continue  # Need sufficient lookback for rolling features

                row = feat_df.iloc[pos]

                # Extract only the stationary feature columns, skip NaN rows
                feat_dict = {}
                has_nan = False
                for col in feat_cols:
                    val = row.get(col)
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        has_nan = True
                        break
                    feat_dict[col] = float(val)

                if has_nan or not feat_dict:
                    continue

                feature_id = str(uuid.uuid4())

                batch_features.append({
                    "id": feature_id,
                    "ticker": ticker,
                    "timeframe": tf,
                    "signal_name": signal.name,
                    "signal_time": label.entry_time.isoformat(),
                    "features": feat_dict
                })

                batch_labels.append({
                    "feature_id": feature_id,
                    "label": label.label,
                    "return_pct": label.return_pct,
                    "bars_held": label.bars_held,
                    "exit_time": label.exit_time.isoformat() if label.exit_time else None,
                    "geometry_used": {
                        "profit_mult": geometry.profit_mult,
                        "loss_mult": geometry.loss_mult,
                        "max_bars": geometry.max_bars
                    }
                })

            # Batch flush to Neon (2 round-trips instead of 2×N)
            if batch_features:
                try:
                    self.ml_store.save_ml_batch(batch_features, batch_labels)
                except Exception as e:
                    logger.warning(f"Failed to batch-save {len(batch_features)} ML records for {ticker}: {e}")

        # ====== END ML DATA LAKE ======

        # Calculate metrics
        returns = [l.return_pct for l in labels]
        n_profit = sum(1 for l in labels if l.label == 1)
        n_loss = sum(1 for l in labels if l.label == -1)
        n_time = sum(1 for l in labels if l.label == 0)
        bars = [l.bars_held for l in labels]

        total_return = sum(returns)
        avg_return = np.mean(returns) if returns else 0.0
        win_rate = n_profit / max(len(labels), 1) * 100

        # Sharpe calculation (annualized)
        if len(returns) > 1:
            ret_std = np.std(returns, ddof=1)
            if ret_std > 0:
                sharpe = (avg_return / ret_std) * np.sqrt(252 / max(np.mean(bars), 1))
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        # Profit factor
        gross_profit = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r < 0))
        pf = gross_profit / max(gross_loss, 0.001)

        # Max drawdown (sequential)
        cum = np.cumsum(returns)
        peak = np.maximum.accumulate(cum)
        dd = cum - peak
        max_dd = float(np.min(dd)) if len(dd) > 0 else 0.0

        # Forensic metrics
        loss_bars = [l.bars_held for l in labels if l.label == -1]
        avg_bars_to_loss = round(float(np.mean(loss_bars)), 1) if loss_bars else 0.0
        pct_loss_hit = round((n_loss / len(labels)) * 100, 1) if labels else 0.0
        pct_time_hit = round((n_time / len(labels)) * 100, 1) if labels else 0.0

        result = OracleResult(
            signal_name=signal.name,
            ticker=ticker,
            timeframe=tf,
            n_entries=len(labels),
            n_profitable=n_profit,
            n_loss=n_loss,
            n_time_exit=n_time,
            win_rate=round(win_rate, 2),
            avg_return_pct=round(avg_return, 4),
            total_return_pct=round(total_return, 4),
            ceiling_sharpe=round(sharpe, 4),
            profit_factor=round(pf, 4),
            max_drawdown_pct=round(max_dd, 4),
            avg_bars_held=round(float(np.mean(bars)), 1),
            avg_bars_to_loss=avg_bars_to_loss,
            pct_loss_hit=pct_loss_hit,
            pct_time_hit=pct_time_hit,
            profit_mult=geometry.profit_mult,
            loss_mult=geometry.loss_mult,
            max_bars=geometry.max_bars,
        )

        logger.info(
            f"Oracle: {signal.name} → Sharpe={result.ceiling_sharpe} "
            f"WR={result.win_rate}% PF={result.profit_factor} "
            f"Entries={result.n_entries}"
        )
        return result

    def run_composite(
        self,
        ticker: str,
        tf: str,
        signals: list[SignalPort],
        weights: dict[str, float],
        threshold: float,
        geometry: OracleGeometry,
        context: dict | None = None,
    ) -> OracleResult:
        """
        Evaluate a weighted combination of signals.

        Entry triggered when weighted sum ≥ threshold.
        """
        ohlc = self.store.load_bars(ticker, tf)
        if ohlc.empty or len(ohlc) < 100:
            return OracleResult(signal_name="composite", ticker=ticker, timeframe=tf)

        # Generate all signals
        composite = pd.Series(0.0, index=ohlc.index)
        for signal in signals:
            weight = weights.get(signal.name, 0.0)
            if weight <= 0:
                continue
            signal_df = signal.generate(ohlc, context)
            composite += signal_df["signal"].astype(float) * weight

        # Normalize by total weight
        total_weight = sum(weights.get(s.name, 0) for s in signals if weights.get(s.name, 0) > 0)
        if total_weight > 0:
            composite /= total_weight

        entries = composite >= threshold

        # Reuse same labeling logic
        labels = self.labeler.label_entries(
            ohlc, entries,
            profit_mult=geometry.profit_mult,
            loss_mult=geometry.loss_mult,
            max_bars=geometry.max_bars,
        )

        if not labels or len(labels) < self.MIN_ENTRIES:
            return OracleResult(
                signal_name="composite", ticker=ticker, timeframe=tf,
                n_entries=len(labels) if labels else 0,
            )

        # Calculate metrics (same as run_signal)
        returns = [l.return_pct for l in labels]
        n_profit = sum(1 for l in labels if l.label == 1)
        bars = [l.bars_held for l in labels]

        avg_return = np.mean(returns)
        ret_std = np.std(returns, ddof=1) if len(returns) > 1 else 1.0
        sharpe = (avg_return / max(ret_std, 0.001)) * np.sqrt(252 / max(np.mean(bars), 1))

        gross_profit = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r < 0))

        # Forensic metrics
        loss_bars = [l.bars_held for l in labels if l.label == -1]
        avg_bars_to_loss = round(float(np.mean(loss_bars)), 1) if loss_bars else 0.0
        n_loss = sum(1 for l in labels if l.label == -1)
        n_time = sum(1 for l in labels if l.label == 0)
        pct_loss_hit = round((n_loss / len(labels)) * 100, 1) if labels else 0.0
        pct_time_hit = round((n_time / len(labels)) * 100, 1) if labels else 0.0

        return OracleResult(
            signal_name="composite",
            ticker=ticker,
            timeframe=tf,
            n_entries=len(labels),
            n_profitable=n_profit,
            n_loss=n_loss,
            n_time_exit=n_time,
            win_rate=round(n_profit / len(labels) * 100, 2),
            avg_return_pct=round(avg_return, 4),
            total_return_pct=round(sum(returns), 4),
            ceiling_sharpe=round(sharpe, 4),
            profit_factor=round(gross_profit / max(gross_loss, 0.001), 4),
            avg_bars_held=round(float(np.mean(bars)), 1),
            avg_bars_to_loss=avg_bars_to_loss,
            pct_loss_hit=pct_loss_hit,
            pct_time_hit=pct_time_hit,
            profit_mult=geometry.profit_mult,
            loss_mult=geometry.loss_mult,
            max_bars=geometry.max_bars,
        )

    def rank_signals(
        self,
        ticker: str,
        tf: str,
        signals: list[SignalPort],
        category: InvestmentCategory = InvestmentCategory.SPECULATIVE_SPRING,
        context: dict | None = None,
    ) -> list[SignalRanking]:
        """
        Rank all signals by their individual Alpha Ceiling.

        Returns sorted list (best first) with viability flags.
        """
        geometry = ORACLE_GEOMETRY[category]
        rankings = []

        for signal in signals:
            result = self.run_signal(ticker, tf, signal, geometry, context)

            ranking = SignalRanking(
                name=result.signal_name,
                ceiling_sharpe=result.ceiling_sharpe,
                win_rate=result.win_rate,
                profit_factor=result.profit_factor,
                n_entries=result.n_entries,
                avg_return_pct=result.avg_return_pct,
                viable=(
                    result.ceiling_sharpe >= 0.3
                    and result.n_entries >= self.MIN_ENTRIES
                    and result.win_rate >= 30
                ),
            )
            rankings.append(ranking)

        # Sort by ceiling Sharpe descending
        rankings.sort(key=lambda r: r.ceiling_sharpe, reverse=True)

        # Assign ranks
        for i, r in enumerate(rankings):
            r.rank = i + 1

        logger.info(
            f"Oracle Ranking for {ticker}/{tf} ({category.value}):\n"
            + "\n".join(
                f"  #{r.rank} {r.name}: Sharpe={r.ceiling_sharpe} "
                f"WR={r.win_rate}% Grade={r.grade} {'✅' if r.viable else '❌'}"
                for r in rankings
            )
        )
        return rankings
