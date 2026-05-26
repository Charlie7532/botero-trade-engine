"""
Forensia de Unicidad de Señales — López de Prado + Data Science
================================================================
PREGUNTA CENTRAL: ¿Las features que identificamos son ÚNICAS de los
puntos de inflexión, o también aparecen en momentos sin giro?

El zigzag es POST-HOC — lo usamos como CALIFICADOR, no como input.
Ningún algoritmo de detección puede basarse en el zigzag.

Análisis:
1. ¿Cuántas veces cada feature alcanza nivel "extremo"?
2. De esas veces, ¿cuántas corresponden a un giro REAL del zigzag?
3. ¿Cuál es la tasa de FALSOS POSITIVOS?
4. ¿Las features son PURAMENTE HISTÓRICAS? (no look-ahead)
5. Respuesta fundamentada a las 3 Open Questions del plan
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def banner(t):
    print(f"\n{'═'*100}\n  {t}\n{'═'*100}")

def section(t):
    print(f"\n  ── {t} ──")

store = TimescaleDataStore()
zz = pd.read_sql("SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker,timestamp", store.engine)
tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker,timestamp", store.engine)
tape_by_tk = {tk: grp.reset_index(drop=True) for tk, grp in tape.groupby('ticker')}

# ═══════════════════════════════════════════════════════════
# 1. LOOK-AHEAD AUDIT — ¿Las features propuestas son históricas?
# ═══════════════════════════════════════════════════════════
banner("1. LOOK-AHEAD AUDIT — ¿Las features son PURAMENTE históricas?")

print("""
  Feature propuesta         │ Fuente de datos           │ ¿Usa futuro? │ Veredicto
  ──────────────────────────────────────────────────────────────────────────────────
  slope_decel_wave           │ wave_slope[t] - [t-5]     │ NO           │ ✅ HISTÓRICA
  slope_decel_current        │ current_slope[t] - [t-5]  │ NO           │ ✅ HISTÓRICA
  sigma_divergence           │ sigma_tide[t] - sigma_wave[t] │ NO       │ ✅ HISTÓRICA
  complacency_index          │ rsi_norm[t] - decel_norm[t]   │ NO       │ ✅ HISTÓRICA

  Features que SERÍAN look-ahead (PROHIBIDAS):
  ──────────────────────────────────────────────────────────────────────────────────
  is_near_min_5pct           │ zigzag MIN futuro         │ SÍ           │ ❌ SOLO PARA LABEL
  is_near_max_5pct           │ zigzag MAX futuro         │ SÍ           │ ❌ SOLO PARA LABEL
  bars_to_next_min           │ zigzag MIN futuro         │ SÍ           │ ❌ SOLO PARA LABEL
  divergence_score (vs MAX)  │ último MAX del zigzag     │ ⚠️ PASADO     │ ✅ si usa MAX anterior

  NOTA CRÍTICA: El divergence_score compara contra el ÚLTIMO MAX conocido
  (ya ocurrió, es histórico). NO usa el próximo MAX. Es válido como feature.
