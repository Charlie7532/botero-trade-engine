#!/usr/bin/env python3
"""Análisis de la hipotesis de supervivencia condicional de piernas zigzag.
P(continúa a k+1 | ya cumplió k) — degradación con la edad de la pierna.
Todo observable en tiempo real: la edad de la pierna actual se conoce en cada barra.
"""
import sys
sys.path.insert(0, 'research/01_señales_entry_exit')
from medir_senal import cargar_datos
import numpy as np

df, spy = cargar_datos()
spy_close = spy['close']
spy_idx = spy_close.index

# ── 1. Duración de cada pierna (barras entre pivotes consecutivos) ──
pivot_dates = df['pivot_date'].tolist()
pivot_types = df['pivot_type'].tolist()
durations, directions, amplitudes = [], [], []
for i in range(len(pivot_dates) - 1):
    t0 = spy_idx.searchsorted(pivot_dates[i])
    t1 = spy_idx.searchsorted(pivot_dates[i + 1])
    if t1 >= len(spy_idx) or t1 <= t0:
        continue
    dur = t1 - t0
    p0 = float(spy_close.iloc[t0]); p1 = float(spy_close.iloc[t1])
    amp = (p1 - p0) / p0
    durations.append(dur)
    directions.append('UP' if pivot_types[i] == 'MIN' else 'DOWN')
    amplitudes.append(amp)
dur = np.array(durations)
print(f'=== PIERNAS COMPLETAS: N={len(dur)} ===')
print(f'Duración: mediana={np.median(dur):.0f} media={dur.mean():.1f} P25={np.percentile(dur,25):.0f} P75={np.percentile(dur,75):.0f} P95={np.percentile(dur,95):.0f} max={dur.max()}')
for d in ('UP', 'DOWN'):
    sub = dur[np.array(directions) == d]
    print(f'  {d}: N={len(sub)} mediana={np.median(sub):.0f}')
print()

# ── 2. Función de supervivencia S(k) = P(duración >= k) ──
print('=== SUPERVIVENCIA CONDICIONAL: P(continúa a k+1 | ya cumplió k) ===')
print(f'{"k":>3} | {"N en riesgo":>10} | {"P(cont|k)":>9} | {"P(cont|k) UP":>12} | {"P(cont|k) DOWN":>13}')
dur_up = dur[np.array(directions) == 'UP']
dur_dn = dur[np.array(directions) == 'DOWN']
rows = []
for k in list(range(1, 21)) + [25, 30, 40, 50, 75, 100]:
    at_risk = (dur >= k).sum()
    cont = (dur >= k + 1).sum()
    p = cont / at_risk if at_risk > 0 else np.nan
    au = (dur_up >= k).sum(); cu = (dur_up >= k + 1).sum()
    ad = (dur_dn >= k).sum(); cd = (dur_dn >= k + 1).sum()
    pu = cu / au if au > 0 else np.nan
    pd_ = cd / ad if ad > 0 else np.nan
    rows.append((k, at_risk, p, pu, pd_))
    print(f'{k:>3} | {at_risk:>10} | {p:>8.1%}  | {pu:>11.1%}  | {pd_:>12.1%}')
print()

# ── 3. ¿La degradación es monótona? (regresión de P(cont|k) vs k) ──
ks = np.array([r[0] for r in rows if r[1] >= 30])
ps = np.array([r[2] for r in rows if r[1] >= 30])
slope = np.polyfit(ks, ps, 1)[0]
print(f'=== DEGRADACIÓN: pendiente de P(cont|k) vs k = {slope:+.4f} por barra ===')
print(f'Interpretación: cada barra adicional de vida de la pierna, la probabilidad')
print(f'de continuar cambia {slope:+.2%} en términos absolutos.')
print()

# ── 4. Cono de dispersión: dado edad k, distribución de duración restante ──
print('=== CONO DE DISPERSIÓN: duración restante dado que la pierna ya cumplió k ===')
print(f'{"k":>3} | {"restante med":>12} | {"restante P25":>12} | {"restante P75":>12} | {"restante P95":>12}')
for k in [3, 5, 8, 12, 20, 30]:
    sub = dur[dur >= k] - k  # duración restante
    if len(sub) < 20:
        continue
    print(f'{k:>3} | {np.median(sub):>11.0f}b | {np.percentile(sub,25):>11.0f}b | {np.percentile(sub,75):>11.0f}b | {np.percentile(sub,95):>11.0f}b')
print()

# ── 5. Condición doble: edad k Y amplitud acumulada (lo realista) ──
print('=== CONO CONDICIONADO POR AMPLITUD (edad=5 barras) ===')
amps = np.abs(np.array(amplitudes))
for amp_lo, amp_hi, lab in [(0, 0.01, 'movió <1%'), (0.01, 0.025, 'movió 1-2.5%'), (0.025, 0.05, 'movió 2.5-5%'), (0.05, 1.0, 'movió >5%')]:
    mask = (dur >= 5) & (amps >= amp_lo) & (amps < amp_hi)
    sub = dur[mask]
    if len(sub) < 10:
        print(f'  edad=5, {lab}: N={len(sub)} (muestra baja)')
        continue
    cont = (sub >= 6).mean()
    rest = sub - 5
    print(f'  edad=5, {lab}: N={len(sub)} P(cont|cumplió 5)={cont:.1%} restante mediana={np.median(rest):.0f}b')
print()

# ── 6. Estabilidad por década (check anti-fracaso) ──
print('=== ESTABILIDAD POR DÉCADA: P(duración > mediana global) ===')
years_legs = df['pivot_date'].dt.year.values[:len(dur)]
med_global = np.median(dur)
for dec_lo in range(1993, 2024, 10):
    mask = (years_legs >= dec_lo) & (years_legs < dec_lo + 10)
    sub = dur[mask]
    if len(sub) < 30:
        continue
    print(f'  {dec_lo}s: N={len(sub)} P(dur>{med_global:.0f}b)={(sub > med_global).mean():.1%} mediana={np.median(sub):.0f}b')
print()

# ── 7. CONO COMBINADO edad × amplitud (la regla operacional) ──
print('=== CONO COMBINADO: P(cont|edad, amplitud acumulada) — LA REGLA ===')
print(f'{"edad":>5} {"amp":>10} | {"N":>4} | {"P(cont)":>8} | {"rest.med":>8}')
for k in [3, 5, 8, 12]:
    for amp_lo, amp_hi, lab in [(0.01, 0.025, '1-2.5%'), (0.025, 0.05, '2.5-5%'), (0.05, 1.0, '>5%')]:
        mask = (dur >= k) & (amps >= amp_lo) & (amps < amp_hi)
        sub = dur[mask]
        if len(sub) < 10:
            continue
        cont = (sub >= k + 1).mean()
        rest_med = np.median(sub - k)
        print(f'{k:>4}b {lab:>10} | {len(sub):>4} | {cont:>7.1%} | {rest_med:>7.0f}b')
