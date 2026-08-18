#!/usr/bin/env python3
"""
Forensic Lab v13 — TRIPLE REGRESSION + VWAP EVALUATION
========================================================
Scientific evaluation of the proposed 3-line system vs current 2-line:

CURRENT (2 lines):
  TIDE  = 200 bars (fixed)
  WAVE  = cycle-adaptive (10-60 bars)

PROPOSED (3 lines):
  TIDE  = 240 bars (macro trend, ~1 year)
  CURRENT = 60 bars (medium trend, ~quarter)
  WAVE  = 30 bars or adaptive (short surfing wave)

For each configuration, compute ALL derivatives:
  - 3 sigma positions (price vs each regression)
  - 3 slopes (normalized)
  - 3 accelerations (slope change)
  - 3 pairwise conjugations (slope differences)
  - 3 pairwise sigma spreads (sigma differences between lines)
  - VWAP continuous distance (not just boolean)

Then correlate each with Oracle labels to evaluate predictive power.

Uses store.load_bars() exclusively.
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
from sklearn.feature_selection import mutual_info_classif

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")


# ═══════════════════════════════════════════════════════════
# CORE: REGRESSION FUNCTIONS (reusing production math)
# ═══════════════════════════════════════════════════════════

def linreg_channel(close: np.ndarray, window: int):
    """Same as production: returns (reg_value, slope_norm, residual_std)."""
    if len(close) < window:
        return 0.0, 0.0, 1.0
    y = close[-window:]
    x = np.arange(window, dtype=float)
    x_mean, y_mean = x.mean(), y.mean()
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    reg_line = slope * (window - 1) + intercept
    fitted = slope * x + intercept
    residuals = y - fitted
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 1.0
    slope_norm = (slope / y_mean * 100) if y_mean > 0 else 0.0
    return reg_line, slope_norm, max(residual_std, 1e-8)


def calc_vwap(close, high, low, volume, window=20):
    """Production VWAP."""
    if len(close) < window:
        return close[-1] if len(close) > 0 else 0.0
    typical = (close[-window:] + high[-window:] + low[-window:]) / 3.0
    vol = volume[-window:]
    total_vol = vol.sum()
    if total_vol <= 0:
        return typical[-1]
    return float(np.sum(typical * vol) / total_vol)


def sigma(price, reg_value, residual_std):
    if residual_std <= 0: return 0.0
    return (price - reg_value) / residual_std


# ═══════════════════════════════════════════════════════════
# TRIPLE REGRESSION: Compute all derivatives at one point
# ═══════════════════════════════════════════════════════════

def compute_triple_regression(close, high, low, volume, idx,
                              tide_w=240, current_w=60, wave_w=30):
    """Compute 3-line regression and ALL derivatives at bar idx."""
    price_now = close[idx]
    pw = close[:idx + 1]
    pw_prev = close[:idx]

    features = {}

    # Skip if insufficient data
    if idx < tide_w + 5:
        return None

    # ── 3 Regression Lines ──
    tide_val, tide_slope, tide_std = linreg_channel(pw, tide_w)
    curr_val, curr_slope, curr_std = linreg_channel(pw, current_w)
    wave_val, wave_slope, wave_std = linreg_channel(pw, wave_w)

    # ── 3 Sigma Positions ──
    sig_tide = sigma(price_now, tide_val, tide_std)
    sig_curr = sigma(price_now, curr_val, curr_std)
    sig_wave = sigma(price_now, wave_val, wave_std)

    features["sigma_tide"] = round(sig_tide, 4)
    features["sigma_current"] = round(sig_curr, 4)
    features["sigma_wave"] = round(sig_wave, 4)

    # ── 3 Slopes ──
    features["tide_slope"] = round(tide_slope, 6)
    features["current_slope"] = round(curr_slope, 6)
    features["wave_slope"] = round(wave_slope, 6)

    # ── 3 Accelerations (slope change vs previous bar) ──
    if idx > tide_w + 6:
        _, tide_slope_p, _ = linreg_channel(pw_prev, tide_w)
        _, curr_slope_p, _ = linreg_channel(pw_prev, current_w)
        _, wave_slope_p, _ = linreg_channel(pw_prev, wave_w)
        features["tide_accel"] = round(tide_slope - tide_slope_p, 6)
        features["current_accel"] = round(curr_slope - curr_slope_p, 6)
        features["wave_accel"] = round(wave_slope - wave_slope_p, 6)
    else:
        features["tide_accel"] = 0.0
        features["current_accel"] = 0.0
        features["wave_accel"] = 0.0

    # ── 3 Pairwise Conjugations (slope differences) ──
    features["conj_wave_current"] = round(wave_slope - curr_slope, 6)
    features["conj_wave_tide"] = round(wave_slope - tide_slope, 6)
    features["conj_current_tide"] = round(curr_slope - tide_slope, 6)

    # ── 3 Sigma Spreads (sigma differences between lines) ──
    features["spread_tide_current"] = round(sig_tide - sig_curr, 4)
    features["spread_tide_wave"] = round(sig_tide - sig_wave, 4)
    features["spread_current_wave"] = round(sig_curr - sig_wave, 4)

    # ── VWAP Continuous (distance in sigma units) ──
    hw = high[:idx + 1]
    lw = low[:idx + 1]
    vw = volume[:idx + 1]
    vwap_val = calc_vwap(close[:idx + 1], hw, lw, vw, 20)
    vwap_dist = (price_now - vwap_val) / tide_std if tide_std > 0 else 0.0
    features["vwap_distance"] = round(vwap_dist, 4)
    features["below_vwap"] = 1 if price_now < vwap_val else 0

    # ── Residual Std Ratios (volatility compression between timeframes) ──
    features["std_ratio_wave_tide"] = round(wave_std / max(tide_std, 1e-8), 4)
    features["std_ratio_current_tide"] = round(curr_std / max(tide_std, 1e-8), 4)

    return features


# ═══════════════════════════════════════════════════════════
# LOAD LABELS + COMPUTE TRIPLE REGRESSION ON EACH
# ═══════════════════════════════════════════════════════════

def load_labels_with_triple_regression():
    """Load Oracle labels and compute triple regression at each signal point."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    pg_url = os.environ["POSTGRES_URL"]
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM engine.entry_forensic_labels WHERE signal_direction = 1")
    rows = cur.fetchall()
    conn.close()

    print(f"  Loaded {len(rows)} labels")

    # Group by ticker for efficiency
    by_ticker = {}
    for row in rows:
        t = row["ticker"]
        if t not in by_ticker:
            by_ticker[t] = []
        by_ticker[t].append(row)

    records = []
    skipped = 0

    for ticker in sorted(by_ticker.keys()):
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 250:
            skipped += len(by_ticker[ticker])
            continue

        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)

        for row in by_ticker[ticker]:
            sig_time = pd.Timestamp(row["signal_time"])
            if ohlc.index.tz and sig_time.tz is None:
                sig_time = sig_time.tz_localize(ohlc.index.tz)
            elif ohlc.index.tz is None and sig_time.tz is not None:
                sig_time = sig_time.tz_localize(None)

            # Find the correct bar (exact match by date)
            date_match = ohlc.index.date == sig_time.date()
            if not date_match.any():
                skipped += 1
                continue
            idx = int(np.where(date_match)[0][0])

            # Get old snapshot features
            snap = row["snapshot"]
            if isinstance(snap, str): snap = json.loads(snap)

            # Compute triple regression
            triple = compute_triple_regression(close, high, low, volume, idx)
            if triple is None:
                skipped += 1
                continue

            # Also compute CURRENT 2-line system for comparison
            two_line = compute_triple_regression(close, high, low, volume, idx,
                                                  tide_w=200, current_w=200, wave_w=30)

            rec = {
                "ticker": ticker,
                "signal_name": row["signal_name"],
                "signal_time": row["signal_time"],
                "classification": row["classification"],
                "is_win": 1 if row["classification"] in ("GOLDEN_RUN", "SOLID_MOVE") else 0,
                "year": sig_time.year,
            }

            # Add old snapshot sigma_tide for comparison
            if snap and "sigma_tide" in snap:
                rec["old_sigma_tide"] = float(snap["sigma_tide"])

            # Add triple regression features
            for k, v in triple.items():
                rec[f"new_{k}"] = v

            records.append(rec)

        print(f"    {ticker}: {len(by_ticker[ticker])} labels, {len(ohlc)} bars")

    print(f"  Total: {len(records)} computed, {skipped} skipped")
    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════

