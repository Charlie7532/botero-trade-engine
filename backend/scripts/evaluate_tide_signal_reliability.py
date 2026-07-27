#!/usr/bin/env python3
"""
Signal Reliability Evaluation
================================
Evaluates the accuracy of all 9 RC tide signals against actual
zigzag pivots across 640K bars and 547 tickers.

For each signal fire, checks whether a zigzag pivot (2.5%/5%/7.5%)
occurred within a forward window of 5/10/20 bars, measuring:
  - Precision (hits / fires)
  - Recall (hits / total pivots in zone)
  - LIFT vs baseline
  - Distance to nearest pivot
  - Missed pivots & false alarms
  - Threshold sensitivity scan

READ-ONLY — no tables or files are modified.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
        backend/scripts/evaluate_tide_signal_reliability.py
"""
import os, sys, json, time, math, warnings
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════
DERIVED_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json"
FORWARD_WINDOWS = [5, 10, 20]
ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZZ_LABEL = {0.025: "2.5%", 0.05: "5.0%", 0.075: "7.5%"}

# Slope thresholds — from rc_slope_classifier.py (must match training)
SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}
SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]

# Signals grouped by action type
ENTRY_SIGNALS = {"ACCUMULATE", "BUY_DIP"}       # Should predict bottoms
EXIT_SIGNALS = {"TAKE_PROFIT", "REDUCE"}          # Should predict tops
HOLD_SIGNALS = {"MOMENTUM", "STRONG_TREND", "BULL_TREND", "WATCH", "NO_EDGE"}


# ═══════════════════════════════════════════════════════════════
# Classification (must match train_combined_table.py exactly)
# ═══════════════════════════════════════════════════════════════
def classify_slope(value: float, channel: str) -> str:
    th = SLOPE_TH[channel]
    if value >= 0:
        p33, p66 = th["+"]
        if value >= p66:
            return f"{channel}+++"
        elif value >= p33:
            return f"{channel}++"
        else:
            return f"{channel}+"
    else:
        p33, p66 = th["-"]
        av = abs(value)
        if av >= p66:
            return f"{channel}---"
        elif av >= p33:
            return f"{channel}--"
        else:
            return f"{channel}-"


def classify_sigma_vw(value: float) -> str:
    for lo, hi, label in SIGMA_BINS:
        if lo <= value < hi:
            return label
    return ">>"


# ═══════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════
def load_all_data(store):
    """Bulk-load all snapshots and zigzag points with pandas vectorized memory layout."""
    import pandas as pd
    conn = store._conn()
    try:
        print("  Loading channel_snapshots via pandas C-arrays...")
        t0 = time.time()
        df_snaps = pd.read_sql("""
            SELECT ticker, timestamp::date as date, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE tide_slope IS NOT NULL
              AND current_slope IS NOT NULL
              AND vwap_sigma_wave IS NOT NULL
            ORDER BY ticker, timestamp
        """, conn)
        print(f"    → {len(df_snaps):,} rows in {time.time()-t0:.1f}s")

        print("  Loading zigzag_points via pandas C-arrays...")
        t0 = time.time()
        df_zz = pd.read_sql("""
            SELECT ticker, timestamp::date as date, min_swing_pct, tp_type
            FROM engine.zigzag_points
            ORDER BY ticker, timestamp
        """, conn)
        print(f"    → {len(df_zz):,} rows in {time.time()-t0:.1f}s")

        ticker_bars = {}
        for tk, group in df_snaps.groupby("ticker"):
            ticker_bars[tk] = list(zip(group["date"].values, group["tide_slope"].values, group["current_slope"].values, group["vwap_sigma_wave"].values))

        ticker_zigzags = defaultdict(lambda: defaultdict(list))
        for r in df_zz.itertuples(index=False):
            ticker_zigzags[r.ticker][r.date].append((float(r.min_swing_pct), r.tp_type))

        return ticker_bars, dict(ticker_zigzags)
    finally:
        store._put(conn)


