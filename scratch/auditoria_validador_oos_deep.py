#!/usr/bin/env python3
"""
auditoria_validador_oos_deep.py — Script de verificación empírica profunda
para la auditoría externa del validador OOS y cadena de medición.
"""
import sys
import os
import json
import inspect
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research/01_señales_entry_exit"))
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))

from arnes import SEÑALES, cargar_datos
from evaluador_vela_a_vela import first_passage, BLANCOS, ESCALAS
from sigma_overflow import STATION_MU_SIGMA

df, spy = cargar_datos()
prices = spy["close"].astype(float).values
spy_idx = spy.close.index
piv_dates = df["pivot_date"].values
piv_types = df["pivot_type"].values
piv_pos = np.array([spy_idx.searchsorted(pd.Timestamp(d)) for d in piv_dates])
n_piv = len(piv_dates)

print("=" * 80)
print("1. VERIFICACIÓN H1: BINNEO D2/D3 Y LOOK-AHEAD EN ENGINE")
print("=" * 80)
# Look-ahead in v3_fact_table_engine.py:
# D1 uses expanding rank: ind_df['val'].expanding(min_periods=252).rank(pct=True)
# D2 uses calib_df['d2_velocity'].quantile(PERCENTILES_D2_GAUSS) across FULL history
# D3 uses calib_df['vol_norm'].quantile(PERCENTILES_D3_GAUSS) across FULL history
# Let's verify which signals in the codebase use D2 or D3
d2_d3_signals = []
d1_only_signals = []
full_df_signals = []

for name, fn in sorted(SEÑALES.items()):
    src = inspect.getsource(fn)
    uses_d1 = 'str[0]' in src or 'bin_d1' in src
    uses_d2 = 'str[1]' in src or 'bin_d2' in src or 'vel' in src
    uses_d3 = 'str[2]' in src or 'bin_d3' in src or 'vol' in src
    uses_df_quant = 'quantile' in src or 'mean(' in src
    if uses_df_quant:
        full_df_signals.append(name)
    if uses_d2 or uses_d3:
        d2_d3_signals.append((name, uses_d2, uses_d3))
    elif uses_d1:
        d1_only_signals.append(name)

print(f"Señales que usan D2/D3 ({len(d2_d3_signals)}):")
for s, d2, d3 in d2_d3_signals:
    print(f"  - {s:30s} (uses D2: {d2}, D3: {d3})")

print(f"\nSeñales que usan SOLO D1 ({len(d1_only_signals)}):")
for s in d1_only_signals:
    print(f"  - {s}")

print(f"\nSeñales con cálculo sobre el DataFrame completo ({len(full_df_signals)}):")
for s in full_df_signals:
    print(f"  - {s}")

print("\n" + "=" * 80)
print("2. VERIFICACIÓN CATALOGO_V7 EN VALIDADOR OOS")
print("=" * 80)
CATALOGO_V7 = [
    "pcr_put_panic", "credit_stress", "capitulacion", "panico_total",
    "vvix_entry", "bsi_washed_out", "breadth_contraction_exit",
    "skew_paranoia_exit",
]
print("Verificando señales en CATALOGO_V7:")
for s in CATALOGO_V7:
    src = inspect.getsource(SEÑALES[s])
    uses_d1 = 'str[0]' in src
    uses_d2 = 'str[1]' in src
    uses_d3 = 'str[2]' in src
    print(f"  {s:28s} -> D1: {uses_d1}, D2: {uses_d2}, D3: {uses_d3} | "
          f"{'Limpia de look-ahead D2/D3' if (uses_d1 and not uses_d2 and not uses_d3) else 'CONTAMINADA'}")

