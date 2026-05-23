#!/usr/bin/env python3
"""
Forensic Lab v19 — META-LABEL CALIBRATION: Predicted vs Real
================================================================
The meta-label filter says "this entry is good" or "this entry is bad."
But HOW GOOD? And WHERE does it fail?

This lab:
  1. Scores every entry on a continuous 0-1 scale (not binary pass/fail)
  2. Compares predicted quality vs actual outcome
  3. Finds WHERE the filter was wrong (false negatives & false positives)
  4. Discovers patterns in the errors → LEARNS → RETRAINS thresholds
  5. Builds the actual XGBoost Meta-Labeler (LdP's full pipeline)

Closed-loop: DETECT → LEARN → RETRAIN → PREVENT
"""

import os, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = ["AMZN", "MCD", "MRK", "COST", "JPM", "XOM", "MSFT", "AAPL", "SPY"]
MAX_HOLD = 120

# ── Thesis exit (same as v18) ──
def check_thesis_exit(entry_snap, current_snap, bars_held):
    if current_snap.sigma_tide > 0:
        return "THESIS_COMPLETE"
    if entry_snap.regime == "BULL" and current_snap.regime == "BEAR":
        return "REGIME_DETERIORATED"
    if current_snap.spread_tide_current > 0.5 and entry_snap.spread_tide_current < -0.5:
        return "SPREAD_RESOLVED"
    if current_snap.sigma_wave > 1.0 and entry_snap.sigma_wave < -1.0:
        return "WAVE_NORMALIZED"
    if bars_held >= MAX_HOLD:
        return "TIME_EXIT"
    return None


def compute_meta_score(snap):
    """
    Continuous 0-1 quality score based on v17 DNA features.
    Higher = more likely to be a winner.
    NOT binary — captures HOW GOOD the entry looks.
    """
    scores = []

    # Feature 1: spread_tide_current (p=0.0001, winners avg -1.195)
    # More negative = better. Scale: -2.0 → score 1.0, 0 → score 0
    s1 = np.clip(-snap.spread_tide_current / 2.0, 0, 1)
    scores.append(("spread_tc", s1, 0.35))  # weight from p-value rank

    # Feature 2: sigma_current (p=0.002, winners avg -1.744)
    # Sweet spot: -1.5 to -2.5. Too extreme (<-3) = bad. Too mild (>-1) = bad.
    if -2.5 <= snap.sigma_current <= -1.0:
        s2 = 1.0 - abs(snap.sigma_current + 1.75) / 1.25  # peak at -1.75
    else:
        s2 = 0.0
    s2 = np.clip(s2, 0, 1)
    scores.append(("sigma_current", s2, 0.25))

    # Feature 3: current_slope (p=0.007, winners avg -0.235)
    # More negative = sharper selloff = V-recovery. Scale: -0.5 → 1.0, 0 → 0
    s3 = np.clip(-snap.current_slope / 0.5, 0, 1)
    scores.append(("current_slope", s3, 0.20))

    # Feature 4: vol_up_down_ratio (p=0.015, winners avg 0.709)
    # Lower = sellers exhausted. Scale: 0.5 → 1.0, 1.0 → 0
    s4 = np.clip((1.0 - snap.vol_up_down_ratio) * 2, 0, 1)
    scores.append(("vol_ratio", s4, 0.10))

    # Feature 5: vwap_sigma_current (p=0.007, winners avg -2.116)
    # More negative = below VWAP = institutional discount
    s5 = np.clip(-snap.vwap_sigma_current / 3.0, 0, 1)
    scores.append(("vwap_sigma_c", s5, 0.10))

    # Weighted average
    total_weight = sum(w for _, _, w in scores)
    meta_score = sum(s * w for _, s, w in scores) / total_weight

    return meta_score, {name: val for name, val, _ in scores}


