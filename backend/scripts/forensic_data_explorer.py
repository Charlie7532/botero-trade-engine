#!/usr/bin/env python3
"""
Forensic Data Explorer — Extract, Flatten, and Analyze forensic labels from Neon.
Produces a full statistical analysis of each indicator's snapshot features
vs. forward-looking outcomes (win/loss, horizons, classifications).

Usage:
    PYTHONPATH=. backend/.venv/bin/python backend/scripts/forensic_data_explorer.py
"""

import os
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras

# ════════════════════════════════════════════════════════════
# 1. EXTRACT: Pull all forensic labels from Neon
# ════════════════════════════════════════════════════════════

def extract_labels(table_name: str) -> pd.DataFrame:
    """Extract all forensic labels from a given table, flatten JSONB."""
    pg_url = os.environ.get("POSTGRES_URL", "")
    if not pg_url:
        print("ERROR: POSTGRES_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT * FROM engine.{table_name}")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"  No data in engine.{table_name}")
        return pd.DataFrame()

    records = []
    for row in rows:
        flat = {
            "ticker": row["ticker"],
            "signal_name": row["signal_name"],
            "signal_direction": row["signal_direction"],
            "signal_confidence": row["signal_confidence"],
            "signal_time": row["signal_time"],
            "signal_price": row["signal_price"],
            "classification": row["classification"],
            "failure_diagnosis": row["failure_diagnosis"],
            "foreseeability": row["foreseeability"],
        }

        # Flatten snapshot JSONB
        snap = row["snapshot"]
        if isinstance(snap, str):
            snap = json.loads(snap)
        if snap:
            for k, v in snap.items():
                flat[f"snap_{k}"] = v

        # Flatten horizons JSONB
        horizons = row["horizons"]
        if isinstance(horizons, str):
            horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
                for metric, metric_val in h_val.items():
                    flat[f"h{h_key}_{metric}"] = metric_val

        records.append(flat)

    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    return df


def print_header(title: str):
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_subheader(title: str):
    print()
    print(f"  ── {title} ──")


# ════════════════════════════════════════════════════════════
# 2. ANALYSIS FUNCTIONS
# ════════════════════════════════════════════════════════════

