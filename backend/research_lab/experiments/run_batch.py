"""
Quaternion Batch Runner — Autonomous Server Execution
=========================================================
Runs the full Oracle + Feature Discovery pipeline across ALL tickers
in the Neon universe. Designed to run unattended on the server.

Launch and forget:
    cd /root/botero-trade
    nohup PYTHONPATH=. backend/.venv/bin/python backend/research_lab/experiments/run_batch.py > quaternion_batch.log 2>&1 &

Check progress:
    tail -f quaternion_batch.log
    cat backend/research_lab/experiments/results/batch_progress.json

Stop gracefully:
    kill -SIGINT <pid>
"""
import json
import logging
import signal
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from backend.research_lab.experiments.experiment_registry import ExperimentRegistry
from backend.research_lab.experiments.feature_discovery_runner import (
    build_enriched_features, label_next_bar, run_xgboost_importance,
    backward_elimination, _evaluate_subset,
)
from backend.research_lab.experiments.quaternion_signal import QuaternionSignalAdapter
from backend.research_lab.models.quaternion_core import MarketQuaternion

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("QuaternionBatch")

# ── Graceful shutdown ──
_shutdown_requested = False

def _handle_sigint(signum, frame):
    global _shutdown_requested
    logger.info("⚠️ Shutdown requested — finishing current ticker then stopping...")
    _shutdown_requested = True

signal.signal(signal.SIGINT, _handle_sigint)
signal.signal(signal.SIGTERM, _handle_sigint)

# ── Progress file ──
PROGRESS_FILE = Path(__file__).parent / "results" / "batch_progress.json"


