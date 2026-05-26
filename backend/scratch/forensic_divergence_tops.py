"""
Forensia de Techos Perdidos — Divergencias + Regresiones
=========================================================
1. Regression features: sigmas, slopes, deceleration
2. DIVERGENCIAS: precio HH pero indicador LH → bearish divergence
3. ¿Cuáles divergencias anticipan los techos que perdemos?

"En un bull, RSI=70 no es sobrecompra. Pero RSI=70 cuando RSI_anterior=75
 con precio nuevo máximo → ESO es la señal." — System Architect
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

REGRESSION_FEATS = [
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'tide_slope', 'current_slope', 'wave_slope',
    'compression_ratio', 'kalman_velocity',
    'vol_up_down_ratio', 'fear_level', 'rsi_value',
    'd_sigma_wave', 'd_tide_slope', 'd_kalman_velocity',
    'd_wave_accel', 'd_compression_ratio', 'd_vol_up_down_ratio',
    'd_rsi_value', 'd_fear_level',
]

# ═══════════════════════════════════════════════════════════
# BUILD: Feature matrix at consecutive zigzag MAX points (for divergence)
# ═══════════════════════════════════════════════════════════
banner("1. BUILDING DIVERGENCE MATRIX")

rows = []
for tk in sorted(zz['ticker'].unique()):
    tk_tape = tape_by_tk.get(tk)
    if tk_tape is None: continue
    
    maxs = zz[(zz['ticker']==tk) & (zz['tp_type']=='MAX')].sort_values('timestamp').reset_index(drop=True)
    
    for i in range(1, len(maxs)):
        curr = maxs.iloc[i]
        prev = maxs.iloc[i-1]
        
        # Price pattern: HH or LH?
        price_hh = curr['price'] > prev['price']
        
        # Get features at CURRENT max
        td = (tk_tape['timestamp'] - curr['timestamp']).abs()
        if td.min() > pd.Timedelta(days=3): continue
        center = td.idxmin()
        if center < LOOK_BACK: continue
        
        # Get features at PREVIOUS max
        td_prev = (tk_tape['timestamp'] - prev['timestamp']).abs()
        if td_prev.min() > pd.Timedelta(days=3): continue
        prev_center = td_prev.idxmin()
        
        # Detection classification
        window = tk_tape.iloc[center - LOOK_BACK: center + 1]
        strong = any(window[h].max() >= THR_STRONG for h in SHORT_HEADS if h in window.columns)
        weak = any(window[h].max() >= 0.50 for h in SHORT_HEADS if h in window.columns)
        cls = 'DETECTED' if strong else ('PARTIAL' if weak else 'MISSED')
        
        bar_curr = tk_tape.iloc[center]
        bar_prev = tk_tape.iloc[prev_center]
        
        row = {
            'ticker': tk, 'timestamp': curr['timestamp'],
            'classification': cls,
            'price_pattern': 'HH' if price_hh else 'LH',
            'price_curr': curr['price'], 'price_prev': prev['price'],
            'swing_return': curr['swing_return'],
            'swing_days': curr['swing_days'],
        }
        
        # Features at current and previous MAX
        for f in REGRESSION_FEATS:
            if f in tk_tape.columns:
                val_curr = bar_curr.get(f, np.nan)
                val_prev = bar_prev.get(f, np.nan)
                row[f'{f}_curr'] = val_curr
                row[f'{f}_prev'] = val_prev
                
                # DIVERGENCE: price HH but feature LH (bearish divergence)
                if not np.isnan(val_curr) and not np.isnan(val_prev):
                    feat_hh = val_curr > val_prev
                    if price_hh and not feat_hh:
                        row[f'{f}_div'] = 'BEARISH'  # Price HH, feature LH
                    elif not price_hh and feat_hh:
                        row[f'{f}_div'] = 'BULLISH'  # Price LH, feature HH
                    else:
                        row[f'{f}_div'] = 'NONE'     # Aligned
                else:
                    row[f'{f}_div'] = np.nan
        
        rows.append(row)

df = pd.DataFrame(rows)
det = df[df['classification']=='DETECTED']
mis = df[df['classification'].isin(['MISSED','PARTIAL'])]
print(f"  Total consecutive MAX pairs: {len(df)}")
print(f"  Detected: {len(det)}, Partial+Missed: {len(mis)}")

# ═══════════════════════════════════════════════════════════
banner("2. DIVERGENCE POWER — ¿Qué divergencias predicen techos perdidos?")
# ═══════════════════════════════════════════════════════════

# Only look at HH (price higher high) — that's where divergences matter
hh = df[df['price_pattern']=='HH']
hh_det = hh[hh['classification']=='DETECTED']
hh_mis = hh[hh['classification'].isin(['MISSED','PARTIAL'])]

print(f"\n  Focus: Higher Highs only (N={len(hh)}, Det={len(hh_det)}, Partial+Miss={len(hh_mis)})")

section("Bearish Divergence Rate: price HH but feature LH")
print(f"  {'Feature':>25s} │ {'Det Bear%':>10s} │ {'Miss Bear%':>11s} │ {'Lift':>6s} │ Power")
print(f"  {'─'*70}")

div_results = []
for f in REGRESSION_FEATS:
    div_col = f'{f}_div'
    if div_col not in df.columns: continue
    
    det_bear = (hh_det[div_col]=='BEARISH').mean() * 100 if len(hh_det) > 0 else 0
    mis_bear = (hh_mis[div_col]=='BEARISH').mean() * 100 if len(hh_mis) > 0 else 0
    
    lift = mis_bear - det_bear
    if mis_bear > det_bear and lift > 3:
        power = "★★★" if lift > 10 else ("★★" if lift > 5 else "★")
    else:
        power = ""
    
    div_results.append((f, det_bear, mis_bear, lift, power))

div_results.sort(key=lambda x: -x[3])
for f, db, mb, lift, power in div_results:
    print(f"  {f:>25s} │ {db:>9.1f}% │ {mb:>10.1f}% │ {lift:>+5.1f} │ {power}")

# ═══════════════════════════════════════════════════════════
banner("3. REGRESSION FEATURES — Nivel absoluto en techos DETECTED vs MISSED")
# ═══════════════════════════════════════════════════════════

print(f"\n  {'Feature':>25s} │ {'Detected':>9s} │ {'Part+Miss':>10s} │ {'Delta':>9s} │ {'Cohen d':>8s} │ Power")
print(f"  {'─'*85}")

feat_results = []
for f in REGRESSION_FEATS:
    curr_col = f'{f}_curr'
    if curr_col not in df.columns: continue
    dv = det[curr_col].dropna()
    mv = mis[curr_col].dropna()
    if len(dv) < 30 or len(mv) < 30: continue
    
    delta = mv.mean() - dv.mean()
    pooled = np.sqrt((dv.std()**2 + mv.std()**2)/2)
    d = delta/pooled if pooled > 0 else 0
    _, pval = sp_stats.mannwhitneyu(dv, mv, alternative='two-sided')
    
    if pval < 0.001 and abs(d) > 0.3:
        power = "★★★ STRONG"
    elif pval < 0.01 and abs(d) > 0.15:
        power = "★★  USEFUL"
    elif pval < 0.05:
        power = "★   WEAK"
    else:
        power = "    none"
    
    feat_results.append((f, dv.mean(), mv.mean(), delta, d, pval, power))

feat_results.sort(key=lambda x: -abs(x[4]))
for f, dv, mv, delta, d, pval, power in feat_results:
    print(f"  {f:>25s} │ {dv:>+9.4f} │ {mv:>+10.4f} │ {delta:>+8.4f} │ {d:>+7.3f} │ {power}")

# ═══════════════════════════════════════════════════════════
banner("4. SLOPE DECELERATION — ¿Se aplana la regresión antes del techo?")
# ═══════════════════════════════════════════════════════════

for slope in ['tide_slope', 'current_slope', 'wave_slope']:
    curr_col = f'{slope}_curr'
    prev_col = f'{slope}_prev'
    if curr_col not in df.columns or prev_col not in df.columns: continue
    
    section(f"{slope} change (curr - prev MAX)")
    df[f'{slope}_change'] = df[curr_col] - df[prev_col]
    
    for label, sub in [('DETECTED', det), ('PARTIAL+MISSED', mis)]:
        # Recompute since det/mis are from before adding column
        sub_data = df[df['classification']=='DETECTED'] if label=='DETECTED' else df[df['classification'].isin(['MISSED','PARTIAL'])]
        vals = sub_data[f'{slope}_change'].dropna()
        if len(vals) < 20: continue
        pneg = (vals < 0).mean() * 100
        print(f"    {label:>15s}: mean_change={vals.mean():+.5f}  P(decel)={pneg:.1f}%  median={vals.median():+.5f}")

# ═══════════════════════════════════════════════════════════
banner("5. COMPOSITE DIVERGENCE SCORE")
# ═══════════════════════════════════════════════════════════

print("  Counting how many features show bearish divergence at each HH top")

for _, row in hh.iterrows():
    bear_count = sum(1 for f in REGRESSION_FEATS 
                     if f'{f}_div' in hh.columns and row.get(f'{f}_div') == 'BEARISH')
    df.loc[df.index == row.name, 'n_bearish_divs'] = bear_count

hh = df[df['price_pattern']=='HH']  # refresh
section("Distribution of bearish divergence count")
for label, sub in [('DETECTED', hh[hh['classification']=='DETECTED']),
                    ('PARTIAL+MISSED', hh[hh['classification'].isin(['MISSED','PARTIAL'])])]:
    if 'n_bearish_divs' not in sub.columns or len(sub) < 10: continue
    vals = sub['n_bearish_divs'].dropna()
    print(f"    {label:>15s}: mean={vals.mean():.1f}  P(≥5)={((vals>=5).mean()*100):.1f}%  P(≥8)={((vals>=8).mean()*100):.1f}%")

section("Can # of divergences predict missed tops?")
hh_v = hh.dropna(subset=['n_bearish_divs'])
if len(hh_v) > 50:
    dv = hh_v[hh_v['classification']=='DETECTED']['n_bearish_divs']
    mv = hh_v[hh_v['classification'].isin(['MISSED','PARTIAL'])]['n_bearish_divs']
    if len(dv) > 20 and len(mv) > 20:
        _, pval = sp_stats.mannwhitneyu(dv, mv, alternative='two-sided')
        d = (mv.mean() - dv.mean()) / np.sqrt((dv.std()**2 + mv.std()**2)/2)
        print(f"    Detected mean={dv.mean():.1f}  Missed mean={mv.mean():.1f}")
        print(f"    Cohen d={d:+.3f}  p={pval:.4f} {'★★★' if pval<0.001 else '★★' if pval<0.01 else '★' if pval<0.05 else 'ns'}")

# ═══════════════════════════════════════════════════════════
banner("6. RANKING FINAL — ¿Qué debemos ESCUCHAR para techos?")
# ═══════════════════════════════════════════════════════════

print("""
  CATEGORÍAS:
    📐 REGRESSION (sigma, distancia a línea)  — ¿qué tan lejos está el precio?
    📈 SLOPE (pendiente, ángulo)               — ¿se está aplanando?
    🔀 DIVERGENCE (precio vs indicador)        — ¿el indicador YA giró?
    📏 BANDWIDTH (compression)                  — ¿las bandas se abren?
    📊 VOLUME (up/down ratio)                   — ¿quién domina?
    ⚠️  MOMENTUM (RSI)                          — NO CONFIABLE en tendencia