# ═══════════════════════════════════════════════════════════════
# Core Evaluation
# ═══════════════════════════════════════════════════════════════
def evaluate_ticker(bars, zigzags, signal_lookup):
    """Evaluate signal reliability for one ticker.

    Args:
        bars: [(date, t_slope, c_slope, svw)]
        zigzags: {date: [(level, tp_type)]}
        signal_lookup: {state_key: signal_name}

    Returns dict with per-signal stats.
    """
    n = len(bars)
    if n < 100:
        return None

    # Pre-classify all bars
    bar_states = []
    bar_dates = []
    for date, t_slope, c_slope, svw in bars:
        t = classify_slope(t_slope, 'T')
        c = classify_slope(c_slope, 'C')
        s = classify_sigma_vw(svw)
        state_key = f"{t}|{c}|{s}"
        signal = signal_lookup.get(state_key, "NO_EDGE")
        bar_states.append((state_key, signal))
        bar_dates.append(date)

    # Pre-build zigzag lookup arrays for forward scanning
    # For each bar index, record if a zigzag pivot exists
    bar_zz = []  # [(level, tp_type) or None]
    for date in bar_dates:
        zz_at = zigzags.get(date, [])
        bar_zz.append(zz_at)

    results = {
        "signal_fires": Counter(),  # signal → count of fires
        "forward_hits": defaultdict(lambda: defaultdict(lambda: defaultdict(int))),
        # signal → window → zz_level → count of hits
        "distances": defaultdict(list),  # signal → [distance_to_nearest_pivot]
        "pivot_at_fire": defaultdict(lambda: defaultdict(int)),
        # signal → zz_level → count of T=0 coincidences
        "missed_pivots": defaultdict(lambda: defaultdict(int)),
        # zone → zz_level → count of pivots missed by all signals
        "total_pivots_in_zone": defaultdict(lambda: defaultdict(int)),
        # zone → zz_level → total pivots
    }

    # Additional: unique hits (binary: did this fire find ANY pivot?)
    unique_hits = defaultdict(lambda: defaultdict(int))  # signal → window → fires_with_hit

    for i in range(n):
        state_key, signal = bar_states[i]
        zone = state_key.split("|")[2]  # <<, <, ~, >, >>

        # Count signal fires (only actionable signals)
        if signal in ENTRY_SIGNALS or signal in EXIT_SIGNALS:
            results["signal_fires"][signal] += 1

            # Check T=0 coincidence
            for level, tp_type in bar_zz[i]:
                results["pivot_at_fire"][signal][(level, tp_type)] += 1

            # Forward scan for each window
            for window in FORWARD_WINDOWS:
                best_dist = None
                found_hit = False
                for j in range(i + 1, min(i + window + 1, n)):
                    for level, tp_type in bar_zz[j]:
                        # Entry signals look for bottoms (MIN)
                        if signal in ENTRY_SIGNALS and tp_type == "MIN":
                            results["forward_hits"][signal][window][level] += 1
                            found_hit = True
                            if best_dist is None:
                                best_dist = j - i
                        # Exit signals look for tops (MAX)
                        elif signal in EXIT_SIGNALS and tp_type == "MAX":
                            results["forward_hits"][signal][window][level] += 1
                            found_hit = True
                            if best_dist is None:
                                best_dist = j - i

                if found_hit:
                    unique_hits[signal][window] += 1
                if best_dist is not None and window == 10:
                    results["distances"][signal].append(best_dist)

        # Track ALL pivots in each zone for recall calculation
        for level, tp_type in bar_zz[i]:
            results["total_pivots_in_zone"][(zone, tp_type)][level] += 1

            # Check if ANY actionable signal fired on this bar
            if tp_type == "MIN" and signal not in ENTRY_SIGNALS:
                results["missed_pivots"][(zone, "MIN")][level] += 1
            elif tp_type == "MAX" and signal not in EXIT_SIGNALS:
                results["missed_pivots"][(zone, "MAX")][level] += 1

    results["unique_hits"] = dict(unique_hits)
    return results


