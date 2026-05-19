"""
walk_forward_narrative_dsr.py — DSR Validation for Narrative Signatures
========================================================================
Tests whether the narrative decomposition sub-signals maintain their alpha
in walk-forward OOS validation. Uses same framework as walk_forward_dsr_v2.py.

Setups tested:
  1. HYPER_3BC_MB (base) — re-validation with 20yr data
  2. HYPER_3BC_MB + BEARISH_ENGULFING central — confidence ×1.25
  3. HYPER_3BC_MB + BEARISH_MARUBOZU central — confidence ×1.25
  4. HYPER_3BC_MB + floor close position (≤0.28)
  5. HYPER_3BC_MB + extreme body ratio (>0.80)
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import linregress, norm
from pathlib import Path

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.pattern_recognition.application.use_cases.detect_patterns import PatternRecognitionIntelligence
from backend.modules.simulation.infrastructure.signal_adapters import PatternSignalAdapter
from backend.scripts.calibrate_passports import QUALITY_TICKERS

import logging
logging.getLogger("backend.modules.pattern_recognition").setLevel(logging.ERROR)

EXTENDED_TICKERS = list(QUALITY_TICKERS) + ["SPY", "QQQ"]


def get_trend_state(closes, i, lookback=60):
    y = closes[i-lookback:i]
    if len(y) < lookback or y[0] <= 0:
        return "HORIZONTAL"
    x = np.arange(lookback)
    y_norm = y / y[0]
    slope, _, _, _, _ = linregress(x, y_norm)
    if slope > 0.0020:     return "MUY_ALCISTA"
    elif slope > 0.0005:   return "ALCISTA"
    elif slope > -0.0005:  return "HORIZONTAL"
    elif slope > -0.0020:  return "BAJISTA"
    else:                  return "MUY_BAJISTA"


def deflated_sharpe_ratio(observed_sr, all_sharpes, T):
    N = len(all_sharpes)
    if N <= 1 or T <= 1:
        return 0.0
    gamma = 0.5772
    sr_std = max(np.std(all_sharpes, ddof=1), 0.01)
    z_inv = norm.ppf(1.0 - 1.0 / N) if N > 1 else 0
    z_inv_e = norm.ppf(1.0 - 1.0 / (N * np.e)) if N > 1 else 0
    e_max_sr = sr_std * ((1 - gamma) * z_inv + gamma * z_inv_e)
    se_sr = np.sqrt(1.0 / T)
    if se_sr <= 0:
        return 0.0
    return norm.cdf((observed_sr - e_max_sr) / se_sr)


def main():
    store = TimescaleDataStore()
    engine = PatternRecognitionIntelligence()
    adapter = PatternSignalAdapter()

    TRAIN_DAYS = int(2 * 365.25)
    TEST_DAYS = int(0.5 * 365.25)
    PURGE_DAYS = 10

    print("=" * 120)
    print(f"{'WALK-FORWARD DSR — NARRATIVE SIGNATURE VALIDATION':^120}")
    print(f"{'Train=2yr, Test=6mo, Purge=10d | 32 tickers | 20yr+ history':^120}")
    print("=" * 120)

    # ── Phase 1: Collect HYPER_3BC_MB events with narrative decomposition ──
    print("\n  Phase 1: Collecting HYPER_3BC_MB events with narrative decomposition...")
    events = []

    for ti, ticker in enumerate(EXTENDED_TICKERS):
        print(f"    [{ti+1}/{len(EXTENDED_TICKERS)}] {ticker}...", flush=True)
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue

        closes = ohlc["close"].values
        opens = ohlc["open"].values
        highs = ohlc["high"].values
        lows = ohlc["low"].values
        trend_series = adapter._compute_dlr_trend(ohlc, lookback=60)

        for i in range(60, len(ohlc) - 11):
            if trend_series.iloc[i] != "MUY_BAJISTA":
                continue

            hyper_df = adapter.synthesize_hyper_candles(ohlc, end_idx=i)
            if hyper_df is None or len(hyper_df) < 3:
                continue

            verdict = engine.detect(hyper_df)
            if verdict.primary_pattern != "THREE_BLACK_CROWS":
                continue

            # Forward return
            exec_price = opens[i+1] + (highs[i+1] - lows[i+1]) * 0.10
            if exec_price <= 0:
                continue
            ret_10d = (closes[i+10] - exec_price) / exec_price * 100

            # Narrative decomposition
            narrative = adapter.decompose_narrative(engine, ohlc, end_idx=i)
            macro_central = narrative["macro_central"] if narrative else "NONE"
            macro_final = narrative["macro_final"] if narrative else "NONE"
            confidence = narrative["confidence"] if narrative else 1.0
            morphology = narrative.get("morphology", []) if narrative else []

            final_close_pos = morphology[2]["close_position"] if len(morphology) == 3 else 0.5
            final_body_ratio = morphology[2]["body_ratio"] if len(morphology) == 3 else 0.5

            events.append({
                "date": ohlc.index[i],
                "ticker": ticker,
                "ret_10d": ret_10d,
                "macro_central": macro_central,
                "macro_final": macro_final,
                "confidence": confidence,
                "final_close_pos": final_close_pos,
                "final_body_ratio": final_body_ratio,
            })

    store.close()
    events.sort(key=lambda x: x["date"])
    dates = [e["date"] for e in events]
    min_date, max_date = dates[0], dates[-1]
    total_years = (max_date - min_date).days / 365.25
    print(f"  Total HYPER_3BC_MB events: {len(events):,} | "
          f"Range: {min_date.strftime('%Y-%m-%d')} → {max_date.strftime('%Y-%m-%d')} ({total_years:.1f}yr)")

    # ── Define sub-setups ──
    SETUPS = [
        {"label": "HYPER_3BC_MB (base)",
         "filter": lambda e: True},
        {"label": "  + BE_CENTRAL (Bearish Engulfing central)",
         "filter": lambda e: e["macro_central"] == "BEARISH_ENGULFING"},
        {"label": "  + BM_CENTRAL (Bearish Marubozu central)",
         "filter": lambda e: e["macro_central"] == "BEARISH_MARUBOZU"},
        {"label": "  + DEEP_CENTRAL (BE or BM)",
         "filter": lambda e: e["macro_central"] in ("BEARISH_ENGULFING", "BEARISH_MARUBOZU")},
        {"label": "  + FLOOR_CLOSE (close_pos ≤ 0.28)",
         "filter": lambda e: e["final_close_pos"] <= 0.28},
        {"label": "  + EXTREME_BODY (body_ratio > 0.80)",
         "filter": lambda e: e["final_body_ratio"] > 0.80},
        {"label": "  + CONFIDENCE ≥ 1.25",
         "filter": lambda e: e["confidence"] >= 1.25},
        {"label": "  + DRAGONFLY_CENTRAL (anti-signal)",
         "filter": lambda e: e["macro_central"] == "DRAGONFLY_DOJI"},
        {"label": "  + MORNING_STAR_FINAL (trap)",
         "filter": lambda e: e["macro_final"] in ("MORNING_STAR", "BULLISH_ENGULFING", "THREE_WHITE_SOLDIERS")},
    ]

    # ── Phase 2: Walk-Forward per sub-setup ──
    print(f"\n  Phase 2: Walk-Forward (2yr train / 6mo test)...")
    print(f"\n  {'Setup':<50} | {'N_OOS':>5} | {'WR_OOS':>6} | {'Sharpe':>7} | {'DSR':>5} | {'Folds':>5} | Grade")
    print(f"  {'-'*50}-+-{'-'*5}-+-{'-'*6}-+-{'-'*7}-+-{'-'*5}-+-{'-'*5}-+-{'-'*10}")

    all_sharpes_collector = []

    for setup in SETUPS:
        matching = [e for e in events if setup["filter"](e)]
        if len(matching) < 5:
            print(f"  {setup['label']:<50} | {'N/A':>5} | {'N/A':>6} | {'N/A':>7} | {'N/A':>5} | {'N/A':>5} | SKIP (N={len(matching)})")
            continue

        oos_returns = []
        n_folds = 0

        window_start = min_date
        while True:
            train_end = window_start + pd.Timedelta(days=TRAIN_DAYS)
            test_start = train_end + pd.Timedelta(days=PURGE_DAYS)
            test_end = test_start + pd.Timedelta(days=TEST_DAYS)

            if test_end > max_date:
                break

            train_events = [e for e in matching if window_start <= e["date"] < train_end]
            test_events = [e for e in matching if test_start <= e["date"] < test_end]

            if len(train_events) >= 2 and len(test_events) >= 1:
                for e in test_events:
                    oos_returns.append(e["ret_10d"])
                n_folds += 1

            window_start += pd.Timedelta(days=TEST_DAYS)

        if len(oos_returns) < 3:
            print(f"  {setup['label']:<50} | {len(oos_returns):>5} | {'N/A':>6} | {'N/A':>7} | {'N/A':>5} | {n_folds:>5} | INSUFFICIENT")
            continue

        oos_arr = np.array(oos_returns)
        wr = (oos_arr > 0).mean() * 100
        sharpe = oos_arr.mean() / max(oos_arr.std(), 0.01)
        all_sharpes_collector.append(sharpe)

        if len(all_sharpes_collector) >= 2:
            dsr = deflated_sharpe_ratio(sharpe, all_sharpes_collector, len(oos_arr))
        else:
            dsr = float("nan")

        if wr >= 70 and len(oos_arr) >= 30:
            grade = "[VALIDATED] B"
        elif wr >= 60 and len(oos_arr) >= 20:
            grade = "[VALIDATED] C"
        elif wr >= 55 and len(oos_arr) >= 10:
            grade = "[HYPOTHESIS] C"
        elif wr < 50:
            grade = "REJECT"
        else:
            grade = "[HYPOTHESIS] D"

        print(f"  {setup['label']:<50} | {len(oos_arr):>5} | {wr:>5.1f}% | {sharpe:>+6.3f} | "
              f"{dsr:>5.3f} | {n_folds:>5} | {grade}")

    # Save
    log_dir = _root / "backend/scripts/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(events).to_csv(log_dir / "narrative_dsr_events.csv", index=False)
    print(f"\n  Events saved to: {log_dir / 'narrative_dsr_events.csv'}")


if __name__ == "__main__":
    main()
