#!/usr/bin/env python3
"""
Conjunction Precision — What happens when 2-3 features fire TOGETHER?
======================================================================
For each archetype:
  - Take top-N features by individual precision
  - Test ALL pairs and top triples
  - For each combination: find bars where ALL features fire simultaneously
  - Measure: TP, FP, Precision, Recall
  - Compare to individual precision

Key question: Does conjunction multiply precision or are features redundant?
"""

import sys, os, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from itertools import combinations

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
MATCH_WINDOW = 2  # t-2..t=0
TOP_N = 10        # Top features per archetype to combine
WARMUP = 250      # Skip first N bars

# Top features per archetype (from precision forensics results)
TOP_FEATURES = {
    "LL": [
        "vwap_sigma_current", "vwap_sigma_tide", "sigma_tide",
        "vwap_sigma_wave", "rsi_value", "kf_rsi_pred_val",
        "kf_price_pred_val", "wave_slope", "fear_level",
        "sigma_current",
    ],
    "HL": [
        "sigma_current", "kf_price_pred_val", "vwap_sigma_wave",
        "sigma_wave", "kf_rsi_filt_vel", "wave_accel",
        "vwap_sigma_current", "kf_tension_filt_vel",
        "kf_price_filt_vel", "conj_wave_tide",
    ],
    "HH": [
        "kf_conj_pred_val", "current_accel", "vwap_spread_tide_wave",
        "vwap_spread_tide_current", "conj_wave_tide",
        "vwap_spread_current_wave", "conj_current_tide",
        "wave_accel", "kf_price_pred_val", "conj_wave_current",
    ],
    "LH": [
        "kf_price_pred_val", "kf_price_filt_vel", "kf_price_innovation",
        "kf_conj_filt_vel", "compression_ratio", "wave_slope",
        "wave_accel", "conj_wave_current", "kf_conj_pred_val",
        "vwap_sigma_tide",
    ],
}

ALL_FEATURES = list(set(f for feats in TOP_FEATURES.values() for f in feats))

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
OUT_DIR = root_dir / "backend" / "scripts" / "conjunction_forensics_output"
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
    feature_cols = ", ".join(ALL_FEATURES)
    cur.execute(f"""
        SELECT timestamp, {feature_cols}
        FROM engine.channel_snapshots
        WHERE ticker = %s AND timeframe = '1d'
          AND kf_rsi_pred_val IS NOT NULL
        ORDER BY timestamp
    """, (ticker,))
    rows = cur.fetchall()
    cols = ["timestamp"] + ALL_FEATURES
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    cur.execute("""
        SELECT timestamp, tp_type, price
        FROM engine.zigzag_points
        WHERE ticker = %s AND min_swing_pct = %s
        ORDER BY timestamp
    """, (ticker, ZZ_SCALE))
    zz_rows = cur.fetchall()
    zz = pd.DataFrame(zz_rows, columns=["timestamp", "tp_type", "price"])
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
        if diffs[bar_idx] / np.timedelta64(1, "D") > 3:
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
            turns.append({"bar_idx": bar_idx, "archetype": archetype})
    return turns


def compute_zscores(df):
    result = df.copy()
    for feat in ALL_FEATURES:
        vals = df[feat].values.astype(float)
        mu = np.nanmean(vals)
        sigma = np.nanstd(vals)
        if sigma < 1e-8:
            sigma = 1.0
        result[f"z_{feat}"] = (vals - mu) / sigma
    return result


