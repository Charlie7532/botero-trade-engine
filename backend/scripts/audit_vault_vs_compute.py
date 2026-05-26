#!/usr/bin/env python3
"""
AUDITOR COMPLETO 17 TICKERS — Cómputo Fresco vs Vault
=========================================================
Verifica TODOS los tickers, 5 barras cada uno, 37 campos.
Optimizado: pre-computa RSI y Kalman full-series (no barra por barra).
"""
import os, sys, warnings, time, random
from pathlib import Path
warnings.filterwarnings('ignore')

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]
BARS_PER_TICKER = 5
RC_FIELDS = {
    'sigma_tide': 0.01, 'sigma_current': 0.01, 'sigma_wave': 0.01,
    'reg_value_tide': 0.05, 'reg_value_current': 0.05, 'reg_value_wave': 0.05,
    'residual_std_tide': 0.01, 'residual_std_current': 0.01, 'residual_std_wave': 0.01,
    'tide_slope': 0.0001, 'current_slope': 0.0001, 'wave_slope': 0.0001,
    'tide_accel': 0.0001, 'current_accel': 0.0001, 'wave_accel': 0.0001,
    'conj_wave_tide': 0.0001, 'conj_wave_current': 0.0001, 'conj_current_tide': 0.0001,
    'spread_tide_current': 0.01, 'spread_tide_wave': 0.01, 'spread_current_wave': 0.01,
    'vwap_sigma_tide': 0.01, 'vwap_sigma_current': 0.01, 'vwap_sigma_wave': 0.01,
    'fear_level': 0.5,
    'compression_ratio': 0.01,
    'tension_tide': 0.01, 'tension_current': 0.01, 'tension_wave': 0.01,
    'geo_state_norm': 0.01, 'geo_velocity_align': 0.01,
    'geo_exit_align': 0.01, 'geo_accel_align': 0.01, 'geo_phase_angle': 0.01,
}


def precompute_kalman_full(close, volume):
    """Full-series Kalman — fast."""
    tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
    vol_s = pd.Series(volume)
    vol_m = vol_s.rolling(window=20, min_periods=1).mean()
    returns = pd.Series(close).pct_change()
    results = []
    for i in range(len(close)):
        rv = float(volume[i]); av = float(vol_m.iloc[i])
        orvol = rv / av if av > 0 else 1.0
        pc = float(close[max(0, i-1)]); cc = float(close[i])
        chg = ((cc - pc) / pc * 100) if pc > 0 else 0.0
        st = tracker.update("a", orvol, chg)
        vel = st.get('velocity', 0.0)
        if i >= 20:
            v20 = returns.iloc[max(0, i-19):i+1].std()
            vad = vel / max(v20 * 100, 0.01)
        else:
            vad = 0.0
        results.append((round(float(vel), 6), round(float(vad), 6)))
    return results


def audit_ticker(store, ticker):
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < 300:
        return 0, 0, []
    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)
    timestamps = ohlc.index.tolist()

    stored = store.load_snapshots(ticker, "1d")
    if stored.empty:
        return 0, 0, []

    # Pre-compute RSI full series
    intel = RSIIntelligence()
    raw_rsi = intel._calc_rsi_series(close, 14)
    rsi_full = np.concatenate(([50.0], raw_rsi))

    # Pre-compute Kalman full series
    kalman_all = precompute_kalman_full(close, volume)

    # Pick deterministic random bars
    random.seed(17 + hash(ticker))
    valid = list(range(260, len(ohlc)))
    idxs = sorted(random.sample(valid, min(BARS_PER_TICKER, len(valid))))

    matches = 0
    mismatches = 0
    errors = []

    for idx in idxs:
        ts = timestamps[idx]
        if ts not in stored.index:
            continue
        sr = stored.loc[ts]
        if isinstance(sr, pd.DataFrame):
            sr = sr.iloc[0]

        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

        # RC fields
        for field, tol in RC_FIELDS.items():
            fresh = getattr(snap, field, None)
            sv = sr.get(field)
            if fresh is None or sv is None:
                continue
            diff = abs(float(fresh) - float(sv))
            if diff > tol:
                mismatches += 1
                errors.append(f"{field}: fresh={fresh} stored={sv} Δ={diff:.6f}")
            else:
                matches += 1

        # Regime string
        if str(snap.regime) == str(sr.get('regime', '')):
            matches += 1
        else:
            mismatches += 1
            errors.append(f"regime: fresh={snap.regime} stored={sr.get('regime')}")

        # RSI
        rsi_f = round(float(rsi_full[idx]), 1)
        rsi_s = sr.get('rsi_value')
        if rsi_s is not None:
            diff = abs(rsi_f - float(rsi_s))
            if diff > 0.2:
                mismatches += 1
                errors.append(f"rsi_value: fresh={rsi_f:.1f} stored={float(rsi_s):.1f}")
            else:
                matches += 1

        # Kalman
        kv_f, vad_f = kalman_all[idx]
        kv_s = sr.get('kalman_velocity')
        if kv_s is not None:
            diff = abs(kv_f - float(kv_s))
            if diff > 0.001:
                mismatches += 1
                errors.append(f"kalman_velocity: fresh={kv_f:.6f} stored={float(kv_s):.6f}")
            else:
                matches += 1

        vad_s = sr.get('vol_adj_delta')
        if vad_s is not None:
            diff = abs(vad_f - float(vad_s))
            if diff > 0.001:
                mismatches += 1
                errors.append(f"vol_adj_delta: fresh={vad_f:.6f} stored={float(vad_s):.6f}")
            else:
                matches += 1

    return matches, mismatches, errors


def main():
    print("=" * 90)
    print("  AUDITOR COMPLETO — 17 TICKERS × 5 BARRAS × 37 CAMPOS")
    print("  Cómputo fresco independiente vs Vault almacenado")
    print("=" * 90)

    t0 = time.time()
    store = TimescaleDataStore()
    
    total_m = 0
    total_mm = 0
    all_errors = []

    for ticker in TICKERS:
        t1 = time.time()
        m, mm, errs = audit_ticker(store, ticker)
        elapsed = time.time() - t1
        total_m += m
        total_mm += mm

        total = m + mm
        if mm == 0:
            print(f"  ✅ {ticker:>5s}: {m}/{total} match ({elapsed:.1f}s)")
        else:
            print(f"  ❌ {ticker:>5s}: {mm}/{total} MISMATCH ({elapsed:.1f}s)")
            for e in errs[:3]:
                print(f"     → {e}")
            all_errors.extend([(ticker, e) for e in errs])

    store.close()
    elapsed = time.time() - t0

    print(f"\n{'=' * 90}")
    grand = total_m + total_mm
    print(f"  RESULTADO: {total_m:,d}/{grand:,d} match | {total_mm:,d} mismatches | {elapsed:.1f}s")
    if total_mm == 0:
        print(f"  ★★★ AUDITORÍA APROBADA — DATA INTEGRITY 100% ★★★")
    else:
        pct = total_mm / max(grand, 1) * 100
        print(f"  ✖ {total_mm} MISMATCHES ({pct:.1f}%)")
    print(f"{'=' * 90}")


if __name__ == "__main__":
    main()