def evaluate_features(df, feature_cols, label=""):
    """Evaluate each feature's predictive power."""
    y = df["is_win"]

    print(f"\n    {'Feature':<28s} │ {'r_pb':>8s} {'p-val':>8s} │ {'MI':>6s} │ {'AUC':>6s} │ {'Ticker%':>7s} │ {'Status':>12s}")
    print(f"    {'─'*90}")

    results = []
    for feat in feature_cols:
        vals = df[feat].dropna()
        y_f = y.loc[vals.index]
        if len(vals) < 50: continue

        r_pb, p_val = stats.pointbiserialr(y_f, vals)

        mi = mutual_info_classif(
            vals.values.reshape(-1, 1), y_f.values,
            discrete_features=False, random_state=42
        )[0]

        from sklearn.metrics import roc_auc_score
        try:
            auc = roc_auc_score(y_f, vals)
            if auc < 0.5: auc = 1 - auc
        except: auc = 0.5

        # Cross-ticker
        positive = 0
        total = 0
        for ticker in df["ticker"].unique():
            sub = df[df["ticker"] == ticker]
            v = sub[feat].dropna()
            yv = sub.loc[v.index, "is_win"]
            if len(v) < 15: continue
            total += 1
            rt, _ = stats.pointbiserialr(yv, v)
            if abs(rt) > 0.05: positive += 1
        pct = positive / max(total, 1) * 100

        if abs(r_pb) > 0.1 and p_val < 0.01:
            status = "★★ STRONG"
        elif abs(r_pb) > 0.05 and p_val < 0.05:
            status = "★ MODERATE"
        elif abs(r_pb) > 0.03 and p_val < 0.10:
            status = "~ WEAK"
        else:
            status = "✗ NONE"

        sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
        print(f"    {feat:<28s} │ {r_pb:>+7.4f} {p_val:>7.4f}{sig:>1s} │ {mi:>6.4f} │ {auc:>6.3f} │ {pct:>5.0f}%  │ {status:>12s}")

        results.append({"feature": feat, "r_pb": r_pb, "p_val": p_val, "mi": mi, "auc": auc, "pct": pct, "status": status})

    return results