def merge_results(all_results):
    """Merge per-ticker results into global stats."""
    merged = {
        "signal_fires": Counter(),
        "forward_hits": defaultdict(lambda: defaultdict(lambda: defaultdict(int))),
        "unique_hits": defaultdict(lambda: defaultdict(int)),
        "distances": defaultdict(list),
        "pivot_at_fire": defaultdict(lambda: defaultdict(int)),
        "missed_pivots": defaultdict(lambda: defaultdict(int)),
        "total_pivots_in_zone": defaultdict(lambda: defaultdict(int)),
    }

    for r in all_results:
        if r is None:
            continue
        for sig, count in r["signal_fires"].items():
            merged["signal_fires"][sig] += count
        for sig, windows in r["forward_hits"].items():
            for w, levels in windows.items():
                for lvl, cnt in levels.items():
                    merged["forward_hits"][sig][w][lvl] += cnt
        for sig, dists in r["distances"].items():
            merged["distances"][sig].extend(dists)
        for sig, windows in r.get("unique_hits", {}).items():
            for w, cnt in windows.items():
                merged["unique_hits"][sig][w] += cnt
        for sig, levels in r["pivot_at_fire"].items():
            for key, cnt in levels.items():
                merged["pivot_at_fire"][sig][key] += cnt
        for zone_tp, levels in r["missed_pivots"].items():
            for lvl, cnt in levels.items():
                merged["missed_pivots"][zone_tp][lvl] += cnt
        for zone_tp, levels in r["total_pivots_in_zone"].items():
            for lvl, cnt in levels.items():
                merged["total_pivots_in_zone"][zone_tp][lvl] += cnt

    return merged


