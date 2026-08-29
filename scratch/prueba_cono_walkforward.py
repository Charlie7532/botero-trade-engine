#!/usr/bin/env python3
"""
PRUEBA DEL CONO DE SUPERVIVENCIA — walk-forward honesto, día a día, en paralelo con el zigzag.
Sin parches al doc: solo datos.

1. Cono walk-forward: P(continúa | edad, amplitud_σ) entrenado SOLO con piernas
   confirmadas ANTES del momento de decisión. Brier + calibración vs baseline edad-only.
2. Eventos de CONTRADICCIÓN: el cono prospecta continuación (P≥0.8) pero la pierna revierte.
   ¿Qué estados D1/D3 ocurren en esos pivotes vs la base?
3. Re-validación de la señal de SILENCIO SV5T (LOW_TURBULENCE) en techos,
   sola y como precursora de contradicciones.
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

# ── 1. Reconstruir piernas con fecha de confirmación (= fecha del siguiente pivote) ──
legs = []
for i in range(len(pivot_dates) - 1):
    t0 = spy_idx.searchsorted(pivot_dates[i])
    t1 = spy_idx.searchsorted(pivot_dates[i + 1])
    t_confirm = spy_idx.searchsorted(pivot_dates[i + 1])  # el pivote final se sella al aparecer el siguiente
    if t1 >= len(spy_idx) or t1 <= t0:
        continue
    p0 = float(spy_close.iloc[t0])
    direction = 'UP' if pivot_types[i] == 'MIN' else 'DOWN'
    sigma0 = float(sigma20.iloc[t0]) if not pd.isna(sigma20.iloc[t0]) else None
    # serie de amplitudes acumuladas por barra (observable en tiempo real)
    ages, amps_sigma, prices = [], [], []
    for k in range(1, t1 - t0 + 1):
        tk = t0 + k
        if tk >= len(spy_idx):
            break
        pk = float(spy_close.iloc[tk])
        amp_log = abs(np.log(pk / p0))
        sig_k = amp_log / (sigma0 * np.sqrt(k)) if sigma0 and sigma0 > 0 else np.nan
        ages.append(k)
        amps_sigma.append(sig_k)
    legs.append({
        'idx': i, 'start_bar': t0, 'end_bar': t1, 'dur': t1 - t0,
        'start_date': pivot_dates[i], 'confirm_date': pivot_dates[i + 1],
        'end_pivot_idx': i + 1, 'direction': direction,
        'ages': ages, 'amps_sigma': amps_sigma,
    })
print(f'Piernas reconstruidas: N={len(legs)}')

AGE_BINS = [(1, 2), (3, 5), (6, 10), (11, 20), (21, 10**9)]
AMP_BINS = [(0, 1), (1, 2), (2, 3), (3, 10**9)]

def age_bin(k):
    for b, (lo, hi) in enumerate(AGE_BINS):
        if lo <= k <= hi:
            return b
    return len(AGE_BINS) - 1

def amp_bin(a):
    if np.isnan(a):
        return None
    for b, (lo, hi) in enumerate(AMP_BINS):
        if lo <= a < hi:
            return b
    return len(AMP_BINS) - 1

# ── 2. Walk-forward: para cada barra de cada pierna, predecir con tabla entrenada en el pasado ──
preds = []  # (k, amp_sigma, p_cono, p_age_only, outcome, leg_idx)
for li, leg in enumerate(legs):
    # entrenamiento: piernas cuya CONFIRMACIÓN (confirm_date) es estrictamente anterior al inicio de esta pierna
    train = [L for L in legs[:li] if L['confirm_date'] < leg['start_date']]
    if len(train) < 100:
        continue
    # construir tablas de supervivencia del entrenamiento
    tab_full = {}   # (age_b, amp_b): [cont, total]
    tab_age = {}    # age_b: [cont, total]
    for L in train:
        for k in range(1, L['dur'] + 1):
            cont = 1 if k < L['dur'] else 0
            ab = age_bin(k)
            # amplitud acumulada en la barra k de la pierna de entrenamiento
            if k - 1 < len(L['amps_sigma']):
                ampb = amp_bin(L['amps_sigma'][k - 1])
            else:
                ampb = None
            tab_age.setdefault(ab, [0, 0])
            tab_age[ab][0] += cont
            tab_age[ab][1] += 1
            if ampb is not None:
                tab_full.setdefault((ab, ampb), [0, 0])
                tab_full[(ab, ampb)][0] += cont
                tab_full[(ab, ampb)][1] += 1
    # predecir cada barra de la pierna test
    for k in range(1, leg['dur'] + 1):
        outcome = 1 if k < leg['dur'] else 0
        ab = age_bin(k)
        ampb = amp_bin(leg['amps_sigma'][k - 1]) if k - 1 < len(leg['amps_sigma']) else None
        # baseline edad-only (suavizado Laplace)
        c, n = tab_age.get(ab, [0, 0])
        p_age = (c + 1) / (n + 2)
        # cono edad×amplitud: si la celda tiene N≥15 úsala, si no, cae a edad-only
        if ampb is not None and tab_full.get((ab, ampb), [0, 0])[1] >= 15:
            c2, n2 = tab_full[(ab, ampb)]
            p_cono = (c2 + 1) / (n2 + 2)
        else:
            p_cono = p_age
        preds.append({'k': k, 'amp': leg['amps_sigma'][k - 1] if k - 1 < len(leg['amps_sigma']) else np.nan,
                      'p_cono': p_cono, 'p_age': p_age, 'y': outcome, 'leg': li})

P = pd.DataFrame(preds)
brier_cono = float(((P['p_cono'] - P['y']) ** 2).mean())
brier_age = float(((P['p_age'] - P['y']) ** 2).mean())
acc_cono = float(((P['p_cono'] >= 0.5) == P['y']).mean())
acc_age = float(((P['p_age'] >= 0.5) == P['y']).mean())
print(f'\n=== WALK-FORWARD HONESTO (tabla entrenada solo con pasado) ===')
print(f'Observaciones barra-a-barra: N={len(P)}')
print(f'Brier cono (edad×σ):  {brier_cono:.5f}')
print(f'Brier baseline edad:  {brier_age:.5f}')
print(f'Mejora del cono:      {(brier_age - brier_cono) / brier_age:+.2%} de reducción de error')
print(f'Accuracy cono:        {acc_cono:.2%} | Accuracy edad-only: {acc_age:.2%}')

# calibración del cono en bins de probabilidad
print(f'\n=== CALIBRACIÓN DEL CONO ===')
print(f'{"P predicho":>12} | {"N":>6} | {"% continuó real":>15}')
for lo, hi in [(0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]:
    m = (P['p_cono'] >= lo) & (P['p_cono'] < hi)
    if m.sum() > 0:
        print(f'  [{lo:.1f},{hi:.1f}) | {m.sum():>6} | {P.loc[m, "y"].mean():>14.1%}')

# ── 3. CONTRADICCIONES: cono dice continuar (P≥0.8) pero la pierna muere ahí ──
contras = P[(P['p_cono'] >= 0.8) & (P['y'] == 0)]
print(f'\n=== EVENTOS DE CONTRADICCIÓN (P≥0.8 pero revirtió) ===')
print(f'N contradicciones: {len(contras)} de {(P["p_cono"] >= 0.8).sum()} pronósticos de alta continuación ({len(contras) / max(1,(P["p_cono"] >= 0.8).sum()):.1%})')
contra_legs = contras['leg'].unique()
contra_pivot_idxs = sorted({legs[li]['end_pivot_idx'] for li in contra_legs})
print(f'Pivotes donde ocurrió contradicción: N={len(contra_pivot_idxs)}')

# estados D1/D3 de SV5T en pivotes de contradicción vs todos los pivotes
def sv5t_states(idxs):
    rows = df.iloc[idxs]
    sk = rows['sv5_turbulence_sk'].dropna()
    d1 = sk.str.split('__').str[0]
    d3 = sk.str.split('__').str[2]
    return d1, d3

d1_c, d3_c = sv5t_states(contra_pivot_idxs)
d1_all, d3_all = sv5t_states(list(range(len(df))))
print(f'\n=== SV5T en pivotes de CONTRADICCIÓN vs base ===')
print(f'{"estado D1":>28} | {"contradicción":>13} | {"base":>8} | {"lift":>6}')
for st in d1_all.value_counts().index[:6]:
    pc = (d1_c == st).mean() if len(d1_c) else 0
    pa = (d1_all == st).mean()
    lift = pc / pa if pa > 0 else np.nan
    flag = ' ← SOBRE-REPRESENTADO' if lift > 1.3 else ''
    print(f'{st:>28} | {pc:>12.1%} | {pa:>7.1%} | {lift:>5.2f}x{flag}')

# ── 4. Re-validación de la señal de SILENCIO SV5T en techos ──
print(f'\n=== RE-VALIDACIÓN: SILENCIO SV5T (LOW_TURBULENCE) en techos MAX ===')
max_mask = df['pivot_type'] == 'MAX'
fwd = df['prev_leg_return'].shift(-1)
base_cae_max = float((fwd[max_mask & fwd.notna()] <= 0).mean())
sk = df['sv5_turbulence_sk']
sv5_d1 = sk.str.split('__').str[0]
sv5_d3 = sk.str.split('__').str[2]

variantes = {
    'LOW_TURBULENCE solo': (sv5_d1 == 'LOW_TURBULENCE'),
    'LOW_TURB + D3 vol_exp (definición original)': (sv5_d1 == 'LOW_TURBULENCE') & sv5_d3.isin(['VOL_ACCELERATING_EXPANSION', 'VOL_PEAK_DECELERATION']),
    'QUIET_FLOW solo': (sv5_d1 == 'QUIET_FLOW'),
    'QUIET_FLOW + D3 vol_exp': (sv5_d1 == 'QUIET_FLOW') & sv5_d3.isin(['VOL_ACCELERATING_EXPANSION', 'VOL_PEAK_DECELERATION']),
}
print(f'Base rate caída en MAX: {base_cae_max:.1%}')
for name, cond in variantes.items():
    m = cond & max_mask & fwd.notna()
    n = int(m.sum())
    if n < 5:
        print(f'  {name:45s}: N={n} (muestra baja)')
        continue
    pct = float((fwd[m] <= 0).mean())
    lift = pct / base_cae_max
    ci_lo, ci_hi = None, None
    print(f'  {name:45s}: N={n:3d} %Cae={pct:.1%} Lift={lift:.3f}x {"← mejor que base" if lift > 1.05 else "← peor/igual que base" if lift < 0.95 else ""}')

# presencia de silencio en contradicciones (cualquier pivote, no solo MAX)
sil_contra = (d1_c == 'LOW_TURBULENCE').mean() if len(d1_c) else 0
sil_base = (d1_all == 'LOW_TURBULENCE').mean()
print(f'\nSilencio SV5T en contradicciones: {sil_contra:.1%} vs base {sil_base:.1%} (lift {sil_contra/sil_base if sil_base>0 else np.nan:.2f}x)')
