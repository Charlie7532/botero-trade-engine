#!/usr/bin/env python3
"""
Precision Forensics — False Positive Analysis
================================================
The INVERSE question: when a feature fires (|z| > 2), is there actually a turn?

For EACH ticker × archetype × feature:
  - Find ALL bars where |z| > 2 in the entire history
  - For each fire: is it within t-2..t=0 of a turn of that archetype? → TRUE POSITIVE
  - If not near any turn of that archetype → FALSE POSITIVE
  - PRECISION = TP / (TP + FP) = P(turn | fire)
  - Also: temporal profile (median offset, mean offset, class)

This is the HONEST test. LIFT can be 30x but precision can be 5% if the feature
fires constantly. We need both.

Output: Per-ticker precision tables + cross-ticker summary.
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
MATCH_WINDOW = 2      # fire within t-2..t=0 of a turn = TRUE POSITIVE

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
OUT_DIR = root_dir / "backend" / "scripts" / "precision_forensics_output"
OUT_DIR.mkdir(exist_ok=True)
LOG = []
T0 = time.time()

def log(msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.append(line)

def log_section(title):
    log("═" * 100)
    log(f"  {title}")
    log("═" * 100)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
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
# PRECISION ANALYSIS
# ═══════════════════════════════════════════════════════════════

def compute_precision(df, turns, features):
    """For each archetype × feature:
    - Find ALL bars where |z| > threshold (fires)
    - For each fire: is it within MATCH_WINDOW bars before a turn of that archetype?
    - TP = fire near turn, FP = fire NOT near turn
    - Precision = TP / (TP + FP)
    
    Also compute temporal offset distribution for TPs."""

    n_bars = len(df)
    results = {}  # archetype -> list of feature results

    for archetype in ["LL", "HL", "HH", "LH"]:
        arch_turns = [t for t in turns if t["archetype"] == archetype]
        n_turns = len(arch_turns)
        if n_turns < 3:
            continue

        # Build set of "near turn" bar indices for this archetype
        # A fire at bar_idx is a TP if bar_idx is in [turn_bar - MATCH_WINDOW, turn_bar]
        turn_bar_indices = set()
        turn_bar_to_offset = {}  # bar_idx -> offset relative to nearest turn
        for t in arch_turns:
            for offset in range(-MATCH_WINDOW, 1):  # -2, -1, 0 (causal only)
                idx = t["bar_idx"] + offset
                if 0 <= idx < n_bars:
                    turn_bar_indices.add(idx)
                    # Store the offset (negative = before turn)
                    # If multiple turns claim this bar, keep the closest
                    existing = turn_bar_to_offset.get(idx)
                    if existing is None or abs(offset) < abs(existing):
                        turn_bar_to_offset[idx] = offset

        feat_results = []
        for feat in features:
            z_col = f"z_{feat}"
            z_vals = df[z_col].values

            # Find ALL fires (|z| > threshold) in the ENTIRE history
            # Skip first 250 bars (warmup)
            fire_indices = []
            for i in range(250, n_bars):
                if abs(z_vals[i]) > Z_THRESHOLD:
                    fire_indices.append(i)

            total_fires = len(fire_indices)
            if total_fires == 0:
                continue

            # Classify each fire as TP or FP
            tp_count = 0
            fp_count = 0
            tp_offsets = []  # offset relative to turn for each TP

            for fire_idx in fire_indices:
                if fire_idx in turn_bar_indices:
                    tp_count += 1
                    tp_offsets.append(turn_bar_to_offset[fire_idx])
                else:
                    fp_count += 1

            precision = tp_count / total_fires if total_fires > 0 else 0
            
            # Recall: of all turns of this archetype, how many had at least one
            # fire in their t-MATCH_WINDOW..t=0 window?
            turns_detected = 0
            for t in arch_turns:
                detected = False
                for offset in range(-MATCH_WINDOW, 1):
                    idx = t["bar_idx"] + offset
                    if 0 <= idx < n_bars and abs(z_vals[idx]) > Z_THRESHOLD:
                        detected = True
                        break
                if detected:
                    turns_detected += 1
            recall = turns_detected / n_turns if n_turns > 0 else 0

            # Temporal stats for TPs
            if tp_offsets:
                mean_offset = np.mean(tp_offsets)
                median_offset = np.median(tp_offsets)
            else:
                mean_offset = 0
                median_offset = 0

            # Classify temporal behavior
            if median_offset <= -1.5:
                temporal_class = "ALERTA"
            elif -0.5 <= median_offset <= 0.5:
                temporal_class = "DETECTION"
            elif median_offset >= 0.5:
                temporal_class = "LATE"
            else:
                temporal_class = "ALERTA"

            # Fire rate: what % of ALL bars have this feature active?
            fire_rate = total_fires / (n_bars - 250)

            feat_results.append({
                "feature": feat,
                "n_turns": n_turns,
                "total_fires": total_fires,
                "fire_rate": fire_rate,
                "tp": tp_count,
                "fp": fp_count,
                "precision": precision,
                "recall": recall,
                "turns_detected": turns_detected,
                "mean_offset": mean_offset,
                "median_offset": median_offset,
                "temporal_class": temporal_class,
            })

        # Sort by precision (the honest metric)
        feat_results.sort(key=lambda x: x["precision"], reverse=True)
        results[archetype] = feat_results

    return results


# ═══════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════

def report_ticker(ticker, results):
    log_section(f"TICKER: {ticker}")

    for archetype in ["LL", "HL", "HH", "LH"]:
        if archetype not in results:
            continue

        feat_results = results[archetype]
        if not feat_results:
            continue

        n_turns = feat_results[0]["n_turns"]
        log(f"\n  ── {archetype} ({n_turns} turns) ──")
        log(f"  {'Feature':<28s} │ {'Fires':>6s} │ {'Rate':>5s} │ {'TP':>4s} │ {'FP':>5s} │ "
            f"{'Prec%':>5s} │ {'Recall%':>7s} │ {'μ_off':>5s} │ {'med':>4s} │ {'Class':>10s}")
        log(f"  {'─'*28} │ {'─'*6} │ {'─'*5} │ {'─'*4} │ {'─'*5} │ "
            f"{'─'*5} │ {'─'*7} │ {'─'*5} │ {'─'*4} │ {'─'*10}")

        for r in feat_results[:20]:
            prec_pct = r["precision"] * 100
            recall_pct = r["recall"] * 100
            fire_rate_pct = r["fire_rate"] * 100

            # Color-code precision
            if prec_pct >= 15:
                verdict = "★★★"
            elif prec_pct >= 10:
                verdict = "★★"
            elif prec_pct >= 5:
                verdict = "★"
            else:
                verdict = ""

            log(f"  {r['feature']:<28s} │ {r['total_fires']:>6d} │ {fire_rate_pct:>4.1f}% │ "
                f"{r['tp']:>4d} │ {r['fp']:>5d} │ "
                f"{prec_pct:>4.1f}% │ {recall_pct:>6.1f}% │ "
                f"{r['mean_offset']:>+4.1f} │ {r['median_offset']:>+3.0f} │ "
                f"{r['temporal_class']:>10s} {verdict}")


def cross_ticker_precision(all_results):
    """For each archetype × feature: median precision across tickers."""
    log_section("CROSS-TICKER PRECISION SUMMARY")
    log(f"  Match window: t-{MATCH_WINDOW}..t=0 (causal only)")
    log(f"  TP = fire within {MATCH_WINDOW} bars before or at turn")
    log(f"  FP = fire with no turn nearby")
    log(f"  Precision = P(turn | fire)")

    for archetype in ["LL", "HL", "HH", "LH"]:
        log(f"\n  ── {archetype} ──")
        log(f"  {'Feature':<28s} │ {'#Tk':>3s} │ {'Med Prec%':>9s} │ {'Med Recall%':>11s} │ "
            f"{'Prec Range':>14s} │ {'Med FireRate':>11s} │ {'Med Offset':>10s} │ {'Class':>10s}")
        log(f"  {'─'*28} │ {'─'*3} │ {'─'*9} │ {'─'*11} │ "
            f"{'─'*14} │ {'─'*11} │ {'─'*10} │ {'─'*10}")

        feat_stats = {}
        for feat in FEATURES:
            precisions = []
            recalls = []
            fire_rates = []
            offsets = []

            for ticker, results in all_results.items():
                if archetype not in results:
                    continue
                for r in results[archetype]:
                    if r["feature"] == feat and r["total_fires"] >= 5:
                        precisions.append(r["precision"])
                        recalls.append(r["recall"])
                        fire_rates.append(r["fire_rate"])
                        offsets.append(r["median_offset"])

            if len(precisions) < 3:
                continue

            med_prec = np.median(precisions) * 100
            med_recall = np.median(recalls) * 100
            min_prec = min(precisions) * 100
            max_prec = max(precisions) * 100
            med_fire = np.median(fire_rates) * 100
            med_off = np.median(offsets)

            if med_off <= -1.5:
                cls = "ALERTA"
            elif -0.5 <= med_off <= 0.5:
                cls = "★ DETECT"
            else:
                cls = "LATE"

            feat_stats[feat] = {
                "n_tickers": len(precisions),
                "med_prec": med_prec,
                "med_recall": med_recall,
                "min_prec": min_prec,
                "max_prec": max_prec,
                "med_fire": med_fire,
                "med_offset": med_off,
                "cls": cls,
            }

        # Sort by precision
        ranked = sorted(feat_stats.items(), key=lambda x: x[1]["med_prec"], reverse=True)

        for feat, s in ranked[:20]:
            verdict = ""
            if s["med_prec"] >= 10:
                verdict = "★★★"
            elif s["med_prec"] >= 5:
                verdict = "★★"
            elif s["med_prec"] >= 3:
                verdict = "★"

            log(f"  {feat:<28s} │ {s['n_tickers']:>3d} │ {s['med_prec']:>8.1f}% │ "
                f"{s['med_recall']:>10.1f}% │ "
                f"{s['min_prec']:>5.1f}%-{s['max_prec']:>5.1f}% │ "
                f"{s['med_fire']:>10.1f}% │ "
                f"{s['med_offset']:>+9.1f} │ {s['cls']:>10s} {verdict}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log_section("PRECISION FORENSICS — False Positive Analysis")
    log(f"  ZigZag: {ZZ_SCALE*100:.0f}%   Z-threshold: {Z_THRESHOLD}")
    log(f"  Match window: t-{MATCH_WINDOW}..t=0 (causal)")
    log(f"  Question: When feature fires, what's the probability of a REAL turn?")

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

    all_results = {}
    all_csvs = []

    for ticker in tickers:
        log(f"\n  Processing {ticker}...")
        df, zz = load_ticker_data(store, ticker)
        if len(df) < 300 or len(zz) < 4:
            continue

        turns = classify_turns(df, zz)
        if len(turns) < 5:
            continue

        df = compute_zscores(df, FEATURES)
        results = compute_precision(df, turns, FEATURES)

        if results:
            all_results[ticker] = results
            report_ticker(ticker, results)

            # Save CSV
            csv_rows = []
            for arch, feat_results in results.items():
                for r in feat_results:
                    csv_rows.append({"ticker": ticker, "archetype": arch, **r})
            if csv_rows:
                csv_df = pd.DataFrame(csv_rows)
                csv_df.to_csv(OUT_DIR / f"{ticker}_precision.csv", index=False)
                all_csvs.append(csv_df)

    store.close()

    cross_ticker_precision(all_results)

    if all_csvs:
        combined = pd.concat(all_csvs, ignore_index=True)
        combined.to_csv(OUT_DIR / "all_tickers_precision.csv", index=False)

    elapsed = time.time() - T0
    log(f"\n  COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    log_path = OUT_DIR / f"precision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(LOG))
    log(f"  Log: {log_path}")
