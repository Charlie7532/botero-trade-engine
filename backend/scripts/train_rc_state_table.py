#!/usr/bin/env python3
"""
RC State Intelligence Table — Training Script

Processes all 17 tickers individually. For each:
  1. Classifies RC state (7 states) at every bar
  2. Deduplicates entries (first bar of each pullback where σ ≤ -1.5)
  3. Measures risk/reward vs zigzag truth (MIN/MAX)
  4. Computes detection rates at zigzag inflection points
  5. Splits train (2006-2020) / test (2020-2026)

Output: per-ticker stats + GLOBAL table + detection rates
"""

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np
import json
import sys
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

SIGMA_ENTRY_THRESHOLD = -1.5
SIGMA_EXIT_THRESHOLD = 1.5
TRAIN_CUTOFF = pd.Timestamp("2020-01-01", tz="UTC")
EMBARGO_BARS = 20
MIN_SAMPLES_TICKER = 10
MIN_SAMPLES_GLOBAL = 30

MATURITY_BINS = [
    (0, 5, "0-5%"),
    (5, 10, "5-10%"),
    (10, 15, "10-15%"),
    (15, 25, "15-25%"),
    (25, 100, ">25%"),
]

VWAP_TENSION_BINS = [
    (-999, -0.1, "NEGATIVE"),
    (-0.1, 0.1, "NEUTRAL"),
    (0.1, 999, "POSITIVE"),
]

STATE_LABELS = {
    "A": "BREATH_FUERTE",
    "B": "BREATH_MADURO",
    "C": "CORRECCION_PROFUNDA",
    "D": "REBOTE_EN_CURSO",
    "E": "CAIDA_ESTRUCTURAL",
    "F": "RALLY_EN_BEAR",
    "G": "TRANSICION",
}

STATE_DESCRIPTIONS = {
    "A": "Marea↑ accel | Trim↑ | Ola↓",
    "B": "Marea↑ decel | Trim↑ | Ola↓",
    "C": "Marea↑ | Trim↓ | Ola↓",
    "D": "Marea↑ | Ola↑ (rebotó)",
    "E": "Marea↓ | Ola↓ (todo baja)",
    "F": "Marea↓ | Ola↑ (contra-tend)",
    "G": "Mixto / flat",
}


# ═══════════════════════════════════════════════════════════════
# CLASSIFIERS
# ═══════════════════════════════════════════════════════════════

def classify_rc_state(row: pd.Series) -> str:
    """Classify RC state from slopes and acceleration."""
    ts = row["tide_slope"]
    cs = row["current_slope"]
    ws = row["wave_slope"]
    ta = row["tide_accel"]

    tide_up = ts > 0.01
    tide_down = ts < -0.01
    current_up = cs > 0
    current_down = cs < 0
    wave_up = ws > 0
    wave_down = ws < 0
    tide_accel = ta > 0 if not pd.isna(ta) else False

    if tide_up and current_up and wave_down:
        return "A" if tide_accel else "B"
    elif tide_up and current_down and wave_down:
        return "C"
    elif tide_up and wave_up:
        return "D"
    elif tide_down and wave_down:
        return "E"
    elif tide_down and wave_up:
        return "F"
    return "G"


def classify_maturity(drop_pct: float) -> str:
    """Classify maturity from drop since last zigzag MAX."""
    for lo, hi, label in MATURITY_BINS:
        if lo <= drop_pct < hi:
            return label
    return ">25%"


def classify_vwap_tension(tension_wave: float) -> str:
    """Classify VWAP tension from tension_wave field."""
    if pd.isna(tension_wave):
        return "NEUTRAL"
    for lo, hi, label in VWAP_TENSION_BINS:
        if lo <= tension_wave < hi:
            return label
    return "NEUTRAL"


def classify_accel(tide_accel: float) -> str:
    """Classify tide acceleration."""
    if pd.isna(tide_accel):
        return "DECEL"
    return "ACCEL" if tide_accel > 0 else "DECEL"


