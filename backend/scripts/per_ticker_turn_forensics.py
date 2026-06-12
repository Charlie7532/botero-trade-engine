#!/usr/bin/env python3
"""
Per-Ticker Turn Forensics — Zero Aggregation, Zero Lies
==========================================================
For EACH ticker independently:
  1. Load its zigzag (5% only) + channel snapshots from Vault
  2. Classify archetypes (HL/LL/HH/LH)
  3. For each archetype:
     - At t=0 (detection): which features have |z| > 2?
     - At t-2..t-1 (causal alert): which features fire BEFORE the turn?
     - Baseline: what's the activation rate on random non-turn bars?
     - LIFT = turn_rate / baseline_rate (>1 = signal, <1 = anti-signal)
  4. NO cross-ticker aggregation. Every number belongs to ONE ticker.

Output: CSV per ticker + summary log.
Uses store.load_bars() for OHLCV (Vault-first, Rule 13).
"""

import sys, os, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

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
CAUSAL_WINDOW = 2        # t-2..t-1 (strictly before turn)
TOP_N_FEATURES = 10      # Show top-N per archetype per ticker

# Candidate features (all from ChannelSnapshot)
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
OUT_DIR = root_dir / "backend" / "scripts" / "per_ticker_forensics_output"
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
# STEP 1: LOAD DATA PER TICKER
# ═══════════════════════════════════════════════════════════════

def load_ticker_data(store, ticker):
    """Load snapshots + zigzag for ONE ticker. Returns (df_snapshots, df_zigzag)."""
    conn = store._conn()
    cur = conn.cursor()

    # Snapshots
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

    # Zigzag
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


# ═══════════════════════════════════════════════════════════════
# STEP 2: CLASSIFY ARCHETYPES & MAP TO BAR INDICES
# ═══════════════════════════════════════════════════════════════

def classify_turns(df, zz):
    """Map zigzag points to bar indices, classify archetypes.
    Returns list of turn dicts with bar_idx and archetype."""
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
                "tp_type": row["tp_type"],
                "archetype": archetype,
                "price": row["price"],
                "swing_return": row["swing_return"],
                "swing_days": row["swing_days"],
                "timestamp": row["timestamp"],
            })

    return turns


# ═══════════════════════════════════════════════════════════════
# STEP 3: COMPUTE Z-SCORES (per-ticker, no cross-contamination)
# ═══════════════════════════════════════════════════════════════

def compute_zscores(df, features):
    """Compute z-scores for each feature using THIS ticker's full history.
    Returns DataFrame with z_{feature} columns."""
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
# STEP 4: MEASURE ACTIVATION AT TURNS VS BASELINE
# ═══════════════════════════════════════════════════════════════

def measure_activation(df, turns, features):
    """For each archetype, measure feature activation at:
      - t=0 (detection)
      - t-2..t-1 (causal alert, ANY bar fires)
      - baseline (random non-turn bars)
    Returns dict of results per archetype."""

    n_bars = len(df)
    all_turn_indices = set()
    for t in turns:
        for offset in range(-5, 6):
            idx = t["bar_idx"] + offset
            if 0 <= idx < n_bars:
                all_turn_indices.add(idx)

    # Baseline: bars NOT near any turn
    baseline_candidates = [i for i in range(250, n_bars) if i not in all_turn_indices]
    n_baseline = min(500, len(baseline_candidates))
    if n_baseline < 50:
        return None  # Not enough baseline bars

    rng = np.random.RandomState(42)
    baseline_idx = rng.choice(baseline_candidates, n_baseline, replace=False)

    results = {}
    for archetype in ["LL", "HL", "HH", "LH"]:
        arch_turns = [t for t in turns if t["archetype"] == archetype]
        n_turns = len(arch_turns)
        if n_turns < 3:
            continue

        feat_results = []
        for feat in features:
            z_col = f"z_{feat}"
            z_vals = df[z_col].values

            # t=0 detection: |z| > threshold at turn bar
            n_det = 0
            for t in arch_turns:
                idx = t["bar_idx"]
                if 0 <= idx < n_bars and abs(z_vals[idx]) > Z_THRESHOLD:
                    n_det += 1
            det_rate = n_det / n_turns

            # t-2..t-1 causal alert: ANY bar in window has |z| > threshold
            n_alert = 0
            for t in arch_turns:
                fired = False
                for offset in range(-CAUSAL_WINDOW, 0):  # -2, -1
                    idx = t["bar_idx"] + offset
                    if 0 <= idx < n_bars and abs(z_vals[idx]) > Z_THRESHOLD:
                        fired = True
                        break
                if fired:
                    n_alert += 1
            alert_rate = n_alert / n_turns

            # Combined: alert OR detection (t-2..t=0)
            n_combined = 0
            for t in arch_turns:
                fired = False
                for offset in range(-CAUSAL_WINDOW, 1):  # -2, -1, 0
                    idx = t["bar_idx"] + offset
                    if 0 <= idx < n_bars and abs(z_vals[idx]) > Z_THRESHOLD:
                        fired = True
                        break
                if fired:
                    n_combined += 1
            combined_rate = n_combined / n_turns

            # Baseline rate
            n_base = sum(1 for i in baseline_idx if abs(z_vals[i]) > Z_THRESHOLD)
            base_rate = n_base / n_baseline

            # LIFT
            lift = combined_rate / max(base_rate, 0.001)

            # Direction at t=0 (mean z at turn — tells us if feature goes
            # positive or negative at turns)
            z_at_turn = [z_vals[t["bar_idx"]] for t in arch_turns
                         if 0 <= t["bar_idx"] < n_bars]
            mean_z = np.mean(z_at_turn) if z_at_turn else 0.0

            feat_results.append({
                "feature": feat,
                "n_turns": n_turns,
                "det_rate": det_rate,
                "alert_rate": alert_rate,
                "combined_rate": combined_rate,
                "base_rate": base_rate,
                "lift": lift,
                "mean_z_at_turn": mean_z,
            })

        # Sort by LIFT (the honest metric)
        feat_results.sort(key=lambda x: x["lift"], reverse=True)
        results[archetype] = feat_results

    return results