print("\n" + "=" * 80)
print("3. VERIFICACIÓN H2: SIGN-TEST Y POTENCIA ESTADÍSTICA")
print("=" * 80)
from scipy.stats import binomtest
# How many folds are needed to achieve power = 0.80 under H1: p_success = 0.75, 0.80, 0.90?
for p_true in [0.60, 0.70, 0.80, 0.90]:
    print(f"Potencia estadística para detectar p_true = {p_true:.2f} con alpha = 0.05 (unilateral):")
    for k_folds in [4, 6, 8, 10, 12, 15, 20]:
        # Critical value c for alpha=0.05 under H0 (p=0.5)
        # We reject if k >= c where P(K >= c | p=0.5) <= 0.05
        from scipy.stats import binom
        crit_k = None
        for k in range(k_folds + 1):
            pval = binomtest(k, k_folds, 0.5, alternative="greater").pvalue
            if pval <= 0.05:
                crit_k = k
                break
        if crit_k is not None:
            # Power = P(K >= crit_k | p_true)
            power = 1.0 - binom.cdf(crit_k - 1, k_folds, p_true)
            min_pval = binomtest(k_folds, k_folds, 0.5, alternative="greater").pvalue
            print(f"  Folds={k_folds:2d} | Crit={crit_k:2d}/{k_folds} | Min p-val={min_pval:.4f} | Power={power:.3f}")
        else:
            print(f"  Folds={k_folds:2d} | IMPOSIBLE alcanzar p<=0.05 (mínimo p={0.5**k_folds:.4f})")
    print("-" * 50)

print("\n" + "=" * 80)
print("4. VERIFICACIÓN PREGUNTA 1: QUANTS_OBS.PKL vs MOTOR FACT STORE")
print("=" * 80)
print("Analizando quants_obs.pkl:")
print(f"  Total filas en quants_obs.pkl: {len(df)}")
print(f"  Rango de fechas: {df['pivot_date'].min()} a {df['pivot_date'].max()}")
print(f"  Columnas disponibles: {list(df.columns)}")

# Check if state_keys match standard D1__D2__D3 format
sample_sk = df[["vix_sk", "bsi_sk", "credit_sk", "skew_sk"]].dropna().head(5)
print("\nEjemplo de state keys en quants_obs.pkl:")
print(sample_sk)

print("\n" + "=" * 80)
print("5. VERIFICACIÓN PREGUNTA 3: EXCLUSIÓN EN FICHAS_BASELINE()")
print("=" * 80)
# In validador_oos.py:
# B_train = fichas_baseline(tipo, blanco, T0, t_from, set(pd.DatetimeIndex(df.loc[mask, 'pivot_date'])))
# B_test = fichas_baseline(tipo, blanco, t_from, t_to, set(pd.DatetimeIndex(df.loc[mask, 'pivot_date'])))
# Notice: 'excluir_fechas' passes set(pd.DatetimeIndex(df.loc[mask, 'pivot_date'])) which is ALL dates where the signal fired across the FULL history!
# Let's inspect the effect:
# When evaluating test fold [t_from, t_to), fichas_baseline loops over all pivots i where t_from <= d < t_to.
# If d in excluir_fechas, it skips it.
# Is skipping a pivot in [t_from, t_to) that was a signal pivot in [t_from, t_to) look-ahead?
# In the test window, a baseline pivot shouldn't be a signal pivot in the test window.
# But does excluir_fechas leak signal firings from FUTURE folds into the test window?
# If d is in [t_from, t_to), d cannot be in a future fold! Because d is strictly in [t_from, t_to).
# So excluding d where d is a signal date within [t_from, t_to) only excludes signal dates of the test window itself!
print("Análisis de fichas_baseline:")
print("excluir_fechas = set de TODAS las fechas donde la señal disparó en la historia.")
print("Dentro de [t_from, t_to), solo las fechas de señal que caen dentro de [t_from, t_to) pueden coincidir con d.")
print("Por lo tanto, NO hay fuga de fechas futuras en el baseline de test: sólo se excluyen las fechas de señal de ese fold.")

print("\n" + "=" * 80)
print("6. VERIFICACIÓN PREGUNTA 4: RÉGIMEN OBSERVABLE EN FOLDS TEMPRANOS")
print("=" * 80)
MIN_TRAIN_DIAS = 1825
BLOQUE_TEST_DIAS = 1095
T0 = pd.Timestamp(df["pivot_date"].min())
T1 = pd.Timestamp(df["pivot_date"].max()) + pd.Timedelta(days=1)
folds = []
t = T0 + pd.Timedelta(days=MIN_TRAIN_DIAS)
while t < T1:
    folds.append((t, min(t + pd.Timedelta(days=BLOQUE_TEST_DIAS), T1)))
    t += pd.Timedelta(days=BLOQUE_TEST_DIAS)

def régimen_en(t_pos):
    idx = np.arange(n_piv - 1)
    conf = piv_pos[1:]
    valid = idx[conf <= t_pos]
    if len(valid) == 0:
        return "NA"
    return "ALZA" if piv_types[valid[-1]] == "MIN" else "BAJA"

