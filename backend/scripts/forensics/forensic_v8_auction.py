#!/usr/bin/env python3
"""
Forensic Lab v8 — AUCTION PSYCHOLOGY + VOLUME-SIGMA CORRELATIONS
=================================================================
Addressing 4 System Architect comments:
  1. AAPL high CV: correlate with sigma extremes (maximos/minimos)
  2. Telebolito: dryness × sigma × fear × kalman (the ping-pong)
  3. BOOM direction: who's driving? Buy/sell flow × sigma position
  4. Auction psychology: WHERE in σ range does volume event occur?
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


def enrich_volume(ticker: str, entry_df: pd.DataFrame) -> pd.DataFrame:
    """Add volume features from OHLCV to entry labels."""
    ohlcv = load_ohlcv(ticker)
    close = ohlcv["close"].values.astype(float)
    volume = ohlcv["volume"].values.astype(float)
    times = ohlcv["time"].values
    n = len(close)

    # Precompute volume features
    vol_sma20 = np.full(n, np.nan)
    vol_std20 = np.full(n, np.nan)
    vol_cv20 = np.full(n, np.nan)
    vol_dryness = np.full(n, np.nan)
    vol_spike = np.full(n, np.nan)
    # Price range (ATR-like) for auction context
    atr14 = np.full(n, np.nan)

    for i in range(50, n):
        vol_sma20[i] = np.mean(volume[i-20:i])
        vol_std20[i] = np.std(volume[i-20:i])
        vol_cv20[i] = vol_std20[i] / vol_sma20[i] if vol_sma20[i] > 0 else 0

        dry_count = 0
        for j in range(i, max(i-20, 49), -1):
            if volume[j] < vol_sma20[i] * 0.8:
                dry_count += 1
            else:
                break
        vol_dryness[i] = dry_count

        prev_avg = np.mean(volume[max(0, i-5):i])
        vol_spike[i] = volume[i] / prev_avg if prev_avg > 0 else 1.0

        # ATR(14)
        if i >= 14:
            trs = []
            for j in range(i-14, i):
                tr = max(close[j] - close[j-1] if j > 0 else 0,
                         abs(close[j] - close[j-1]) if j > 0 else 0)
                tr = max(tr, ohlcv["high"].values[j] - ohlcv["low"].values[j])
                trs.append(tr)
            atr14[i] = np.mean(trs)

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 20:
        return pd.DataFrame()

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
        rec["atr14"] = atr14[bar_idx]

        # Auction: price range relative to ATR (was the bar narrow or wide?)
        bar_range = ohlcv["high"].values[bar_idx] - ohlcv["low"].values[bar_idx]
        rec["bar_range_ratio"] = bar_range / atr14[bar_idx] if atr14[bar_idx] > 0 else 1.0

        # Volume direction context at signal
        rec["bar_direction"] = 1 if close[bar_idx] >= ohlcv["open"].values[bar_idx] else -1

        enriched.append(rec)

    return pd.DataFrame(enriched) if enriched else pd.DataFrame()


# ════════════════════════════════════════════════════════════
# PART 1: AAPL CV × SIGMA EXTREMES
# "Como correlaciona con nuestros momentos, maximos y minimos"
# ════════════════════════════════════════════════════════════

def cv_sigma_correlation(edf: pd.DataFrame, ticker: str):
    sp(f"CV × SIGMA EXTREMES: {ticker}")

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 20: continue

        cv = sig_df["vol_cv20"].dropna()
        sw = sig_df["snap_sigma_wave"]
        ts = sig_df["snap_tide_slope"]
        y = sig_df["is_win"]

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # σ position buckets
        sigma_zones = [
            (sw < -1.5, "σ DEEP (<-1.5)"),
            ((sw >= -1.5) & (sw < -0.5), "σ MID-LOW (-1.5→-0.5)"),
            ((sw >= -0.5) & (sw < 0.5), "σ NEUTRAL (-0.5→+0.5)"),
            (sw >= 0.5, "σ HIGH (>+0.5)"),
        ]

        # CV terciles
        q33 = cv.quantile(0.33)
        q67 = cv.quantile(0.67)
        cv_zones = [
            (cv <= q33, "Low CV"),
            ((cv > q33) & (cv <= q67), "Med CV"),
            (cv > q67, "High CV"),
        ]

        print(f"      CV × σ Position (Win Rate):")
        print(f"      {'':>20s} │ {'Low CV':>10s} {'Med CV':>10s} {'High CV':>10s}")
        print(f"      {'─'*60}")

        for sigma_mask, sigma_name in sigma_zones:
            row_vals = []
            for cv_mask, cv_name in cv_zones:
                combined = sigma_mask & cv_mask
                n = combined.sum()
                if n >= 3:
                    wr = y[combined].mean() * 100
                    marker = "★" if wr > 60 else "✗" if wr < 40 else " "
                    row_vals.append(f"{wr:5.1f}%{marker}({n:2d})")
                else:
                    row_vals.append(f"  {'—':>5s}    ")
            print(f"      {sigma_name:>20s} │ {row_vals[0]:>10s} {row_vals[1]:>10s} {row_vals[2]:>10s}")

        # Trend × CV
        print(f"\n      Trend × CV:")
        print(f"      {'':>12s} │ {'Low CV':>10s} {'Med CV':>10s} {'High CV':>10s}")
        print(f"      {'─'*50}")
        for trend_mask, trend_name in [(ts > 0.01, "BULL"), (ts < -0.01, "BEAR")]:
            row_vals = []
            for cv_mask, cv_name in cv_zones:
                combined = trend_mask & cv_mask
                n = combined.sum()
                if n >= 3:
                    wr = y[combined].mean() * 100
                    marker = "★" if wr > 60 else "✗" if wr < 40 else " "
                    row_vals.append(f"{wr:5.1f}%{marker}({n:2d})")
                else:
                    row_vals.append(f"  {'—':>5s}    ")
            print(f"      {trend_name:>12s} │ {row_vals[0]:>10s} {row_vals[1]:>10s} {row_vals[2]:>10s}")


# ════════════════════════════════════════════════════════════
# PART 2: TELEBOLITO — Dryness × σ × Fear × Kalman
# "El ping-pong sin volumen que busca zona de interés"
# ════════════════════════════════════════════════════════════

def telebolito_analysis(edf: pd.DataFrame, ticker: str):
    sp(f"TELEBOLITO — Dryness × Context: {ticker}")

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 20: continue

        dry = sig_df["vol_dryness"]
        sw = sig_df["snap_sigma_wave"]
        fear = sig_df["snap_fear_level"]
        kv = sig_df["snap_kalman_velocity"]
        ts = sig_df["snap_tide_slope"]
        y = sig_df["is_win"]

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # Dryness levels
        dry_levels = [
            (dry == 0, "No drought (0)"),
            ((dry >= 1) & (dry <= 2), "Mild (1-2)"),
            ((dry >= 3) & (dry <= 5), "Dry spell (3-5)"),
            (dry >= 6, "Extended (6+)"),
        ]

        # What happens when dry? Where is sigma? Where is fear?
        print(f"      Dryness × σ Position:")
        for dry_mask, dry_name in dry_levels:
            if dry_mask.sum() < 3: continue
            # σ stats during this dryness
            sw_dry = sw[dry_mask].dropna()
            y_dry = y[dry_mask]
            if len(sw_dry) < 3: continue
            wr = y_dry.mean() * 100
            sigma_mean = sw_dry.mean()
            sigma_std = sw_dry.std()
            print(f"        {dry_name:>18s} │ WR={wr:5.1f}% n={dry_mask.sum():3d}  "
                  f"σ_mean={sigma_mean:+.2f}  σ_std={sigma_std:.2f}")

        # The telebolito question: when dry, does σ direction predict?
        print(f"\n      Dryness × σ Direction (the ping-pong):")
        has_drought = dry >= 1
        if has_drought.sum() >= 10:
            # During drought: is σ above or below zero?
            dry_df = sig_df[has_drought]
            for cond_mask, cond_name in [
                (dry_df["snap_sigma_wave"] < -1, "Drought + σ<-1 (bouncing at FLOOR)"),
                ((dry_df["snap_sigma_wave"] >= -1) & (dry_df["snap_sigma_wave"] < 0),
                 "Drought + σ[-1,0) (mid-low)"),
                ((dry_df["snap_sigma_wave"] >= 0) & (dry_df["snap_sigma_wave"] < 1),
                 "Drought + σ[0,+1) (mid-high)"),
                (dry_df["snap_sigma_wave"] >= 1, "Drought + σ≥+1 (at CEILING)"),
            ]:
                if cond_mask.sum() < 3: continue
                wr = dry_df.loc[cond_mask, "is_win"].mean() * 100
                cnt = cond_mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"          {cond_name:<45s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Drought + Fear: the telebolito in panic
        print(f"\n      Dryness × Fear Level:")
        if has_drought.sum() >= 10:
            dry_df = sig_df[has_drought]
            for fl, fl_name in [(0, "CALM"), (1, "CAUTION"), (2, "FEAR"),
                                (3, "ANXIETY"), (4, "PANIC")]:
                mask = dry_df["snap_fear_level"] == fl
                if mask.sum() < 3: continue
                wr = dry_df.loc[mask, "is_win"].mean() * 100
                cnt = mask.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"          Drought+{fl_name:<10s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Drought + Kalman velocity: is the filter seeing direction?
        print(f"\n      Dryness × Kalman Velocity:")
        if has_drought.sum() >= 10:
            dry_df = sig_df[has_drought]
            kv_dry = dry_df["snap_kalman_velocity"].dropna()
            if len(kv_dry) >= 10:
                for cond_mask, cond_name in [
                    (kv_dry < -0.1, "KV falling (sellers winning)"),
                    ((kv_dry >= -0.1) & (kv_dry <= 0.1), "KV flat (equilibrium)"),
                    (kv_dry > 0.1, "KV rising (buyers winning)"),
                ]:
                    if cond_mask.sum() < 3: continue
                    wr = dry_df.loc[kv_dry[cond_mask].index, "is_win"].mean() * 100
                    cnt = cond_mask.sum()
                    bar = "█" * int(wr / 5)
                    marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                    print(f"          {cond_name:<35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# PART 3: BOOM DIRECTION — Who's driving? At what σ?
# "Cuando hay volumen hay compra-vendedores o vende-compradores"
# ════════════════════════════════════════════════════════════

def boom_direction_analysis(edf: pd.DataFrame, ticker: str):
    sp(f"BOOM DIRECTION — Flow × σ × Trend: {ticker}")

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 20: continue

        spike = sig_df["vol_spike"]
        vudr = sig_df["snap_vol_up_down_ratio"]
        sw = sig_df["snap_sigma_wave"]
        ts = sig_df["snap_tide_slope"]
        bar_dir = sig_df["bar_direction"]
        y = sig_df["is_win"]

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # Volume regimes
        vol_regimes = [
            (spike < 0.7, "QUIET (<0.7x)"),
            ((spike >= 0.7) & (spike < 1.2), "NORMAL"),
            ((spike >= 1.2) & (spike < 2.0), "ELEVATED"),
            (spike >= 2.0, "BOOM (2x+)"),
        ]

        # Flow direction at signal bar
        flow_types = [
            ((vudr > 1.2) & (bar_dir > 0), "BUY FLOW (vudr>1.2 + green bar)"),
            ((vudr < 0.8) & (bar_dir < 0), "SELL FLOW (vudr<0.8 + red bar)"),
            (True, "ALL"),  # Will be used as reference
        ]

        print(f"      Vol Regime × Flow Direction × σ Position:")
        for vol_mask, vol_name in vol_regimes:
            if vol_mask.sum() < 5: continue
            print(f"\n        {vol_name}:")

            for flow_mask, flow_name in flow_types[:2]:  # Skip ALL for this view
                combined = vol_mask & flow_mask
                if combined.sum() < 3: continue

                # Where in σ are they?
                sw_here = sw[combined].dropna()
                y_here = y[combined]
                wr = y_here.mean() * 100
                sigma_mean = sw_here.mean() if len(sw_here) > 0 else 0

                # σ split
                deep = combined & (sw < -1)
                mid = combined & (sw >= -1) & (sw < 0)
                high = combined & (sw >= 0)

                parts = []
                for zone_mask, zone_name in [(deep, "σ<-1"), (mid, "σ[-1,0)"), (high, "σ≥0")]:
                    if zone_mask.sum() >= 3:
                        z_wr = y[zone_mask].mean() * 100
                        z_marker = "★" if z_wr > 60 else "✗" if z_wr < 40 else ""
                        parts.append(f"{zone_name}={z_wr:.0f}%{z_marker}(n={zone_mask.sum()})")

                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"          {flow_name:<40s} │ WR={wr:5.1f}% n={combined.sum():3d}  "
                      f"σ̄={sigma_mean:+.2f}{marker}")
                if parts:
                    print(f"            ↳ {' | '.join(parts)}")

        # The key question: BOOM at σ extremes — floor or ceiling?
        print(f"\n      BOOM/ELEVATED at σ Extremes (floor vs ceiling):")
        big_vol = (spike >= 1.2)
        for cond_mask, cond_name in [
            (big_vol & (sw < -1.5) & (bar_dir > 0),
             "High vol + σ<-1.5 + GREEN bar → FLOOR FOUND?"),
            (big_vol & (sw < -1.5) & (bar_dir < 0),
             "High vol + σ<-1.5 + RED bar → FLOOR BREAKING?"),
            (big_vol & (sw > 1.0) & (bar_dir > 0),
             "High vol + σ>+1 + GREEN bar → BREAKOUT?"),
            (big_vol & (sw > 1.0) & (bar_dir < 0),
             "High vol + σ>+1 + RED bar → CEILING HIT?"),
        ]:
            if cond_mask.sum() < 3: continue
            wr = y[cond_mask].mean() * 100
            cnt = cond_mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★ SIGNAL" if wr > 60 else " ✗ TRAP" if wr < 40 else ""
            print(f"          {cond_name}")
            print(f"          {'':>50s} WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# PART 4: AUCTION PSYCHOLOGY — Exhaustion Reformulated
# WHERE in the σ range does the volume event occur?
# ════════════════════════════════════════════════════════════

def auction_psychology(edf: pd.DataFrame, ticker: str):
    sp(f"AUCTION PSYCHOLOGY: {ticker}")

    for signal in edf["signal_name"].unique():
        sig_df = edf[edf["signal_name"] == signal]
        if len(sig_df) < 20: continue

        spike = sig_df["vol_spike"]
        dry = sig_df["vol_dryness"]
        sw = sig_df["snap_sigma_wave"]
        ts = sig_df["snap_tide_slope"]
        kv = sig_df["snap_kalman_velocity"]
        fear = sig_df["snap_fear_level"]
        bar_range = sig_df["bar_range_ratio"]
        bar_dir = sig_df["bar_direction"]
        y = sig_df["is_win"]

        print(f"\n    {signal} × {ticker} (N={len(sig_df)})")

        # Auction state classification
        # A: Quiet + Narrow range → BALANCE (market resting, no conviction)
        # B: Quiet + Wide range → EXPLORATION (telebolito! searching for value)
        # C: Loud + Narrow range → COMPRESSION (buyers and sellers jammed)
        # D: Loud + Wide range → INITIATIVE (someone took control)

        # Using vol_spike and bar_range_ratio
        quiet = spike < 0.8
        loud = spike >= 1.2
        narrow = bar_range < 0.8
        wide = bar_range >= 1.2

        auction_states = [
            (quiet & narrow, "BALANCE (quiet+narrow)", "⚖"),
            (quiet & wide, "EXPLORATION (quiet+wide)", "🔍"),
            (loud & narrow, "COMPRESSION (loud+narrow)", "🗜"),
            (loud & wide, "INITIATIVE (loud+wide)", "🚀"),
            (~quiet & ~loud, "NORMAL VOLUME", "➡"),
        ]

        print(f"      Auction State Classification:")
        for mask, name, emoji in auction_states:
            if mask.sum() < 3: continue
            wr = y[mask].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
            print(f"        {emoji} {name:<35s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Auction state × σ position
        print(f"\n      Auction State × σ Position:")
        for mask, name, emoji in auction_states:
            if mask.sum() < 8: continue
            for sigma_mask, sigma_name in [
                (sw < -1, "σ<-1"),
                ((sw >= -1) & (sw < 0), "σ[-1,0)"),
                (sw >= 0, "σ≥0"),
            ]:
                combined = mask & sigma_mask
                if combined.sum() < 3: continue
                wr = y[combined].mean() * 100
                cnt = combined.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"        {emoji} {name[:15]:<15s} + {sigma_name:<10s} │ "
                      f"WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Auction state × trend
        print(f"\n      Auction State × Trend:")
        for mask, name, emoji in auction_states:
            if mask.sum() < 8: continue
            for trend_mask, trend_name in [(ts > 0.01, "BULL"), (ts < -0.01, "BEAR")]:
                combined = mask & trend_mask
                if combined.sum() < 3: continue
                wr = y[combined].mean() * 100
                cnt = combined.sum()
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"        {emoji} {name[:15]:<15s} + {trend_name:<5s} │ "
                      f"WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # NEW EXHAUSTION: Drought THEN Initiative (the slingshot release)
        print(f"\n      Sequence Pattern: Drought → Initiative:")
        # Drought in recent history + current bar is initiative
        drought_then_init = (dry >= 2) & (spike >= 1.2) & (wide)
        drought_then_balance = (dry >= 2) & quiet & narrow
        just_initiative = (dry == 0) & (spike >= 1.2) & wide
        
        for mask, name in [
            (drought_then_init, "DROUGHT → INITIATIVE (the awakening)"),
            (drought_then_balance, "DROUGHT → BALANCE (still sleeping)"),
            (just_initiative, "INITIATIVE (no drought — already active)"),
        ]:
            if mask.sum() < 3: continue
            wr = y[mask].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★ SLINGSHOT" if wr > 65 else " ✗" if wr < 40 else ""
            print(f"        {name:<50s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # Bar direction during initiative at σ extremes
        print(f"\n      Initiative Bar Direction at σ Extremes:")
        init_mask = (spike >= 1.2) & wide
        if init_mask.sum() >= 5:
            for cond, label in [
                (init_mask & (sw < -1) & (bar_dir > 0), "Initiative + σ<-1 + GREEN → REVERSAL BUY"),
                (init_mask & (sw < -1) & (bar_dir < 0), "Initiative + σ<-1 + RED → CONTINUATION SELL"),
                (init_mask & (sw > 0.5) & (bar_dir > 0), "Initiative + σ>0.5 + GREEN → BREAKOUT"),
                (init_mask & (sw > 0.5) & (bar_dir < 0), "Initiative + σ>0.5 + RED → EXHAUSTION"),
            ]:
                if cond.sum() < 3: continue
                wr = y[cond].mean() * 100
                cnt = cond.sum()
                bar = "█" * int(wr / 5)
                marker = " ★ SIGNAL" if wr > 60 else " ✗ TRAP" if wr < 40 else ""
                print(f"          {label}")
                print(f"          {'':>45s} WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v8 — AUCTION PSYCHOLOGY + VOLUME-SIGMA CORRELATIONS")

    print("\n  Loading forensic labels...")
    entry_df = load_labels()
    print(f"  → {len(entry_df)} entry labels")

    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        print(f"\n  Enriching {ticker} with volume features...")
        edf = enrich_volume(ticker, entry_df)
        if len(edf) < 20:
            print(f"    ⚠ Not enough data for {ticker}")
            continue

        p(f"PART 1: CV × SIGMA EXTREMES — {ticker}")
        cv_sigma_correlation(edf, ticker)

        p(f"PART 2: TELEBOLITO — Dryness × Context — {ticker}")
        telebolito_analysis(edf, ticker)

        p(f"PART 3: BOOM DIRECTION — Flow × σ — {ticker}")
        boom_direction_analysis(edf, ticker)

        p(f"PART 4: AUCTION PSYCHOLOGY — {ticker}")
        auction_psychology(edf, ticker)

    p("v8 AUCTION PSYCHOLOGY COMPLETE")
