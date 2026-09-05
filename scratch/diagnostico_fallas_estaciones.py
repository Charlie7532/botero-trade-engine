import json
from collections import defaultdict
from scipy.stats import binomtest

with open('comite_metar/salidas/comite_registro_forense.json') as f:
    frames = json.load(f)

print(f"Total frames: {len(frames)}")

# Ground truth distribution
resolved_25 = [f for f in frames if f.get('pivote_real', {}).get('zz25', {}).get('resuelto')]
dirs_25 = [f['pivote_real']['zz25']['direccion'] for f in resolved_25]
n_alza = dirs_25.count('ALZA')
n_baja = dirs_25.count('BAJA')
tot = len(dirs_25)
print(f"SPY zz25 Ground Truth: Total={tot}, ALZA={n_alza} ({n_alza/tot:.4f}), BAJA={n_baja} ({n_baja/tot:.4f})")

# Per station analysis
stations = defaultdict(lambda: {
    'all': {'hits': 0, 'n': 0, 'alza': 0, 'baja': 0},
    'conv_alta_media': {'hits': 0, 'n': 0, 'alza': 0, 'baja': 0},
    'conv_alta': {'hits': 0, 'n': 0, 'alza': 0, 'baja': 0},
    'conv_media': {'hits': 0, 'n': 0, 'alza': 0, 'baja': 0},
    'conv_baja': {'hits': 0, 'n': 0, 'alza': 0, 'baja': 0},
    'by_rol': defaultdict(lambda: {'hits': 0, 'n': 0}),
})

for f in frames:
    pr = f.get('pivote_real', {}).get('zz25')
    if not pr or not pr.get('resuelto'):
        continue
    spy_dir = pr['direccion']
    
    hits_est = f.get('hits_por_estacion', {})
    for est, h in hits_est.items():
        pred = h.get('pred')
        if pred not in ('ALZA', 'BAJA'):
            continue
        conv = h.get('conv')
        rol = h.get('rol')
        hit = (pred == spy_dir)
        
        # all
        s = stations[est]
        s['all']['n'] += 1
        if hit: s['all']['hits'] += 1
        if pred == 'ALZA': s['all']['alza'] += 1
        else: s['all']['baja'] += 1
        
        # conv breakdown
        if conv == 'ALTA':
            s['conv_alta']['n'] += 1
            if hit: s['conv_alta']['hits'] += 1
            if pred == 'ALZA': s['conv_alta']['alza'] += 1
            else: s['conv_alta']['baja'] += 1
            s['conv_alta_media']['n'] += 1
            if hit: s['conv_alta_media']['hits'] += 1
            if pred == 'ALZA': s['conv_alta_media']['alza'] += 1
            else: s['conv_alta_media']['baja'] += 1
        elif conv == 'MEDIA':
            s['conv_media']['n'] += 1
            if hit: s['conv_media']['hits'] += 1
            if pred == 'ALZA': s['conv_media']['alza'] += 1
            else: s['conv_media']['baja'] += 1
            s['conv_alta_media']['n'] += 1
            if hit: s['conv_alta_media']['hits'] += 1
            if pred == 'ALZA': s['conv_alta_media']['alza'] += 1
            else: s['conv_alta_media']['baja'] += 1
        elif conv == 'BAJA':
            s['conv_baja']['n'] += 1
            if hit: s['conv_baja']['hits'] += 1
            if pred == 'ALZA': s['conv_baja']['alza'] += 1
            else: s['conv_baja']['baja'] += 1
            
        if rol:
            s['by_rol'][rol]['n'] += 1
            if hit: s['by_rol'][rol]['hits'] += 1

print("\n" + "="*80)
print(f"{'ESTACION':<16} | {'ALL ACC (N)':<16} | {'ALTA+MED ACC (N)':<18} | {'ALTA ACC (N)':<16} | {'BAJA ACC (N)':<16}")
print("="*80)

baseline = max(n_alza, n_baja) / tot

for est, d in sorted(stations.items()):
    all_n = d['all']['n']
    all_acc = d['all']['hits'] / all_n if all_n else 0
    
    am_n = d['conv_alta_media']['n']
    am_acc = d['conv_alta_media']['hits'] / am_n if am_n else 0
    
    a_n = d['conv_alta']['n']
    a_acc = d['conv_alta']['hits'] / a_n if a_n else 0
    
    b_n = d['conv_baja']['n']
    b_acc = d['conv_baja']['hits'] / b_n if b_n else 0
    
    print(f"{est:<16} | {all_acc:6.2%} ({all_n:>4})   | {am_acc:6.2%} ({am_n:>4})     | {a_acc:6.2%} ({a_n:>4})   | {b_acc:6.2%} ({b_n:>4})")

print("\n" + "="*80)
print("DIRECTIONS PREDOMINANCE (ALZA vs BAJA)")
print("="*80)
for est, d in sorted(stations.items()):
    all_n = d['all']['n']
    alz = d['all']['alza']
    baj = d['all']['baja']
    print(f"{est:<16} | Total: {all_n:>4} | ALZA: {alz:>4} ({alz/all_n:5.1%}) | BAJA: {baj:>4} ({baj/all_n:5.1%})")

print("\n" + "="*80)
print("ROLES PRECOGNITIVOS ACCURACY")
print("="*80)
for est, d in sorted(stations.items()):
    roles_str = []
    for rol, rd in sorted(d['by_rol'].items()):
        rn = rd['n']
        racc = rd['hits'] / rn if rn else 0
        roles_str.append(f"{rol}: {racc:5.1%} (N={rn})")
    print(f"{est:<16} | " + " | ".join(roles_str))
