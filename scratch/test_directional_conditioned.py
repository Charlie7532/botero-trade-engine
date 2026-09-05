import json
import glob
import os
import sys
sys.path.insert(0, '.')
from collections import defaultdict
from scipy.stats import binomtest

with open('comite_metar/salidas/comite_registro_forense.json') as f:
    frames = json.load(f)

# Load fact stores
fact_stores = {}
for p in glob.glob('backend/modules/entry_decision/domain/rules/*_fact_store.json'):
    station = os.path.basename(p).replace('_fact_store.json', '')
    with open(p) as f:
        fact_stores[station] = json.load(f)

# Calculate ground-truth baselines per scale
baselines = {}
for sc in ('zz25', 'zz50', 'zz75'):
    res = [f['pivote_real'][sc] for f in frames if f.get('pivote_real', {}).get(sc, {}).get('resuelto')]
    n_tot = len(res)
    n_alza = sum(1 for r in res if r['direccion'] == 'ALZA')
    n_baja = sum(1 for r in res if r['direccion'] == 'BAJA')
    baselines[sc] = {
        'total': n_tot,
        'alza': n_alza / n_tot if n_tot else 0.5,
        'baja': n_baja / n_tot if n_tot else 0.5,
        'n_alza': n_alza,
        'n_baja': n_baja
    }

print("Baselines del Lake por escala:")
for sc, b in baselines.items():
    print(f"  {sc}: Total={b['total']}, ALZA={b['alza']:.4f} ({b['n_alza']}), BAJA={b['baja']:.4f} ({b['n_baja']})")

# Let's test the directional-conditioned evaluation for Fact Store predictions
# across the 3 scales
from comite_metar.scripts import common
from comite_metar.agentes._agente_base import Agente
lake = common.cargar_lake()
perfiles = common.cargar_perfiles()
agentes = {p["estacion"]: Agente(p["estacion"], p, lake=lake) for p in perfiles}

# Tally per station, per scale, per direction
# both operational (conv in ALTA, MEDIA) and bruto
tally = defaultdict(lambda: {
    sc: {
        'operacional': {'alza': {'hits': 0, 'n': 0}, 'baja': {'hits': 0, 'n': 0}},
        'bruto': {'alza': {'hits': 0, 'n': 0}, 'baja': {'hits': 0, 'n': 0}}
    } for sc in ('zz25', 'zz50', 'zz75')
})

for f in frames:
    pos = f.get('t0')
    if pos is None:
        continue
    pr = f.get('pivote_real', {})
    
    for est, ag in agentes.items():
        fs = fact_stores.get(est)
        if not fs:
            continue
        try:
            r = ag.leer(pos)
            lec = r.get('lectura')
            if not lec:
                continue
            sk = lec.get('D1xD2xD3', {}).get('state_key')
            sdata = fs.get('states', {}).get(sk)
            if not sdata:
                continue
            conv = lec.get('conviccion')
            is_operacional = (conv in ('ALTA', 'MEDIA'))
            
            for sc in ('zz25', 'zz50', 'zz75'):
                sc_pr = pr.get(sc)
                if not sc_pr or not sc_pr.get('resuelto'):
                    continue
                real_dir = sc_pr['direccion']
                
                sc_fs = sdata.get(sc)
                if not sc_fs:
                    continue
                pb = sc_fs.get('p_bull', 0.5)
                n_raw = sc_fs.get('n_raw', 0)
                if n_raw < 3:
                    continue
                
                # Emit direction based on Fact Store
                pred_dir = None
                if pb >= 0.536:
                    pred_dir = 'ALZA'
                elif pb <= 0.464:
                    pred_dir = 'BAJA'
                
                if not pred_dir:
                    continue
                
                hit = (pred_dir == real_dir)
                dir_key = pred_dir.lower()
                
                tally[est][sc]['bruto'][dir_key]['n'] += 1
                if hit:
                    tally[est][sc]['bruto'][dir_key]['hits'] += 1
                    
                if is_operacional:
                    tally[est][sc]['operacional'][dir_key]['n'] += 1
                    if hit:
                        tally[est][sc]['operacional'][dir_key]['hits'] += 1
        except Exception:
            pass

print("\n" + "="*115)
print("EVALUACION DIRECCIONAL-CONDICIONADA POR ESCALA (FACT STORE - OPERACIONAL)")
print("="*115)
print(f"{'ESTACION':<15} | {'ESCALA':<6} | {'N_ALZA':<7} | {'ACC_ALZA':<10} | {'EDGE_ALZA':<10} | {'P_ALZA':<8} | {'N_BAJA':<7} | {'ACC_BAJA':<10} | {'EDGE_BAJA':<10} | {'P_BAJA':<8} | {'EDGE_COMB'}")
print("="*115)

for est in sorted(common.ESTACIONES):
    for sc in ('zz25', 'zz50', 'zz75'):
        b_alza = baselines[sc]['alza']
        b_baja = baselines[sc]['baja']
        
        op = tally[est][sc]['operacional']
        n_a, h_a = op['alza']['n'], op['alza']['hits']
        n_b, h_b = op['baja']['n'], op['baja']['hits']
        
        acc_a = h_a / n_a if n_a else 0
        acc_b = h_b / n_b if n_b else 0
        
        edge_a = acc_a - b_alza if n_a else 0
        edge_b = acc_b - b_baja if n_b else 0
        
        p_a = binomtest(h_a, n_a, b_alza, alternative='greater').pvalue if n_a else 1.0
        p_b = binomtest(h_b, n_b, b_baja, alternative='greater').pvalue if n_b else 1.0
        
        tot_n = n_a + n_b
        # Combined conditioned edge: weighted difference vs the conditioned expected hits
        edge_comb = (h_a + h_b - (n_a * b_alza + n_b * b_baja)) / tot_n if tot_n else 0
        
        sig_a = "*" if p_a < 0.15 and edge_a > 0.03 else ""
        sig_b = "*" if p_b < 0.15 and edge_b > 0.03 else ""
        
        if tot_n >= 15:
            print(f"{est:<15} | {sc:<6} | {n_a:>7} | {acc_a:7.1%}   | {edge_a:+7.1%}{sig_a:<2} | {p_a:7.4f} | {n_b:>7} | {acc_b:7.1%}   | {edge_b:+7.1%}{sig_b:<2} | {p_b:7.4f} | {edge_comb:+7.1%}")