for fold_idx, (t_from, t_to) in enumerate(folds):
    # Check train window [T0, t_from)
    train_mask = (pd.to_datetime(df["pivot_date"]) >= T0) & (pd.to_datetime(df["pivot_date"]) < t_from)
    train_pivs = df[train_mask]
    
    # Check test window [t_from, t_to)
    test_mask = (pd.to_datetime(df["pivot_date"]) >= t_from) & (pd.to_datetime(df["pivot_date"]) < t_to)
    test_pivs = df[test_mask]
    
    # Compute regime for test pivots
    test_regs = []
    for d in test_pivs["pivot_date"]:
        pos = spy_idx.searchsorted(pd.Timestamp(d))
        test_regs.append(régimen_en(pos))
    test_reg_s = pd.Series(test_regs).value_counts().to_dict()
    
    print(f"Fold {fold_idx+1:2d} | Train: {T0.date()} to {t_from.date()} ({len(train_pivs):4d} pivs) | "
          f"Test: {t_from.date()} to {t_to.date()} ({len(test_pivs):3d} pivs) | Regímenes Test: {test_reg_s}")

print("\n" + "=" * 80)
print("7. VERIFICACIÓN PREGUNTA 5: FIRST-PASSAGE CLOSES vs INTRADAY HIGH/LOW (MAE)")
print("=" * 80)
# Compare MAE using only closes vs MAE using low/high
maes_close = []
maes_intraday = []

# Take a sample of 100 random pivots
sample_indices = np.random.RandomState(42).choice(len(df) - 10, 100, replace=False)
for idx in sample_indices:
    d = df["pivot_date"].iloc[idx]
    t_pos = spy_idx.searchsorted(pd.Timestamp(d))
    if t_pos >= len(prices) - 50:
        continue
    scale = 0.05  # zz50
    p0 = prices[t_pos]
    
    # Close-only first-passage
    path_close = spy["close"].iloc[t_pos + 1:].values
    up_i = np.where(path_close >= p0 * (1 + scale))[0]
    dn_i = np.where(path_close <= p0 * (1 - scale))[0]
    up_i = up_i[0] if len(up_i) else np.inf
    dn_i = dn_i[0] if len(dn_i) else np.inf
    if np.isinf(up_i) and np.isinf(dn_i):
        continue
    event_i = int(min(up_i, dn_i))
    
    # Segment for close vs intraday
    seg_close = spy["close"].iloc[t_pos: t_pos + 1 + event_i + 1].values
    seg_low = spy["low"].iloc[t_pos: t_pos + 1 + event_i + 1].values
    
    # For a LONG entry (MIN blanco):
    mae_c = (seg_close.min() - p0) / p0
    mae_intra = (seg_low.min() - p0) / p0
    
    maes_close.append(mae_c)
    maes_intraday.append(mae_intra)

maes_close = np.array(maes_close)
maes_intraday = np.array(maes_intraday)
diff = maes_intraday - maes_close

print(f"MAE Close-only (media):    {maes_close.mean():.4f} ({maes_close.mean()*100:.2f}%)")
print(f"MAE Intraday Low (media):  {maes_intraday.mean():.4f} ({maes_intraday.mean()*100:.2f}%)")
print(f"Diferencia (subestimación de dolor): {diff.mean():.4f} ({diff.mean()*100:.2f} pp de drawdown no capturado)")
print(f"Máxima subestimación en un trade:    {diff.min():.4f} ({diff.min()*100:.2f} pp)")

print("\n" + "=" * 80)
print("8. VERIFICACIÓN PREGUNTA 6: INDEPENDENCIA DE FOLDS Y AUTOCORRELACIÓN EN TRAIN")
print("=" * 80)
print("Estructura de walk-forward anclado (expanding window):")
print("Fold 1 Train: [0, 5y]  -> Test: [5y, 8y]")
print("Fold 2 Train: [0, 8y]  -> Test: [8y, 11y]")
print("Fold 3 Train: [0, 11y] -> Test: [11y, 14y]")
print("Los bloques de TEST son disjuntos temporalmente (no se solapan).")
print("PERO la selección de celda (train) comparte historia previa.")
print("¿El sign-test sobre los folds asume independencia?")
print("Bajo H0 (sin edge real), los tests en períodos no solapados con celdas seleccionadas son cuasi-independientes,")
print("pero el sesgo de selección del modelo arrastra persistencia de celdas elegidas.")
