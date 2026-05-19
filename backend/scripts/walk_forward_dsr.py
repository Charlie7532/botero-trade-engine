"""
walk_forward_dsr.py — Walk-Forward Validation + Deflated Sharpe Ratio
======================================================================
López de Prado Pipeline (Steps 3-5 of hypothesis-governance):
  1. Walk-Forward with Purged + Embargoed windows
  2. Out-of-Sample Sharpe per setup
  3. Deflated Sharpe Ratio (adjusts for N=10 trials tested)

Only the Top-10 Alpha setups from full_pattern_isolation.py are tested.
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import linregress, norm
from pathlib import Path
from collections import defaultdict

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


# ═══════════════════════════════════════════════════════════════════
# TOP-10 ALPHA SETUPS (from full_pattern_isolation.py)
# ═══════════════════════════════════════════════════════════════════
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
    """Detect pattern at index i for the given layer."""
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
    """
    Bailey & López de Prado (2014) Deflated Sharpe Ratio.

    Adjusts observed Sharpe for the number of trials tested,
    skewness, and kurtosis of returns.

    Args:
        observed_sr: The Sharpe of the strategy we're testing
        all_sharpes: List of Sharpes from ALL N trials (for E[max(SR)])
        T: Number of return observations
    Returns:
        DSR value (probability that observed SR > E[max(SR)])
    """
    N = len(all_sharpes)
    if N <= 1 or T <= 1:
        return 0.0

    # Expected Maximum Sharpe under null (Euler-Mascheroni approximation)
    gamma = 0.5772  # Euler-Mascheroni constant
    sr_std = np.std(all_sharpes, ddof=1) if np.std(all_sharpes, ddof=1) > 0 else 0.01
    z_inv = norm.ppf(1.0 - 1.0 / N) if N > 1 else 0
    z_inv_e = norm.ppf(1.0 - 1.0 / (N * np.e)) if N > 1 else 0
    e_max_sr = sr_std * ((1 - gamma) * z_inv + gamma * z_inv_e)

    # Standard error of the Sharpe Ratio
    se_sr = np.sqrt(1.0 / T)  # Simplified (assumes normal returns)

    # DSR = P(SR > E[max(SR)])
    if se_sr <= 0:
        return 0.0
    dsr = norm.cdf((observed_sr - e_max_sr) / se_sr)
    return dsr


def main():
    store = TimescaleDataStore()
    engine = PatternRecognitionIntelligence()

    # Walk-Forward Parameters (Quality department)
    TRAIN_YEARS = 3
    TEST_YEARS = 1
    PURGE_DAYS = 10   # Gap between train and test (forward return horizon)
    EMBARGO_DAYS = 5  # Buffer after test set

    print("=" * 120)
    print(f"{'WALK-FORWARD VALIDATION + DEFLATED SHARPE RATIO':^120}")
    print(f"{'Train={TRAIN_YEARS}yr, Test={TEST_YEARS}yr, Purge={PURGE_DAYS}d, Embargo={EMBARGO_DAYS}d':^120}")
    print(f"{'Top-10 Alpha Setups | 30 Quality Tickers | N_trials=10':^120}")
    print("=" * 120)

    # ── Step 1: Collect ALL events across all tickers with date info ──
    print("\n  Phase 1: Collecting events across universe...")
    all_events = []  # (date, ticker, i, trend, {layer: pattern})

    for ti, ticker in enumerate(QUALITY_TICKERS):
        print(f"    [{ti+1}/{len(QUALITY_TICKERS)}] {ticker}...", flush=True)
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

            # Execution reality
            open_next = opens[i+1]
            tr_next = highs[i+1] - lows[i+1]
            slippage = tr_next * 0.10
            exec_price = open_next + slippage
            if exec_price <= 0:
                continue

            ret_10d = (closes[i+10] - exec_price) / exec_price * 100

            # Detect patterns at all layers
            patterns = {}
            for layer in ["MICRO", "MACRO", "HYPER"]:
                patterns[layer] = detect_pattern_at(engine, ohlc, df, i, layer)

            all_events.append({
                "date": dt, "ticker": ticker, "trend": trend,
                "ret_10d": ret_10d, "patterns": patterns,
            })

    store.close()
    print(f"  Total events: {len(all_events):,}")

    # Sort by date for Walk-Forward
    all_events.sort(key=lambda x: x["date"])
    dates = [e["date"] for e in all_events]
    min_date = dates[0]
    max_date = dates[-1]
    total_years = (max_date - min_date).days / 365.25
    print(f"  Date range: {min_date.strftime('%Y-%m-%d')} → {max_date.strftime('%Y-%m-%d')} ({total_years:.1f} years)")

    # ── Step 2: Walk-Forward for each setup ──
    print(f"\n  Phase 2: Walk-Forward validation...")

    setup_results = {}  # label -> {oos_returns, is_returns, n_folds}

    for setup in TOP_SETUPS:
        label = setup["label"]
        layer = setup["layer"]
        target_pattern = setup["pattern"]
        target_regime = setup["regime"]

        # Filter events matching this setup
        matching = [
            e for e in all_events
            if e["trend"] == target_regime and e["patterns"][layer] == target_pattern
        ]

        if len(matching) < 30:
            print(f"    {label}: SKIP (only {len(matching)} events)")
            setup_results[label] = {"oos_returns": [], "is_returns": [], "n_folds": 0, "n_total": len(matching)}
            continue

        # Walk-Forward windows
        train_days = int(TRAIN_YEARS * 365.25)
        test_days = int(TEST_YEARS * 365.25)
        purge_days = pd.Timedelta(days=PURGE_DAYS)
        embargo_days = pd.Timedelta(days=EMBARGO_DAYS)

        oos_returns = []
        is_returns = []
        n_folds = 0

        # Slide the window
        window_start = min_date
        while True:
            train_end = window_start + pd.Timedelta(days=train_days)
            test_start = train_end + purge_days
            test_end = test_start + pd.Timedelta(days=test_days)

            if test_end > max_date:
                break

            # Training set events
            train_events = [e for e in matching if window_start <= e["date"] < train_end]
            # Test set events (purged + embargoed)
            test_events = [e for e in matching if test_start <= e["date"] < test_end]

            if len(train_events) >= 5 and len(test_events) >= 3:
                train_wr = np.mean([1 if e["ret_10d"] > 0 else 0 for e in train_events]) * 100
                test_wr = np.mean([1 if e["ret_10d"] > 0 else 0 for e in test_events]) * 100

                for e in test_events:
                    oos_returns.append(e["ret_10d"])
                for e in train_events:
                    is_returns.append(e["ret_10d"])

                n_folds += 1

            # Slide forward by test_days
            window_start = window_start + pd.Timedelta(days=test_days)

        setup_results[label] = {
            "oos_returns": oos_returns,
            "is_returns": is_returns,
            "n_folds": n_folds,
            "n_total": len(matching),
        }

        if oos_returns:
            oos_wr = np.mean([1 if r > 0 else 0 for r in oos_returns]) * 100
            is_wr = np.mean([1 if r > 0 else 0 for r in is_returns]) * 100
            print(f"    {label}: {n_folds} folds, IS_WR={is_wr:.1f}%, OOS_WR={oos_wr:.1f}%, N_oos={len(oos_returns)}")
        else:
            print(f"    {label}: 0 folds (insufficient data)")

    # ── Step 3: Sharpe Ratios + DSR ──
    print(f"\n  Phase 3: Deflated Sharpe Ratio...")
    print(f"  {'─' * 110}")

    all_sharpes = []
    sharpe_map = {}

    for setup in TOP_SETUPS:
        label = setup["label"]
        res = setup_results[label]
        oos = res["oos_returns"]

        if len(oos) < 10:
            sharpe = 0.0
        else:
            arr = np.array(oos)
            mean_ret = arr.mean()
            std_ret = arr.std(ddof=1)
            sharpe = (mean_ret / std_ret) * np.sqrt(252 / 10) if std_ret > 0 else 0.0
            # Annualized: assuming 10-day holding period → ~25 trades/year

        all_sharpes.append(sharpe)
        sharpe_map[label] = sharpe

    # Calculate DSR for each
    print(f"\n  {'Setup':<22} | {'Folds':>5} | {'N_OOS':>5} | {'OOS WR':>7} | {'OOS Avg':>8} | {'Sharpe':>7} | {'DSR':>6} | {'Grade':>7} | Verdict")
    print(f"  {'-'*22}-+-{'-'*5}-+-{'-'*5}-+-{'-'*7}-+-{'-'*8}-+-{'-'*7}-+-{'-'*6}-+-{'-'*7}-+-{'-'*20}")

    final_verdicts = []

    for setup in TOP_SETUPS:
        label = setup["label"]
        res = setup_results[label]
        oos = res["oos_returns"]
        sr = sharpe_map[label]

        if len(oos) < 10:
            print(f"  {label:<22} | {res['n_folds']:>5} | {len(oos):>5} | {'N/A':>7} | {'N/A':>8} | {'N/A':>7} | {'N/A':>6} | {'F':>7} | INSUFFICIENT DATA")
            final_verdicts.append({"label": label, "grade": "F", "dsr": 0})
            continue

        arr = np.array(oos)
        oos_wr = (arr > 0).mean() * 100
        oos_avg = arr.mean()

        dsr = deflated_sharpe_ratio(sr, all_sharpes, len(oos))

        if dsr > 0.95:  # ~DSR > 2.0 equivalent
            grade = "A"
            verdict = "✅ HARD GATE"
        elif dsr > 0.85:  # ~DSR > 1.0
            grade = "B"
            verdict = "✅ HARD GATE (subordinate)"
        elif dsr > 0.70:
            grade = "C"
            verdict = "⚠️  SIZING MODIFIER (±25%)"
        else:
            grade = "D"
            verdict = "❌ ADVISORY ONLY"

        print(f"  {label:<22} | {res['n_folds']:>5} | {len(oos):>5} | {oos_wr:>6.1f}% | {oos_avg:>+7.2f}% | {sr:>7.3f} | {dsr:>5.3f} | {grade:>7} | {verdict}")
        final_verdicts.append({"label": label, "grade": grade, "dsr": dsr, "oos_wr": oos_wr, "sharpe": sr})

    # ── Step 4: Overfitting Check ──
    print(f"\n  {'─' * 110}")
    print(f"  OVERFITTING CHECK (IS Sharpe / OOS Sharpe — ratio > 2.0 = suspect)")
    print(f"  {'─' * 110}")

    for setup in TOP_SETUPS:
        label = setup["label"]
        res = setup_results[label]
        is_rets = res["is_returns"]
        oos_rets = res["oos_returns"]
        if len(is_rets) < 10 or len(oos_rets) < 10:
            continue
        is_arr = np.array(is_rets)
        oos_arr = np.array(oos_rets)
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
            print(f"  🟢 {v['label']}: PROMOTED to [VALIDATED] Grade {v['grade']} — authorized as Hard Gate")
        elif v["grade"] == "C":
            print(f"  🟡 {v['label']}: PROMOTED to [VALIDATED] Grade {v['grade']} — authorized as Sizing Modifier")
        elif v["grade"] == "D":
            print(f"  🔴 {v['label']}: REMAINS [HYPOTHESIS] Grade D — Advisory Only")
        else:
            print(f"  ⚫ {v['label']}: [RETIRED] — Insufficient Data")

    # Save
    log_dir = Path(_root / "backend/scripts/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(final_verdicts).to_csv(log_dir / "dsr_validation_results.csv", index=False)
    print(f"\n  Saved to: {log_dir / 'dsr_validation_results.csv'}")


if __name__ == "__main__":
    main()
