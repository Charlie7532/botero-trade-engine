#!/usr/bin/env python3
"""
credit_easing_pisos.py — Hipótesis: "sin crédito la caída no tiene fondo"
=======================================================================

Testea si CREDIT easing (HYG/LQD subiendo, spread crediticio bajando) es
condición necesaria/suficiente para que un drawdown de SPY forme piso real.

MÉTODO:
  1. Identificar TODOS los drawdowns de SPY (tramos MAX→MIN en zigzag zz25)
  2. Medir si CREDIT hizo easing en ventana CORTA previa al piso (K=1,3,5 pivotes)
  3. Clasificar drawdowns: EASING (credit subió) vs SIN_EASING (credit no subió)
  4. Medir forward SPY después del piso para cada grupo con CI95 bootstrap 3000
  5. Veredicto: ¿condición necesaria? ¿condición suficiente?

DATOS: data/research/pivots/quants_obs.pkl (1,590 pivotes SPY zz25, 1993-2026)

REGLAS: DATO MATA RELATO. CI95 + N. WINS/LOSSES SEPARADOS. ANTI-ADULACIÓN.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

# ── Bootstrap helpers ──
def bootstrap_ci_mean(values, n_boot=3000, seed=42):
    """CI95 de la media via bootstrap."""
    vals = np.asarray(values, dtype=float)
    vals = vals[~np.isnan(vals)]
    if len(vals) < 5:
        return np.nan, np.nan
    rng = np.random.RandomState(seed)
    means = np.array([rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(n_boot)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

def bootstrap_ci_wr(events, n_boot=3000, seed=42):
    """CI95 de win rate via bootstrap."""
    ev = np.asarray(events, dtype=float)
    ev = ev[~np.isnan(ev)]
    if len(ev) < 5:
        return np.nan, np.nan
    rng = np.random.RandomState(seed)
    rates = np.array([rng.choice(ev, size=len(ev), replace=True).mean() for _ in range(n_boot)])
    return float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5))

def bootstrap_ci_pctile(values, pct=50, n_boot=3000, seed=42):
    """CI95 de un percentil via bootstrap."""
    vals = np.asarray(values, dtype=float)
    vals = vals[~np.isnan(vals)]
    if len(vals) < 5:
        return np.nan, np.nan
    rng = np.random.RandomState(seed)
    pcts = np.array([np.percentile(rng.choice(vals, size=len(vals), replace=True), pct) for _ in range(n_boot)])
    return float(np.percentile(pcts, 2.5)), float(np.percentile(pcts, 97.5))


# ══════════════════════════════════════════════════════════════════════════════
# PASO 0: Cargar datos
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("  CREDIT EASING PISOS — Test de hipótesis")
print("  'sin crédito la caída no tiene fondo'")
print("=" * 80)

df = pd.read_pickle('data/research/pivots/quants_obs.pkl')
print(f"\nCargados {len(df)} pivotes zz25 ({df['pivot_date'].min()} → {df['pivot_date'].max()})")

# Convertir pivot_date a datetime si no lo es
if not pd.api.types.is_datetime64_any_dtype(df['pivot_date']):
    df['pivot_date'] = pd.to_datetime(df['pivot_date'])

# ══════════════════════════════════════════════════════════════════════════════
# PASO 1: Identificar TODOS los drawdowns significativos
# ══════════════════════════════════════════════════════════════════════════════
# Un drawdown = tramo MAX→MIN. En el pivote MIN, prev_leg_return es el retorno
# de la pierna bajista que terminó en ese piso.
# Filtramos MIN pivots con prev_leg_return < 0 (drawdown real).

min_mask = (df['pivot_type'] == 'MIN') & (df['prev_leg_return'].notna())
min_df = df[min_mask].copy()
min_df = min_df.reset_index(drop=True)

# El índice original en el DataFrame completo
min_indices = np.where(min_mask)[0]

# Para cada MIN, el inicio del drawdown es el MAX anterior (índice - 1)
drawdowns = []
for i, (local_idx, global_idx) in enumerate(zip(min_df.index, min_indices)):
    dd_return = min_df.loc[local_idx, 'prev_leg_return']  # negativo = drawdown
    
    # El inicio es el MAX anterior
    if global_idx > 0:
        prev_row = df.iloc[global_idx - 1]
        start_date = prev_row['pivot_date']
        start_credit_val = prev_row['credit_val']
    else:
        start_date = None
        start_credit_val = np.nan
    
    floor_date = min_df.loc[local_idx, 'pivot_date']
    floor_credit_val = min_df.loc[local_idx, 'credit_val']
    daily_bounce = min_df.loc[local_idx, 'daily_return_pct']
    duration_bars = min_df.loc[local_idx, 'prev_leg_duration']
    
    # Forward return: next row's prev_leg_return (bull leg from floor)
    if global_idx + 1 < len(df):
        next_row = df.iloc[global_idx + 1]
        fwd_return = next_row['prev_leg_return']
        fwd_cascade_50 = next_row['cascade_50'] if 'cascade_50' in next_row.index else np.nan
        fwd_cascade_75 = next_row['cascade_75'] if 'cascade_75' in next_row.index else np.nan
    else:
        fwd_return = np.nan
        fwd_cascade_50 = np.nan
        fwd_cascade_75 = np.nan
    
    # Cascade desde este piso (si el MIN mismo cascades)
    cascade_50 = min_df.loc[local_idx, 'cascade_50'] if 'cascade_50' in min_df.columns else np.nan
    cascade_75 = min_df.loc[local_idx, 'cascade_75'] if 'cascade_75' in min_df.columns else np.nan
    
    drawdowns.append({
        'idx': global_idx,
        'start_date': start_date,
        'floor_date': floor_date,
        'dd_return': dd_return,           # negativo = magnitud del drawdown
        'dd_magnitude': abs(dd_return),    # magnitud absoluta
        'duration_bars': duration_bars,
        'daily_bounce': daily_bounce,
        'start_credit_val': start_credit_val,
        'floor_credit_val': floor_credit_val,
        'fwd_return': fwd_return,          # forward return (bull leg)
        'cascade_50': cascade_50,
        'cascade_75': cascade_75,
        'fwd_cascade_50': fwd_cascade_50,
        'fwd_cascade_75': fwd_cascade_75,
    })

print(f"Drawdowns identificados (MIN pivots): {len(drawdowns)}")

# Filtrar por magnitud mínima
for threshold, label in [(0.02, ">2%"), (0.05, ">5%"), (0.10, ">10%")]:
    n = sum(1 for d in drawdowns if d['dd_magnitude'] > threshold)
    print(f"  Drawdowns {label}: {n}")

# ══════════════════════════════════════════════════════════════════════════════
# PASO 2: Medir CREDIT easing en ventana CORTA previa al piso
# ══════════════════════════════════════════════════════════════════════════════
# EASING = credit_val(t_piso) > credit_val(t_piso − K pivotes)
# CREDIT subiendo = spread crediticio bajando = easing

for K in [1, 3, 5]:
    key_easing = f'easing_K{K}'
    key_delta = f'credit_delta_K{K}'
    for d in drawdowns:
        global_idx = d['idx']
        lookback_idx = global_idx - K
        if lookback_idx >= 0:
            credit_back = df.iloc[lookback_idx]['credit_val']
            floor_credit = d['floor_credit_val']
            if pd.notna(floor_credit) and pd.notna(credit_back):
                d[key_delta] = float(floor_credit - credit_back)
                d[key_easing] = d[key_delta] > 0
            else:
                d[key_delta] = np.nan
                d[key_easing] = np.nan
        else:
            d[key_delta] = np.nan
            d[key_easing] = np.nan

# ══════════════════════════════════════════════════════════════════════════════
# PASO 3: Clasificar drawdowns
# ══════════════════════════════════════════════════════════════════════════════
# GRUPO A: EASING — CREDIT subió en la ventana previa al piso
# GRUPO B: SIN_EASING — CREDIT no subió

# También medir easing desde el INICIO del drawdown
for d in drawdowns:
    if pd.notna(d['start_credit_val']) and pd.notna(d['floor_credit_val']):
        d['credit_dd_delta'] = float(d['floor_credit_val'] - d['start_credit_val'])
        d['easing_full_dd'] = d['credit_dd_delta'] > 0
    else:
        d['credit_dd_delta'] = np.nan
        d['easing_full_dd'] = np.nan


# ══════════════════════════════════════════════════════════════════════════════
# PASO 4: Medir forward SPY después del piso
# ══════════════════════════════════════════════════════════════════════════════

def analyze_group(dd_list, group_name, K_values=[1, 3, 5]):
    """
    Para un grupo de drawdowns, analizar forward returns.
    Retorna dict con estadísticas para cada K y threshold.
    """
    results = {'group_name': group_name, 'n_total': len(dd_list)}
    
    for dd_threshold, dd_label in [(0.02, ">2%"), (0.05, ">5%"), (0.10, ">10%")]:
        filtered = [d for d in dd_list if d['dd_magnitude'] > dd_threshold]
        dd_key = f'dd_{dd_label.replace(">","gt").replace("%","pct")}'
        results[dd_key] = {'n': len(filtered)}
        
        if len(filtered) == 0:
            continue
        
        # Forward return (full bull leg)
        fwd_rets = np.array([d['fwd_return'] for d in filtered if pd.notna(d['fwd_return'])])
        fwd_wins = fwd_rets > 0
        fwd_losses = fwd_rets < 0
        
        results[dd_key]['forward'] = {
            'n': len(fwd_rets),
            'mean': float(np.mean(fwd_rets)),
            'median': float(np.median(fwd_rets)),
            'std': float(np.std(fwd_rets)),
            'min': float(np.min(fwd_rets)),
            'max': float(np.max(fwd_rets)),
            'p5': float(np.percentile(fwd_rets, 5)),
            'p25': float(np.percentile(fwd_rets, 25)),
            'p75': float(np.percentile(fwd_rets, 75)),
            'p95': float(np.percentile(fwd_rets, 95)),
            'ci95_mean': list(bootstrap_ci_mean(fwd_rets)),
            'ci95_median': list(bootstrap_ci_pctile(fwd_rets, 50)),
            'win_rate': float(np.mean(fwd_wins)),
            'ci95_wr': list(bootstrap_ci_wr(fwd_wins)),
            'wins': {
                'n': int(np.sum(fwd_wins)),
                'mean': float(np.mean(fwd_rets[fwd_wins])) if np.sum(fwd_wins) > 0 else np.nan,
                'median': float(np.median(fwd_rets[fwd_wins])) if np.sum(fwd_wins) > 0 else np.nan,
                'std': float(np.std(fwd_rets[fwd_wins])) if np.sum(fwd_wins) > 0 else np.nan,
                'min': float(np.min(fwd_rets[fwd_wins])) if np.sum(fwd_wins) > 0 else np.nan,
                'max': float(np.max(fwd_rets[fwd_wins])) if np.sum(fwd_wins) > 0 else np.nan,
            },
            'losses': {
                'n': int(np.sum(fwd_losses)),
                'mean': float(np.mean(fwd_rets[fwd_losses])) if np.sum(fwd_losses) > 0 else np.nan,
                'median': float(np.median(fwd_rets[fwd_losses])) if np.sum(fwd_losses) > 0 else np.nan,
                'std': float(np.std(fwd_rets[fwd_losses])) if np.sum(fwd_losses) > 0 else np.nan,
                'min': float(np.min(fwd_rets[fwd_losses])) if np.sum(fwd_losses) > 0 else np.nan,
                'max': float(np.max(fwd_rets[fwd_losses])) if np.sum(fwd_losses) > 0 else np.nan,
            },
            'profit_factor': float(np.sum(fwd_rets[fwd_wins]) / abs(np.sum(fwd_rets[fwd_losses]))) 
                             if np.sum(fwd_losses) > 0 and abs(np.sum(fwd_rets[fwd_losses])) > 0 
                             else (np.inf if np.sum(fwd_wins) > 0 else 0.0),
        }
        
        # Win/Loss ratio
        if np.sum(fwd_wins) > 0 and np.sum(fwd_losses) > 0:
            avg_win = np.mean(fwd_rets[fwd_wins])
            avg_loss = abs(np.mean(fwd_rets[fwd_losses]))
            wl = avg_win / avg_loss if avg_loss > 0 else np.inf
            kelly = float(np.mean(fwd_wins)) - (1 - float(np.mean(fwd_wins))) / wl if wl > 0 else -1.0
        else:
            wl = np.inf if np.sum(fwd_wins) > 0 else 0.0
            kelly = 1.0 if np.sum(fwd_losses) == 0 and np.sum(fwd_wins) > 0 else -1.0
        
        results[dd_key]['forward']['wl_ratio'] = float(wl) if wl != np.inf else 'inf'
        results[dd_key]['forward']['kelly'] = float(kelly)
        
        # Cascade rates
        cascade_50_vals = np.array([d['cascade_50'] for d in filtered if pd.notna(d['cascade_50'])])
        cascade_75_vals = np.array([d['cascade_75'] for d in filtered if pd.notna(d['cascade_75'])])
        
        if len(cascade_50_vals) > 0:
            results[dd_key]['cascade_50_rate'] = float(np.mean(cascade_50_vals))
            results[dd_key]['cascade_50_ci95'] = list(bootstrap_ci_wr(cascade_50_vals))
        if len(cascade_75_vals) > 0:
            results[dd_key]['cascade_75_rate'] = float(np.mean(cascade_75_vals))
            results[dd_key]['cascade_75_ci95'] = list(bootstrap_ci_wr(cascade_75_vals))
        
        # Floor bounce (daily_return_pct at the floor)
        bounces = np.array([d['daily_bounce'] for d in filtered if pd.notna(d['daily_bounce'])])
        if len(bounces) > 0:
            results[dd_key]['floor_bounce'] = {
                'mean': float(np.mean(bounces)),
                'median': float(np.median(bounces)),
                'ci95_mean': list(bootstrap_ci_mean(bounces)),
            }
    
    return results


# ── Análisis por K y por threshold ──
all_results = {}

for K in [1, 3, 5]:
    easing_key = f'easing_K{K}'
    
    # Filtrar drawdowns con CREDIT disponible
    valid_dds = [d for d in drawdowns if pd.notna(d.get(easing_key))]
    
    easing_dds = [d for d in valid_dds if d[easing_key] == True]
    no_easing_dds = [d for d in valid_dds if d[easing_key] == False]
    
    print(f"\n{'─'*80}")
    print(f"  K={K} pivotes: EASING={len(easing_dds)}, SIN_EASING={len(no_easing_dds)}")
    print(f"  (CREDIT disponible: {len(valid_dds)}/{len(drawdowns)} drawdowns)")
    
    all_results[f'K{K}_EASING'] = analyze_group(easing_dds, f'K={K} EASING')
    all_results[f'K{K}_SIN_EASING'] = analyze_group(no_easing_dds, f'K={K} SIN_EASING')

# ── También: easing desde el inicio del drawdown ──
valid_full = [d for d in drawdowns if pd.notna(d.get('easing_full_dd'))]
easing_full = [d for d in valid_full if d['easing_full_dd'] == True]
no_easing_full = [d for d in valid_full if d['easing_full_dd'] == False]
all_results['FULL_EASING'] = analyze_group(easing_full, 'FULL DD EASING')
all_results['FULL_SIN_EASING'] = analyze_group(no_easing_full, 'FULL DD SIN EASING')


# ══════════════════════════════════════════════════════════════════════════════
# PASO 5: Veredicto
# ══════════════════════════════════════════════════════════════════════════════

def compute_verdict(all_results):
    """
    Computar veredicto sobre:
    - ¿CREDIT easing es CONDICIÓN NECESARIA? (¿hay pisos reales SIN easing?)
    - ¿CREDIT easing es CONDICIÓN SUFICIENTE? (¿todo easing produce piso real?)
    - ¿La señal es más fuerte en drawdowns grandes?
    """
    verdict = {
        'hipotesis': 'sin crédito la caída no tiene fondo',
        'fecha_analisis': datetime.now().isoformat(),
        'data': 'quants_obs.pkl (1,590 pivotes SPY zz25, 1993-2026)',
    }
    
    # Para cada K, analizar la tabla de contingencia
    for K in [1, 3, 5]:
        easing_key = f'easing_K{K}'
        valid_dds = [d for d in drawdowns if pd.notna(d.get(easing_key))]
        
        for dd_threshold, dd_label in [(0.02, "gt2pct"), (0.05, "gt5pct"), (0.10, "gt10pct")]:
            filtered = [d for d in valid_dds if d['dd_magnitude'] > dd_threshold]
            
            if len(filtered) < 20:
                continue
            
            easing = [d for d in filtered if d[easing_key] == True]
            no_easing = [d for d in filtered if d[easing_key] == False]
            
            # Piso real = forward return > 0
            easing_real = [d for d in easing if pd.notna(d['fwd_return']) and d['fwd_return'] > 0]
            easing_false = [d for d in easing if pd.notna(d['fwd_return']) and d['fwd_return'] <= 0]
            no_easing_real = [d for d in no_easing if pd.notna(d['fwd_return']) and d['fwd_return'] > 0]
            no_easing_false = [d for d in no_easing if pd.notna(d['fwd_return']) and d['fwd_return'] <= 0]
            
            n_easing = len(easing)
            n_no_easing = len(no_easing)
            n_easing_real = len(easing_real)
            n_easing_false = len(easing_false)
            n_no_easing_real = len(no_easing_real)
            n_no_easing_false = len(no_easing_false)
            
            # Forward return stats
            easing_fwd = np.array([d['fwd_return'] for d in easing if pd.notna(d['fwd_return'])])
            no_easing_fwd = np.array([d['fwd_return'] for d in no_easing if pd.notna(d['fwd_return'])])
            
            # Condición necesaria: ¿hay pisos reales SIN easing?
            # Si n_no_easing_real > 0 → easing NO es necesaria
            necesaria = n_no_easing_real == 0
            
            # Condición suficiente: ¿todo easing produce piso real?
            # Si n_easing_false == 0 → easing ES suficiente
            suficiente = n_easing_false == 0 and n_easing > 0
            
            # Sensibilidad: P(easing | piso real)
            sens = n_easing_real / (n_easing_real + n_no_easing_real) if (n_easing_real + n_no_easing_real) > 0 else np.nan
            
            # Especificidad: P(no easing | piso falso)
            espec = n_no_easing_false / (n_easing_false + n_no_easing_false) if (n_easing_false + n_no_easing_false) > 0 else np.nan
            
            # Valor predictivo positivo: P(piso real | easing)
            vpp = n_easing_real / n_easing if n_easing > 0 else np.nan
            
            # Valor predictivo negativo: P(piso falso | no easing)
            vpn = n_no_easing_false / n_no_easing if n_no_easing > 0 else np.nan
            
            # Test de diferencia de medias bootstrap
            if len(easing_fwd) >= 5 and len(no_easing_fwd) >= 5:
                rng = np.random.RandomState(42)
                diffs = []
                for _ in range(3000):
                    e_sample = rng.choice(easing_fwd, size=len(easing_fwd), replace=True)
                    ne_sample = rng.choice(no_easing_fwd, size=len(no_easing_fwd), replace=True)
                    diffs.append(np.mean(e_sample) - np.mean(ne_sample))
                diffs = np.array(diffs)
                diff_mean = float(np.mean(diffs))
                diff_ci95 = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
                diff_p_le_0 = float(np.mean(diffs <= 0))
            else:
                diff_mean = np.nan
                diff_ci95 = [np.nan, np.nan]
                diff_p_le_0 = np.nan
            
            entry = {
                'n_total': len(filtered),
                'n_easing': n_easing,
                'n_sin_easing': n_no_easing,
                'easing_real_floor': n_easing_real,
                'easing_false_floor': n_easing_false,
                'no_easing_real_floor': n_no_easing_real,
                'no_easing_false_floor': n_no_easing_false,
                'necesaria': necesaria,
                'suficiente': suficiente,
                'sensibilidad': round(sens, 4) if not np.isnan(sens) else None,
                'especificidad': round(espec, 4) if not np.isnan(espec) else None,
                'vpp': round(vpp, 4) if not np.isnan(vpp) else None,
                'vpn': round(vpn, 4) if not np.isnan(vpn) else None,
                'forward_mean_easing': round(float(np.mean(easing_fwd)), 4) if len(easing_fwd) > 0 else None,
                'forward_mean_no_easing': round(float(np.mean(no_easing_fwd)), 4) if len(no_easing_fwd) > 0 else None,
                'diff_means': round(diff_mean, 4),
                'diff_ci95': [round(x, 4) for x in diff_ci95],
                'diff_p_le_0': round(diff_p_le_0, 4),
                'diff_significativo': diff_ci95[0] > 0 if not np.isnan(diff_ci95[0]) else None,
                'easing_fwd': {
                    'n': len(easing_fwd),
                    'mean': round(float(np.mean(easing_fwd)), 4) if len(easing_fwd) > 0 else None,
                    'ci95': [round(x, 4) for x in bootstrap_ci_mean(easing_fwd)] if len(easing_fwd) >= 5 else None,
                },
                'no_easing_fwd': {
                    'n': len(no_easing_fwd),
                    'mean': round(float(np.mean(no_easing_fwd)), 4) if len(no_easing_fwd) > 0 else None,
                    'ci95': [round(x, 4) for x in bootstrap_ci_mean(no_easing_fwd)] if len(no_easing_fwd) >= 5 else None,
                },
            }
            
            key = f'K{K}_dd_{dd_label}'
            verdict[key] = entry
    
    # ── Resumen ejecutivo ──
    summary_lines = []
    summary_lines.append("=" * 70)
    summary_lines.append("  VEREDICTO: ¿CREDIT easing es condición necesaria/suficiente?")
    summary_lines.append("=" * 70)
    
    for K in [1, 3, 5]:
        for dd_threshold, dd_label in [(0.02, ">2%"), (0.05, ">5%"), (0.10, ">10%")]:
            key = f'K{K}_dd_{dd_label.replace(">","gt").replace("%","pct")}'
            if key not in verdict:
                continue
            v = verdict[key]
            summary_lines.append(f"\n  K={K}, DD {dd_label} (N={v['n_total']}):")
            summary_lines.append(f"    EASING: {v['n_easing']} drawdowns → {v['easing_real_floor']} pisos reales, {v['easing_false_floor']} falsos (VPP={v['vpp']})")
            summary_lines.append(f"    SIN_EASING: {v['n_sin_easing']} drawdowns → {v['no_easing_real_floor']} pisos reales, {v['no_easing_false_floor']} falsos (VPN={v['vpn']})")
            summary_lines.append(f"    Forward EASING: {v['forward_mean_easing']} vs SIN_EASING: {v['forward_mean_no_easing']}")
            summary_lines.append(f"    Diferencia: {v['diff_means']} CI95 {v['diff_ci95']} (p≤0: {v['diff_p_le_0']})")
            
            if v['necesaria']:
                summary_lines.append(f"    ✓ CONDICIÓN NECESARIA: 0 pisos reales sin easing")
            else:
                summary_lines.append(f"    ✗ NO es necesaria: {v['no_easing_real_floor']} pisos reales sin easing")
            
            if v['suficiente']:
                summary_lines.append(f"    ✓ CONDICIÓN SUFICIENTE: 0 falsos positivos con easing")
            else:
                summary_lines.append(f"    ✗ NO es suficiente: {v['easing_false_floor']} falsos positivos con easing")
            
            if v['diff_significativo']:
                summary_lines.append(f"    ✓ DIFERENCIA SIGNIFICATIVA: easing > no easing")
            elif v['diff_significativo'] is False:
                summary_lines.append(f"    ✗ DIFERENCIA NO SIGNIFICATIVA (CI95 cruza cero)")
    
    # ── Veredicto final ──
    summary_lines.append(f"\n{'─'*70}")
    summary_lines.append("  CONCLUSIÓN FINAL:")
    
    # Encontrar la mejor señal (mayor diferencia)
    best_diff = -999
    best_key = None
    for key, v in verdict.items():
        if key.startswith('K') and 'diff_means' in v and v['diff_means'] is not None:
            if v['diff_means'] > best_diff:
                best_diff = v['diff_means']
                best_key = key
    
    if best_key:
        v = verdict[best_key]
        summary_lines.append(f"  Mejor discriminación: {best_key}")
        summary_lines.append(f"  Diferencia EASING vs SIN_EASING: {v['diff_means']:.4f} CI95 {v['diff_ci95']}")
        
        if v['diff_significativo']:
            summary_lines.append(f"  → CREDIT easing DISCRIMINA pisos reales vs falsos (diferencia significativa)")
        else:
            summary_lines.append(f"  → CREDIT easing NO discrimina significativamente (CI95 cruza cero)")
        
        if v['necesaria']:
            summary_lines.append(f"  → CREDIT easing ES condición necesaria para piso real")
        else:
            summary_lines.append(f"  → CREDIT easing NO es condición necesaria ({v['no_easing_real_floor']} pisos sin easing)")
        
        if v['suficiente']:
            summary_lines.append(f"  → CREDIT easing ES condición suficiente (0 falsos positivos)")
        else:
            summary_lines.append(f"  → CREDIT easing NO es condición suficiente ({v['easing_false_floor']} falsos positivos)")
    
    # Honestidad: si no hay señal fuerte, decirlo
    all_diffs_sig = [verdict[k].get('diff_significativo', False) for k in verdict if k.startswith('K')]
    if not any(all_diffs_sig):
        summary_lines.append(f"\n  ⚠️ HONESTIDAD: En ninguna configuración K×threshold la diferencia")
        summary_lines.append(f"     EASING vs SIN_EASING es estadísticamente significativa.")
        summary_lines.append(f"     → La hipótesis 'sin crédito la caída no tiene fondo' NO SE SOSTIENE")
        summary_lines.append(f"       con la evidencia disponible en ventanas CORTAS (K=1,3,5 pivotes).")
    
    verdict['resumen'] = '\n'.join(summary_lines)
    return verdict


verdict = compute_verdict(all_results)

# ── Imprimir resumen ──
print(verdict['resumen'])

# ── Guardar reporte ──
report = {
    'metadata': {
        'script': 'credit_easing_pisos.py',
        'hipotesis': 'sin crédito la caída no tiene fondo',
        'fecha': datetime.now().isoformat(),
        'data': 'quants_obs.pkl (1,590 pivotes SPY zz25, 1993-2026)',
        'n_total_drawdowns': len(drawdowns),
        'n_drawdowns_gt2pct': sum(1 for d in drawdowns if d['dd_magnitude'] > 0.02),
        'n_drawdowns_gt5pct': sum(1 for d in drawdowns if d['dd_magnitude'] > 0.05),
        'n_drawdowns_gt10pct': sum(1 for d in drawdowns if d['dd_magnitude'] > 0.10),
        'credit_coverage': sum(1 for d in drawdowns if pd.notna(d['floor_credit_val'])),
        'credit_coverage_pct': round(sum(1 for d in drawdowns if pd.notna(d['floor_credit_val'])) / len(drawdowns) * 100, 1),
    },
    'grupos': {},
    'veredicto': verdict,
}

# Convertir grupos a formato serializable
for key, val in all_results.items():
    # Convertir numpy types
    report['grupos'][key] = json.loads(
        json.dumps(val, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x))
    )

# Limpiar veredicto de NaN
def clean_nan(obj):
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, float) and np.isnan(obj):
        return None
    elif isinstance(obj, float) and np.isinf(obj):
        return 'inf' if obj > 0 else '-inf'
    return obj

report_clean = clean_nan(report)

with open('data/research/stations/credit_easing_pisos_report.json', 'w') as f:
    json.dump(report_clean, f, indent=2, ensure_ascii=False, default=str)

print(f"\n✅ Reporte guardado: data/research/credit_easing_pisos_report.json")
print("DONE.")