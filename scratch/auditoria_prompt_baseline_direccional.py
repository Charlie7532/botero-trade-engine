import json
from collections import defaultdict
from scipy.stats import binomtest
import pandas as pd

with open('comite_metar/salidas/comite_registro_forense.json') as f:
    frames = json.load(f)

# Evaluate each scale: zz25, zz50, zz75
scales = ['zz25', 'zz50', 'zz75']

for scale in scales:
    resolved = [f for f in frames if f.get('pivote_real', {}).get(scale, {}).get('resuelto')]
    dirs = [f['pivote_real'][scale]['direccion'] for f in resolved]
    tot = len(dirs)
    base_alza = dirs.count('ALZA') / tot if tot else 0.5
    base_baja = dirs.count('BAJA') / tot if tot else 0.5
    
    print("="*95)
    print(f"ESCALA: {scale.upper()} | Total Resueltos: {tot} | Baseline ALZA: {base_alza:.4f} | Baseline BAJA: {base_baja:.4f}")
    print("="*95)
    
    # Per station directional tally
    tally = defaultdict(lambda: {
        'n_alza': 0, 'hits_alza': 0,
        'n_baja': 0, 'hits_baja': 0,
    })
    
    for f in frames:
        pr = f.get('pivote_real', {}).get(scale)
        if not pr or not pr.get('resuelto'):
            continue
        spy_dir = pr['direccion']
        
        hits_est = f.get('hits_por_estacion', {})
        for est, h in hits_est.items():
            pred = h.get('pred')
            if pred == 'ALZA':
                tally[est]['n_alza'] += 1
                if spy_dir == 'ALZA':
                    tally[est]['hits_alza'] += 1
            elif pred == 'BAJA':
                tally[est]['n_baja'] += 1
                if spy_dir == 'BAJA':
                    tally[est]['hits_baja'] += 1

    print(f"{'ESTACION':<15} | {'ALZA: acc (N) lift p_val':<28} | {'BAJA: acc (N) lift p_val':<28} | {'COMB EDGE':<10} | {'VALIDA?'}")
    print("-" * 95)
    
    for est, d in sorted(tally.items()):
        na, ha = d['n_alza'], d['hits_alza']
        nb, hb = d['n_baja'], d['hits_baja']
        
        acc_a = ha / na if na else 0.0
        acc_b = hb / nb if nb else 0.0
        
        lift_a = (acc_a - base_alza) / base_alza if base_alza > 0 else 0.0
        lift_b = (acc_b - base_baja) / base_baja if base_baja > 0 else 0.0
        
        edge_a = acc_a - base_alza
        edge_b = acc_b - base_baja
        
        pa = binomtest(ha, na, base_alza, alternative='greater').pvalue if na else 1.0
        pb = binomtest(hb, nb, base_baja, alternative='greater').pvalue if nb else 1.0
        
        # Weighted edge proposed in prompt
        ntot = na + nb
        comb_edge = (edge_a * na + edge_b * nb) / ntot if ntot else 0.0
        
        # Prompt criterion: at least one direction passes with edge > 0.03 and p < 0.15
        val_a = (edge_a >= 0.03 and pa < 0.15 and na >= 20)
        val_b = (edge_b >= 0.03 and pb < 0.15 and nb >= 20)
        status = []
        if val_a: status.append(f"ALZA(p={pa:.3f})")
        if val_b: status.append(f"BAJA(p={pb:.3f})")
        val_str = " + ".join(status) if status else "NO"
        
        str_a = f"{acc_a:5.1%} ({na:>3}) {edge_a:+5.1%}p p={pa:.3f}" if na else "N/A"
        str_b = f"{acc_b:5.1%} ({nb:>3}) {edge_b:+5.1%}p p={pb:.3f}" if nb else "N/A"
        
        print(f"{est:<15} | {str_a:<28} | {str_b:<28} | {comb_edge:+5.2%}    | {val_str}")
    print()