def generate_scored_trades(ticker, ohlc):
    """Generate ALL trades with continuous meta-score + actual outcome."""
    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)

    trades = []
    in_trade = False
    entry_snap = entry_idx = entry_price = meta_score = score_detail = None

    for idx in range(250, len(ohlc)):
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

        if in_trade:
            bars_held = idx - entry_idx
            exit_reason = check_thesis_exit(entry_snap, snap, bars_held)
            if exit_reason:
                exit_price = close[idx]
                ret = (exit_price / entry_price - 1) * 100
                actual_win = 1 if ret > 0 else 0

                trades.append({
                    "ticker": ticker,
                    "entry_time": ohlc.index[entry_idx],
                    "return_pct": ret,
                    "bars_held": bars_held,
                    "exit_reason": exit_reason,
                    "actual_win": actual_win,
                    # Meta-label prediction
                    "meta_score": meta_score,
                    "score_spread_tc": score_detail["spread_tc"],
                    "score_sigma_current": score_detail["sigma_current"],
                    "score_current_slope": score_detail["current_slope"],
                    "score_vol_ratio": score_detail["vol_ratio"],
                    "score_vwap_sigma_c": score_detail["vwap_sigma_c"],
                    # Raw features (for XGBoost)
                    "sigma_tide": entry_snap.sigma_tide,
                    "sigma_current": entry_snap.sigma_current,
                    "sigma_wave": entry_snap.sigma_wave,
                    "vwap_sigma_tide": entry_snap.vwap_sigma_tide,
                    "vwap_sigma_current": entry_snap.vwap_sigma_current,
                    "vwap_sigma_wave": entry_snap.vwap_sigma_wave,
                    "tide_slope": entry_snap.tide_slope,
                    "current_slope": entry_snap.current_slope,
                    "wave_slope": entry_snap.wave_slope,
                    "tide_accel": entry_snap.tide_accel,
                    "current_accel": entry_snap.current_accel,
                    "wave_accel": entry_snap.wave_accel,
                    "spread_tide_current": entry_snap.spread_tide_current,
                    "spread_tide_wave": entry_snap.spread_tide_wave,
                    "spread_current_wave": entry_snap.spread_current_wave,
                    "conj_wave_current": entry_snap.conj_wave_current,
                    "conj_wave_tide": entry_snap.conj_wave_tide,
                    "conj_current_tide": entry_snap.conj_current_tide,
                    "vol_up_down_ratio": entry_snap.vol_up_down_ratio,
                    "fear_level": entry_snap.fear_level,
                    "regime": entry_snap.regime,
                    "vwap_spread_tide_current": entry_snap.vwap_spread_tide_current,
                    "vwap_spread_tide_wave": entry_snap.vwap_spread_tide_wave,
                    "vwap_spread_current_wave": entry_snap.vwap_spread_current_wave,
                    "residual_std_tide": entry_snap.residual_std_tide,
                    "residual_std_current": entry_snap.residual_std_current,
                    "residual_std_wave": entry_snap.residual_std_wave,
                })
                in_trade = False
        else:
            # ALL_EXTREME entry condition
            if snap.sigma_tide < -2.0 and snap.vwap_sigma_wave < -1.5 and snap.below_all_vwaps:
                meta_score, score_detail = compute_meta_score(snap)
                in_trade = True
                entry_snap = snap
                if idx + 1 < len(ohlc):
                    entry_price = ohlc["open"].values[idx + 1]
                    entry_idx = idx + 1
                else:
                    in_trade = False

    return pd.DataFrame(trades) if trades else None


# ═══════════════════════════════════════════════════════════
# ANALYSIS 1: Calibration — Predicted vs Actual
# ═══════════════════════════════════════════════════════════