def grade_cell(ratio: float, win_rate: float, n: int, min_n: int) -> str:
    """Assign grade based on ratio, win rate, and sample size."""
    if n < min_n:
        return "INSUFFICIENT"
    if ratio >= 3.0 and win_rate >= 0.85:
        return "PREMIUM"
    if ratio >= 2.0 and win_rate >= 0.80:
        return "BUENA"
    if win_rate >= 0.70:
        return "MODERADA"
    return "EVITAR"


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_data():
    """Load channel snapshots, OHLCV, and zigzag points."""
    store = TimescaleDataStore()
    conn = store._conn()

    print("Loading channel_snapshots...")
    snapshots = pd.read_sql("""
        SELECT cs.ticker, cs.timestamp,
               o.close AS entry_price,
               cs.sigma_tide, cs.sigma_current, cs.sigma_wave,
               cs.tide_slope, cs.current_slope, cs.wave_slope,
               cs.tide_accel, cs.current_accel, cs.wave_accel,
               cs.vwap_sigma_wave, cs.tension_wave,
               cs.regime, cs.rsi_value
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars o
          ON o.ticker = cs.ticker AND o.time::date = cs.timestamp::date
        WHERE cs.timeframe = '1d'
        ORDER BY cs.ticker, cs.timestamp
    """, conn)

    print("Loading zigzag_points...")
    zigzag = pd.read_sql("""
        SELECT ticker, timestamp, tp_type, price
        FROM engine.zigzag_points
        WHERE min_swing_pct = 0.05
        ORDER BY ticker, timestamp
    """, conn)

    store._put(conn)
    store.close()

    print(f"  Snapshots: {len(snapshots):,} rows, {snapshots['ticker'].nunique()} tickers")
    print(f"  Zigzag:    {len(zigzag):,} points")
    return snapshots, zigzag


# ═══════════════════════════════════════════════════════════════
# PER-TICKER PROCESSING
# ═══════════════════════════════════════════════════════════════

def process_ticker(ticker: str, snapshots: pd.DataFrame, zigzag: pd.DataFrame):
    """Process a single ticker: classify, deduplicate, measure risk/reward."""

    tk_snap = snapshots[snapshots["ticker"] == ticker].sort_values("timestamp").copy()
    tk_zz = zigzag[zigzag["ticker"] == ticker].sort_values("timestamp")
    tk_zz_min = tk_zz[tk_zz["tp_type"] == "MIN"]
    tk_zz_max = tk_zz[tk_zz["tp_type"] == "MAX"]

    if len(tk_snap) < 100 or len(tk_zz_min) < 5:
        return None, None

    # ── Classify every bar ──
    tk_snap["rc_state"] = tk_snap.apply(classify_rc_state, axis=1)
    tk_snap["vwap_tension"] = tk_snap["tension_wave"].apply(classify_vwap_tension)
    tk_snap["accel_zone"] = tk_snap["tide_accel"].apply(classify_accel)

    # ── Deduplicate: first bar of each pullback ──
    entries = []
    in_zone = False
    for _, row in tk_snap.iterrows():
        if row["sigma_current"] <= SIGMA_ENTRY_THRESHOLD and not in_zone:
            entries.append(row)
            in_zone = True
        elif row["sigma_current"] > SIGMA_ENTRY_THRESHOLD:
            in_zone = False

    if not entries:
        return None, None

    entries_df = pd.DataFrame(entries)

    # ── Measure risk/reward for each entry ──
    results = []
    for _, bar in entries_df.iterrows():
        ep = bar["entry_price"]
        et = bar["timestamp"]

        # Find next zigzag MIN
        future_mins = tk_zz_min[tk_zz_min["timestamp"] >= et]
        if len(future_mins) == 0:
            continue
        nxt_min = future_mins.iloc[0]

        # Find next zigzag MAX after that MIN
        future_maxs = tk_zz_max[tk_zz_max["timestamp"] > nxt_min["timestamp"]]
        if len(future_maxs) == 0:
            continue
        nxt_max = future_maxs.iloc[0]

        risk = ((ep - nxt_min["price"]) / ep) * 100
        pnl = ((nxt_max["price"] - ep) / ep) * 100
        days_min = (nxt_min["timestamp"] - et).days
        days_max = (nxt_max["timestamp"] - et).days

        # Maturity: drop from last zigzag MAX
        past_maxs = tk_zz_max[tk_zz_max["timestamp"] < et]
        if len(past_maxs) > 0:
            last_max = past_maxs.iloc[-1]
            drop = ((last_max["price"] - ep) / last_max["price"]) * 100
            days_since_max = (et - last_max["timestamp"]).days
        else:
            drop = None
            days_since_max = None

        results.append({
            "ticker": ticker,
            "timestamp": et,
            "entry_price": ep,
            "rc_state": bar["rc_state"],
            "maturity": classify_maturity(drop) if drop is not None else None,
            "drop_pct": drop,
            "vwap_tension": bar["vwap_tension"],
            "accel_zone": bar["accel_zone"],
            "sigma_current": bar["sigma_current"],
            "vwap_sigma_wave": bar.get("vwap_sigma_wave"),
            "rsi_value": bar.get("rsi_value"),
            "risk": risk,
            "pnl": pnl,
            "win": pnl > 0,
            "days_to_floor": days_min,
            "days_to_ceiling": days_max,
            "days_since_max": days_since_max,
        })

    results_df = pd.DataFrame(results) if results else pd.DataFrame()

    # ── Detection rates at zigzag inflection points ──
    detections = []
    for tp_type, zz_pts in [("MIN", tk_zz_min), ("MAX", tk_zz_max)]:
        for _, zz in zz_pts.iterrows():
            # Find snapshot closest to this zigzag point (within 2 days)
            diffs = abs(tk_snap["timestamp"] - zz["timestamp"])
            idx = diffs.idxmin()
            if diffs[idx] > pd.Timedelta(days=2):
                continue
            snap = tk_snap.loc[idx]
            detections.append({
                "ticker": ticker,
                "tp_type": tp_type,
                "zz_timestamp": zz["timestamp"],
                "rc_state": snap["rc_state"],
                "sigma_current": snap["sigma_current"],
                "vwap_tension": snap["vwap_tension"],
                "accel_zone": snap["accel_zone"],
                "in_value_zone": snap["sigma_current"] <= SIGMA_ENTRY_THRESHOLD,
                "in_overbought": snap["sigma_current"] >= SIGMA_EXIT_THRESHOLD,
            })

    detections_df = pd.DataFrame(detections) if detections else pd.DataFrame()

    return results_df, detections_df