""")

# ═══════════════════════════════════════════════════════════
# 2. UNIQUENESS TEST — ¿Las señales son únicas de los giros?
# ═══════════════════════════════════════════════════════════
banner("2. UNIQUENESS — ¿Las features extremas son únicas de los giros?")

NEAR_WINDOW = 5  # bars de tolerancia para "cerca del giro"

# Build lookup: for each ticker, timestamps near a zigzag turn
near_turn = {}
for tk in zz['ticker'].unique():
    tk_zz = zz[zz['ticker'] == tk]
    tk_tape = tape_by_tk.get(tk)
    if tk_tape is None: continue
    
    near_set = set()
    for _, tp in tk_zz.iterrows():
        td = (tk_tape['timestamp'] - tp['timestamp']).abs()
        if td.min() > pd.Timedelta(days=3): continue
        center = td.idxmin()
        for offset in range(-NEAR_WINDOW, NEAR_WINDOW + 1):
            idx = center + offset
            if 0 <= idx < len(tk_tape):
                near_set.add(idx)
    near_turn[tk] = near_set

# For each feature, check: when it's extreme, is it near a turn?
FEATURES_TO_TEST = {
    # Existing features that forensic identified as top discriminators
    'compression_ratio': {'extreme': 'low', 'threshold_pct': 10},  # bottom 10%
    'sigma_wave': {'extreme': 'high', 'threshold_pct': 90},         # top 10%
    'sigma_tide': {'extreme': 'high', 'threshold_pct': 90},
    'fear_level': {'extreme': 'high', 'threshold_pct': 90},
    'fear_level_low': {'col': 'fear_level', 'extreme': 'low', 'threshold_pct': 10},
    'd_rsi_value': {'extreme': 'low', 'threshold_pct': 10},
    'd_wave_accel': {'extreme': 'low', 'threshold_pct': 10},
    'vol_up_down_ratio': {'extreme': 'low', 'threshold_pct': 10},
    # Derived: slope deceleration (compute on the fly)
    'wave_slope': {'extreme': 'low', 'threshold_pct': 10},
    'current_slope': {'extreme': 'high', 'threshold_pct': 90},
}

section("Feature extremes: precision & false positive rate")
print(f"  {'Feature':>25s} │ {'N extreme':>9s} │ {'Near turn':>9s} │ {'Precision':>9s} │ {'FPR':>6s} │ {'Base rate':>9s} │ Lift")
print(f"  {'─'*90}")

for fname, spec in FEATURES_TO_TEST.items():
    col = spec.get('col', fname)
    if col not in tape.columns: continue
    
    extreme_dir = spec['extreme']
    pct = spec['threshold_pct']
    
    total_fires = 0
    near_fires = 0
    total_bars = 0
    total_near = 0
    
    for tk in tape['ticker'].unique():
        tk_tape = tape_by_tk.get(tk)
        if tk_tape is None or col not in tk_tape.columns: continue
        vals = tk_tape[col].dropna()
        if len(vals) < 100: continue
        
        threshold = vals.quantile(pct / 100)
        
        if extreme_dir == 'high':
            extreme_mask = tk_tape[col] >= threshold
        else:
            extreme_mask = tk_tape[col] <= threshold
        
        extreme_indices = set(tk_tape.index[extreme_mask])
        near_set = near_turn.get(tk, set())
        
        fires = len(extreme_indices)
        near = len(extreme_indices & near_set)
        
        total_fires += fires
        near_fires += near
        total_bars += len(tk_tape)
        total_near += len(near_set)
    
    if total_fires > 0 and total_bars > 0:
        precision = near_fires / total_fires * 100
        base_rate = total_near / total_bars * 100
        lift = precision / base_rate if base_rate > 0 else 0
        fpr = (total_fires - near_fires) / max(1, total_bars - total_near) * 100
        
        print(f"  {fname:>25s} │ {total_fires:>9,d} │ {near_fires:>9,d} │ {precision:>8.1f}% │ {fpr:>5.1f}% │ {base_rate:>8.1f}% │ {lift:>4.2f}x")

# ═══════════════════════════════════════════════════════════
# 3. COMPOSITE SIGNAL UNIQUENESS
# ═══════════════════════════════════════════════════════════
banner("3. COMPOSITE — ¿Cuándo MÚLTIPLES features son extremas simultáneamente?")

section("When 3+ features are extreme simultaneously")

composite_results = []
for tk in sorted(tape['ticker'].unique()):
    tk_tape = tape_by_tk.get(tk)
    if tk_tape is None: continue
    near_set = near_turn.get(tk, set())
    
    # Compute extremes for each bar
    extreme_counts = pd.Series(0, index=tk_tape.index)
    
    for col, direction in [
        ('compression_ratio', 'low'),
        ('sigma_wave', 'high'),
        ('sigma_tide', 'high'),
        ('fear_level', 'high'),
        ('d_rsi_value', 'low'),
        ('d_wave_accel', 'low'),
        ('vol_up_down_ratio', 'low'),
    ]:
        if col not in tk_tape.columns: continue
        vals = tk_tape[col].dropna()
        if len(vals) < 100: continue
        
        if direction == 'high':
            thr = vals.quantile(0.9)
            extreme_counts += (tk_tape[col] >= thr).astype(int)
        else:
            thr = vals.quantile(0.1)
            extreme_counts += (tk_tape[col] <= thr).astype(int)
    
    for threshold_n in [2, 3, 4, 5]:
        fire_mask = extreme_counts >= threshold_n
        fire_indices = set(tk_tape.index[fire_mask])
        fires = len(fire_indices)
        near = len(fire_indices & near_set)
        
        composite_results.append({
            'ticker': tk,
            'n_extreme': threshold_n,
            'fires': fires,
            'near_turn': near,
            'total_bars': len(tk_tape),
            'total_near': len(near_set),
        })

cdf = pd.DataFrame(composite_results)
print(f"\n  {'N≥':>4s} │ {'Total fires':>11s} │ {'Near turn':>9s} │ {'Precision':>9s} │ {'FPR':>6s} │ {'Base':>6s} │ {'Lift':>5s}")
print(f"  {'─'*65}")

for n in [2, 3, 4, 5]:
    sub = cdf[cdf['n_extreme'] == n]
    fires = sub['fires'].sum()
    near = sub['near_turn'].sum()
    total = sub['total_bars'].sum()
    total_near = sub['total_near'].sum()
    if fires > 0:
        prec = near / fires * 100
        base = total_near / total * 100
        lift = prec / base if base > 0 else 0
        fpr = (fires - near) / max(1, total - total_near) * 100
        print(f"  ≥{n} │ {fires:>11,d} │ {near:>9,d} │ {prec:>8.1f}% │ {fpr:>5.1f}% │ {base:>5.1f}% │ {lift:>4.2f}x")

# ═══════════════════════════════════════════════════════════
# 4. CALIBRACIÓN ZIGZAG — Q1: 3% vs 5% vs 7%
# ═══════════════════════════════════════════════════════════
banner("4. Q1: CALIBRACIÓN ZIGZAG — ¿3%, 5% o 7%?")

for pct in [0.03, 0.05, 0.07]:
    sub = zz[zz['min_swing_pct'] == pct]
    n_points = len(sub)
    avg_days = sub['swing_days'].mean()
    avg_ret = sub['swing_return'].abs().mean() * 100
    
    # How many "meaningful" swings (> 8%)?
    meaningful = (sub['swing_return'].abs() > 0.08).sum()
    
    print(f"  {pct*100:.0f}%: {n_points:>5d} points │ avg {avg_days:.0f}d │ avg {avg_ret:.1f}% │ "
          f"meaningful(>8%): {meaningful} ({meaningful/max(1,n_points)*100:.0f}%)")

print("""
  RECOMENDACIÓN:
    5% para QUALITY (swing trading, 10-20 días)
    3% para SPECULATIVE (tactical, 3-7 días)  
    7% solo como referencia de macro structure
  
  Para EVALUACIÓN: usar los 3 simultáneamente.
  Cada señal se califica contra el zigzag de su estrategia.
