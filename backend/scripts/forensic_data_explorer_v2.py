#!/usr/bin/env python3
"""
Forensic Data Explorer v2 — TREND-AWARE + DIRECTION-AWARE + ML
Incorporates user insights:
  1. RSI valid in OPPOSITE quadrant to trend
  2. σ_position is a PROCESS — direction matters (slingshot)
  3. Kalman + Volume CONFIRM the snap
  4. Slope conjugation detects floor/ceiling formation
  5. In uptrend, regressions are entries NOT exits
  6. ML to discover non-obvious interactions
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

# ════════════════════════════════════════════════════════════
# EXTRACT
# ════════════════════════════════════════════════════════════

def extract_labels(table_name: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT * FROM engine.{table_name}")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame()
    records = []
    for row in rows:
        flat = {
            "ticker": row["ticker"], "signal_name": row["signal_name"],
            "signal_direction": row["signal_direction"],
            "signal_confidence": row["signal_confidence"],
            "signal_time": row["signal_time"], "signal_price": row["signal_price"],
            "classification": row["classification"],
            "failure_diagnosis": row["failure_diagnosis"],
            "foreseeability": row["foreseeability"],
        }
        snap = row["snapshot"]
        if isinstance(snap, str): snap = json.loads(snap)
        if snap:
            for k, v in snap.items(): flat[f"snap_{k}"] = v
        horizons = row["horizons"]
        if isinstance(horizons, str): horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
                for metric, mval in h_val.items():
                    flat[f"h{h_key}_{metric}"] = mval
        records.append(flat)
    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    return df


def p(title): print(f"\n{'='*80}\n  {title}\n{'='*80}")
def sp(title): print(f"\n  ── {title} ──")


# ════════════════════════════════════════════════════════════
# DERIVED FEATURES — Trend context + Direction
# ════════════════════════════════════════════════════════════

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add trend-context and direction-derived features."""
    df = df.copy()

    # 1. Binary win
    df["is_win"] = df["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)

    # 2. Regime from snapshot
    if "snap_regime" in df.columns:
        df["regime"] = df["snap_regime"].fillna("FLAT")
    else:
        df["regime"] = "FLAT"

    # 3. Trend direction: BULL (SBULL+BULL), BEAR (SBEAR+BEAR), FLAT
    df["trend"] = df["regime"].map({
        "SBULL": "BULL", "BULL": "BULL",
        "FLAT": "FLAT",
        "BEAR": "BEAR", "SBEAR": "BEAR"
    }).fillna("FLAT")

    # 4. σ_wave DIRECTION — is it reversing or continuing?
    #    wave_slope > 0 = rising (potential slingshot from below)
    #    wave_slope < 0 = still falling
    if "snap_wave_slope" in df.columns:
        ws = pd.to_numeric(df["snap_wave_slope"], errors="coerce")
        df["wave_direction"] = np.where(ws > 0.05, "RISING",
                               np.where(ws < -0.05, "FALLING", "FLAT"))

    # 5. Slingshot detection: σ deep + direction reversing
    if "snap_sigma_wave" in df.columns and "snap_wave_flip" in df.columns:
        sw = pd.to_numeric(df["snap_sigma_wave"], errors="coerce")
        wf = df["snap_wave_flip"]
        wfd = pd.to_numeric(df.get("snap_wave_flip_direction", 0), errors="coerce")
        df["slingshot_buy"] = (sw < -1.0) & (wf == True) & (wfd == 1)
        df["slingshot_sell"] = (sw > 1.0) & (wf == True) & (wfd == -1)

    # 6. Floor/ceiling formation: slope_conjugation narrowing toward zero
    if "snap_slope_conjugation" in df.columns:
        sc = pd.to_numeric(df["snap_slope_conjugation"], errors="coerce")
        df["floor_forming"] = (sc < -0.1) & (sc > -0.4)  # converging from below
        df["ceiling_forming"] = (sc > 0.1) & (sc < 0.4)  # converging from above

    # 7. Kalman confirmation
    if "snap_kalman_velocity" in df.columns:
        kv = pd.to_numeric(df["snap_kalman_velocity"], errors="coerce")
        df["kalman_bullish"] = kv > 0.005
        df["kalman_bearish"] = kv < -0.005

    # 8. Volume confirmation
    if "snap_rvol" in df.columns and "snap_vol_up_down_ratio" in df.columns:
        rvol = pd.to_numeric(df["snap_rvol"], errors="coerce")
        vudr = pd.to_numeric(df["snap_vol_up_down_ratio"], errors="coerce")
        df["vol_accumulation"] = (vudr > 1.0) & (rvol > 0.8)
        df["vol_distribution"] = (vudr < 0.9) & (rvol > 0.8)

    return df


# ════════════════════════════════════════════════════════════
# ANALYSIS 1: TREND-AWARE RSI ANALYSIS
# ════════════════════════════════════════════════════════════

def analyze_rsi_by_trend(df: pd.DataFrame, ticker: str):
    """RSI readings in the OPPOSITE quadrant to trend are most valid."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == "rsi_intelligence") &
                (df["signal_direction"] == 1)].copy()
    n = len(subset)
    if n < 10: return

    sp(f"RSI × {ticker} — TREND-AWARE ANALYSIS ({n} signals)")

    # RSI by Trend Regime
    print(f"\n    Win Rate by Trend Regime:")
    for trend in ["BULL", "FLAT", "BEAR"]:
        mask = subset["trend"] == trend
        if mask.sum() < 3: continue
        wr = subset.loc[mask, "is_win"].mean() * 100
        cnt = mask.sum()
        bar = "█" * int(wr / 5)
        print(f"      {trend:>6s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")

    # RSI in OPPOSITE quadrant to trend
    if "snap_rsi_value" in subset.columns:
        rsi = pd.to_numeric(subset["snap_rsi_value"], errors="coerce")

        # In BEAR trend: RSI in upper zone (40-60) = lower highs = trend continuation
        # In BULL trend: RSI in lower zone (30-40) = higher lows = bounce
        print(f"\n    RSI Quadrant vs Trend (opposite quadrant theory):")

        # BEAR + RSI 40-60 (the valid bear zone)
        mask_bear_valid = (subset["trend"] == "BEAR") & (rsi >= 40) & (rsi <= 60)
        if mask_bear_valid.sum() >= 3:
            wr = subset.loc[mask_bear_valid, "is_win"].mean() * 100
            print(f"      BEAR + RSI 40-60 (bear continuation) │ WR={wr:5.1f}% n={mask_bear_valid.sum():3d}")

        # BEAR + RSI < 30 (oversold in downtrend)
        mask_bear_os = (subset["trend"] == "BEAR") & (rsi < 30)
        if mask_bear_os.sum() >= 3:
            wr = subset.loc[mask_bear_os, "is_win"].mean() * 100
            print(f"      BEAR + RSI < 30  (oversold in bear)  │ WR={wr:5.1f}% n={mask_bear_os.sum():3d}")

        # BULL + RSI 30-40 (healthy pullback in uptrend)
        mask_bull_pb = (subset["trend"] == "BULL") & (rsi >= 30) & (rsi <= 40)
        if mask_bull_pb.sum() >= 3:
            wr = subset.loc[mask_bull_pb, "is_win"].mean() * 100
            print(f"      BULL + RSI 30-40 (pullback in bull)   │ WR={wr:5.1f}% n={mask_bull_pb.sum():3d}")

        # BULL + RSI 40-50 (mild pullback)
        mask_bull_mild = (subset["trend"] == "BULL") & (rsi >= 40) & (rsi <= 50)
        if mask_bull_mild.sum() >= 3:
            wr = subset.loc[mask_bull_mild, "is_win"].mean() * 100
            print(f"      BULL + RSI 40-50 (mild pullback bull) │ WR={wr:5.1f}% n={mask_bull_mild.sum():3d}")

        # FLAT + RSI < 40 (ranging — mean reversion candidate)
        mask_flat_low = (subset["trend"] == "FLAT") & (rsi < 40)
        if mask_flat_low.sum() >= 3:
            wr = subset.loc[mask_flat_low, "is_win"].mean() * 100
            print(f"      FLAT + RSI < 40  (range mean-revert)  │ WR={wr:5.1f}% n={mask_flat_low.sum():3d}")


# ════════════════════════════════════════════════════════════
# ANALYSIS 2: SLINGSHOT DETECTION
# ════════════════════════════════════════════════════════════

def analyze_slingshot(df: pd.DataFrame, ticker: str, signal: str):
    """σ deep + direction reversing + Kalman/volume confirmation."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal) &
                (df["signal_direction"] == 1)].copy()
    n = len(subset)
    if n < 10: return

    sp(f"SLINGSHOT ANALYSIS: {signal} × {ticker} ({n} signals)")

    # σ_wave direction matters
    if "wave_direction" in subset.columns:
        print(f"\n    Win Rate by σ_wave Position × Direction:")
        sw = pd.to_numeric(subset["snap_sigma_wave"], errors="coerce")

        for zone, lo, hi in [("Deep oversold (<-1σ)", -999, -1.0),
                              ("Mild oversold (-1→0)", -1.0, 0.0),
                              ("Neutral (0→1)", 0.0, 1.0),
                              ("Extended (>1σ)", 1.0, 999)]:
            mask_zone = (sw >= lo) & (sw < hi)
            if mask_zone.sum() < 3: continue

            for direction in ["RISING", "FLAT", "FALLING"]:
                mask_dir = subset["wave_direction"] == direction
                combined = mask_zone & mask_dir
                if combined.sum() < 3: continue
                wr = subset.loc[combined, "is_win"].mean() * 100
                cnt = combined.sum()
                marker = " ← SLINGSHOT!" if (lo < -0.5 and direction == "RISING" and wr > 55) else \
                         " ← KNIFE" if (lo < -0.5 and direction == "FALLING" and wr < 45) else ""
                bar = "█" * int(wr / 5)
                print(f"      {zone:>22s} + {direction:>7s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

    # Slingshot flag (wave_flip + deep σ)
    if "slingshot_buy" in subset.columns:
        sling = subset["slingshot_buy"] == True
        if sling.sum() >= 3:
            wr = subset.loc[sling, "is_win"].mean() * 100
            print(f"\n    🏹 SLINGSHOT BUY (σ<-1 + flip + dir=+1): WR={wr:5.1f}% n={sling.sum()}")

            # With Kalman confirmation
            if "kalman_bullish" in subset.columns:
                sling_kalman = sling & (subset["kalman_bullish"] == True)
                if sling_kalman.sum() >= 3:
                    wr_k = subset.loc[sling_kalman, "is_win"].mean() * 100
                    print(f"      + Kalman ↑ confirmation:              WR={wr_k:5.1f}% n={sling_kalman.sum()}")

            # With volume confirmation
            if "vol_accumulation" in subset.columns:
                sling_vol = sling & (subset["vol_accumulation"] == True)
                if sling_vol.sum() >= 3:
                    wr_v = subset.loc[sling_vol, "is_win"].mean() * 100
                    print(f"      + Volume accumulation:                WR={wr_v:5.1f}% n={sling_vol.sum()}")

            # Triple confirmation: slingshot + Kalman + volume
            if "kalman_bullish" in subset.columns and "vol_accumulation" in subset.columns:
                triple = sling & (subset["kalman_bullish"] == True) & (subset["vol_accumulation"] == True)
                if triple.sum() >= 2:
                    wr_t = subset.loc[triple, "is_win"].mean() * 100
                    print(f"      + Kalman ↑ + Volume (triple):         WR={wr_t:5.1f}% n={triple.sum()} ★")


# ════════════════════════════════════════════════════════════
# ANALYSIS 3: FLOOR/CEILING FORMATION
# ════════════════════════════════════════════════════════════

def analyze_floor_ceiling(df: pd.DataFrame, ticker: str, signal: str):
    """Slope conjugation detects floor/ceiling formation."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal) &
                (df["signal_direction"] == 1)].copy()
    n = len(subset)
    if n < 10: return

    sp(f"FLOOR/CEILING FORMATION: {signal} × {ticker}")

    if "snap_slope_conjugation" not in subset.columns: return
    sc = pd.to_numeric(subset["snap_slope_conjugation"], errors="coerce")
    ts = pd.to_numeric(subset.get("snap_tide_slope", 0), errors="coerce")
    ws = pd.to_numeric(subset.get("snap_wave_slope", 0), errors="coerce")

    print(f"\n    Slope Pair Analysis (tide_slope × wave_slope → conjugation):")

    # Case 1: Tide flat/down, wave turning up → FLOOR FORMING
    floor_mask = (ts < 0.05) & (ws > 0)
    if floor_mask.sum() >= 3:
        wr = subset.loc[floor_mask, "is_win"].mean() * 100
        print(f"      Tide ≤flat + Wave ↑ (FLOOR FORMING)   │ WR={wr:5.1f}% n={floor_mask.sum()}")

    # Case 2: Tide up, wave turning down → CEILING FORMING
    ceiling_mask = (ts > 0.05) & (ws < 0)
    if ceiling_mask.sum() >= 3:
        wr = subset.loc[ceiling_mask, "is_win"].mean() * 100
        print(f"      Tide ↑ + Wave ↓ (CEILING FORMING)     │ WR={wr:5.1f}% n={ceiling_mask.sum()}")

    # Case 3: Both slopes same direction → TREND CONTINUATION
    same_up = (ts > 0.05) & (ws > 0)
    if same_up.sum() >= 3:
        wr = subset.loc[same_up, "is_win"].mean() * 100
        print(f"      Tide ↑ + Wave ↑ (TREND CONTINUATION)  │ WR={wr:5.1f}% n={same_up.sum()}")

    same_down = (ts < -0.05) & (ws < 0)
    if same_down.sum() >= 3:
        wr = subset.loc[same_down, "is_win"].mean() * 100
        print(f"      Tide ↓ + Wave ↓ (DOWNTREND ACCEL)     │ WR={wr:5.1f}% n={same_down.sum()}")

    # Case 4: Conjugation magnitude + acceleration → speed of convergence
    if "snap_tide_accel" in subset.columns:
        ta = pd.to_numeric(subset["snap_tide_accel"], errors="coerce")
        # Acceleration turning (tide deceleration = potential turn)
        decel = (ts < 0) & (ta > 0)  # Downtrend decelerating
        if decel.sum() >= 3:
            wr = subset.loc[decel, "is_win"].mean() * 100
            print(f"      Tide ↓ but DECELERATING (turn ahead?) │ WR={wr:5.1f}% n={decel.sum()}")

        accel_up = (ts > 0) & (ta > 0)  # Uptrend accelerating
        if accel_up.sum() >= 3:
            wr = subset.loc[accel_up, "is_win"].mean() * 100
            print(f"      Tide ↑ + ACCELERATING                 │ WR={wr:5.1f}% n={accel_up.sum()}")


# ════════════════════════════════════════════════════════════
# ANALYSIS 4: KALMAN + WYCKOFF STATE TRANSITIONS
# ════════════════════════════════════════════════════════════

def analyze_kalman_transitions(df: pd.DataFrame, ticker: str, signal: str):
    """When does Kalman signal the start of the next move?"""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal) &
                (df["signal_direction"] == 1)].copy()
    n = len(subset)
    if n < 10: return

    sp(f"KALMAN STATE × DIRECTION: {signal} × {ticker}")

    if "snap_wyckoff_state" not in subset.columns or "snap_kalman_velocity" not in subset.columns:
        return

    kv = pd.to_numeric(subset["snap_kalman_velocity"], errors="coerce")

    print(f"\n    Wyckoff State × Kalman Velocity Direction:")
    for state in sorted(subset["snap_wyckoff_state"].dropna().unique()):
        mask_state = subset["snap_wyckoff_state"] == state
        if mask_state.sum() < 3: continue

        # Kalman turning bullish from this state
        kalman_up = mask_state & (kv > 0.005)
        kalman_down = mask_state & (kv < -0.005)
        kalman_flat = mask_state & (kv.abs() <= 0.005)

        for label, mask in [("KV↑", kalman_up), ("KV→", kalman_flat), ("KV↓", kalman_down)]:
            if mask.sum() < 2: continue
            wr = subset.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            marker = " ★" if (state == "CONSOLIDATION" and label == "KV↑" and wr > 55) else \
                     " ★" if (state == "ACCUMULATION" and label == "KV↑" and wr > 55) else ""
            bar = "█" * int(wr / 5)
            print(f"      {state:>16s} + {label} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# ANALYSIS 5: TREND-AWARE EXIT ANALYSIS
# ════════════════════════════════════════════════════════════

def analyze_exits_by_trend(df: pd.DataFrame, ticker: str, signal: str):
    """In uptrend, regressions are entries NOT exits."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal)].copy()
    n = len(subset)
    if n < 5: return

    subset["is_save"] = subset["classification"].isin(["SAVED_US", "GOOD_WARNING"]).astype(int)

    sp(f"EXIT TREND-AWARE: {signal} × {ticker} ({n} signals)")

    # Save rate by trend regime
    print(f"\n    Save Rate by Trend Regime:")
    for trend in ["BULL", "FLAT", "BEAR"]:
        mask = subset["trend"] == trend
        if mask.sum() < 3: continue
        sr = subset.loc[mask, "is_save"].mean() * 100
        cnt = mask.sum()
        bar = "█" * int(sr / 5)
        note = " ← EXPECTED: exits wrong here" if (trend == "BULL" and sr < 30) else \
               " ← EXPECTED: exits valid here" if (trend == "BEAR" and sr > 40) else ""
        print(f"      {trend:>6s} │ SR={sr:5.1f}% n={cnt:3d}  {bar}{note}")

    # σ_wave overextension analysis for exits
    if "snap_sigma_wave" in subset.columns:
        sw = pd.to_numeric(subset["snap_sigma_wave"], errors="coerce")
        print(f"\n    Save Rate by σ_wave (exit = leaving channel?):")
        for zone, lo, hi in [("Deep below (<-1.5σ)", -999, -1.5),
                              ("Below (-1.5→-0.5σ)", -1.5, -0.5),
                              ("Center (-0.5→0.5σ)", -0.5, 0.5),
                              ("Above (0.5→1.5σ)", 0.5, 1.5),
                              ("Extended (>1.5σ)", 1.5, 999)]:
            mask = (sw >= lo) & (sw < hi)
            if mask.sum() < 3: continue
            sr = subset.loc[mask, "is_save"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(sr / 5)
            marker = " ← EXIT VALID" if (hi >= 1.5 and sr > 35) else \
                     " ← EXIT WRONG" if (lo < -0.5 and sr < 25) else ""
            print(f"      {zone:>25s} │ SR={sr:5.1f}% n={cnt:3d}  {bar}{marker}")

    # Euphoria / black swan detection
    if "snap_sigma_wave" in subset.columns and "snap_fear_level" in subset.columns:
        sw = pd.to_numeric(subset["snap_sigma_wave"], errors="coerce")
        fl = pd.to_numeric(subset["snap_fear_level"], errors="coerce")

        # Euphoria exit: σ_wave > 1.5 + GREED = valid exit (correction coming)
        euphoria = (sw > 1.5) & (fl <= 1)
        if euphoria.sum() >= 2:
            sr = subset.loc[euphoria, "is_save"].mean() * 100
            print(f"\n    🎪 EUPHORIA EXIT (σ>1.5 + GREED/CONF):     SR={sr:5.1f}% n={euphoria.sum()}")

        # Panic exit: σ_wave < -1.5 + PANIC = likely wrong (oversold bounce)
        panic_exit = (sw < -1.5) & (fl >= 4)
        if panic_exit.sum() >= 2:
            sr = subset.loc[panic_exit, "is_save"].mean() * 100
            print(f"    😱 PANIC EXIT (σ<-1.5 + FEAR/PANIC):       SR={sr:5.1f}% n={panic_exit.sum()}")


# ════════════════════════════════════════════════════════════
# ANALYSIS 6: ML FEATURE IMPORTANCE (Random Forest)
# ════════════════════════════════════════════════════════════

def ml_feature_importance(df: pd.DataFrame, ticker: str, signal: str, direction: int):
    """Quick Random Forest to find non-obvious feature interactions."""
    label = "Entry" if direction == 1 else "Exit"
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal) &
                (df["signal_direction"] == direction)].copy()
    n = len(subset)
    if n < 30: return

    if direction == 1:
        subset["target"] = subset["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    else:
        subset["target"] = subset["classification"].isin(["SAVED_US", "GOOD_WARNING"]).astype(int)

    features = ["snap_sigma_tide", "snap_sigma_wave", "snap_tide_slope", "snap_wave_slope",
                "snap_tide_accel", "snap_rvol", "snap_vol_up_down_ratio",
                "snap_slope_conjugation", "snap_fear_level"]
    if "snap_rsi_value" in subset.columns: features.append("snap_rsi_value")
    if "snap_kalman_velocity" in subset.columns: features.append("snap_kalman_velocity")

    available = [f for f in features if f in subset.columns]
    X = subset[available].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = subset["target"]

    if len(y.unique()) < 2: return

    try:
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.inspection import permutation_importance

        sp(f"ML FEATURE IMPORTANCE: {signal} × {ticker} ({label}, n={n})")

        # Random Forest
        rf = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=42, min_samples_leaf=5)
        cv_scores = cross_val_score(rf, X, y, cv=min(5, n // 10), scoring="accuracy")
        rf.fit(X, y)

        print(f"\n    Random Forest CV Accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
        print(f"    (Baseline random: {y.mean():.3f})")

        # Permutation importance (MDA — López de Prado preferred)
        perm = permutation_importance(rf, X, y, n_repeats=30, random_state=42)
        feat_imp = sorted(zip([f.replace("snap_", "") for f in available],
                              perm.importances_mean, perm.importances_std),
                          key=lambda x: abs(x[1]), reverse=True)

        print(f"\n    Permutation Importance (MDA):")
        for fname, imp, std in feat_imp:
            sig = "***" if imp > 0.02 else "**" if imp > 0.01 else "*" if imp > 0.005 else ""
            bar = "█" * int(imp * 200) if imp > 0 else ""
            print(f"      {fname:<28s} MDA={imp:+.4f} ± {std:.4f}  {bar} {sig}")

        # Gradient Boosting for interaction detection
        gb = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42,
                                         min_samples_leaf=5, learning_rate=0.1)
        cv_gb = cross_val_score(gb, X, y, cv=min(5, n // 10), scoring="accuracy")
        gb.fit(X, y)

        print(f"\n    Gradient Boosting CV Accuracy: {cv_gb.mean():.3f} ± {cv_gb.std():.3f}")

        # Built-in feature importance (MDI)
        gb_imp = sorted(zip([f.replace("snap_", "") for f in available],
                            gb.feature_importances_), key=lambda x: x[1], reverse=True)
        print(f"    MDI (Tree-Based):")
        for fname, imp in gb_imp[:6]:
            bar = "█" * int(imp * 50)
            print(f"      {fname:<28s} MDI={imp:.4f}  {bar}")

    except ImportError:
        print("    ⚠ scikit-learn not available for ML analysis")


# ════════════════════════════════════════════════════════════
# ANALYSIS 7: COMBINED EDGE MATRIX
# ════════════════════════════════════════════════════════════

def combined_edge_matrix(df: pd.DataFrame, ticker: str, signal: str):
    """Test all meaningful combined conditions for entry signals."""
    subset = df[(df["ticker"] == ticker) & (df["signal_name"] == signal) &
                (df["signal_direction"] == 1)].copy()
    n = len(subset)
    if n < 20: return

    sp(f"COMBINED EDGE MATRIX: {signal} × {ticker} ({n} signals)")

    sw = pd.to_numeric(subset.get("snap_sigma_wave", 0), errors="coerce")
    fl = pd.to_numeric(subset.get("snap_fear_level", 2), errors="coerce")
    kv = pd.to_numeric(subset.get("snap_kalman_velocity", 0), errors="coerce")
    rvol = pd.to_numeric(subset.get("snap_rvol", 1), errors="coerce")
    vudr = pd.to_numeric(subset.get("snap_vol_up_down_ratio", 1), errors="coerce")
    ws = pd.to_numeric(subset.get("snap_wave_slope", 0), errors="coerce")
    sc = pd.to_numeric(subset.get("snap_slope_conjugation", 0), errors="coerce")
    rsi = pd.to_numeric(subset.get("snap_rsi_value", 50), errors="coerce")
    wf = subset.get("snap_wave_flip", False)
    wfd = pd.to_numeric(subset.get("snap_wave_flip_direction", 0), errors="coerce")

    conditions = []

    # Slingshot: deep σ + flip + Kalman confirmation
    m = (sw < -1.0) & (wf == True) & (wfd == 1) & (kv > 0)
    if m.sum() >= 3: conditions.append(("σ<-1 + flip↑ + Kalman↑", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Deep σ + Fear + Volume accumulation
    m = (sw < -1.0) & (fl >= 3) & (vudr > 1.0)
    if m.sum() >= 3: conditions.append(("σ<-1 + Fear≥ANX + VolAccum", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Floor forming + Kalman turning
    m = (sc < -0.1) & (sc > -0.4) & (kv > 0)
    if m.sum() >= 3: conditions.append(("Floor forming + Kalman↑", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Wave rising from deep + RVOL high
    m = (sw < -0.5) & (ws > 0) & (rvol > 1.0)
    if m.sum() >= 3: conditions.append(("σ<-0.5 + wave↑ + RVOL>1", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # RSI < 35 + Fear elevated
    m = (rsi < 35) & (fl >= 3)
    if m.sum() >= 3: conditions.append(("RSI<35 + Fear≥ANXIETY", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Deep σ + wave turning + Kalman + volume (FULL CONFLUENCE)
    m = (sw < -1.0) & (ws > 0) & (kv > 0) & (vudr > 0.9)
    if m.sum() >= 2: conditions.append(("★ FULL: σ<-1+wave↑+KV↑+Vol", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Fear + below VWAP + RVOL
    bv = subset.get("snap_below_vwap", False)
    m = (fl >= 3) & (bv == True) & (rvol > 0.8)
    if m.sum() >= 3: conditions.append(("Fear≥ANX + <VWAP + RVOL>0.8", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Conjugation strong negative + wave flip
    m = (sc < -0.3) & (wf == True) & (wfd == 1)
    if m.sum() >= 3: conditions.append(("Conj<-0.3 + flip↑", m.sum(),
                                         subset.loc[m, "is_win"].mean() * 100))

    # Sort by WR descending
    conditions.sort(key=lambda x: x[2], reverse=True)
    print()
    for cond, cnt, wr in conditions:
        bar = "█" * int(wr / 5)
        marker = " ← EDGE!" if wr > 65 else " ← promising" if wr > 55 else ""
        print(f"      {cond:<38s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v2 — TREND-AWARE + DIRECTION + SLINGSHOT + ML")

    print("\n  Extracting from Neon...")
    entry_df = enrich(extract_labels("entry_forensic_labels"))
    exit_df = enrich(extract_labels("exit_forensic_labels"))
    print(f"  → {len(entry_df)} entry + {len(exit_df)} exit = {len(entry_df)+len(exit_df)} total labels")

    # ═══ ENTRIES ═══
    p("PART 1: TREND-AWARE RSI ANALYSIS")
    for ticker in ["COST", "AAPL", "SPY", "QQQ"]:
        analyze_rsi_by_trend(entry_df, ticker)

    p("PART 2: SLINGSHOT DETECTION (σ direction + Kalman + Volume)")
    for ticker in ["COST", "AAPL", "SPY", "QQQ"]:
        for sig in ["rsi_intelligence", "regression_channel"]:
            analyze_slingshot(entry_df, ticker, sig)

    p("PART 3: FLOOR/CEILING FORMATION (Slope Pair Analysis)")
    for ticker in ["COST", "AAPL", "SPY", "QQQ"]:
        for sig in ["rsi_intelligence", "regression_channel"]:
            analyze_floor_ceiling(entry_df, ticker, sig)

    p("PART 4: KALMAN STATE TRANSITIONS")
    for ticker in ["COST", "AAPL", "SPY", "QQQ"]:
        for sig in ["rsi_intelligence", "regression_channel"]:
            analyze_kalman_transitions(entry_df, ticker, sig)

    p("PART 5: COMBINED EDGE MATRIX — Entry Confluences")
    for ticker in ["COST", "AAPL", "SPY", "QQQ"]:
        for sig in ["rsi_intelligence", "regression_channel"]:
            combined_edge_matrix(entry_df, ticker, sig)

    # ═══ EXITS ═══
    p("PART 6: TREND-AWARE EXIT ANALYSIS")
    for ticker in ["COST", "AAPL", "SPY", "QQQ"]:
        for sig in ["rsi_intelligence", "regression_channel"]:
            analyze_exits_by_trend(exit_df, ticker, sig)

    # ═══ ML ═══
    p("PART 7: ML FEATURE IMPORTANCE (Random Forest + Gradient Boosting)")
    for ticker in ["COST", "SPY"]:  # Focus on best tollkeeper + best index
        for sig in ["rsi_intelligence", "regression_channel"]:
            ml_feature_importance(entry_df, ticker, sig, direction=1)

    p("PART 8: ML EXIT FEATURE IMPORTANCE")
    for ticker in ["COST", "SPY"]:
        for sig in ["regression_channel"]:  # RC has most exit data
            ml_feature_importance(exit_df, ticker, sig, direction=-1)

    p("ANALYSIS COMPLETE")