# ═══════════════════════════════════════════════════════════════
# CELL STATISTICS
# ═══════════════════════════════════════════════════════════════

def compute_cell_stats(df: pd.DataFrame, label: str, min_n: int,
                       total_years: float, n_tickers: int):
    """Compute statistics grouped by (rc_state, maturity)."""
    cells = []
    dm = df.dropna(subset=["maturity"])

    for state in sorted(dm["rc_state"].unique()):
        for _, (mlo, mhi, mlabel) in enumerate(MATURITY_BINS):
            sub = dm[(dm["rc_state"] == state) &
                     (dm["drop_pct"] >= mlo) & (dm["drop_pct"] < mhi)]
            if len(sub) < 5:
                continue

            risk_med = sub["risk"].median()
            pnl_med = sub["pnl"].median()
            ratio = pnl_med / risk_med if risk_med > 0.1 else 99.0
            wr = sub["win"].mean()
            per_yr = len(sub) / total_years if total_years > 0 else 0
            per_tk_yr = per_yr / n_tickers if n_tickers > 0 else 0
            interval = int(252 / per_tk_yr) if per_tk_yr > 0.01 else 9999

            cells.append({
                "label": label,
                "rc_state": state,
                "state_name": STATE_LABELS.get(state, state),
                "maturity": mlabel,
                "n": len(sub),
                "risk_median": round(risk_med, 2),
                "risk_p75": round(sub["risk"].quantile(0.75), 2),
                "pnl_median": round(pnl_med, 2),
                "pnl_p25": round(sub["pnl"].quantile(0.25), 2),
                "ratio": round(ratio, 1),
                "win_rate": round(wr, 3),
                "days_floor_median": int(sub["days_to_floor"].median()),
                "days_floor_p25": int(sub["days_to_floor"].quantile(0.25)),
                "days_floor_p75": int(sub["days_to_floor"].quantile(0.75)),
                "signals_per_year": round(per_yr, 1),
                "per_ticker_year": round(per_tk_yr, 2),
                "interval_days": interval,
                "grade": grade_cell(ratio, wr, len(sub), min_n),
            })

    return pd.DataFrame(cells)