def compare_old_vs_new(df):
    """Compare old 2-line sigma_tide with new 3-line sigma_tide."""
    p("COMPARISON: OLD sigma_tide (200) vs NEW sigma_tide (240)")

    has_old = df["old_sigma_tide"].notna()
    comp = df[has_old].copy()
    if len(comp) < 50:
        print("  Insufficient data with old sigma_tide")
        return

    y = comp["is_win"]
    old = comp["old_sigma_tide"]
    new = comp["new_sigma_tide"]

    r_old, p_old = stats.pointbiserialr(y, old)
    r_new, p_new = stats.pointbiserialr(y, new)

    print(f"\n    OLD sigma_tide (200 bars): r={r_old:+.4f}, p={p_old:.4f}")
    print(f"    NEW sigma_tide (240 bars): r={r_new:+.4f}, p={p_new:.4f}")
    print(f"    Δr = {r_new - r_old:+.4f}")
    print(f"    Correlation old↔new: {old.corr(new):.4f}")

    # Is the new one better?
    if abs(r_new) > abs(r_old):
        print(f"\n    ★ NEW (240) is {abs(r_new)/abs(r_old)*100-100:.1f}% STRONGER")
    else:
        print(f"\n    ✗ OLD (200) is {abs(r_old)/abs(r_new)*100-100:.1f}% STRONGER")


def vwap_deep_dive(df):
    """Deep analysis of VWAP as continuous feature."""
    p("VWAP DEEP DIVE — Continuous Distance vs Boolean")

    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig = df[df["signal_name"] == signal]
        y = sig["is_win"]

        # Boolean (old)
        bv = sig["new_below_vwap"].dropna()
        y_bv = y.loc[bv.index]

        # Continuous (new)
        cv = sig["new_vwap_distance"].dropna()
        y_cv = y.loc[cv.index]

        if len(cv) < 50: continue

        r_bool, p_bool = stats.pointbiserialr(y_bv, bv)
        r_cont, p_cont = stats.pointbiserialr(y_cv, cv)

        print(f"\n    Boolean (below_vwap):   r={r_bool:+.4f}, p={p_bool:.4f}")
        print(f"    Continuous (vwap_dist): r={r_cont:+.4f}, p={p_cont:.4f}")

        # VWAP × sigma_tide interaction
        if "new_sigma_tide" in sig.columns:
            both = sig[["new_vwap_distance", "new_sigma_tide", "is_win"]].dropna()
            if len(both) > 50:
                # Create interaction term
                both["vwap_x_sigma"] = both["new_vwap_distance"] * both["new_sigma_tide"]
                r_int, p_int = stats.pointbiserialr(both["is_win"], both["vwap_x_sigma"])
                print(f"    Interaction (vwap×σ):  r={r_int:+.4f}, p={p_int:.4f}")

                # Conditional: sigma_tide < -1 AND below VWAP
                mask = (both["new_sigma_tide"] < -1) & (both["new_vwap_distance"] < 0)
                if mask.sum() > 20:
                    wr = both.loc[mask, "is_win"].mean() * 100
                    n = mask.sum()
                    base_wr = both["is_win"].mean() * 100
                    print(f"    σ_tide<-1 + below_VWAP: WR={wr:.1f}% (N={n}, base={base_wr:.1f}%, edge={wr-base_wr:+.1f}%)")

        # WR by VWAP distance quintile
        print(f"\n    WR by VWAP distance quintile:")
        try:
            sig_copy = sig.copy()
            sig_copy["vwap_q"] = pd.qcut(sig_copy["new_vwap_distance"], 5, labels=False, duplicates="drop")
            for q in sorted(sig_copy["vwap_q"].dropna().unique()):
                mask = sig_copy["vwap_q"] == q
                n = mask.sum()
                wr = sig_copy.loc[mask, "is_win"].mean() * 100
                vwap_range = sig_copy.loc[mask, "new_vwap_distance"]
                print(f"      Q{int(q)}: VWAP_dist=[{vwap_range.min():+.2f}, {vwap_range.max():+.2f}] WR={wr:.1f}% N={n}")
        except Exception as e:
            print(f"      Quintile error: {e}")


