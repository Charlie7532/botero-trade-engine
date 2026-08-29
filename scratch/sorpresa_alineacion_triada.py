#!/usr/bin/env python3
"""
¿Tiene significado la SORPRESA y la ALINEACIÓN de la tríada?
1. SORPRESA: la esperanza dice una dirección y la vela hace lo contrario.
2. ALINEACIÓN: las escalas apuntan todas en la misma dirección
   (y si son proporcionales o de proporciones distintas).
Target: reversión de la pierna en ≤3 barras.
Todo observable en tiempo real (estados del día, sin saber el pivote).
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

# piernas
legs = []
for i in range(len(pivot_dates) - 1):
    t0 = spy_idx.searchsorted(pivot_dates[i])
    t1 = spy_idx.searchsorted(pivot_dates[i + 1])
    if t1 >= len(spy_idx) or t1 <= t0:
        continue
    legs.append({'t0': t0, 't1': t1, 'dur': t1 - t0,
                 'direction': 1 if pivot_types[i] == 'MIN' else -1,
                 'df_row': i})

# consenso de esperanza por día: media de (pbull - 0.5) de 4 estaciones × 2 escalas
pbull_cols = ['vix_zk_pbull', 'vix_zz25_pbull', 'credit_zk_pbull', 'credit_zz25_pbull',
              'bsi_zk_pbull', 'bsi_zz25_pbull', 'fg_zk_pbull', 'fg_zz25_pbull']
consensus = (df[pbull_cols] - 0.5).mean(axis=1)   # >0 = esperanza alcista
# alineación de la tríada VIX (zk vs zz25) + ev_net
zk = df['vix_zk_pbull']; z25 = df['vix_zz25_pbull']

rows = []
for leg in legs:
    row0 = leg['df_row']
    for pos in range(leg['dur']):
        t = leg['t0'] + pos
        if t + 1 >= len(spy_idx) or row0 + pos >= len(df):
            continue
        r_next = float(spy_close.iloc[t + 1] / spy_close.iloc[t] - 1)
        exp_dir = np.sign(consensus.iloc[row0 + pos]) if not pd.isna(consensus.iloc[row0 + pos]) else 0
        against = (r_next * exp_dir < 0) and exp_dir != 0
        s = float(sigma20.iloc[t]) if not pd.isna(sigma20.iloc[t]) else np.nan
        surprise = -r_next * exp_dir / s if s and s > 0 and exp_dir != 0 else np.nan  # >0 = sorpresa negativa
        # alineación de escalas (VIX como ejemplo)
        a, b = zk.iloc[row0 + pos], z25.iloc[row0 + pos]
        if pd.isna(a) or pd.isna(b):
            align = 'NA'
        elif a > 0.5 and b > 0.5:
            align = 'UP' if abs(a - b) < 0.1 else 'UP_prop_diff'
        elif a < 0.5 and b < 0.5:
            align = 'DOWN' if abs(a - b) < 0.1 else 'DOWN_prop_diff'
        else:
            align = 'MIXED'
        bars_left = leg['t1'] - t - 1
        rows.append({'against': against, 'surprise': surprise, 'align': align,
                     'age': pos + 1, 'died_3': bars_left <= 3})

E = pd.DataFrame(rows)
base = E['died_3'].mean()
print(f'Barras dentro de piernas: N={len(E)} | P(muere≤3b) base={base:.1%}')

print(f'\n=== 1. SORPRESA (esperanza vs vela real) ===')
print(f'{"condición":>40} | {"N":>6} | {"P(muere≤3b)":>11} | {"lift":>6}')
conds = [
    ('vela A FAVOR de la esperanza', ~E['against']),
    ('vela CONTRA la esperanza (cualquiera)', E['against']),
    ('sorpresa moderada (0.5-1σ)', (E['surprise'] > 0.5) & (E['surprise'] <= 1)),
    ('sorpresa fuerte (1-2σ)', (E['surprise'] > 1) & (E['surprise'] <= 2)),
    ('sorpresa extrema (>2σ)', E['surprise'] > 2),
]
for name, m in conds:
    m = m & m.notna() if m.dtype != bool else m
    n = int(m.sum())
    if n < 10:
        continue
    p = E.loc[m, 'died_3'].mean()
    print(f'{name:>40} | {n:>6} | {p:>10.1%} | {p/base:>5.2f}x')

print(f'\n=== 2. ALINEACIÓN DE LAS ESCALAS (tríada VIX) ===')
print(f'{"alineación":>20} | {"N":>6} | {"P(muere≤3b)":>11} | {"lift":>6}')
for al in ['UP', 'UP_prop_diff', 'DOWN', 'DOWN_prop_diff', 'MIXED']:
    m = E['align'] == al
    n = int(m.sum())
    if n < 20:
        continue
    p = E.loc[m, 'died_3'].mean()
    print(f'{al:>20} | {n:>6} | {p:>10.1%} | {p/base:>5.2f}x')

print(f'\n=== 3. INTERACCIÓN: sorpresa extrema × alineación ===')
for al in ['UP', 'UP_prop_diff', 'MIXED']:
    m = (E['surprise'] > 1) & (E['align'] == al)
    n = int(m.sum())
    if n < 10:
        continue
    p = E.loc[m, 'died_3'].mean()
    print(f'  sorpresa>1σ con escalas {al:>14}: N={n:4d} P(muere≤3b)={p:.1%} lift={p/base:.2f}x')

print(f'\n=== 4. INTERACCIÓN: sorpresa × edad de la pierna ===')
for age_lo, age_hi, lab in [(1, 3, 'joven ≤3b'), (4, 8, 'media 4-8b'), (9, 10**9, 'madura >8b')]:
    m = (E['surprise'] > 1) & (E['age'] >= age_lo) & (E['age'] <= age_hi)
    n = int(m.sum())
    if n < 10:
        continue
    p = E.loc[m, 'died_3'].mean()
    print(f'  sorpresa>1σ pierna {lab:>12}: N={n:4d} P(muere≤3b)={p:.1%} lift={p/base:.2f}x')
