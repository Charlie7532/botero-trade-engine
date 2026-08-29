#!/usr/bin/env python3
"""
Vela CONTRARIA FUERA DEL CONO con tríada convergente: ¿ruido o aviso?
- En cada barra DENTRO de una pierna (observable real-time):
  ¿la siguiente vela va CONTRA la dirección de la pierna?
- Si la vela contraria es grande (>1σ diaria), ¿la pierna muere después?
- Permutaciones de resultado tras vela contraria: muere en 1-3 barras vs continúa.
"""
import sys
sys.path.insert(0, 'research/01_señales_entry_exit')
from medir_senal import cargar_datos
import numpy as np
import pandas as pd

df, spy = cargar_datos()
spy_close = spy['close']
spy_idx = spy_close.index
logret = np.log(spy_close).diff()
sigma20 = logret.rolling(20).std()

pivot_dates = df['pivot_date'].tolist()
pivot_types = df['pivot_type'].tolist()

# reconstruir piernas
legs = []
for i in range(len(pivot_dates) - 1):
    t0 = spy_idx.searchsorted(pivot_dates[i])
    t1 = spy_idx.searchsorted(pivot_dates[i + 1])
    if t1 >= len(spy_idx) or t1 <= t0:
        continue
    legs.append({'t0': t0, 't1': t1, 'dur': t1 - t0,
                 'direction': 1 if pivot_types[i] == 'MIN' else -1,
                 'start_date': pivot_dates[i]})
print(f'Piernas: N={len(legs)}')

# ── 1. En cada barra interna de cada pierna: ¿la siguiente vela va contra la dirección? ──
contra_events = []  # (leg_i, bar_pos, size_sigma, leg_died_within)
for li, leg in enumerate(legs):
    sig_path = []
    for pos in range(leg['t0'], leg['t1']):
        if pos + 1 >= len(spy_idx):
            continue
        r_next = float(spy_close.iloc[pos + 1] / spy_close.iloc[pos] - 1)
        against = r_next * leg['direction'] < 0          # vela contra la pierna
        s = float(sigma20.iloc[pos]) if not pd.isna(sigma20.iloc[pos]) else np.nan
        size_sigma = abs(r_next) / s if s and s > 0 else np.nan
        # ¿la pierna muere en las próximas 1-3 barras?
        bars_left = leg['t1'] - pos - 1
        died_3 = bars_left <= 3
        contra_events.append({'against': against, 'size_sigma': size_sigma,
                              'died_3': died_3, 'bars_left': bars_left})
E = pd.DataFrame(contra_events)

base_died3 = E['died_3'].mean()
print(f'\n=== BASE: barras dentro de piernas N={len(E)} ===')
print(f'P(vela contra la pierna):            {E["against"].mean():.1%}')
print(f'P(vela contra Y grande >1σ):         {(E["against"] & (E["size_sigma"]>1)).mean():.1%}')
print(f'P(vela contra Y enorme >2σ):         {(E["against"] & (E["size_sigma"]>2)).mean():.1%}')
print(f'P(muerte de pierna en ≤3 barras) base: {base_died3:.1%}')

print(f'\n=== ¿QUÉ SIGNIFICA LA VELA CONTRARIA? (condicionado) ===')
print(f'{"condición":>42} | {"N":>6} | {"P(muere≤3b)":>11} | {"lift vs base":>12}')
conds = [
    ('sin vela contraria', ~E['against']),
    ('vela contraria cualquiera', E['against']),
    ('vela contraria >1σ', E['against'] & (E['size_sigma'] > 1)),
    ('vela contraria >2σ (FUERA DEL CONO)', E['against'] & (E['size_sigma'] > 2)),
    ('vela contraria >2σ Y edad pierna >5b', E['against'] & (E['size_sigma'] > 2) & (E['bars_left'] < 10**9)),
]
for name, m in conds:
    n = int(m.sum())
    if n < 10:
        continue
    p = E.loc[m, 'died_3'].mean()
    print(f'{name:>42} | {n:>6} | {p:>10.1%} | {p/base_died3:>11.2f}x')

# ── 2. Edad de la pierna al momento de la vela contraria grande ──
print(f'\n=== VELA CONTRA >2σ: ¿a qué edad de la pierna ocurre? ===')
big = E[E['against'] & (E['size_sigma'] > 2)].copy()
big['age'] = 0
# recomputar edad: posición dentro de la pierna
ages = []
for li, leg in enumerate(legs):
    for pos_i in range(leg['dur']):
        ages.append(pos_i + 1)
E['age'] = ages[:len(E)]
big = E[E['against'] & (E['size_sigma'] > 2)]
print(f'N={len(big)} | edad mediana={big["age"].median():.0f}b | P(muere≤3b)={big["died_3"].mean():.1%}')
print(f'P(muere≤3b | contra>2σ, edad≤3b):  {big.loc[big["age"]<=3,"died_3"].mean():.1%} (N={(big["age"]<=3).sum()})')
print(f'P(muere≤3b | contra>2σ, edad>8b):  {big.loc[big["age"]>8,"died_3"].mean():.1%} (N={(big["age"]>8).sum()})')

# ── 3. Permutaciones de la tríada: 2^3 = 8 combinaciones bull/bear ──
print(f'\n=== PERMUTACIONES DE LA TRÍADA (desde quants_obs, pivotes) ===')
tri_cols = [c for c in df.columns if 'zk_pbull' in c]
print(f'Columnas p_bull tríada disponibles: {len(tri_cols)} estaciones')
if tri_cols:
    st = df[tri_cols[0]]
    # usar primera estación como ejemplo de permutación bull/bear en 3 escalas
    zk = df.get('sv5_turbulence_zk_pbull'), df.get('sv5_turbulence_zz25_pbull'), df.get('sv5_turbulence_ev_net')
fwd = df['prev_leg_return'].shift(-1)
# permutación con columna de una estación que tenga las 3 escalas
cols3 = ['vix_zk_pbull', 'vix_zz25_pbull', 'vix_ev_net']
have = [c for c in ['vix_sk'] if c in df.columns]
# construcción directa: p_bull>0.5 en 3 escalas para VIX si existen
vcols = [c for c in df.columns if c.startswith('vix_') and ('zk_pbull' in c or 'zz25_pbull' in c)]
print(f'Escalas VIX disponibles: {vcols}')
