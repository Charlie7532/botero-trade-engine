#!/usr/bin/env python3
"""
Forensic Lab v6 — FINAL AUDIT: Volume Variance, Per-Stock Calibration, Architecture
======================================================================================
  1. VOLUME VARIANCE: Detect the exhaustion → BOOM pattern.
     Not the slope of volume, but the sudden SPIKE after a quiet period.
     
  2. PER-STOCK CALIBRATION: Automatically detect the optimal σ entry 
     window per ticker. The "training before operating" idea.
     
  3. FEATURE ABSORPTION ANALYSIS: Is RC fully absorbed by an enhanced RSI?
     What does RSI+fixed_wave_slope+sigma+fear capture that RC alone provided?
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

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")


# ════════════════════════════════════════════════════════════
# DATA LOADERS
# ════════════════════════════════════════════════════════════

def load_labels() -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM engine.entry_forensic_labels")
    rows = cur.fetchall()
    conn.close()
    records = []
    for row in rows:
        flat = {
            "ticker": row["ticker"], "signal_name": row["signal_name"],
            "signal_direction": row["signal_direction"],
            "signal_time": row["signal_time"], "classification": row["classification"],
        }
        snap = row["snapshot"]
        if isinstance(snap, str): snap = json.loads(snap)
        if snap:
            for k, v in snap.items(): flat[f"snap_{k}"] = v
        horizons = row["horizons"]
        if isinstance(horizons, str): horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
                for m, mv in h_val.items(): flat[f"h{h_key}_{m}"] = mv
        records.append(flat)
    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    df["is_win"] = df["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    for c in [col for col in df.columns if col.startswith("snap_")]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ════════════════════════════════════════════════════════════
# PART 1: VOLUME VARIANCE — Exhaustion → BOOM
# ════════════════════════════════════════════════════════════

def volume_variance_analysis(entry_df: pd.DataFrame):
    """Detect the exhaustion → volume BOOM pattern using rvol and vol_up_down_ratio."""
    sp("VOLUME VARIANCE: Exhaustion → BOOM Detection")

    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        for signal in ["rsi_intelligence", "regression_channel"]:
            subset = entry_df[
                (entry_df["ticker"] == ticker) &
                (entry_df["signal_name"] == signal) &
                (entry_df["signal_direction"] == 1)
            ].copy()
            if len(subset) < 20: continue

            rvol = subset["snap_rvol"]
            vudr = subset["snap_vol_up_down_ratio"]
            ts = subset["snap_tide_slope"]

            # Volume regime: quiet (rvol < 0.8) vs normal (0.8-1.3) vs BOOM (>1.3)
            subset["vol_regime"] = np.where(rvol > 1.5, "BOOM",
                                   np.where(rvol > 1.0, "ELEVATED",
                                   np.where(rvol < 0.7, "QUIET", "NORMAL")))

            # Flow direction during volume event
            subset["flow_dir"] = np.where(vudr > 1.3, "BUY_FLOW",
                                  np.where(vudr < 0.7, "SELL_FLOW", "MIXED_FLOW"))

            # Trend context
            subset["trend"] = np.where(ts > 0.01, "BULL",
                               np.where(ts < -0.01, "BEAR", "FLAT"))

            print(f"\n    {signal[:3]} × {ticker}:")

            # Volume regime × win rate
            print(f"      Volume Regime:")
            for regime in ["QUIET", "NORMAL", "ELEVATED", "BOOM"]:
                mask = subset["vol_regime"] == regime
                if mask.sum() < 3: continue
                wr = subset.loc[mask, "is_win"].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"        {regime:>10s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

            # The MAGIC combo: volume regime × flow direction × trend
            print(f"      Volume × Flow × Trend:")
            for vol_reg in ["QUIET", "BOOM", "ELEVATED"]:
                for flow in ["BUY_FLOW", "SELL_FLOW"]:
                    for trend in ["BULL", "BEAR"]:
                        mask = ((subset["vol_regime"] == vol_reg) &
                                (subset["flow_dir"] == flow) &
                                (subset["trend"] == trend))
                        if mask.sum() < 3: continue
                        wr = subset.loc[mask, "is_win"].mean() * 100
                        cnt = mask.sum()
                        bar = "█" * int(wr / 5)
                        label = f"{vol_reg}+{flow}+{trend}"
                        # Detect the exhaustion → reversal pattern
                        marker = ""
                        if vol_reg == "BOOM" and flow == "BUY_FLOW" and trend == "BEAR":
                            marker = " ← BEAR EXHAUSTION + BUY BOOM" if wr > 55 else " ← BEAR+BUY BOOM"
                        elif vol_reg == "BOOM" and flow == "SELL_FLOW" and trend == "BULL":
                            marker = " ← BULL EXHAUSTION + SELL BOOM" if wr < 45 else ""
                        elif vol_reg == "QUIET" and trend == "BULL":
                            marker = " ← QUIET ACCUMULATION" if wr > 55 else ""
                        print(f"        {label:<35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

            # RVOL as continuous: high rvol in bear = exhaustion?
            print(f"      RVOL × Trend (continuous):")
            for trend in ["BULL", "BEAR"]:
                tmask = subset["trend"] == trend
                if tmask.sum() < 10: continue
                rv = rvol[tmask]
                y_t = subset.loc[tmask, "is_win"]
                r, pval = stats.pointbiserialr(y_t, rv)
                sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
                print(f"        {trend:>5s}: rvol×win r={r:+.4f} p={pval:.4f}{sig}")


# ════════════════════════════════════════════════════════════
# PART 2: PER-STOCK CALIBRATION — Optimal σ Windows
# ════════════════════════════════════════════════════════════

def per_stock_calibration(entry_df: pd.DataFrame):
    """Automatically detect optimal σ_wave entry window per ticker."""
    sp("PER-STOCK CALIBRATION: Optimal σ_wave Entry Windows")

    sigma_bins = [
        (-999, -2.5, "σ<-2.5 (extreme)"),
        (-2.5, -2.0, "σ -2.5→-2"),
        (-2.0, -1.5, "σ -2→-1.5"),
        (-1.5, -1.0, "σ -1.5→-1"),
        (-1.0, -0.5, "σ -1→-0.5"),
        (-0.5, 0.0, "σ -0.5→0"),
        (0.0, 0.5, "σ 0→+0.5"),
        (0.5, 1.0, "σ +0.5→+1"),
        (1.0, 999, "σ>+1"),
    ]

    all_tickers = entry_df["ticker"].unique()
    
    print(f"\n    ┌──────────────────────────────────────────────────────────────────┐")
    print(f"    │ σ_WAVE OPTIMAL WINDOW CALIBRATION (all signals, direction=1)     │")
    print(f"    └──────────────────────────────────────────────────────────────────┘")

    calibration_results = {}

    for ticker in sorted(all_tickers):
        subset = entry_df[
            (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
        ].copy()
        if len(subset) < 30: continue

        sw = subset["snap_sigma_wave"]
        y = subset["is_win"]

        print(f"\n    {ticker} (N={len(subset)}):")
        best_wr = 0
        best_window = ""
        best_n = 0

        for lo, hi, label in sigma_bins:
            mask = (sw >= lo) & (sw < hi)
            if mask.sum() < 3: continue
            wr = y[mask].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★ OPTIMAL" if wr > 60 and cnt >= 5 else \
                     " ✗ AVOID" if wr < 40 and cnt >= 5 else ""
            print(f"      {label:>20s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")
            if wr > best_wr and cnt >= 5:
                best_wr = wr
                best_window = label
                best_n = cnt

        # Find optimal contiguous window (sliding window of 2-3 adjacent bins)
        print(f"\n      Contiguous Window Search (2-3 adjacent bins):")
        best_contig_wr = 0
        best_contig_range = ""
        best_contig_n = 0

        for width in [2, 3]:
            for start in range(len(sigma_bins) - width + 1):
                lo = sigma_bins[start][0]
                hi = sigma_bins[start + width - 1][1]
                label_start = sigma_bins[start][2].split("(")[0].strip()
                label_end = sigma_bins[start + width - 1][2].split("(")[0].strip()
                mask = (sw >= lo) & (sw < hi)
                if mask.sum() < 8: continue
                wr = y[mask].mean() * 100
                cnt = mask.sum()
                range_label = f"[{lo:+.1f}, {hi:+.1f})"
                if wr > best_contig_wr and cnt >= 8:
                    best_contig_wr = wr
                    best_contig_range = range_label
                    best_contig_n = cnt
                if wr > 55 and cnt >= 8:
                    bar = "█" * int(wr / 5)
                    print(f"        {range_label:>15s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")

        calibration_results[ticker] = {
            "best_bin": best_window, "best_bin_wr": best_wr, "best_bin_n": best_n,
            "best_contig": best_contig_range, "best_contig_wr": best_contig_wr,
            "best_contig_n": best_contig_n,
        }

    # Summary table
    print(f"\n    ┌──────────────────────────────────────────────────────────────────┐")
    print(f"    │ CALIBRATION SUMMARY — Per-Stock Optimal Windows                  │")
    print(f"    └──────────────────────────────────────────────────────────────────┘")
    print(f"\n    {'Ticker':>8s} │ {'Best Single Bin':>20s} {'WR':>6s} {'N':>4s} │ {'Best Contiguous':>15s} {'WR':>6s} {'N':>4s}")
    print(f"    {'─'*80}")
    for ticker, cal in sorted(calibration_results.items()):
        print(f"    {ticker:>8s} │ {cal['best_bin']:>20s} {cal['best_bin_wr']:5.1f}% {cal['best_bin_n']:3d}  │ "
              f"{cal['best_contig']:>15s} {cal['best_contig_wr']:5.1f}% {cal['best_contig_n']:3d}")


# ════════════════════════════════════════════════════════════
# PART 3: FEATURE ABSORPTION — Is RC absorbed by Enhanced RSI?
# ════════════════════════════════════════════════════════════

def feature_absorption_analysis(entry_df: pd.DataFrame):
    """Test whether RC is fully absorbed by an enhanced RSI feature set."""
    sp("FEATURE ABSORPTION: RC vs Enhanced RSI")

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import cross_val_score
    except ImportError:
        print("    ⚠ sklearn not available")
        return

    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        # Get RSI signals and RC signals separately
        rsi_df = entry_df[
            (entry_df["ticker"] == ticker) &
            (entry_df["signal_name"] == "rsi_intelligence") &
            (entry_df["signal_direction"] == 1)
        ].copy()
        rc_df = entry_df[
            (entry_df["ticker"] == ticker) &
            (entry_df["signal_name"] == "regression_channel") &
            (entry_df["signal_direction"] == 1)
        ].copy()

        if len(rsi_df) < 30 or len(rc_df) < 30: continue

        print(f"\n    {ticker}: RSI signals={len(rsi_df)}, RC signals={len(rc_df)}")

        # Common features available in both
        common_feats = ["snap_tide_slope", "snap_tide_accel", "snap_sigma_wave",
                        "snap_sigma_tide", "snap_slope_conjugation", "snap_fear_level",
                        "snap_kalman_velocity", "snap_rvol", "snap_vol_up_down_ratio"]
        common_feats = [f for f in common_feats if f in rsi_df.columns and f in rc_df.columns]

        # RSI-specific features
        rsi_feats = common_feats + (["snap_rsi_value"] if "snap_rsi_value" in rsi_df.columns else [])

        # Test 1: RSI signal with RSI features only
        X_rsi = rsi_df[rsi_feats].dropna()
        y_rsi = rsi_df.loc[X_rsi.index, "is_win"]

        # Test 2: RC signal with common features
        X_rc = rc_df[common_feats].dropna()
        y_rc = rc_df.loc[X_rc.index, "is_win"]

        # Test 3: COMBINED (RSI + RC signals, with signal_name as feature)
        combined = pd.concat([rsi_df, rc_df])
        combined["is_rsi"] = (combined["signal_name"] == "rsi_intelligence").astype(int)
        X_comb = combined[common_feats + ["is_rsi"]].dropna()
        y_comb = combined.loc[X_comb.index, "is_win"]

        gb = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                         random_state=42, min_samples_leaf=5)

        if len(X_rsi) >= 30 and len(y_rsi.unique()) >= 2:
            rsi_score = cross_val_score(gb, X_rsi, y_rsi, cv=5, scoring="accuracy").mean()
            print(f"      RSI-only model:     acc={rsi_score:.3f}  (N={len(X_rsi)})")

        if len(X_rc) >= 30 and len(y_rc.unique()) >= 2:
            rc_score = cross_val_score(gb, X_rc, y_rc, cv=5, scoring="accuracy").mean()
            print(f"      RC-only model:      acc={rc_score:.3f}  (N={len(X_rc)})")

        if len(X_comb) >= 30 and len(y_comb.unique()) >= 2:
            comb_score = cross_val_score(gb, X_comb, y_comb, cv=5, scoring="accuracy").mean()
            print(f"      Combined model:     acc={comb_score:.3f}  (N={len(X_comb)})")

        # Test 4: Does adding signal_type improve the combined model?
        X_comb_no_signal = X_comb.drop(columns=["is_rsi"])
        if len(X_comb_no_signal) >= 30:
            no_signal_score = cross_val_score(gb, X_comb_no_signal, y_comb, cv=5, scoring="accuracy").mean()
            delta = comb_score - no_signal_score
            verdict = "★ RC ADDS VALUE" if delta > 0.01 else \
                      "~ MARGINAL" if delta > 0 else "❌ RC ABSORBED"
            print(f"      Without signal_type: acc={no_signal_score:.3f}  Δ={delta:+.4f}  {verdict}")

        # Test 5: Overlap analysis — how many signals fire at the same time?
        rsi_times = set(rsi_df["signal_time"].dt.normalize().values)
        rc_times = set(rc_df["signal_time"].dt.normalize().values)
        overlap = rsi_times & rc_times
        only_rsi = rsi_times - rc_times
        only_rc = rc_times - rsi_times
        
        total = len(rsi_times | rc_times)
        print(f"      Signal Overlap:")
        print(f"        Both fire:  {len(overlap):3d} ({len(overlap)/max(total,1)*100:.1f}%)")
        print(f"        RSI only:   {len(only_rsi):3d} ({len(only_rsi)/max(total,1)*100:.1f}%)")
        print(f"        RC only:    {len(only_rc):3d} ({len(only_rc)/max(total,1)*100:.1f}%)")

        # WR comparison for overlapping signals
        if len(overlap) >= 5:
            overlap_rsi = rsi_df[rsi_df["signal_time"].dt.normalize().isin(overlap)]
            overlap_rc = rc_df[rc_df["signal_time"].dt.normalize().isin(overlap)]
            if len(overlap_rsi) >= 5 and len(overlap_rc) >= 5:
                wr_rsi_overlap = overlap_rsi["is_win"].mean() * 100
                wr_rc_overlap = overlap_rc["is_win"].mean() * 100
                print(f"        When both fire: RSI WR={wr_rsi_overlap:.1f}%, RC WR={wr_rc_overlap:.1f}%")

        # RSI-only signals WR
        only_rsi_df = rsi_df[rsi_df["signal_time"].dt.normalize().isin(only_rsi)]
        only_rc_df = rc_df[rc_df["signal_time"].dt.normalize().isin(only_rc)]
        if len(only_rsi_df) >= 5:
            print(f"        RSI-only WR:  {only_rsi_df['is_win'].mean()*100:.1f}% (n={len(only_rsi_df)})")
        if len(only_rc_df) >= 5:
            print(f"        RC-only WR:   {only_rc_df['is_win'].mean()*100:.1f}% (n={len(only_rc_df)})")


# ════════════════════════════════════════════════════════════
# PART 4: ARCHITECTURE PROPOSAL — Monolith vs Modular
# ════════════════════════════════════════════════════════════

def architecture_analysis(entry_df: pd.DataFrame):
    """Analyze which features belong where in the architecture."""
    sp("ARCHITECTURE: Feature → Module Mapping")

    # For each feature, which signal uses it most effectively?
    features = ["snap_tide_slope", "snap_tide_accel", "snap_sigma_wave",
                "snap_sigma_tide", "snap_slope_conjugation", "snap_fear_level",
                "snap_kalman_velocity", "snap_rvol", "snap_vol_up_down_ratio",
                "snap_rsi_value", "snap_wave_slope"]

    print(f"\n    Feature Effectiveness Matrix (Cohen's d by signal × ticker):")
    print(f"    {'Feature':<25s} │ {'COST RSI':>10s} {'COST RC':>10s} {'SPY RSI':>10s} {'SPY RC':>10s} │ Best Owner")
    print(f"    {'─'*100}")

    for feat in features:
        ds = []
        for ticker in ["COST", "SPY"]:
            for signal in ["rsi_intelligence", "regression_channel"]:
                subset = entry_df[
                    (entry_df["ticker"] == ticker) &
                    (entry_df["signal_name"] == signal) &
                    (entry_df["signal_direction"] == 1)
                ]
                vals = subset[feat].dropna() if feat in subset.columns else pd.Series()
                wins = vals[subset.loc[vals.index, "is_win"] == 1] if len(vals) > 0 else pd.Series()
                losses = vals[subset.loc[vals.index, "is_win"] == 0] if len(vals) > 0 else pd.Series()
                if len(wins) >= 5 and len(losses) >= 5:
                    pooled = np.sqrt(((len(wins)-1)*wins.var() + (len(losses)-1)*losses.var()) /
                                     (len(wins)+len(losses)-2))
                    d = (wins.mean() - losses.mean()) / pooled if pooled > 0 else 0
                else:
                    d = 0
                ds.append(d)

        name = feat.replace("snap_", "")
        # Determine best owner based on where the effect is strongest
        labels = ["COST RSI", "COST RC", "SPY RSI", "SPY RC"]
        abs_ds = [abs(d) for d in ds]
        best_idx = abs_ds.index(max(abs_ds))
        best_owner = labels[best_idx]

        # Architecture recommendation
        if "rsi" in name:
            arch = "→ RSI Module"
        elif name in ("sigma_wave", "sigma_tide", "tide_slope", "tide_accel",
                       "slope_conjugation", "wave_slope", "fear_level"):
            arch = "→ RC Module (shared)"
        elif name in ("kalman_velocity",):
            arch = "→ Volume Module"
        elif name in ("rvol", "vol_up_down_ratio"):
            arch = "→ Volume Module"
        else:
            arch = "→ Shared"

        print(f"    {name:<25s} │ {ds[0]:+10.3f} {ds[1]:+10.3f} {ds[2]:+10.3f} {ds[3]:+10.3f} │ {best_owner} {arch}")

    # Proposed architecture
    print(f"""
    ┌──────────────────────────────────────────────────────────────────┐
    │ PROPOSED ARCHITECTURE: RSISuperPlus + ConfirmationLayer          │
    ├──────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │  LAYER 1: SignalGenerator (per indicator)                        │
    │    ├─ RSI Intelligence → fires when RSI condition met            │
    │    └─ RC Intelligence → fires when σ condition met               │
    │                                                                  │
    │  LAYER 2: ContextEnricher (SHARED — runs on ANY signal)          │
    │    ├─ tide_slope, tide_accel  (macro direction)                   │
    │    ├─ sigma_wave, sigma_tide  (position)                         │
    │    ├─ slope_conjugation       (micro-macro angle)                │
    │    ├─ fear_level              (sentiment encoding)               │
    │    ├─ kalman_velocity         (flow confirmation)                │
    │    ├─ rvol, vol_up_down_ratio (volume regime)                    │
    │    ├─ sigma_structure         (HH/HL/LH/LL from v3)             │
    │    └─ norm_trough_delta       (adaptive floor speed from v4)     │
    │                                                                  │
    │  LAYER 3: PerStockCalibrator (trained per ticker)                │
    │    ├─ Optimal σ window        (e.g. AAPL: [-2, -1])             │
    │    ├─ Pullback buyability     (trend-aware from v5)              │
    │    └─ Volume interpretation   (COST: +vol=good, SPY: +vol=bad)  │
    │                                                                  │
    │  LAYER 4: MetaLabeler (ML classifier)                            │
    │    ├─ Input: enriched context + calibrated thresholds            │
    │    ├─ Output: P(win | signal_fired, context)                     │
    │    └─ Method: Purged Walk-Forward CV (López de Prado)            │
    │                                                                  │
    └──────────────────────────────────────────────────────────────────┘
    """)


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v6 — FINAL AUDIT: Volume Variance + Calibration + Architecture")

    print("\n  Loading forensic labels...")
    entry_df = load_labels()
    print(f"  → {len(entry_df)} entry labels")

    # ═══ PART 1: Volume Variance ═══
    p("PART 1: VOLUME VARIANCE — Exhaustion → BOOM")
    volume_variance_analysis(entry_df)

    # ═══ PART 2: Per-Stock Calibration ═══
    p("PART 2: PER-STOCK CALIBRATION — Optimal σ Windows")
    per_stock_calibration(entry_df)

    # ═══ PART 3: Feature Absorption ═══
    p("PART 3: FEATURE ABSORPTION — Is RC absorbed by Enhanced RSI?")
    feature_absorption_analysis(entry_df)

    # ═══ PART 4: Architecture ═══
    p("PART 4: ARCHITECTURE PROPOSAL")
    architecture_analysis(entry_df)

    p("v6 FINAL AUDIT COMPLETE")
