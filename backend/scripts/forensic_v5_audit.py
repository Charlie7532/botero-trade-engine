#!/usr/bin/env python3
"""
Forensic Lab v5 — DEEP AUDIT: Wave Slope, Volume Regression, Pullback Classification
======================================================================================
Addresses System Architect's 4 critical comments:

  1. WAVE SLOPE AUDIT: Is it redundant with sigma_wave? Partial correlations,
     incremental value, fixed vs adaptive window comparison, angle between them.
  
  2. VOLUME/KALMAN TIDE SLOPE: Build regression slopes on volume and Kalman
     velocity series — do they carry independent signal?
  
  3. SLOPE VELOCITY: Rate of change between successive slope readings.
     The "acceleration of the acceleration" — second-order dynamics.
  
  4. TREND-AWARE PULLBACK CLASSIFICATION: In bull trends, classify pullbacks
     as "buyable" based on slingshot formation probability. In bear trends,
     classify advances as "continuable" based on exhaustion probability.
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

from backend.modules.quality_swing.domain.rules.regression_channel import (
    linreg_channel, sigma_position as calc_sigma,
)
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle

LONG_WINDOW = 200
FIXED_SHORT_WINDOW = 50  # Fixed wave window for comparison

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")


# ════════════════════════════════════════════════════════════
# DATA LOADERS
# ════════════════════════════════════════════════════════════

def load_ohlcv(ticker: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    df = pd.read_sql(
        "SELECT time, open, high, low, close, volume FROM market.ohlcv_bars "
        "WHERE ticker = %s ORDER BY time", conn, params=(ticker,))
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df


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
    df["is_win"] = df["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    for c in [col for col in df.columns if col.startswith("snap_")]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ════════════════════════════════════════════════════════════
# PART 1: WAVE SLOPE DEEP AUDIT
# Fixed vs Adaptive, Partial Correlations, Incremental Value
# ════════════════════════════════════════════════════════════

def compute_extended_series(close: np.ndarray, volume: np.ndarray):
    """Compute extended time series including fixed/adaptive wave slopes,
    volume regression, and slope velocity."""
    n = len(close)

    # Price-based series
    sigma_tide = np.full(n, np.nan)
    sigma_wave_adapt = np.full(n, np.nan)
    sigma_wave_fixed = np.full(n, np.nan)
    tide_slope = np.full(n, np.nan)
    wave_slope_adapt = np.full(n, np.nan)
    wave_slope_fixed = np.full(n, np.nan)

    # Volume regression series
    vol_tide_slope = np.full(n, np.nan)
    vol_wave_slope = np.full(n, np.nan)

    # Kalman-like: EMA of slope changes
    slope_velocity = np.full(n, np.nan)
    slope_accel = np.full(n, np.nan)

    dom_cycle = detect_dominant_cycle(close)
    adapt_window = max(10, min(dom_cycle, 60))

    for i in range(LONG_WINDOW + 5, n):
        pw = close[:i + 1]
        cp = close[i]

        # ── TIDE (200-bar) ──
        rv, ts, rs = linreg_channel(pw, LONG_WINDOW)
        sigma_tide[i] = calc_sigma(cp, rv, rs)
        tide_slope[i] = ts

        # ── WAVE ADAPTIVE (cycle-detected) ──
        if i >= adapt_window + 5:
            rv_a, ws_a, rs_a = linreg_channel(pw, adapt_window)
            sigma_wave_adapt[i] = calc_sigma(cp, rv_a, rs_a)
            wave_slope_adapt[i] = ws_a

        # ── WAVE FIXED (50-bar constant) ──
        if i >= FIXED_SHORT_WINDOW + 5:
            rv_f, ws_f, rs_f = linreg_channel(pw, FIXED_SHORT_WINDOW)
            sigma_wave_fixed[i] = calc_sigma(cp, rv_f, rs_f)
            wave_slope_fixed[i] = ws_f

        # ── VOLUME REGRESSION ──
        vol_window = volume[:i + 1]
        if len(vol_window) >= LONG_WINDOW:
            # Volume tide slope (200-bar regression on volume)
            v_y = vol_window[-LONG_WINDOW:]
            v_x = np.arange(LONG_WINDOW, dtype=float)
            v_xm, v_ym = v_x.mean(), v_y.mean()
            v_ssxx = np.sum((v_x - v_xm) ** 2)
            v_ssxy = np.sum((v_x - v_xm) * (v_y - v_ym))
            v_slope = v_ssxy / v_ssxx if v_ssxx > 0 else 0
            vol_tide_slope[i] = (v_slope / v_ym * 100) if v_ym > 0 else 0

        if len(vol_window) >= FIXED_SHORT_WINDOW:
            # Volume wave slope (50-bar)
            v_y = vol_window[-FIXED_SHORT_WINDOW:]
            v_x = np.arange(FIXED_SHORT_WINDOW, dtype=float)
            v_xm, v_ym = v_x.mean(), v_y.mean()
            v_ssxx = np.sum((v_x - v_xm) ** 2)
            v_ssxy = np.sum((v_x - v_xm) * (v_y - v_ym))
            v_slope = v_ssxy / v_ssxx if v_ssxx > 0 else 0
            vol_wave_slope[i] = (v_slope / v_ym * 100) if v_ym > 0 else 0

    # ── SLOPE VELOCITY: d(wave_slope)/dt ──
    for i in range(LONG_WINDOW + 10, n):
        if not np.isnan(wave_slope_adapt[i]) and not np.isnan(wave_slope_adapt[i-5]):
            slope_velocity[i] = wave_slope_adapt[i] - wave_slope_adapt[i-5]
        if not np.isnan(slope_velocity[i]) and not np.isnan(slope_velocity[i-5]):
            slope_accel[i] = slope_velocity[i] - slope_velocity[i-5]

    return {
        "sigma_tide": sigma_tide, "sigma_wave_adapt": sigma_wave_adapt,
        "sigma_wave_fixed": sigma_wave_fixed, "tide_slope": tide_slope,
        "wave_slope_adapt": wave_slope_adapt, "wave_slope_fixed": wave_slope_fixed,
        "vol_tide_slope": vol_tide_slope, "vol_wave_slope": vol_wave_slope,
        "slope_velocity": slope_velocity, "slope_accel": slope_accel,
    }


def wave_slope_audit(ticker: str, entry_df: pd.DataFrame):
    """Deep audit of wave_slope vs sigma_wave redundancy."""
    sp(f"WAVE SLOPE AUDIT: {ticker}")

    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    volume = ohlcv["volume"].values.astype(float)
    times = ohlcv["time"].values

    print(f"    Computing extended series (fixed/adaptive/volume/velocity)...")
    series = compute_extended_series(close, volume)

    # Get entry signals
    ticker_entries = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(ticker_entries) < 20: return

    # Map signals to bar indices and extract new features
    enriched = []
    for _, row in ticker_entries.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())

        if bar_idx < LONG_WINDOW + 15: continue

        rec = row.to_dict()
        rec["wave_slope_adapt"] = series["wave_slope_adapt"][bar_idx]
        rec["wave_slope_fixed"] = series["wave_slope_fixed"][bar_idx]
        rec["sigma_wave_adapt"] = series["sigma_wave_adapt"][bar_idx]
        rec["sigma_wave_fixed"] = series["sigma_wave_fixed"][bar_idx]
        rec["vol_tide_slope"] = series["vol_tide_slope"][bar_idx]
        rec["vol_wave_slope"] = series["vol_wave_slope"][bar_idx]
        rec["slope_velocity"] = series["slope_velocity"][bar_idx]
        rec["slope_accel"] = series["slope_accel"][bar_idx]

        # Angle between fixed and adaptive wave slopes
        ws_a = series["wave_slope_adapt"][bar_idx]
        ws_f = series["wave_slope_fixed"][bar_idx]
        if not np.isnan(ws_a) and not np.isnan(ws_f):
            rec["wave_slope_delta"] = ws_f - ws_a  # Fixed - Adaptive
            rec["wave_slope_ratio"] = ws_f / ws_a if abs(ws_a) > 0.001 else 0
        else:
            rec["wave_slope_delta"] = np.nan
            rec["wave_slope_ratio"] = np.nan

        # Volume slope conjugation (vol_wave - vol_tide)
        vws = series["vol_wave_slope"][bar_idx]
        vts = series["vol_tide_slope"][bar_idx]
        rec["vol_slope_conj"] = vws - vts if not (np.isnan(vws) or np.isnan(vts)) else np.nan

        enriched.append(rec)

    edf = pd.DataFrame(enriched)
    if len(edf) < 30: return

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal].copy()
        if len(sig_df) < 20: continue

        print(f"\n    ┌───────────────────────────────────────────────────────┐")
        print(f"    │ {signal} × {ticker} (N={len(sig_df)})")
        print(f"    └───────────────────────────────────────────────────────┘")

        # ── 1a. wave_slope vs sigma_wave: Partial Correlation ──
        print(f"\n    1a. PARTIAL CORRELATION (controlling for sigma_wave):")
        ws = sig_df["wave_slope_adapt"].dropna()
        sw = sig_df["sigma_wave_adapt"].dropna()
        y = sig_df.loc[ws.index & sw.index, "is_win"]
        common = ws.index & sw.index & y.index
        if len(common) > 20:
            ws_c, sw_c, y_c = ws[common], sw[common], y[common]
            # Bivariate
            r_ws, p_ws = stats.pointbiserialr(y_c, ws_c)
            r_sw, p_sw = stats.pointbiserialr(y_c, sw_c)
            print(f"      wave_slope vs win (bivariate):   r={r_ws:+.4f}  p={p_ws:.4f}")
            print(f"      sigma_wave vs win (bivariate):   r={r_sw:+.4f}  p={p_sw:.4f}")

            # Partial: wave_slope → win | sigma_wave
            from sklearn.linear_model import LinearRegression
            lr1 = LinearRegression().fit(sw_c.values.reshape(-1,1), ws_c.values)
            ws_resid = ws_c.values - lr1.predict(sw_c.values.reshape(-1,1))
            lr2 = LinearRegression().fit(sw_c.values.reshape(-1,1), y_c.values)
            y_resid = y_c.values - lr2.predict(sw_c.values.reshape(-1,1))
            r_partial, p_partial = stats.pearsonr(ws_resid, y_resid)
            print(f"      wave_slope → win | σ_wave:       r={r_partial:+.4f}  p={p_partial:.4f}")
            verdict = "★ INDEPENDENT INFO" if p_partial < 0.05 else \
                      "⚠ MARGINAL" if p_partial < 0.15 else "❌ REDUNDANT"
            print(f"      VERDICT: {verdict}")

        # ── 1b. Fixed vs Adaptive wave slope comparison ──
        print(f"\n    1b. FIXED (50-bar) vs ADAPTIVE ({detect_dominant_cycle(close)}-bar) wave slope:")
        for col, label in [("wave_slope_adapt", "Adaptive"),
                           ("wave_slope_fixed", "Fixed (50)")]:
            vals = sig_df[col].dropna()
            wins = vals[sig_df.loc[vals.index, "is_win"] == 1]
            losses = vals[sig_df.loc[vals.index, "is_win"] == 0]
            if len(wins) < 5 or len(losses) < 5: continue
            t, pval = stats.ttest_ind(wins, losses)
            print(f"      {label:>16s}: t={t:+6.3f}  p={pval:.4f}  μw={wins.mean():+.4f}  μl={losses.mean():+.4f}")

        # ── 1c. Angle between Fixed and Adaptive ──
        print(f"\n    1c. ANGLE between Fixed and Adaptive (wave_slope_delta = fixed - adaptive):")
        delta = sig_df["wave_slope_delta"].dropna()
        y_d = sig_df.loc[delta.index, "is_win"]
        if len(delta) > 15:
            r, pval = stats.pointbiserialr(y_d, delta)
            print(f"      Correlation with win: r={r:+.4f}  p={pval:.4f}")

            # Bucketize
            q33, q67 = delta.quantile(0.33), delta.quantile(0.67)
            for lo, hi, name in [(delta.min()-1, q33, "Fixed << Adapt (diverging)"),
                                  (q33, q67, "~Same (converging)"),
                                  (q67, delta.max()+1, "Fixed >> Adapt (fixed faster)")]:
                mask = (delta >= lo) & (delta < hi)
                if mask.sum() < 5: continue
                wr = y_d[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                print(f"        {name:>35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}")

        # ── 2. VOLUME REGRESSION SLOPES ──
        print(f"\n    2. VOLUME REGRESSION SLOPES:")
        for col, label in [("vol_tide_slope", "Volume Tide Slope (200-bar)"),
                           ("vol_wave_slope", "Volume Wave Slope (50-bar)"),
                           ("vol_slope_conj", "Volume Slope Conjugation (wave-tide)")]:
            vals = sig_df[col].dropna()
            y_v = sig_df.loc[vals.index, "is_win"]
            if len(vals) < 15: continue
            r, pval = stats.pointbiserialr(y_v, vals)
            wins = vals[y_v == 1]
            losses = vals[y_v == 0]
            print(f"      {label:>40s} │ r={r:+.4f}  p={pval:.4f}  μw={wins.mean():+.4f}  μl={losses.mean():+.4f}")

        # Volume slope buckets
        for col, label in [("vol_tide_slope", "vol_tide"),
                           ("vol_wave_slope", "vol_wave")]:
            vals = sig_df[col].dropna()
            y_v = sig_df.loc[vals.index, "is_win"]
            if len(vals) < 20: continue
            print(f"\n      {label} terciles:")
            q33, q67 = vals.quantile(0.33), vals.quantile(0.67)
            for lo, hi, name in [(vals.min()-1, q33, "Declining vol"),
                                  (q33, q67, "Stable vol"),
                                  (q67, vals.max()+1, "Rising vol")]:
                mask = (vals >= lo) & (vals < hi)
                if mask.sum() < 5: continue
                wr = y_v[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"        {name:>15s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── 3. SLOPE VELOCITY: d(wave_slope)/dt ──
        print(f"\n    3. SLOPE VELOCITY (Δ wave_slope over 5 bars):")
        sv = sig_df["slope_velocity"].dropna()
        y_sv = sig_df.loc[sv.index, "is_win"]
        if len(sv) > 15:
            r, pval = stats.pointbiserialr(y_sv, sv)
            print(f"      Correlation with win: r={r:+.4f}  p={pval:.4f}")

            q33, q67 = sv.quantile(0.33), sv.quantile(0.67)
            for lo, hi, name in [(sv.min()-1, q33, "Decelerating (slope falling)"),
                                  (q33, q67, "Stable slope"),
                                  (q67, sv.max()+1, "Accelerating (slope rising)")]:
                mask = (sv >= lo) & (sv < hi)
                if mask.sum() < 5: continue
                wr = y_sv[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"        {name:>35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Slope acceleration
        sa = sig_df["slope_accel"].dropna()
        y_sa = sig_df.loc[sa.index, "is_win"]
        if len(sa) > 15:
            r, pval = stats.pointbiserialr(y_sa, sa)
            print(f"      Slope Accel (d²/dt²): r={r:+.4f}  p={pval:.4f}")


# ════════════════════════════════════════════════════════════
# PART 2: TREND-AWARE PULLBACK/ADVANCE CLASSIFICATION
# ════════════════════════════════════════════════════════════

def pullback_classification(ticker: str, entry_df: pd.DataFrame):
    """Classify pullbacks in bull and advances in bear by buyability score."""
    sp(f"PULLBACK/ADVANCE CLASSIFICATION: {ticker}")

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 30: return

    ts = subset["snap_tide_slope"]
    ws = subset["snap_wave_slope"]
    sw = subset["snap_sigma_wave"]
    st = subset["snap_sigma_tide"]
    fl = subset["snap_fear_level"]
    kv = subset["snap_kalman_velocity"]
    sc = subset["snap_slope_conjugation"]

    for signal in subset["signal_name"].unique():
        sig_df = subset[subset["signal_name"] == signal]
        if len(sig_df) < 20: continue

        print(f"\n    ┌───────────────────────────────────────────────────────┐")
        print(f"    │ {signal} × {ticker} (N={len(sig_df)})")
        print(f"    └───────────────────────────────────────────────────────┘")

        ts_sig = sig_df["snap_tide_slope"]
        ws_sig = sig_df["snap_wave_slope"]
        sw_sig = sig_df["snap_sigma_wave"]
        fl_sig = sig_df["snap_fear_level"]
        sc_sig = sig_df["snap_slope_conjugation"]
        kv_sig = sig_df["snap_kalman_velocity"]

        # ── BULL PULLBACKS ──
        bull = ts_sig > 0.01  # Tide slope positive = bull trend
        if bull.sum() >= 10:
            print(f"\n    🐂 BULL PULLBACKS (tide_slope > 0.01, N={bull.sum()}):")

            # Pullback = wave_slope negative (micro dipping while macro rising)
            pullback = bull & (ws_sig < 0)
            no_pullback = bull & (ws_sig >= 0)

            if pullback.sum() >= 5:
                wr_pb = sig_df.loc[pullback, "is_win"].mean() * 100
                wr_no = sig_df.loc[no_pullback, "is_win"].mean() * 100 if no_pullback.sum() >= 3 else 0
                print(f"      Pullback (wave<0):    WR={wr_pb:5.1f}% n={pullback.sum():3d}")
                print(f"      No pullback (wave≥0): WR={wr_no:5.1f}% n={no_pullback.sum():3d}")

                # Depth classification
                print(f"\n      Pullback Depth (σ_wave during bull):")
                for lo, hi, name in [(-999, -2.0, "Deep pullback (σ<-2)"),
                                      (-2.0, -1.0, "Standard pullback (σ -2→-1)"),
                                      (-1.0, -0.5, "Shallow pullback (σ -1→-0.5)"),
                                      (-0.5, 0, "Minor dip (σ -0.5→0)")]:
                    mask = pullback & (sw_sig >= lo) & (sw_sig < hi)
                    if mask.sum() < 3: continue
                    wr = sig_df.loc[mask, "is_win"].mean() * 100
                    cnt = mask.sum()
                    bar = "█" * int(wr / 5)
                    marker = " ★ BUYABLE" if wr > 60 else " ✗ TRAP" if wr < 40 else ""
                    print(f"        {name:>35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

                # Slingshot formation: pullback + fear + sigma descending
                print(f"\n      Slingshot Formation (bull pullback + fear/sigma conditions):")
                for cond_mask, cond_label in [
                    (pullback & (fl_sig >= 3), "Pullback + Fear≥ANX"),
                    (pullback & (fl_sig >= 3) & (sw_sig < -1), "Pullback + Fear≥ANX + σ<-1"),
                    (pullback & (sc_sig < -0.02), "Pullback + Conj<-0.02 (deep angle)"),
                    (pullback & (kv_sig < 0), "Pullback + KV↓ (Kalman bearish)"),
                    (pullback & (kv_sig > 0), "Pullback + KV↑ (Kalman turning)"),
                    (pullback & (fl_sig >= 3) & (kv_sig > 0), "Pullback + Fear + KV↑ (SLINGSHOT)"),
                ]:
                    if cond_mask.sum() < 3: continue
                    wr = sig_df.loc[cond_mask, "is_win"].mean() * 100
                    cnt = cond_mask.sum()
                    bar = "█" * int(wr / 5)
                    marker = " ★ SLINGSHOT" if wr > 65 else ""
                    print(f"        {cond_label:<45s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── BEAR ADVANCES (going against trend) ──
        bear = ts_sig < -0.01  # Tide slope negative = bear trend
        if bear.sum() >= 10:
            print(f"\n    🐻 BEAR MARKET ENTRIES (tide_slope < -0.01, N={bear.sum()}):")

            # In bear, a BUY signal fires → is it a trap or a reversal?
            print(f"      Overall WR in bear: {sig_df.loc[bear, 'is_win'].mean()*100:.1f}%")

            # Classify by continuation probability
            print(f"\n      Reversal Confidence (bear → potential reversal):")
            for cond_mask, cond_label in [
                (bear & (ws_sig > 0), "Wave turning up (counter-trend)"),
                (bear & (ws_sig > 0) & (sw_sig < -1.5), "Wave up + deep σ"),
                (bear & (ws_sig > 0) & (fl_sig >= 4), "Wave up + Fear≥FEAR"),
                (bear & (ws_sig > 0) & (kv_sig > 0), "Wave up + KV↑ (confirmed turn)"),
                (bear & (ws_sig < 0) & (sw_sig < -2.0), "Wave still falling but σ<-2 (EXTREME)"),
                (bear & (sc_sig > 0.02), "Slope conjugation positive (wave > tide)"),
                (bear & (sc_sig > 0.02) & (fl_sig >= 4), "Conj+ + Fear≥FEAR (slingshot)"),
            ]:
                if cond_mask.sum() < 3: continue
                wr = sig_df.loc[cond_mask, "is_win"].mean() * 100
                cnt = cond_mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★ REVERSAL" if wr > 60 else " ✗ TRAP" if wr < 40 else ""
                print(f"        {cond_label:<45s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── FLAT TREND ──
        flat_trend = (ts_sig >= -0.01) & (ts_sig <= 0.01)
        if flat_trend.sum() >= 10:
            print(f"\n    ➡ FLAT TREND (|tide_slope| ≤ 0.01, N={flat_trend.sum()}):")
            print(f"      Overall WR: {sig_df.loc[flat_trend, 'is_win'].mean()*100:.1f}%")
            for cond_mask, cond_label in [
                (flat_trend & (sw_sig < -1.5), "σ<-1.5 (statistical extreme)"),
                (flat_trend & (ws_sig > 0) & (sw_sig < -1.0), "Wave turning + σ<-1"),
                (flat_trend & (fl_sig >= 3), "Fear≥ANX (contrarian)"),
            ]:
                if cond_mask.sum() < 3: continue
                wr = sig_df.loc[cond_mask, "is_win"].mean() * 100
                cnt = cond_mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else ""
                print(f"        {cond_label:<45s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# PART 3: INCREMENTAL VALUE TEST — Does adding new features
# improve on the v4 feature set?
# ════════════════════════════════════════════════════════════

def incremental_value_test(ticker: str, entry_df: pd.DataFrame):
    """Test if volume slope, slope velocity, and fixed-adaptive angle
    add incremental value over the existing feature set."""
    sp(f"INCREMENTAL VALUE TEST: {ticker}")

    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    volume = ohlcv["volume"].values.astype(float)
    times = ohlcv["time"].values

    print(f"    Computing extended series...")
    series = compute_extended_series(close, volume)

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 30: return

    # Map to bar indices and extract
    rows = []
    for _, row in subset.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())
        if bar_idx < LONG_WINDOW + 15: continue

        r = row.to_dict()
        r["vol_tide_slope"] = series["vol_tide_slope"][bar_idx]
        r["vol_wave_slope"] = series["vol_wave_slope"][bar_idx]
        r["slope_velocity"] = series["slope_velocity"][bar_idx]
        ws_a = series["wave_slope_adapt"][bar_idx]
        ws_f = series["wave_slope_fixed"][bar_idx]
        r["wave_angle"] = ws_f - ws_a if not (np.isnan(ws_a) or np.isnan(ws_f)) else np.nan
        rows.append(r)

    rdf = pd.DataFrame(rows)
    if len(rdf) < 30: return

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import cross_val_score

        # Base features (v4 final set)
        base_feats = ["snap_tide_slope", "snap_tide_accel", "snap_slope_conjugation",
                       "snap_sigma_wave", "snap_kalman_velocity", "snap_rvol",
                       "snap_vol_up_down_ratio"]
        base_feats = [f for f in base_feats if f in rdf.columns]

        # New candidate features
        new_feats = {
            "vol_tide_slope": "Volume Tide Slope (200-bar vol regression)",
            "vol_wave_slope": "Volume Wave Slope (50-bar vol regression)",
            "slope_velocity": "Slope Velocity (Δwave_slope/5 bars)",
            "wave_angle": "Wave Angle (fixed - adaptive slope)",
        }

        X_base = rdf[base_feats].apply(pd.to_numeric, errors="coerce").dropna()
        y = rdf.loc[X_base.index, "is_win"]

        if len(X_base) < 30: return

        gb = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                         random_state=42, min_samples_leaf=5)
        base_score = cross_val_score(gb, X_base, y, cv=5, scoring="accuracy").mean()
        print(f"\n    Base model (7 features): accuracy = {base_score:.3f}")

        for feat, label in new_feats.items():
            new_vals = rdf.loc[X_base.index, feat]
            new_vals = pd.to_numeric(new_vals, errors="coerce")
            valid = ~new_vals.isna()
            if valid.sum() < 30: continue

            X_new = X_base.loc[valid].copy()
            X_new[feat] = new_vals[valid].values
            y_new = y[valid]

            gb_new = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                                 random_state=42, min_samples_leaf=5)
            new_score = cross_val_score(gb_new, X_new, y_new, cv=5, scoring="accuracy").mean()
            delta = new_score - base_score
            marker = "★ ADD" if delta > 0.01 else "↑ marginal" if delta > 0 else "❌ no value"
            print(f"    + {label:<45s} acc={new_score:.3f}  Δ={delta:+.4f}  {marker}")

        # All new features combined
        all_new = list(new_feats.keys())
        valid_all = pd.Series(True, index=X_base.index)
        for f in all_new:
            nv = pd.to_numeric(rdf.loc[X_base.index, f], errors="coerce")
            valid_all = valid_all & ~nv.isna()
        if valid_all.sum() > 30:
            X_all = X_base.loc[valid_all].copy()
            for f in all_new:
                X_all[f] = pd.to_numeric(rdf.loc[valid_all.index[valid_all], f], errors="coerce").values
            y_all = y[valid_all]
            gb_all = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                                 random_state=42, min_samples_leaf=5)
            all_score = cross_val_score(gb_all, X_all, y_all, cv=5, scoring="accuracy").mean()
            delta = all_score - base_score
            marker = "★★ COMBINED VALUE" if delta > 0.02 else "★" if delta > 0.01 else "marginal"
            print(f"    + ALL NEW COMBINED                                  acc={all_score:.3f}  Δ={delta:+.4f}  {marker}")

            # Feature importances of the combined model
            gb_all.fit(X_all, y_all)
            importances = sorted(zip(X_all.columns, gb_all.feature_importances_),
                                 key=lambda x: x[1], reverse=True)
            print(f"\n    Feature Importances (combined model):")
            for name, imp in importances:
                clean = name.replace("snap_", "")
                bar = "█" * int(imp * 100)
                print(f"      {clean:<30s} imp={imp:.4f}  {bar}")

    except ImportError:
        print("    ⚠ sklearn not available")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v5 — WAVE SLOPE AUDIT + VOLUME REGRESSION + PULLBACK CLASSIFICATION")

    print("\n  Loading forensic labels...")
    entry_df = extract_labels("entry_forensic_labels")
    print(f"  → {len(entry_df)} entry labels")

    # ═══ PART 1+2: Wave Slope Audit + Volume/Velocity ═══
    p("PART 1: WAVE SLOPE DEEP AUDIT + VOLUME REGRESSION + SLOPE VELOCITY")
    for ticker in ["COST", "SPY"]:
        wave_slope_audit(ticker, entry_df)

    # ═══ PART 3: Pullback Classification ═══
    p("PART 2: TREND-AWARE PULLBACK/ADVANCE CLASSIFICATION")
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        pullback_classification(ticker, entry_df)

    # ═══ PART 4: Incremental Value Test ═══
    p("PART 3: INCREMENTAL VALUE TEST — Do new features improve the model?")
    for ticker in ["COST", "SPY"]:
        incremental_value_test(ticker, entry_df)

    p("v5 ANALYSIS COMPLETE")
    print("  Key questions answered:")
    print("    1. Is wave_slope redundant with sigma_wave? (Partial correlation)")
    print("    2. Does volume regression carry signal? (Volume tide/wave slopes)")
    print("    3. Does slope velocity add value? (d(wave_slope)/dt)")
    print("    4. Fixed vs adaptive angle? (Constant - adaptive wave slope)")
    print("    5. Pullback buyability in bull/bear/flat trends")
    print()
