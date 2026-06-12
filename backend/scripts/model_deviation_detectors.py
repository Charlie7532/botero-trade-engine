#!/usr/bin/env python3
"""
Model Deviation Detector Comparison
=====================================
¿Cuál herramienta detecta MEJOR cuándo el modelo se equivoca?

El modelo dice P(bull)=X%. La realidad es bull o bear (zigzag).
¿Cuándo el modelo está EQUIVOCADO, cuál detector lo señaló?

Detectores evaluados:
  1. hookup (close > prev_close) — reversión de vela
  2. kf_price_innovation — error de predicción del Kalman
  3. wave_accel sign — aceleración del Wave
  4. current_accel sign — aceleración del Current  
  5. kf_price_filt_vel — velocidad filtrada Kalman
  6. σVw transition — cambio del flujo VWAP Wave

Métricas:
  - P(model_wrong | detector_flag) — cuándo el detector señala, ¿el modelo falla?
  - P(detector_flag | model_wrong) — cuándo el modelo falla, ¿el detector señaló?
  - Lift = P(wrong|flag) / P(wrong|no_flag) — cuánto mejora la detección
"""
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_state_probability import (
    lookup_probability, _classify_sigma,
)


TEST_START = "2020-02-01"
ZIGZAG_LEVEL = 0.05


def load_data():
    store = TimescaleDataStore(); conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, vwap_sigma_wave, tide_slope,
               current_accel, wave_accel, tide_accel,
               kf_price_innovation, kf_price_filt_vel,
               kf_rvol_pred_val, kf_tension_filt_vel
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points
        WHERE min_swing_pct = {ZIGZAG_LEVEL}
        ORDER BY ticker, timestamp
    """, conn)

    bars = pd.read_sql("""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)

    store._put(conn); store.close()
    for d in [cs, zz, bars]:
        d['date'] = pd.to_datetime(d['date'])
    return cs, zz, bars


def label_outcomes(cs, zz, bars):
    """For each bar, determine actual bull/bear outcome from zigzag."""
    df = cs.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # Add P(bull)
    p_bulls = []
    for _, r in df.iterrows():
        rc = lookup_probability(
            float(r['tide_slope']), float(r['sigma_current']),
            float(r['sigma_wave']), float(r['vwap_sigma_wave']))
        p_bulls.append(rc.prob_bull if rc else None)
    df['p_bull'] = p_bulls
    df = df.dropna(subset=['p_bull'])

    # Add hookup, σVw transition
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    df['hookup'] = df['close'] > df['prev_close']

    svw_bin = df['vwap_sigma_wave'].apply(_classify_sigma)
    prev_svw = df.groupby('ticker')['vwap_sigma_wave'].shift(1).apply(_classify_sigma)
    rank_map = {'<<': 0, '<': 1, '~': 2, '>': 3, '>>': 4}
    df['svw_rank'] = svw_bin.map(rank_map)
    df['prev_svw_rank'] = prev_svw.map(rank_map)
    df['svw_transition'] = df['svw_rank'] - df['prev_svw_rank']

    # Actual outcome: is next zigzag event bullish?
    # Bull = next peak is higher than current price by >2%
    # Bear = next trough is lower than current price by >2%
    outcomes = []
    for ticker in df['ticker'].unique():
        tk = df[df['ticker'] == ticker]
        tk_zz = zz[zz['ticker'] == ticker].sort_values('date')
        peaks = tk_zz[tk_zz['tp_type'] == 'MAX']
        troughs = tk_zz[tk_zz['tp_type'] == 'MIN']

        peak_dates = pd.to_datetime(peaks['date']).values
        peak_prices = peaks['price'].values.astype(float)
        trough_dates = pd.to_datetime(troughs['date']).values
        trough_prices = troughs['price'].values.astype(float)

        for _, row in tk.iterrows():
            d = np.datetime64(row['date'])
            price = float(row['close'])

            # Next peak
            pi = np.searchsorted(peak_dates, d, side='right')
            # Next trough
            ti = np.searchsorted(trough_dates, d, side='right')

            if pi >= len(peak_dates) or ti >= len(trough_dates):
                outcomes.append(None)
                continue

            next_peak = peak_prices[pi]
            next_trough = trough_prices[ti]
            next_peak_date = peak_dates[pi]
            next_trough_date = trough_dates[ti]

            # Which comes first: peak or trough?
            if next_peak_date < next_trough_date:
                # Peak comes first → bullish (price goes up before going down)
                outcomes.append(True)
            else:
                # Trough comes first → bearish (price goes down before going up)
                outcomes.append(False)

    df['actual_bull'] = outcomes
    df = df.dropna(subset=['actual_bull'])
    df['actual_bull'] = df['actual_bull'].astype(bool)

    # Model prediction
    df['model_says_bull'] = df['p_bull'] >= 0.65
    df['model_says_bear'] = df['p_bull'] <= 0.35
    df['model_correct'] = ((df['model_says_bull'] & df['actual_bull']) |
                           (df['model_says_bear'] & ~df['actual_bull']) |
                           (~df['model_says_bull'] & ~df['model_says_bear']))
    df['model_wrong'] = df['model_says_bull'] & ~df['actual_bull']  # Said bull, was bear
    df['model_wrong_bear'] = df['model_says_bear'] & df['actual_bull']  # Said bear, was bull

    return df


