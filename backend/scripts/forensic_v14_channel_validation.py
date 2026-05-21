#!/usr/bin/env python3
"""
Forensic Lab v14 — CHANNEL SNAPSHOT VALIDATION
================================================
Validates the production compute_channel_snapshot() on real Vault data.

5 PANELS answering 5 questions:

  PANEL A: ORTHOGONALITY MATRIX
    Are sigma_tide, sigma_current, sigma_wave truly independent?
    Are vwap_sigma_* redundant with regression sigma_*?

  PANEL B: UNIVARIATE PREDICTIVE POWER
    Which of the 41 fields actually predict returns?
    Separated by RSI vs RC signal type.

  PANEL C: RSI × VWAP SIGMA CONFLUENCE
    Why is vwap_sigma_wave ★★ STRONG for RSI but not RC?
    Cross-tab: RSI zone × vwap_sigma_wave bucket → WR

  PANEL D: REGRESSION vs VWAP HEAD-TO-HEAD
    For each window (240, 60, cycle):
      corr(sigma, vwap_sigma) → are they measuring the same thing?

  PANEL E: SPREAD & CONJUGATION VALUE
    Are spreads/conjugations genuinely NEW info or just derived noise?
    Information Value (IV) test.

Uses production compute_channel_snapshot() — NOT standalone math.
Uses store.load_bars() exclusively (Vault-first).
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
from sklearn.metrics import roc_auc_score

from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")


# ═══════════════════════════════════════════════════════════
# DATA LOADING — Oracle labels + production ChannelSnapshot
# ═══════════════════════════════════════════════════════════

def load_labels_with_channel_snapshot() -> pd.DataFrame:
    """Load Oracle labels and compute production ChannelSnapshot at each signal point."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    pg_url = os.environ["POSTGRES_URL"]
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM engine.entry_forensic_labels WHERE signal_direction = 1")
    rows = cur.fetchall()
    conn.close()

    print(f"  Loaded {len(rows)} labels from DB")

    # Group by ticker for efficiency (1 OHLCV load per ticker)
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
        if ohlc is None or len(ohlc) < 300:
            skipped += len(by_ticker[ticker])
            continue

        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)

        ticker_count = 0
        for row in by_ticker[ticker]:
            sig_time = pd.Timestamp(row["signal_time"])
            if ohlc.index.tz and sig_time.tz is None:
                sig_time = sig_time.tz_localize(ohlc.index.tz)
            elif ohlc.index.tz is None and sig_time.tz is not None:
                sig_time = sig_time.tz_localize(None)

            date_match = ohlc.index.date == sig_time.date()
            if not date_match.any():
                skipped += 1
                continue
            idx = int(np.where(date_match)[0][0])

            # Compute production ChannelSnapshot
            snap = compute_channel_snapshot(close, high, low, volume, idx)
            if snap is None:
                skipped += 1
                continue

            # Get old snapshot for comparison
            old_snap = row["snapshot"]
            if isinstance(old_snap, str): old_snap = json.loads(old_snap)

            rec = {
                "ticker": ticker,
                "signal_name": row["signal_name"],
                "signal_time": row["signal_time"],
                "classification": row["classification"],
                "is_win": 1 if row["classification"] in ("GOLDEN_RUN", "SOLID_MOVE") else 0,
                "year": sig_time.year,
            }

            # Add ALL ChannelSnapshot fields
            snap_dict = snap.to_dict()
            for k, v in snap_dict.items():
                if isinstance(v, (int, float, bool, np.integer, np.floating)):
                    rec[k] = float(v) if not isinstance(v, bool) else int(v)

            # Add old sigma_tide for comparison
            if old_snap and "sigma_tide" in old_snap:
                rec["old_sigma_tide_200"] = float(old_snap["sigma_tide"])

            # Add RSI value from old snapshot if available
            if old_snap and "rsi_value" in old_snap:
                rec["rsi_value"] = float(old_snap["rsi_value"])

            records.append(rec)
            ticker_count += 1

        print(f"    {ticker}: {ticker_count}/{len(by_ticker[ticker])} computed, {len(ohlc)} bars")

    store.close()
    print(f"\n  Total: {len(records)} computed, {skipped} skipped")
    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════
