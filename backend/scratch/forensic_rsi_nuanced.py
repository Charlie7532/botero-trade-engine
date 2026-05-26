"""
Forensia RSI Matizada — "Poco confiable no significa inútil"
=============================================================
System Architect: "El RSI sigue proporcionando señales de sobrecompra
que deben ser consideradas, y divergencias."

Hipótesis a testear:
1. RSI DIVERGENCIA (precio HH, RSI LH) → ¿mejor que sigma divergencias?
2. RSI overbought (>70) + contexto = ¿señal válida cuando se combina?
3. RSI overbought + slope decelerando = ¿mejora la detección de techos?
4. d_rsi_value como proxy de divergencia implícita
5. ¿Cuándo SÍ funciona RSI overbought como señal?
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def banner(t):
    print(f"\n{'═'*100}\n  {t}\n{'═'*100}")

def section(t):
    print(f"\n  ── {t} ──")

store = TimescaleDataStore()
zz = pd.read_sql("SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker,timestamp", store.engine)
tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker,timestamp", store.engine)
tape_by_tk = {tk: grp.reset_index(drop=True) for tk, grp in tape.groupby('ticker')}

LOOK_BACK = 5
THR_STRONG = 0.60
SHORT_HEADS = ['p_short_entry','p_swing_exit','p_trend_reversal','p_pullback_depth']

# ═══════════════════════════════════════════════════════════
banner("1. RSI DIVERGENCIA vs SIGMA DIVERGENCIA — Head to Head")
# ═══════════════════════════════════════════════════════════

print("  Para cada par de MAXs consecutivos del zigzag:")
print("  ¿Cuántos techos perdidos captura cada tipo de divergencia?")

rows = []
for tk in sorted(zz['ticker'].unique()):
    tk_tape = tape_by_tk.get(tk)
    if tk_tape is None: continue
    maxs = zz[(zz['ticker']==tk) & (zz['tp_type']=='MAX')].sort_values('timestamp').reset_index(drop=True)
    
    for i in range(1, len(maxs)):
        curr, prev = maxs.iloc[i], maxs.iloc[i-1]
        price_hh = curr['price'] > prev['price']
        if not price_hh: continue  # Only HH (where divergences matter)
        
        td = (tk_tape['timestamp'] - curr['timestamp']).abs()
        if td.min() > pd.Timedelta(days=3): continue
        center = td.idxmin()
        if center < LOOK_BACK: continue
        
        td_prev = (tk_tape['timestamp'] - prev['timestamp']).abs()
        if td_prev.min() > pd.Timedelta(days=3): continue
        prev_center = td_prev.idxmin()
        
        window = tk_tape.iloc[center - LOOK_BACK: center + 1]
        strong = any(window[h].max() >= THR_STRONG for h in SHORT_HEADS if h in window.columns)
        weak = any(window[h].max() >= 0.50 for h in SHORT_HEADS if h in window.columns)
        cls = 'DETECTED' if strong else ('PARTIAL' if weak else 'MISSED')
        
        bar_c, bar_p = tk_tape.iloc[center], tk_tape.iloc[prev_center]
        
        # RSI divergence: price HH but RSI LH
        rsi_div = bar_c.get('rsi_value', np.nan) < bar_p.get('rsi_value', np.nan)
        # Sigma divergences
        sig_c_div = bar_c.get('sigma_current', np.nan) < bar_p.get('sigma_current', np.nan)
        sig_w_div = bar_c.get('sigma_wave', np.nan) < bar_p.get('sigma_wave', np.nan)
        sig_t_div = bar_c.get('sigma_tide', np.nan) < bar_p.get('sigma_tide', np.nan)
        # Slope divergence
        ws_div = bar_c.get('wave_slope', np.nan) < bar_p.get('wave_slope', np.nan)
        # d_rsi (negative = RSI declining = bearish)
        d_rsi = bar_c.get('d_rsi_value', np.nan)
        
        # RSI level
        rsi_curr = bar_c.get('rsi_value', np.nan)
        rsi_ob = rsi_curr > 70 if not np.isnan(rsi_curr) else False
        rsi_extreme = rsi_curr > 75 if not np.isnan(rsi_curr) else False
        
        # Slope decel
        ws_c = bar_c.get('wave_slope', np.nan)
        ws_p = bar_p.get('wave_slope', np.nan)
        slope_decel = ws_c < ws_p if not np.isnan(ws_c) and not np.isnan(ws_p) else False
        
        rows.append({
            'ticker': tk, 'timestamp': curr['timestamp'],
            'classification': cls,
            'swing_return': curr['swing_return'],
            'rsi_curr': rsi_curr,
            'rsi_div': rsi_div,
            'sig_c_div': sig_c_div,
            'sig_w_div': sig_w_div,
            'sig_t_div': sig_t_div,
            'ws_div': ws_div,
            'rsi_ob': rsi_ob,
            'rsi_extreme': rsi_extreme,
            'd_rsi': d_rsi,
            'slope_decel': slope_decel,
            # Combinations
            'rsi_div_AND_sig_c': rsi_div and sig_c_div,
            'rsi_ob_AND_slope_decel': rsi_ob and slope_decel,
            'rsi_div_AND_slope_decel': rsi_div and slope_decel,
            'rsi_ob_AND_rsi_div': rsi_ob and rsi_div,
            'triple': rsi_div and sig_c_div and slope_decel,
        })

df = pd.DataFrame(rows)
det = df[df['classification']=='DETECTED']
mis = df[df['classification'].isin(['MISSED','PARTIAL'])]

section("Individual divergence capture rates")
print(f"  {'Divergence type':>30s} │ {'Det rate':>8s} │ {'Miss rate':>9s} │ {'Lift':>6s} │ {'Unique to miss':>14s}")
print(f"  {'─'*80}")

for col, label in [
    ('rsi_div', 'RSI divergence (LH)'),
    ('sig_c_div', 'Sigma_current div (LH)'),
    ('sig_w_div', 'Sigma_wave div (LH)'),
    ('sig_t_div', 'Sigma_tide div (LH)'),
    ('ws_div', 'Wave_slope div (LH)'),
]:
    dr = det[col].mean() * 100
    mr = mis[col].mean() * 100
    lift = mr - dr
    print(f"  {label:>30s} │ {dr:>7.1f}% │ {mr:>8.1f}% │ {lift:>+5.1f} │ {'★' if lift > 3 else ''}")

# ═══════════════════════════════════════════════════════════
banner("2. RSI OVERBOUGHT — ¿Cuándo SÍ funciona?")
# ═══════════════════════════════════════════════════════════

section("RSI overbought (>70) sola vs combinada")
print(f"  {'Condition':>40s} │ {'N fire':>7s} │ {'Det':>5s} │ {'Miss':>5s} │ {'MissRate':>8s} │ {'MissRate base':>13s}")
print(f"  {'─'*90}")

base_miss_rate = len(mis) / len(df) * 100

for col, label in [
    ('rsi_ob', 'RSI > 70 (sola)'),
    ('rsi_extreme', 'RSI > 75 (extrema)'),
    ('rsi_div', 'RSI divergence (sola)'),
    ('sig_c_div', 'Sigma_current divergence'),
    ('slope_decel', 'Slope decelerating'),
    ('rsi_ob_AND_slope_decel', 'RSI>70 + Slope decel'),
    ('rsi_ob_AND_rsi_div', 'RSI>70 + RSI divergence'),
    ('rsi_div_AND_sig_c', 'RSI div + Sigma_c div'),
    ('rsi_div_AND_slope_decel', 'RSI div + Slope decel'),
    ('triple', 'RSI div + Sigma_c + Slope decel'),
]:
    sub = df[df[col] == True]
    n = len(sub)
    if n < 10: continue
    d = (sub['classification']=='DETECTED').sum()
    m = (sub['classification'].isin(['MISSED','PARTIAL'])).sum()
    mr = m / n * 100
    print(f"  {label:>40s} │ {n:>7d} │ {d:>5d} │ {m:>5d} │ {mr:>7.1f}% │ {base_miss_rate:>12.1f}%")

# ═══════════════════════════════════════════════════════════
banner("3. RSI OVERBOUGHT + DIVERGENCIA = ¿MEJORA TECHOS PERDIDOS?")
# ═══════════════════════════════════════════════════════════

section("Focus: Of the MISSED+PARTIAL tops, how many had RSI signals?")
print(f"  Total Partial+Missed HH tops: {len(mis)}")

for col, label in [
    ('rsi_ob', 'RSI > 70'),
    ('rsi_extreme', 'RSI > 75'),
    ('rsi_div', 'RSI bearish divergence'),
    ('rsi_ob_AND_rsi_div', 'RSI>70 AND RSI divergence'),
    ('rsi_ob_AND_slope_decel', 'RSI>70 AND slope decel'),
    ('rsi_div_AND_slope_decel', 'RSI div AND slope decel'),
    ('triple', 'RSI div + Sigma_c + Slope decel'),
]:
    had_signal = mis[col].sum()
    pct = had_signal / len(mis) * 100
    print(f"    {label:>40s}: {had_signal:>4.0f} / {len(mis)} ({pct:.1f}%)")

# ═══════════════════════════════════════════════════════════
banner("4. d_rsi_value — ¿El CAMBIO de RSI complementa las regresiones?")
# ═══════════════════════════════════════════════════════════

section("d_rsi_value at HH tops: Detected vs Missed")
for label, sub in [('DETECTED', det), ('PARTIAL+MISSED', mis)]:
    vals = sub['d_rsi'].dropna()
    if len(vals) < 20: continue
    neg_pct = (vals < 0).mean() * 100
    print(f"    {label:>15s}: mean={vals.mean():+.2f}  P(d_rsi<0)={neg_pct:.1f}%  median={vals.median():+.2f}")

section("d_rsi < 0 (RSI declining) as top detector")
neg_drsi = df[df['d_rsi'] < 0]
pos_drsi = df[df['d_rsi'] >= 0]
if len(neg_drsi) > 50 and len(pos_drsi) > 50:
    mr_neg = neg_drsi['classification'].isin(['MISSED','PARTIAL']).mean() * 100
    mr_pos = pos_drsi['classification'].isin(['MISSED','PARTIAL']).mean() * 100
    print(f"    d_rsi < 0 (declining): {mr_neg:.1f}% miss rate (N={len(neg_drsi)})")
    print(f"    d_rsi ≥ 0 (rising):    {mr_pos:.1f}% miss rate (N={len(pos_drsi)})")
    print(f"    → When RSI is declining at a HH, miss rate {'HIGHER' if mr_neg > mr_pos else 'LOWER'}")

# ═══════════════════════════════════════════════════════════
banner("5. RSI REGIMES — ¿En qué rango de RSI detectamos MEJOR?")
# ═══════════════════════════════════════════════════════════

section("Detection rate by RSI bucket at HH tops")
df['rsi_bucket'] = pd.cut(df['rsi_curr'], bins=[0, 40, 50, 60, 65, 70, 75, 80, 100],
                           labels=['<40', '40-50', '50-60', '60-65', '65-70', '70-75', '75-80', '>80'])

print(f"  {'RSI bucket':>12s} │ {'N':>5s} │ {'Detected':>8s} │ {'Missed':>7s} │ {'MissRate':>8s} │ {'Avg swing':>10s}")
print(f"  {'─'*65}")

for bucket in ['<40', '40-50', '50-60', '60-65', '65-70', '70-75', '75-80', '>80']:
    sub = df[df['rsi_bucket'] == bucket]
    n = len(sub)
    if n < 10: continue
    d = (sub['classification']=='DETECTED').sum()
    m = (sub['classification'].isin(['MISSED','PARTIAL'])).sum()
    avg_sw = sub['swing_return'].abs().mean() * 100
    print(f"  {bucket:>12s} │ {n:>5d} │ {d:>8d} │ {m:>7d} │ {m/n*100:>7.1f}% │ {avg_sw:>+9.1f}%")

# ═══════════════════════════════════════════════════════════
banner("6. VEREDICTO FINAL RSI")
# ═══════════════════════════════════════════════════════════

# Best RSI-based composite
best_composites = []
for col, label in [
    ('rsi_ob', 'RSI>70 sola'),
    ('rsi_div', 'RSI div sola'),
    ('rsi_ob_AND_slope_decel', 'RSI>70 + slope decel'),
    ('rsi_ob_AND_rsi_div', 'RSI>70 + RSI div'),
    ('rsi_div_AND_sig_c', 'RSI div + sigma_c div'),
    ('triple', 'Triple (RSI+sigma+slope)'),
]:
    sub = df[df[col]==True]
    if len(sub) < 10: continue
    mr = sub['classification'].isin(['MISSED','PARTIAL']).mean() * 100
    # Of missed tops, how many does this catch?
    catch = mis[col].sum() / len(mis) * 100
    best_composites.append((label, len(sub), mr, catch))

best_composites.sort(key=lambda x: -x[3])  # Sort by catch rate

print(f"\n  {'Signal':>35s} │ {'N events':>8s} │ {'MissRate':>8s} │ {'Catch%':>7s}")
print(f"  {'─'*65}")
for label, n, mr, catch in best_composites:
    print(f"  {label:>35s} │ {n:>8d} │ {mr:>7.1f}% │ {catch:>6.1f}%")

print(f"\n  Base miss rate (all HH): {base_miss_rate:.1f}%")

store.close()
banner("FORENSIA RSI MATIZADA COMPLETA")
