#!/usr/bin/env python3
"""Anatomía de Velas en Overflows Cinemáticos V2.0 — Protocolo C.5 & C.6.

Mejoras clave vs V1.0:
1. SEGREGACIÓN MIN vs MAX vs ENTRE (elimina la mezcla de pisos y techos).
2. DESCOMPOSICIÓN DE EV EN BAR[+1]:
   - body_when_green (retorno medio cuando acierta)
   - body_when_red (retorno medio cuando falla)
   - EV_bar1 = WR_green * body_when_green + (1 - WR_green) * body_when_red
   - RR_bar1 = |body_when_green| / |body_when_red|
3. ANATOMÍA EXPANDIDA:
   - Sombra superior (wick): (high - max(open, close)) / close
   - Sombra inferior (tail): (min(open, close) - low) / close
   - Rango total: (high - low) / close
   - Volumen relativo: volume / SMA(volume, 20)
4. MANTIENE la segregación de Magnitudes: [2σ,3σ), [3σ,4σ), ≥4σ y Signos (+/-).
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
    'yield_curve': 'YIELD_SPREAD', 'rotation': 'ROTATION_INDEX', 'bsi': 'S5TW',
    'dxy': 'DXY',
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
    
    # Anatomical components
    spy_max_oc = np.maximum(spy_open, spy_close)
    spy_min_oc = np.minimum(spy_open, spy_close)
    spy_upper_wick = (spy_high - spy_max_oc) / spy_close
    spy_lower_tail = (spy_min_oc - spy_low) / spy_close
    spy_range_pct = (spy_high - spy_low) / spy_close
    spy_vol_sma20 = spy_volume.rolling(20).mean()
    spy_rel_vol = spy_volume / spy_vol_sma20.replace(0, np.nan)

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

    def slot_label(sd, pt):
        if abs(sd) > 2:
            return 'ENTRE', 'ENTRE'
        sl = {0: 't=0', -1: 't-1', -2: 't-2', 1: 't+1', 2: 't+2'}.get(sd, 'ENTRE')
        return sl, pt

    slot_info = [slot_label(sd, pt) for sd, pt in zip(best_sd, best_pt)]
    slots = np.array([x[0] for x in slot_info])
    pivot_contexts = np.array([x[1] for x in slot_info])

    spy_idx = spy_close.index
    spy_pos = {dt: i for i, dt in enumerate(spy_idx)}

    SLOT_ORDER = ['t-2', 't-1', 't=0', 't+1', 't+2', 'ENTRE']
    PIVOT_TYPES = ['MIN', 'MAX', 'ENTRE']

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
                    for pt_name in PIVOT_TYPES:
                        if sl_name == 'ENTRE' and pt_name != 'ENTRE':
                            continue
                        if sl_name != 'ENTRE' and pt_name == 'ENTRE':
                            continue

                        sl_mask = np.array([
                            (slots[np.searchsorted(common_dates, dt)] == sl_name and
                             pivot_contexts[np.searchsorted(common_dates, dt)] == pt_name)
                            if dt in common_dates else False
                            for dt in ovf_dates
                        ])
                        sl_dates = ovf_dates[sl_mask]
                        if len(sl_dates) < 3:
                            continue

                        # Collect candle anatomy for bar[-1], bar[0], bar[+1]
                        body_m1 = []
                        body_0 = []
                        body_p1 = []
                        
                        wick_p1 = []
                        tail_p1 = []
                        range_p1 = []
                        relvol_p1 = []
                        
                        z_vals = []

                        for dt in sl_dates:
                            pos = spy_pos.get(dt)
                            if pos is None or pos < 1 or pos >= len(spy_idx) - 1:
                                continue
                            body_m1.append(float(spy_body_pct.iloc[pos - 1]))
                            body_0.append(float(spy_body_pct.iloc[pos]))
                            body_p1.append(float(spy_body_pct.iloc[pos + 1]))
                            
                            wick_p1.append(float(spy_upper_wick.iloc[pos + 1]))
                            tail_p1.append(float(spy_lower_tail.iloc[pos + 1]))
                            range_p1.append(float(spy_range_pct.iloc[pos + 1]))
                            relvol_p1.append(float(spy_rel_vol.iloc[pos + 1]))
                            
                            z_vals.append(float(z_series.loc[dt]))

                        if len(body_0) < 3:
                            continue

                        body_m1 = np.array(body_m1)
                        body_0 = np.array(body_0)
                        body_p1 = np.array(body_p1)
                        wick_p1 = np.array(wick_p1)
                        tail_p1 = np.array(tail_p1)
                        range_p1 = np.array(range_p1)
                        relvol_p1 = np.array(relvol_p1)
                        z_vals = np.array(z_vals)

                        green_m1 = (body_m1 > 0).mean()
                        green_0 = (body_0 > 0).mean()
                        green_p1 = (body_p1 > 0).mean()

                        # EV Decomposition for bar[+1]
                        green_mask_p1 = body_p1 > 0
                        red_mask_p1 = body_p1 < 0

                        body_win = float(body_p1[green_mask_p1].mean()) if green_mask_p1.sum() > 0 else 0.0
                        body_loss = float(body_p1[red_mask_p1].mean()) if red_mask_p1.sum() > 0 else 0.0
                        
                        ev_bar1 = green_p1 * body_win + (1.0 - green_p1) * body_loss
                        abs_loss = abs(body_loss) if abs(body_loss) > 1e-6 else 1e-6
                        rr_bar1 = body_win / abs_loss if body_win > 0 else 0.0

                        n_samples = len(body_0)
                        n_win = int(green_mask_p1.sum())
                        n_loss = int(red_mask_p1.sum())

                        if n_samples >= 30:
                            tier = 'TIER_A (N≥30)'
                        elif n_samples >= 10:
                            tier = 'TIER_B (10-29)'
                        else:
                            tier = 'TIER_C (5-9)'

                        is_rr_artifact = (n_loss <= 2 or n_win <= 2)

                        results.append({
                            'station': station,
                            'dim': dim,
                            'sigma_bucket': bucket_name,
                            'sign': sign_name,
                            'slot': sl_name,
                            'pivot_type': pt_name,
                            'N': n_samples,
                            'tier': tier,
                            'n_win': n_win,
                            'n_loss': n_loss,
                            'is_rr_artifact': is_rr_artifact,
                            'z_mean': float(np.mean(z_vals)),
                            'z_max_abs': float(np.max(np.abs(z_vals))),
                            'bar_m1_green%': green_m1,
                            'bar_m1_body_mean': float(np.mean(body_m1)),
                            'bar_0_green%': green_0,
                            'bar_0_body_mean': float(np.mean(body_0)),
                            'bar_p1_green%': green_p1,
                            'bar_p1_body_mean': float(np.mean(body_p1)),
                            'body_when_green': body_win,
                            'body_when_red': body_loss,
                            'ev_bar1': ev_bar1,
                            'rr_bar1': rr_bar1,
                            'wick_p1_mean': float(np.nanmean(wick_p1)),
                            'tail_p1_mean': float(np.nanmean(tail_p1)),
                            'range_p1_mean': float(np.nanmean(range_p1)),
                            'relvol_p1_mean': float(np.nanmean(relvol_p1)),
                        })

    rdf = pd.DataFrame(results)

    # Save complete dataset as JSON/CSV
    out_dir = ROOT / 'data' / 'research' / 'anatomy'
    out_dir.mkdir(parents=True, exist_ok=True)
    rdf.to_json(out_dir / 'overflow_candle_anatomy_v2.json', orient='records', indent=2)
    rdf.to_csv(out_dir / 'overflow_candle_anatomy_v2.csv', index=False)
    print(f'Dataset guardado exitosamente: {len(rdf)} combinaciones analizadas.')

    # Print Key Analytical Views by Confidence Tier
    print('\n' + '=' * 130)
    print('TOP DIAMANTES ALCISTAS (MIN / t=0 / ENTRE) CLASIFICADOS POR TIER DE CONFIANZA')
    print('=' * 130)
    for tier in ['TIER_A (N≥30)', 'TIER_B (10-29)', 'TIER_C (5-9)']:
        print(f'\n--- {tier} ---')
        sub = rdf[(rdf['tier'] == tier) & (rdf['bar_p1_green%'] >= 0.70)].sort_values('ev_bar1', ascending=False)
        print(f'{"Canal":<18s} | {"Sigma":<6s} | {"Sign":<12s} | {"Slot":<5s} | {"Piv":<5s} | {"N":>3s} | {"WR_+1":>6s} | {"Win_+1":>7s} | {"Loss_+1":>7s} | {"EV_+1":>7s} | {"RR_+1":>7s} | {"RelVol":>6s}')
        print('-' * 125)
        for _, r in sub.head(10).iterrows():
            rr_str = f"{r['rr_bar1']:4.1f}:1*" if r['is_rr_artifact'] else f"{r['rr_bar1']:4.1f}:1"
            print(f'{r["station"]+"."+r["dim"]:<18s} | {r["sigma_bucket"]:<6s} | {r["sign"]:<12s} | {r["slot"]:<5s} | {r["pivot_type"]:<5s} | {r["N"]:3d} | {r["bar_p1_green%"]:6.1%} | {r["body_when_green"]:+6.2%} | {r["body_when_red"]:+6.2%} | {r["ev_bar1"]:+6.2%} | {rr_str:>7s} | {r["relvol_p1_mean"]:5.2f}x')

    print('\n' + '=' * 130)
    print('TOP DIAMANTES BAJISTAS (MAX / t=0 / t-1 / ENTRE) CLASIFICADOS POR TIER DE CONFIANZA')
    print('=' * 130)
    for tier in ['TIER_A (N≥30)', 'TIER_B (10-29)', 'TIER_C (5-9)']:
        print(f'\n--- {tier} ---')
        sub = rdf[(rdf['tier'] == tier) & (rdf['bar_p1_green%'] <= 0.30)].sort_values('ev_bar1', ascending=True)
        print(f'{"Canal":<18s} | {"Sigma":<6s} | {"Sign":<12s} | {"Slot":<5s} | {"Piv":<5s} | {"N":>3s} | {"WR_+1":>6s} | {"Win_+1":>7s} | {"Loss_+1":>7s} | {"EV_+1":>7s} | {"RR_+1":>7s} | {"RelVol":>6s}')
        print('-' * 125)
        for _, r in sub.head(10).iterrows():
            rr_str = f"{r['rr_bar1']:4.1f}:1*" if r['is_rr_artifact'] else f"{r['rr_bar1']:4.1f}:1"
            print(f'{r["station"]+"."+r["dim"]:<18s} | {r["sigma_bucket"]:<6s} | {r["sign"]:<12s} | {r["slot"]:<5s} | {r["pivot_type"]:<5s} | {r["N"]:3d} | {r["bar_p1_green%"]:6.1%} | {r["body_when_green"]:+6.2%} | {r["body_when_red"]:+6.2%} | {r["ev_bar1"]:+6.2%} | {rr_str:>7s} | {r["relvol_p1_mean"]:5.2f}x')


if __name__ == '__main__':
    run()
