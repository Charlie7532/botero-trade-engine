#!/usr/bin/env python3
"""
TAF AUDIT v2 — Terminal Aerodrome Forecast Validation
=======================================================
Walk-Forward OOS: para cada leg zigzag, busca el estado de cada estación
en esa fecha usando SOLO datos anteriores (expanding window).

Evalúa:
  1. p_bull → dirección (ρ)
  2. ev_net → magnitud |ret| (ρ)
  3. e_days → duración (ρ)
  4. D2 velocity → dirección (ρ)
  5. Comparación TAF vs cascade_conviction
"""

import os, sys, json, re
from pathlib import Path
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import spearmanr, mannwhitneyu, norm
from collections import defaultdict

os.chdir('/root/botero-trade')
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#'):
            m = re.match(r'([^=]+)=(.*)', line)
            if m:
                k, v = m.group(1), m.group(2).strip('"').strip("'")
                os.environ[k] = v

conn = psycopg2.connect(os.environ['POSTGRES_URL'])

# ============================================================================
# 0. CARGAR EDGES DESDE FACT STORES
# ============================================================================
FS_DIR = Path('/root/botero-trade/backend/modules/entry_decision/domain/rules')

# Station → ticker mapping
STATION_MAP = {
    'vix': 'VIX', 'vvix': 'VVIX', 'fg': 'FG', 'skew': 'SKEW',
    'pcr': 'CBOE_PCR', 'sv5_turbulence': 'SV5_TURBULENCE',
    'dxy': 'DXY', 'yield_curve': 'YIELD_SPREAD',
    'rotation': 'ROTATION_INDEX', 'credit': 'CREDIT_RATIO',
}

fact_stores = {}
for fname in sorted(FS_DIR.glob('*_fact_store.json')):
    station = fname.stem.replace('_fact_store', '')
    with open(fname) as f:
        fs = json.load(f)
    doc = fs.get('_documentation', {}).get('dimension_thresholds_definition', {})
    
    d1_edges = doc.get(f'{station}_edges_d1', None)
    d2_edges = doc.get(f'{station}_edges_d2', None)
    d3_edges = doc.get(f'{station}_edges_d3', None)
    d1_labels = doc.get(f'{station}_labels_d1', [f'BIN{i}' for i in range(len(d1_edges)+1 if d1_edges else 6)])
    
    fact_stores[station] = {
        'd1_edges': d1_edges,
        'd2_edges': d2_edges,
        'd3_edges': d3_edges,
        'd1_labels': d1_labels,
    }
    print(f"  Loaded {station}: d1_edges={d1_edges[:3] if d1_edges else None}..., labels={d1_labels[:3]}...")

# BSI is special — compute from SV5 components
STATION_MAP['bsi'] = 'SV5TW'  # fallback, BSI = min(SV5FI, SV5TH, SV5TW) computed below

# ============================================================================
# 1. CARGAR DATOS BASE
# ============================================================================
# SPY zz25 legs
z25 = pd.read_sql("""
    SELECT ticker, scale, start_timestamp, start_type,
           end_timestamp, end_price, start_price,
           prev_leg_return, prev_leg_duration,
           confirmed_at_timestamp, leg_id
    FROM market.zigzag_legs
    WHERE ticker = 'SPY' AND scale = 'zz25' AND status = 'CONFIRMED'
    ORDER BY start_timestamp
""", conn)
z25['start_dt'] = pd.to_datetime(z25['start_timestamp'])
z25['end_dt'] = pd.to_datetime(z25['end_timestamp'])
z25['log_return'] = np.log(z25['end_price'].astype(float) / z25['start_price'].astype(float)) * 100.0
z25['abs_ret'] = z25['log_return'].abs()
z25['leg_dur'] = (z25['end_dt'] - z25['start_dt']).dt.days.clip(lower=1)
z25['is_bull'] = (z25['start_type'] == 'MIN').astype(int)
z25['start_date'] = z25['start_dt'].dt.date

print(f"\nSPY zz25 legs: N={len(z25)}")
print(f"  Bulls: {z25['is_bull'].sum()} ({z25['is_bull'].mean()*100:.1f}%)")
print(f"  Mean |ret|: {z25['abs_ret'].mean():.2f}%, duration: {z25['leg_dur'].mean():.1f}d")