# ═══════════════════════════════════════════════════════════════
# Threshold Sensitivity Scan
# ═══════════════════════════════════════════════════════════════
def threshold_sensitivity_scan(bars_all, zigzags_all, derived_data):
    """Scan key thresholds to find LIFT-maximizing values.

    Re-classifies the 180 states at each threshold step,
    then re-evaluates forward hits across all tickers.
    """
    from backend.scripts.generate_tide_derived_table import (
        classify_signal as _classify_signal_original,
        _CEILING_ZZ50_MAX_BASELINE,
    )

    states = derived_data.get("l3_states", derived_data.get("states", {}))

    state_metrics = {}
    for key, v in states.items():
        if "identity" in v:
            zone = v["identity"]["zone"]
            p_b = v["direction"]["p_bull"]
            zz25_min = v["turn_risk"]["bottom_25"]["pct"]
            zz25_max = v["turn_risk"]["top_25"]["pct"]
            asym = v["turn_risk"]["asymmetry_pp"]
            purity = v["composition"]["momentum_purity"]
            zz50_min = v["turn_risk"]["bottom_50"]["pct"]
            zz75_min = v["turn_risk"]["bottom_75"]["pct"]
            zz50_max = v["turn_risk"]["top_50"]["pct"]
        else:
            levels = v.get("levels", {})
            zz25 = levels.get("zz25", {})
            zz50 = levels.get("zz50", {})
            zz75 = levels.get("zz75", {})
            parts = key.split("|")
            zone = parts[2] if len(parts) >= 3 else "~"
            p_b = zz50.get("p_bull", 0.5) * 100.0 if zz50.get("p_bull", 0.5) <= 1.0 else zz50.get("p_bull", 50.0)
            zz25_min = abs(zz25.get("e_ret_min", 0.0)) * 100.0
            zz25_max = zz25.get("e_ret_max", 0.0) * 100.0
            asym = zz50.get("rr_asymmetry", 1.0)
            purity = 50.0
            zz50_min = abs(zz50.get("e_ret_min", 0.0)) * 100.0
            zz75_min = abs(zz75.get("e_ret_min", 0.0)) * 100.0
            zz50_max = zz50.get("e_ret_max", 0.0) * 100.0

        state_metrics[key] = {
            "zone": zone,
            "p_bull": p_b,
            "zz25_min_pct": zz25_min,
            "zz25_max_pct": zz25_max,
            "asym_pp": asym,
            "momentum_purity": purity,
            "zz50_min_pct": zz50_min,
            "zz75_min_pct": zz75_min,
            "zz50_max_pct": zz50_max,
        }

    # Thresholds to scan — (id, label, lo, hi, step, target_signal, pivot_type)
    scans = [
        ("p_bull_accum", "p_bull < X (ACCUMULATE)", 30.0, 42.0, 1.0, "ACCUMULATE", "MIN"),
        ("zz75_accum", "zz75_min > X (ACCUMULATE)", 5.0, 12.0, 0.5, "ACCUMULATE", "MIN"),
        ("asym_buydip", "asym_pp > X (BUY_DIP)", 10.0, 25.0, 1.0, "BUY_DIP", "MIN"),
        ("zz25_tp", "zz25_max > X (TAKE_PROFIT)", 12.0, 20.0, 0.5, "TAKE_PROFIT", "MAX"),
        ("zz50_tp", "zz50_max > X (TAKE_PROFIT zone guard)", 5.5, 9.0, 0.25, "TAKE_PROFIT", "MAX"),
        ("pbull_momentum", "p_bull > X (MOMENTUM ABOVE)", 63.0, 78.0, 1.0, "MOMENTUM", None),
    ]

    results = {}

    # Pre-classify and pre-build lookup structures to avoid repeating costly calculations
    print("  Pre-classifying bars for sensitivity scan...")
    preclassified_data = []
    for ticker, bars in bars_all.items():
        nb = len(bars)
        if nb < 100:
            continue
        zz = zigzags_all.get(ticker, {})
        sk_list = []
        bar_dates = []
        for date, t_slope, c_slope, svw in bars:
            t = classify_slope(t_slope, 'T')
            c = classify_slope(c_slope, 'C')
            s = classify_sigma_vw(svw)
            sk_list.append(f"{t}|{c}|{s}")
            bar_dates.append(date)
        preclassified_data.append((sk_list, bar_dates, zz))
    print(f"  → Pre-classified {len(preclassified_data)} tickers")

    for scan_id, label, lo, hi, step, target_signal, pivot_type in scans:
        print(f"  Scanning: {label} [{lo:.1f} → {hi:.1f}]")
        scan_results = []
        threshold = lo
        while threshold <= hi + 0.001:
            # Re-classify states with modified threshold
            new_lookup = {}
            for key, m in state_metrics.items():
                sig = _reclassify(m, scan_id, threshold)
                new_lookup[key] = sig

            # Per-signal eval: count fires and unique binary hits
            sig_fires = 0
            sig_hits = 0

            if pivot_type is None:
                # MOMENTUM — just count how many states fire this signal
                sig_fires = sum(1 for v in new_lookup.values() if v == target_signal)
                scan_results.append({
                    "threshold": round(threshold, 2),
                    "states_classified": sig_fires,
                    "fires": 0, "hits": 0, "precision": 0.0,
                })
                threshold += step
                continue

            for sk_list, bar_dates, zz in preclassified_data:
                nb = len(sk_list)
                for i in range(nb):
                    sk = sk_list[i]
                    sig = new_lookup.get(sk, "NO_EDGE")

                    if sig == target_signal:
                        sig_fires += 1
                        # Binary hit: at least one pivot of matching type in 10 bars
                        for j in range(i+1, min(i+11, nb)):
                            dj = bar_dates[j]
                            for level, tp in zz.get(dj, []):
                                if tp == pivot_type:
                                    sig_hits += 1
                                    break
                            else:
                                continue
                            break

            prec = sig_hits / sig_fires * 100 if sig_fires > 0 else 0
            scan_results.append({
                "threshold": round(threshold, 2),
                "fires": sig_fires,
                "hits": sig_hits,
                "precision": round(prec, 2),
            })
            threshold += step

        results[scan_id] = {"label": label, "target": target_signal, "data": scan_results}

    return results