# ═══════════════════════════════════════════════════════════════
# CONJUNCTION ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_conjunctions(df, turns, archetype, features):
    """Test all pairs and top triples of features for conjunction precision."""
    n_bars = len(df)
    arch_turns = [t for t in turns if t["archetype"] == archetype]
    n_turns = len(arch_turns)
    if n_turns < 3:
        return []

    # Build turn proximity set: bars within MATCH_WINDOW of a turn
    turn_bars = set()
    for t in arch_turns:
        for offset in range(-MATCH_WINDOW, 1):
            idx = t["bar_idx"] + offset
            if 0 <= idx < n_bars:
                turn_bars.add(idx)

    # Precompute fire masks per feature (boolean arrays)
    fire_masks = {}
    for feat in features:
        z_col = f"z_{feat}"
        if z_col not in df.columns:
            continue
        z_vals = df[z_col].values
        mask = np.zeros(n_bars, dtype=bool)
        for i in range(WARMUP, n_bars):
            if abs(z_vals[i]) > Z_THRESHOLD:
                mask[i] = True
        fire_masks[feat] = mask

    available = [f for f in features if f in fire_masks]
    results = []

    # ── SINGLES ──
    for feat in available:
        mask = fire_masks[feat]
        fire_indices = np.where(mask)[0]
        total = len(fire_indices)
        if total == 0:
            continue
        tp = sum(1 for i in fire_indices if i in turn_bars)
        fp = total - tp

        # Recall: how many turns detected?
        turns_hit = 0
        for t in arch_turns:
            for offset in range(-MATCH_WINDOW, 1):
                idx = t["bar_idx"] + offset
                if 0 <= idx < n_bars and mask[idx]:
                    turns_hit += 1
                    break

        results.append({
            "combo": feat,
            "n_features": 1,
            "total_fires": total,
            "tp": tp,
            "fp": fp,
            "precision": tp / total,
            "recall": turns_hit / n_turns,
            "turns_hit": turns_hit,
            "n_turns": n_turns,
            "fire_rate": total / (n_bars - WARMUP),
        })

    # ── PAIRS ──
    for f1, f2 in combinations(available, 2):
        mask = fire_masks[f1] & fire_masks[f2]
        fire_indices = np.where(mask)[0]
        total = len(fire_indices)
        if total < 2:
            continue
        tp = sum(1 for i in fire_indices if i in turn_bars)
        fp = total - tp

        turns_hit = 0
        for t in arch_turns:
            for offset in range(-MATCH_WINDOW, 1):
                idx = t["bar_idx"] + offset
                if 0 <= idx < n_bars and mask[idx]:
                    turns_hit += 1
                    break

        results.append({
            "combo": f"{f1} + {f2}",
            "n_features": 2,
            "total_fires": total,
            "tp": tp,
            "fp": fp,
            "precision": tp / total if total > 0 else 0,
            "recall": turns_hit / n_turns,
            "turns_hit": turns_hit,
            "n_turns": n_turns,
            "fire_rate": total / (n_bars - WARMUP),
        })

    # ── TRIPLES (top 6 features only to limit combinatorics) ──
    top6 = available[:6]
    for f1, f2, f3 in combinations(top6, 3):
        mask = fire_masks[f1] & fire_masks[f2] & fire_masks[f3]
        fire_indices = np.where(mask)[0]
        total = len(fire_indices)
        if total < 1:
            continue
        tp = sum(1 for i in fire_indices if i in turn_bars)
        fp = total - tp

        turns_hit = 0
        for t in arch_turns:
            for offset in range(-MATCH_WINDOW, 1):
                idx = t["bar_idx"] + offset
                if 0 <= idx < n_bars and mask[idx]:
                    turns_hit += 1
                    break

        results.append({
            "combo": f"{f1} + {f2} + {f3}",
            "n_features": 3,
            "total_fires": total,
            "tp": tp,
            "fp": fp,
            "precision": tp / total if total > 0 else 0,
            "recall": turns_hit / n_turns,
            "turns_hit": turns_hit,
            "n_turns": n_turns,
            "fire_rate": total / (n_bars - WARMUP),
        })

    return results


# ═══════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════

