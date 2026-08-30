#!/usr/bin/env python3
"""Recomputación Triádica Dinámica de Señales Entry/Exit — Protocolo C.1 & C.2.

Para cada una de las 28+3 señales del arnés:
1. Evalúa las fechas de disparo sobre quants_obs.pkl (1,354 pivotes únicos deduplicados).
2. Extrae los state_keys activos en las estaciones involucradas.
3. Cruza dinámicamente con los Fact Stores JSON correspondientes.
4. Extrae la tríada estocástica: zz25 (2.5%), zz50 (5.0%), zz75 (7.5%):
   - p_bull (probabilidad bayesiana)
   - e_ret_max (retorno medio pierna alcista)
   - e_ret_min (retorno medio pierna bajista)
   - EV_raw = p_bull * e_ret_max + (1-p_bull) * e_ret_min
   - ev_net (EV bayesiano regularizado)
   - R:R = |e_ret_max| / |e_ret_min|
   - e_days (horizonte natural estocástico)
5. Clasifica el PATRÓN INTER-ESCALA (Convergencia, Divergencia, Asimetría).
6. Genera el Fact Sheet Institucional Definitivo.
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
import arnes.señales  # registers all 28 signals

FACT_STORE_DIR = ROOT / 'backend' / 'modules' / 'entry_decision' / 'domain/rules'

STATIONS = [
    'vix', 'vvix', 'bsi', 'credit', 'pcr', 'skew',
    'sv5_turbulence', 'fg', 'rotation', 'yield_curve', 'dxy'
]


def load_fact_stores():
    stores = {}
    for st in STATIONS:
        p = FACT_STORE_DIR / f'{st}_fact_store.json'
        if p.exists():
            with open(p) as f:
                stores[st] = json.load(f)
    return stores


def classify_interscale_pattern(zk):
    """Clasifica el patrón inter-escala a partir de zz25, zz50, zz75."""
    p25 = zk.get('zz25', {}).get('p_bull')
    p50 = zk.get('zz50', {}).get('p_bull')
    p75 = zk.get('zz75', {}).get('p_bull')
    
    ev25 = zk.get('zz25', {}).get('ev_raw')
    ev50 = zk.get('zz50', {}).get('ev_raw')
    ev75 = zk.get('zz75', {}).get('ev_raw')
    
    if p25 is None or p50 is None or p75 is None:
        return 'INCOMPLETO'

    if p25 >= 0.55 and p50 >= 0.55 and p75 >= 0.55:
        if ev75 > ev50 > ev25:
            return 'CONVERGENCIA_BULL (Asimetría Creciente)'
        return 'CONVERGENCIA_BULL'
    elif p25 <= 0.45 and p50 <= 0.45 and p75 <= 0.45:
        return 'CONVERGENCIA_BEAR'
    elif p25 >= 0.55 and p75 <= 0.48:
        return 'DIVERGENCIA_AGOTAMIENTO (Scalp/Tactical only)'
    elif p25 <= 0.48 and p75 >= 0.55:
        return 'DIVERGENCIA_REVERSION (Pullback en Bull estructural)'
    else:
        return 'REGIMEN_MIXTO / NEUTRAL'


def run():
    print('=' * 110)
    print('RECOMPUTACIÓN TRIÁDICA DINÁMICA DE SEÑALES ENTRY/EXIT — PROTOCOLO C.1 & C.2')
    print('=' * 110)

    df, spy = cargar_datos()
    stores = load_fact_stores()
    print(f'Datos cargados: {len(df)} pivotes únicos. Fact stores cargados: {len(stores)} estaciones.')

    # Signals evaluation
    signal_results = []

    for name, fn in SEÑALES.items():
        meta = _CERTEZA.get(name, {})
        mask = fn(df)
        sub = df[mask]
        n_hits = len(sub)
        
        if n_hits == 0:
            continue

        # Find which stations are primary for this signal
        # Check active state_keys in sub
        station_metrics = {}
        for st in STATIONS:
            col = f'{st}_sk'
            if col in sub.columns:
                active_sks = sub[col].dropna().value_counts()
                if len(active_sks) > 0:
                    top_sk = active_sks.index[0]
                    top_freq = active_sks.iloc[0] / len(sub)
                    station_metrics[st] = (top_sk, top_freq)

        # Pick the most concentrated / characteristic station
        primary_station = None
        primary_sk = None
        best_concentration = -1.0
        
        # Explicit priority overrides based on signal domain
        for st in ['credit', 'vix', 'vvix', 'bsi', 'skew', 'pcr', 'fg', 'sv5_turbulence', 'rotation', 'yield_curve', 'dxy']:
            if st in name:
                primary_station = st
                if st in station_metrics:
                    primary_sk = station_metrics[st][0]
                break
        
        if not primary_station and station_metrics:
            for st, (sk, freq) in station_metrics.items():
                if freq > best_concentration:
                    best_concentration = freq
                    primary_station = st
                    primary_sk = sk

        # Extract triadic data from the fact store
        zk_data = {}
        if primary_station and primary_station in stores and primary_sk:
            st_states = stores[primary_station].get('states', {})
            st_obj = st_states.get(primary_sk, {})
            zk_obj = st_obj.get('zigzag_kinematic', {})
            
            for scale in ['zz25', 'zz50', 'zz75']:
                d = zk_obj.get(scale, {})
                if d and 'p_bull' in d:
                    pb = d['p_bull']
                    emax = d.get('e_ret_max', 0.0)
                    emin = d.get('e_ret_min', -0.02)
                    ev_net = d.get('ev_net', 0.0)
                    edays = d.get('e_days', 0.0)
                    rr = d.get('rr_asymmetry', 1.0)
                    
                    ev_raw = pb * emax + (1.0 - pb) * emin
                    
                    zk_data[scale] = {
                        'p_bull': pb,
                        'e_ret_max': emax,
                        'e_ret_min': emin,
                        'ev_raw': ev_raw,
                        'ev_net': ev_net,
                        'e_days': edays,
                        'rr_asymmetry': rr,
                    }

        pattern = classify_interscale_pattern(zk_data)

        # Baseline empirical returns in df (provisional reference)
        fwd20 = sub['fwd_20d'].mean() if 'fwd_20d' in sub.columns else 0.0
        wr20 = (sub['fwd_20d'] > 0).mean() if 'fwd_20d' in sub.columns else 0.0

        signal_results.append({
            'signal_name': name,
            'tipo': meta.get('tipo', 'entry'),
            'pivot_type_filter': meta.get('pivot_type', 'BOTH'),
            'n_hits': n_hits,
            'primary_station': primary_station,
            'primary_sk': primary_sk,
            'pattern': pattern,
            'wr20_prov': wr20,
            'fwd20_prov': fwd20,
            'zk': zk_data,
        })

    # Display results
    print('\n' + '=' * 140)
    print(f'{"Señal":<26s} | {"Tipo":<5s} | {"N":>4s} | {"Estación Primaria":<12s} | {"zz25 p/ev/RR":<22s} | {"zz50 p/ev/e_d":<22s} | {"zz75 p/ev/RR":<22s} | {"Patrón Inter-Escala"}')
    print('-' * 140)

    for r in signal_results:
        zk = r['zk']
        
        def fmt_scale(sc_name):
            d = zk.get(sc_name, {})
            if not d:
                return "N/A"
            pb = d['p_bull']
            evr = d['ev_raw']
            rr = d.get('rr_asymmetry', 0)
            ed = d.get('e_days', 0)
            if sc_name == 'zz50':
                return f"{pb:.2f} / {evr:+5.1f}% / {ed:.0f}d"
            return f"{pb:.2f} / {evr:+5.1f}% / {rr:.1f}:1"

        s25 = fmt_scale('zz25')
        s50 = fmt_scale('zz50')
        s75 = fmt_scale('zz75')
        
        sig_str = r['signal_name'][:25]
        st_str = (r['primary_station'] or 'N/A')[:12]
        pat_str = r['pattern'][:35]
        
        print(f"{sig_str:<26s} | {r['tipo']:<5s} | {r['n_hits']:4d} | {st_str:<12s} | {s25:<22s} | {s50:<22s} | {s75:<22s} | {pat_str}")

    # Export to JSON
    out_path = ROOT / 'data' / 'research' / 'signals_triad_fact_sheet.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(signal_results, f, indent=2)
    print(f'\nFact Sheet de Señales guardado exitosamente en: {out_path}')


if __name__ == '__main__':
    run()