_CEILING_ZZ50_BASELINE_DEFAULT = 7.15

def _reclassify(m, scan_id, threshold):
    """Re-classify a single state with one threshold modified."""
    zone = m["zone"]
    p_bull = m["p_bull"]
    zz25_min = m["zz25_min_pct"]
    zz25_max = m["zz25_max_pct"]
    asym = m["asym_pp"]
    purity = m["momentum_purity"]
    zz50_min = m["zz50_min_pct"]
    zz75_min = m["zz75_min_pct"]
    zz50_max = m["zz50_max_pct"]

    # Override the scanned parameter
    pb_accum = 38.0
    zz75_th = 8.0
    asym_th = 15.0
    zz25_tp_th = 15.0
    zz50_tp_th = _CEILING_ZZ50_BASELINE_DEFAULT
    pb_mom = 70.0

    if scan_id == "p_bull_accum":
        pb_accum = threshold
    elif scan_id == "zz75_accum":
        zz75_th = threshold
    elif scan_id == "asym_buydip":
        asym_th = threshold
    elif scan_id == "zz25_tp":
        zz25_tp_th = threshold
    elif scan_id == "zz50_tp":
        zz50_tp_th = threshold
    elif scan_id == "pbull_momentum":
        pb_mom = threshold

    if zone == "FLOOR" and p_bull < pb_accum and (zz75_min > zz75_th or zz50_min > 12.0):
        return "ACCUMULATE"
    if zone in ("FLOOR", "BELOW") and p_bull < 46.0 and (asym > asym_th or zz25_min > 18.0):
        return "BUY_DIP"
    if zone == "CEILING" and (zz25_max > zz25_tp_th or zz50_max > zz50_tp_th):
        return "TAKE_PROFIT"
    if zone == "CEILING" and p_bull > 78.0 and zz25_max < 12.0:
        return "STRONG_TREND"
    if zone == "CEILING":
        return "REDUCE"
    if zone == "ABOVE" and p_bull > pb_mom and purity > 70.0 and zz25_max < 10.0:
        return "MOMENTUM"
    if zone == "ABOVE" and p_bull > 65.0 and zz25_max < 10.0:
        return "BULL_TREND"
    if zone in ("FLOOR", "BELOW"):
        return "WATCH"
    return "NO_EDGE"


