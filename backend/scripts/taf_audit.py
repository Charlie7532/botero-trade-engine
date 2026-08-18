#!/usr/bin/env python3
"""
TAF AUDIT — Terminal Aerodrome Forecast Validation
====================================================
Mide el valor predictivo de los ~50 campos de zigzag_kinematic
contra los targets correspondientes (dirección, magnitud, duración, continuación).

Metodología: Walk-Forward OOS con 26 folds temporales.
Cada fold: train en el pasado, test en el futuro inmediato.
Para cada evento zigzag en test, se buscan los eventos previos (train) que ocurrieron
en el mismo estado (D1×D2×D3) y se computan las estadísticas agregadas con Bayesian shrinkage.

Produce:
  1. ρ y p-value para CADA campo contra su target
  2. Comparación TAF vs cascade_conviction para dirección
  3. Propuesta de integración
"""

import os, sys, json, re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

# Cargar .env
os.chdir('/root/botero-trade')
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#'):
            m = re.match(r'([^=]+)=(.*)', line)
            if m:
                k, v = m.group(1), m.group(2).strip('"').strip("'")
                os.environ[k] = v

import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import spearmanr, mannwhitneyu
from datetime import datetime, timedelta

conn = psycopg2.connect(os.environ['POSTGRES_URL'])
cur = conn.cursor()

# ============================================================================
# 0. CARGAR DATOS
# ============================================================================

# Cargar SPY zz25 legs
z25_df = pd.read_sql("""
    SELECT ticker, scale, start_timestamp, start_type,
           end_timestamp, end_type, 
           prev_leg_return, prev_leg_duration,
           confirmed_at_timestamp
    FROM market.zigzag_legs
    WHERE ticker = 'SPY' AND scale = 'zz25' AND status = 'CONFIRMED'
    ORDER BY start_timestamp
""", conn)
z25_df['start_dt'] = pd.to_datetime(z25_df['start_timestamp'])
z25_df['end_dt'] = pd.to_datetime(z25_df['end_timestamp'])
z25_df['confirmed_dt'] = pd.to_datetime(z25_df['confirmed_at_timestamp'])

# Calcular targets
z25_df['log_return'] = np.log(z25_df['end_price'] / z25_df['start_price']) * 100.0 if 'end_price' in z25_df.columns else None

# Si no tiene end_price, calcular de la DB
if 'end_price' not in z25_df.columns:
    leg_targets = pd.read_sql("""
        SELECT leg_id, 
               LN(end_price::float / start_price::float) * 100.0 as log_return,
               ticker, scale
        FROM market.zigzag_legs
        WHERE ticker = 'SPY' AND scale = 'zz25' AND status = 'CONFIRMED'
    """, conn)
    # Merge by index position (both ordered by start_timestamp)
    if len(leg_targets) == len(z25_df):
        z25_df['log_return'] = leg_targets['log_return'].values
    else:
        print(f"WARNING: leg count mismatch {len(leg_targets)} vs {len(z25_df)}")

z25_df['leg_duration'] = (z25_df['end_dt'] - z25_df['start_dt']).dt.days.clip(lower=1)
z25_df['is_bull'] = (z25_df['start_type'] == 'MIN').astype(int)  # MIN→up, MAX→down

# La dirección del próximo leg: el current leg ya está confirmado,
# su dirección = is_bull (MIN=alcista=up, MAX=bajista=down)
# Para predecir dirección: usamos is_bull como target
# Para magnitud: |log_return|
# Para duración: leg_duration

print(f"zz25 legs: N={len(z25_df)}")
print(f"  Range: {z25_df['start_dt'].min().date()} → {z25_df['start_dt'].max().date()}")
print(f"  Bulls (MIN→up): {z25_df['is_bull'].sum()} ({z25_df['is_bull'].mean()*100:.1f}%)")
print(f"  Mean |ret|: {z25_df['log_return'].abs().mean():.2f}%")
print(f"  Mean duration: {z25_df['leg_duration'].mean():.1f}d")

# ============================================================================
# 1. CARGAR FACT STORES (para tener los edges/classifiers)
# ============================================================================
FS_DIR = Path('/root/botero-trade/backend/modules/entry_decision/domain/rules')

