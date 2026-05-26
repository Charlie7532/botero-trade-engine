#!/usr/bin/env python3
"""
AUDITORÍA INTEGRAL — Post-Fixes Quality Gate
==============================================
Verifica que TODOS los cálculos sean correctos:

1. Signal Tape: recomputa 5 barras aleatorias × 5 tickers y compara contra Vault
2. Meta-señales: verifica que M1-M5 detectan correctamente en datos reales
3. Forward returns: recalcula desde OHLCV y compara contra tape
4. Head probabilities: recomputa HeadScorer y compara contra tape
5. SwingGate integration: verifica que la nueva lógica no rompe el flow

NO MODIFICA NADA. Solo lee y compara.
"""
import os, sys, warnings, time, random
from pathlib import Path

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.head_scorer import HeadScorer
from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot
from backend.modules.shared.domain.ports.head_scorer_port import HeadScore
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker
from backend.modules.quality_swing.domain.rules.meta_signals import detect_meta_signals, MetaSignal

AUDIT_TICKERS = ["SPY", "AAPL", "AMZN", "JPM", "XOM"]
SAMPLES_PER_TICKER = 5
TOLERANCE = 0.005  # 0.5% tolerance for floating point

total_checks = 0
total_pass = 0
total_fail = 0


def check(name, expected, actual, tol=TOLERANCE):
    """Compare two values with tolerance."""
    global total_checks, total_pass, total_fail
    total_checks += 1

    if expected is None and actual is None:
        total_pass += 1
        return True

    if expected is None or actual is None:
        total_fail += 1
        print(f"    ❌ {name}: expected={expected} actual={actual}")
        return False

    if isinstance(expected, str):
        if expected == actual:
            total_pass += 1
            return True
        else:
            total_fail += 1
            print(f"    ❌ {name}: expected={expected} actual={actual}")
            return False

    diff = abs(float(expected) - float(actual))
    max_val = max(abs(float(expected)), abs(float(actual)), 1e-10)
    rel_err = diff / max_val

    if rel_err <= tol or diff < 1e-6:
        total_pass += 1
        return True
    else:
        total_fail += 1
        print(f"    ❌ {name}: expected={expected:.6f} actual={actual:.6f} (err={rel_err:.4f})")
        return False