def _load_progress() -> dict:
    """Load batch progress from disk."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {
        "started_at": None,
        "last_updated": None,
        "total_tickers": 0,
        "completed_tickers": 0,
        "tickers_done": [],
        "tickers_promoted": [],
        "tickers_observation": [],
        "tickers_rejected": [],
        "current_ticker": None,
        "status": "not_started",
    }


def _save_progress(progress: dict) -> None:
    """Persist progress to disk."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["last_updated"] = datetime.now(UTC).isoformat()
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def run_ticker_pipeline(
    ticker: str,
    timeframe: str,
    store,
    registry: ExperimentRegistry,
) -> dict:
    """
    Run the full pipeline for a single ticker:
      1. Oracle test (SPECULATIVE_SPRING + QUALITY_VALUE)
      2. Feature Discovery (XGBoost backward elimination)

    Returns summary dict.
    """
    from backend.modules.simulation.application.use_cases.oracle_backtest import OracleBacktester
    from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
    from backend.modules.simulation.domain.entities.strategy_profile import (
        InvestmentCategory, ORACLE_GEOMETRY,
    )

    labeler = TripleBarrierAdapter()
    oracle = OracleBacktester(store, labeler)

    result_summary = {
        "ticker": ticker,
        "oracle_speculative_sharpe": 0.0,
        "oracle_quality_sharpe": 0.0,
        "discovery_full_sharpe": 0.0,
        "discovery_optimized_sharpe": 0.0,
        "discovery_full_dims": 0,
        "optimal_dimensions": [],
        "verdict": "REJECTED",
    }

    # ── Phase 1: Oracle Alpha Ceiling ──
    for category in [InvestmentCategory.SPECULATIVE_SPRING, InvestmentCategory.QUALITY_VALUE]:
        geometry = ORACLE_GEOMETRY[category]
        adapter = QuaternionSignalAdapter(include_predictions=False)

        try:
            oracle_result = oracle.run_signal(ticker, timeframe, adapter, geometry)

            key = "oracle_speculative_sharpe" if "SPECULATIVE" in category.value else "oracle_quality_sharpe"
            result_summary[key] = oracle_result.ceiling_sharpe

            registry.record(
                description=f"Oracle {category.value} {ticker}",
                dimensions_used=MarketQuaternion.BASE_DIMS + MarketQuaternion.DERIVATIVE_DIMS,
                dimensions_excluded=[],
                ticker=ticker, timeframe=timeframe,
                n_samples=oracle_result.n_entries,
                accuracy=oracle_result.win_rate / 100,
                sharpe=oracle_result.ceiling_sharpe,
                profit_factor=oracle_result.profit_factor,
                win_rate=oracle_result.win_rate,
                max_drawdown=oracle_result.max_drawdown_pct,
                n_trades=oracle_result.n_entries,
            )
        except Exception as e:
            logger.warning(f"  Oracle {category.value} failed for {ticker}: {e}")

    # ── Phase 2: Feature Discovery (only if Oracle showed promise) ──
    best_oracle = max(result_summary["oracle_speculative_sharpe"],
                      result_summary["oracle_quality_sharpe"])

    if best_oracle >= 0.3:
        try:
            ohlcv = store.load_bars(ticker, timeframe)
            if len(ohlcv) >= 300:
                # Build enriched features
                macro_extras = _load_macro_extras(store, ohlcv)
                features = build_enriched_features(ohlcv, macro_extras or None)
                labels = label_next_bar(ohlcv)
                result_summary["discovery_full_dims"] = features.shape[1]

                # Full model
                importance, full_acc = run_xgboost_importance(features, labels)
                if importance:
                    _, sharpe_full, pf_full, wr_full, mdd_full, nt_full = _evaluate_subset(
                        features, labels, ohlcv,
                    )
                    result_summary["discovery_full_sharpe"] = sharpe_full

                    registry.record(
                        description=f"Full {ticker} ({features.shape[1]}D)",
                        dimensions_used=list(features.columns),
                        dimensions_excluded=[],
                        ticker=ticker, timeframe=timeframe,
                        n_samples=len(features),
                        accuracy=full_acc, sharpe=sharpe_full,
                        profit_factor=pf_full, win_rate=wr_full,
                        max_drawdown=mdd_full, n_trades=nt_full,
                    )

                    # Backward elimination
                    optimal_features, optimal_acc = backward_elimination(
                        features, labels, importance,
                    )
                    _, sharpe_opt, pf_opt, wr_opt, mdd_opt, nt_opt = _evaluate_subset(
                        features[optimal_features], labels, ohlcv,
                    )
                    result_summary["discovery_optimized_sharpe"] = sharpe_opt
                    result_summary["optimal_dimensions"] = optimal_features

                    excluded = [f for f in features.columns if f not in optimal_features]
                    registry.record(
                        description=f"Opt {ticker} ({len(optimal_features)}D)",
                        dimensions_used=optimal_features,
                        dimensions_excluded=excluded,
                        ticker=ticker, timeframe=timeframe,
                        n_samples=len(features),
                        accuracy=optimal_acc, sharpe=sharpe_opt,
                        profit_factor=pf_opt, win_rate=wr_opt,
                        max_drawdown=mdd_opt, n_trades=nt_opt,
                    )
                else:
                    logger.info(f"  XGBoost returned empty importances for {ticker}")
        except Exception as e:
            logger.warning(f"  Feature Discovery failed for {ticker}: {e}")

    # Determine final verdict
    all_sharpes = [
        result_summary["oracle_speculative_sharpe"],
        result_summary["oracle_quality_sharpe"],
        result_summary["discovery_optimized_sharpe"],
    ]
    best = max(all_sharpes)
    if best >= 1.0:
        result_summary["verdict"] = "PROMOTED"
    elif best >= 0.5:
        result_summary["verdict"] = "OBSERVATION"
    else:
        result_summary["verdict"] = "REJECTED"

    return result_summary


def _load_macro_extras(store, ohlcv) -> dict:
    """Load macro z-scores from Neon vault."""
    extras = {}
    for raw_ticker, label in [("SKEW", "skew"), ("VVIX", "vvix")]:
        try:
            macro_bars = store.load_bars(raw_ticker, "1d")
            if not macro_bars.empty:
                raw = macro_bars["close"].reindex(ohlcv.index, method="ffill")
                mean = raw.rolling(50, min_periods=10).mean()
                std = raw.rolling(50, min_periods=10).std().clip(lower=1e-8)
                extras[f"{label}_zscore"] = (raw - mean) / std
                extras[f"{label}_delta"] = raw.pct_change(5)
        except Exception:
            pass
    return extras