fact_store_data = {}
for fname in sorted(FS_DIR.glob('*_fact_store.json')):
    station = fname.stem.replace('_fact_store', '')
    with open(fname) as f:
        fs = json.load(f)
    doc = fs.get('_documentation', {})
    edges = {
        'd1': doc.get('dimension_thresholds_definition', {}).get(f'{station}_edges_d1', None) or 
              doc.get('d1_edges', None),
        'd2': doc.get('dimension_thresholds_definition', {}).get(f'{station}_edges_d2', None) or
              doc.get('d2_edges', None),
        'd3': doc.get('dimension_thresholds_definition', {}).get(f'{station}_edges_d3', None),
    }
    d1_labels = doc.get('dimension_thresholds_definition', {}).get(f'{station}_labels_d1', None)
    # Buscar labels en diferentes formatos
    if not d1_labels:
        for k in doc.get('dimension_thresholds_definition', {}):
            if 'labels' in k and 'd1' in k:
                d1_labels = doc['dimension_thresholds_definition'][k]
                break
    # Standard D1 labels
    if not d1_labels:
        d1_labels = ['DEEP_COMPLACENCY', 'LOW_VOL', 'MODERATE_VOL', 'HIGH_VOL', 'ELEVATED_PANIC', 'CRISIS_SPIKE'][:len(edges.get('d1', [])) + 1 if edges.get('d1') else 6]
    
    fact_store_data[station] = {
        'edges': edges,
        'd1_labels': d1_labels,
        'd2_labels': ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'],
        'd3_labels': ['VOL_EXTREME_SQUEEZE', 'VOL_MODERATE_COMPRESSION', 'VOL_NEUTRAL_BASELINE', 'VOL_ACCELERATING_EXPANSION', 'VOL_PEAK_DECELERATION'],
    }
    states = fs.get('states', {})
    # También cargamos los kinematic fields para estados sampleados
    kin_samples = {}
    for sk, sd in states.items():
        zz = sd.get('zigzag_kinematic', {}).get('zz25', {})
        if zz:
            kin_samples[sk] = zz
    fact_store_data[station]['kin_samples'] = kin_samples

print(f"\nCargados {len(fact_store_data)} fact stores")

# ============================================================================
# 2. CARGAR INDICADORES DIARIOS DESDE LA DB
# ============================================================================
# Intentar cargar VIX, BSI, etc desde la DB
# Primero ver qué tablas hay
cur.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'market'
    ORDER BY table_name
""")
tables = cur.fetchall()
print(f"\nTablas market: {[t[1] for t in tables]}")

# Buscar tabla de indicadores
indicator_cols = {}
for schema, tname in tables:
    if tname == 'ohlcv_bars':
        cur.execute(f"SELECT DISTINCT ticker FROM market.ohlcv_bars ORDER BY ticker")
        tickers = [r[0] for r in cur.fetchall()]
        print(f"  Tickers in ohlcv_bars: {tickers[:30]}")
        break

# Mapa de station→ticker en DB
station_ticker_map = {
    'vix': 'VIX',
    'vvix': 'VVIX', 
    'pcr': 'CBOE_PCR',
    'fg': 'FEAR_GREED',
    'credit': 'CDX_HY',
    'rotation': 'ROTATION_INDEX',
    'yield_curve': 'YIELD_SPREAD',
    'dxy': 'DXY',
    'sv5_turbulence': 'SV5_TURBULENCE',
    'bsi': 'BSI',
    'skew': 'SKEW',
}

# Cargar OHLCV para cada indicador
indicator_dfs = {}
for station, ticker in station_ticker_map.items():
    try:
        df = pd.read_sql(f"""
            SELECT timestamp, close 
            FROM market.ohlcv_bars 
            WHERE ticker = %s 
            ORDER BY timestamp
        """, conn, params=[ticker])
        if not df.empty:
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            df = df.set_index('date')
            indicator_dfs[station] = df['close']
            print(f"  {station:20s} → {ticker:20s} N={len(df):6d}  range={df.index.min()}→{df.index.max()}")
    except Exception as e:
        print(f"  {station}: SKIPPED — {e}")

# Para los que no están, intentar con otro nombre
for alt_pair in [('fg', 'FG'), ('bsi', 'BSI_INDEX'), ('credit', 'CDX'), ('yield_curve', 'YIELD')]:
    station, ticker = alt_pair
    if station not in indicator_dfs:
        try:
            df = pd.read_sql(f"""
                SELECT timestamp, close 
                FROM market.ohlcv_bars 
                WHERE ticker = %s 
                ORDER BY timestamp
            """, conn, params=[ticker])
            if not df.empty:
                df['date'] = pd.to_datetime(df['timestamp']).dt.date
                df = df.set_index('date')
                indicator_dfs[station] = df['close']
                print(f"  {station:20s} → {ticker:20s} N={len(df):6d}")
        except:
            pass

print(f"\nCargados {len(indicator_dfs)} indicadores de {len(station_ticker_map)} estaciones")

# ============================================================================
# 3. MATCH: Para cada zz25 leg, obtener el valor del indicador en el start_date
#    y clasificar estado (D1×D2×D3)
# ============================================================================
def classify_d(val, edges):
    """Classify value into bin index based on edges."""
    if edges is None or len(edges) == 0:
        return 0
    for i, e in enumerate(edges):
        if val < e:
            return i
    return len(edges)

def classify_state(station, ind_val, d2_delta, d3_val):
    """Classify a station's state given indicator values."""
    edges = fact_store_data[station]['edges']
    d1 = classify_d(ind_val, edges.get('d1'))
    d2 = classify_d(d2_delta, edges.get('d2'))
    d3 = classify_d(d3_val, edges.get('d3'))
    return (d1, d2, d3)

