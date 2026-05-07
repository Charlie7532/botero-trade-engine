"""
Neural Batch Runner — TCN+LSTM PoC on Top Promoted Tickers
==============================================================
Reads the V2 registry to identify top performers by Sharpe ratio,
then trains the TCN+LSTM neural sequencer on each one using
walk-forward validation.

Compares neural Sharpe vs XGBoost Sharpe to quantify the gain
from "letters → words" transition.

Usage:
    PYTHONPATH=. backend/.venv/bin/python backend/research_lab/experiments/neural_batch.py
    PYTHONPATH=. backend/.venv/bin/python backend/research_lab/experiments/neural_batch.py --top 5
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from backend.research_lab.models.neural_sequencer import (
    NeuralSequencer,
    SequencerConfig,
    create_sequences,
    walk_forward_split,
    train_one_fold,
    evaluate_sharpe,
)
from backend.research_lab.experiments.feature_discovery_runner import (
    build_enriched_features,
    label_next_bar,
)
from backend.research_lab.experiments.run_batch import _load_macro_extras, _load_market_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("NeuralBatch")


def load_top_tickers(registry_path: Path, top_n: int = 10) -> list[dict]:
    """
    Load the top N promoted tickers from the V2 registry,
    ranked by best Sharpe. Returns unique tickers only
    (one entry per ticker, the best experiment).
    """
    with open(registry_path) as f:
        records = json.load(f)

    # Filter to PROMOTED experiments with backward-eliminated dimensions
    promoted = [
        r for r in records
        if r.get("verdict") == "PROMOTED"
        and "Optimized" in r.get("description", "")
    ]

    if not promoted:
        # Fallback: any PROMOTED
        promoted = [r for r in records if r.get("verdict") == "PROMOTED"]

    # Best experiment per ticker
    best_per_ticker: dict[str, dict] = {}
    for r in promoted:
        ticker = r["ticker"]
        if ticker not in best_per_ticker or r["sharpe"] > best_per_ticker[ticker]["sharpe"]:
            best_per_ticker[ticker] = r

    # Sort by Sharpe descending, take top N
    sorted_tickers = sorted(
        best_per_ticker.values(),
        key=lambda x: x["sharpe"],
        reverse=True,
    )[:top_n]

    return sorted_tickers


def run_neural_experiment(
    ticker: str,
    optimal_dims: list[str],
    xgboost_sharpe: float,
    store,
    config: SequencerConfig,
) -> dict:
    """
    Run the TCN+LSTM experiment for a single ticker.

    1. Load OHLCV + macro data from Neon.
    2. Build enriched features (same as XGBoost pipeline).
    3. Filter to the optimal dimensions discovered by XGBoost.
    4. Create temporal sequences (sliding window).
    5. Walk-forward train/validate the neural sequencer.
    6. Compare neural Sharpe vs XGBoost Sharpe.
    """
    import torch
    device = torch.device("cpu")  # No GPU on this server

    logger.info(f"{'='*60}")
    logger.info(f"TICKER: {ticker} | XGBoost Sharpe: {xgboost_sharpe:.2f} | Dims: {len(optimal_dims)}")
    logger.info(f"{'='*60}")

    # 1. Load data
    ohlcv = store.load_bars(ticker, "1d")
    if len(ohlcv) < 300:
        logger.warning(f"  {ticker}: insufficient data ({len(ohlcv)} bars)")
        return {"ticker": ticker, "status": "SKIP", "reason": "insufficient_data"}

    macro_extras = _load_macro_extras(store, ohlcv)
    market_data = _load_market_data(store, ticker)
    features = build_enriched_features(ohlcv, macro_extras or None, market_data)
    labels = label_next_bar(ohlcv)

    # 2. Filter to optimal dimensions (discovered by XGBoost backward elimination)
    available_dims = [d for d in optimal_dims if d in features.columns]
    if len(available_dims) < 5:
        logger.warning(f"  {ticker}: too few dims available ({len(available_dims)}/{len(optimal_dims)})")
        return {"ticker": ticker, "status": "SKIP", "reason": "missing_dims"}

    X_raw = features[available_dims].values
    y_raw = labels.reindex(features.index).values

    # 3. Z-Score normalization (mandatory for neural networks)
    means = np.nanmean(X_raw, axis=0)
    stds = np.nanstd(X_raw, axis=0)
    stds[stds < 1e-8] = 1.0
    X_norm = (X_raw - means) / stds

    # Replace NaN/Inf with 0 after normalization
    X_norm = np.nan_to_num(X_norm, nan=0.0, posinf=0.0, neginf=0.0)

    # 4. Create sequences
    try:
        X_seq, y_seq = create_sequences(X_norm, y_raw, seq_len=config.seq_len)
    except ValueError as e:
        logger.warning(f"  {ticker}: {e}")
        return {"ticker": ticker, "status": "SKIP", "reason": str(e)}

    logger.info(f"  Sequences: {X_seq.shape[0]} windows × {X_seq.shape[1]} steps × {X_seq.shape[2]} dims")

    # 5. Walk-forward validation
    config.n_features = len(available_dims)
    splits = walk_forward_split(X_seq, y_seq, n_splits=3)

    fold_results = []
    for fold_idx, (X_tr, y_tr, X_te, y_te) in enumerate(splits):
        logger.info(f"  Fold {fold_idx + 1}/{len(splits)}: train={len(X_tr)}, test={len(X_te)}")

        model = NeuralSequencer(config)
        fold_metrics = train_one_fold(model, X_tr, y_tr, X_te, y_te, config, device)
        sharpe_metrics = evaluate_sharpe(model, X_te, y_te, device)

        fold_result = {**fold_metrics, **sharpe_metrics, "fold": fold_idx}
        fold_results.append(fold_result)

        logger.info(
            f"    → Acc={fold_metrics['val_accuracy']:.3f}, "
            f"Sharpe={sharpe_metrics['sharpe']:.2f}, "
            f"Trades={sharpe_metrics['n_trades']}, "
            f"Epochs={fold_metrics['best_epoch']}"
        )

    # 6. Aggregate results
    avg_sharpe = np.mean([f["sharpe"] for f in fold_results])
    avg_accuracy = np.mean([f["val_accuracy"] for f in fold_results])
    total_trades = sum(f["n_trades"] for f in fold_results)

    delta_sharpe = avg_sharpe - xgboost_sharpe
    verdict = "UPGRADE" if delta_sharpe > 0.5 else ("MATCH" if delta_sharpe > -0.5 else "DOWNGRADE")

    result = {
        "ticker": ticker,
        "status": "DONE",
        "xgboost_sharpe": xgboost_sharpe,
        "neural_sharpe": round(avg_sharpe, 4),
        "delta_sharpe": round(delta_sharpe, 4),
        "neural_accuracy": round(avg_accuracy, 4),
        "n_folds": len(fold_results),
        "total_trades": total_trades,
        "n_dims": len(available_dims),
        "seq_len": config.seq_len,
        "verdict": verdict,
        "fold_details": fold_results,
    }

    emoji = {"UPGRADE": "🚀", "MATCH": "🟡", "DOWNGRADE": "🔴"}
    logger.info(
        f"\n  {emoji.get(verdict, '⚪')} {ticker}: Neural Sharpe={avg_sharpe:.2f} vs "
        f"XGBoost={xgboost_sharpe:.2f} → Δ={delta_sharpe:+.2f} [{verdict}]\n"
    )
    return result


def main(top_n: int = 10, registry_path: str = None):
    """Main entry point for the neural batch."""
    import torch
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

    # Default registry: use V2 results
    if registry_path is None:
        registry_path = Path(__file__).parent / "results" / "registry.json"
    else:
        registry_path = Path(registry_path)

    logger.info(f"Neural Batch Runner — TCN+LSTM PoC")
    logger.info(f"Registry: {registry_path}")
    logger.info(f"Top N: {top_n}")
    logger.info(f"Device: {torch.device('cpu')}")

    # Load top tickers from V2 registry
    top_tickers = load_top_tickers(registry_path, top_n)
    if not top_tickers:
        logger.error("No promoted tickers found in registry. Run the V2 batch first.")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"TOP {len(top_tickers)} TICKERS FOR NEURAL PoC:")
    for i, t in enumerate(top_tickers, 1):
        logger.info(f"  {i}. {t['ticker']}: Sharpe={t['sharpe']:.2f}, Dims={len(t['dimensions_used'])}")
    logger.info(f"{'='*60}\n")

    store = TimescaleDataStore()
    config = SequencerConfig()

    results = []
    for entry in top_tickers:
        ticker = entry["ticker"]
        optimal_dims = entry["dimensions_used"]
        xgb_sharpe = entry["sharpe"]

        try:
            result = run_neural_experiment(
                ticker, optimal_dims, xgb_sharpe, store, config,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"  ❌ {ticker} failed: {e}")
            results.append({"ticker": ticker, "status": "ERROR", "error": str(e)})

    # Save results
    output_file = Path(__file__).parent / "results" / "neural_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Summary
    done = [r for r in results if r["status"] == "DONE"]
    if done:
        logger.info(f"\n{'='*60}")
        logger.info("NEURAL BATCH SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"{'Ticker':<8} {'XGB Sharpe':>11} {'Neural Sharpe':>14} {'Delta':>8} {'Verdict':<10}")
        logger.info("-" * 55)
        for r in sorted(done, key=lambda x: x["delta_sharpe"], reverse=True):
            logger.info(
                f"{r['ticker']:<8} {r['xgboost_sharpe']:>11.2f} {r['neural_sharpe']:>14.2f} "
                f"{r['delta_sharpe']:>+8.2f} {r['verdict']:<10}"
            )

        avg_delta = np.mean([r["delta_sharpe"] for r in done])
        upgrades = sum(1 for r in done if r["verdict"] == "UPGRADE")
        logger.info(f"\nAvg Δ Sharpe: {avg_delta:+.2f}")
        logger.info(f"Upgrades: {upgrades}/{len(done)}")

    store.close()
    logger.info(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Neural Batch Runner (TCN+LSTM PoC)")
    parser.add_argument("--top", type=int, default=10, help="Number of top tickers to test")
    parser.add_argument("--registry", type=str, default=None, help="Path to registry.json")
    args = parser.parse_args()

    main(top_n=args.top, registry_path=args.registry)