# PANEL A: ORTHOGONALITY MATRIX
# ═══════════════════════════════════════════════════════════

def panel_a_orthogonality(df):
    p("PANEL A: ORTHOGONALITY MATRIX — Are features truly independent?")

    # Key groups to check
    groups = {
        "Triple Regression σ": ["sigma_tide", "sigma_current", "sigma_wave"],
        "Triple VWAP σ": ["vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave"],
        "Cross: Reg vs VWAP (same window)": [
            ("sigma_tide", "vwap_sigma_tide"),
            ("sigma_current", "vwap_sigma_current"),
            ("sigma_wave", "vwap_sigma_wave"),
        ],
        "Triple Slopes": ["tide_slope", "current_slope", "wave_slope"],
        "Triple Accelerations": ["tide_accel", "current_accel", "wave_accel"],
    }

    # Within-group correlations
    for group_name, cols in groups.items():
        sp(group_name)
        if isinstance(cols[0], tuple):
            # Cross-correlation pairs
            for a, b in cols:
                if a in df.columns and b in df.columns:
                    valid = df[[a, b]].dropna()
                    if len(valid) > 50:
                        r = valid[a].corr(valid[b])
                        tag = "REDUNDANT ⚠️" if abs(r) > 0.85 else "OVERLAP" if abs(r) > 0.70 else "ORTHOGONAL ✅"
                        print(f"    corr({a}, {b}) = {r:+.3f}  → {tag}")
        else:
            available = [c for c in cols if c in df.columns]
            if len(available) >= 2:
                corr_m = df[available].corr()
                for i, a in enumerate(available):
                    for j, b in enumerate(available):
                        if j > i:
                            r = corr_m.loc[a, b]
                            tag = "REDUNDANT ⚠️" if abs(r) > 0.85 else "OVERLAP" if abs(r) > 0.70 else "ORTHOGONAL ✅"
                            print(f"    corr({a}, {b}) = {r:+.3f}  → {tag}")

    # Full correlation matrix of top features
    sp("Full Correlation Matrix — Top 15 Features")
    top_features = [
        "sigma_tide", "sigma_current", "sigma_wave",
        "vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave",
        "tide_slope", "current_slope", "wave_slope",
        "tide_accel", "current_accel", "wave_accel",
        "spread_tide_current", "conj_wave_tide", "conj_current_tide",
    ]
    available = [f for f in top_features if f in df.columns]
    corr = df[available].corr()

    # Print as compact matrix
    header = "".join(f"{f[:7]:>8s}" for f in available)
    print(f"    {'':12s}{header}")
    for f in available:
        row = "".join(f"{corr.loc[f, g]:+7.2f} " for g in available)
        print(f"    {f:12s}{row}")


# ═══════════════════════════════════════════════════════════
# PANEL B: UNIVARIATE PREDICTIVE POWER
# ═══════════════════════════════════════════════════════════