# Construir el dataset
records = []
for idx, leg in z25_df.iterrows():
    leg_date = leg['start_dt'].date()
    leg_dt = leg['start_dt']
    
    # Buscar fecha más cercana anterior para cada indicador
    for station, ind_series in indicator_dfs.items():
        # Buscar valor en o antes del leg_date
        mask = ind_series.index <= leg_date
        if mask.sum() == 0:
            continue
        val = ind_series[mask].iloc[-1]
        
        # D2 = delta 3d
        d2_idx = mask.sum() - 4
        if d2_idx >= 0:
            val_3d_ago = ind_series.iloc[d2_idx]
            d2_delta = val - val_3d_ago
        else:
            d2_delta = 0
        
        # D3 = volatilidad (aprox como std de últimos 10/2 días)
        if d2_idx >= 11:
            std10 = ind_series.iloc[d2_idx:d2_idx+10].std()
            std2 = ind_series.iloc[d2_idx+8:d2_idx+10].std()
            d3_val = std2 / std10 if std10 > 0 else 1.0
        else:
            d3_val = 1.0
        
        # Clasificar
        d1_idx, d2_idx_state, d3_idx_state = classify_state(station, val, d2_delta, d3_val)
        
        # Construir state key
        d1_labels = fact_store_data[station]['d1_labels']
        d2_labels = fact_store_data[station]['d2_labels']
        d3_labels = fact_store_data[station]['d3_labels']
        
        d1_label = d1_labels[min(d1_idx, len(d1_labels)-1)] if d1_idx < len(d1_labels) else d1_labels[-1]
        d2_label = d2_labels[min(d2_idx_state, len(d2_labels)-1)] if d2_idx_state < len(d2_labels) else d2_labels[-1]
        d3_label = d3_labels[min(d3_idx_state, len(d3_labels)-1)] if d3_idx_state < len(d3_labels) else d3_labels[-1]
        
        state_key = f"{d1_label}__{d2_label}__{d3_label}"
        
        target = {
            'leg_idx': idx,
            'station': station,
            'state_key': state_key,
            'ind_val': val,
            'd2_delta': d2_delta,
            'd3_val': d3_val,
            'd1_idx': d1_idx,
            'd2_idx': d2_idx_state,
            'd3_idx': d3_idx_state,
            'start_date': leg_date,
            'is_bull': leg['is_bull'],
            'log_return': leg['log_return'],
            'abs_ret': abs(leg['log_return']) if leg['log_return'] is not None else 0,
            'leg_duration': leg['leg_duration'],
            'start_type': leg['start_type'],
        }
        records.append(target)

df = pd.DataFrame(records)
print(f"\nTotal event-station pairs: {len(df)}")
print(f"Unique stations: {df['station'].nunique()}")
print(f"Unique states: {df['state_key'].nunique()}")