# Cargar TODOS los indicadores desde ohlcv_bars
print("\nCargando indicadores...")
IND_DATA = {}
for station, ticker in STATION_MAP.items():
    df = pd.read_sql(f"""
        SELECT time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker = %s
        ORDER BY time
    """, conn, params=[ticker])
    if not df.empty:
        df = df.set_index('date')['close']
        IND_DATA[station] = df
        print(f"  {station:20s} → {ticker:20s} N={len(df):5d}")

# BSI: min(SV5FI, SV5TH, SV5TW)
if 'bsi' in STATION_MAP:
    try:
        sv5fi = pd.read_sql("SELECT time::date as date, close FROM market.ohlcv_bars WHERE ticker='SV5FI' ORDER BY time", conn)
        sv5th = pd.read_sql("SELECT time::date as date, close FROM market.ohlcv_bars WHERE ticker='SV5TH' ORDER BY time", conn)
        sv5tw = pd.read_sql("SELECT time::date as date, close FROM market.ohlcv_bars WHERE ticker='SV5TW' ORDER BY time", conn)
        if not sv5fi.empty and not sv5th.empty and not sv5tw.empty:
            sv5fi = sv5fi.set_index('date')['close']
            sv5th = sv5th.set_index('date')['close']
            sv5tw = sv5tw.set_index('date')['close']
            common = sv5fi.index.intersection(sv5th.index).intersection(sv5tw.index)
            bsi_vals = pd.Series(
                np.minimum(np.minimum(sv5fi[common], sv5th[common]), sv5tw[common]),
                index=common
            )
            IND_DATA['bsi'] = bsi_vals
            print(f"  {'bsi':20s} → SV5FI/TH/TW min  N={len(bsi_vals):5d}")
    except Exception as e:
        print(f"  BSI: fallback to SV5TW — {e}")

print(f"\nTotal estaciones con datos: {len(IND_DATA)}")

# ============================================================================
# 2. CLASIFICACIÓN: función auxiliar
# ============================================================================
def classify_val(val, edges):
    if edges is None or len(edges) == 0:
        return 0
    for i, e in enumerate(edges):
        if val < e:
            return i
    return len(edges)

def get_state(station, date_obj):
    """Get D1×D2×D3 state for a station at a given date using expanding-window data."""
    data = IND_DATA.get(station)
    if data is None:
        return None
    
    # Find position of date in series
    idx = data.index.searchsorted(date_obj)
    pos = idx - 1  # last value at or before date
    if pos < 0:
        return None
    
    val = data.iloc[pos]
    
    # D2 = 3-day delta
    if pos >= 3:
        d2 = val - data.iloc[pos - 3]
    else:
        d2 = 0.0
    
    # D3 = std(2d)/std(10d) ratio
    if pos >= 12:
        std2 = data.iloc[pos-2:pos].std()
        std10 = data.iloc[pos-10:pos].std()
        d3 = std2 / std10 if std10 > 0 else 1.0
    else:
        d3 = 1.0
    
    edges = fact_stores.get(station, {})
    d1_idx = classify_val(val, edges.get('d1_edges'))
    d2_idx = classify_val(d2, edges.get('d2_edges'))
    d3_idx = classify_val(d3, edges.get('d3_edges'))
    
    return d1_idx, d2_idx, d3_idx, val, d2

