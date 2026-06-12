#!/usr/bin/env python3
"""
Temporal Profile Forensics — WHEN does each signal fire?
==========================================================
For EACH feature × archetype × ticker:
  - Scan t-10 to t+5 around every turn
  - Record EVERY bar where |z| > 2
  - Compute: mean offset, median offset, p25, p75, min, max
  - Classify: EARLY WARNING (t<-2), ALERTA (t-2..t-1), DETECTION (t=0),
              CONFIRMATION (t+1..t+2), LATE (t>2)

Output: Per-ticker temporal profiles + cross-ticker summary.
No aggregation lies. Every number belongs to one ticker.
"""

import sys, os, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
ZZ_SCALE = 0.05
Z_THRESHOLD = 2.0
SCAN_BEFORE = 10   # scan t-10
SCAN_AFTER = 5     # scan t+5
# Total window: 16 bars per turn (t-10 to t+5)

FEATURES = [
    "sigma_tide", "sigma_current", "sigma_wave",
    "vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave",
    "tide_slope", "current_slope", "wave_slope",
    "tide_accel", "current_accel", "wave_accel",
    "conj_wave_tide", "conj_current_tide", "conj_wave_current",
    "tension_tide", "tension_current", "tension_wave",
    "vwap_spread_tide_current", "vwap_spread_tide_wave", "vwap_spread_current_wave",
    "compression_ratio", "fear_level", "rsi_value",
    "kf_price_pred_val", "kf_price_filt_vel", "kf_price_innovation",
    "kf_rsi_pred_val", "kf_rsi_filt_vel",
    "kf_tension_pred_val", "kf_tension_filt_vel",
    "kf_conj_pred_val", "kf_conj_filt_vel",
    "kf_rvol_pred_val", "kf_rvol_filt_vel",
]

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
OUT_DIR = root_dir / "backend" / "scripts" / "temporal_profile_output"
OUT_DIR.mkdir(exist_ok=True)
LOG = []
T0 = time.time()