# ═══════════════════════════════════════════════════════════════
# DETECTION RATE ANALYSIS
# ═══════════════════════════════════════════════════════════════

def compute_detection_rates(detections_df: pd.DataFrame, entries_df: pd.DataFrame):
    """Compute detection rates at zigzag inflection points."""
    if len(detections_df) == 0:
        return pd.DataFrame()

    results = []
    for tp_type in ["MIN", "MAX"]:
        tp_det = detections_df[detections_df["tp_type"] == tp_type]
        total_points = len(tp_det)

        for state in sorted(tp_det["rc_state"].unique()):
            state_at_turn = tp_det[tp_det["rc_state"] == state]
            n_detected = len(state_at_turn)

            # For MIN: also check if σ was in value zone
            if tp_type == "MIN":
                in_zone = state_at_turn["in_value_zone"].sum()
            else:
                in_zone = state_at_turn["in_overbought"].sum()

            # Total signals of this state (for false positive calc)
            total_signals = len(entries_df[entries_df["rc_state"] == state]) if len(entries_df) > 0 else 0

            results.append({
                "direction": "ZIG (piso)" if tp_type == "MIN" else "ZAG (techo)",
                "rc_state": state,
                "state_name": STATE_LABELS.get(state, state),
                "total_inflections": total_points,
                "state_present": n_detected,
                "detection_rate": round(n_detected / total_points, 3) if total_points > 0 else 0,
                "in_sigma_zone": int(in_zone),
                "sigma_zone_rate": round(in_zone / total_points, 3) if total_points > 0 else 0,
            })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    snapshots, zigzag = load_data()

    all_tickers = sorted(snapshots["ticker"].unique())
    total_years = (snapshots["timestamp"].max() - snapshots["timestamp"].min()).days / 365.25
    n_tickers = len(all_tickers)

    print(f"\nProcessing {n_tickers} tickers over {total_years:.1f} years...")
    print("=" * 100)

    # ── Process each ticker ──
    all_entries = []
    all_detections = []

    for ticker in all_tickers:
        entries_df, detections_df = process_ticker(ticker, snapshots, zigzag)
        if entries_df is not None and len(entries_df) > 0:
            all_entries.append(entries_df)
        if detections_df is not None and len(detections_df) > 0:
            all_detections.append(detections_df)

        n_entries = len(entries_df) if entries_df is not None else 0
        n_det = len(detections_df) if detections_df is not None else 0
        print(f"  {ticker:<6s}: {n_entries:>4d} entries, {n_det:>4d} zigzag detections")

    full_entries = pd.concat(all_entries, ignore_index=True)
    full_detections = pd.concat(all_detections, ignore_index=True)

    print(f"\nTotal entries (deduplicado): {len(full_entries):,}")
    print(f"Total zigzag detections:     {len(full_detections):,}")

    # ══════════════════════════════════════════════════════════
    # SPLIT: TRAIN (2006-2020) / TEST (2020-2026)
    # ══════════════════════════════════════════════════════════
    train = full_entries[full_entries["timestamp"] < TRAIN_CUTOFF]
    test = full_entries[full_entries["timestamp"] >= TRAIN_CUTOFF + pd.Timedelta(days=EMBARGO_BARS)]
    train_years = (TRAIN_CUTOFF - train["timestamp"].min()).days / 365.25 if len(train) > 0 else 1
    test_years = (test["timestamp"].max() - TRAIN_CUTOFF).days / 365.25 if len(test) > 0 else 1

    print(f"\n{'='*100}")
    print(f"  TRAIN: {len(train):,} entries ({train_years:.1f} years)")
    print(f"  TEST:  {len(test):,} entries ({test_years:.1f} years)  [embargo={EMBARGO_BARS} bars]")
    print(f"{'='*100}")

    # ══════════════════════════════════════════════════════════
    # PER-TICKER TABLES
    # ══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("  PER-TICKER STATISTICS (TRAIN period)")
    print(f"{'='*100}")

    for ticker in all_tickers:
        tk_train = train[train["ticker"] == ticker]
        if len(tk_train) < 20:
            continue

        tk_years = train_years
        print(f"\n  ── {ticker} ({len(tk_train)} entries) ──")
        print(f"  {'State':<8s} {'Maturity':<10s} {'N':>4s} {'Risk':>7s} {'P&L':>7s} {'Ratio':>6s} {'Win%':>5s} {'→piso':>6s} {'Grade':<10s}")

        cells = compute_cell_stats(tk_train, ticker, MIN_SAMPLES_TICKER, tk_years, 1)
        for _, c in cells.iterrows():
            icon = "🟢" if c["grade"] == "PREMIUM" else "✅" if c["grade"] == "BUENA" else "⚠️" if c["grade"] == "MODERADA" else "❌"
            print(f"  {icon} {c['rc_state']:<5s} {c['maturity']:<10s} {c['n']:>4d} {c['risk_median']:>+6.2f}% {c['pnl_median']:>+6.2f}% {c['ratio']:>5.1f}x {c['win_rate']:>4.0%} {c['days_floor_median']:>5d}d {c['grade']:<10s}")

    # ══════════════════════════════════════════════════════════
    # GLOBAL TABLE (TRAIN)
    # ══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("  GLOBAL TABLE (TRAIN 2006-2020)")
    print(f"{'='*100}")
    print(f"\n  {'State':<28s} {'Mat':<8s} {'N':>5s} {'Risk':>7s} {'P&L':>8s} {'Ratio':>6s} {'Win%':>5s} {'→piso':>6s} {'Freq':>8s} {'Grade':<10s}")
    print(f"  {'─'*26:<28s} {'─'*6:<8s} {'─'*3:>5s} {'─'*5:>7s} {'─'*6:>8s} {'─'*4:>6s} {'─'*3:>5s} {'─'*4:>6s} {'─'*6:>8s}")

    global_cells_train = compute_cell_stats(train, "GLOBAL_TRAIN", MIN_SAMPLES_GLOBAL, train_years, n_tickers)
    for _, c in global_cells_train.iterrows():
        icon = "🟢" if c["grade"] == "PREMIUM" else "✅" if c["grade"] == "BUENA" else "⚠️" if c["grade"] == "MODERADA" else "❌"
        state_full = f"{c['rc_state']}: {c['state_name']}"
        print(f"  {icon} {state_full:<25s} {c['maturity']:<8s} {c['n']:>5d} {c['risk_median']:>+6.2f}% {c['pnl_median']:>+7.2f}% {c['ratio']:>5.1f}x {c['win_rate']:>4.0%} {c['days_floor_median']:>5d}d {c['per_ticker_year']:>7.2f}/y {c['grade']:<10s}")

    # ══════════════════════════════════════════════════════════
    # GLOBAL TABLE (TEST — OUT OF SAMPLE)
    # ══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("  GLOBAL TABLE (TEST 2020-2026 — OUT OF SAMPLE)")
    print(f"{'='*100}")
    print(f"\n  {'State':<28s} {'Mat':<8s} {'N':>5s} {'Risk':>7s} {'P&L':>8s} {'Ratio':>6s} {'Win%':>5s} {'→piso':>6s} {'Grade':<10s}")
    print(f"  {'─'*26:<28s} {'─'*6:<8s} {'─'*3:>5s} {'─'*5:>7s} {'─'*6:>8s} {'─'*4:>6s} {'─'*3:>5s} {'─'*4:>6s}")

    global_cells_test = compute_cell_stats(test, "GLOBAL_TEST", 10, test_years, n_tickers)
    for _, c in global_cells_test.iterrows():
        icon = "🟢" if c["grade"] == "PREMIUM" else "✅" if c["grade"] == "BUENA" else "⚠️" if c["grade"] == "MODERADA" else "❌"
        state_full = f"{c['rc_state']}: {c['state_name']}"
        print(f"  {icon} {state_full:<25s} {c['maturity']:<8s} {c['n']:>5d} {c['risk_median']:>+6.2f}% {c['pnl_median']:>+7.2f}% {c['ratio']:>5.1f}x {c['win_rate']:>4.0%} {c['days_floor_median']:>5d}d {c['grade']:<10s}")

    # ══════════════════════════════════════════════════════════
    # TRAIN vs TEST COMPARISON
    # ══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("  TRAIN vs TEST — ¿Sobrevive el edge out-of-sample?")
    print(f"{'='*100}")
    print(f"\n  {'State':<28s} {'Mat':<8s} {'Train':>10s} {'Test':>10s} {'Train':>6s} {'Test':>6s} {'Δ Ratio':>8s} {'Verdict':<12s}")
    print(f"  {'':28s} {'':8s} {'Ratio':>10s} {'Ratio':>10s} {'Win%':>6s} {'Win%':>6s}")

    for _, tr in global_cells_train.iterrows():
        key = (tr["rc_state"], tr["maturity"])
        te_match = global_cells_test[
            (global_cells_test["rc_state"] == key[0]) &
            (global_cells_test["maturity"] == key[1])
        ]
        if len(te_match) == 0:
            continue
        te = te_match.iloc[0]

        ratio_delta = te["ratio"] - tr["ratio"]
        ratio_ratio = te["ratio"] / tr["ratio"] if tr["ratio"] > 0 else 0

        if ratio_ratio >= 0.7 and te["win_rate"] >= 0.70:
            verdict = "✅ SURVIVES"
        elif ratio_ratio >= 0.5:
            verdict = "⚠️ DEGRADES"
        else:
            verdict = "❌ FAILS"

        state_full = f"{tr['rc_state']}: {tr['state_name']}"
        print(f"  {state_full:<25s} {tr['maturity']:<8s} {tr['ratio']:>9.1f}x {te['ratio']:>9.1f}x {tr['win_rate']:>5.0%} {te['win_rate']:>5.0%} {ratio_delta:>+7.1f}x {verdict}")

    # ══════════════════════════════════════════════════════════
    # DETECTION RATES AT ZIGZAG INFLECTIONS
    # ══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("  DETECTION RATES: ¿Qué estado estaba en cada punto de inflexión del zigzag?")
    print(f"{'='*100}")

    det_rates = compute_detection_rates(full_detections, full_entries)
    if len(det_rates) > 0:
        for direction in ["ZIG (piso)", "ZAG (techo)"]:
            dr = det_rates[det_rates["direction"] == direction]
            print(f"\n  ── {direction} ──")
            print(f"  {'State':<28s} {'Present':>8s} {'/ Total':>8s} {'Rate':>7s} {'In σ zone':>10s} {'σ Rate':>7s}")
            for _, r in dr.iterrows():
                state_full = f"{r['rc_state']}: {r['state_name']}"
                print(f"  {state_full:<28s} {r['state_present']:>8d} {r['total_inflections']:>8d} {r['detection_rate']:>6.1%} {r['in_sigma_zone']:>10d} {r['sigma_zone_rate']:>6.1%}")

    # ══════════════════════════════════════════════════════════
    # STATE FREQUENCY (market-wide)
    # ══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("  STATE FREQUENCY — ¿Qué % del tiempo está el mercado en cada estado?")
    print(f"{'='*100}")

    for state in ["A", "B", "C", "D", "E", "F", "G"]:
        # Count from raw snapshots (all bars, not just entries)
        # We need to reclassify the full snapshot set
        pass  # This was already computed in the ad-hoc queries — 
              # the frequencies are baked into the plan constants

    print(f"\n  (Frequencies from full dataset: {len(snapshots):,} bars)")
    snapshots_classified = snapshots.copy()
    snapshots_classified["rc_state"] = snapshots_classified.apply(classify_rc_state, axis=1)
    total_bars = len(snapshots_classified)
    
    print(f"  {'State':<28s} {'Bars':>8s} {'%':>7s}  Visual")
    for state in ["A", "B", "C", "D", "E", "F", "G"]:
        n = len(snapshots_classified[snapshots_classified["rc_state"] == state])
        pct = n / total_bars * 100
        bar = "█" * int(pct / 2)
        desc = STATE_DESCRIPTIONS[state]
        print(f"  {state}: {STATE_LABELS[state]:<22s} {n:>8,d} {pct:>6.1f}%  {bar}  {desc}")

    print(f"\n{'='*100}")
    print("  TRAINING COMPLETE")
    print(f"{'='*100}")


if __name__ == "__main__":
    main()