# ═══════════════════════════════════════════════════════════════
# Report Generation
# ═══════════════════════════════════════════════════════════════
def generate_report(merged, total_bars, n_tickers, sensitivity, derived_data):
    """Generate the final Markdown report."""
    lines = []
    L = lines.append

    L("# Signal Reliability Evaluation Report")
    L(f"\n> **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L(f"> **Bars analyzed:** {total_bars:,} across {n_tickers} tickers")
    L(f"> **Forward windows:** {FORWARD_WINDOWS}")
    L("")

    # ── Section 1: Signal Scorecard ──
    L("## 1. Signal Scorecard\n")

    # Compute baseline hit rate (any pivot within 10 bars for the whole market)
    # This is approximately: total_pivots / total_bars
    total_min = sum(
        cnt for (zone_tp, lvl_dict) in merged["total_pivots_in_zone"].items()
        for lvl, cnt in lvl_dict.items()
        if zone_tp[1] == "MIN"
    )
    total_max = sum(
        cnt for (zone_tp, lvl_dict) in merged["total_pivots_in_zone"].items()
        for lvl, cnt in lvl_dict.items()
        if zone_tp[1] == "MAX"
    )
    baseline_min_rate = total_min / total_bars if total_bars > 0 else 0
    baseline_max_rate = total_max / total_bars if total_bars > 0 else 0

    L("### Entry Signals (look for bottoms)")
    L(f"\nBaseline: {total_min:,} total MIN pivots across all zones ({baseline_min_rate:.1%} per bar)\n")
    L("| Signal | Fires | Unique Hits@10 | Precision | @5 | @20 | Avg Dist | LIFT |")
    L("|---|---:|---:|---:|---:|---:|---:|---:|")

    for sig in ["ACCUMULATE", "BUY_DIP"]:
        fires = merged["signal_fires"].get(sig, 0)
        uhits_10 = merged["unique_hits"].get(sig, {}).get(10, 0)
        uhits_5 = merged["unique_hits"].get(sig, {}).get(5, 0)
        uhits_20 = merged["unique_hits"].get(sig, {}).get(20, 0)
        prec_10 = uhits_10 / fires if fires > 0 else 0
        dists = merged["distances"].get(sig, [])
        avg_dist = np.mean(dists) if dists else 0
        lift = prec_10 / baseline_min_rate if baseline_min_rate > 0 else 0
        L(f"| **{sig}** | {fires:,} | {uhits_10:,} | {prec_10:.1%} | {uhits_5 / fires if fires else 0:.1%} | {uhits_20 / fires if fires else 0:.1%} | {avg_dist:.1f} bars | {lift:.2f}x |")

    L("")
    L("### Exit Signals (look for tops)")
    L(f"\nBaseline: {total_max:,} total MAX pivots across all zones ({baseline_max_rate:.1%} per bar)\n")
    L("| Signal | Fires | Unique Hits@10 | Precision | @5 | @20 | Avg Dist | LIFT |")
    L("|---|---:|---:|---:|---:|---:|---:|---:|")

    for sig in ["TAKE_PROFIT", "REDUCE"]:
        fires = merged["signal_fires"].get(sig, 0)
        uhits_10 = merged["unique_hits"].get(sig, {}).get(10, 0)
        uhits_5 = merged["unique_hits"].get(sig, {}).get(5, 0)
        uhits_20 = merged["unique_hits"].get(sig, {}).get(20, 0)
        prec_10 = uhits_10 / fires if fires > 0 else 0
        dists = merged["distances"].get(sig, [])
        avg_dist = np.mean(dists) if dists else 0
        lift = prec_10 / baseline_max_rate if baseline_max_rate > 0 else 0
        L(f"| **{sig}** | {fires:,} | {uhits_10:,} | {prec_10:.1%} | {uhits_5 / fires if fires else 0:.1%} | {uhits_20 / fires if fires else 0:.1%} | {avg_dist:.1f} bars | {lift:.2f}x |")

    # ── Section 2: ZZ Level Profile ──
    L("\n## 2. Zigzag Level Profile (10-bar window)\n")
    L("Which zigzag levels does each signal capture?\n")
    L("| Signal | 2.5% hits | 5.0% hits | 7.5% hits | % of hits from 5%+ |")
    L("|---|---:|---:|---:|---:|")

    for sig in ["ACCUMULATE", "BUY_DIP", "TAKE_PROFIT", "REDUCE"]:
        h10 = merged["forward_hits"].get(sig, {}).get(10, {})
        h25 = h10.get(0.025, 0)
        h50 = h10.get(0.05, 0)
        h75 = h10.get(0.075, 0)
        total_h = h25 + h50 + h75
        pct_major = (h50 + h75) / total_h * 100 if total_h > 0 else 0
        L(f"| **{sig}** | {h25:,} | {h50:,} | {h75:,} | {pct_major:.1f}% |")

    # ── Section 3: Distance Distribution ──
    L("\n## 3. Distance to Nearest Pivot (10-bar window)\n")
    for sig in ["ACCUMULATE", "BUY_DIP", "TAKE_PROFIT", "REDUCE"]:
        dists = merged["distances"].get(sig, [])
        if not dists:
            continue
        arr = np.array(dists)
        L(f"### {sig}")
        L(f"- N = {len(dists):,}")
        L(f"- Mean: {arr.mean():.1f} bars")
        L(f"- Median: {np.median(arr):.0f} bars")
        L(f"- P25: {np.percentile(arr, 25):.0f} bars")
        L(f"- P75: {np.percentile(arr, 75):.0f} bars")

        # Histogram buckets
        buckets = [0]*11
        for d in dists:
            if d <= 10:
                buckets[d] += 1
        L(f"- Distribution: ", )
        hist_str = " | ".join(f"d={d}: {buckets[d]:,}" for d in range(1, 11))
        L(f"  {hist_str}")
        L("")

    # ── Section 4: Missed Pivots ──
    L("\n## 4. Missed Pivots (pivots where signal was HOLD/WATCH/NO_EDGE)\n")

    # Map sigma zones
    zone_names = {"<<": "FLOOR", "<": "BELOW", "~": "NEUTRAL", ">": "ABOVE", ">>": "CEILING"}

    L("### Missed Bottoms (pivots where no ACCUMULATE/BUY_DIP fired)")
    L("| Zone | 2.5% missed | 5.0% missed | 7.5% missed | Total in zone | Recall 5%+ |")
    L("|---|---:|---:|---:|---:|---:|")

    for zone_key in ["<<", "<", "~", ">", ">>"]:
        missed = merged["missed_pivots"].get((zone_key, "MIN"), {})
        total = merged["total_pivots_in_zone"].get((zone_key, "MIN"), {})
        m25 = missed.get(0.025, 0)
        m50 = missed.get(0.05, 0)
        m75 = missed.get(0.075, 0)
        t50 = total.get(0.05, 0)
        t75 = total.get(0.075, 0)
        total_zone = sum(total.values())
        caught_major = (t50 - m50) + (t75 - m75)
        total_major = t50 + t75
        recall = caught_major / total_major if total_major > 0 else 0
        zn = zone_names.get(zone_key, zone_key)
        L(f"| {zn} | {m25:,} | {m50:,} | {m75:,} | {total_zone:,} | {recall:.1%} |")

    L("\n### Missed Tops (pivots where no TAKE_PROFIT/REDUCE fired)")
    L("| Zone | 2.5% missed | 5.0% missed | 7.5% missed | Total in zone | Recall 5%+ |")
    L("|---|---:|---:|---:|---:|---:|")

    for zone_key in ["<<", "<", "~", ">", ">>"]:
        missed = merged["missed_pivots"].get((zone_key, "MAX"), {})
        total = merged["total_pivots_in_zone"].get((zone_key, "MAX"), {})
        m25 = missed.get(0.025, 0)
        m50 = missed.get(0.05, 0)
        m75 = missed.get(0.075, 0)
        t50 = total.get(0.05, 0)
        t75 = total.get(0.075, 0)
        total_zone = sum(total.values())
        caught_major = (t50 - m50) + (t75 - m75)
        total_major = t50 + t75
        recall = caught_major / total_major if total_major > 0 else 0
        zn = zone_names.get(zone_key, zone_key)
        L(f"| {zn} | {m25:,} | {m50:,} | {m75:,} | {total_zone:,} | {recall:.1%} |")

    # ── Section 5: Threshold Sensitivity ──
    if sensitivity:
        L("\n## 5. Threshold Sensitivity Scan\n")
        L("For each threshold, precision is measured at 10-bar window.\n")

        for scan_id, scan_data in sensitivity.items():
            label = scan_data["label"]
            target = scan_data.get("target", "?")
            data = scan_data["data"]
            L(f"### {label} (target: {target})\n")

            # Check if MOMENTUM scan (no forward hits)
            if data and "states_classified" in data[0]:
                L("| Threshold | States Classified |")
                L("|---:|---:|")
                for d in data:
                    L(f"| {d['threshold']} | {d['states_classified']} |")
                L("")
                continue

            L(f"| Threshold | {target} Fires | Hits | Precision | Δ vs Current |")
            L("|---:|---:|---:|---:|---:|")
            # Use middle threshold as "current" baseline for delta
            current_idx = len(data) // 2
            current_prec = data[current_idx]["precision"] if data else 0
            for d in data:
                delta = d["precision"] - current_prec
                marker = " ◄" if d["precision"] == max(x["precision"] for x in data) else ""
                L(f"| {d['threshold']} | {d['fires']:,} | {d['hits']:,} | {d['precision']:.2f}% | {delta:+.2f}pp{marker} |")

            best = max(data, key=lambda x: x["precision"])
            L(f"\n> **Optimal:** threshold = {best['threshold']} → precision = {best['precision']:.2f}% ({best['fires']:,} fires, {best['hits']:,} hits)")
            L("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("Signal Reliability Evaluation")
    print("=" * 70)

    print("\n[1/5] Loading official probability table...")
    with open(DERIVED_PATH) as f:
        derived = json.load(f)

    from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_real_ev

    signal_lookup = {}
    l3_dict = derived.get("l3_states", {})
    for k in l3_dict.keys():
        parts = k.split("|")
        if len(parts) == 3:
            t_s, c_s, svw = parts
            sig_obj = lookup_real_ev(t_slope=t_s, c_slope=c_s, svw=svw, level="zz50")
            if sig_obj:
                sig_name = sig_obj.signal
                if sig_name == "TRIM":
                    sig_name = "TAKE_PROFIT"
                signal_lookup[k] = sig_name

    print(f"  → {len(signal_lookup)} estados L3 clasificados mediante el adaptador de EV Real")

    # Load all data
    print("\n[2/5] Loading data from Vault...")
    store = TimescaleDataStore()
    bars_all, zigzags_all = load_all_data(store)
    n_tickers = len(bars_all)
    total_bars = sum(len(bars) for bars in bars_all.values())
    print(f"  → {total_bars:,} bars across {n_tickers} tickers")

    # Evaluate per ticker
    print(f"\n[3/5] Evaluating signal reliability across {n_tickers} tickers...")
    all_results = []
    t0 = time.time()
    for i, (ticker, bars) in enumerate(sorted(bars_all.items())):
        zz = zigzags_all.get(ticker, {})
        r = evaluate_ticker(bars, zz, signal_lookup)
        all_results.append(r)
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"    {i+1}/{n_tickers} ({elapsed:.0f}s)")

    elapsed = time.time() - t0
    print(f"  → Done in {elapsed:.1f}s")

    # Merge results
    merged = merge_results(all_results)

    # Quick summary before sensitivity scan
    print("\n  Signal fires summary:")
    for sig in ["ACCUMULATE", "BUY_DIP", "TAKE_PROFIT", "REDUCE",
                 "MOMENTUM", "STRONG_TREND", "BULL_TREND", "WATCH", "NO_EDGE"]:
        fires = merged["signal_fires"].get(sig, 0)
        if fires > 0:
            hits = sum(merged["forward_hits"].get(sig, {}).get(10, {}).values())
            prec = hits / fires if fires > 0 else 0
            print(f"    {sig:<15}: {fires:>8,} fires, {hits:>7,} hits@10, precision={prec:.1%}")

    # Threshold sensitivity
    print(f"\n[4/5] Running threshold sensitivity scan...")
    t0 = time.time()
    sensitivity = threshold_sensitivity_scan(bars_all, zigzags_all, derived)
    print(f"  → Done in {time.time()-t0:.1f}s")

    # Generate report
    print(f"\n[5/5] Generating report...")
    report = generate_report(merged, total_bars, n_tickers, sensitivity, derived)

    output_path = Path(
        "/root/.gemini/antigravity-ide/brain/f5b8323c-589c-4ffd-bbc9-0eb7dfac9909"
        "/signal_reliability_report.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)
    print(f"\n  Report saved to: {output_path}")
    print("  DONE.")


if __name__ == "__main__":
    main()
