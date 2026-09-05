import json
from collections import Counter

with open('comite_metar/salidas/comite_registro_forense.json') as f:
    frames = json.load(f)

test_frames = [f for f in frames if f.get('fecha', '') >= '2023-01-01']
print(f'Test frames count: {len(test_frames)}')

conf_dirs = [f.get('confluencia', {}).get('direccion_confluente') for f in test_frames]
print('Confluence directions in test:', Counter(conf_dirs))

spy_dirs = [f.get('pivote_real', {}).get('zz25', {}).get('direccion') for f in test_frames if f.get('pivote_real', {}).get('zz25', {}).get('resuelto')]
print('SPY zz25 directions in test:', Counter(spy_dirs))

# Evaluate test hits
hits_test = [f for f in test_frames if f.get('hit_confluente')]
print(f'Test hits: {len(hits_test)} / {len(test_frames)}')

# Break down by predicted direction
for d in ['ALZA', 'BAJA']:
    sub = [f for f in test_frames if f.get('confluencia', {}).get('direccion_confluente') == d]
    sub_res = [f for f in sub if f.get('pivote_real', {}).get('zz25', {}).get('resuelto')]
    hits = [f for f in sub_res if f.get('hit_confluente')]
    acc = len(hits) / len(sub_res) if sub_res else 0
    print(f'Confluence {d}: {len(hits)} / {len(sub_res)} ({acc:.2%})')
