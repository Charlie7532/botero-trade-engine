#!/usr/bin/env python3
"""Anatomía de Velas en Overflows Cinemáticos — Análisis Correcto.

Para cada overflow ≥2σ detectado vela a vela en el Vault:
1. Aísla la magnitud: [2σ,3σ), [3σ,4σ), ≥4σ — positivos y negativos por separado
2. Mide la anatomía de 3 velas: bar[-1] (antecesora), bar[0] (actual), bar[+1] (siguiente)
3. Clasifica por slot temporal relativo al pivote: t-2, t-1, t=0, t+1, t+2, ENTRE
4. Identifica señales diamante por la reacción inmediata de SPY

NO mide retornos a horizonte fijo. Mide COMPORTAMIENTO de la vela individual.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.sigma_overflow import STATION_MU_SIGMA

TICKERS = {
    'vix': 'VIX', 'vvix': 'VVIX', 'pcr': 'CBOE_PCR', 'fg': 'FG',
    'sv5_turbulence': 'SV5_TURBULENCE', 'skew': 'SKEW', 'credit': 'CREDIT_RATIO',
    'yield_curve': 'YIELD_SPREAD', 'rotation': 'ROTATION_INDEX', 'bsi': 'S5TW'
}

SIGMA_BUCKETS = [
    ('2σ_3σ', 2.0, 3.0),
    ('3σ_4σ', 3.0, 4.0),
    ('≥4σ',   4.0, 999.0),
]


def run():
    store = TimescaleDataStore()

    # SPY candle data (OHLCV)
    spy = store.load_bars('SPY', '1d').sort_index()
    spy.index = spy.index.tz_localize(None).normalize()
    spy_close = spy['close']
    spy_open = spy['open']
    spy_high = spy['high']
    spy_low = spy['low']
    spy_volume = spy['volume']

    # SPY bar return = (close - open) / open (intraday body)
    spy_body_pct = (spy_close - spy_open) / spy_open
    # SPY close-to-close return
    spy_cc_ret = spy_close.pct_change()
    # SPY range (high-low)/close
    spy_range_pct = (spy_high - spy_low) / spy_close

    # Pivots
    qo = pd.read_pickle(ROOT / 'data' / 'research' / 'pivots' / 'quants_obs.pkl')
    pivot_df = qo.drop_duplicates(subset=['pivot_date'], keep='first').copy()
    pivot_df['dt'] = pd.to_datetime(pivot_df['pivot_date']).dt.tz_localize(None).dt.normalize()
    pivot_df = pivot_df.sort_values('dt')
    piv_dates_int = pivot_df['dt'].values.astype('datetime64[D]').astype(int)
    piv_types = pivot_df['pivot_type'].values

    # Build z-matrix
    z_frames = {}
    for station, dims in STATION_MU_SIGMA.items():
        ticker = TICKERS.get(station)
        if not ticker:
            continue
        bars = store.load_bars(ticker, '1d')
        if bars is None or len(bars) < 30:
            continue
        raw = bars.sort_index()['close']
        raw.index = raw.index.tz_localize(None).normalize()
        for d, (mu, sigma) in dims.items():
            if sigma <= 0:
                continue
            if d == 'd1':
                s = raw
            elif d == 'd2':
                s = raw.diff(3)
            elif d == 'd3':
                s = raw.rolling(2).std() / raw.rolling(10).std()
            else:
                continue
            z = (s.dropna() - mu) / sigma
            z_frames[f'{station}.{d}'] = z

    z_mat = pd.DataFrame(z_frames)
    # Align to SPY dates
    common_dates = z_mat.index.intersection(spy_close.index)
    z_mat = z_mat.loc[common_dates]

    dates_int = common_dates.values.astype('datetime64[D]').astype(int)

    # Vectorized nearest pivot
    idxs = np.searchsorted(piv_dates_int, dates_int)
    idxs_c = np.clip(idxs, 0, len(piv_dates_int) - 1)
    idxs_p = np.clip(idxs - 1, 0, len(piv_dates_int) - 1)
    d_prev = dates_int - piv_dates_int[idxs_p]
    d_next = dates_int - piv_dates_int[idxs_c]
    best_sd = np.where(np.abs(d_prev) < np.abs(d_next), d_prev, d_next)
    best_pt = np.where(np.abs(d_prev) < np.abs(d_next), piv_types[idxs_p], piv_types[idxs_c])

    def slot(sd):
        return {0: 't=0', -1: 't-1', -2: 't-2', 1: 't+1', 2: 't+2'}.get(sd, 'ENTRE')

    slots = np.array([slot(s) for s in best_sd])

    # SPY position lookup
    spy_idx = spy_close.index
    spy_pos = {dt: i for i, dt in enumerate(spy_idx)}

    print('=' * 100)
    print('ANATOMÍA DE VELAS: OVERFLOWS AISLADOS POR MAGNITUD, SIGNO Y ESTACIÓN')
    print('=' * 100)

    # For each station.dim, for each sigma bucket, for each sign:
    # Collect bar[-1], bar[0], bar[+1] SPY behavior
    SLOT_ORDER = ['t-2', 't-1', 't=0', 't+1', 't+2', 'ENTRE']

    results = []

    for col in z_mat.columns:
        z_series = z_mat[col].dropna()
        station, dim = col.split('.')

        for bucket_name, lo, hi in SIGMA_BUCKETS:
            for sign_name, sign_fn in [('POSITIVO(+)', lambda z: z > 0), ('NEGATIVO(-)', lambda z: z < 0)]:
                mask = sign_fn(z_series) & (z_series.abs() >= lo) & (z_series.abs() < hi)
                ovf_dates = z_series.index[mask]
                if len(ovf_dates) < 3:
                    continue

                for sl_name in SLOT_ORDER:
                    sl_mask = np.array([slots[np.searchsorted(common_dates, dt)] == sl_name
                                        if dt in common_dates else False
                                        for dt in ovf_dates])
                    sl_dates = ovf_dates[sl_mask]
                    if len(sl_dates) < 3:
                        continue

                    # Collect candle anatomy
                    body_m1 = []  # bar[-1]
                    body_0 = []   # bar[0]
                    body_p1 = []  # bar[+1]
                    z_vals = []

                    for dt in sl_dates:
                        pos = spy_pos.get(dt)
                        if pos is None or pos < 1 or pos >= len(spy_idx) - 1:
                            continue
                        body_m1.append(float(spy_body_pct.iloc[pos - 1]))
                        body_0.append(float(spy_body_pct.iloc[pos]))
                        body_p1.append(float(spy_body_pct.iloc[pos + 1]))
                        z_vals.append(float(z_series.loc[dt]))

                    if len(body_0) < 3:
                        continue

                    body_m1 = np.array(body_m1)
                    body_0 = np.array(body_0)
                    body_p1 = np.array(body_p1)
                    z_vals = np.array(z_vals)

                    # Green candle = body > 0
                    green_m1 = (body_m1 > 0).mean()
                    green_0 = (body_0 > 0).mean()
                    green_p1 = (body_p1 > 0).mean()

                    results.append({
                        'station': station,
                        'dim': dim,
                        'sigma_bucket': bucket_name,
                        'sign': sign_name,
                        'slot': sl_name,
                        'N': len(body_0),
                        'z_mean': np.mean(z_vals),
                        'z_max_abs': np.max(np.abs(z_vals)),
                        'bar_m1_green%': green_m1,
                        'bar_m1_body_mean': np.mean(body_m1),
                        'bar_0_green%': green_0,
                        'bar_0_body_mean': np.mean(body_0),
                        'bar_p1_green%': green_p1,
                        'bar_p1_body_mean': np.mean(body_p1),
                    })

    rdf = pd.DataFrame(results)

    # ═══ RESUMEN GLOBAL: % velas verdes por magnitud sigma ═══
    print('\n>>> RESUMEN GLOBAL: % VELA VERDE SPY EN BAR[0] POR MAGNITUD DE OVERFLOW')
    print(f'{"Sigma":>8s} | {"Sign":>13s} | {"N":>6s} | {"Bar[-1] Green%":>14s} | {"Bar[0] Green%":>13s} | {"Bar[+1] Green%":>14s}')
    print('-' * 80)
    for bucket in ['2σ_3σ', '3σ_4σ', '≥4σ']:
        for sign in ['POSITIVO(+)', 'NEGATIVO(-)']:
            sub = rdf[(rdf['sigma_bucket'] == bucket) & (rdf['sign'] == sign)]
            if sub.empty:
                continue
            total_n = sub['N'].sum()
            # Weighted average of green%
            wg_m1 = (sub['bar_m1_green%'] * sub['N']).sum() / total_n
            wg_0 = (sub['bar_0_green%'] * sub['N']).sum() / total_n
            wg_p1 = (sub['bar_p1_green%'] * sub['N']).sum() / total_n
            print(f'{bucket:>8s} | {sign:>13s} | {total_n:6d} | {wg_m1:13.1%} | {wg_0:12.1%} | {wg_p1:13.1%}')

    # ═══ POR ESTACIÓN: Señales diamante (bar[+1] ≥70% o ≤30%) ═══
    print('\n>>> SEÑALES DIAMANTE: Bar[+1] Green% ≥70% o ≤30% (N≥10)')
    print(f'{"Canal":>22s} | {"Sigma":>6s} | {"Sign":>13s} | {"Slot":>6s} | {"N":>5s} | {"B[-1]%":>7s} | {"B[0]%":>7s} | {"B[+1]%":>7s} | {"B[+1] body":>10s}')
    print('-' * 100)
    diamonds = rdf[(rdf['N'] >= 10) & ((rdf['bar_p1_green%'] >= 0.70) | (rdf['bar_p1_green%'] <= 0.30))]
    diamonds = diamonds.sort_values('bar_p1_green%', ascending=False)
    for _, row in diamonds.iterrows():
        print(f'{row["station"]+"."+row["dim"]:>22s} | {row["sigma_bucket"]:>6s} | {row["sign"]:>13s} | {row["slot"]:>6s} | {row["N"]:5d} | {row["bar_m1_green%"]:6.0%} | {row["bar_0_green%"]:6.0%} | {row["bar_p1_green%"]:6.0%} | {row["bar_p1_body_mean"]:+9.4f}')

    # ═══ POR SLOT: Comportamiento medio de la vela ═══
    print('\n>>> POR SLOT TEMPORAL: Media de cuerpo de vela SPY')
    print(f'{"Slot":>6s} | {"N":>6s} | {"Bar[-1] Body%":>14s} | {"Bar[0] Body%":>13s} | {"Bar[+1] Body%":>14s}')
    print('-' * 65)
    for sl in SLOT_ORDER:
        sub = rdf[rdf['slot'] == sl]
        if sub.empty:
            continue
        total_n = sub['N'].sum()
        wg_m1 = (sub['bar_m1_body_mean'] * sub['N']).sum() / total_n
        wg_0 = (sub['bar_0_body_mean'] * sub['N']).sum() / total_n
        wg_p1 = (sub['bar_p1_body_mean'] * sub['N']).sum() / total_n
        print(f'{sl:>6s} | {total_n:6d} | {wg_m1:+13.4f} | {wg_0:+12.4f} | {wg_p1:+13.4f}')

    # ═══ EXTREMOS: ≥4σ separados ═══
    print('\n>>> EVENTOS EXTREMOS ≥4σ: Anatomía individual')
    extremes = rdf[rdf['sigma_bucket'] == '≥4σ'].sort_values('N', ascending=False)
    print(f'{"Canal":>22s} | {"Sign":>13s} | {"Slot":>6s} | {"N":>4s} | {"z_max":>6s} | {"B[-1]%":>7s} | {"B[0]%":>7s} | {"B[+1]%":>7s}')
    print('-' * 90)
    for _, row in extremes.head(30).iterrows():
        print(f'{row["station"]+"."+row["dim"]:>22s} | {row["sign"]:>13s} | {row["slot"]:>6s} | {row["N"]:4d} | {row["z_max_abs"]:5.1f} | {row["bar_m1_green%"]:6.0%} | {row["bar_0_green%"]:6.0%} | {row["bar_p1_green%"]:6.0%}')


if __name__ == '__main__':
    run()