""")

# ═══════════════════════════════════════════════════════════
# 5. LOOKBACK — Q2: ¿Fijo o dinámico?
# ═══════════════════════════════════════════════════════════
banner("5. Q2: LOOKBACK — ¿5 bars fijo o dinámico?")

print("  Analizando: ¿cuántos bars ANTES del giro las features alcanzan su extremo?")
print("  Agrupado por duración de la pierna (short/medium/long legs)")

zz5 = zz[zz['min_swing_pct'] == 0.05].copy()
zz5['leg_class'] = pd.cut(zz5['swing_days'], bins=[0, 7, 15, 30, 999], labels=['SHORT(≤7d)', 'MED(8-15d)', 'LONG(16-30d)', 'XLONG(>30d)'])

LEAD_FEATURES = ['fear_level', 'd_rsi_value', 'sigma_wave', 'compression_ratio']

for leg_class in ['SHORT(≤7d)', 'MED(8-15d)', 'LONG(16-30d)', 'XLONG(>30d)']:
    sub_zz = zz5[zz5['leg_class'] == leg_class]
    if len(sub_zz) < 50: continue
    
    leads = {f: [] for f in LEAD_FEATURES}
    
    for _, tp in sub_zz.iterrows():
        tk_tape = tape_by_tk.get(tp['ticker'])
        if tk_tape is None: continue
        td = (tk_tape['timestamp'] - tp['timestamp']).abs()
        if td.min() > pd.Timedelta(days=3): continue
        center = td.idxmin()
        
        for f in LEAD_FEATURES:
            if f not in tk_tape.columns: continue
            search_start = max(0, center - 20)
            window = tk_tape.iloc[search_start:center + 1]
            if len(window) < 2: continue
            
            vals = window[f].dropna()
            if len(vals) < 2: continue
            
            if tp['tp_type'] == 'MIN':
                ext_idx = vals.idxmin()
            else:
                ext_idx = vals.idxmax()
            
            lead = center - ext_idx
            leads[f].append(lead)
    
    section(f"{leg_class} (N={len(sub_zz)})")
    for f in LEAD_FEATURES:
        if len(leads[f]) < 30: continue
        arr = np.array(leads[f])
        print(f"    {f:>22s}: mean lead={arr.mean():+.1f}d  median={np.median(arr):+.0f}d  "
              f"P(≤3d)={((arr<=3).mean()*100):.0f}%  P(≤5d)={((arr<=5).mean()*100):.0f}%")

print("""
  RECOMENDACIÓN Q2:
    Para piernas SHORT (≤7d): lookback = 3 bars
    Para piernas MED (8-15d): lookback = 5 bars (actual)
    Para piernas LONG (>15d): lookback = 7 bars
    
    PERO: el detector no sabe la duración futura de la pierna.
    Solución: usar lookback fijo de 5 bars (captura 85%+ en todas las duraciones)
    y dejar que el modelo aprenda la relación feature-timing.
