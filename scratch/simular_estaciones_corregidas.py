import json
import glob
import os
import sys
sys.path.insert(0, '.')
from collections import defaultdict
from scipy.stats import binomtest
import pandas as pd

with open('comite_metar/salidas/comite_registro_forense.json') as f:
    frames = json.load(f)

# Load fact stores
fact_stores = {}
for p in glob.glob('backend/modules/entry_decision/domain/rules/*_fact_store.json'):
    station = os.path.basename(p).replace('_fact_store.json', '')
    with open(p) as f:
        fact_stores[station] = json.load(f)

print(f"Loaded {len(fact_stores)} fact stores.")

# Ground truth baseline
resolved = [f for f in frames if f.get('pivote_real', {}).get('zz25', {}).get('resuelto')]
dirs = [f['pivote_real']['zz25']['direccion'] for f in resolved]
base_lake = max(dirs.count('ALZA'), dirs.count('BAJA')) / len(dirs)
print(f"Total resolved: {len(resolved)}, Baseline Lake: {base_lake:.4f}")

# Compare 3 scenarios:
# S0: Current (all readings with dir != NEUTRAL)
# S1: Conviction Filter (only conviccion in ('ALTA', 'MEDIA'))
# S2: Fact Store Conditioning (using p_bull from Fact Store for the state d1__d2__d3)
# S3: Fact Store + Conviction Filter

from comite_metar.curador import modelador as MOD

scenarios = {
    'S0_Current': defaultdict(lambda: {'hits': 0, 'n': 0, 'dirs': defaultdict(int)}),
    'S1_Filter_Conv': defaultdict(lambda: {'hits': 0, 'n': 0, 'dirs': defaultdict(int)}),
    'S2_FactStore': defaultdict(lambda: {'hits': 0, 'n': 0, 'dirs': defaultdict(int)}),
    'S3_FS_and_Conv': defaultdict(lambda: {'hits': 0, 'n': 0, 'dirs': defaultdict(int)}),
}

# We need the lake to get the state_key at each episode pos
from comite_metar.scripts import common
lake = common.cargar_lake()
perfiles = common.cargar_perfiles()
from comite_metar.agentes._agente_base import Agente
agentes = {p["estacion"]: Agente(p["estacion"], p, lake=lake) for p in perfiles}

for f in frames:
    pr = f.get('pivote_real', {}).get('zz25')
    if not pr or not pr.get('resuelto'):
        continue
    spy_dir = pr['direccion']
    pos = f.get('t0')
    
    hits_est = f.get('hits_por_estacion', {})
    for est, h in hits_est.items():
        pred_curr = h.get('pred')
        conv = h.get('conv')
        
        # S0: Current
        if pred_curr in ('ALZA', 'BAJA'):
            scenarios['S0_Current'][est]['n'] += 1
            scenarios['S0_Current'][est]['dirs'][pred_curr] += 1
            if pred_curr == spy_dir:
                scenarios['S0_Current'][est]['hits'] += 1
                
        # S1: Only ALTA / MEDIA conviction
        if pred_curr in ('ALZA', 'BAJA') and conv in ('ALTA', 'MEDIA'):
            scenarios['S1_Filter_Conv'][est]['n'] += 1
            scenarios['S1_Filter_Conv'][est]['dirs'][pred_curr] += 1
            if pred_curr == spy_dir:
                scenarios['S1_Filter_Conv'][est]['hits'] += 1

        # S2 & S3: Fact Store prediction
        fs = fact_stores.get(est)
        ag = agentes.get(est)
        if fs and ag and pos is not None:
            try:
                r = ag.leer(pos)
                lec = r.get('lectura')
                if lec:
                    sk = lec.get('D1xD2xD3', {}).get('state_key')
                    sdata = fs.get('states', {}).get(sk)
                    if sdata and 'zz25' in sdata:
                        pb = sdata['zz25'].get('p_bull', 0.5)
                        n_raw = sdata['zz25'].get('n_raw', 0)
                        fs_pred = None
                        if n_raw >= 3:
                            if pb >= 0.536:
                                fs_pred = 'ALZA'
                            elif pb <= 0.464:
                                fs_pred = 'BAJA'
                        
                        if fs_pred:
                            scenarios['S2_FactStore'][est]['n'] += 1
                            scenarios['S2_FactStore'][est]['dirs'][fs_pred] += 1
                            if fs_pred == spy_dir:
                                scenarios['S2_FactStore'][est]['hits'] += 1
                                
                            if conv in ('ALTA', 'MEDIA'):
                                scenarios['S3_FS_and_Conv'][est]['n'] += 1
                                scenarios['S3_FS_and_Conv'][est]['dirs'][fs_pred] += 1
                                if fs_pred == spy_dir:
                                    scenarios['S3_FS_and_Conv'][est]['hits'] += 1
            except Exception:
                pass

print("\n" + "="*95)
print(f"{'ESTACION':<15} | {'S0 Current':<16} | {'S1 Conv Filter':<16} | {'S2 Fact Store':<18} | {'S3 FS + Conv':<18}")
print("="*95)

for est in sorted(common.ESTACIONES):
    def fmt(sc_name):
        d = scenarios[sc_name][est]
        n = d['n']
        h = d['hits']
        if n == 0:
            return "N=0"
        acc = h / n
        edge = acc - base_lake
        p = binomtest(h, n, base_lake, alternative='greater').pvalue
        sig = "*" if p < 0.15 and edge >= 0.03 else ""
        return f"{acc:5.1%} ({n:>3}) {edge:+4.1%}p{sig}"

    print(f"{est:<15} | {fmt('S0_Current'):<16} | {fmt('S1_Filter_Conv'):<16} | {fmt('S2_FactStore'):<18} | {fmt('S3_FS_and_Conv'):<18}")