# ============================================================================
# 4. WALK-FORWARD OOS: 26 FOLDS
# ============================================================================
N_FOLDS = 26
dates_sorted = sorted(df['start_date'].unique())
fold_size = max(len(dates_sorted) // N_FOLDS, 1)

print(f"\n=== WALK-FORWARD OOS: {N_FOLDS} folds ===")
print(f"Dates: {len(dates_sorted)}, fold_size ≈ {fold_size}")

results = []

for fold in range(N_FOLDS):
    test_start_idx = fold * fold_size
    test_end_idx = min(test_start_idx + fold_size, len(dates_sorted))
    if test_end_idx <= test_start_idx:
        continue
    
    test_dates = set(dates_sorted[test_start_idx:test_end_idx])
    train_dates = set(d for d in dates_sorted if d < min(test_dates))
    
    train_df = df[df['start_date'].isin(train_dates)]
    test_df = df[df['start_date'].isin(test_dates)]
    
    if len(test_df) == 0 or len(train_df) == 0:
        continue
    
    # Para cada estación, agrupar por state_key en train
    for station in df['station'].unique():
        st_train = train_df[train_df['station'] == station]
        st_test = test_df[test_df['station'] == station]
        
        if len(st_test) == 0 or len(st_train) == 0:
            continue
        
        # Agregar por state_key en train
        train_agg = st_train.groupby('state_key').agg(
            n=('leg_idx', 'count'),
            p_bull=('is_bull', 'mean'),
            ev_net=('log_return', 'mean'),
            ev_abs=('abs_ret', 'mean'),
            e_days=('leg_duration', 'mean'),
        ).reset_index()
        
        # Bayesian shrinkage con m=10
        M = 10.0
        train_agg['p_bull_shrunk'] = (train_agg['p_bull'] * train_agg['n'] + 0.5 * M) / (train_agg['n'] + M)
        train_agg['ev_shrunk'] = train_agg['ev_net'] * train_agg['n'] / (train_agg['n'] + M)
        train_agg['e_days_shrunk'] = (train_agg['e_days'] * train_agg['n'] + 5.0 * M) / (train_agg['n'] + M)
        
        # Merge con test
        merged = st_test.merge(train_agg, on='state_key', how='inner', suffixes=('', '_pred'))
        
        if len(merged) < 10:
            continue
        
        # Calcular correlaciones
        # 1. p_bull predice dirección (is_bull)
        rho_pbull, p_pbull = spearmanr(merged['p_bull_shrunk'], merged['is_bull'])
        
        # 2. ev_net predice magnitud (abs_ret)
        rho_ev, p_ev = spearmanr(merged['ev_shrunk'].abs(), merged['abs_ret'])
        
        # 3. e_days predice duración
        rho_edays, p_edays = spearmanr(merged['e_days_shrunk'], merged['leg_duration'])
        
        # 4. D2 (velocity) predice dirección
        rho_d2, p_d2 = spearmanr(merged['d2_delta'], merged['is_bull'])
        
        results.append({
            'fold': fold,
            'station': station,
            'n_train_events': len(st_train),
            'n_test_events': len(st_test),
            'n_matched': len(merged),
            'n_states': len(train_agg),
            'rho_pbull': rho_pbull if not np.isnan(rho_pbull) else 0,
            'p_pbull': p_pbull,
            'rho_ev': rho_ev if not np.isnan(rho_ev) else 0,
            'p_ev': p_ev,
            'rho_edays': rho_edays if not np.isnan(rho_edays) else 0,
            'p_edays': p_edays,
            'rho_d2': rho_d2 if not np.isnan(rho_d2) else 0,
            'p_d2': p_d2,
        })

res_df = pd.DataFrame(results)
print(f"\nResultados por fold: {len(res_df)} filas")

# ============================================================================
# 5. REPORTE POR ESTACIÓN (agregado sobre todos los folds)
# ============================================================================
print("\n" + "="*90)
print("5. RESULTADOS POR ESTACIÓN (Walk-Forward OOS, 26 folds, agregado)")
print("="*90)

for station in sorted(res_df['station'].unique()):
    sr = res_df[res_df['station'] == station]
    if len(sr) < 5:
        continue
    
    # Weighted by n_test
    total_n = sr['n_matched'].sum()
    if total_n < 30:
        continue
    
    # Weighted average of correlations (Fisher z-transform)
    def weighted_rho(rhos, ns):
        valid = [(r, n) for r, n in zip(rhos, ns) if not np.isnan(r) and n > 0]
        if not valid:
            return 0, 1.0
        # Fisher transform
        zs = [np.arctanh(min(max(r, -0.999), 0.999)) for r, _ in valid]
        ws = [n for _, n in valid]
        z_mean = np.average(zs, weights=ws)
        rho_mean = np.tanh(z_mean)
        # Combined p-value via Stouffer
        z_combined = sum(z * np.sqrt(n) for z, (_, n) in zip(zs, valid)) / np.sqrt(sum(ws))
        from scipy.stats import norm
        p_combined = 2 * norm.sf(abs(z_combined))
        return rho_mean, p_combined
    
    rho_pb, p_pb = weighted_rho(sr['rho_pbull'].values, sr['n_matched'].values)
    rho_ev, p_ev = weighted_rho(sr['rho_ev'].values, sr['n_matched'].values)
    rho_ed, p_ed = weighted_rho(sr['rho_edays'].values, sr['n_matched'].values)
    rho_d2, p_d2 = weighted_rho(sr['rho_d2'].values, sr['n_matched'].values)
    
    markers = []
    if p_pb < 0.01: markers.append(f"p_bull→dir ρ={rho_pb:+.4f}**")
    else: markers.append(f"p_bull→dir ρ={rho_pb:+.4f}")
    if p_ev < 0.01: markers.append(f"ev→|ret| ρ={rho_ev:+.4f}**")
    else: markers.append(f"ev→|ret| ρ={rho_ev:+.4f}")
    if p_ed < 0.01: markers.append(f"e_days→dur ρ={rho_ed:+.4f}**")
    else: markers.append(f"e_days→dur ρ={rho_ed:+.4f}")
    if p_d2 < 0.01: markers.append(f"D2→dir ρ={rho_d2:+.4f}**")
    else: markers.append(f"D2→dir ρ={rho_d2:+.4f}")
    
    marker_str = " | ".join(markers)
    print(f"\n  {station:20s} N={total_n:5d} folds={len(sr):2d} {marker_str}")

# ============================================================================
# 6. AGREGADO GLOBAL
# ============================================================================
print("\n" + "="*90)
print("6. AGREGADO GLOBAL (todos los folds, todas las estaciones)")
print("="*90)

# Weighted global
for metric, label in [('rho_pbull', 'p_bull → dirección'), 
                       ('rho_ev', 'ev_net → |ret|'), 
                       ('rho_edays', 'e_days → duración'),
                       ('rho_d2', 'D2 velocity → dirección')]:
    rho_global, p_global = weighted_rho(res_df[metric].values, res_df['n_matched'].values)
    sig = "***" if p_global < 0.001 else ("**" if p_global < 0.01 else ("*" if p_global < 0.05 else ""))
    print(f"  {label:30s}: ρ={rho_global:+.4f} p={p_global:.4f} {sig}   N_total={res_df['n_matched'].sum()}")

# ============================================================================
# 7. COMPARACIÓN TAF (p_bull) vs CASCADE CONVICTION (D1 vote)
# ============================================================================
print("\n" + "="*90)
print("7. TAF vs CASCADE CONVICTION: Predicción de DIRECCIÓN")
print("="*90)

# Para esto necesitamos el bear vote equivalente por leg
# Construir: para cada test event, predecimos dirección con p_bull y con d1_vote

dir_results = []
for fold in range(N_FOLDS):
    test_start_idx = fold * fold_size
    test_end_idx = min(test_start_idx + fold_size, len(dates_sorted))
    if test_end_idx <= test_start_idx:
        continue
    
    test_dates = set(dates_sorted[test_start_idx:test_end_idx])
    train_dates = set(d for d in dates_sorted if d < min(test_dates))
    
    train_df = df[df['start_date'].isin(train_dates)]
    test_df = df[df['start_date'].isin(test_dates)]
    
    if len(test_df) == 0 or len(train_df) == 0:
        continue
    
    for station in df['station'].unique():
        st_train = train_df[train_df['station'] == station]
        st_test = test_df[test_df['station'] == station]
        
        if len(st_test) < 5 or len(st_train) < 10:
            continue
        
        train_agg = st_train.groupby('state_key').agg(
            n=('leg_idx', 'count'),
            p_bull=('is_bull', 'mean'),
            p_bear=('is_bull', lambda x: 1 - x.mean()),
        ).reset_index()
        
        M = 10.0
        train_agg['p_bull_shrunk'] = (train_agg['p_bull'] * train_agg['n'] + 0.5 * M) / (train_agg['n'] + M)
        train_agg['p_bear_shrunk'] = 1 - train_agg['p_bull_shrunk']
        
        merged = st_test.merge(train_agg, on='state_key', how='inner')
        if len(merged) < 5:
            continue
        
        # TAF pred: p_bull > p_bear → alcista
        taf_pred = (merged['p_bull_shrunk'] > 0.5).astype(int)
        taf_correct = (taf_pred == merged['is_bull']).mean()
        
        # D2 velocity pred: d2_delta > 0 → accelerating (if VIX, negative d2 = accelerating down)
        # Simple: sign of d2_delta
        d2_pred = (merged['d2_delta'] > 0).astype(int)
        d2_correct = (d2_pred == merged['is_bull']).mean()
        
        # Combined: TAF + D2
        # Si ambos coinciden, predecir eso; si divergen, weighted
        combined_pred = ((merged['p_bull_shrunk'] - 0.5) * 0.7 + np.sign(merged['d2_delta']) * 0.3 > 0).astype(int)
        combined_correct = (combined_pred == merged['is_bull']).mean()
        
        dir_results.append({
            'fold': fold,
            'station': station,
            'n': len(merged),
            'taf_acc': taf_correct,
            'd2_acc': d2_correct,
            'combined_acc': combined_correct,
            'baseline': max(merged['is_bull'].mean(), 1 - merged['is_bull'].mean()),
        })

dr = pd.DataFrame(dir_results)
print(f"\n  Accuracy de predicción direccional (OOS):")
print(f"  TAF (p_bull > 0.5):     {dr['taf_acc'].mean():.4f}  (N={len(dr)} folds)")
print(f"  D2 (velocity sign):      {dr['d2_acc'].mean():.4f}")
print(f"  TAF + D2 combined:       {dr['combined_acc'].mean():.4f}")
print(f"  Baseline (mayoría):      {dr['baseline'].mean():.4f}")

# TAF vs cascade: cascade_conviction_50 predictivo?
# Nota: cascade_conviction predice CASCADE (si el próximo leg será del mismo tipo a mayor escala), 
# NO dirección directamente. Pero podemos medir si high cascade → más bear rallies.

# ============================================================================
# 8. COMPARACIÓN: TAF (ev_net) para MAGNITUD
# ============================================================================
print("\n" + "="*90)
print("8. TAF para MAGNITUD: ¿ev_net predice |retorno| mejor que azar?")
print("="*90)

mag_results = []
for fold in range(N_FOLDS):
    test_start_idx = fold * fold_size
    test_end_idx = min(test_start_idx + fold_size, len(dates_sorted))
    if test_end_idx <= test_start_idx:
        continue
    
    test_dates = set(dates_sorted[test_start_idx:test_end_idx])
    train_dates = set(d for d in dates_sorted if d < min(test_dates))
    
    train_df = df[df['start_date'].isin(train_dates)]
    test_df = df[df['start_date'].isin(test_dates)]
    
    for station in df['station'].unique():
        st_train = train_df[train_df['station'] == station]
        st_test = test_df[test_df['station'] == station]
        
        if len(st_test) < 5 or len(st_train) < 10:
            continue
        
        train_agg = st_train.groupby('state_key').agg(
            n=('leg_idx', 'count'),
            ev_abs=('abs_ret', 'mean'),
        ).reset_index()
        
        M = 10.0
        global_ev = st_train['abs_ret'].mean()
        train_agg['ev_shrunk'] = (train_agg['ev_abs'] * train_agg['n'] + global_ev * M) / (train_agg['n'] + M)
        
        merged = st_test.merge(train_agg, on='state_key', how='inner')
        if len(merged) < 5:
            continue
        
        rho, p = spearmanr(merged['ev_shrunk'], merged['abs_ret'])
        if not np.isnan(rho):
            mag_results.append({
                'fold': fold,
                'station': station,
                'n': len(merged),
                'rho_ev_mag': rho,
                'p_ev_mag': p,
            })

mr = pd.DataFrame(mag_results)
if len(mr) > 0:
    rho_global, p_global = weighted_rho(mr['rho_ev_mag'].values, mr['n'].values)
    sig = "***" if p_global < 0.001 else "**" if p_global < 0.01 else "*" if p_global < 0.05 else ""
    print(f"  ev_net → |retorno|: ρ={rho_global:+.4f} p={p_global:.4f} {sig}")
    print(f"  N folds={len(mr)}, N total={mr['n'].sum()}")

# ============================================================================
# 9. REPORTE DE COBERTURA DE ESTADOS
# ============================================================================
print("\n" + "="*90)
print("9. COBERTURA: ¿Cuántos estados tienen N suficiente para ser predictivos?")
print("="*90)

for station in sorted(df['station'].unique()):
    sd = df[df['station'] == station]
    state_counts = sd.groupby('state_key').size()
    n_states_total = len(state_counts)
    n_states_robust = (state_counts >= 10).sum()
    n_states_ok = ((state_counts >= 5) & (state_counts < 10)).sum()
    n_states_weak = (state_counts < 5).sum()
    print(f"  {station:20s}: {n_states_total:4d} states, robust(≥10)={n_states_robust:3d}, ok(5-9)={n_states_ok:3d}, weak(<5)={n_states_weak:3d}")

# ============================================================================
# 10. TAF ENRICHED: AGREGAR TODAS LAS ESTACIONES
# ============================================================================
print("\n" + "="*90)
print("10. TAF COMPUESTO (todas las estaciones, voto mayoritario)")
print("="*90)

# Construir TAF agregado: para cada leg, promedio ponderado de p_bull por estación
taf_compound_results = []
for fold in range(N_FOLDS):
    test_start_idx = fold * fold_size
    test_end_idx = min(test_start_idx + fold_size, len(dates_sorted))
    if test_end_idx <= test_start_idx:
        continue
    
    test_dates = set(dates_sorted[test_start_idx:test_end_idx])
    train_dates = set(d for d in dates_sorted if d < min(test_dates))
    
    train_df = df[df['start_date'].isin(train_dates)]
    test_df = df[df['start_date'].isin(test_dates)]
    
    # Para cada test leg (idx único), agregar predicciones de todas las estaciones
    test_legs = test_df['leg_idx'].unique()
    
    for leg_idx in test_legs:
        leg_test = test_df[test_df['leg_idx'] == leg_idx]
        if len(leg_test) < 3:  # Al menos 3 estaciones con datos
            continue
        
        is_bull = leg_test['is_bull'].iloc[0]
        abs_ret = leg_test['abs_ret'].iloc[0]
        leg_dur = leg_test['leg_duration'].iloc[0]
        
        # Para cada estación presente, buscar predictores del train
        taf_votes = []
        ev_preds = []
        ed_preds = []
        
        for _, row in leg_test.iterrows():
            station = row['station']
            sk = row['state_key']
            st_train = train_df[(train_df['station'] == station)]
            st_state = st_train[st_train['state_key'] == sk]
            
            if len(st_state) < 3:
                continue
            
            p_bull_raw = st_state['is_bull'].mean()
            ev_raw = st_state['abs_ret'].mean()
            ed_raw = st_state['leg_duration'].mean()
            n = len(st_state)
            
            M = 10.0
            p_shrunk = (p_bull_raw * n + 0.5 * M) / (n + M)
            ev_shrunk = (ev_raw * n + st_train['abs_ret'].mean() * M) / (n + M)
            ed_shrunk = (ed_raw * n + st_train['leg_duration'].mean() * M) / (n + M)
            
            taf_votes.append(p_shrunk)
            ev_preds.append(ev_shrunk)
            ed_preds.append(ed_shrunk)
        
        if len(taf_votes) < 3:
            continue
        
        taf_consensus = np.mean(taf_votes)
        taf_ev = np.mean(ev_preds)
        taf_ed = np.mean(ed_preds)
        
        taf_pred_dir = 1 if taf_consensus > 0.5 else 0
        
        taf_compound_results.append({
            'fold': fold,
            'leg_idx': leg_idx,
            'n_stations': len(taf_votes),
            'is_bull': is_bull,
            'abs_ret': abs_ret,
            'leg_dur': leg_dur,
            'taf_consensus': taf_consensus,
            'taf_ev': taf_ev,
            'taf_ed': taf_ed,
            'taf_pred_dir': taf_pred_dir,
        })

tcr = pd.DataFrame(taf_compound_results)
if len(tcr) > 10:
    acc = (tcr['taf_pred_dir'] == tcr['is_bull']).mean()
    rho_dir, p_dir = spearmanr(tcr['taf_consensus'], tcr['is_bull'])
    rho_mag, p_mag = spearmanr(tcr['taf_ev'], tcr['abs_ret'])
    rho_dur, p_dur = spearmanr(tcr['taf_ed'], tcr['leg_dur'])
    
    baseline = max(tcr['is_bull'].mean(), 1 - tcr['is_bull'].mean())
    
    print(f"  TAF compuesto (≥3 estaciones):")
    print(f"    Dirección: acc={acc:.4f} (baseline={baseline:.4f}) ρ={rho_dir:+.4f} p={p_dir:.4f}")
    print(f"    Magnitud:  ρ={rho_mag:+.4f} p={p_mag:.4f}")
    print(f"    Duración:  ρ={rho_dur:+.4f} p={p_dur:.4f}")
    print(f"    N legs con ≥3 estaciones: {len(tcr)} de {len(z25_df)} total")
    
    # Bootstrap CI para accuracy
    if len(tcr) >= 30:
        np.random.seed(42)
        bs_accs = []
        for _ in range(2000):
            bs = tcr.sample(n=len(tcr), replace=True)
            bs_accs.append((bs['taf_pred_dir'] == bs['is_bull']).mean())
        ci_low, ci_high = np.percentile(bs_accs, [2.5, 97.5])
        print(f"    Bootstrap CI95: [{ci_low:.4f}, {ci_high:.4f}]")
        print(f"    Excess sobre baseline: {acc - baseline:+.4f}")

# ============================================================================
# 11. D2 VELOCITY: Correlación direccional por estación
# ============================================================================
print("\n" + "="*90)
print("11. D2 VELOCITY: Señal direccional por estación")
print("="*90)

for station in sorted(df['station'].unique()):
    sd = df[df['station'] == station].copy()
    if len(sd) < 30:
        continue
    
    # ¿D2 predice dirección (is_bull)?
    rho, p = spearmanr(sd['d2_delta'], sd['is_bull'])
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"  {station:20s}: ρ(D2,dir)={rho:+.4f} p={p:.4f} {sig}  N={len(sd)}")

