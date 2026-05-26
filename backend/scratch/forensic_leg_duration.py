"""
FORENSIA — Duración Estadística de Piernas del Mercado
=======================================================
Comité: López de Prado (estadística), Druckenmiller (timing), Simons (patrones)

Pregunta: ¿Cuánto dura una pierna alcista y bajista del zigzag 5%?
¿Qué horizonte captura el 75% del movimiento?
¿Cómo varía con la volatilidad?

Objetivo: Calibrar HEAD_CONFIGS con datos, no presunciones.
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
zz = pd.read_sql(
    "SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp",
    store.engine
)
print(f"  Total zigzag points: {len(zz):,d}")

# ═══════════════════════════════════════════════════════════
banner("1. DURACIÓN DE PIERNAS — Estadísticas completas")
# ═══════════════════════════════════════════════════════════

legs = []
for tk in sorted(zz['ticker'].unique()):
    tk_zz = zz[zz['ticker'] == tk].sort_values('timestamp').reset_index(drop=True)
    for i in range(1, len(tk_zz)):
        curr = tk_zz.iloc[i]
        prev = tk_zz.iloc[i-1]
        duration = (curr['timestamp'] - prev['timestamp']).days
        ret = (curr['price'] - prev['price']) / prev['price'] * 100
        direction = 'BULL' if curr['tp_type'] == 'MAX' else 'BEAR'
        legs.append({
            'ticker': tk,
            'direction': direction,
            'duration_days': duration,
            'return_pct': ret,
            'abs_return': abs(ret),
            'start_price': prev['price'],
            'end_price': curr['price'],
            'start_date': prev['timestamp'],
            'end_date': curr['timestamp'],
        })

df = pd.DataFrame(legs)
bulls = df[df['direction'] == 'BULL']
bears = df[df['direction'] == 'BEAR']

section("Piernas BULL (MIN → MAX)")
print(f"  N = {len(bulls)}")
for label, vals in [
    ('Duración (días)', bulls['duration_days']),
    ('Return (%)', bulls['return_pct']),
]:
    p5, p25, p50, p75, p95 = np.percentile(vals, [5, 25, 50, 75, 95])
    print(f"    {label:>20s}: mean={vals.mean():>8.1f}  std={vals.std():>7.1f}  "
          f"P5={p5:>7.1f}  P25={p25:>7.1f}  P50={p50:>7.1f}  P75={p75:>7.1f}  P95={p95:>7.1f}")

section("Piernas BEAR (MAX → MIN)")
print(f"  N = {len(bears)}")
for label, vals in [
    ('Duración (días)', bears['duration_days']),
    ('Return (%)', bears['return_pct']),
]:
    p5, p25, p50, p75, p95 = np.percentile(vals, [5, 25, 50, 75, 95])
    print(f"    {label:>20s}: mean={vals.mean():>8.1f}  std={vals.std():>7.1f}  "
          f"P5={p5:>7.1f}  P25={p25:>7.1f}  P50={p50:>7.1f}  P75={p75:>7.1f}  P95={p95:>7.1f}")

# ═══════════════════════════════════════════════════════════
banner("2. ¿QUÉ HORIZONTE CAPTURA EL 75% DEL MOVIMIENTO?")
# ═══════════════════════════════════════════════════════════

section("Si tomamos el 75% de la duración de cada pierna:")
for label, sub in [('BULL', bulls), ('BEAR', bears)]:
    dur_75 = sub['duration_days'] * 0.75
    print(f"  {label}:")
    for pctl in [25, 50, 75]:
        val = np.percentile(dur_75, pctl)
        print(f"    P{pctl} de (duración × 0.75) = {val:.0f} días")
    print(f"    Mean de (duración × 0.75) = {dur_75.mean():.0f} días")

section("Horizonte donde capturamos 75% de la pierna promedio:")
for label, sub in [('BULL', bulls), ('BEAR', bears)]:
    mean_dur = sub['duration_days'].mean()
    med_dur = sub['duration_days'].median()
    h75_mean = mean_dur * 0.75
    h75_med = med_dur * 0.75
    print(f"  {label}: duration_mean={mean_dur:.0f}d → 75% = {h75_mean:.0f}d  |  "
          f"duration_median={med_dur:.0f}d → 75% = {h75_med:.0f}d")

# ═══════════════════════════════════════════════════════════
banner("3. HORIZONTE = MEDIANA - 1σ (Conservador)")
# ═══════════════════════════════════════════════════════════

section("Horizonte conservador = median - 1 std")
for label, sub in [('BULL', bulls), ('BEAR', bears)]:
    dur = sub['duration_days']
    h_cons = max(5, dur.median() - dur.std())
    h_aggr = dur.median()
    print(f"  {label}: median={dur.median():.0f}d  std={dur.std():.0f}d  →  "
          f"conservador={h_cons:.0f}d  moderado={h_aggr:.0f}d")

# ═══════════════════════════════════════════════════════════
banner("4. POR TICKER — ¿Varía la duración entre acciones?")
# ═══════════════════════════════════════════════════════════

print(f"  {'Ticker':>6s} │ {'N bull':>6s} │ {'Bull dur':>8s} │ {'Bull med':>8s} │ "
      f"{'N bear':>6s} │ {'Bear dur':>8s} │ {'Bear med':>8s} │ {'Bull ret':>8s} │ {'Bear ret':>8s}")
print(f"  {'─'*95}")

for tk in sorted(df['ticker'].unique()):
    tk_b = df[(df['ticker']==tk) & (df['direction']=='BULL')]
    tk_r = df[(df['ticker']==tk) & (df['direction']=='BEAR')]
    print(f"  {tk:>6s} │ {len(tk_b):>6d} │ {tk_b['duration_days'].mean():>7.1f}d │ "
          f"{tk_b['duration_days'].median():>7.0f}d │ {len(tk_r):>6d} │ "
          f"{tk_r['duration_days'].mean():>7.1f}d │ {tk_r['duration_days'].median():>7.0f}d │ "
          f"{tk_b['return_pct'].mean():>+7.1f}% │ {tk_r['return_pct'].mean():>+7.1f}%")

# ═══════════════════════════════════════════════════════════
banner("5. POR RÉGIMEN DE VOLATILIDAD — ¿Piernas más cortas en alta vol?")
# ═══════════════════════════════════════════════════════════

# Load VIX to classify vol regime at each leg start
vix = store.load_bars("VIX", "1d")
if vix is not None and not vix.empty:
    vix_close = vix['close']
    
    section("Clasificar cada pierna por VIX al inicio")
    vol_regimes = []
    for _, leg in df.iterrows():
        start = leg['start_date']
        # Find nearest VIX
        td = (vix.index - start).to_series().abs()
        if td.min() < pd.Timedelta(days=5):
            vix_val = float(vix_close.iloc[td.idxmin()])
        else:
            vix_val = np.nan
        
        if vix_val < 15:
            regime = 'LOW (<15)'
        elif vix_val < 20:
            regime = 'MODERATE (15-20)'
        elif vix_val < 30:
            regime = 'HIGH (20-30)'
        else:
            regime = 'EXTREME (>30)'
        vol_regimes.append({'regime': regime, 'vix': vix_val})
    
    df_vol = pd.DataFrame(vol_regimes)
    df['vol_regime'] = df_vol['regime'].values
    df['vix_at_start'] = df_vol['vix'].values
    
    print(f"\n  {'Vol Regime':>20s} │ {'N':>5s} │ {'Bull dur':>8s} │ {'Bear dur':>8s} │ "
          f"{'Bull ret':>8s} │ {'Bear ret':>8s} │ {'H 75%':>6s}")
    print(f"  {'─'*80}")
    
    for regime in ['LOW (<15)', 'MODERATE (15-20)', 'HIGH (20-30)', 'EXTREME (>30)']:
        sub = df[df['vol_regime'] == regime]
        if len(sub) < 10:
            continue
        sb = sub[sub['direction']=='BULL']
        sr = sub[sub['direction']=='BEAR']
        all_dur = sub['duration_days']
        h75 = all_dur.median() * 0.75
        print(f"  {regime:>20s} │ {len(sub):>5d} │ "
              f"{sb['duration_days'].median():>7.0f}d │ {sr['duration_days'].median():>7.0f}d │ "
              f"{sb['return_pct'].mean():>+7.1f}% │ {sr['return_pct'].mean():>+7.1f}% │ "
              f"{h75:>5.0f}d")

# ═══════════════════════════════════════════════════════════
banner("6. RECOMENDACIÓN DEL COMITÉ — Horizontes calibrados")
# ═══════════════════════════════════════════════════════════

section("Resumen estadístico para calibración de HEAD_CONFIGS")

bull_med = bulls['duration_days'].median()
bear_med = bears['duration_days'].median()
bull_mean = bulls['duration_days'].mean()
bear_mean = bears['duration_days'].mean()
bull_std = bulls['duration_days'].std()
bear_std = bears['duration_days'].std()

print(f"""
  PIERNAS BULL (entry timing):
    Mediana:  {bull_med:.0f} días
    Media:    {bull_mean:.0f} días
    Std:      {bull_std:.0f} días
    75% move: {bull_med * 0.75:.0f} días (mediana × 0.75)
    -1σ:      {max(5, bull_med - bull_std):.0f} días (mediana - 1σ)

  PIERNAS BEAR (exit timing):
    Mediana:  {bear_med:.0f} días
    Media:    {bear_mean:.0f} días
    Std:      {bear_std:.0f} días
    75% move: {bear_med * 0.75:.0f} días (mediana × 0.75)
    -1σ:      {max(5, bear_med - bear_std):.0f} días (mediana - 1σ)

  OPCIONES DE HORIZONTE para long_entry:
    A) Mediana × 0.75 = {bull_med * 0.75:.0f}d  (capturar 75% de pierna típica)
    B) Mediana - 1σ   = {max(5, bull_med - bull_std):.0f}d  (conservador: cubrir piernas cortas)
    C) P25 duración   = {np.percentile(bulls['duration_days'], 25):.0f}d  (cubrir el 75% de piernas)
    D) Actual: 20d      (HEAD_CONFIGS actual, sin fundamento empírico)

  OPCIONES DE HORIZONTE para swing_exit:
    A) Mediana × 0.75 = {bear_med * 0.75:.0f}d
    B) P25 duración   = {np.percentile(bears['duration_days'], 25):.0f}d
    C) Actual: 10d      (HEAD_CONFIGS actual)
""")

store.close()
