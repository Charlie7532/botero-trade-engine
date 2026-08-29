#!/usr/bin/env python3
"""Recomputación Triádica Dinámica de Señales Entry/Exit V2.0 — Protocolo C.1 & C.2 Definitivo.

Correcciones clave vs V1.0 (Auditoría Claude Opus):
1. AGREGACIÓN PONDERADA COMPLETA sobre TODOS los state_keys activos (elimina el sesgo de elegir solo top-1).
2. SOPORTE MULTI-ESTACIÓN: Señales bi-estación (p. ej. capitulación = VIX + BSI) reportan AMBAS estaciones y su convergencia conjunta.
3. MAPEO DETERMINISTA EXPLICITO (SIGNAL_STATIONS) para las 31 señales del arnés.
4. CLASIFICACIÓN EN TIERS DE CONFIANZA MUESTRAL (Tier A: N≥30, Tier B: 10≤N<30, Tier C: 5≤N<10).
5. Descomposición matemática rigurosa: E[p_bull], E[e_ret_max], E[e_ret_min], E[EV_raw], E[ev_net], E[R:R], E[e_days].
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'research' / '01_señales_entry_exit'))

from arnes.datos import cargar_datos
from arnes.registro import SEÑALES, _CERTEZA
import arnes.señales  # registers all signals

FACT_STORE_DIR = ROOT / 'backend' / 'modules' / 'entry_decision' / 'domain/rules'

SIGNAL_STATIONS = {
    'credit_easing_k1': ['credit'],
    'sorpresa_total': ['vix', 'skew', 'credit', 'bsi'],  # Estaciones representativas del vector Shannon
    'panico_total': ['vix', 'skew'],
    'capitulacion': ['vix', 'bsi'],
    'sub_reaccion': ['vix', 'bsi'],
    'euforia': ['vix', 'bsi'],
    'vvix_entry': ['vvix'],
    'bsi_washed_out': ['bsi'],
    'credit_stress': ['credit'],
    'dxy_bearish': ['dxy'],
    'pcr_put_panic': ['pcr'],
    'fg_extreme_fear': ['fg'],
    'fg_extreme_greed': ['fg'],
    'bsi_recovery': ['bsi'],
    'vix_crisis_spike': ['vix'],
    'cascade_reversal': ['sv5_turbulence', 'vix'],
    'credit_stress_exit': ['credit'],
    'dxy_spike_exit': ['dxy'],
    'pcr_panic_exit': ['pcr'],
    'skew_paranoia_exit': ['skew'],
    'vix_complacency_exit': ['vix'],
    'credit_ease_exit': ['credit'],
    'breadth_contraction_exit': ['bsi'],
    'regime_change_exit': ['credit', 'vix', 'bsi'],
    'sv5t_silent_distribution': ['sv5_turbulence'],
    'credit_equity_divergence': ['credit'],
    'stealth_tail_hedging': ['vix', 'skew'],
    'defensive_rotation_divergence': ['rotation'],
    'capitulacion_v2': ['vix', 'bsi'],
    'euforia_v2': ['bsi'],
    'vix_crisis_spike_v2': ['vix'],
}


def load_fact_stores():
    stores = {}
    for st in ['vix', 'vvix', 'bsi', 'credit', 'pcr', 'skew', 'sv5_turbulence', 'fg', 'rotation', 'yield_curve', 'dxy']:
        p = FACT_STORE_DIR / f'{st}_fact_store.json'
        if p.exists():
            with open(p) as f:
                stores[st] = json.load(f)
    return stores


def classify_pattern(triad_dict):
    """Clasifica el patrón a partir de la tupla (p_bull, ev_raw) en zz25, zz50, zz75."""
    p25 = triad_dict['zz25']['p_bull']
    p50 = triad_dict['zz50']['p_bull']
    p75 = triad_dict['zz75']['p_bull']
    ev25 = triad_dict['zz25']['ev_raw']
    ev50 = triad_dict['zz50']['ev_raw']
    ev75 = triad_dict['zz75']['ev_raw']

    if p25 >= 0.53 and p50 >= 0.53 and p75 >= 0.53:
        if ev75 > ev50 > ev25:
            return 'CONVERGENCIA_BULL (Asimetría Creciente)'
        return 'CONVERGENCIA_BULL'
    elif p25 <= 0.47 and p50 <= 0.47 and p75 <= 0.47:
        return 'CONVERGENCIA_BEAR'
    elif p25 >= 0.53 and p75 <= 0.47:
        return 'DIVERGENCIA_AGOTAMIENTO (Scalp/Tactical only)'
    elif p25 <= 0.47 and p75 >= 0.53:
        return 'DIVERGENCIA_REVERSION (Pullback en Bull estructural)'
    else:
        return 'REGIMEN_MIXTO / NEUTRAL'


def compute_weighted_station_triad(sub, st, stores):
    """Calcula la tríada agregada ponderada sobre TODOS los state_keys activos de una estación."""
    col = f'{st}_sk'
    if col not in sub.columns:
        return None

    sk_counts = sub[col].dropna().value_counts()
    n_total = len(sub)
    if n_total == 0 or len(sk_counts) == 0:
        return None

    st_states = stores.get(st, {}).get('states', {})
    triad = {}

    for scale in ['zz25', 'zz50', 'zz75']:
        p_bull_w = 0.0
        emax_w = 0.0
        emin_w = 0.0
        ev_net_w = 0.0
        edays_w = 0.0
        tot_w = 0.0

        for sk, count in sk_counts.items():
            if sk in st_states and 'zigzag_kinematic' in st_states[sk]:
                zk = st_states[sk]['zigzag_kinematic'].get(scale, {})
                if zk and 'p_bull' in zk:
                    w = count / n_total
                    tot_w += w
                    p_bull_w += w * zk.get('p_bull', 0.5)
                    emax_w += w * zk.get('e_ret_max', 0.0)
                    emin_w += w * zk.get('e_ret_min', -0.02)
                    ev_net_w += w * zk.get('ev_net', 0.0)
                    edays_w += w * zk.get('e_days', 0.0)

        if tot_w > 0:
            p_bull_w /= tot_w
            emax_w /= tot_w
            emin_w /= tot_w
            ev_net_w /= tot_w
            edays_w /= tot_w

        ev_raw_w = p_bull_w * emax_w + (1.0 - p_bull_w) * emin_w
        rr_w = emax_w / abs(emin_w) if abs(emin_w) > 1e-6 else 1.0

        triad[scale] = {
            'p_bull': round(float(p_bull_w), 4),
            'e_ret_max': round(float(emax_w), 4),
            'e_ret_min': round(float(emin_w), 4),
            'ev_raw': round(float(ev_raw_w), 4),
            'ev_net': round(float(ev_net_w), 4),
            'rr_asymmetry': round(float(rr_w), 4),
            'e_days': round(float(edays_w), 1),
            'coverage': round(float(tot_w), 4),
        }

    return {
        'station': st,
        'n_distinct_sks': len(sk_counts),
        'top_sk': sk_counts.index[0],
        'top_sk_freq': round(float(sk_counts.iloc[0] / n_total), 4),
        'triad': triad,
        'pattern': classify_pattern(triad),
    }


def run():
    print('=' * 130)
    print('RECOMPUTACIÓN TRIÁDICA DINÁMICA DE SEÑALES V2.0 — PROTOCOLO C.1 & C.2 DEFINITIVO')
    print('=' * 130)

    df, spy = cargar_datos()
    stores = load_fact_stores()
    print(f'Datos cargados: {len(df)} pivotes únicos deduplicados. Fact stores: {len(stores)} estaciones.\n')

    results = []

    for name, fn in SEÑALES.items():
        meta = _CERTEZA.get(name, {})
        mask = fn(df)
        sub = df[mask]
        n_hits = len(sub)

        if n_hits == 0:
            continue

        # Confidence Tier
        if n_hits >= 30:
            tier = 'TIER_A (N≥30)'
        elif n_hits >= 10:
            tier = 'TIER_B (10-29)'
        else:
            tier = 'TIER_C (5-9)'

        # Target stations
        target_stations = SIGNAL_STATIONS.get(name, ['vix'])
        station_profiles = {}

        for st in target_stations:
            prof = compute_weighted_station_triad(sub, st, stores)
            if prof:
                station_profiles[st] = prof

        # NOTA: fwd_20d ELIMINADO (V3.4 restricción E.9).
        # Los retornos a horizonte fijo son métricas NO-CAUSALES.
        # La medición correcta es la tríada ponderada (zz25/zz50/zz75).

        results.append({
            'signal_name': name,
            'tipo': meta.get('tipo', 'entry'),
            'pivot_filter': meta.get('pivot_type', 'BOTH'),
            'n_hits': n_hits,
            'tier': tier,
            'stations': station_profiles,
        })

    # Display Institutional Table
    print(f'{"Señal":<26s} | {"Tipo":<5s} | {"N":>4s} | {"Tier":<13s} | {"Estación":<6s} | {"zz25 (p/EV/RR)":<22s} | {"zz50 (p/EV/ed)":<22s} | {"zz75 (p/EV/RR)":<22s} | {"Patrón"}')
    print('-' * 145)

    for r in results:
        sig_name = r['signal_name'][:25]
        tipo = r['tipo'][:5]
        n_str = f"{r['n_hits']:4d}"
        tier_str = r['tier'][:13]

        first = True
        for st, prof in r['stations'].items():
            t = prof['triad']
            s25 = f"{t['zz25']['p_bull']:.2f} / {t['zz25']['ev_raw']:+5.1f}% / {t['zz25']['rr_asymmetry']:3.1f}:1"
            s50 = f"{t['zz50']['p_bull']:.2f} / {t['zz50']['ev_raw']:+5.1f}% / {t['zz50']['e_days']:3.0f}d"
            s75 = f"{t['zz75']['p_bull']:.2f} / {t['zz75']['ev_raw']:+5.1f}% / {t['zz75']['rr_asymmetry']:3.1f}:1"
            pat = prof['pattern'][:30]

            if first:
                print(f"{sig_name:<26s} | {tipo:<5s} | {n_str:>4s} | {tier_str:<13s} | {st:<6s} | {s25:<22s} | {s50:<22s} | {s75:<22s} | {pat}")
                first = False
            else:
                print(f"{'':<26s} | {'':<5s} | {'':>4s} | {'':<13s} | {st:<6s} | {s25:<22s} | {s50:<22s} | {s75:<22s} | {pat}")

    # Export complete dataset
    out_file = ROOT / 'data' / 'research' / 'signals_triad_fact_sheet_v2.json'
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nFact Sheet Triádico V2 guardado exitosamente en: {out_file}')


if __name__ == '__main__':
    run()