def report_ticker(ticker, all_results):
    log_section(f"TICKER: {ticker}")

    for archetype in ["LL", "HL", "HH", "LH"]:
        if archetype not in all_results:
            continue

        results = all_results[archetype]
        if not results:
            continue

        n_turns = results[0]["n_turns"]

        # Separate by type
        singles = sorted([r for r in results if r["n_features"] == 1],
                         key=lambda x: x["precision"], reverse=True)
        pairs = sorted([r for r in results if r["n_features"] == 2],
                       key=lambda x: x["precision"], reverse=True)
        triples = sorted([r for r in results if r["n_features"] == 3],
                         key=lambda x: x["precision"], reverse=True)

        log(f"\n  ── {archetype} ({n_turns} turns) ──")

        # Singles (top 5)
        log(f"\n  SINGLES:")
        log(f"  {'Combo':<55s} │ {'Fires':>5s} │ {'TP':>3s} │ {'FP':>4s} │ {'Prec%':>5s} │ {'Recall%':>7s} │ {'FireRate':>8s}")
        log(f"  {'─'*55} │ {'─'*5} │ {'─'*3} │ {'─'*4} │ {'─'*5} │ {'─'*7} │ {'─'*8}")
        for r in singles[:5]:
            log(f"  {r['combo']:<55s} │ {r['total_fires']:>5d} │ {r['tp']:>3d} │ {r['fp']:>4d} │ "
                f"{r['precision']*100:>4.1f}% │ {r['recall']*100:>6.1f}% │ {r['fire_rate']*100:>7.2f}%")

        # Pairs (top 10)
        log(f"\n  PAIRS (top 10):")
        log(f"  {'Combo':<55s} │ {'Fires':>5s} │ {'TP':>3s} │ {'FP':>4s} │ {'Prec%':>5s} │ {'Recall%':>7s} │ {'FireRate':>8s}")
        log(f"  {'─'*55} │ {'─'*5} │ {'─'*3} │ {'─'*4} │ {'─'*5} │ {'─'*7} │ {'─'*8}")
        for r in pairs[:10]:
            log(f"  {r['combo']:<55s} │ {r['total_fires']:>5d} │ {r['tp']:>3d} │ {r['fp']:>4d} │ "
                f"{r['precision']*100:>4.1f}% │ {r['recall']*100:>6.1f}% │ {r['fire_rate']*100:>7.2f}%")

        # Triples (top 10)
        if triples:
            log(f"\n  TRIPLES (top 10):")
            log(f"  {'Combo':<55s} │ {'Fires':>5s} │ {'TP':>3s} │ {'FP':>4s} │ {'Prec%':>5s} │ {'Recall%':>7s} │ {'FireRate':>8s}")
            log(f"  {'─'*55} │ {'─'*5} │ {'─'*3} │ {'─'*4} │ {'─'*5} │ {'─'*7} │ {'─'*8}")
            for r in triples[:10]:
                log(f"  {r['combo']:<55s} │ {r['total_fires']:>5d} │ {r['tp']:>3d} │ {r['fp']:>4d} │ "
                    f"{r['precision']*100:>4.1f}% │ {r['recall']*100:>6.1f}% │ {r['fire_rate']*100:>7.2f}%")

        # BEST overall
        all_combos = singles + pairs + triples
        # Best precision with recall >= 10%
        viable = [r for r in all_combos if r["recall"] >= 0.10 and r["total_fires"] >= 3]
        if viable:
            best = max(viable, key=lambda x: x["precision"])
            log(f"\n  ★ BEST (Prec with Recall≥10%): {best['combo']}")
            log(f"    Precision={best['precision']*100:.1f}%  Recall={best['recall']*100:.1f}%  "
                f"Fires={best['total_fires']}  TP={best['tp']}  FP={best['fp']}")


