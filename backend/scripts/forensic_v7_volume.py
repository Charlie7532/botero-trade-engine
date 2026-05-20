#!/usr/bin/env python3
"""
Forensic Lab v7 — VOLUME THESES + RSI DIVERGENCE + PRICE-VOLUME DIVERGENCE
============================================================================
Final calibration round:
  1. Volume exhaustion → BOOM (vol-of-vol, dryness → spike detection)
  2. RSI divergence reconstruction (missing from forensic labels)
  3. Price-volume divergence (price direction ≠ volume direction)
  4. Volume regime transitions as signal
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

from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")


def load_ohlcv(ticker: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    df = pd.read_sql(
        "SELECT time, open, high, low, close, volume FROM market.ohlcv_bars "
        "WHERE ticker = %s ORDER BY time", conn, params=(ticker,))
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df


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
# PART 1: VOLUME EXHAUSTION → BOOM
# Vol-of-vol, dryness measurement, spike detection
# ════════════════════════════════════════════════════════════

def volume_exhaustion_analysis(ticker: str, entry_df: pd.DataFrame):
    sp(f"VOLUME EXHAUSTION → BOOM: {ticker}")

    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    volume = ohlcv["volume"].values.astype(float)
    times = ohlcv["time"].values
    n = len(close)

    # Compute volume features for every bar
    vol_sma20 = np.full(n, np.nan)
    vol_sma50 = np.full(n, np.nan)
    vol_std20 = np.full(n, np.nan)  # Vol-of-vol (std of volume)
    vol_cv20 = np.full(n, np.nan)   # Coefficient of variation
    vol_dryness = np.full(n, np.nan)  # How many consecutive bars below avg
    vol_spike = np.full(n, np.nan)    # Current bar vs previous 5-bar avg

    for i in range(50, n):
        vol_sma20[i] = np.mean(volume[i-20:i])
        vol_sma50[i] = np.mean(volume[i-50:i])
        vol_std20[i] = np.std(volume[i-20:i])
        vol_cv20[i] = vol_std20[i] / vol_sma20[i] if vol_sma20[i] > 0 else 0

        # Dryness: consecutive bars below 80% of 20-bar SMA
        dry_count = 0
        for j in range(i, max(i-20, 49), -1):
            if volume[j] < vol_sma20[i] * 0.8:
                dry_count += 1
            else:
                break
        vol_dryness[i] = dry_count

        # Spike: current bar volume vs mean of previous 5 bars
        prev_avg = np.mean(volume[max(0, i-5):i])
        vol_spike[i] = volume[i] / prev_avg if prev_avg > 0 else 1.0

    # Map to entry signals
    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 20: return

    enriched = []
    for _, row in subset.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())
        if bar_idx < 55: continue

        rec = row.to_dict()
        rec["vol_cv20"] = vol_cv20[bar_idx]
        rec["vol_dryness"] = vol_dryness[bar_idx]
        rec["vol_spike"] = vol_spike[bar_idx]
        rec["vol_sma_ratio"] = vol_sma20[bar_idx] / vol_sma50[bar_idx] if vol_sma50[bar_idx] > 0 else 1.0

        # Exhaustion pattern: dryness in previous bars THEN spike at signal
        # Look back 5 bars for dryness, then see if current bar spikes
        dry_before = vol_dryness[max(bar_idx-5, 50)]
        spike_now = vol_spike[bar_idx]
        rec["exhaustion_score"] = dry_before * spike_now  # Dryness × Spike magnitude

        enriched.append(rec)

    edf = pd.DataFrame(enriched)
    if len(edf) < 20: return

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 15: continue

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # ── Vol-of-Vol (CV) ──
        print(f"      Vol-of-Vol (Coefficient of Variation):")
        cv = sig_df["vol_cv20"].dropna()
        y = sig_df.loc[cv.index, "is_win"]
        if len(cv) > 15:
            r, pval = stats.pointbiserialr(y, cv)
            print(f"        r={r:+.4f}  p={pval:.4f}")
            q33, q67 = cv.quantile(0.33), cv.quantile(0.67)
            for lo, hi, name in [(cv.min()-1, q33, "Low CV (steady vol)"),
                                  (q33, q67, "Medium CV"),
                                  (q67, cv.max()+1, "High CV (erratic vol)")]:
                mask = (cv >= lo) & (cv < hi)
                if mask.sum() < 3: continue
                wr = y[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"          {name:>25s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Dryness ──
        print(f"      Volume Dryness (consecutive bars < 80% SMA):")
        dry = sig_df["vol_dryness"].dropna()
        y_d = sig_df.loc[dry.index, "is_win"]
        if len(dry) > 15:
            r, pval = stats.pointbiserialr(y_d, dry)
            print(f"        r={r:+.4f}  p={pval:.4f}")
            for lo, hi, name in [(0, 1, "No dryness (0 bars)"),
                                  (1, 3, "Mild dryness (1-2 bars)"),
                                  (3, 6, "Dry spell (3-5 bars)"),
                                  (6, 99, "Extended drought (6+)")]:
                mask = (dry >= lo) & (dry < hi)
                if mask.sum() < 3: continue
                wr = y_d[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★ EXHAUSTION" if wr > 60 else ""
                print(f"          {name:>30s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Volume Spike ──
        print(f"      Volume Spike (current bar / prev 5-bar avg):")
        spike = sig_df["vol_spike"].dropna()
        y_s = sig_df.loc[spike.index, "is_win"]
        if len(spike) > 15:
            r, pval = stats.pointbiserialr(y_s, spike)
            print(f"        r={r:+.4f}  p={pval:.4f}")
            for lo, hi, name in [(0, 0.7, "Volume drying up"),
                                  (0.7, 1.2, "Normal volume"),
                                  (1.2, 2.0, "Elevated spike"),
                                  (2.0, 99, "BOOM (2x+ spike)")]:
                mask = (spike >= lo) & (spike < hi)
                if mask.sum() < 3: continue
                wr = y_s[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★ BOOM" if wr > 60 and name == "BOOM (2x+ spike)" else \
                         " ★" if wr > 60 else ""
                print(f"          {name:>25s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Exhaustion Score (Dryness × Spike) ──
        print(f"      Exhaustion Score (dryness × spike):")
        exh = sig_df["exhaustion_score"].dropna()
        y_e = sig_df.loc[exh.index, "is_win"]
        if len(exh) > 15:
            r, pval = stats.pointbiserialr(y_e, exh)
            print(f"        r={r:+.4f}  p={pval:.4f}")
            # Top 20% exhaustion score
            q80 = exh.quantile(0.80)
            high_exh = exh >= q80
            if high_exh.sum() >= 3:
                wr_high = y_e[high_exh].mean() * 100
                wr_low = y_e[~high_exh].mean() * 100
                print(f"          Top 20% exhaustion: WR={wr_high:5.1f}% n={high_exh.sum()}")
                print(f"          Bottom 80%:         WR={wr_low:5.1f}% n={(~high_exh).sum()}")


# ════════════════════════════════════════════════════════════
# PART 2: RSI DIVERGENCE RECONSTRUCTION
# ════════════════════════════════════════════════════════════

def rsi_divergence_analysis(ticker: str, entry_df: pd.DataFrame):
    sp(f"RSI DIVERGENCE RECONSTRUCTION: {ticker}")

    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    times = ohlcv["time"].values

    rsi_intel = RSIIntelligence()

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 20: return

    enriched = []
    for _, row in subset.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())
        if bar_idx < 55: continue

        # Use enough history for divergence detection
        close_window = close[:bar_idx + 1]
        result = rsi_intel.analyze(close_window)

        rec = row.to_dict()
        rec["div_type"] = result.divergence_type
        rec["div_strength"] = result.divergence_strength
        rec["rsi_conviction"] = result.rsi_conviction
        rec["rsi_zone"] = result.rsi_zone
        rec["rsi_regime"] = result.rsi_regime
        rec["slope_alignment"] = result.slope_alignment
        rec["price_slope"] = result.price_slope
        rec["rsi_slope"] = result.rsi_slope
        enriched.append(rec)

    edf = pd.DataFrame(enriched)
    if len(edf) < 20: return

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 15: continue

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # ── Divergence Type WR ──
        print(f"      Divergence Type:")
        for dtype in ["NONE", "POSITIVE_REVERSAL", "NEGATIVE_REVERSAL",
                       "CLASSIC_BULLISH_DIV", "CLASSIC_BEARISH_DIV"]:
            mask = sig_df["div_type"] == dtype
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
            print(f"        {dtype:<25s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Divergence Strength (continuous) ──
        has_div = sig_df["div_type"] != "NONE"
        if has_div.sum() >= 5:
            div_df = sig_df[has_div]
            r, pval = stats.pointbiserialr(div_df["is_win"], div_df["div_strength"])
            print(f"      Div Strength × Win: r={r:+.4f}  p={pval:.4f}")

        # ── RSI Conviction Score ──
        conv = sig_df["rsi_conviction"].dropna()
        y_c = sig_df.loc[conv.index, "is_win"]
        if len(conv) > 15:
            r, pval = stats.pointbiserialr(y_c, conv)
            print(f"      RSI Conviction × Win: r={r:+.4f}  p={pval:.4f}")
            q33, q67 = conv.quantile(0.33), conv.quantile(0.67)
            for lo, hi, name in [(conv.min()-1, q33, "Low conviction (bearish)"),
                                  (q33, q67, "Medium conviction"),
                                  (q67, conv.max()+1, "High conviction (bullish)")]:
                mask = (conv >= lo) & (conv < hi)
                if mask.sum() < 3: continue
                wr = y_c[mask].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"          {name:>30s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Slope Alignment ──
        print(f"      Slope Alignment (price vs RSI):")
        for align in ["ALIGNED", "DIVERGING", "CONVERGING"]:
            mask = sig_df["slope_alignment"] == align
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
            print(f"        {align:<15s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Combined: Divergence + Fear + σ ──
        print(f"      Divergence Combos:")
        for cond_mask, cond_label in [
            (has_div, "Any divergence"),
            (has_div & (sig_df["snap_fear_level"] >= 3), "Divergence + Fear≥ANX"),
            (has_div & (sig_df["snap_sigma_wave"] < -1), "Divergence + σ<-1"),
            (has_div & (sig_df["snap_fear_level"] >= 3) & (sig_df["snap_sigma_wave"] < -1),
             "Divergence + Fear + σ<-1"),
            ((sig_df["div_type"] == "POSITIVE_REVERSAL"), "POSITIVE_REVERSAL only"),
            ((sig_df["div_type"] == "CLASSIC_BULLISH_DIV"), "CLASSIC_BULLISH only"),
        ]:
            if cond_mask.sum() < 3: continue
            wr = sig_df.loc[cond_mask, "is_win"].mean() * 100
            cnt = cond_mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★ SLINGSHOT" if wr > 65 else ""
            print(f"        {cond_label:<35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# PART 3: PRICE-VOLUME DIVERGENCE
# ════════════════════════════════════════════════════════════

def price_volume_divergence(ticker: str, entry_df: pd.DataFrame):
    sp(f"PRICE-VOLUME DIVERGENCE: {ticker}")

    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    volume = ohlcv["volume"].values.astype(float)
    times = ohlcv["time"].values
    n = len(close)

    # Compute 10-bar slopes for price and volume
    price_slope_10 = np.full(n, np.nan)
    vol_slope_10 = np.full(n, np.nan)

    for i in range(10, n):
        x = np.arange(10, dtype=float)
        # Price slope (normalized)
        py = close[i-10:i]
        px_mean, py_mean = x.mean(), py.mean()
        ssxx = np.sum((x - px_mean)**2)
        ssxy = np.sum((x - px_mean) * (py - py_mean))
        ps = ssxy / ssxx if ssxx > 0 else 0
        price_slope_10[i] = ps / py_mean * 100 if py_mean > 0 else 0

        # Volume slope (normalized)
        vy = volume[i-10:i]
        vy_mean = vy.mean()
        ssxy_v = np.sum((x - px_mean) * (vy - vy_mean))
        vs = ssxy_v / ssxx if ssxx > 0 else 0
        vol_slope_10[i] = vs / vy_mean * 100 if vy_mean > 0 else 0

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 20: return

    enriched = []
    for _, row in subset.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())
        if bar_idx < 55: continue

        rec = row.to_dict()
        ps = price_slope_10[bar_idx]
        vs = vol_slope_10[bar_idx]
        rec["price_slope_10"] = ps
        rec["vol_slope_10"] = vs

        # Divergence: price falling but volume rising (accumulation)
        # or price rising but volume falling (distribution/exhaustion)
        if not (np.isnan(ps) or np.isnan(vs)):
            if ps < -0.05 and vs > 0.5:
                rec["pv_div"] = "ACCUMULATION"  # Price↓ Vol↑
            elif ps > 0.05 and vs < -0.5:
                rec["pv_div"] = "DISTRIBUTION"  # Price↑ Vol↓
            elif ps < -0.05 and vs < -0.5:
                rec["pv_div"] = "CAPITULATION"  # Price↓ Vol↓ (selling exhaustion)
            elif ps > 0.05 and vs > 0.5:
                rec["pv_div"] = "CONFIRMATION"  # Price↑ Vol↑ (healthy trend)
            else:
                rec["pv_div"] = "NEUTRAL"
        else:
            rec["pv_div"] = "NEUTRAL"

        enriched.append(rec)

    edf = pd.DataFrame(enriched)
    if len(edf) < 20: return

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 15: continue

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # Price-Volume Divergence Types
        print(f"      Price-Volume Divergence:")
        for pv_type in ["ACCUMULATION", "CAPITULATION", "CONFIRMATION", "DISTRIBUTION", "NEUTRAL"]:
            mask = sig_df["pv_div"] == pv_type
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
            emoji = {"ACCUMULATION": "📥", "CAPITULATION": "💀",
                     "CONFIRMATION": "✅", "DISTRIBUTION": "📤",
                     "NEUTRAL": "➡"}.get(pv_type, "")
            print(f"        {emoji} {pv_type:<15s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Combined with trend
        ts = sig_df["snap_tide_slope"]
        print(f"\n      PV Divergence × Trend:")
        for pv_type in ["ACCUMULATION", "CAPITULATION"]:
            for trend, trend_label in [(ts > 0.01, "BULL"), (ts < -0.01, "BEAR")]:
                mask = (sig_df["pv_div"] == pv_type) & trend
                if mask.sum() < 3: continue
                wr = sig_df.loc[mask, "is_win"].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★ SIGNAL" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"        {pv_type}+{trend_label:<5s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v7 — VOLUME THESES + RSI DIVERGENCE + PV DIVERGENCE")

    print("\n  Loading forensic labels...")
    entry_df = load_labels()
    print(f"  → {len(entry_df)} entry labels")

    p("PART 1: VOLUME EXHAUSTION → BOOM (Vol-of-Vol + Dryness + Spike)")
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        volume_exhaustion_analysis(ticker, entry_df)

    p("PART 2: RSI DIVERGENCE RECONSTRUCTION")
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        rsi_divergence_analysis(ticker, entry_df)

    p("PART 3: PRICE-VOLUME DIVERGENCE")
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        price_volume_divergence(ticker, entry_df)

    p("v7 ANALYSIS COMPLETE")
