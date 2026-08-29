#!/usr/bin/env python3
"""Auditoría Profunda de la Confluencia y Polaridad del Vector de Estado Completo."""

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.sigma_overflow import STATION_MU_SIGMA

def run_deep_audit():
    store = TimescaleDataStore()
    spy = store.load_bars('SPY', '1d').sort_index()
    spy_close = spy['close']
    fwd_1d = spy_close.pct_change(1).shift(-1)
    fwd_5d = spy_close.pct_change(5).shift(-5)
    fwd_20d = spy_close.pct_change(20).shift(-20)
    for s in [fwd_1d, fwd_5d, fwd_20d]:
        s.index = s.index.tz_localize(None).normalize()

    qo = pd.read_pickle('data/research/pivots/quants_obs.pkl')
    pivot_df = qo.drop_duplicates(subset=['pivot_date'], keep='first').copy()
    pivot_df['dt'] = pd.to_datetime(pivot_df['pivot_date']).dt.tz_localize(None).dt.normalize()
    pivot_df = pivot_df.sort_values('dt')
    piv_dates = pivot_df['dt'].values
    piv_types = pivot_df['pivot_type'].values
    piv_dates_int = piv_dates.astype('datetime64[D]').astype(int)

    TICKERS = {
        'vix': 'VIX', 'vvix': 'VVIX', 'pcr': 'CBOE_PCR', 'fg': 'FG',
        'sv5_turbulence': 'SV5_TURBULENCE', 'skew': 'SKEW', 'credit': 'CREDIT_RATIO',
        'yield_curve': 'YIELD_SPREAD', 'rotation': 'ROTATION_INDEX', 'bsi': 'S5TW'
    }

    z_frames = {}
    for station, dims in STATION_MU_SIGMA.items():
        ticker = TICKERS.get(station)
        if not ticker: continue
        bars = store.load_bars(ticker, '1d')
        if bars is None or len(bars) < 30: continue
        raw = bars.sort_index()['close']
        for d, (mu, sigma) in dims.items():
            if sigma <= 0: continue
            s = raw if d=='d1' else (raw.diff(3) if d=='d2' else raw.rolling(2).std()/raw.rolling(10).std())
            z = (s.dropna() - mu) / sigma
            z.index = z.index.tz_localize(None).normalize()
            z_frames[f'{station}.{d}'] = z

    # Aligned DataFrame
    valid_dates = fwd_20d.dropna().index
    z_mat = pd.DataFrame(z_frames).reindex(valid_dates)
    fwd_1d_aligned = fwd_1d.reindex(valid_dates)
    fwd_5d_aligned = fwd_5d.reindex(valid_dates)
    fwd_20d_aligned = fwd_20d.reindex(valid_dates)

    dates_int = valid_dates.values.astype('datetime64[D]').astype(int)

    # Fast vectorized nearest search
    idxs = np.searchsorted(piv_dates_int, dates_int)
    idxs_clamped = np.clip(idxs, 0, len(piv_dates_int)-1)
    idxs_prev = np.clip(idxs-1, 0, len(piv_dates_int)-1)

    d1 = dates_int - piv_dates_int[idxs_prev]
    d2 = dates_int - piv_dates_int[idxs_clamped]

    best_sd = np.where(np.abs(d1) < np.abs(d2), d1, d2)
    best_pt = np.where(np.abs(d1) < np.abs(d2), piv_types[idxs_prev], piv_types[idxs_clamped])

    slots = []
    for sd in best_sd:
        if sd == 0: slots.append('t=0')
        elif sd == -1: slots.append('t-1')
        elif sd == -2: slots.append('t-2')
        elif sd == 1: slots.append('t+1')
        elif sd == 2: slots.append('t+2')
        else: slots.append('ENTRE')
    slots = np.array(slots)

    # Panic vs Euphoria scores
    panic_scores = np.zeros(len(z_mat), dtype=int)
    euphoria_scores = np.zeros(len(z_mat), dtype=int)

    for col in z_mat.columns:
        st, dim = col.split('.')
        vals = z_mat[col].values
        pos = (vals >= 2.0)
        neg = (vals <= -2.0)
        
        # Panic signs
        if st in ['vix', 'vvix', 'pcr', 'sv5_turbulence']:
            panic_scores += np.where(pos, 1, 0)
        elif st in ['fg', 'bsi', 'rotation']:
            euphoria_scores += np.where(pos, 1, 0)
            
        if st in ['fg', 'bsi', 'credit', 'rotation']:
            panic_scores += np.where(neg, 1, 0)
        elif st in ['vix', 'pcr']:
            euphoria_scores += np.where(neg, 1, 0)

    n_sim = (z_mat.abs() >= 2.0).sum(axis=1).values

    df = pd.DataFrame({
        'date': valid_dates,
        'slot': slots,
        'signed_dist': best_sd,
        'pivot_type': best_pt,
        'n_sim': n_sim,
        'panic_score': panic_scores,
        'euphoria_score': euphoria_scores,
        'fwd_1d': fwd_1d_aligned.values,
        'fwd_5d': fwd_5d_aligned.values,
        'fwd_20d': fwd_20d_aligned.values,
    })

    print("=" * 80)
    print("AUDITORÍA DE POLARIDAD Y CONFLUENCIA: t=0 MIN (PISOS) vs t=0 MAX (TECHOS)")
    print("=" * 80)

    t0_min = df[(df['slot'] == 't=0') & (df['pivot_type'] == 'MIN') & (df['n_sim'] > 0)]
    t0_max = df[(df['slot'] == 't=0') & (df['pivot_type'] == 'MAX') & (df['n_sim'] > 0)]

    print(f"\n>>> t=0 MIN (Pisos reales del mercado, N={len(t0_min)})")
    print(f"Panic Score medio: {t0_min['panic_score'].mean():.2f} | Euphoria Score medio: {t0_min['euphoria_score'].mean():.2f}")
    print(f"{'PanicScore':>11s} | {'N':>5s} | {'WR_1d':>8s} | {'WR_5d':>8s} | {'WR_20d':>8s} | {'Fwd_20d':>10s}")
    print("-" * 55)
    for ps in sorted(t0_min['panic_score'].unique()):
        sub = t0_min[t0_min['panic_score'] == ps]
        if len(sub) < 3: continue
        w1 = (sub['fwd_1d'] > 0).mean()
        w5 = (sub['fwd_5d'] > 0).mean()
        w20 = (sub['fwd_20d'] > 0).mean()
        fm = sub['fwd_20d'].mean()
        print(f"{ps:11d} | {len(sub):5d} | {w1:7.1%} | {w5:7.1%} | {w20:7.1%} | {fm:+9.4f}")

    print(f"\n>>> t=0 MAX (Techos reales del mercado, N={len(t0_max)})")
    print(f"Euphoria Score medio: {t0_max['euphoria_score'].mean():.2f} | Panic Score medio: {t0_max['panic_score'].mean():.2f}")
    print(f"{'EuphoriaScore':>13s} | {'N':>5s} | {'Short_WR_1d':>12s} | {'Short_WR_5d':>12s} | {'Short_WR_20d':>13s} | {'Fwd_20d':>10s}")
    print("-" * 65)
    for es in sorted(t0_max['euphoria_score'].unique()):
        sub = t0_max[t0_max['euphoria_score'] == es]
        if len(sub) < 2: continue
        w1 = (sub['fwd_1d'] < 0).mean()
        w5 = (sub['fwd_5d'] < 0).mean()
        w20 = (sub['fwd_20d'] < 0).mean()
        fm = sub['fwd_20d'].mean()
        print(f"{es:13d} | {len(sub):5d} | {w1:11.1%} | {w5:11.1%} | {w20:12.1%} | {fm:+9.4f}")

    print("\n" + "=" * 80)
    print("AUDITORÍA DE POLARIDAD EN EVENTOS ENTRE (>2d de cualquier pivote)")
    print("=" * 80)
    entre = df[(df['slot'] == 'ENTRE') & (df['n_sim'] > 0)]
    print(f"Total barras ENTRE con overflow: {len(entre)}")
    
    print("\n>>> ENTRE con Panic Score >= K (Capitulación en tendencia):")
    print(f"{'PanicScore>=':>13s} | {'N':>5s} | {'Long_WR_1d':>11s} | {'Long_WR_5d':>11s} | {'Long_WR_20d':>12s} | {'Fwd_20d':>10s}")
    print("-" * 65)
    for ps in [1, 2, 3, 4, 5, 6, 7]:
        sub = entre[entre['panic_score'] >= ps]
        if len(sub) >= 3:
            w1 = (sub['fwd_1d'] > 0).mean()
            w5 = (sub['fwd_5d'] > 0).mean()
            w20 = (sub['fwd_20d'] > 0).mean()
            fm = sub['fwd_20d'].mean()
            print(f"{ps:13d} | {len(sub):5d} | {w1:10.1%} | {w5:10.1%} | {w20:11.1%} | {fm:+9.4f}")

    print("\n>>> ENTRE con Euphoria Score >= K (Euforia / Agotamiento en tendencia):")
    print(f"{'EuphoriaScore>=':>16s} | {'N':>5s} | {'Short_WR_1d':>12s} | {'Short_WR_5d':>12s} | {'Short_WR_20d':>13s} | {'Fwd_20d':>10s}")
    print("-" * 70)
    for es in [1, 2, 3, 4, 5]:
        sub = entre[entre['euphoria_score'] >= es]
        if len(sub) >= 3:
            w1 = (sub['fwd_1d'] < 0).mean()
            w5 = (sub['fwd_5d'] < 0).mean()
            w20 = (sub['fwd_20d'] < 0).mean()
            fm = sub['fwd_20d'].mean()
            print(f"{es:16d} | {len(sub):5d} | {w1:11.1%} | {w5:11.1%} | {w20:12.1%} | {fm:+9.4f}")

if __name__ == '__main__':
    run_deep_audit()