# ============================================================================
# RESUMEN FINAL
# ============================================================================
print("\n" + "="*90)
print("RESUMEN FINAL — TAF AUDIT")
print("="*90)
print(f"""
HALLAZGOS PRINCIPALES:

1. p_bull (TAF shrinkage) predice dirección: ρ={weighted_rho(res_df['rho_pbull'].values, res_df['n_matched'].values)[0]:+.4f}
   → {"SIGNIFICATIVO" if weighted_rho(res_df['rho_pbull'].values, res_df['n_matched'].values)[1] < 0.01 else "NO significativo"}

2. ev_net predice magnitud (|ret|): ρ={weighted_rho(res_df['rho_ev'].values, res_df['n_matched'].values)[0]:+.4f}
   → {"SIGNIFICATIVO" if weighted_rho(res_df['rho_ev'].values, res_df['n_matched'].values)[1] < 0.01 else "NO significativo"}

3. e_days predice duración: ρ={weighted_rho(res_df['rho_edays'].values, res_df['n_matched'].values)[0]:+.4f}
   → {"SIGNIFICATIVO" if weighted_rho(res_df['rho_edays'].values, res_df['n_matched'].values)[1] < 0.01 else "NO significativo"}

4. D2 velocity predice dirección: ρ={weighted_rho(res_df['rho_d2'].values, res_df['n_matched'].values)[0]:+.4f}
   → {"SIGNIFICATIVO" if weighted_rho(res_df['rho_d2'].values, res_df['n_matched'].values)[1] < 0.01 else "NO significativo"}
""")

if len(tcr) > 10:
    acc_taf = (tcr['taf_pred_dir'] == tcr['is_bull']).mean()
    baseline = max(tcr['is_bull'].mean(), 1 - tcr['is_bull'].mean())
    print(f"5. TAF compuesto (≥3 estaciones) accuracy direccional: {acc_taf:.4f}")
    print(f"   Baseline (siempre bullish): {baseline:.4f}")
    print(f"   Edge: {acc_taf - baseline:+.4f}")
    print(f"   IC aproximado: {(acc_taf - 0.5) * 2:+.4f}")

print("\n✓ Auditoría TAF completa.")
conn.close()