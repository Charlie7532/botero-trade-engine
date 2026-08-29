#!/usr/bin/env python3
"""
Todos los casos visibles: sorpresa × alineación × edad de la pierna.
Target: P(reversión ≤3 barras). Todo observable en tiempo real.
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

legs = []
for i in range(len(pivot_dates) - 1):
    t0 = spy_idx.searchsorted(pivot_dates[i])
    t1 = spy_idx.searchsorted(pivot_dates[i + 1])
    if t1 >= len(spy_idx) or t1 <= t0:
        continue
    legs.append({'t0': t0, 't1': t1, 'dur': t1 - t0,
                 'direction': 1 if pivot_types[i] == 'MIN' else -1,
                 'df_row': i})

pbull_cols = ['vix_zk_pbull', 'vix_zz25_pbull', 'credit_zk_pbull', 'credit_zz25_pbull',
              'bsi_zk_pbull', 'bsi_zz25_pbull', 'fg_zk_pbull', 'fg_zz25_pbull']
consensus = (df[pbull_cols] - 0.5).mean(axis=1)
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
        surprise = -r_next * exp_dir / s if s and s > 0 and exp_dir != 0 else np.nan
        a, b = zk.iloc[row0 + pos], z25.iloc[row0 + pos]
        if pd.isna(a) or pd.isna(b):
            align = 'NA'
        elif a > 0.5 and b > 0.5:
            align = 'UP_prop' if abs(a - b) < 0.1 else 'UP_diff'
        elif a < 0.5 and b < 0.5:
            align = 'DOWN_prop' if abs(a - b) < 0.1 else 'DOWN_diff'
        else:
            align = 'MIXED'
        bars_left = leg['t1'] - t - 1
        age = pos + 1
        age_cat = 'joven' if age <= 3 else ('media' if age <= 8 else 'madura')
        rows.append({'against': against, 'surprise': surprise, 'align': align,
                     'age_cat': age_cat, 'died_3': bars_left <= 3})

E = pd.DataFrame(rows)
base = E['died_3'].mean()
rng = np.random.default_rng(42)

def ci(k, n, nboot=2000):
    if n < 5: return (np.nan, np.nan)
    x = np.concatenate([np.ones(k), np.zeros(n - k)])
    boots = [rng.choice(x, n, replace=True).mean() for _ in range(nboot)]
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))

print(f'Barras: N={len(E)} | P(reversión≤3b) base={base:.1%}')
print(f'\n{"CASO VISIBLE":>55} | {"N":>5} | {"P(rev)":>7} | {"CI95":>18} | {"lift":>6}')
print('-' * 105)

# Todos los casos: sorpresa_bin × align × age_cat
for surp_lo, surp_hi, surp_lab in [(0, 0.5, 'sin sorpresa'), (0.5, 1, 'sorp 0.5-1σ'),
                                     (1, 2, 'sorp 1-2σ'), (2, 10, 'sorp >2σ')]:
    for al in ['UP_prop', 'UP_diff', 'DOWN_prop', 'DOWN_diff', 'MIXED']:
        for ac in ['joven', 'media', 'madura']:
            m = ((E['surprise'] >= surp_lo) & (E['surprise'] < surp_hi) &
                 (E['align'] == al) & (E['age_cat'] == ac))
            n = int(m.sum())
            if n < 15:
                continue
            k = int(E.loc[m, 'died_3'].sum())
            p = k / n
            lo, hi = ci(k, n)
            lift = p / base
            flag = '⚠️' if lift > 1.2 else ('✅' if lift < 0.8 else '')
            label = f'{surp_lab} | {al} | {ac}'
            print(f'{label:>55} | {n:>5} | {p:>6.1%} | [{lo:.1%}, {hi:.1%}] | {lift:>5.2f}x {flag}')

# resumen de los casos más extremos
print(f'\n=== RESUMEN: CASOS CON MAYOR/MENOR P(reversión) ===')
all_cases = []
for surp_lo, surp_hi, surp_lab in [(0, 0.5, 'sin sorpresa'), (0.5, 1, 'sorp 0.5-1σ'),
                                     (1, 2, 'sorp 1-2σ'), (2, 10, 'sorp >2σ')]:
    for al in ['UP_prop', 'UP_diff', 'DOWN_prop', 'DOWN_diff', 'MIXED']:
        for ac in ['joven', 'media', 'madura']:
            m = ((E['surprise'] >= surp_lo) & (E['surprise'] < surp_hi) &
                 (E['align'] == al) & (E['age_cat'] == ac))
            n = int(m.sum())
            if n < 15:
                continue
            k = int(E.loc[m, 'died_3'].sum())
            p = k / n
            lo, hi = ci(k, n)
            all_cases.append((f'{surp_lab} | {al} | {ac}', n, p, lo, hi))

all_cases.sort(key=lambda x: -x[2])
print('TOP 5 (mayor P(reversión)):')
for label, n, p, lo, hi in all_cases[:5]:
    print(f'  {label:>55}: N={n:4d} P={p:.1%} CI95=[{lo:.1%},{hi:.1%}]')
print('BOTTOM 5 (menor P(reversión)):')
for label, n, p, lo, hi in all_cases[-5:]:
    print(f'  {label:>55}: N={n:4d} P={p:.1%} CI95=[{lo:.1%},{hi:.1%}]')