def panel_b_predictive_power(df):
    p("PANEL B: UNIVARIATE PREDICTIVE POWER — Which features predict returns?")

    # All numeric feature columns (exclude metadata)
    exclude = {"ticker", "signal_name", "signal_time", "classification",
               "is_win", "year", "old_sigma_tide_200", "rsi_value",
               "tide_window", "current_window", "wave_window"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in [np.float64, np.int64, float, int]
                    and not c.startswith("old_")]

    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig = df[df["signal_name"] == signal]
        y = sig["is_win"]
        n_total = len(y)
        wr_base = y.mean() * 100

        print(f"    N={n_total}, Base WR={wr_base:.1f}%\n")
        print(f"    {'Feature':<28s} │ {'r_pb':>8s} {'p-val':>8s} │ {'MI':>6s} │ {'AUC':>6s} │ {'Tckr%':>5s} │ {'Grade':>12s}")
        print(f"    {'─'*90}")

        results = []
        for feat in sorted(feature_cols):
            vals = sig[feat].dropna()
            y_f = y.loc[vals.index]
            if len(vals) < 50: continue
            if vals.nunique() < 3: continue  # Skip near-constant

            r_pb, p_val = stats.pointbiserialr(y_f, vals)
            mi = mutual_info_classif(
                vals.values.reshape(-1, 1), y_f.values,
                discrete_features=False, random_state=42
            )[0]
            try:
                auc = roc_auc_score(y_f, vals)
                if auc < 0.5: auc = 1 - auc
            except: auc = 0.5

            # Cross-ticker universality
            positive = 0
            total = 0
            for t in sig["ticker"].unique():
                sub = sig[sig["ticker"] == t]
                v = sub[feat].dropna()
                yv = sub.loc[v.index, "is_win"]
                if len(v) < 15: continue
                total += 1
                rt, _ = stats.pointbiserialr(yv, v)
                if abs(rt) > 0.05: positive += 1
            pct = positive / max(total, 1) * 100

            if abs(r_pb) > 0.1 and p_val < 0.01:
                grade = "★★ STRONG"
            elif abs(r_pb) > 0.05 and p_val < 0.05:
                grade = "★ MODERATE"
            elif abs(r_pb) > 0.03 and p_val < 0.10:
                grade = "~ WEAK"
            else:
                grade = "✗ NONE"

            sig_m = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
            print(f"    {feat:<28s} │ {r_pb:>+7.4f} {p_val:>7.4f}{sig_m:>1s} │ {mi:>6.4f} │ {auc:>6.3f} │ {pct:>4.0f}% │ {grade:>12s}")

            results.append({"feature": feat, "signal": signal, "r_pb": r_pb,
                           "p_val": p_val, "mi": mi, "auc": auc, "pct": pct, "grade": grade})

        # Summary
        strong = [r for r in results if "STRONG" in r["grade"]]
        moderate = [r for r in results if "MODERATE" in r["grade"]]
        print(f"\n    Summary: {len(strong)} STRONG, {len(moderate)} MODERATE out of {len(results)} features")


# ═══════════════════════════════════════════════════════════
# PANEL C: RSI × VWAP SIGMA CONFLUENCE
# ═══════════════════════════════════════════════════════════