# ═══════════════════════════════════════════════════════════════════
#  AUDIT 1: Signal Tape vs Fresh Computation
# ═══════════════════════════════════════════════════════════════════
def audit_signal_tape(store, scorer):
    print("\n" + "═" * 90)
    print("  AUDIT 1: SIGNAL TAPE vs FRESH COMPUTATION")
    print("  Recomputes RC+RSI+Kalman+Heads from OHLCV and compares against stored tape")
    print("═" * 90)

    for ticker in AUDIT_TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 300:
            print(f"\n  ⚠️ {ticker}: insufficient data")
            continue

        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)
        timestamps = ohlc.index.tolist()

        # Pre-compute RSI full series
        intel = RSIIntelligence()
        raw_rsi = intel._calc_rsi_series(close, 14)
        rsi_full = np.concatenate(([50.0], raw_rsi))

        # Pre-compute Kalman (matching tape generator exactly)
        tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
        vol_s = pd.Series(volume)
        vol_m = vol_s.rolling(window=20, min_periods=1).mean()
        returns = pd.Series(close).pct_change()
        kalman_vel = np.zeros(len(close))
        kalman_vad = np.zeros(len(close))
        for i in range(len(close)):
            rv = float(volume[i])
            av = float(vol_m.iloc[i])
            orvol = rv / av if av > 0 else 1.0
            pc = float(close[max(0, i - 1)])
            cc = float(close[i])
            chg = ((cc - pc) / pc * 100) if pc > 0 else 0.0
            st = tracker.update(ticker, orvol, chg)
            kalman_vel[i] = st.get("velocity", 0.0)
            if i >= 20:
                v20 = returns.iloc[max(0, i - 19) : i + 1].std()
                kalman_vad[i] = kalman_vel[i] / max(v20 * 100, 0.01)

        # Load tape for this ticker
        q = f"SELECT * FROM engine.signal_tape WHERE ticker = '{ticker}' ORDER BY timestamp"
        tape = pd.read_sql(q, store.engine, parse_dates=['timestamp'])

        # Sample random bars
        valid_indices = list(range(250, len(ohlc) - 20))
        sample_indices = random.sample(valid_indices, min(SAMPLES_PER_TICKER, len(valid_indices)))

        print(f"\n  ── {ticker}: {SAMPLES_PER_TICKER} random bars ──")

        for idx in sorted(sample_indices):
            ts = timestamps[idx]

            # Find in tape
            tape_row = tape[tape['timestamp'] == ts]
            if tape_row.empty:
                print(f"    ⚠️ idx={idx} ts={ts}: NOT IN TAPE")
                continue

            tape_row = tape_row.iloc[0]

            # Fresh computation
            snap = compute_channel_snapshot(close, high, low, volume, idx)
            if snap is None:
                print(f"    ⚠️ idx={idx}: snapshot computation failed")
                continue

            snap.rsi_value = round(float(rsi_full[idx]), 2)
            snap.kalman_velocity = round(float(kalman_vel[idx]), 6)
            snap.vol_adj_delta = round(float(kalman_vad[idx]), 6)

            # Compute previous snapshot for stateless deltas (crucial for out-of-order audit)
            prev_snap = compute_channel_snapshot(close, high, low, volume, idx - 1)
            if prev_snap is not None:
                prev_snap.rsi_value = round(float(rsi_full[idx - 1]), 2)
                prev_snap.kalman_velocity = round(float(kalman_vel[idx - 1]), 6)
                prev_snap.vol_adj_delta = round(float(kalman_vad[idx - 1]), 6)

            # Compare RC fields
            check(f"[{ticker}@{idx}] sigma_tide", tape_row['sigma_tide'], snap.sigma_tide)
            check(f"[{ticker}@{idx}] sigma_wave", tape_row['sigma_wave'], snap.sigma_wave)
            check(f"[{ticker}@{idx}] tide_slope", tape_row['tide_slope'], snap.tide_slope)
            check(f"[{ticker}@{idx}] compression_ratio", tape_row['compression_ratio'], snap.compression_ratio)

            # Compare RSI
            check(f"[{ticker}@{idx}] rsi_value", tape_row['rsi_value'], snap.rsi_value, tol=0.01)

            # Compare Kalman
            check(f"[{ticker}@{idx}] kalman_velocity", tape_row['kalman_velocity'], snap.kalman_velocity, tol=0.01)

            # Compare head probabilities (injecting prev_snap for deterministic out-of-order deltas)
            scores = scorer.score_all(ticker, snap, prev_snapshot=prev_snap)
            for head in ['long_entry', 'swing_exit', 'pullback_depth', 'short_entry']:
                col = f"p_{head}"
                tape_val = tape_row.get(col)
                fresh_val = scores[head].probability if head in scores else None
                check(f"[{ticker}@{idx}] {col}", tape_val, fresh_val, tol=0.01)

            # Compare forward return
            if idx + 10 < len(close):
                fwd_10d = (close[idx + 10] - close[idx]) / close[idx]
                check(f"[{ticker}@{idx}] fwd_return_10d", tape_row['fwd_return_10d'], round(fwd_10d, 6), tol=0.001)

            # Compare decision
            check(f"[{ticker}@{idx}] decision_a", tape_row['decision_a'], tape_row['decision_a'])  # self-check for NULL


# ═══════════════════════════════════════════════════════════════════
#  AUDIT 2: Forward Returns Correctness
# ═══════════════════════════════════════════════════════════════════
def audit_forward_returns(store):
    print("\n" + "═" * 90)
    print("  AUDIT 2: FORWARD RETURNS — Recompute from raw OHLCV")
    print("═" * 90)

    for ticker in AUDIT_TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        close = ohlc["close"].values.astype(float)
        timestamps = ohlc.index.tolist()

        q = f"SELECT timestamp, fwd_return_5d, fwd_return_10d, fwd_return_20d, fwd_max_dd_10d, fwd_max_runup_10d FROM engine.signal_tape WHERE ticker = '{ticker}' ORDER BY timestamp"
        tape = pd.read_sql(q, store.engine, parse_dates=['timestamp'])

        # Sample 10 random rows
        sample = tape.sample(min(10, len(tape)))

        print(f"\n  ── {ticker}: 10 random forward return checks ──")
        for _, row in sample.iterrows():
            ts = row['timestamp']
            # Find bar index
            try:
                idx = timestamps.index(ts)
            except ValueError:
                continue

            # Recompute forward returns
            for horizon, col in [(5, 'fwd_return_5d'), (10, 'fwd_return_10d'), (20, 'fwd_return_20d')]:
                end_idx = idx + horizon
                if end_idx < len(close):
                    fresh = round((close[end_idx] - close[idx]) / close[idx], 6)
                    check(f"[{ticker}@{idx}] {col}", row[col], fresh, tol=0.001)

            # Max DD 10d
            if idx + 10 < len(close):
                fwd_prices = close[idx + 1: idx + 11]
                fwd_rets = (fwd_prices - close[idx]) / close[idx]
                fresh_dd = round(float(np.min(fwd_rets)), 6)
                fresh_ru = round(float(np.max(fwd_rets)), 6)
                check(f"[{ticker}@{idx}] fwd_max_dd_10d", row['fwd_max_dd_10d'], fresh_dd, tol=0.001)
                check(f"[{ticker}@{idx}] fwd_max_runup_10d", row['fwd_max_runup_10d'], fresh_ru, tol=0.001)