def cross_ticker_summary(all_ticker_results):
    """For each archetype: which combinations are consistently best?"""
    log_section("CROSS-TICKER CONJUNCTION SUMMARY")

    for archetype in ["LL", "HL", "HH", "LH"]:
        log(f"\n  ── {archetype} ──")

        # Collect all combos across tickers
        combo_stats = {}  # combo -> list of {ticker, precision, recall, fires}
        for ticker, arch_results in all_ticker_results.items():
            if archetype not in arch_results:
                continue
            for r in arch_results[archetype]:
                if r["total_fires"] < 2:
                    continue
                combo_stats.setdefault(r["combo"], []).append({
                    "ticker": ticker,
                    "precision": r["precision"],
                    "recall": r["recall"],
                    "fires": r["total_fires"],
                    "tp": r["tp"],
                    "fp": r["fp"],
                })

        # Filter: combos present in >= 5 tickers
        consistent = {k: v for k, v in combo_stats.items() if len(v) >= 5}
        if not consistent:
            log(f"  No consistent combinations found!")
            continue

        # Rank by median precision
        ranked = []
        for combo, stats in consistent.items():
            precs = [s["precision"] for s in stats]
            recalls = [s["recall"] for s in stats]
            ranked.append({
                "combo": combo,
                "n_tickers": len(stats),
                "med_prec": np.median(precs) * 100,
                "min_prec": min(precs) * 100,
                "max_prec": max(precs) * 100,
                "med_recall": np.median(recalls) * 100,
                "total_tp": sum(s["tp"] for s in stats),
                "total_fp": sum(s["fp"] for s in stats),
                "n_features": combo.count("+") + 1,
            })

        ranked.sort(key=lambda x: x["med_prec"], reverse=True)

        # Show singles, pairs, triples separately
        for n_feat, label in [(1, "SINGLES"), (2, "PAIRS"), (3, "TRIPLES")]:
            subset = [r for r in ranked if r["n_features"] == n_feat][:10]
            if not subset:
                continue

            log(f"\n  {label}:")
            log(f"  {'Combo':<55s} │ {'#Tk':>3s} │ {'Med P%':>6s} │ {'P range':>14s} │ "
                f"{'Med R%':>6s} │ {'ΣTP':>4s} │ {'ΣFP':>5s} │ {'Glob P%':>7s}")
            log(f"  {'─'*55} │ {'─'*3} │ {'─'*6} │ {'─'*14} │ "
                f"{'─'*6} │ {'─'*4} │ {'─'*5} │ {'─'*7}")

            for r in subset:
                glob_prec = r["total_tp"] / max(r["total_tp"] + r["total_fp"], 1) * 100
                log(f"  {r['combo']:<55s} │ {r['n_tickers']:>3d} │ {r['med_prec']:>5.1f}% │ "
                    f"{r['min_prec']:>5.1f}%-{r['max_prec']:>5.1f}% │ "
                    f"{r['med_recall']:>5.1f}% │ {r['total_tp']:>4d} │ {r['total_fp']:>5d} │ "
                    f"{glob_prec:>6.1f}%")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log_section("CONJUNCTION PRECISION — Does combining features reduce false positives?")
    log(f"  ZigZag: {ZZ_SCALE*100:.0f}%   Z: {Z_THRESHOLD}σ   Window: t-{MATCH_WINDOW}..t=0")

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

    all_ticker_results = {}

    for ticker in tickers:
        log(f"\n  Processing {ticker}...")
        df, zz = load_ticker_data(store, ticker)
        if len(df) < 300 or len(zz) < 4:
            continue

        turns = classify_turns(df, zz)
        if len(turns) < 5:
            continue

        df = compute_zscores(df)
        ticker_results = {}

        for archetype in ["LL", "HL", "HH", "LH"]:
            features = TOP_FEATURES[archetype]
            results = analyze_conjunctions(df, turns, archetype, features)
            if results:
                ticker_results[archetype] = results

        if ticker_results:
            all_ticker_results[ticker] = ticker_results
            report_ticker(ticker, ticker_results)

    store.close()

    cross_ticker_summary(all_ticker_results)

    elapsed = time.time() - T0
    log(f"\n  COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    log_path = OUT_DIR / f"conjunction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(LOG))
    log(f"  Log: {log_path}")