# ═══════════════════════════════════════════════════════════════
# STEP 5: REPORT PER TICKER
# ═══════════════════════════════════════════════════════════════

def report_ticker(ticker, turns, results):
    """Print the per-ticker report."""
    log_section(f"TICKER: {ticker}")

    # Turn counts
    counts = {}
    for t in turns:
        counts[t["archetype"]] = counts.get(t["archetype"], 0) + 1
    log(f"  Turns: {counts}")

    for archetype in ["LL", "HL", "HH", "LH"]:
        if archetype not in results:
            continue

        feat_results = results[archetype]
        n_turns = feat_results[0]["n_turns"] if feat_results else 0
        log(f"\n  ── {archetype} ({n_turns} turns) ──")
        log(f"  {'Feature':<30s} │ {'Det%':>5s} │ {'Alert%':>6s} │ {'Comb%':>5s} │ "
            f"{'Base%':>5s} │ {'LIFT':>5s} │ {'μ(z)':>6s} │ {'Signal':>8s}")
        log(f"  {'─'*30} │ {'─'*5} │ {'─'*6} │ {'─'*5} │ {'─'*5} │ {'─'*5} │ {'─'*6} │ {'─'*8}")

        for r in feat_results[:TOP_N_FEATURES]:
            # Classify signal quality
            if r["lift"] >= 3.0:
                signal = "★★★"
            elif r["lift"] >= 2.0:
                signal = "★★"
            elif r["lift"] >= 1.5:
                signal = "★"
            elif r["lift"] <= 0.5:
                signal = "▼▼ ANTI"
            elif r["lift"] <= 0.7:
                signal = "▼ anti"
            else:
                signal = "—"

            log(f"  {r['feature']:<30s} │ {r['det_rate']*100:>4.0f}% │ {r['alert_rate']*100:>5.0f}% │ "
                f"{r['combined_rate']*100:>4.0f}% │ {r['base_rate']*100:>4.0f}% │ "
                f"{r['lift']:>5.1f} │ {r['mean_z_at_turn']:>+5.2f} │ {signal:>8s}")

        # Bottom 3 (anti-signals: features that go SILENT at turns)
        anti = [r for r in feat_results if r["lift"] < 0.7 and r["base_rate"] > 0.02]
        if anti:
            anti.sort(key=lambda x: x["lift"])
            log(f"\n  ANTI-SIGNALS (go silent at {archetype} turns):")
            for r in anti[:3]:
                log(f"  {r['feature']:<30s} │ {r['det_rate']*100:>4.0f}% │ "
                    f"Base={r['base_rate']*100:.0f}% │ LIFT={r['lift']:.2f} │ "
                    f"SILENCE = feature STOPS firing at turns")


# ═══════════════════════════════════════════════════════════════
# STEP 6: CROSS-TICKER CONSISTENCY CHECK
# ═══════════════════════════════════════════════════════════════