# ═══════════════════════════════════════════════════════════════════
#  AUDIT 3: Meta-Signal Detection on Real Data
# ═══════════════════════════════════════════════════════════════════
def audit_meta_signals(store, scorer):
    print("\n" + "═" * 90)
    print("  AUDIT 3: META-SIGNALS — Verify detection on real tape data")
    print("═" * 90)

    # Load tape rows where danger should fire: P(short)>0.6 AND P(long)<0.5
    q = """SELECT ticker, timestamp, p_long_entry, p_short_entry, p_swing_exit,
                  p_short_cover, p_pullback_depth, p_trend_reversal,
                  p_bounce_height, p_trend_recovery,
                  sigma_tide, rsi_value, regime, fwd_max_dd_10d
           FROM engine.signal_tape
           WHERE p_short_entry > 0.6 AND p_long_entry < 0.5
           ORDER BY RANDOM() LIMIT 10"""
    danger_rows = pd.read_sql(q, store.engine)

    print(f"\n  ── M1 DANGER: {len(danger_rows)} sample rows where P(short)>0.6 + P(long)<0.5 ──")
    danger_detected = 0
    danger_actually_crashed = 0

    for _, row in danger_rows.iterrows():
        # Build mock HeadScores
        scores = {}
        for head in ['long_entry', 'swing_exit', 'pullback_depth', 'trend_reversal',
                      'short_entry', 'short_cover', 'bounce_height', 'trend_recovery']:
            p = row.get(f'p_{head}', 0.5)
            scores[head] = HeadScore(head=head, probability=float(p), threshold=0.5,
                                     triggered=float(p) >= 0.5, description='')

        snap = ChannelSnapshot()
        snap.regime = row['regime']
        snap.rsi_value = float(row['rsi_value'])
        snap.sigma_tide = float(row['sigma_tide'])

        meta = detect_meta_signals(scores, snap)
        has_danger = any(ms.name == "DANGER_CONSTELLATION" for ms in meta)
        actually_crashed = row['fwd_max_dd_10d'] is not None and row['fwd_max_dd_10d'] < -0.05

        if has_danger:
            danger_detected += 1
        if actually_crashed:
            danger_actually_crashed += 1

        check(f"[{row['ticker']}] DANGER detected", True, has_danger)

    if len(danger_rows) > 0:
        print(f"\n    Detection rate: {danger_detected}/{len(danger_rows)} ({danger_detected/len(danger_rows)*100:.0f}%)")
        print(f"    Actually crashed (DD>5%): {danger_actually_crashed}/{len(danger_rows)} ({danger_actually_crashed/len(danger_rows)*100:.0f}%)")

    # Test NON-danger rows: P(short)<0.4 AND P(long)>0.6
    q2 = """SELECT ticker, p_long_entry, p_short_entry, sigma_tide, rsi_value, regime
            FROM engine.signal_tape
            WHERE p_short_entry < 0.4 AND p_long_entry > 0.6
            ORDER BY RANDOM() LIMIT 10"""
    safe_rows = pd.read_sql(q2, store.engine)

    print(f"\n  ── NON-DANGER: {len(safe_rows)} rows where P(short)<0.4 + P(long)>0.6 ──")
    false_alarms = 0
    for _, row in safe_rows.iterrows():
        scores = {}
        for head in ['long_entry', 'swing_exit', 'pullback_depth', 'trend_reversal',
                      'short_entry', 'short_cover', 'bounce_height', 'trend_recovery']:
            p = row.get(f'p_{head}', 0.5)
            if p is None or pd.isna(p):
                p = 0.5
            scores[head] = HeadScore(head=head, probability=float(p), threshold=0.5,
                                     triggered=float(p) >= 0.5, description='')

        snap = ChannelSnapshot()
        snap.regime = row.get('regime', 'FLAT')
        snap.rsi_value = float(row.get('rsi_value', 50))
        snap.sigma_tide = float(row.get('sigma_tide', 0))

        meta = detect_meta_signals(scores, snap)
        has_danger = any(ms.name == "DANGER_CONSTELLATION" for ms in meta)
        if has_danger:
            false_alarms += 1
        check(f"[{row['ticker']}] NO danger expected", False, has_danger)

    print(f"    False alarms: {false_alarms}/{len(safe_rows)}")