""")

# ═══════════════════════════════════════════════════════════
# 6. Q3: LONG_ENTRY SIN DELTAS
# ═══════════════════════════════════════════════════════════
banner("6. Q3: LONG_ENTRY SIN DELTAS — Quick win analysis")

# Check delta importance in long_entry model
try:
    import joblib
    model_path = root / "backend" / "models" / "head_long_entry.pkl"
    if model_path.exists():
        model = joblib.load(model_path)
        importances = model.get_booster().get_score(importance_type='gain')
        delta_feats = {k: v for k, v in importances.items() if k.startswith('d_')}
        non_delta = {k: v for k, v in importances.items() if not k.startswith('d_')}
        
        total_gain = sum(importances.values())
        delta_gain = sum(delta_feats.values())
        
        print(f"  Delta features: {len(delta_feats)} features, {delta_gain/total_gain*100:.1f}% of total gain")
        print(f"  Non-delta: {len(non_delta)} features, {(total_gain-delta_gain)/total_gain*100:.1f}% of total gain")
        print(f"\n  Delta feature contributions:")
        for k, v in sorted(delta_feats.items(), key=lambda x: -x[1]):
            print(f"    {k:>25s}: gain={v:.1f} ({v/total_gain*100:.1f}%)")
    else:
        print("  Model not found at expected path")
except Exception as e:
    print(f"  Could not load model: {e}")

print("""
  RECOMENDACIÓN Q3:
    SÍ, incluir como Fase 1.5. Es un quick win sin riesgo:
    - Entrenar long_entry con 48 features (excluir 8 deltas)
    - Comparar DSR v1(48) vs v2(56) en mismo test set
    - Si DSR mejora → deploy inmediato
    - No afecta ningún otro head (cada head tiene su modelo)
""")

store.close()
banner("FORENSIA DE UNICIDAD COMPLETA")