def log(msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.append(line)

def log_section(title):
    log("═" * 90)
    log(f"  {title}")
    log("═" * 90)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING (same as per_ticker_turn_forensics.py)
# ═══════════════════════════════════════════════════════════════

def load_ticker_data(store, ticker):
    conn = store._conn()
    cur = conn.cursor()
    feature_cols = ", ".join(FEATURES)
    cur.execute(f"""
        SELECT timestamp, {feature_cols}
        FROM engine.channel_snapshots
        WHERE ticker = %s AND timeframe = '1d'
          AND kf_rsi_pred_val IS NOT NULL
        ORDER BY timestamp
    """, (ticker,))
    rows = cur.fetchall()
    cols = ["timestamp"] + FEATURES
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    cur.execute("""
        SELECT timestamp, tp_type, price, swing_return, swing_days
        FROM engine.zigzag_points
        WHERE ticker = %s AND min_swing_pct = %s
        ORDER BY timestamp
    """, (ticker, ZZ_SCALE))
    zz_rows = cur.fetchall()
    zz = pd.DataFrame(zz_rows, columns=["timestamp", "tp_type", "price",
                                         "swing_return", "swing_days"])
    zz["timestamp"] = pd.to_datetime(zz["timestamp"], utc=True)
    store._put(conn)
    return df, zz


def classify_turns(df, zz):
    ts_arr = df["timestamp"].values.astype("datetime64[ns]")
    turns = []
    prev_min_price = None
    prev_max_price = None

    for _, row in zz.iterrows():
        zz_ts = np.datetime64(row["timestamp"])
        diffs = np.abs(ts_arr - zz_ts)
        bar_idx = int(np.argmin(diffs))
        match_days = diffs[bar_idx] / np.timedelta64(1, "D")
        if match_days > 3:
            continue

        archetype = None
        if row["tp_type"] == "MIN":
            if prev_min_price is not None:
                archetype = "HL" if row["price"] > prev_min_price else "LL"
            prev_min_price = row["price"]
        elif row["tp_type"] == "MAX":
            if prev_max_price is not None:
                archetype = "HH" if row["price"] > prev_max_price else "LH"
            prev_max_price = row["price"]

        if archetype is not None:
            turns.append({
                "bar_idx": bar_idx,
                "archetype": archetype,
                "price": row["price"],
                "timestamp": row["timestamp"],
            })
    return turns


def compute_zscores(df, features):
    result = df.copy()
    for feat in features:
        vals = df[feat].values.astype(float)
        mu = np.nanmean(vals)
        sigma = np.nanstd(vals)
        if sigma < 1e-8:
            sigma = 1.0
        result[f"z_{feat}"] = (vals - mu) / sigma
    return result


# ═══════════════════════════════════════════════════════════════
# TEMPORAL PROFILE: When does each feature fire?
# ═══════════════════════════════════════════════════════════════

def compute_temporal_profiles(df, turns, features):
    """For each archetype × feature, scan t-SCAN_BEFORE..t+SCAN_AFTER.
    Record the offset of EVERY bar where |z| > threshold.
    Returns dict: archetype -> feature -> list of offsets."""

    n_bars = len(df)
    profiles = {}  # archetype -> feature -> {"offsets": [...], "n_turns": N}

    for archetype in ["LL", "HL", "HH", "LH"]:
        arch_turns = [t for t in turns if t["archetype"] == archetype]
        if len(arch_turns) < 3:
            continue

        feat_profiles = {}
        for feat in features:
            z_col = f"z_{feat}"
            z_vals = df[z_col].values
            offsets = []

            for t in arch_turns:
                for offset in range(-SCAN_BEFORE, SCAN_AFTER + 1):
                    idx = t["bar_idx"] + offset
                    if 0 <= idx < n_bars:
                        if abs(z_vals[idx]) > Z_THRESHOLD:
                            offsets.append(offset)

            feat_profiles[feat] = {
                "offsets": offsets,
                "n_turns": len(arch_turns),
                "n_fires": len(offsets),
            }

        profiles[archetype] = feat_profiles

    return profiles


def compute_heatmap(df, turns, features):
    """Compute activation RATE at each offset for the heatmap.
    Returns dict: archetype -> feature -> {offset: rate}."""

    n_bars = len(df)
    heatmaps = {}

    for archetype in ["LL", "HL", "HH", "LH"]:
        arch_turns = [t for t in turns if t["archetype"] == archetype]
        if len(arch_turns) < 3:
            continue

        feat_heatmaps = {}
        for feat in features:
            z_col = f"z_{feat}"
            z_vals = df[z_col].values
            offset_counts = defaultdict(int)

            for t in arch_turns:
                for offset in range(-SCAN_BEFORE, SCAN_AFTER + 1):
                    idx = t["bar_idx"] + offset
                    if 0 <= idx < n_bars:
                        if abs(z_vals[idx]) > Z_THRESHOLD:
                            offset_counts[offset] += 1

            # Convert to rates
            n = len(arch_turns)
            offset_rates = {off: cnt / n for off, cnt in offset_counts.items()}
            feat_heatmaps[feat] = offset_rates

        heatmaps[archetype] = feat_heatmaps

    return heatmaps


# ═══════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════

def report_temporal(ticker, profiles, heatmaps):
    """Print temporal profile for each archetype's top features."""
    log_section(f"TICKER: {ticker}")

    for archetype in ["LL", "HL", "HH", "LH"]:
        if archetype not in profiles:
            continue

        feat_profiles = profiles[archetype]
        feat_heatmaps = heatmaps[archetype]

        # Sort features by number of fires at or before t=0 (causal fires)
        def causal_score(feat):
            offsets = feat_profiles[feat]["offsets"]
            causal = [o for o in offsets if o <= 0]
            return len(causal) / max(feat_profiles[feat]["n_turns"], 1)

        ranked = sorted(FEATURES, key=causal_score, reverse=True)

        n_turns = feat_profiles[ranked[0]]["n_turns"] if ranked else 0
        log(f"\n  ── {archetype} ({n_turns} turns) ──")
        log(f"  {'Feature':<28s} │ {'μ':>5s} │ {'med':>4s} │ {'p25':>4s} │ {'p75':>4s} │ "
            f"{'t-10→t-3':>8s} │ {'t-2,t-1':>7s} │ {'t=0':>4s} │ {'t+1,t+2':>7s} │ {'t+3→t+5':>8s} │ {'Class':>12s}")
        log(f"  {'─'*28} │ {'─'*5} │ {'─'*4} │ {'─'*4} │ {'─'*4} │ "
            f"{'─'*8} │ {'─'*7} │ {'─'*4} │ {'─'*7} │ {'─'*8} │ {'─'*12}")

        for feat in ranked[:15]:
            p = feat_profiles[feat]
            offsets = p["offsets"]
            n = p["n_turns"]

            if len(offsets) < 3:
                continue

            arr = np.array(offsets)
            mean_off = np.mean(arr)
            med_off = np.median(arr)
            p25 = np.percentile(arr, 25)
            p75 = np.percentile(arr, 75)

            # Compute % of turns where feature fires in each zone
            hm = feat_heatmaps[feat]
            early = sum(hm.get(o, 0) for o in range(-10, -2)) / 8 * 100  # avg rate per bar
            alert = sum(hm.get(o, 0) for o in range(-2, 0)) / 2 * 100
            det = hm.get(0, 0) * 100
            conf = sum(hm.get(o, 0) for o in range(1, 3)) / 2 * 100
            late = sum(hm.get(o, 0) for o in range(3, 6)) / 3 * 100

            # Classify the temporal behavior
            if med_off <= -3:
                cls = "EARLY WARN"
            elif med_off <= -1:
                cls = "ALERTA"
            elif -0.5 <= med_off <= 0.5:
                cls = "DETECTION"
            elif med_off <= 2:
                cls = "CONFIRM"
            else:
                cls = "LATE"

            # Mark if it PEAKS before, at, or after t=0
            peak_zone = max(
                [("early", sum(hm.get(o, 0) for o in range(-10, -2))),
                 ("alert", sum(hm.get(o, 0) for o in range(-2, 0))),
                 ("t=0", hm.get(0, 0)),
                 ("conf", sum(hm.get(o, 0) for o in range(1, 3))),
                 ("late", sum(hm.get(o, 0) for o in range(3, 6)))],
                key=lambda x: x[1]
            )[0]

            log(f"  {feat:<28s} │ {mean_off:>+4.1f} │ {med_off:>+3.0f} │ {p25:>+3.0f} │ {p75:>+3.0f} │ "
                f"{early:>7.0f}% │ {alert:>6.0f}% │ {det:>3.0f}% │ {conf:>6.0f}% │ {late:>7.0f}% │ {cls:>12s}")

        # HEATMAP: Visual temporal bar chart for top 5
        top5 = ranked[:5]
        log(f"\n  HEATMAP (% of {archetype} turns where feature fires at each offset):")
        log(f"  {'':28s}  t-10 t-9  t-8  t-7  t-6  t-5  t-4  t-3  t-2  t-1  t=0  t+1  t+2  t+3  t+4  t+5")
        log(f"  {'':28s}  {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4}")

        for feat in top5:
            hm = feat_heatmaps[feat]
            bars = []
            for offset in range(-SCAN_BEFORE, SCAN_AFTER + 1):
                rate = hm.get(offset, 0) * 100
                if rate >= 20:
                    bars.append(f"{'█':>3s}{rate:>1.0f}")
                elif rate >= 10:
                    bars.append(f"{'▓':>3s}{rate:>1.0f}")
                elif rate >= 5:
                    bars.append(f"{'▒':>3s}{rate:>1.0f}")
                elif rate >= 1:
                    bars.append(f"{'░':>3s}{rate:>1.0f}")
                else:
                    bars.append(f"{'·':>4s}")
            log(f"  {feat:<28s}  {' '.join(bars)}")


# ═══════════════════════════════════════════════════════════════
# CROSS-TICKER TEMPORAL SUMMARY
# ═══════════════════════════════════════════════════════════════

def temporal_summary(all_profiles):
    """For each archetype × feature: what's the MEDIAN of medians across tickers?"""
    log_section("CROSS-TICKER TEMPORAL SUMMARY")
    log("  For each feature: median offset across all tickers (where it fired ≥3 times)")

    for archetype in ["LL", "HL", "HH", "LH"]:
        log(f"\n  ── {archetype} ──")
        log(f"  {'Feature':<28s} │ {'#Tickers':>8s} │ {'Med(μ)':>6s} │ {'Med(med)':>8s} │ "
            f"{'Range μ':>12s} │ {'Temporal Class':>14s}")
        log(f"  {'─'*28} │ {'─'*8} │ {'─'*6} │ {'─'*8} │ {'─'*12} │ {'─'*14}")

        feat_stats = {}
        for feat in FEATURES:
            means = []
            medians = []
            for ticker, profiles in all_profiles.items():
                if archetype not in profiles:
                    continue
                p = profiles[archetype].get(feat)
                if p is None or len(p["offsets"]) < 3:
                    continue
                arr = np.array(p["offsets"])
                means.append(float(np.mean(arr)))
                medians.append(float(np.median(arr)))

            if len(means) < 3:
                continue

            feat_stats[feat] = {
                "n_tickers": len(means),
                "med_of_means": np.median(means),
                "med_of_medians": np.median(medians),
                "min_mean": min(means),
                "max_mean": max(means),
            }

        # Sort by absolute distance from 0 (closest to detection first)
        ranked = sorted(feat_stats.items(),
                        key=lambda x: abs(x[1]["med_of_medians"]))

        for feat, s in ranked[:20]:
            m = s["med_of_medians"]
            if m <= -3:
                cls = "EARLY WARNING"
            elif m <= -1:
                cls = "ALERTA"
            elif -0.5 <= m <= 0.5:
                cls = "★ DETECTION"
            elif m <= 2:
                cls = "CONFIRMATION"
            else:
                cls = "LATE"

            log(f"  {feat:<28s} │ {s['n_tickers']:>8d} │ {s['med_of_means']:>+5.1f} │ "
                f"{m:>+7.1f} │ "
                f"{s['min_mean']:>+5.1f}..{s['max_mean']:>+4.1f} │ {cls:>14s}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log_section("TEMPORAL PROFILE FORENSICS — When does each signal fire?")
    log(f"  ZigZag: {ZZ_SCALE*100:.0f}%   Z-threshold: {Z_THRESHOLD}")
    log(f"  Scan window: t-{SCAN_BEFORE} to t+{SCAN_AFTER}")
    log(f"  Features: {len(FEATURES)}")

    store = TimescaleDataStore()
    conn = store._conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ticker FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND kf_rsi_pred_val IS NOT NULL
        ORDER BY ticker
    """)
    tickers = [r[0] for r in cur.fetchall()]
    store._put(conn)
    log(f"  Tickers: {tickers}")

    all_profiles = {}
    all_heatmaps = {}

    for ticker in tickers:
        log(f"\n  Processing {ticker}...")
        df, zz = load_ticker_data(store, ticker)
        if len(df) < 300 or len(zz) < 4:
            log(f"  SKIP: insufficient data")
            continue

        turns = classify_turns(df, zz)
        if len(turns) < 5:
            log(f"  SKIP: only {len(turns)} turns")
            continue

        df = compute_zscores(df, FEATURES)
        profiles = compute_temporal_profiles(df, turns, FEATURES)
        heatmaps = compute_heatmap(df, turns, FEATURES)

        if profiles:
            all_profiles[ticker] = profiles
            all_heatmaps[ticker] = heatmaps
            report_temporal(ticker, profiles, heatmaps)

    store.close()

    # Cross-ticker temporal summary
    temporal_summary(all_profiles)

    # Save log
    elapsed = time.time() - T0
    log(f"\n  COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    log_path = OUT_DIR / f"temporal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(LOG))
    log(f"  Log: {log_path}")
