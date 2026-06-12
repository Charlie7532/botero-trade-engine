#!/usr/bin/env python3
"""
Temporal Conjunction Precision — WHERE do the conjunctions fire?
=================================================================
Same top conjunctions, but measured at THREE separate windows:
  t-2 ONLY: Truly anticipatory (2 bars before turn)
  t-1 ONLY: Alert (1 bar before turn)
  t=0 ONLY: Detection/Reactive (AT the turn — HISTORY)

If precision comes from t=0, the signal is reactive = useless for entry.
If precision comes from t-2 or t-1, the signal is anticipatory = actionable.
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

ZZ_SCALE = 0.05
Z_THRESHOLD = 2.0
WARMUP = 250

# Best combos from conjunction forensics
COMBOS = {
    "LL": [
        # Singles
        ["vwap_sigma_current"],
        ["vwap_sigma_tide"],
        ["sigma_tide"],
        # Best pairs
        ["vwap_sigma_current", "wave_slope"],
        ["vwap_sigma_tide", "sigma_current"],
        ["vwap_sigma_current", "vwap_sigma_tide"],
        ["vwap_sigma_current", "kf_price_pred_val"],
        ["rsi_value", "fear_level"],
        # Best triples
        ["vwap_sigma_current", "vwap_sigma_tide", "sigma_tide"],
        ["vwap_sigma_current", "vwap_sigma_tide", "vwap_sigma_wave"],
        ["vwap_sigma_current", "vwap_sigma_tide", "rsi_value"],
        ["vwap_sigma_current", "sigma_tide", "rsi_value"],
    ],
    "HL": [
        ["sigma_current"],
        ["sigma_current", "kf_tension_filt_vel"],
        ["sigma_current", "vwap_sigma_wave"],
        ["sigma_current", "sigma_wave", "kf_rsi_filt_vel"],
        ["sigma_current", "kf_price_pred_val", "kf_rsi_filt_vel"],
    ],
    "HH": [
        ["kf_conj_pred_val"],
        ["kf_conj_pred_val", "current_accel"],
        ["kf_conj_pred_val", "current_accel", "vwap_spread_tide_current"],
    ],
    "LH": [
        ["kf_price_pred_val"],
        ["kf_price_pred_val", "compression_ratio"],
        ["kf_price_pred_val", "kf_conj_filt_vel", "compression_ratio"],
        ["kf_price_pred_val", "kf_price_filt_vel", "compression_ratio"],
    ],
}

ALL_FEATURES = list(set(f for combos in COMBOS.values() for c in combos for f in c))

OUT_DIR = root_dir / "backend" / "scripts" / "temporal_conjunction_output"
OUT_DIR.mkdir(exist_ok=True)
LOG = []
T0 = time.time()

def log(msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.append(line)

def log_section(title):
    log("═" * 110)
    log(f"  {title}")
    log("═" * 110)


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


def analyze_temporal_conjunction(df, turns, archetype, combo):
    """For a specific combination, measure precision at t-2, t-1, t=0 separately."""
    n_bars = len(df)
    arch_turns = [t for t in turns if t["archetype"] == archetype]
    n_turns = len(arch_turns)
    if n_turns < 3:
        return None

    # Build conjunction fire mask (ALL features must fire simultaneously)
    conj_mask = np.ones(n_bars, dtype=bool)
    for feat in combo:
        z_col = f"z_{feat}"
        z_vals = df[z_col].values
        feat_mask = np.zeros(n_bars, dtype=bool)
        for i in range(WARMUP, n_bars):
            if abs(z_vals[i]) > Z_THRESHOLD:
                feat_mask[i] = True
        conj_mask &= feat_mask

    fire_indices = np.where(conj_mask)[0]
    total_fires = len(fire_indices)
    if total_fires < 1:
        return None

    # Build turn bar sets for each offset
    turn_bars_at = {}
    for offset in [-2, -1, 0]:
        bars = set()
        for t in arch_turns:
            idx = t["bar_idx"] + offset
            if 0 <= idx < n_bars:
                bars.add(idx)
        turn_bars_at[offset] = bars

    # Combined (t-2..t=0)
    turn_bars_combined = turn_bars_at[-2] | turn_bars_at[-1] | turn_bars_at[0]

    # Count TPs at each offset
    tp_at = {-2: 0, -1: 0, 0: 0}
    tp_combined = 0
    fp = 0

    for fire_idx in fire_indices:
        is_tp = False
        for offset in [-2, -1, 0]:
            if fire_idx in turn_bars_at[offset]:
                tp_at[offset] += 1
                is_tp = True
                # Don't break — a fire can be t-2 of one turn and t=0 of another
                # but in practice these don't overlap at 5% zigzag
                break
        if is_tp:
            tp_combined += 1
        else:
            fp += 1

    # Recall at each offset
    recall_at = {}
    for offset in [-2, -1, 0]:
        hits = 0
        for t in arch_turns:
            idx = t["bar_idx"] + offset
            if 0 <= idx < n_bars and conj_mask[idx]:
                hits += 1
        recall_at[offset] = hits / n_turns

    # Combined recall
    combined_hits = 0
    for t in arch_turns:
        found = False
        for offset in [-2, -1, 0]:
            idx = t["bar_idx"] + offset
            if 0 <= idx < n_bars and conj_mask[idx]:
                found = True
                break
        if found:
            combined_hits += 1
    recall_combined = combined_hits / n_turns

    return {
        "combo": " + ".join(combo),
        "n_features": len(combo),
        "total_fires": total_fires,
        "tp_at_t-2": tp_at[-2],
        "tp_at_t-1": tp_at[-1],
        "tp_at_t0": tp_at[0],
        "tp_combined": tp_combined,
        "fp": fp,
        "prec_t-2": tp_at[-2] / total_fires if total_fires > 0 else 0,
        "prec_t-1": tp_at[-1] / total_fires if total_fires > 0 else 0,
        "prec_t0": tp_at[0] / total_fires if total_fires > 0 else 0,
        "prec_combined": tp_combined / total_fires if total_fires > 0 else 0,
        "recall_t-2": recall_at[-2],
        "recall_t-1": recall_at[-1],
        "recall_t0": recall_at[0],
        "recall_combined": recall_combined,
        "n_turns": n_turns,
    }


def report_ticker(ticker, results):
    log_section(f"TICKER: {ticker}")

    for archetype in ["LL", "HL", "HH", "LH"]:
        if archetype not in results or not results[archetype]:
            continue

        log(f"\n  ── {archetype} ──")
        log(f"  {'Combo':<55s} │ {'Fires':>5s} │ {'P(t-2)':>6s} │ {'P(t-1)':>6s} │ {'P(t=0)':>6s} │ "
            f"{'P(all)':>6s} │ {'R(t-2)':>6s} │ {'R(t-1)':>6s} │ {'R(t=0)':>6s} │ {'R(all)':>6s} │ {'Verdict':>12s}")
        log(f"  {'─'*55} │ {'─'*5} │ {'─'*6} │ {'─'*6} │ {'─'*6} │ "
            f"{'─'*6} │ {'─'*6} │ {'─'*6} │ {'─'*6} │ {'─'*6} │ {'─'*12}")

        for r in results[archetype]:
            # Classify where the signal lives
            total_tp = r["tp_at_t-2"] + r["tp_at_t-1"] + r["tp_at_t0"]
            if total_tp == 0:
                verdict = "DEAD"
                pct_anticipatory = 0
            else:
                pct_before = (r["tp_at_t-2"] + r["tp_at_t-1"]) / total_tp * 100
                pct_at = r["tp_at_t0"] / total_tp * 100
                if pct_before >= 60:
                    verdict = "★ ANTICIPA"
                elif pct_before >= 40:
                    verdict = "MIXED"
                else:
                    verdict = "⚠ REACTIVA"

            log(f"  {r['combo']:<55s} │ {r['total_fires']:>5d} │ "
                f"{r['prec_t-2']*100:>5.1f}% │ {r['prec_t-1']*100:>5.1f}% │ {r['prec_t0']*100:>5.1f}% │ "
                f"{r['prec_combined']*100:>5.1f}% │ "
                f"{r['recall_t-2']*100:>5.1f}% │ {r['recall_t-1']*100:>5.1f}% │ {r['recall_t0']*100:>5.1f}% │ "
                f"{r['recall_combined']*100:>5.1f}% │ {verdict:>12s}")


def cross_ticker_summary(all_ticker_results):
    log_section("CROSS-TICKER TEMPORAL CONJUNCTION SUMMARY")
    log("  P(t-2) = precision if we only count fires 2 bars BEFORE the turn")
    log("  P(t-1) = precision if we only count fires 1 bar BEFORE the turn")
    log("  P(t=0) = precision if we only count fires AT the turn (= HISTORY)")
    log("  ANTICIPA = >60% of TPs are at t-2 or t-1 (actionable)")
    log("  REACTIVA = >60% of TPs are at t=0 (too late)")

    for archetype in ["LL", "HL", "HH", "LH"]:
        log(f"\n  ── {archetype} ──")

        # Collect all combos
        combo_data = {}
        for ticker, results in all_ticker_results.items():
            if archetype not in results:
                continue
            for r in results[archetype]:
                if r is None or r["total_fires"] < 1:
                    continue
                combo_data.setdefault(r["combo"], []).append(r)

        if not combo_data:
            continue

        log(f"  {'Combo':<55s} │ {'#Tk':>3s} │ {'MedP t-2':>8s} │ {'MedP t-1':>8s} │ {'MedP t=0':>8s} │ "
            f"{'MedP all':>8s} │ {'MedR all':>8s} │ {'%Antic':>6s} │ {'Verdict':>12s}")
        log(f"  {'─'*55} │ {'─'*3} │ {'─'*8} │ {'─'*8} │ {'─'*8} │ "
            f"{'─'*8} │ {'─'*8} │ {'─'*6} │ {'─'*12}")

        rows = []
        for combo, data_list in combo_data.items():
            if len(data_list) < 5:
                continue
            med_p2 = np.median([d["prec_t-2"] for d in data_list]) * 100
            med_p1 = np.median([d["prec_t-1"] for d in data_list]) * 100
            med_p0 = np.median([d["prec_t0"] for d in data_list]) * 100
            med_pa = np.median([d["prec_combined"] for d in data_list]) * 100
            med_ra = np.median([d["recall_combined"] for d in data_list]) * 100

            # Aggregate TP distribution
            total_tp2 = sum(d["tp_at_t-2"] for d in data_list)
            total_tp1 = sum(d["tp_at_t-1"] for d in data_list)
            total_tp0 = sum(d["tp_at_t0"] for d in data_list)
            total_tp = total_tp2 + total_tp1 + total_tp0
            pct_antic = (total_tp2 + total_tp1) / max(total_tp, 1) * 100

            if pct_antic >= 60:
                verdict = "★ ANTICIPA"
            elif pct_antic >= 40:
                verdict = "MIXED"
            else:
                verdict = "⚠ REACTIVA"

            rows.append({
                "combo": combo,
                "n_tk": len(data_list),
                "med_p2": med_p2, "med_p1": med_p1, "med_p0": med_p0,
                "med_pa": med_pa, "med_ra": med_ra,
                "pct_antic": pct_antic, "verdict": verdict,
                "total_tp2": total_tp2, "total_tp1": total_tp1, "total_tp0": total_tp0,
            })

        rows.sort(key=lambda x: x["med_pa"], reverse=True)

        for r in rows:
            log(f"  {r['combo']:<55s} │ {r['n_tk']:>3d} │ "
                f"{r['med_p2']:>7.1f}% │ {r['med_p1']:>7.1f}% │ {r['med_p0']:>7.1f}% │ "
                f"{r['med_pa']:>7.1f}% │ {r['med_ra']:>7.1f}% │ "
                f"{r['pct_antic']:>5.0f}% │ {r['verdict']:>12s}")

        # TP breakdown for best combo
        if rows:
            best = rows[0]
            log(f"\n  TP BREAKDOWN for best ({best['combo']}):")
            log(f"    t-2: {best['total_tp2']} TPs ({best['total_tp2']/(best['total_tp2']+best['total_tp1']+best['total_tp0'])*100:.0f}%)")
            log(f"    t-1: {best['total_tp1']} TPs ({best['total_tp1']/(best['total_tp2']+best['total_tp1']+best['total_tp0'])*100:.0f}%)")
            log(f"    t=0: {best['total_tp0']} TPs ({best['total_tp0']/(best['total_tp2']+best['total_tp1']+best['total_tp0'])*100:.0f}%)")


if __name__ == "__main__":
    log_section("TEMPORAL CONJUNCTION — Are signals anticipatory or reactive?")
    log(f"  ZigZag: {ZZ_SCALE*100:.0f}%   Z: {Z_THRESHOLD}σ")

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
        for archetype, combos in COMBOS.items():
            arch_results = []
            for combo in combos:
                # Check all features exist
                if all(f"z_{f}" in df.columns for f in combo):
                    r = analyze_temporal_conjunction(df, turns, archetype, combo)
                    if r is not None:
                        arch_results.append(r)
            ticker_results[archetype] = arch_results

        all_ticker_results[ticker] = ticker_results
        report_ticker(ticker, ticker_results)

    store.close()
    cross_ticker_summary(all_ticker_results)

    elapsed = time.time() - T0
    log(f"\n  COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    log_path = OUT_DIR / f"temporal_conj_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(LOG))
    log(f"  Log: {log_path}")