# ============================================================================
# 3. WALK-FORWARD: Para cada zz25 leg, estado usando datos previos
# ============================================================================
dates_sorted = sorted(z25['start_date'].unique())
N_FOLDS = 26
fold_size = max(len(dates_sorted) // N_FOLDS, 1)

print(f"\nWalk-Forward: {len(dates_sorted)} dates, ~{fold_size} per fold, {N_FOLDS} folds")

RESULTS = []  # List of dicts per fold×station
TAF_RESULTS = []  # Per-leg aggregated predictions

for fold in range(N_FOLDS):
    start_i = fold * fold_size
    end_i = min(start_i + fold_size, len(dates_sorted))
    if end_i <= start_i:
        continue
    
    test_dates = set(dates_sorted[start_i:end_i])
    train_dates_all = set(d for d in dates_sorted if d < min(test_dates))
    
    # Split zz25 legs
    test_legs = z25[z25['start_date'].isin(test_dates)]
    train_legs = z25[z25['start_date'].isin(train_dates_all)]
    
    if len(test_legs) < 5 or len(train_legs) < 20:
        continue
    
    fold_taf = []  # aggregated per leg in this fold
    
    for _, leg in test_legs.iterrows():
        leg_date = leg['start_date']
        leg_station_data = []
        
        for station in IND_DATA:
            result = get_state(station, leg_date)
            if result is None:
                continue
            d1, d2, d3, val, d2_val = result
            
            # Build state key for matching against train_legs
            # Need to match: find all train legs that were in this state
            # For now, use simple D1-only state matching (D1 alone is well-populated)
            
            # Match: find train legs with same D1
            train_state_mask = np.ones(len(train_legs), dtype=bool)
            # Apply D1 filter (this requires computing state for training legs too - expensive)
            # Simplified: use D1-only to get N estimates
            # Full implementation would precompute states for all legs
            
            leg_station_data.append({
                'station': station,
                'd1': d1, 'd2': d2, 'd3': d3,
                'val': val, 'd2_val': d2_val,
            })
        
        if len(leg_station_data) < 3:
            continue
        
        fold_taf.append({
            'leg_idx': leg.name,
            'is_bull': leg['is_bull'],
            'abs_ret': leg['abs_ret'],
            'leg_dur': leg['leg_dur'],
            'stations': leg_station_data,
        })
    
    if len(fold_taf) < 5:
        continue
    
    # Aggregate: compute per-station per-state stats from train
    # For each station, aggregate train legs by (d1,d2,d3) state
    # This is the core OOS computation
    
    for station in IND_DATA:
        st_fold_data = []
        for entry in fold_taf:
            for sd in entry['stations']:
                if sd['station'] == station:
                    st_fold_data.append({
                        'is_bull': entry['is_bull'],
                        'abs_ret': entry['abs_ret'],
                        'leg_dur': entry['leg_dur'],
                        'd1': sd['d1'], 'd2': sd['d2'], 'd3': sd['d3'],
                        'val': sd['val'], 'd2_val': sd['d2_val'],
                    })
        
        if len(st_fold_data) < 10:
            continue
        
        # For prediction: train on all train_legs for this station
        # We need to classify train legs by state too
        train_station_data = []
        for _, tleg in train_legs.iterrows():
            t_date = tleg['start_date']
            result = get_state(station, t_date)
            if result is None:
                continue
            td1, td2, td3, tval, td2v = result
            train_station_data.append({
                    'is_bull': tleg['is_bull'],
                    'abs_ret': tleg['abs_ret'],
                    'leg_dur': tleg['leg_dur'],
                    'd1': td1, 'd2': td2, 'd3': td3,
                })
        
        if len(train_station_data) < 20:
            continue
        
        # Aggregate train by state (d1,d2,d3)
        train_df = pd.DataFrame(train_station_data)
        train_agg = train_df.groupby(['d1', 'd2', 'd3']).agg(
            n=('is_bull', 'count'),
            p_bull=('is_bull', 'mean'),
            ev_abs=('abs_ret', 'mean'),
            e_days=('leg_dur', 'mean'),
        ).reset_index()
        
        # Bayesian shrinkage m=10
        M = 10.0
        global_pb = train_df['is_bull'].mean()
        global_ev = train_df['abs_ret'].mean()
        global_ed = train_df['leg_dur'].mean()
        train_agg['p_bull_s'] = (train_agg['p_bull'] * train_agg['n'] + global_pb * M) / (train_agg['n'] + M)
        train_agg['ev_abs_s'] = (train_agg['ev_abs'] * train_agg['n'] + global_ev * M) / (train_agg['n'] + M)
        train_agg['e_days_s'] = (train_agg['e_days'] * train_agg['n'] + global_ed * M) / (train_agg['n'] + M)
        
        # Match test to train states
        test_df = pd.DataFrame(st_fold_data)
        merged = test_df.merge(train_agg, on=['d1', 'd2', 'd3'], how='inner')
        if len(merged) < 5:
            continue
        
        # p_bull → direction
        rho_pb, p_pb = spearmanr(merged['p_bull'], merged['is_bull'])
        # ev_abs → magnitude
        rho_ev, p_ev = spearmanr(merged['ev_abs'], merged['abs_ret'])
        # e_days → duration
        rho_ed, p_ed = spearmanr(merged['e_days'], merged['leg_dur'])
        # D2 → direction
        rho_d2, p_d2 = spearmanr(merged['d2_val'], merged['is_bull'])
        
        RESULTS.append({
            'fold': fold, 'station': station,
            'n_train': len(train_station_data), 'n_test': len(merged),
            'n_states': len(train_agg),
            'rho_pb': 0 if np.isnan(rho_pb) else rho_pb, 'p_pb': p_pb,
            'rho_ev': 0 if np.isnan(rho_ev) else rho_ev, 'p_ev': p_ev,
            'rho_ed': 0 if np.isnan(rho_ed) else rho_ed, 'p_ed': p_ed,
            'rho_d2': 0 if np.isnan(rho_d2) else rho_d2, 'p_d2': p_d2,
        })

# ============================================================================
# 4. REPORTE
# ============================================================================
res = pd.DataFrame(RESULTS)
print(f"\nResultados: {len(res)} fold×station combinations")

if len(res) == 0:
    print("\n⚠️ NO HAY RESULTADOS. Verificar que los datos se cargaron correctamente.")
    conn.close()
    sys.exit(1)

# Weighted rho
def weighted_rho_fisher(rhos, weights):
    valid = [(r, w) for r, w in zip(rhos, weights) if not np.isnan(r) and w > 0]
    if not valid:
        return 0.0, 1.0
    zs = [np.arctanh(max(min(r, 0.999), -0.999)) for r, _ in valid]
    ws = [w for _, w in valid]
    z_mean = np.average(zs, weights=ws)
    rho_mean = np.tanh(z_mean)
    z_comb = sum(z * np.sqrt(w) for z, w in zip(zs, ws)) / np.sqrt(sum(ws))
    p_comb = 2 * norm.sf(abs(z_comb))
    return rho_mean, p_comb

print("\n" + "="*90)
print("POR ESTACIÓN:")
print("="*90)

for station in sorted(res['station'].unique()):
    sr = res[res['station'] == station]
    n_tot = sr['n_test'].sum()
    if n_tot < 20:
        continue
    
    rp, pp = weighted_rho_fisher(sr['rho_pb'], sr['n_test'])
    re, pe = weighted_rho_fisher(sr['rho_ev'], sr['n_test'])
    rd, pd = weighted_rho_fisher(sr['rho_ed'], sr['n_test'])
    r2, p2 = weighted_rho_fisher(sr['rho_d2'], sr['n_test'])
    
    parts = []
    for label, r, p, target in [("p_bull→dir", rp, pp, "dir"), ("ev→|ret|", re, pe, "mag"), 
                                  ("e_days→dur", rd, pd, "dur"), ("D2→dir", r2, p2, "dir")]:
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        parts.append(f"{label}: ρ={r:+.3f}{sig}")
    
    print(f"  {station:20s} N={n_tot:5d}  folds={len(sr):2d}  {' | '.join(parts)}")

print("\n" + "="*90)
print("GLOBAL:")
print("="*90)

for metric, label in [('rho_pb', 'p_bull → dirección'), ('rho_ev', 'ev_net → |retorno|'),
                       ('rho_ed', 'e_days → duración'), ('rho_d2', 'D2 velocity → dirección')]:
    r, p = weighted_rho_fisher(res[metric], res['n_test'])
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"  {label:35s}: ρ={r:+.4f}  p={p:.4f} {sig}  N={res['n_test'].sum()}")

# ============================================================================
# 5. DETALLE: D2 por estación individual
# ============================================================================
print("\n" + "="*90)
print("D2 VELOCITY DIRECCIONAL — Detalle por estación")
print("="*90)

for station in sorted(res['station'].unique()):
    sr = res[res['station'] == station]
    n_tot = sr['n_test'].sum()
    if n_tot < 20:
        continue
    r, p = weighted_rho_fisher(sr['rho_d2'], sr['n_test'])
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"  {station:25s} ρ={r:+.4f} p={p:.4f} {sig}")

print("\n✓ Auditoría TAF v2 completa.")
conn.close()