""")

print(f"  {'Rank':>4s} │ {'Feature':>25s} │ {'Cohen d':>8s} │ {'Why it works for tops':>35s}")
print(f"  {'─'*80}")

explanations = {
    'compression_ratio': 'Bandas abiertas = sin tensión',
    'd_compression_ratio': 'Bandas abriéndose = pérdida de estructura',
    'sigma_wave': 'Precio lejos de regresión corta',
    'd_sigma_wave': 'Velocidad de alejamiento',
    'rsi_value': '⚠️ NO CONFIABLE en bull fuerte',
    'd_rsi_value': 'Pero el CAMBIO de RSI sí importa',
    'fear_level': 'Complacencia = miedo bajo',
    'd_fear_level': 'El miedo deja de subir',
    'kalman_velocity': 'Kalman desacelera antes del giro',
    'd_kalman_velocity': 'Cambio en velocidad del filtro',
    'current_slope': 'Pendiente intermedia se aplana',
    'wave_slope': 'Pendiente corta se aplana',
    'tide_slope': 'Pendiente larga se aplana',
    'vol_up_down_ratio': 'Volumen comprador se agota',
    'd_vol_up_down_ratio': 'Cambio en asimetría de volumen',
    'sigma_tide': 'Precio lejos de regresión larga',
    'sigma_current': 'Precio lejos de regresión media',
    'd_wave_accel': 'Aceleración de onda se frena',
    'd_tide_slope': 'Pendiente macro desacelera',
}

for i, (f, dv, mv, delta, d, pval, power) in enumerate(feat_results[:15]):
    exp = explanations.get(f, '')
    print(f"  #{i+1:>3d} │ {f:>25s} │ {d:>+7.3f} │ {exp:>35s}")

store.close()
banner("FORENSIA DIVERGENCIA + REGRESIÓN COMPLETA")