def calibration_analysis(df):
    p("1. CALIBRATION: Meta-Score vs Actual Win Rate")

    # Bucket trades by meta_score
    df["score_bucket"] = pd.cut(df["meta_score"], bins=[0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0],
                                 labels=["0-0.2", "0.2-0.35", "0.35-0.5", "0.5-0.65", "0.65-0.8", "0.8-1.0"])

    print(f"\n    {'Score Bucket':<14s} │ {'N':>4s} │ {'Actual WR':>9s} │ {'Avg Ret':>7s} │ {'PF':>5s} │ {'Interpretation':<30s}")
    print(f"    {'─'*85}")

    for bucket in ["0-0.2", "0.2-0.35", "0.35-0.5", "0.5-0.65", "0.65-0.8", "0.8-1.0"]:
        sub = df[df["score_bucket"] == bucket]
        if len(sub) < 3:
            print(f"    {bucket:<14s} │ {len(sub):>4d} │      --- │    --- │  --- │ (too few)")
            continue
        wr = sub["actual_win"].mean() * 100
        avg_ret = sub["return_pct"].mean()
        gp = sub[sub["return_pct"] > 0]["return_pct"].sum()
        gl = abs(sub[sub["return_pct"] < 0]["return_pct"].sum())
        pf = gp / max(gl, 0.001)

        if wr > 80:
            interp = "★★★ HIGH CONFIDENCE"
        elif wr > 70:
            interp = "★★ GOOD"
        elif wr > 60:
            interp = "★ ACCEPTABLE"
        elif wr > 50:
            interp = "⚠️ MARGINAL"
        else:
            interp = "❌ UNRELIABLE"

        print(f"    {bucket:<14s} │ {len(sub):>4d} │ {wr:>8.1f}% │ {avg_ret:>+6.2f}% │ {pf:>5.2f} │ {interp:<30s}")

    # Overall calibration quality
    brier = brier_score_loss(df["actual_win"], df["meta_score"])
    corr, pval = stats.pearsonr(df["meta_score"], df["actual_win"])
    print(f"\n    Brier Score: {brier:.4f} (lower = better calibrated, perfect = 0)")
    print(f"    Correlation (score→outcome): r={corr:.3f}, p={pval:.4f}")

    # Monotonicity check
    sp("MONOTONICITY — Does higher score = higher WR consistently?")
    bucket_wrs = []
    for bucket in ["0-0.2", "0.2-0.35", "0.35-0.5", "0.5-0.65", "0.65-0.8", "0.8-1.0"]:
        sub = df[df["score_bucket"] == bucket]
        if len(sub) >= 3:
            bucket_wrs.append(sub["actual_win"].mean())
    if len(bucket_wrs) >= 3:
        monotonic = all(bucket_wrs[i] <= bucket_wrs[i+1] for i in range(len(bucket_wrs)-1))
        print(f"    WRs by bucket: {[f'{w:.1%}' for w in bucket_wrs]}")
        print(f"    Monotonic: {'YES ✅ — score reliably predicts quality' if monotonic else 'NO ❌ — score needs recalibration'}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 2: Error Analysis — False Negatives & Positives
# ═══════════════════════════════════════════════════════════

def error_analysis(df):
    p("2. ERROR ANALYSIS: Where the filter is WRONG")

    # Define "filter pass" = meta_score > 0.5 (equivalent to v18 filter)
    threshold = 0.45  # We'll find optimal below
    df["filter_pass"] = df["meta_score"] >= threshold

    passed = df[df["filter_pass"]]
    rejected = df[~df["filter_pass"]]

    sp(f"FILTER THRESHOLD = {threshold}")
    print(f"    Passed: {len(passed)} trades, WR={passed['actual_win'].mean()*100:.1f}%")
    print(f"    Rejected: {len(rejected)} trades, WR={rejected['actual_win'].mean()*100:.1f}%")

    # FALSE NEGATIVES: Filter rejected, but actually won
    fn = rejected[rejected["actual_win"] == 1]
    sp("FALSE NEGATIVES — Good trades the filter KILLED")
    print(f"    {len(fn)}/{len(rejected)} rejected trades were actually WINNERS ({len(fn)/max(len(rejected),1)*100:.1f}%)")
    if len(fn) > 5:
        print(f"    Avg return of killed winners: {fn['return_pct'].mean():+.2f}%")
        print(f"    Total alpha lost by filter: {fn['return_pct'].sum():+.1f}%")
        # What features do these false negatives have?
        print(f"\n    DNA of False Negatives (what we missed):")
        for feat in ["spread_tide_current", "sigma_current", "current_slope", "vol_up_down_ratio"]:
            fn_mean = fn[feat].mean()
            winner_mean = df[df["actual_win"] == 1][feat].mean()
            print(f"      {feat:<25s}: FN={fn_mean:+.3f} vs All Winners={winner_mean:+.3f}")

    # FALSE POSITIVES: Filter passed, but actually lost
    fp = passed[passed["actual_win"] == 0]
    sp("FALSE POSITIVES — Bad trades the filter LET THROUGH")
    print(f"    {len(fp)}/{len(passed)} passed trades were actually LOSERS ({len(fp)/max(len(passed),1)*100:.1f}%)")
    if len(fp) > 5:
        print(f"    Avg loss: {fp['return_pct'].mean():+.2f}%")
        print(f"    Total damage from false positives: {fp['return_pct'].sum():+.1f}%")
        # What features do these false positives have?
        print(f"\n    DNA of False Positives (what should have been caught):")
        for feat in ["spread_tide_current", "sigma_current", "current_slope",
                      "vol_up_down_ratio", "conj_wave_tide", "wave_accel",
                      "vwap_spread_tide_current", "residual_std_wave"]:
            fp_mean = fp[feat].mean()
            loser_mean = df[df["actual_win"] == 0][feat].mean()
            diff = fp_mean - loser_mean
            print(f"      {feat:<28s}: FP={fp_mean:+.3f} vs All Losers={loser_mean:+.3f} (Δ={diff:+.3f})")

    # OPTIMAL THRESHOLD SEARCH
    sp("OPTIMAL THRESHOLD — Testing 0.2 to 0.7")
    print(f"\n    {'Threshold':>9s} │ {'Passed':>6s} │ {'WR':>5s} │ {'PF':>5s} │ {'Sharpe':>7s} │ {'Ret':>7s} │ {'Lost α':>8s}")
    print(f"    {'─'*65}")

    best_sharpe = -999
    best_thresh = 0.5
    for thresh in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        sub = df[df["meta_score"] >= thresh]
        rejected_sub = df[df["meta_score"] < thresh]
        if len(sub) < 10:
            continue
        wr = sub["actual_win"].mean() * 100
        avg_ret = sub["return_pct"].mean()
        std_ret = sub["return_pct"].std(ddof=1) if len(sub) > 1 else 1
        avg_bars = sub["bars_held"].mean()
        sharpe = (avg_ret / max(std_ret, 0.001)) * np.sqrt(252 / max(avg_bars, 1))
        gp = sub[sub["return_pct"] > 0]["return_pct"].sum()
        gl = abs(sub[sub["return_pct"] < 0]["return_pct"].sum())
        pf = gp / max(gl, 0.001)
        # Alpha lost = winners in rejected set
        lost = rejected_sub[rejected_sub["actual_win"] == 1]["return_pct"].sum()
        mark = " ← BEST" if sharpe > best_sharpe else ""
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_thresh = thresh
        print(f"    {thresh:>9.2f} │ {len(sub):>6d} │ {wr:>4.1f}% │ {pf:>5.2f} │ {sharpe:>+6.3f} │ {avg_ret:>+6.2f}% │ {lost:>+7.1f}%{mark}")

    print(f"\n    ★ Optimal threshold: {best_thresh:.2f} (Sharpe = {best_sharpe:+.3f})")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 3: XGBoost Meta-Labeler (LdP Full Pipeline)
# ═══════════════════════════════════════════════════════════

def xgboost_meta_labeler(df):
    p("3. XGBOOST META-LABELER — LdP Full Pipeline")

    feature_cols = [
        "sigma_tide", "sigma_current", "sigma_wave",
        "vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave",
        "tide_slope", "current_slope", "wave_slope",
        "tide_accel", "current_accel", "wave_accel",
        "spread_tide_current", "spread_tide_wave", "spread_current_wave",
        "conj_wave_current", "conj_wave_tide", "conj_current_tide",
        "vol_up_down_ratio", "fear_level",
        "vwap_spread_tide_current", "vwap_spread_tide_wave", "vwap_spread_current_wave",
        "residual_std_tide", "residual_std_current", "residual_std_wave",
    ]

    X = df[feature_cols].values
    y = df["actual_win"].values

    # Purged walk-forward: train on first 70%, test on last 30% (with 5% gap)
    n = len(df)
    train_end = int(n * 0.65)
    test_start = int(n * 0.70)  # 5% purge gap

    X_train, y_train = X[:train_end], y[:train_end]
    X_test, y_test = X[test_start:], y[test_start:]

    sp(f"PURGED SPLIT: Train={train_end}, Gap={test_start-train_end}, Test={n-test_start}")

    # Train XGBoost
    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Predict probabilities on test set
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred_class = (y_pred_proba >= 0.5).astype(int)

    # Metrics
    test_wr = y_test.mean() * 100
    pred_wr = y_pred_class.mean() * 100
    accuracy = (y_pred_class == y_test).mean() * 100
    brier = brier_score_loss(y_test, y_pred_proba)

    print(f"    Test set actual WR: {test_wr:.1f}%")
    print(f"    XGBoost predicted WR: {pred_wr:.1f}%")
    print(f"    Accuracy: {accuracy:.1f}%")
    print(f"    Brier Score: {brier:.4f}")

    # Feature importance
    sp("FEATURE IMPORTANCE — What XGBoost learned")
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]

    print(f"\n    {'Rank':>4s} │ {'Feature':<28s} │ {'Importance':>10s} │ {'Cum%':>5s}")
    print(f"    {'─'*55}")
    cum = 0
    for rank, idx in enumerate(sorted_idx[:15], 1):
        imp = importances[idx]
        cum += imp
        print(f"    {rank:>4d} │ {feature_cols[idx]:<28s} │ {imp:>10.4f} │ {cum*100:>4.1f}%")

    # Calibration by probability bucket
    sp("XGB CALIBRATION — Predicted P(win) vs Actual WR")
    prob_buckets = pd.cut(y_pred_proba, bins=[0, 0.3, 0.5, 0.6, 0.7, 0.8, 1.0])
    test_df = pd.DataFrame({"prob": y_pred_proba, "actual": y_test, "bucket": prob_buckets})

    print(f"\n    {'P(win) Bucket':<16s} │ {'N':>4s} │ {'Actual WR':>9s} │ {'Avg P(win)':>10s} │ {'Calibration':<15s}")
    print(f"    {'─'*65}")

    for bucket in sorted(test_df["bucket"].unique()):
        sub = test_df[test_df["bucket"] == bucket]
        if len(sub) < 3:
            continue
        actual_wr = sub["actual"].mean() * 100
        avg_pred = sub["prob"].mean() * 100
        diff = actual_wr - avg_pred
        cal = "Overconfident" if diff < -5 else "Underconfident" if diff > 5 else "Well calibrated"
        print(f"    {str(bucket):<16s} │ {len(sub):>4d} │ {actual_wr:>8.1f}% │ {avg_pred:>9.1f}% │ {cal:<15s}")

    # Compare: rule-based vs XGBoost
    sp("COMPARISON: Rule-Based Score vs XGBoost")
    rule_corr, rule_p = stats.pearsonr(df.iloc[test_start:]["meta_score"].values, y_test)
    xgb_corr, xgb_p = stats.pearsonr(y_pred_proba, y_test)
    print(f"    Rule-based correlation with outcome: r={rule_corr:.3f} (p={rule_p:.4f})")
    print(f"    XGBoost correlation with outcome:    r={xgb_corr:.3f} (p={xgb_p:.4f})")
    winner = "XGBoost" if abs(xgb_corr) > abs(rule_corr) else "Rule-based"
    print(f"    → {winner} is the better predictor")

    return model, feature_cols


