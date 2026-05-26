"""
Forensia de Techos Perdidos — Regresiones, Sigmas, Velocidad Angular
=====================================================================
RSI es UNRELIABLE en mercados tendenciales (sobrecompra en bull = normal).
¿Qué SÍ funciona para detectar techos de agotamiento?

Hipótesis del System Architect:
  1. Sigma de regresión (distancia a la línea) → ¿precio en extremo?
  2. Desaceleración de pendiente (slope change) → el ángulo deja de crecer
  3. Divergencia entre sigmas (tide vs wave vs current) → las bandas se desalinean
  4. Velocidad de cambio del ángulo → d(slope)/dt

"No escuches al RSI — escucha a la geometría de la regresión."
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

# Available regression-based features in tape
REG_FEATURES = [
    'sigma_tide', 'sigma_current', 'sigma_wave',    # distance from regression (in σ)
    'tide_slope', 'current_slope', 'wave_slope',     # slope angles
    'd_tide_slope', 'd_sigma_wave',                   # derivatives (acceleration)
    'd_kalman_velocity', 'd_wave_accel',              # second derivatives
    'compression_ratio', 'd_compression_ratio',       # band width
    'vol_up_down_ratio', 'd_vol_up_down_ratio',       # volume asymmetry
    'kalman_velocity',                                 # kalman trend speed
    'fear_level', 'd_fear_level',                     # fear (for reference)
    'rsi_value', 'd_rsi_value',                       # RSI (for comparison)
]

# Check which exist
avail = [f for f in REG_FEATURES if f in tape.columns]
print(f"Available regression features: {len(avail)}/{len(REG_FEATURES)}")

# ═══════════════════════════════════════════════════════════
# BUILD: Feature snapshots at ALL zigzag MAX points
# + classify as DETECTED vs MISSED
# ═══════════════════════════════════════════════════════════
banner("1. BUILDING FEATURE MATRIX AT ZIGZAG TOPS")

LOOK_BACK = 5
THR_STRONG = 0.60
SHORT_HEADS = ['p_short_entry','p_swing_exit','p_trend_reversal','p_pullback_depth']

rows = []
for _, tp in zz[zz['tp_type']=='MAX'].iterrows():
    tk_tape = tape_by_tk.get(tp['ticker'])
    if tk_tape is None or len(tk_tape) < LOOK_BACK + 1:
        continue
    td = (tk_tape['timestamp'] - tp['timestamp']).abs()
    if td.min() > pd.Timedelta(days=3): continue
    center = td.idxmin()
    if center < LOOK_BACK: continue
    
    window = tk_tape.iloc[center - LOOK_BACK: center + 1]
    strong = any(window[h].max() >= THR_STRONG for h in SHORT_HEADS if h in window.columns)
    weak = any(window[h].max() >= 0.50 for h in SHORT_HEADS if h in window.columns)
    cls = 'DETECTED' if strong else ('PARTIAL' if weak else 'MISSED')
    
    bar = tk_tape.iloc[center]
    # Also get bar at -5 for slope change computation
    bar_5 = tk_tape.iloc[max(0, center-5)]
    
    row = {
        'ticker': tp['ticker'], 'timestamp': tp['timestamp'],
        'classification': cls, 'swing_return': tp['swing_return'],
        'swing_days': tp['swing_days'],
    }
    
    for f in avail:
        row[f] = bar.get(f, np.nan)
        # Compute manual slope change over 5 bars for key features
    
    # Derived: slope deceleration (difference from 5 bars ago)
    for s in ['tide_slope', 'current_slope', 'wave_slope']:
        if s in tk_tape.columns:
            row[f'{s}_decel'] = bar.get(s, np.nan) - bar_5.get(s, np.nan)
    
    # Derived: sigma divergence (tide - wave, tide - current)
    row['sigma_div_tide_wave'] = bar.get('sigma_tide', np.nan) - bar.get('sigma_wave', np.nan)
    row['sigma_div_tide_current'] = bar.get('sigma_tide', np.nan) - bar.get('sigma_current', np.nan)
    row['sigma_div_wave_current'] = bar.get('sigma_wave', np.nan) - bar.get('sigma_current', np.nan)
    
    # Derived: sigma max (the most extreme sigma among the 3)
    sigmas = [bar.get('sigma_tide', np.nan), bar.get('sigma_current', np.nan), bar.get('sigma_wave', np.nan)]
    valid_sigs = [s for s in sigmas if not np.isnan(s)]
    row['sigma_max'] = max(valid_sigs) if valid_sigs else np.nan
    row['sigma_mean'] = np.mean(valid_sigs) if valid_sigs else np.nan
    
    rows.append(row)

df = pd.DataFrame(rows)
det = df[df['classification']=='DETECTED']
mis = df[df['classification'].isin(['MISSED','PARTIAL'])]
print(f"  Detected: {len(det)}, Partial+Missed: {len(mis)}")

# ═══════════════════════════════════════════════════════════
banner("2. REGRESSION FEATURES — ¿Cuáles diferencian DETECTED vs MISSED?")
# ═══════════════════════════════════════════════════════════

all_feats = avail + ['tide_slope_decel', 'current_slope_decel', 'wave_slope_decel',
                      'sigma_div_tide_wave', 'sigma_div_tide_current', 'sigma_div_wave_current',
                      'sigma_max', 'sigma_mean']

print(f"\n  {'Feature':>28s} │ {'Detected':>9s} │ {'Partial+Miss':>12s} │ {'Delta':>9s} │ {'d':>6s} │ {'p-val':>8s} │ Power")
print(f"  {'─'*95}")

results = []
for f in all_feats:
    if f not in df.columns: continue
    dv = det[f].dropna()
    mv = mis[f].dropna()
    if len(dv) < 30 or len(mv) < 30: continue
    
    delta = mv.mean() - dv.mean()
    pooled = np.sqrt((dv.std()**2 + mv.std()**2)/2)
    d_cohen = delta/pooled if pooled > 0 else 0
    _, pval = sp_stats.mannwhitneyu(dv, mv, alternative='two-sided')
    
    if pval < 0.001 and abs(d_cohen) > 0.3:
        power = "★★★ STRONG"
    elif pval < 0.01 and abs(d_cohen) > 0.15:
        power = "★★  USEFUL"
    elif pval < 0.05:
        power = "★   WEAK"
    else:
        power = "    NONE"
    
    results.append((f, dv.mean(), mv.mean(), delta, d_cohen, pval, power))

results.sort(key=lambda x: -abs(x[4]))
for f, dv, mv, delta, d, pval, power in results:
    print(f"  {f:>28s} │ {dv:>+9.4f} │ {mv:>+12.4f} │ {delta:>+8.4f} │ {d:>+5.2f} │ {pval:>8.4f} │ {power}")

# ═══════════════════════════════════════════════════════════
banner("3. SLOPE DECELERATION — ¿La pendiente se aplana antes del techo?")
# ═══════════════════════════════════════════════════════════

for slope in ['tide_slope', 'current_slope', 'wave_slope']:
    decel = f'{slope}_decel'
    if decel not in df.columns: continue
    section(f"{slope} deceleration")
    
    for label, sub in [('DETECTED', det), ('PARTIAL+MISSED', mis)]:
        vals = sub[decel].dropna()
        if len(vals) < 20: continue
        pneg = (vals < 0).mean() * 100  # % decelerating
        print(f"    {label:>15s}: mean={vals.mean():+.5f}  P(decel<0)={pneg:.1f}%  median={vals.median():+.5f}")
    
    # Is deceleration different between groups?
    dv, mv = det[decel].dropna(), mis[decel].dropna()
    if len(dv) > 20 and len(mv) > 20:
        _, pval = sp_stats.mannwhitneyu(dv, mv, alternative='two-sided')
        d = (mv.mean() - dv.mean()) / np.sqrt((dv.std()**2 + mv.std()**2)/2)
        print(f"    DIFFERENCE: d={d:+.3f}, p={pval:.4f} {'★ SIGNIFICANT' if pval < 0.05 else 'ns'}")

# ═══════════════════════════════════════════════════════════
banner("4. SIGMA ANALYSIS — ¿La distancia a la regresión anticipa el techo?")
# ═══════════════════════════════════════════════════════════

for sig in ['sigma_tide', 'sigma_current', 'sigma_wave', 'sigma_max', 'sigma_mean']:
    if sig not in df.columns: continue
    section(f"{sig}")
    
    for label, sub in [('DETECTED', det), ('PARTIAL+MISSED', mis)]:
        vals = sub[sig].dropna()
        if len(vals) < 20: continue
        pgt1 = (vals > 1).mean() * 100   # > 1 sigma
        pgt2 = (vals > 2).mean() * 100   # > 2 sigma
        print(f"    {label:>15s}: mean={vals.mean():+.3f}  P(>1σ)={pgt1:.1f}%  P(>2σ)={pgt2:.1f}%")

# ═══════════════════════════════════════════════════════════
banner("5. SIGMA DIVERGENCE — ¿Las líneas se desalinean en techos perdidos?")
# ═══════════════════════════════════════════════════════════

for div in ['sigma_div_tide_wave', 'sigma_div_tide_current', 'sigma_div_wave_current']:
    if div not in df.columns: continue
    section(f"{div}")
    
    for label, sub in [('DETECTED', det), ('PARTIAL+MISSED', mis)]:
        vals = sub[div].dropna()
        if len(vals) < 20: continue
        print(f"    {label:>15s}: mean={vals.mean():+.4f}  std={vals.std():.4f}  P(>0)={((vals>0).mean()*100):.1f}%")

# ═══════════════════════════════════════════════════════════
banner("6. NEW COMPOSITE — Complacency Score")
# ═══════════════════════════════════════════════════════════

print("  Hypothesis: When RSI is high but slopes are decelerating → COMPLACENCY")
print("  Complacency = RSI_normalized × (1 - slope_decel_normalized)")

# Build complacency for all tops
for slope_key in ['wave_slope_decel', 'current_slope_decel']:
    if slope_key not in df.columns: continue
    section(f"Complacency using {slope_key}")
    
    valid = df[['rsi_value', slope_key, 'classification']].dropna()
    if len(valid) < 50: continue
    
    rsi_norm = (valid['rsi_value'] - valid['rsi_value'].mean()) / valid['rsi_value'].std()
    decel_norm = (valid[slope_key] - valid[slope_key].mean()) / valid[slope_key].std()
    
    # Complacency = high RSI + decelerating slope
    # RSI high = positive, decel negative = slope flattening
    valid['complacency'] = rsi_norm - decel_norm  # high when RSI high and slope decelerating
    
    for label in ['DETECTED', 'PARTIAL', 'MISSED']:
        sub = valid[valid['classification']==label]
        if len(sub) < 5: continue
        c = sub['complacency']
        print(f"    {label:>10s} (N={len(sub):>4d}): complacency={c.mean():+.3f}  std={c.std():.3f}")
    
    # ROC: can complacency separate DETECTED from MISSED?
    detected_c = valid[valid['classification']=='DETECTED']['complacency']
    missed_c = valid[valid['classification'].isin(['MISSED','PARTIAL'])]['complacency']
    if len(detected_c) > 20 and len(missed_c) > 20:
        _, pval = sp_stats.mannwhitneyu(detected_c, missed_c, alternative='two-sided')
        d = (missed_c.mean() - detected_c.mean()) / np.sqrt((detected_c.std()**2 + missed_c.std()**2)/2)
        print(f"    SEPARATION: d={d:+.3f}, p={pval:.4f} {'★★★' if pval<0.001 and abs(d)>0.3 else '★★' if pval<0.01 else '★' if pval<0.05 else 'ns'}")

# ═══════════════════════════════════════════════════════════
banner("7. WHAT SHOULD WE LISTEN TO? — Ranking final")
# ═══════════════════════════════════════════════════════════

print("  Features ranked by power to differentiate DETECTED vs MISSED/PARTIAL tops:")
print("  (Higher |d| = more useful for detecting exhaustion tops)")
print()
print(f"  {'Rank':>4s} │ {'Feature':>28s} │ {'Cohen d':>8s} │ {'Category':>12s}")
print(f"  {'─'*60}")

# Use the results from section 2
for i, (f, _, _, _, d, pval, power) in enumerate(results[:15]):
    if 'rsi' in f.lower():
        cat = "⚠️ MOMENTUM"
    elif 'sigma' in f.lower():
        cat = "📐 REGRESSION"
    elif 'slope' in f.lower() or 'decel' in f.lower():
        cat = "📈 SLOPE"
    elif 'compress' in f.lower():
        cat = "📏 BANDWIDTH"
    elif 'fear' in f.lower():
        cat = "😱 SENTIMENT"
    elif 'vol_up' in f.lower():
        cat = "📊 VOLUME"
    elif 'kalman' in f.lower():
        cat = "🎯 KALMAN"
    else:
        cat = ""
    print(f"  #{i+1:>3d} │ {f:>28s} │ {d:>+7.3f} │ {cat}")

store.close()
banner("FORENSIA REGRESSION TOPS COMPLETA")
