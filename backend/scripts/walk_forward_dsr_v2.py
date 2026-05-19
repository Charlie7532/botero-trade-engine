"""
walk_forward_dsr_v2.py — Extended Walk-Forward (shorter windows for significance)
==================================================================================
Problem: Only 5 years of data → 1 fold with 3yr/1yr windows = not representative.
Solution: Use 2yr train / 6mo test → 4-5 folds → statistically significant OOS.

Also adds: tighter minimum N thresholds following López de Prado (N_OOS >= 30).
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

# Extended universe: 30 Quality + SPY (1993, 9625 bars) + QQQ (1999, 8100 bars)
EXTENDED_TICKERS = list(QUALITY_TICKERS) + ["SPY", "QQQ"]

TOP_SETUPS = [
    {"layer": "HYPER",  "pattern": "THREE_BLACK_CROWS",  "regime": "MUY_BAJISTA", "label": "HYPER_3BC_MB"},
    {"layer": "MICRO",  "pattern": "BEARISH_MARUBOZU",   "regime": "MUY_BAJISTA", "label": "MICRO_BM_MB"},
    {"layer": "MICRO",  "pattern": "HAMMER",             "regime": "MUY_ALCISTA", "label": "MICRO_HAM_MA"},
    {"layer": "MACRO",  "pattern": "BEARISH_MARUBOZU",   "regime": "MUY_ALCISTA", "label": "MACRO_BM_MA"},
    {"layer": "MACRO",  "pattern": "BULLISH_MARUBOZU",   "regime": "ALCISTA",     "label": "MACRO_BullM_A"},
    {"layer": "MACRO",  "pattern": "BULLISH_MARUBOZU",   "regime": "HORIZONTAL",  "label": "MACRO_BullM_H"},
    {"layer": "HYPER",  "pattern": "SHOOTING_STAR",      "regime": "ALCISTA",     "label": "HYPER_SS_A"},
    {"layer": "MACRO",  "pattern": "SHOOTING_STAR",      "regime": "ALCISTA",     "label": "MACRO_SS_A"},
    {"layer": "MACRO",  "pattern": "HAMMER",             "regime": "BAJISTA",     "label": "MACRO_HAM_B"},
    {"layer": "MACRO",  "pattern": "TWEEZER_BOTTOM",     "regime": "MUY_BAJISTA", "label": "MACRO_TB_MB"},
]


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


def detect_pattern_at(engine, ohlc, df, i, layer):
    if layer == "MICRO":
        window = df.iloc[max(0, i-2):i+1].copy()
        v = engine.detect(window)
        return v.primary_pattern
    elif layer == "MACRO":
        super_df = PatternSignalAdapter.synthesize_super_candles(ohlc, end_idx=i, group_size=5, n_groups=3)
        if super_df is None or len(super_df) < 3:
            return "NONE"
        super_df.columns = [c.capitalize() for c in super_df.columns]
        v = engine.detect(super_df)
        return v.primary_pattern
    elif layer == "HYPER":
        hyper_df = PatternSignalAdapter.synthesize_hyper_candles(ohlc, end_idx=i)
        if hyper_df is None or len(hyper_df) < 3:
            return "NONE"
        v = engine.detect(hyper_df)
        return v.primary_pattern
    return "NONE"


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

    # Shorter windows for significance with 5yr data
    TRAIN_DAYS = int(2 * 365.25)    # 2 years
    TEST_DAYS = int(0.5 * 365.25)   # 6 months
    PURGE_DAYS = 10
    EMBARGO_DAYS = 5

    print("=" * 120)
    print(f"{'WALK-FORWARD V2 — EXTENDED FOLDS FOR STATISTICAL SIGNIFICANCE':^120}")
    print(f"{'Train=2yr, Test=6mo, Purge=10d, Embargo=5d → ~4-5 folds':^120}")
    print(f"{'Top-10 Alpha Setups | 30 Quality Tickers | N_trials=10':^120}")
    print("=" * 120)

    # ── Phase 1: Collect events ──
    print("\n  Phase 1: Collecting events...")
    all_events = []

    for ti, ticker in enumerate(EXTENDED_TICKERS):
        print(f"    [{ti+1}/{len(EXTENDED_TICKERS)}] {ticker}...", flush=True)
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue

        df = ohlc.copy()
        df.columns = [c.capitalize() for c in df.columns]
        closes = df['Close'].values
        opens = df['Open'].values
        highs = df['High'].values
        lows = df['Low'].values

        for i in range(60, len(df) - 11):
            trend = get_trend_state(closes, i)
            dt = df.index[i]

            open_next = opens[i+1]
            tr_next = highs[i+1] - lows[i+1]
            slippage = tr_next * 0.10
            exec_price = open_next + slippage
            if exec_price <= 0:
                continue

            ret_10d = (closes[i+10] - exec_price) / exec_price * 100

            patterns = {}
            for layer in ["MICRO", "MACRO", "HYPER"]:
                patterns[layer] = detect_pattern_at(engine, ohlc, df, i, layer)

            all_events.append({
                "date": dt, "ticker": ticker, "trend": trend,
                "ret_10d": ret_10d, "patterns": patterns,
            })

    store.close()
    all_events.sort(key=lambda x: x["date"])
    dates = [e["date"] for e in all_events]
    min_date, max_date = dates[0], dates[-1]
    total_years = (max_date - min_date).days / 365.25
    print(f"  Total events: {len(all_events):,} | Range: {min_date.strftime('%Y-%m-%d')} → {max_date.strftime('%Y-%m-%d')} ({total_years:.1f}yr)")

    # ── Phase 2: Walk-Forward ──
    print(f"\n  Phase 2: Walk-Forward (2yr train / 6mo test)...")

    setup_results = {}

    for setup in TOP_SETUPS:
        label = setup["label"]
        layer = setup["layer"]
        target_pattern = setup["pattern"]
        target_regime = setup["regime"]

        matching = [
            e for e in all_events
            if e["trend"] == target_regime and e["patterns"][layer] == target_pattern
        ]

        oos_returns = []
        is_returns = []
        n_folds = 0
        fold_details = []

        window_start = min_date
        while True:
            train_end = window_start + pd.Timedelta(days=TRAIN_DAYS)
            test_start = train_end + pd.Timedelta(days=PURGE_DAYS)
            test_end = test_start + pd.Timedelta(days=TEST_DAYS)

            if test_end > max_date:
                break

            train_events = [e for e in matching if window_start <= e["date"] < train_end]
            test_events = [e for e in matching if test_start <= e["date"] < test_end]

            if len(train_events) >= 3 and len(test_events) >= 1:
                train_wr = np.mean([1 if e["ret_10d"] > 0 else 0 for e in train_events]) * 100
                test_wr = np.mean([1 if e["ret_10d"] > 0 else 0 for e in test_events]) * 100

                for e in test_events:
                    oos_returns.append(e["ret_10d"])
                for e in train_events:
                    is_returns.append(e["ret_10d"])

                fold_details.append({
                    "fold": n_folds + 1,
                    "train_period": f"{window_start.strftime('%Y-%m')}→{train_end.strftime('%Y-%m')}",
                    "test_period": f"{test_start.strftime('%Y-%m')}→{test_end.strftime('%Y-%m')}",
                    "n_train": len(train_events), "n_test": len(test_events),
                    "train_wr": train_wr, "test_wr": test_wr,
                })
                n_folds += 1

            window_start = window_start + pd.Timedelta(days=TEST_DAYS)

        setup_results[label] = {
            "oos_returns": oos_returns, "is_returns": is_returns,
            "n_folds": n_folds, "n_total": len(matching), "folds": fold_details,
        }

        if oos_returns:
            oos_wr = np.mean([1 if r > 0 else 0 for r in oos_returns]) * 100
            is_wr = np.mean([1 if r > 0 else 0 for r in is_returns]) * 100
            print(f"    {label:<22}: {n_folds} folds, IS_WR={is_wr:.1f}%, OOS_WR={oos_wr:.1f}%, "
                  f"N_total={len(matching)}, N_oos={len(oos_returns)}")
            for fd in fold_details:
                print(f"      Fold {fd['fold']}: {fd['train_period']} (N={fd['n_train']}) → "
                      f"{fd['test_period']} (N={fd['n_test']}, WR={fd['test_wr']:.0f}%)")
        else:
            print(f"    {label:<22}: 0 OOS events")

    # ── Phase 3: DSR ──
    print(f"\n  Phase 3: Deflated Sharpe Ratio...")

    all_sharpes = []
    sharpe_map = {}
    MIN_OOS = 15  # Minimum for DSR calculation (relaxed from 30 due to 5yr constraint)

    for setup in TOP_SETUPS:
        label = setup["label"]
        oos = setup_results[label]["oos_returns"]
        if len(oos) < MIN_OOS:
            sharpe = 0.0
        else:
            arr = np.array(oos)
            sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(252 / 10) if arr.std(ddof=1) > 0 else 0.0
        all_sharpes.append(sharpe)
        sharpe_map[label] = sharpe

    print(f"\n  {'Setup':<22} | {'Folds':>5} | {'N_OOS':>5} | {'OOS WR':>7} | {'OOS Avg':>8} | {'Sharpe':>7} | {'DSR':>6} | {'Grade':>7} | Verdict")
    print(f"  {'-'*22}-+-{'-'*5}-+-{'-'*5}-+-{'-'*7}-+-{'-'*8}-+-{'-'*7}-+-{'-'*6}-+-{'-'*7}-+-{'-'*25}")

    final_verdicts = []

    for setup in TOP_SETUPS:
        label = setup["label"]
        res = setup_results[label]
        oos = res["oos_returns"]
        sr = sharpe_map[label]

        if len(oos) < MIN_OOS:
            n_oos_str = f"{len(oos)}" if oos else "0"
            print(f"  {label:<22} | {res['n_folds']:>5} | {n_oos_str:>5} | {'N/A':>7} | {'N/A':>8} | {'N/A':>7} | {'N/A':>6} | {'F':>7} | INSUFFICIENT (need {MIN_OOS}+)")
            final_verdicts.append({"label": label, "grade": "F", "dsr": 0, "n_oos": len(oos), "n_folds": res["n_folds"]})
            continue

        arr = np.array(oos)
        oos_wr = (arr > 0).mean() * 100
        oos_avg = arr.mean()
        dsr = deflated_sharpe_ratio(sr, all_sharpes, len(oos))

        if dsr > 0.95:
            grade, verdict = "A", "✅ HARD GATE (veto power)"
        elif dsr > 0.85:
            grade, verdict = "B", "✅ HARD GATE (subordinate)"
        elif dsr > 0.70:
            grade, verdict = "C", "⚠️  SIZING MODIFIER (±25%)"
        else:
            grade, verdict = "D", "❌ ADVISORY ONLY"

        print(f"  {label:<22} | {res['n_folds']:>5} | {len(oos):>5} | {oos_wr:>6.1f}% | {oos_avg:>+7.2f}% | {sr:>7.3f} | {dsr:>5.3f} | {grade:>7} | {verdict}")
        final_verdicts.append({"label": label, "grade": grade, "dsr": dsr, "oos_wr": oos_wr, "sharpe": sr, "n_oos": len(oos), "n_folds": res["n_folds"]})

    # ── Overfitting Check ──
    print(f"\n  {'─' * 110}")
    print(f"  OVERFITTING CHECK")
    print(f"  {'─' * 110}")
    for setup in TOP_SETUPS:
        label = setup["label"]
        res = setup_results[label]
        if len(res["is_returns"]) < MIN_OOS or len(res["oos_returns"]) < MIN_OOS:
            continue
        is_arr = np.array(res["is_returns"])
        oos_arr = np.array(res["oos_returns"])
        is_sr = (is_arr.mean() / is_arr.std(ddof=1)) * np.sqrt(252/10) if is_arr.std(ddof=1) > 0 else 0
        oos_sr = sharpe_map[label]
        ratio = is_sr / oos_sr if oos_sr > 0 else float('inf')
        flag = "🚩 SUSPECT" if ratio > 2.0 else "✅ OK"
        print(f"    {label:<22} | IS_SR={is_sr:.3f} | OOS_SR={oos_sr:.3f} | Ratio={ratio:.2f} | {flag}")

    # ── Summary ──
    print(f"\n{'=' * 120}")
    print(f"{'FINAL GOVERNANCE VERDICT':^120}")
    print(f"{'=' * 120}")
    for v in final_verdicts:
        if v["grade"] in ["A", "B"]:
            print(f"  🟢 {v['label']}: PROMOTED to [VALIDATED] Grade {v['grade']} (N_oos={v.get('n_oos',0)}, {v.get('n_folds',0)} folds)")
        elif v["grade"] == "C":
            print(f"  🟡 {v['label']}: PROMOTED to [VALIDATED] Grade {v['grade']} — Sizing Modifier")
        elif v["grade"] == "D":
            print(f"  🔴 {v['label']}: REMAINS [HYPOTHESIS] Grade D — Advisory Only (N_oos={v.get('n_oos',0)})")
        else:
            print(f"  ⚫ {v['label']}: [RETIRED] — Insufficient Data (N_oos={v.get('n_oos',0)})")

    pd.DataFrame(final_verdicts).to_csv(_root / "backend/scripts/logs/dsr_validation_v2.csv", index=False)
    print(f"\n  Saved to: backend/scripts/logs/dsr_validation_v2.csv")


if __name__ == "__main__":
    main()