# ═══════════════════════════════════════════════════════════
# ANALYSIS 4: Per-Ticker Profiles — Adaptive Thresholds
# ═══════════════════════════════════════════════════════════

def per_ticker_profiles(df):
    p("4. PER-TICKER PROFILES — What features matter WHERE")

    feature_cols = ["spread_tide_current", "sigma_current", "current_slope",
                    "vol_up_down_ratio", "vwap_sigma_current", "conj_wave_tide",
                    "tide_accel", "wave_accel"]

    print(f"\n    {'Ticker':<8s} │ {'N':>4s} │ {'WR':>5s} │ {'Top Feature':<25s} │ {'r':>6s} │ {'p':>7s} │ {'2nd Feature':<25s} │ {'r':>6s}")
    print(f"    {'─'*105}")

    for ticker in sorted(df["ticker"].unique()):
        t = df[df["ticker"] == ticker]
        if len(t) < 15:
            continue
        wr = t["actual_win"].mean() * 100

        # Find strongest predictor per ticker
        best = []
        for feat in feature_cols:
            try:
                r, pv = stats.pearsonr(t[feat], t["actual_win"])
                best.append((feat, r, pv))
            except:
                pass
        best.sort(key=lambda x: abs(x[1]), reverse=True)
        if len(best) >= 2:
            f1, r1, p1 = best[0]
            f2, r2, p2 = best[1]
            print(f"    {ticker:<8s} │ {len(t):>4d} │ {wr:>4.1f}% │ {f1:<25s} │ {r1:>+5.3f} │ {p1:>6.4f} │ {f2:<25s} │ {r2:>+5.3f}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v19 — META-LABEL CALIBRATION")
    print("  Predicted vs Real. Where the filter fails. What XGBoost learns.")

    store = TimescaleDataStore()
    all_dfs = []

    for ticker in TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 300:
            continue
        print(f"  {ticker}...", end=" ", flush=True)
        df = generate_scored_trades(ticker, ohlc)
        if df is not None and len(df) > 0:
            all_dfs.append(df)
            print(f"{len(df)} trades, meta_score range [{df['meta_score'].min():.2f}, {df['meta_score'].max():.2f}]")
        else:
            print("0 trades")

    store.close()

    if not all_dfs:
        print("No trades!")
        sys.exit(1)

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\n  Total: {len(combined)} trades, WR={combined['actual_win'].mean()*100:.1f}%")

    calibration_analysis(combined)
    error_analysis(combined)
    xgboost_meta_labeler(combined)
    per_ticker_profiles(combined)

    p("v19 — META-LABEL CALIBRATION COMPLETE")
    print("  Detect → Learn → Retrain → Prevent. The loop is closed.")