def panel_c_rsi_vwap_confluence(df):
    p("PANEL C: RSI × VWAP SIGMA CONFLUENCE — Why is vwap_sigma_wave ★★ for RSI?")

    rsi_df = df[df["signal_name"] == "rsi_intelligence"].copy()
    if len(rsi_df) < 100:
        print("  Insufficient RSI data")
        return

    # Create RSI zone buckets from rsi_value
    if "rsi_value" not in rsi_df.columns or rsi_df["rsi_value"].isna().all():
        print("  No RSI values available")
        return

    def rsi_bucket(rsi):
        if rsi <= 30: return "OVERSOLD"
        if rsi <= 45: return "PULLBACK"
        if rsi <= 55: return "NEUTRAL"
        if rsi <= 70: return "MOMENTUM"
        return "OVERBOUGHT"

    rsi_df["rsi_bucket"] = rsi_df["rsi_value"].apply(rsi_bucket)

    # Create VWAP sigma buckets
    if "vwap_sigma_wave" not in rsi_df.columns:
        print("  No vwap_sigma_wave data")
        return

    def vwap_bucket(v):
        if v <= -1.5: return "DEEP_BELOW"
        if v <= -0.5: return "BELOW"
        if v <= 0.5: return "AT_VWAP"
        if v <= 1.5: return "ABOVE"
        return "FAR_ABOVE"

    rsi_df["vwap_bucket"] = rsi_df["vwap_sigma_wave"].apply(vwap_bucket)

    sp("Cross-tab: RSI Zone × VWAP Sigma Wave → WR")

    # Build cross-tab
    rsi_order = ["OVERSOLD", "PULLBACK", "NEUTRAL", "MOMENTUM", "OVERBOUGHT"]
    vwap_order = ["DEEP_BELOW", "BELOW", "AT_VWAP", "ABOVE", "FAR_ABOVE"]

    print(f"\n    {'RSI \\ VWAP':<12s}", end="")
    for v in vwap_order:
        print(f" │ {v:>11s}", end="")
    print(f" │ {'ALL':>6s}")
    print(f"    {'─'*80}")

    for r in rsi_order:
        print(f"    {r:<12s}", end="")
        r_mask = rsi_df["rsi_bucket"] == r
        for v in vwap_order:
            v_mask = rsi_df["vwap_bucket"] == v
            cell = rsi_df[r_mask & v_mask]
            if len(cell) >= 5:
                wr = cell["is_win"].mean() * 100
                print(f" │ {wr:>5.1f}% N={len(cell):>3d}", end="")
            else:
                print(f" │ {'---':>11s}", end="")
        # Row total
        row_data = rsi_df[r_mask]
        if len(row_data) >= 5:
            wr = row_data["is_win"].mean() * 100
            print(f" │ {wr:>4.1f}%")
        else:
            print(f" │ {'---':>6s}")

    # Hypothesis: PULLBACK + DEEP_BELOW is the strongest combo
    sp("Best & Worst Combos")
    combos = []
    for r in rsi_order:
        for v in vwap_order:
            cell = rsi_df[(rsi_df["rsi_bucket"] == r) & (rsi_df["vwap_bucket"] == v)]
            if len(cell) >= 10:
                wr = cell["is_win"].mean() * 100
                combos.append((r, v, wr, len(cell)))

    combos.sort(key=lambda x: -x[2])
    print(f"\n    TOP 5 combos:")
    for r, v, wr, n in combos[:5]:
        print(f"      {r:>12s} + {v:<11s} → WR={wr:>5.1f}% (N={n})")

    print(f"\n    BOTTOM 5 combos:")
    for r, v, wr, n in combos[-5:]:
        print(f"      {r:>12s} + {v:<11s} → WR={wr:>5.1f}% (N={n})")

    # Also check RC signal for contrast
    sp("Same analysis for RC (for contrast — expect WEAKER)")
    rc_df = df[df["signal_name"] == "regression_channel"].copy()
    if "vwap_sigma_wave" in rc_df.columns and len(rc_df) > 50:
        valid = rc_df["vwap_sigma_wave"].dropna()
        y_f = rc_df.loc[valid.index, "is_win"]
        r_rc, p_rc = stats.pointbiserialr(y_f, valid)
        print(f"    RC: vwap_sigma_wave r={r_rc:+.4f}, p={p_rc:.4f}")
        r_rsi, p_rsi = stats.pointbiserialr(
            rsi_df.loc[rsi_df["vwap_sigma_wave"].notna().values, "is_win"],
            rsi_df["vwap_sigma_wave"].dropna()
        )
        print(f"    RSI: vwap_sigma_wave r={r_rsi:+.4f}, p={p_rsi:.4f}")
        print(f"    → RSI is {abs(r_rsi)/max(abs(r_rc),0.001)*100-100:+.0f}% stronger")


# ═══════════════════════════════════════════════════════════
# PANEL D: REGRESSION vs VWAP HEAD-TO-HEAD
# ═══════════════════════════════════════════════════════════