def test_detectors(df):
    """Test each detector's ability to flag model errors."""
    # Focus on ACCUMULATE signals (P>=65%) that were WRONG
    accum = df[df['model_says_bull']].copy()
    n_total = len(accum)
    n_wrong = accum['model_wrong'].sum()
    base_error_rate = n_wrong / n_total

    print(f"\n{'='*130}")
    print(f"  MODEL DEVIATION DETECTOR COMPARISON")
    print(f"  ACCUMULATE signals (P≥65%): {n_total:,} | Wrong (said bull, was bear): {n_wrong:,} ({base_error_rate:.1%})")
    print(f"{'='*130}")

    # Define detectors — each returns True when it SUSPECTS the model is wrong
    # (i.e., when conditions suggest the prediction might fail)
    detectors = {
        # HOOKUP detectors
        "hookup=NO (no reversal)":
            ~accum['hookup'],
        "hookup=YES (confirming)":
            accum['hookup'],

        # ACCELERATION detectors
        "wave_accel < 0 (still falling)":
            accum['wave_accel'] < 0,
        "wave_accel > 0 (decelerating)":
            accum['wave_accel'] > 0,
        "current_accel < 0":
            accum['current_accel'] < 0,
        "current_accel > 0":
            accum['current_accel'] > 0,
        "BOTH accels < 0 (all falling)":
            (accum['wave_accel'] < 0) & (accum['current_accel'] < 0),
        "BOTH accels > 0 (all rising)":
            (accum['wave_accel'] > 0) & (accum['current_accel'] > 0),

        # KALMAN detectors
        "kf_innovation < 0 (price below pred)":
            accum['kf_price_innovation'] < 0,
        "kf_innovation > 0 (price above pred)":
            accum['kf_price_innovation'] > 0,
        "kf_innovation < -1σ (big miss down)":
            accum['kf_price_innovation'] < accum['kf_price_innovation'].quantile(0.16),
        "kf_innovation > +1σ (big miss up)":
            accum['kf_price_innovation'] > accum['kf_price_innovation'].quantile(0.84),
        "kf_velocity < 0 (Kalman says down)":
            accum['kf_price_filt_vel'] < 0,
        "kf_velocity > 0 (Kalman says up)":
            accum['kf_price_filt_vel'] > 0,

        # σVw TRANSITION detectors
        "σVw improving (Δ≥+1)":
            accum['svw_transition'] >= 1,
        "σVw worsening (Δ≤-1)":
            accum['svw_transition'] <= -1,
        "σVw stable (Δ=0)":
            accum['svw_transition'] == 0,

        # COMBINATIONS
        "hookup=NO + both_accel<0":
            ~accum['hookup'] & (accum['wave_accel'] < 0) & (accum['current_accel'] < 0),
        "hookup=NO + kf_vel<0":
            ~accum['hookup'] & (accum['kf_price_filt_vel'] < 0),
        "both_accel<0 + kf_vel<0":
            (accum['wave_accel'] < 0) & (accum['current_accel'] < 0) & (accum['kf_price_filt_vel'] < 0),
        "ALL 3 negative: !hookup + accel<0 + kf<0":
            ~accum['hookup'] & (accum['wave_accel'] < 0) & (accum['current_accel'] < 0) & (accum['kf_price_filt_vel'] < 0),
        "hookup=YES + both_accel>0":
            accum['hookup'] & (accum['wave_accel'] > 0) & (accum['current_accel'] > 0),
        "hookup=YES + both_accel>0 + kf_vel>0":
            accum['hookup'] & (accum['wave_accel'] > 0) & (accum['current_accel'] > 0) & (accum['kf_price_filt_vel'] > 0),
    }

    print(f"\n  {'Detector':<45s} {'N':>6s} {'%flag':>7s} {'err_flag':>9s} {'err_¬flag':>9s} "
          f"{'LIFT':>6s} {'P(flag|err)':>11s} {'verdict':>10s}")
    print(f"  {'─'*45} {'─'*6} {'─'*7} {'─'*9} {'─'*9} {'─'*6} {'─'*11} {'─'*10}")

    results = []
    for name, flag_mask in detectors.items():
        n_flag = flag_mask.sum()
        if n_flag < 20 or (~flag_mask).sum() < 20:
            continue

        pct_flag = n_flag / n_total

        # P(wrong | flagged)
        wrong_when_flagged = accum[flag_mask]['model_wrong'].sum()
        err_rate_flagged = wrong_when_flagged / n_flag

        # P(wrong | NOT flagged)
        wrong_when_not = accum[~flag_mask]['model_wrong'].sum()
        err_rate_not = wrong_when_not / (~flag_mask).sum()

        # Lift
        lift = err_rate_flagged / max(err_rate_not, 0.001)

        # P(flagged | wrong) — sensitivity
        sensitivity = wrong_when_flagged / max(n_wrong, 1)

        # Verdict
        if lift > 1.3 and sensitivity > 0.3:
            verdict = "★ GOOD"
        elif lift > 1.15:
            verdict = "○ DECENT"
        elif lift < 0.85 and err_rate_flagged < err_rate_not:
            verdict = "✓ SAFE"  # Flag means LESS error
        else:
            verdict = "— WEAK"

        print(f"  {name:<45s} {n_flag:>6,} {pct_flag:>6.1%} {err_rate_flagged:>8.1%} {err_rate_not:>8.1%} "
              f"{lift:>5.2f}x {sensitivity:>10.1%} {verdict:>10s}")

        results.append({
            'name': name, 'n_flag': n_flag, 'err_flagged': err_rate_flagged,
            'err_not': err_rate_not, 'lift': lift, 'sensitivity': sensitivity,
        })

    rt = pd.DataFrame(results)

    # Best DANGER detector (highest lift)
    if len(rt) > 0:
        danger = rt[rt['lift'] > 1.0].nlargest(5, 'lift')
        print(f"\n  TOP 5 DANGER DETECTORS (flag = higher error rate):")
        for _, r in danger.iterrows():
            print(f"    {r['name']:<45s} lift={r['lift']:.2f}x err={r['err_flagged']:.1%}")

        # Best SAFETY detector (lowest error when flagged)
        safe = rt[rt['lift'] < 1.0].nsmallest(5, 'err_flagged')
        print(f"\n  TOP 5 SAFETY DETECTORS (flag = lower error rate):")
        for _, r in safe.iterrows():
            print(f"    {r['name']:<45s} lift={r['lift']:.2f}x err={r['err_flagged']:.1%}")

    # ═══════════════════════════════════════════════════════════
    # By P(bull) quintile — do detectors work differently at different conviction levels?
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*130}")
    print(f"  DETECTOR PERFORMANCE BY P(bull) LEVEL")
    print(f"{'='*130}")

    best_detectors = [
        ("hookup=NO (no reversal)", ~accum['hookup']),
        ("BOTH accels < 0", (accum['wave_accel'] < 0) & (accum['current_accel'] < 0)),
        ("kf_velocity < 0", accum['kf_price_filt_vel'] < 0),
        ("ALL 3 negative", ~accum['hookup'] & (accum['wave_accel'] < 0) & (accum['current_accel'] < 0) & (accum['kf_price_filt_vel'] < 0)),
        ("hookup=YES + accel>0 + kf>0", accum['hookup'] & (accum['wave_accel'] > 0) & (accum['current_accel'] > 0) & (accum['kf_price_filt_vel'] > 0)),
    ]

    pbins = [(0.65, 0.75, "65-75%"), (0.75, 0.85, "75-85%"), (0.85, 1.01, "85-100%")]

    for det_name, det_mask in best_detectors:
        print(f"\n  Detector: {det_name}")
        print(f"  {'P(bull)':<12s} {'N_flag':>8s} {'err_flag':>9s} {'err_¬flag':>9s} {'lift':>6s}")
        for lo, hi, label in pbins:
            pmask = (accum['p_bull'] >= lo) & (accum['p_bull'] < hi)
            sub = accum[pmask]
            sub_flag = sub[det_mask[pmask.values]]
            sub_not = sub[~det_mask[pmask.values]]
            if len(sub_flag) < 20 or len(sub_not) < 20:
                continue
            ef = sub_flag['model_wrong'].mean()
            en = sub_not['model_wrong'].mean()
            lift = ef / max(en, 0.001)
            print(f"  {label:<12s} {len(sub_flag):>8,} {ef:>8.1%} {en:>8.1%} {lift:>5.2f}x")

    print("\nDONE")


def main():
    cs, zz, bars = load_data()
    df = label_outcomes(cs, zz, bars)
    test_detectors(df)


if __name__ == "__main__":
    main()
