#!/usr/bin/env python3
"""
Forensic Lab v4 — DATA SCIENCE + KALMAN + ADAPTIVE SIGMA DELTAS
================================================================
Addresses critical gaps:
  1. Sigma delta normalized by volatility/residual_std (adaptive thresholds)
  2. Kalman velocity as structural feature (missing from v3)
  3. Proper Data Science: correlation matrix, mutual information, PCA,
     feature interactions via tree SHAP, conditional distributions
  4. Statistical rigor: confidence intervals, bootstrap, effect sizes
  5. Feature interaction heatmap: which pairs create non-linear edge?
"""

import os, sys, json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
import psycopg2, psycopg2.extras
from scipy import stats
from scipy.signal import argrelextrema

from backend.modules.quality_swing.domain.rules.regression_channel import (
    linreg_channel, sigma_position as calc_sigma,
)
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle

LONG_WINDOW = 200
PEAK_ORDER = 10

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")


# ════════════════════════════════════════════════════════════
# DATA EXTRACTION (reused from v2/v3)
# ════════════════════════════════════════════════════════════

def extract_labels(table_name: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT * FROM engine.{table_name}")
    rows = cur.fetchall()
    conn.close()
    records = []
    for row in rows:
        flat = {
            "ticker": row["ticker"], "signal_name": row["signal_name"],
            "signal_direction": row["signal_direction"],
            "signal_time": row["signal_time"], "signal_price": row["signal_price"],
            "classification": row["classification"],
        }
        snap = row["snapshot"]
        if isinstance(snap, str): snap = json.loads(snap)
        if snap:
            for k, v in snap.items(): flat[f"snap_{k}"] = v
        horizons = row["horizons"]
        if isinstance(horizons, str): horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
                for m, mv in h_val.items():
                    flat[f"h{h_key}_{m}"] = mv
        records.append(flat)
    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    return df


def load_ohlcv(ticker: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    df = pd.read_sql(
        "SELECT time, open, high, low, close, volume FROM market.ohlcv_bars "
        "WHERE ticker = %s ORDER BY time", conn, params=(ticker,))
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df


def enrich_entry(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_win"] = df["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    # Numeric conversion for all snap_ columns
    snap_cols = [c for c in df.columns if c.startswith("snap_")]
    for c in snap_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ════════════════════════════════════════════════════════════
# PART 1: ADAPTIVE SIGMA DELTAS
# Should delta significance be normalized by volatility?
# ════════════════════════════════════════════════════════════

def compute_sigma_with_context(close: np.ndarray):
    """Compute σ series + residual_std (the channel width = volatility proxy)."""
    n = len(close)
    sigma_tide = np.full(n, np.nan)
    sigma_wave = np.full(n, np.nan)
    res_std_tide = np.full(n, np.nan)
    res_std_wave = np.full(n, np.nan)

    dom_cycle = detect_dominant_cycle(close)
    short_window = max(10, min(dom_cycle, 60))

    for i in range(LONG_WINDOW + 5, n):
        pw = close[:i + 1]
        cp = close[i]
        rv, ts, rs = linreg_channel(pw, LONG_WINDOW)
        sigma_tide[i] = calc_sigma(cp, rv, rs)
        res_std_tide[i] = rs
        if i >= short_window + 5:
            rv_s, ws, rs_s = linreg_channel(pw, short_window)
            sigma_wave[i] = calc_sigma(cp, rv_s, rs_s)
            res_std_wave[i] = rs_s

    return sigma_tide, sigma_wave, res_std_tide, res_std_wave


def analyze_adaptive_deltas(ticker: str, entry_df: pd.DataFrame):
    """Test whether sigma deltas should be normalized by channel width (residual_std)."""
    sp(f"ADAPTIVE SIGMA DELTAS: {ticker}")

    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    times = ohlcv["time"].values

    print(f"    Computing σ + residual_std series...")
    sigma_tide, sigma_wave, res_std_tide, res_std_wave = compute_sigma_with_context(close)

    # Detect wave troughs
    wave_troughs = argrelextrema(sigma_wave, np.less, order=PEAK_ORDER)[0]
    wave_troughs = wave_troughs[~np.isnan(sigma_wave[wave_troughs])]

    # Get ticker entry signals
    ticker_entries = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(ticker_entries) < 20: return

    # Map each signal to bar index
    results = []
    for _, row in ticker_entries.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())

        recent_troughs = wave_troughs[wave_troughs < bar_idx]
        if len(recent_troughs) < 2: continue

        last_trough = recent_troughs[-1]
        prev_trough = recent_troughs[-2]

        # Raw delta (absolute)
        raw_delta = sigma_wave[last_trough] - sigma_wave[prev_trough]

        # Normalized delta: divide by average residual_std at those troughs
        avg_res_std = (res_std_wave[last_trough] + res_std_wave[prev_trough]) / 2
        if avg_res_std > 0:
            norm_delta = raw_delta / avg_res_std
        else:
            norm_delta = raw_delta

        # Volatility-relative delta: divide by ATR-proxy (rolling std of close)
        lookback = min(20, bar_idx)
        atr_proxy = np.std(close[bar_idx - lookback:bar_idx]) if lookback > 2 else 1.0
        vol_delta = raw_delta * res_std_wave[bar_idx] / max(atr_proxy, 0.01)

        results.append({
            "is_win": row["is_win"],
            "signal_name": row["signal_name"],
            "raw_delta": raw_delta,
            "norm_delta": norm_delta,
            "vol_delta": vol_delta,
            "res_std_at_signal": res_std_wave[bar_idx] if not np.isnan(res_std_wave[bar_idx]) else 1.0,
        })

    rdf = pd.DataFrame(results)
    if len(rdf) < 20: return

    # Compare discriminative power: raw vs normalized vs vol-adjusted
    print(f"\n    Discriminative Power Comparison (t-test win vs loss):")
    for col, label in [("raw_delta", "Raw Δ (absolute σ units)"),
                        ("norm_delta", "Normalized Δ (÷ residual_std)"),
                        ("vol_delta", "Vol-Adjusted Δ (× channel_width ÷ ATR)")]:
        wins = rdf.loc[rdf["is_win"] == 1, col].dropna()
        losses = rdf.loc[rdf["is_win"] == 0, col].dropna()
        if len(wins) < 5 or len(losses) < 5: continue
        t, pval = stats.ttest_ind(wins, losses)
        cohens_d = (wins.mean() - losses.mean()) / np.sqrt(
            ((len(wins)-1)*wins.var() + (len(losses)-1)*losses.var()) / (len(wins)+len(losses)-2)
        )
        sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
        print(f"      {label:>40s} │ t={t:+6.3f}  p={pval:.4f}{sig}  d={cohens_d:+.3f}")

    # Win rate by buckets for each
    for col, label in [("raw_delta", "Raw"), ("norm_delta", "Normalized")]:
        vals = rdf[col].dropna()
        q33, q67 = vals.quantile(0.33), vals.quantile(0.67)
        print(f"\n    WR by {label} Δ terciles:")
        for lo, hi, name in [(vals.min()-1, q33, "Bottom 33%"),
                              (q33, q67, "Middle 33%"),
                              (q67, vals.max()+1, "Top 33%")]:
            mask = (rdf[col] >= lo) & (rdf[col] < hi)
            if mask.sum() < 5: continue
            wr = rdf.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            print(f"        {name:>12s} ({lo:+.2f} → {hi:+.2f}) │ WR={wr:5.1f}% n={cnt:3d}  {bar}")


# ════════════════════════════════════════════════════════════
# PART 2: KALMAN × SIGMA STRUCTURE INTERACTION
# ════════════════════════════════════════════════════════════

def analyze_kalman_structure(entry_df: pd.DataFrame, ticker: str):
    """How does Kalman velocity interact with sigma structure signals?"""
    sp(f"KALMAN × SIGMA STRUCTURE: {ticker}")

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 20: return

    kv = subset["snap_kalman_velocity"].dropna()
    if len(kv) < 20: return

    # Kalman velocity terciles
    kv_low = kv.quantile(0.33)
    kv_high = kv.quantile(0.67)
    subset["kv_zone"] = np.where(kv > kv_high, "KV_HIGH",
                         np.where(kv < kv_low, "KV_LOW", "KV_MID"))

    # Kalman acceleration (proxy: is KV accelerating?)
    # We don't have kv history per signal, but we can check kv vs wave_slope alignment
    ws = subset["snap_wave_slope"]
    subset["kv_wave_aligned"] = np.where(
        (kv > 0) & (ws > 0), "ALIGNED_UP",
        np.where((kv < 0) & (ws < 0), "ALIGNED_DOWN", "DIVERGENT")
    )

    for signal in subset["signal_name"].unique():
        sig_df = subset[subset["signal_name"] == signal]
        if len(sig_df) < 15: continue

        print(f"\n    {signal} × {ticker} (N={len(sig_df)}):")

        # Kalman velocity zones
        print(f"      Kalman Velocity Zone:")
        for zone in ["KV_LOW", "KV_MID", "KV_HIGH"]:
            mask = sig_df["kv_zone"] == zone
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            print(f"        {zone:>10s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")

        # Kalman × Wave alignment
        print(f"      Kalman × Wave Slope Alignment:")
        for align in ["ALIGNED_UP", "DIVERGENT", "ALIGNED_DOWN"]:
            mask = sig_df["kv_wave_aligned"] == align
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★ CONFIRMATION" if (align == "ALIGNED_UP" and wr > 55) else \
                     " ← DIVERGENCE" if (align == "DIVERGENT" and wr > 55) else ""
            print(f"        {align:>14s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Kalman + sigma_wave interaction
        sw = sig_df["snap_sigma_wave"]
        print(f"      Kalman + σ_wave Combined:")
        for kz, sw_cond, sw_label in [
            ("KV_HIGH", sw < -1.0, "σ<-1 + KV_HIGH"),
            ("KV_HIGH", sw > 0, "σ>0 + KV_HIGH"),
            ("KV_LOW", sw < -1.0, "σ<-1 + KV_LOW"),
            ("KV_MID", (sw >= -1.0) & (sw <= 0), "σ[-1,0] + KV_MID"),
        ]:
            mask = (sig_df["kv_zone"] == kz) & sw_cond
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else ""
            print(f"        {sw_label:<22s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Kalman + Fear interaction
        fl = sig_df["snap_fear_level"]
        print(f"      Kalman + Fear:")
        for kz in ["KV_LOW", "KV_MID", "KV_HIGH"]:
            for f_cond, f_label in [(fl >= 3, "Fear≥ANX"), (fl < 2, "Fear<NEU")]:
                mask = (sig_df["kv_zone"] == kz) & f_cond
                if mask.sum() < 3: continue
                wr = sig_df.loc[mask, "is_win"].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else ""
                print(f"        {kz}+{f_label:<10s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# PART 3: DATA SCIENCE — Correlation, Mutual Info, PCA
# ════════════════════════════════════════════════════════════

def data_science_analysis(entry_df: pd.DataFrame, ticker: str, signal: str):
    """Rigorous data science: correlation matrix, MI, PCA, interactions."""
    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_name"] == signal) &
        (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 30: return

    sp(f"DATA SCIENCE LAB: {signal} × {ticker} (N={len(subset)})")

    features = ["snap_sigma_tide", "snap_sigma_wave", "snap_tide_slope",
                "snap_wave_slope", "snap_tide_accel", "snap_rvol",
                "snap_vol_up_down_ratio", "snap_slope_conjugation",
                "snap_fear_level", "snap_kalman_velocity"]
    if "snap_rsi_value" in subset.columns:
        features.append("snap_rsi_value")

    available = [f for f in features if f in subset.columns]
    X = subset[available].apply(pd.to_numeric, errors="coerce").dropna()
    y = subset.loc[X.index, "is_win"]

    if len(X) < 30 or len(y.unique()) < 2: return
    clean_names = [f.replace("snap_", "") for f in available]

    # ── 3a. CORRELATION MATRIX with target ──
    print(f"\n    Pearson Correlation with Win (point-biserial r):")
    correlations = []
    for feat, name in zip(available, clean_names):
        r, pval = stats.pointbiserialr(y, X[feat])
        correlations.append((name, r, pval))
    correlations.sort(key=lambda x: abs(x[1]), reverse=True)
    for name, r, pval in correlations:
        sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
        bar = "█" * int(abs(r) * 40) if abs(r) > 0.05 else ""
        print(f"      {name:<25s} r={r:+.4f}  p={pval:.4f} {sig}  {bar}")

    # ── 3b. INTER-FEATURE CORRELATION (redundancy check) ──
    print(f"\n    Top Feature-Feature Correlations (|r| > 0.3):")
    corr_matrix = X.rename(columns=dict(zip(available, clean_names))).corr()
    pairs_seen = set()
    pairs = []
    for i, n1 in enumerate(clean_names):
        for j, n2 in enumerate(clean_names):
            if i >= j: continue
            r = corr_matrix.loc[n1, n2]
            if abs(r) > 0.3:
                pairs.append((n1, n2, r))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    for n1, n2, r in pairs[:10]:
        status = "❌ REDUNDANT" if abs(r) > 0.7 else "⚠️  CORRELATED" if abs(r) > 0.5 else "✅ OK"
        print(f"      {n1:<20s} × {n2:<20s} r={r:+.3f}  {status}")

    # ── 3c. MUTUAL INFORMATION ──
    try:
        from sklearn.feature_selection import mutual_info_classif
        mi = mutual_info_classif(X, y, random_state=42, n_neighbors=5)
        mi_sorted = sorted(zip(clean_names, mi), key=lambda x: x[1], reverse=True)
        print(f"\n    Mutual Information (non-linear dependency):")
        for name, mi_val in mi_sorted:
            bar = "█" * int(mi_val * 100)
            print(f"      {name:<25s} MI={mi_val:.4f}  {bar}")
    except ImportError:
        print("    ⚠ sklearn not available for MI")

    # ── 3d. PCA — Variance explained ──
    try:
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        X_scaled = StandardScaler().fit_transform(X)
        pca = PCA()
        pca.fit(X_scaled)

        print(f"\n    PCA Variance Explained:")
        cumvar = 0
        for i, (var, cumul) in enumerate(zip(pca.explained_variance_ratio_,
                                              np.cumsum(pca.explained_variance_ratio_))):
            bar = "█" * int(var * 100)
            print(f"      PC{i+1:2d}: {var*100:5.1f}% (cumul {cumul*100:5.1f}%)  {bar}")
            if cumul > 0.95: break

        # Top loadings for PC1 and PC2
        for pc_idx in range(min(3, len(pca.components_))):
            loadings = list(zip(clean_names, pca.components_[pc_idx]))
            loadings.sort(key=lambda x: abs(x[1]), reverse=True)
            top = loadings[:4]
            pc_str = ", ".join([f"{n}={v:+.3f}" for n, v in top])
            print(f"      PC{pc_idx+1} loadings: {pc_str}")

    except ImportError:
        print("    ⚠ sklearn not available for PCA")

    # ── 3e. FEATURE INTERACTION HEATMAP via Gradient Boosting ──
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.inspection import permutation_importance
        from itertools import combinations

        print(f"\n    Feature Pair Interaction Analysis (GB with pair features):")

        # Test each pair: does adding the interaction term improve?
        gb_base = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                              random_state=42, min_samples_leaf=5)
        from sklearn.model_selection import cross_val_score
        base_score = cross_val_score(gb_base, X, y, cv=5, scoring="accuracy").mean()

        interactions = []
        for (f1, n1), (f2, n2) in combinations(zip(available, clean_names), 2):
            X_pair = X.copy()
            X_pair[f"inter_{n1}_{n2}"] = X[f1] * X[f2]
            gb_inter = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                                   random_state=42, min_samples_leaf=5)
            inter_score = cross_val_score(gb_inter, X_pair, y, cv=5, scoring="accuracy").mean()
            delta = inter_score - base_score
            if abs(delta) > 0.005:
                interactions.append((n1, n2, delta, inter_score))

        interactions.sort(key=lambda x: x[2], reverse=True)
        if interactions:
            for n1, n2, delta, score in interactions[:8]:
                marker = "★ SYNERGY" if delta > 0.01 else "↑" if delta > 0 else "↓"
                print(f"        {n1:<18s} × {n2:<18s} Δ={delta:+.4f} ({score:.3f})  {marker}")
        else:
            print(f"        No significant interactions found (base accuracy: {base_score:.3f})")

    except ImportError:
        print("    ⚠ sklearn not available for interaction analysis")

    # ── 3f. CONDITIONAL PROBABILITY: P(win | feature_above_median, other_feature_below_median) ──
    print(f"\n    Conditional Probabilities (feature pairs, above/below median):")
    medians = X.median()
    best_conds = []
    for f1, n1 in zip(available[:6], clean_names[:6]):  # Top features only
        for f2, n2 in zip(available[:6], clean_names[:6]):
            if f1 >= f2: continue
            for d1, l1 in [(X[f1] > medians[f1], f"{n1}>med"),
                            (X[f1] <= medians[f1], f"{n1}≤med")]:
                for d2, l2 in [(X[f2] > medians[f2], f"{n2}>med"),
                                (X[f2] <= medians[f2], f"{n2}≤med")]:
                    mask = d1 & d2
                    if mask.sum() < 8: continue
                    wr = y[mask].mean() * 100
                    if wr > 60 or wr < 35:
                        best_conds.append((f"{l1} + {l2}", wr, mask.sum()))

    best_conds.sort(key=lambda x: x[1], reverse=True)
    for label, wr, n in best_conds[:10]:
        bar = "█" * int(wr / 5)
        marker = " ★" if wr > 65 else " ✗" if wr < 35 else ""
        print(f"      {label:<50s} │ WR={wr:5.1f}% n={n:3d}  {bar}{marker}")

    # Bottom conditions (what to AVOID)
    if best_conds:
        print(f"\n    Anti-Patterns (WR < 40%):")
        for label, wr, n in sorted(best_conds, key=lambda x: x[1])[:5]:
            if wr >= 40: continue
            bar = "█" * int(wr / 5)
            print(f"      {label:<50s} │ WR={wr:5.1f}% n={n:3d}  {bar} ✗ AVOID")


# ════════════════════════════════════════════════════════════
# PART 4: BOOTSTRAP CONFIDENCE INTERVALS
# ════════════════════════════════════════════════════════════

def bootstrap_key_conditions(entry_df: pd.DataFrame):
    """Bootstrap CI for the top conditions discovered in v1-v3."""
    sp("BOOTSTRAP CONFIDENCE INTERVALS (1000 resamples)")

    conditions = []
    for ticker in ["COST", "SPY", "QQQ", "AAPL"]:
        for signal in ["rsi_intelligence", "regression_channel"]:
            subset = entry_df[
                (entry_df["ticker"] == ticker) &
                (entry_df["signal_name"] == signal) &
                (entry_df["signal_direction"] == 1)
            ].copy()
            if len(subset) < 10: continue

            sw = subset["snap_sigma_wave"]
            fl = subset["snap_fear_level"]
            kv = subset["snap_kalman_velocity"]
            vudr = subset["snap_vol_up_down_ratio"]

            # Gold Standard: σ<-1 + Fear≥ANX + VolAccum
            mask = (sw < -1.0) & (fl >= 3) & (vudr > 1.0)
            if mask.sum() >= 5:
                conditions.append((f"{signal[:3]}×{ticker} Gold(σ<-1+Fear+Vol)",
                                    subset.loc[mask, "is_win"].values))

            # Kalman-confirmed entry: KV > 0 + σ<-1
            mask = (sw < -1.0) & (kv > 0.005)
            if mask.sum() >= 5:
                conditions.append((f"{signal[:3]}×{ticker} KV↑+σ<-1",
                                    subset.loc[mask, "is_win"].values))

    for label, wins in conditions:
        n = len(wins)
        observed_wr = wins.mean()
        # Bootstrap
        boot_wrs = []
        rng = np.random.RandomState(42)
        for _ in range(1000):
            sample = rng.choice(wins, size=n, replace=True)
            boot_wrs.append(sample.mean())
        ci_low = np.percentile(boot_wrs, 2.5)
        ci_high = np.percentile(boot_wrs, 97.5)
        marker = "★" if ci_low > 0.50 else "OK" if ci_low > 0.40 else "⚠"
        print(f"    {label:<40s} WR={observed_wr:.1%}  95%CI=[{ci_low:.1%}, {ci_high:.1%}]  n={n:3d}  {marker}")


# ════════════════════════════════════════════════════════════
# PART 5: EFFECT SIZE COMPARISON — Cohen's d for ALL features
# ════════════════════════════════════════════════════════════

def effect_size_table(entry_df: pd.DataFrame, ticker: str, signal: str):
    """Cohen's d for each feature — standardized effect sizes."""
    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_name"] == signal) &
        (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 30: return

    sp(f"EFFECT SIZES (Cohen's d): {signal} × {ticker}")

    features = ["snap_sigma_tide", "snap_sigma_wave", "snap_tide_slope",
                "snap_wave_slope", "snap_tide_accel", "snap_rvol",
                "snap_vol_up_down_ratio", "snap_slope_conjugation",
                "snap_fear_level", "snap_kalman_velocity", "snap_rsi_value"]

    results = []
    for feat in features:
        if feat not in subset.columns: continue
        vals = pd.to_numeric(subset[feat], errors="coerce")
        wins = vals[subset["is_win"] == 1].dropna()
        losses = vals[subset["is_win"] == 0].dropna()
        if len(wins) < 5 or len(losses) < 5: continue

        pooled_std = np.sqrt(((len(wins)-1)*wins.var() + (len(losses)-1)*losses.var()) /
                             (len(wins)+len(losses)-2))
        if pooled_std > 0:
            d = (wins.mean() - losses.mean()) / pooled_std
        else:
            d = 0
        t, pval = stats.ttest_ind(wins, losses)
        results.append((feat.replace("snap_", ""), d, pval, wins.mean(), losses.mean()))

    results.sort(key=lambda x: abs(x[1]), reverse=True)
    print(f"\n    {'Feature':<25s} {'Cohen d':>8s} {'p-value':>8s} {'Win μ':>8s} {'Loss μ':>8s}  Effect")
    print(f"    {'─'*80}")
    for name, d, pval, win_mu, loss_mu in results:
        effect = "LARGE" if abs(d) > 0.8 else "MEDIUM" if abs(d) > 0.5 else \
                 "SMALL" if abs(d) > 0.2 else "negligible"
        sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
        print(f"    {name:<25s} d={d:+.4f}  p={pval:.4f}{sig} μw={win_mu:+.3f}  μl={loss_mu:+.3f}  {effect}")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v4 — DATA SCIENCE + KALMAN + ADAPTIVE DELTAS")

    print("\n  Loading forensic labels...")
    entry_df = enrich_entry(extract_labels("entry_forensic_labels"))
    print(f"  → {len(entry_df)} entry labels")

    # ═══ PART 1: Adaptive Sigma Deltas ═══
    p("PART 1: ADAPTIVE SIGMA DELTAS — Fixed vs Normalized thresholds")
    for ticker in ["COST", "SPY"]:
        analyze_adaptive_deltas(ticker, entry_df)

    # ═══ PART 2: Kalman × Structure ═══
    p("PART 2: KALMAN × SIGMA STRUCTURE INTERACTION")
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        analyze_kalman_structure(entry_df, ticker)

    # ═══ PART 3: Data Science Lab ═══
    p("PART 3: DATA SCIENCE LAB — Correlation, MI, PCA, Interactions")
    for ticker in ["COST", "SPY"]:
        for signal in ["rsi_intelligence", "regression_channel"]:
            data_science_analysis(entry_df, ticker, signal)

    # ═══ PART 4: Bootstrap CI ═══
    p("PART 4: BOOTSTRAP CONFIDENCE INTERVALS")
    bootstrap_key_conditions(entry_df)

    # ═══ PART 5: Effect Sizes ═══
    p("PART 5: EFFECT SIZES (Cohen's d)")
    for ticker in ["COST", "SPY"]:
        for signal in ["rsi_intelligence", "regression_channel"]:
            effect_size_table(entry_df, ticker, signal)

    p("DATA SCIENCE ANALYSIS COMPLETE")