def panel_d_regression_vs_vwap(df):
    p("PANEL D: REGRESSION σ vs VWAP σ — Same Window, Different Signal?")

    pairs = [
        ("sigma_tide", "vwap_sigma_tide", "TIDE (240)"),
        ("sigma_current", "vwap_sigma_current", "CURRENT (60)"),
        ("sigma_wave", "vwap_sigma_wave", "WAVE (cycle)"),
    ]

    for reg, vwap, label in pairs:
        sp(f"Window: {label}")
        if reg not in df.columns or vwap not in df.columns:
            print(f"    Missing columns")
            continue

        valid = df[[reg, vwap, "is_win"]].dropna()
        if len(valid) < 50:
            print(f"    Insufficient data")
            continue

        # Correlation between reg and VWAP sigma
        r_corr = valid[reg].corr(valid[vwap])
        print(f"    corr({reg}, {vwap}) = {r_corr:+.3f}")

        # Univariate predictive power
        r_reg, p_reg = stats.pointbiserialr(valid["is_win"], valid[reg])
        r_vwap, p_vwap = stats.pointbiserialr(valid["is_win"], valid[vwap])

        print(f"    Regression σ: r={r_reg:+.4f}, p={p_reg:.4f}")
        print(f"    VWAP σ:       r={r_vwap:+.4f}, p={p_vwap:.4f}")

        # Which is stronger?
        if abs(r_vwap) > abs(r_reg):
            print(f"    → VWAP is {abs(r_vwap)/max(abs(r_reg),0.001)*100-100:+.0f}% stronger ★")
        else:
            print(f"    → Regression is {abs(r_reg)/max(abs(r_vwap),0.001)*100-100:+.0f}% stronger")

        # Are they measuring different things? (residual after controlling for one)
        from sklearn.linear_model import LinearRegression
        lr = LinearRegression().fit(valid[[reg]], valid[vwap])
        residual = valid[vwap] - lr.predict(valid[[reg]])
        r_resid, p_resid = stats.pointbiserialr(valid["is_win"], residual)
        print(f"    Residual VWAP (controlling for Reg): r={r_resid:+.4f}, p={p_resid:.4f}")
        if abs(r_resid) > 0.03 and p_resid < 0.10:
            print(f"    → VWAP has UNIQUE info beyond regression ✅")
        else:
            print(f"    → VWAP is largely explained by regression ⚠️")


# ═══════════════════════════════════════════════════════════
# PANEL E: SPREAD & CONJUGATION VALUE
# ═══════════════════════════════════════════════════════════

def panel_e_derived_features(df):
    p("PANEL E: DERIVED FEATURES — Spreads & Conjugations vs Parents")

    # Test: is spread_tide_current just (sigma_tide - sigma_current)?
    # If so, does it predict BETTER than its parents individually?
    derived = [
        ("spread_tide_current", "sigma_tide", "sigma_current", "σ_tide - σ_current"),
        ("spread_tide_wave", "sigma_tide", "sigma_wave", "σ_tide - σ_wave"),
        ("spread_current_wave", "sigma_current", "sigma_wave", "σ_current - σ_wave"),
        ("conj_wave_tide", "wave_slope", "tide_slope", "wave_slope - tide_slope"),
        ("conj_current_tide", "current_slope", "tide_slope", "curr_slope - tide_slope"),
        ("conj_wave_current", "wave_slope", "current_slope", "wave_slope - curr_slope"),
    ]

    for feat, parent_a, parent_b, formula in derived:
        if feat not in df.columns:
            continue

        valid = df[[feat, parent_a, parent_b, "is_win"]].dropna()
        if len(valid) < 50: continue

        y = valid["is_win"]
        r_feat, p_feat = stats.pointbiserialr(y, valid[feat])
        r_a, p_a = stats.pointbiserialr(y, valid[parent_a])
        r_b, p_b = stats.pointbiserialr(y, valid[parent_b])

        # Is the derived feature more predictive than either parent?
        best_parent_r = max(abs(r_a), abs(r_b))
        if abs(r_feat) > best_parent_r and p_feat < 0.05:
            verdict = "BETTER THAN PARENTS ★"
        elif abs(r_feat) > 0.03 and p_feat < 0.10:
            verdict = "ADDS SOME VALUE"
        else:
            verdict = "NOISE — drop it ✗"

        print(f"\n    {feat} = {formula}")
        print(f"      Derived:  r={r_feat:+.4f}, p={p_feat:.4f}")
        print(f"      Parent A: r={r_a:+.4f} ({parent_a})")
        print(f"      Parent B: r={r_b:+.4f} ({parent_b})")
        print(f"      → {verdict}")