def analyze_entry_signal(df: pd.DataFrame, ticker: str, signal: str):
    """Deep statistical analysis for a specific entry signal × ticker."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal)].copy()
    n = len(subset)
    if n < 10:
        print(f"    ⚠ Only {n} observations — insufficient for statistical analysis")
        return

    # Binary win label: GOLDEN_RUN or SOLID_MOVE = win
    subset["is_win"] = subset["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    # Binary for horizons
    for h in [3, 5, 10, 20, 40]:
        col = f"h{h}_return_pct"
        if col in subset.columns:
            subset[f"win_h{h}"] = (subset[col] > 0).astype(int)

    print_subheader(f"ENTRY: {signal} × {ticker} ({n} signals)")

    # ── 2a. Feature Distributions: Wins vs Losses ──
    features = [
        "snap_sigma_tide", "snap_sigma_wave", "snap_tide_slope", "snap_wave_slope",
        "snap_tide_accel", "snap_rvol", "snap_vol_up_down_ratio",
        "snap_slope_conjugation", "snap_fear_level",
    ]
    if "snap_rsi_value" in subset.columns:
        features.append("snap_rsi_value")
    if "snap_kalman_velocity" in subset.columns:
        features.append("snap_kalman_velocity")

    available = [f for f in features if f in subset.columns]

    print()
    print(f"    {'Feature':<28s} {'Win μ':>8s} {'Win σ':>8s} {'Loss μ':>8s} {'Loss σ':>8s} {'Δμ':>8s} {'t-stat':>8s} {'p-val':>8s}")
    print(f"    {'─' * 28} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")

    from scipy import stats

    for feat in available:
        wins = subset.loc[subset["is_win"] == 1, feat].dropna()
        losses = subset.loc[subset["is_win"] == 0, feat].dropna()
        if len(wins) < 5 or len(losses) < 5:
            continue
        # Convert booleans to numeric
        wins = pd.to_numeric(wins, errors="coerce").dropna()
        losses = pd.to_numeric(losses, errors="coerce").dropna()
        if len(wins) < 5 or len(losses) < 5:
            continue

        w_mean, w_std = wins.mean(), wins.std()
        l_mean, l_std = losses.mean(), losses.std()
        delta = w_mean - l_mean

        t_stat, p_val = stats.ttest_ind(wins, losses, equal_var=False)

        sig_marker = " ***" if p_val < 0.01 else " **" if p_val < 0.05 else " *" if p_val < 0.10 else ""
        feat_short = feat.replace("snap_", "")
        print(f"    {feat_short:<28s} {w_mean:>8.3f} {w_std:>8.3f} {l_mean:>8.3f} {l_std:>8.3f} {delta:>+8.3f} {t_stat:>8.2f} {p_val:>8.4f}{sig_marker}")

    # ── 2b. Win Rate by sigma_position Buckets ──
    for sigma_col, sigma_name in [("snap_sigma_tide", "σ_tide (macro)"), ("snap_sigma_wave", "σ_wave (cycle)")]:
        if sigma_col not in subset.columns:
            continue
        s = pd.to_numeric(subset[sigma_col], errors="coerce")
        bins = [-999, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 999]
        labels_b = ["<-2σ", "-2→-1.5σ", "-1.5→-1σ", "-1→-0.5σ", "-0.5→0σ", "0→0.5σ", "0.5→1σ", "1→1.5σ", "1.5→2σ", ">2σ"]
        subset["_sigma_bucket"] = pd.cut(s, bins=bins, labels=labels_b)

        print()
        print(f"    Win Rate by {sigma_name} Bucket:")
        grp = subset.groupby("_sigma_bucket", observed=True)["is_win"]
        for bucket_name in labels_b:
            if bucket_name in grp.groups:
                g = grp.get_group(bucket_name)
                wr = g.mean() * 100
                cnt = len(g)
                bar = "█" * int(wr / 5)
                print(f"      {bucket_name:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")
        subset.drop(columns=["_sigma_bucket"], inplace=True)

    # ── 2c. Win Rate by Fear Level ──
    if "snap_fear_level" in subset.columns:
        print()
        print(f"    Win Rate by Fear Level:")
        fear_map = {0: "GREED", 1: "CONFIDENCE", 2: "NEUTRAL", 3: "ANXIETY", 4: "FEAR", 5: "PANIC"}
        for fl in sorted(subset["snap_fear_level"].dropna().unique()):
            mask = subset["snap_fear_level"] == fl
            wr = subset.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            label = fear_map.get(int(fl), f"L{int(fl)}")
            bar = "█" * int(wr / 5)
            print(f"      {label:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")

    # ── 2d. Slope Conjugation Analysis ──
    if "snap_slope_conjugation" in subset.columns:
        sc = pd.to_numeric(subset["snap_slope_conjugation"], errors="coerce")
        bins = [-999, -0.3, -0.1, 0.1, 0.3, 999]
        labels_sc = ["Strong↓", "Mild↓", "Flat", "Mild↑", "Strong↑"]
        subset["_conj_bucket"] = pd.cut(sc, bins=bins, labels=labels_sc)
        print()
        print(f"    Win Rate by Slope Conjugation (wave - tide):")
        grp = subset.groupby("_conj_bucket", observed=True)["is_win"]
        for bucket_name in labels_sc:
            if bucket_name in grp.groups:
                g = grp.get_group(bucket_name)
                wr = g.mean() * 100
                cnt = len(g)
                bar = "█" * int(wr / 5)
                print(f"      {bucket_name:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")
        subset.drop(columns=["_conj_bucket"], inplace=True)

    # ── 2e. RSI Bucket Analysis (if present) ──
    if "snap_rsi_value" in subset.columns:
        rsi = pd.to_numeric(subset["snap_rsi_value"], errors="coerce")
        bins = [0, 20, 30, 40, 50, 60, 70, 80, 100]
        labels_rsi = ["<20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", ">80"]
        subset["_rsi_bucket"] = pd.cut(rsi, bins=bins, labels=labels_rsi)
        print()
        print(f"    Win Rate by RSI Bucket:")
        grp = subset.groupby("_rsi_bucket", observed=True)["is_win"]
        for bucket_name in labels_rsi:
            if bucket_name in grp.groups:
                g = grp.get_group(bucket_name)
                wr = g.mean() * 100
                cnt = len(g)
                bar = "█" * int(wr / 5)
                print(f"      {bucket_name:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")
        subset.drop(columns=["_rsi_bucket"], inplace=True)

    # ── 2f. Kalman + Wyckoff ──
    if "snap_kalman_velocity" in subset.columns:
        kv = pd.to_numeric(subset["snap_kalman_velocity"], errors="coerce")
        bins = [-999, -0.01, -0.001, 0.001, 0.01, 999]
        labels_k = ["Strong↓", "Weak↓", "Flat", "Weak↑", "Strong↑"]
        subset["_kalman_bucket"] = pd.cut(kv, bins=bins, labels=labels_k)
        print()
        print(f"    Win Rate by Kalman Velocity:")
        grp = subset.groupby("_kalman_bucket", observed=True)["is_win"]
        for bucket_name in labels_k:
            if bucket_name in grp.groups:
                g = grp.get_group(bucket_name)
                wr = g.mean() * 100
                cnt = len(g)
                bar = "█" * int(wr / 5)
                print(f"      {bucket_name:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")
        subset.drop(columns=["_kalman_bucket"], inplace=True)

    if "snap_wyckoff_state" in subset.columns:
        print()
        print(f"    Win Rate by Wyckoff State:")
        for state in sorted(subset["snap_wyckoff_state"].dropna().unique()):
            mask = subset["snap_wyckoff_state"] == state
            wr = subset.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            print(f"      {str(state):>16s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")

    # ── 2g. RVOL Analysis ──
    if "snap_rvol" in subset.columns:
        rvol = pd.to_numeric(subset["snap_rvol"], errors="coerce")
        bins = [0, 0.5, 0.8, 1.0, 1.3, 2.0, 999]
        labels_rv = ["<0.5x", "0.5-0.8x", "0.8-1.0x", "1.0-1.3x", "1.3-2.0x", ">2.0x"]
        subset["_rvol_bucket"] = pd.cut(rvol, bins=bins, labels=labels_rv)
        print()
        print(f"    Win Rate by Relative Volume:")
        grp = subset.groupby("_rvol_bucket", observed=True)["is_win"]
        for bucket_name in labels_rv:
            if bucket_name in grp.groups:
                g = grp.get_group(bucket_name)
                wr = g.mean() * 100
                cnt = len(g)
                bar = "█" * int(wr / 5)
                print(f"      {bucket_name:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")
        subset.drop(columns=["_rvol_bucket"], inplace=True)

    # ── 2h. Horizon Win Rate Curves ──
    print()
    print(f"    Win Rate Curves by Horizon:")
    for h in [3, 5, 10, 20, 40]:
        col = f"h{h}_return_pct"
        if col in subset.columns:
            returns = pd.to_numeric(subset[col], errors="coerce").dropna()
            wr = (returns > 0).mean() * 100
            avg_ret = returns.mean()
            med_ret = returns.median()
            print(f"      H={h:2d} │ WR={wr:5.1f}%  AvgRet={avg_ret:+6.2f}%  MedRet={med_ret:+6.2f}%")

    # ── 2i. MFE/MAE Analysis ──
    print()
    print(f"    MFE/MAE Analysis by Horizon:")
    for h in [3, 5, 10, 20, 40]:
        mfe_col = f"h{h}_max_up_pct"
        mae_col = f"h{h}_max_down_pct"
        if mfe_col in subset.columns and mae_col in subset.columns:
            mfe = pd.to_numeric(subset[mfe_col], errors="coerce").dropna()
            mae = pd.to_numeric(subset[mae_col], errors="coerce").dropna()
            edge = mfe.mean() / abs(mae.mean()) if abs(mae.mean()) > 0.001 else float("nan")
            print(f"      H={h:2d} │ AvgMFE={mfe.mean():+6.2f}%  AvgMAE={mae.mean():+6.2f}%  Edge={edge:.2f}")

    # ── 2j. COMBINED CONDITION ANALYSIS ──
    # What combination of conditions predicts wins best?
    print()
    print(f"    Combined Condition Win Rates:")

    conditions = []
    # sigma_wave below -1 (deep oversold)
    if "snap_sigma_wave" in subset.columns:
        mask = pd.to_numeric(subset["snap_sigma_wave"], errors="coerce") < -1.0
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("σ_wave < -1.0", mask.sum(), wr))

    # sigma_tide below -1 (macro oversold)
    if "snap_sigma_tide" in subset.columns:
        mask = pd.to_numeric(subset["snap_sigma_tide"], errors="coerce") < -1.0
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("σ_tide < -1.0", mask.sum(), wr))

    # RSI < 30 (classic oversold)
    if "snap_rsi_value" in subset.columns:
        mask = pd.to_numeric(subset["snap_rsi_value"], errors="coerce") < 30
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("RSI < 30", mask.sum(), wr))

    # Fear >= 3 (Anxiety+)
    if "snap_fear_level" in subset.columns:
        mask = pd.to_numeric(subset["snap_fear_level"], errors="coerce") >= 3
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("Fear ≥ ANXIETY", mask.sum(), wr))

    # wave_slope turning up
    if "snap_wave_slope" in subset.columns and "snap_wave_flip" in subset.columns:
        mask_slope = pd.to_numeric(subset["snap_wave_slope"], errors="coerce") > 0
        mask_flip = subset["snap_wave_flip"] == True
        mask = mask_slope & mask_flip
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("wave↑ + flip", mask.sum(), wr))

    # Combined: σ_wave < -1 AND Fear ≥ 3
    if "snap_sigma_wave" in subset.columns and "snap_fear_level" in subset.columns:
        mask = (pd.to_numeric(subset["snap_sigma_wave"], errors="coerce") < -1.0) & \
               (pd.to_numeric(subset["snap_fear_level"], errors="coerce") >= 3)
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("σ_wave<-1 + Fear≥ANXIETY", mask.sum(), wr))

    # Combined: σ_wave < -1 AND wave_slope > 0 (reversal starting)
    if "snap_sigma_wave" in subset.columns and "snap_wave_slope" in subset.columns:
        mask = (pd.to_numeric(subset["snap_sigma_wave"], errors="coerce") < -1.0) & \
               (pd.to_numeric(subset["snap_wave_slope"], errors="coerce") > 0)
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("σ_wave<-1 + wave↑", mask.sum(), wr))

    # RVOL > 1.3 (high conviction)
    if "snap_rvol" in subset.columns:
        mask = pd.to_numeric(subset["snap_rvol"], errors="coerce") > 1.3
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("RVOL > 1.3x", mask.sum(), wr))

    # Below VWAP
    if "snap_below_vwap" in subset.columns:
        mask = subset["snap_below_vwap"] == True
        if mask.sum() >= 5:
            wr = subset.loc[mask, "is_win"].mean() * 100
            conditions.append(("Below VWAP", mask.sum(), wr))

    # Sort by win rate descending
    conditions.sort(key=lambda x: x[2], reverse=True)
    for cond, cnt, wr in conditions:
        bar = "█" * int(wr / 5)
        marker = " ← EDGE" if wr > 60 else ""
        print(f"      {cond:<30s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

    # ── 2k. CORRELATION MATRIX ──
    numeric_feats = [f for f in available if f in subset.columns]
    numeric_df = subset[numeric_feats + ["is_win"]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(numeric_df) >= 20:
        corr = numeric_df.corr()["is_win"].drop("is_win").sort_values(key=abs, ascending=False)
        print()
        print(f"    Feature Correlation with Win (top predictors):")
        for feat, c in corr.head(8).items():
            feat_short = feat.replace("snap_", "")
            sig = "***" if abs(c) > 0.15 else "**" if abs(c) > 0.10 else "*" if abs(c) > 0.05 else ""
            print(f"      {feat_short:<28s} r={c:+.4f} {sig}")


def analyze_exit_signal(df: pd.DataFrame, ticker: str, signal: str):
    """Deep statistical analysis for a specific exit signal × ticker."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal)].copy()
    n = len(subset)
    if n < 5:
        print(f"    ⚠ Only {n} observations — insufficient for statistical analysis")
        return

    # Binary: was the exit helpful?
    subset["is_save"] = subset["classification"].isin(["SAVED_US", "GOOD_WARNING"]).astype(int)

    print_subheader(f"EXIT: {signal} × {ticker} ({n} signals)")

    features = [
        "snap_sigma_tide", "snap_sigma_wave", "snap_tide_slope", "snap_wave_slope",
        "snap_tide_accel", "snap_rvol", "snap_vol_up_down_ratio",
        "snap_slope_conjugation", "snap_fear_level",
    ]
    if "snap_rsi_value" in subset.columns:
        features.append("snap_rsi_value")
    if "snap_kalman_velocity" in subset.columns:
        features.append("snap_kalman_velocity")

    available = [f for f in features if f in subset.columns]

    from scipy import stats

    print()
    print(f"    {'Feature':<28s} {'Save μ':>8s} {'Save σ':>8s} {'Fail μ':>8s} {'Fail σ':>8s} {'Δμ':>8s} {'t-stat':>8s} {'p-val':>8s}")
    print(f"    {'─' * 28} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")

    for feat in available:
        saves = subset.loc[subset["is_save"] == 1, feat].dropna()
        fails = subset.loc[subset["is_save"] == 0, feat].dropna()
        saves = pd.to_numeric(saves, errors="coerce").dropna()
        fails = pd.to_numeric(fails, errors="coerce").dropna()
        if len(saves) < 3 or len(fails) < 3:
            continue

        s_mean, s_std = saves.mean(), saves.std()
        f_mean, f_std = fails.mean(), fails.std()
        delta = s_mean - f_mean

        t_stat, p_val = stats.ttest_ind(saves, fails, equal_var=False)
        sig_marker = " ***" if p_val < 0.01 else " **" if p_val < 0.05 else " *" if p_val < 0.10 else ""
        feat_short = feat.replace("snap_", "")
        print(f"    {feat_short:<28s} {s_mean:>8.3f} {s_std:>8.3f} {f_mean:>8.3f} {f_std:>8.3f} {delta:>+8.3f} {t_stat:>8.2f} {p_val:>8.4f}{sig_marker}")

    # ── Failure mode analysis ──
    print()
    print(f"    Failure Diagnosis Distribution:")
    diag = subset["failure_diagnosis"].value_counts()
    for d, cnt in diag.items():
        if d and d != "None":
            pct = cnt / n * 100
            print(f"      {str(d):<30s} │ {cnt:3d} ({pct:5.1f}%)")

    # ── Fear level vs save rate ──
    if "snap_fear_level" in subset.columns:
        print()
        print(f"    Save Rate by Fear Level:")
        fear_map = {0: "GREED", 1: "CONFIDENCE", 2: "NEUTRAL", 3: "ANXIETY", 4: "FEAR", 5: "PANIC"}
        for fl in sorted(subset["snap_fear_level"].dropna().unique()):
            mask = subset["snap_fear_level"] == fl
            sr = subset.loc[mask, "is_save"].mean() * 100
            cnt = mask.sum()
            label = fear_map.get(int(fl), f"L{int(fl)}")
            bar = "█" * int(sr / 5)
            print(f"      {label:>12s} │ SR={sr:5.1f}% n={cnt:3d}  {bar}")

    # ── Sigma wave vs save rate ──
    if "snap_sigma_wave" in subset.columns:
        s = pd.to_numeric(subset["snap_sigma_wave"], errors="coerce")
        bins = [-999, -1.5, -0.5, 0.5, 1.5, 999]
        labels_b = ["<-1.5σ", "-1.5→-0.5σ", "-0.5→0.5σ", "0.5→1.5σ", ">1.5σ"]
        subset["_sigma_bucket"] = pd.cut(s, bins=bins, labels=labels_b)
        print()
        print(f"    Save Rate by σ_wave Bucket:")
        grp = subset.groupby("_sigma_bucket", observed=True)["is_save"]
        for bucket_name in labels_b:
            if bucket_name in grp.groups:
                g = grp.get_group(bucket_name)
                sr = g.mean() * 100
                cnt = len(g)
                bar = "█" * int(sr / 5)
                print(f"      {bucket_name:>12s} │ SR={sr:5.1f}% n={cnt:3d}  {bar}")
        subset.drop(columns=["_sigma_bucket"], inplace=True)