def new_features_evaluation(df):
    """Evaluate ALL new features from triple regression."""
    p("PART 1: ALL TRIPLE REGRESSION FEATURES — RSI Intelligence")
    sig = df[df["signal_name"] == "rsi_intelligence"]
    new_cols = [c for c in df.columns if c.startswith("new_") and c != "new_below_vwap"]
    evaluate_features(sig, new_cols, "RSI")

    p("PART 2: ALL TRIPLE REGRESSION FEATURES — Regression Channel")
    sig = df[df["signal_name"] == "regression_channel"]
    evaluate_features(sig, new_cols, "RC")


def temporal_stability_new(df):
    """Check temporal stability of the most promising new features."""
    p("TEMPORAL STABILITY — New Features")

    periods = [
        (2006, 2010, "2006-10"),
        (2011, 2015, "2011-15"),
        (2016, 2020, "2016-20"),
        (2021, 2026, "2021-26"),
    ]

    # Top candidates to check
    candidates = [
        "new_sigma_tide", "new_sigma_current", "new_sigma_wave",
        "new_current_slope", "new_current_accel",
        "new_conj_wave_current", "new_conj_current_tide",
        "new_spread_tide_current", "new_vwap_distance",
        "new_std_ratio_wave_tide",
    ]

    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig = df[df["signal_name"] == signal]

        print(f"\n    {'Feature':<28s}", end="")
        for _, _, label in periods:
            print(f" │ {label:>8s}", end="")
        print(f" │ {'Stable?':>7s}")
        print(f"    {'─'*80}")

        for feat in candidates:
            if feat not in sig.columns: continue
            print(f"    {feat:<28s}", end="")
            period_rs = []

            for y_lo, y_hi, _ in periods:
                psub = sig[(sig["year"] >= y_lo) & (sig["year"] <= y_hi)]
                vals = psub[feat].dropna()
                y_f = psub.loc[vals.index, "is_win"]
                if len(vals) < 30:
                    print(f" │ {'N/A':>8s}", end="")
                    continue
                r, pval = stats.pointbiserialr(y_f, vals)
                period_rs.append(r)
                m = "★" if abs(r) > 0.1 and pval < 0.05 else ""
                print(f" │ {r:>+6.3f}{m:>2s}", end="")

            if len(period_rs) >= 3:
                signs = [np.sign(r) for r in period_rs if abs(r) > 0.02]
                if len(signs) >= 3:
                    c = max(signs.count(1), signs.count(-1)) / len(signs)
                    s = "✅" if c >= 0.8 else "⚠" if c >= 0.6 else "🚨"
                else: s = "~"
            else: s = "?"
            print(f" │ {s:>7s}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v13 — TRIPLE REGRESSION + VWAP EVALUATION")
    print("  López de Prado Committee: Evaluate BEFORE implementing")
    print("  Proposed: TIDE(240) + CURRENT(60) + WAVE(30)")

    print("\n  Computing triple regression on all 6,807 Oracle labels...")
    df = load_labels_with_triple_regression()

    compare_old_vs_new(df)
    new_features_evaluation(df)
    temporal_stability_new(df)
    vwap_deep_dive(df)

    p("v13 TRIPLE REGRESSION EVALUATION COMPLETE")