# ═══════════════════════════════════════════════════════════
# PANEL F: OLD vs NEW sigma_tide (200 → 240)
# ═══════════════════════════════════════════════════════════

def panel_f_old_vs_new(df):
    p("PANEL F: sigma_tide OLD (200-bar) vs NEW (240-bar)")

    has_old = df["old_sigma_tide_200"].notna()
    comp = df[has_old].copy()
    if len(comp) < 50:
        print("  Insufficient data with old sigma_tide")
        return

    y = comp["is_win"]
    old = comp["old_sigma_tide_200"]
    new = comp["sigma_tide"]

    r_old, p_old = stats.pointbiserialr(y, old)
    r_new, p_new = stats.pointbiserialr(y, new)

    print(f"\n    OLD sigma_tide (200 bars): r={r_old:+.4f}, p={p_old:.4f}")
    print(f"    NEW sigma_tide (240 bars): r={r_new:+.4f}, p={p_new:.4f}")
    print(f"    Δr = {r_new - r_old:+.4f}")
    print(f"    Correlation old↔new: {old.corr(new):.4f}")

    if abs(r_new) > abs(r_old):
        print(f"\n    ★ NEW (240) is {abs(r_new)/abs(r_old)*100-100:.1f}% STRONGER")
    else:
        print(f"\n    ✗ OLD (200) is {abs(r_old)/abs(r_new)*100-100:.1f}% STRONGER — REVERT?")


# ═══════════════════════════════════════════════════════════
# PANEL G: QUINTILE WR — Top candidates
# ═══════════════════════════════════════════════════════════

def panel_g_quintile_wr(df):
    p("PANEL G: QUINTILE WR — Do features separate winners from losers?")

    candidates = [
        "sigma_tide", "sigma_current", "sigma_wave",
        "vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave",
        "spread_tide_current", "conj_wave_tide", "tide_accel",
    ]

    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig = df[df["signal_name"] == signal]

        for feat in candidates:
            if feat not in sig.columns: continue
            vals = sig[feat].dropna()
            if len(vals) < 50: continue

            try:
                sig_copy = sig.copy()
                sig_copy["q"] = pd.qcut(sig_copy[feat], 5, labels=False, duplicates="drop")
                qs = sorted(sig_copy["q"].dropna().unique())

                wrs = []
                parts = []
                for q in qs:
                    mask = sig_copy["q"] == q
                    n = mask.sum()
                    wr = sig_copy.loc[mask, "is_win"].mean() * 100
                    rng = sig_copy.loc[mask, feat]
                    parts.append(f"Q{int(q)}:{wr:4.0f}%")
                    wrs.append(wr)

                spread = max(wrs) - min(wrs) if wrs else 0
                trend = "✅" if spread > 10 else "~" if spread > 5 else "✗"
                print(f"    {feat:<28s} {' '.join(parts)} │ spread={spread:>4.0f}pp {trend}")
            except:
                pass


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v14 — CHANNEL SNAPSHOT VALIDATION")
    print("  Production compute_channel_snapshot() on real Vault data")
    print("  López de Prado: Evaluate BEFORE feeding to MetaLabeler")

    print("\n  Computing production ChannelSnapshot on all Oracle labels...")
    df = load_labels_with_channel_snapshot()

    print(f"\n  Dataset: {len(df)} samples, {df['ticker'].nunique()} tickers")
    print(f"  WR overall: {df['is_win'].mean()*100:.1f}%")
    print(f"  Signals: {df['signal_name'].value_counts().to_dict()}")
    print(f"  Years: {sorted(df['year'].unique())}")

    # Run all panels
    panel_a_orthogonality(df)
    panel_b_predictive_power(df)
    panel_c_rsi_vwap_confluence(df)
    panel_d_regression_vs_vwap(df)
    panel_e_derived_features(df)
    panel_f_old_vs_new(df)
    panel_g_quintile_wr(df)

    p("v14 CHANNEL SNAPSHOT VALIDATION COMPLETE")
    print("  Next: Use results to filter features for MetaLabeler (Pieza 2)")