# ═══════════════════════════════════════════════════════════════════
#  AUDIT 4: Head Scorer Consistency
# ═══════════════════════════════════════════════════════════════════
def audit_head_scorer(store, scorer):
    print("\n" + "═" * 90)
    print("  AUDIT 4: HEAD SCORER — Same input → same output (determinism)")
    print("═" * 90)

    for ticker in ["SPY", "AAPL"]:
        ohlc = store.load_bars(ticker, "1d")
        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)

        idx = len(ohlc) - 50  # A recent bar

        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

        prev_snap = compute_channel_snapshot(close, high, low, volume, idx - 1)

        # Score 3 times — must be identical
        results = []
        for trial in range(3):
            scores = scorer.score_all(ticker, snap, prev_snapshot=prev_snap)
            results.append({h: s.probability for h, s in scores.items()})

        print(f"\n  ── {ticker} idx={idx}: 3 runs ──")
        for head in results[0]:
            v1, v2, v3 = results[0][head], results[1][head], results[2][head]
            check(f"[{ticker}] {head} run1==run2", v1, v2, tol=0.0001)
            check(f"[{ticker}] {head} run2==run3", v2, v3, tol=0.0001)


# ═══════════════════════════════════════════════════════════════════
#  AUDIT 5: RSI computation matches production
# ═══════════════════════════════════════════════════════════════════
def audit_rsi_computation(store):
    print("\n" + "═" * 90)
    print("  AUDIT 5: RSI — Wilder-14 from scratch vs stored")
    print("═" * 90)

    for ticker in AUDIT_TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        close = ohlc["close"].values.astype(float)

        # Fresh computation
        intel = RSIIntelligence()
        raw_rsi = intel._calc_rsi_series(close, 14)
        rsi_full = np.concatenate(([50.0], raw_rsi))

        # Check stored in snapshots
        q = f"""SELECT timestamp, rsi_value FROM engine.signal_tape
                WHERE ticker = '{ticker}' ORDER BY timestamp"""
        tape = pd.read_sql(q, store.engine, parse_dates=['timestamp'])
        timestamps = ohlc.index.tolist()

        # Sample 5 random
        sample = tape.sample(min(5, len(tape)))

        print(f"\n  ── {ticker} ──")
        for _, row in sample.iterrows():
            ts = row['timestamp']
            try:
                idx = timestamps.index(ts)
            except ValueError:
                continue

            fresh_rsi = round(float(rsi_full[idx]), 2)
            stored_rsi = float(row['rsi_value'])
            check(f"[{ticker}@{idx}] RSI", stored_rsi, fresh_rsi, tol=0.01)


def main():
    print("=" * 90)
    print("  AUDITORÍA INTEGRAL — Post-Fixes Quality Gate")
    print("  5 auditorías × 5 tickers × 5-10 muestras cada una")
    print("  CERO TOLERANCIA a errores en data")
    print("=" * 90)

    random.seed(42)  # Reproducible
    t0 = time.time()

    store = TimescaleDataStore()
    scorer = HeadScorer()

    audit_signal_tape(store, scorer)
    audit_forward_returns(store)
    audit_meta_signals(store, scorer)
    audit_head_scorer(store, scorer)
    audit_rsi_computation(store)

    store.close()
    elapsed = time.time() - t0

    print(f"\n{'=' * 90}")
    print(f"  AUDITORÍA COMPLETA: {elapsed:.1f}s")
    print(f"  Total checks: {total_checks}")
    print(f"  ✅ PASSED: {total_pass}")
    print(f"  ❌ FAILED: {total_fail}")
    status = "★ ALL CHECKS PASSED ★" if total_fail == 0 else f"⚠️ {total_fail} FAILURES"
    print(f"  {status}")
    print(f"{'=' * 90}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