def run_batch(
    timeframe: str = "1d",
    max_tickers: int | None = None,
    skip_done: bool = True,
) -> None:
    """
    Run the full pipeline across the entire Neon universe.

    Args:
        timeframe: Bar timeframe to analyze.
        max_tickers: Limit the number of tickers (None = all).
        skip_done: Skip tickers already processed in a previous run.
    """
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

    store = TimescaleDataStore()
    registry = ExperimentRegistry()
    progress = _load_progress()

    # Get universe from Neon
    try:
        conn = store._conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ticker FROM market.ohlcv_bars
            WHERE timeframe = '1d'
            ORDER BY ticker
        """)
        all_tickers = [row[0] for row in cur.fetchall()]
        cur.close()
        store._put(conn)
    except Exception as e:
        logger.error(f"Failed to load universe: {e}")
        store.close()
        return

    # Filter out already-done tickers (use set for O(1) lookup)
    if skip_done and progress["tickers_done"]:
        done_set = set(progress["tickers_done"])
        remaining = [t for t in all_tickers if t not in done_set]
        logger.info(f"Resuming: {len(done_set)} done, {len(remaining)} remaining")
    else:
        remaining = all_tickers

    if max_tickers:
        remaining = remaining[:max_tickers]

    progress["total_tickers"] = len(all_tickers)
    progress["status"] = "running"
    if not progress["started_at"]:
        progress["started_at"] = datetime.now(UTC).isoformat()
    _save_progress(progress)

    logger.info(f"═══ QUATERNION BATCH: {len(remaining)} tickers to process ═══")

    for i, ticker in enumerate(remaining):
        if _shutdown_requested:
            logger.info("🛑 Graceful shutdown — progress saved.")
            break

        progress["current_ticker"] = ticker
        _save_progress(progress)

        logger.info(f"\n[{i+1}/{len(remaining)}] ── {ticker} ──")
        t0 = time.time()

        try:
            summary = run_ticker_pipeline(ticker, timeframe, store, registry)
            elapsed = time.time() - t0

            # Best sharpe across ALL phases (not just two)
            best_sharpe = max(
                summary["oracle_speculative_sharpe"],
                summary["oracle_quality_sharpe"],
                summary["discovery_optimized_sharpe"],
            )

            emoji = {"PROMOTED": "🟢", "OBSERVATION": "🟡", "REJECTED": "🔴"}[summary["verdict"]]
            logger.info(
                f"  {emoji} {ticker}: best_sharpe={best_sharpe:.2f} "
                f"dims={summary['discovery_full_dims']}→{len(summary['optimal_dimensions'])} "
                f"({summary['verdict']}) [{elapsed:.1f}s]"
            )

            # Update progress
            progress["tickers_done"].append(ticker)
            progress["completed_tickers"] = len(progress["tickers_done"])
            if summary["verdict"] == "PROMOTED":
                progress["tickers_promoted"].append(ticker)
            elif summary["verdict"] == "OBSERVATION":
                progress.setdefault("tickers_observation", []).append(ticker)
            else:
                progress["tickers_rejected"].append(ticker)

        except Exception as e:
            logger.error(f"  ❌ {ticker} failed: {e}")
            progress["tickers_done"].append(ticker)
            progress["completed_tickers"] = len(progress["tickers_done"])

        _save_progress(progress)

    # ── Final summary ──
    progress["status"] = "completed" if not _shutdown_requested else "paused"
    progress["current_ticker"] = None
    _save_progress(progress)

    n_obs = progress["completed_tickers"] - len(progress["tickers_promoted"]) - len(progress["tickers_rejected"])
    logger.info("\n" + "=" * 70)
    logger.info(f"BATCH COMPLETE: {progress['completed_tickers']}/{progress['total_tickers']} tickers")
    logger.info(f"  🟢 PROMOTED:    {len(progress['tickers_promoted'])} → {progress['tickers_promoted'][:20]}")
    logger.info(f"  🟡 OBSERVATION: {n_obs}")
    logger.info(f"  🔴 REJECTED:    {len(progress['tickers_rejected'])}")
    logger.info("\n" + registry.summary_table())

    store.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quaternion Batch Runner")
    parser.add_argument("--tf", default="1d", help="Timeframe")
    parser.add_argument("--max", type=int, default=None, help="Max tickers to process (None=all)")
    parser.add_argument("--fresh", action="store_true", help="Ignore previous progress, start fresh")
    args = parser.parse_args()

    run_batch(
        timeframe=args.tf,
        max_tickers=args.max,
        skip_done=not args.fresh,
    )