# ════════════════════════════════════════════════════════════
# 3. MAIN EXECUTION
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print_header("ORACLE FORENSIC DATA EXPLORER — López de Prado × Simons Lab")

    # Extract all data
    print("\n  Extracting entry forensic labels from Neon...")
    entry_df = extract_labels("entry_forensic_labels")
    print(f"  → {len(entry_df)} entry labels extracted")

    print("\n  Extracting exit forensic labels from Neon...")
    exit_df = extract_labels("exit_forensic_labels")
    print(f"  → {len(exit_df)} exit labels extracted")

    if entry_df.empty and exit_df.empty:
        print("\n  ❌ No forensic data found. Run the Oracle Trainer first.")
        sys.exit(1)

    # ════════════════════════════════════════════════════════════
    # ENTRY ANALYSIS — Indicator by Indicator
    # ════════════════════════════════════════════════════════════
    if not entry_df.empty:
        print_header("ENTRY SIGNAL ANALYSIS")
        for (ticker, signal), grp in entry_df.groupby(["ticker", "signal_name"]):
            analyze_entry_signal(entry_df, ticker, signal)

    # ════════════════════════════════════════════════════════════
    # EXIT ANALYSIS — Indicator by Indicator
    # ════════════════════════════════════════════════════════════
    if not exit_df.empty:
        print_header("EXIT SIGNAL ANALYSIS")
        for (ticker, signal), grp in exit_df.groupby(["ticker", "signal_name"]):
            analyze_exit_signal(exit_df, ticker, signal)

    print()
    print_header("EXPLORATION COMPLETE")
    print("  All forensic labels analyzed. Use the data above to identify:")
    print("    1. Which features PREDICT wins vs losses (statistically significant)")
    print("    2. Which COMBINED CONDITIONS create exploitable edge")
    print("    3. Which exit signals are NOISE and should be suppressed")
    print("    4. Where REGIME context separates identical signals into different outcomes")
    print()
