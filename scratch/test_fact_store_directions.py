import json
import os
import glob
import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np

with open('comite_metar/salidas/comite_registro_forense.json') as f:
    frames = json.load(f)

# Let's inspect the fact stores for each station
fact_stores = {}
for p in glob.glob('backend/modules/entry_decision/domain/rules/*_fact_store.json'):
    station = os.path.basename(p).replace('_fact_store.json', '')
    with open(p) as f:
        fact_stores[station] = json.load(f)

print(f"Loaded {len(fact_stores)} fact stores: {list(fact_stores.keys())}")

# Let's compare what fact store says (p_bull > 0.5 vs < 0.5 in zz25) vs _direccion_spy
results = {}
for station, fs in fact_stores.items():
    n_states = 0
    n_match = 0
    n_diverge = 0
    divergences = []
    
    states_dict = fs.get('states', {})
    for k, v in states_dict.items():
        if not isinstance(v, dict) or 'zz25' not in v:
            continue
        zz25 = v['zz25']
        n_raw = zz25.get('n_raw', 0)
        if n_raw < 5:
            continue
        p_bull = zz25.get('p_bull', 0.5)
        ev_net = zz25.get('ev_net', 0.0)
        op_guide = v.get('operational_guidance', '')
        
        # State key format: d1__d2__d3
        try:
            parts = [int(x) for x in k.split('__')]
            d1, d2, d3 = parts[0], parts[1], parts[2]
        except Exception:
            continue
            
        n_states += 1
        # Determine fact store direction:
        fs_dir = 'ALZA' if p_bull > 0.5359 else ('BAJA' if p_bull < (1 - 0.5359) else 'NEUTRAL')
        
        # Check what _agente_base _direccion_spy does
        from comite_metar.agentes._agente_base import _direccion_spy, _TIPOS_DIR
        agent_dir = _TIPOS_DIR[_direccion_spy(station, d1, d2, d3, False)]
        
        if agent_dir != 'NEUTRAL' and fs_dir != 'NEUTRAL':
            if agent_dir == fs_dir:
                n_match += 1
            else:
                n_diverge += 1
                divergences.append({
                    'state': k, 'd1': d1, 'd2': d2, 'd3': d3,
                    'p_bull': p_bull, 'ev_net': ev_net,
                    'fs_dir': fs_dir, 'agent_dir': agent_dir,
                    'n_raw': n_raw, 'op_guide': op_guide
                })
                
    results[station] = {
        'n_states_eval': n_states,
        'n_match': n_match,
        'n_diverge': n_diverge,
        'divergences': divergences
    }

print("\n" + "="*80)
print(f"{'ESTACION':<16} | {'MATCH':<8} | {'DIVERGE':<8} | {'PCT MATCH':<10} | {'TOP CONFLICT SAMPLE'}")
print("="*80)
for st, r in sorted(results.items()):
    tot = r['n_match'] + r['n_diverge']
    pct = r['n_match'] / tot if tot else 0
    top_conf = r['divergences'][0] if r['divergences'] else None
    conf_str = f"State {top_conf['state']}: FS={top_conf['fs_dir']} (p_bull={top_conf['p_bull']:.2f}, N={top_conf['n_raw']}) vs Agent={top_conf['agent_dir']}" if top_conf else "None"
    print(f"{st:<16} | {r['n_match']:<8} | {r['n_diverge']:<8} | {pct:8.1%}   | {conf_str}")