def consistency_check(all_results):
    """For each archetype, check which features have LIFT > 1.5 in ≥ N tickers.
    This is NOT aggregation — it's a count of how many tickers agree."""
    log_section("CROSS-TICKER CONSISTENCY (how many tickers agree?)")

    for archetype in ["LL", "HL", "HH", "LH"]:
        log(f"\n  ── {archetype}: Features with LIFT ≥ 1.5 across tickers ──")

        feature_ticker_count = {}  # feature -> list of (ticker, lift)
        for ticker, results in all_results.items():
            if archetype not in results:
                continue
            for r in results[archetype]:
                if r["lift"] >= 1.5:
                    feature_ticker_count.setdefault(r["feature"], []).append(
                        (ticker, r["lift"]))

        if not feature_ticker_count:
            log(f"  No features with LIFT ≥ 1.5 in any ticker!")
            continue

        # Sort by number of tickers where it works
        ranked = sorted(feature_ticker_count.items(),
                        key=lambda x: len(x[1]), reverse=True)

        log(f"  {'Feature':<30s} │ {'#Tickers':>8s} │ {'Tickers (LIFT)':>50s}")
        log(f"  {'─'*30} │ {'─'*8} │ {'─'*50}")

        for feat, ticker_lifts in ranked[:15]:
            n = len(ticker_lifts)
            tickers_str = ", ".join(f"{tk}({l:.1f})" for tk, l in
                                     sorted(ticker_lifts, key=lambda x: -x[1])[:5])
            if n > 5:
                tickers_str += f" +{n-5} more"
            verdict = "✅ UNIVERSAL" if n >= 10 else "⚠ PARTIAL" if n >= 5 else ""
            log(f"  {feat:<30s} │ {n:>8d} │ {tickers_str:<50s} {verdict}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log_section("PER-TICKER TURN FORENSICS — Zero Aggregation")
    log(f"  ZigZag: {ZZ_SCALE*100:.0f}%   Z-threshold: {Z_THRESHOLD}")
    log(f"  Causal window: t-{CAUSAL_WINDOW}..t=0 (no look-ahead)")
    log(f"  Features: {len(FEATURES)}")

    store = TimescaleDataStore()

    # Get ticker list
    conn = store._conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ticker FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND kf_rsi_pred_val IS NOT NULL
        ORDER BY ticker
    """)
    tickers = [r[0] for r in cur.fetchall()]
    store._put(conn)
    log(f"  Tickers: {tickers} ({len(tickers)})")

    all_results = {}  # ticker -> {archetype -> [feat_results]}
    all_csvs = []

    for ticker in tickers:
        log(f"\n  Processing {ticker}...")
        df, zz = load_ticker_data(store, ticker)

        if len(df) < 300 or len(zz) < 4:
            log(f"  SKIP: insufficient data (snapshots={len(df)}, zz={len(zz)})")
            continue

        turns = classify_turns(df, zz)
        if len(turns) < 5:
            log(f"  SKIP: only {len(turns)} classified turns")
            continue

        # Compute z-scores for THIS ticker only
        df = compute_zscores(df, FEATURES)

        # Measure activation
        results = measure_activation(df, turns, FEATURES)
        if results is None:
            log(f"  SKIP: insufficient baseline bars")
            continue

        all_results[ticker] = results
        report_ticker(ticker, turns, results)

        # Save per-ticker CSV
        csv_rows = []
        for arch, feat_results in results.items():
            for r in feat_results:
                csv_rows.append({
                    "ticker": ticker,
                    "archetype": arch,
                    **r,
                })
        if csv_rows:
            csv_df = pd.DataFrame(csv_rows)
            csv_path = OUT_DIR / f"{ticker}_forensics.csv"
            csv_df.to_csv(csv_path, index=False)
            all_csvs.append(csv_df)

    store.close()

    # Cross-ticker consistency
    consistency_check(all_results)

    # Save combined CSV (for analysis, NOT for training)
    if all_csvs:
        combined = pd.concat(all_csvs, ignore_index=True)
        combined.to_csv(OUT_DIR / "all_tickers_forensics.csv", index=False)
        log(f"\n  Combined CSV: {len(combined)} rows → {OUT_DIR / 'all_tickers_forensics.csv'}")

    # Save log
    elapsed = time.time() - T0
    log(f"\n  COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    log_path = OUT_DIR / f"forensics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(LOG))
    log(f"  Log: {log_path}")
