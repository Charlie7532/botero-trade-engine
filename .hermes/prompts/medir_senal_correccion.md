# PROMPT PARA GEMINI — Corregir bugs de medir_senal.py
# Archivo de referencia: scratch/medir_senal.py
# Auditoría: Gemini encontró 4 bugs matemáticos en las métricas de trayectoria.

Corregir los 4 errores. Arquitectura general (registro @_registrar, percentiles, 
bootstrap seed fija, JSON) NO se toca.

## BUG 1 — _costo_tarde
arr[:k] toma el primer trade de 1993 y lo divide por la suma de 30 años.
FIX: costo POR TRADE al retrasar entrada k barras. Para cada señal en T0:
  ΔOpportunity(k) = (Close[T0+k] − Close[T0]) / Close[T0]
Usar TimescaleDataStore().load_bars("SPY", "1d") para Close diarios.

## BUG 2 — _drawdown_temprano
cumsun de 20 barras arbitrarias, no MAE real.
FIX: MAE intra-trade real. Para cada señal en T0:
  MAE = min_{t∈[T0,T1]} (Low_t − Close_T0) / Close_T0
T1 = pivote siguiente en quants_obs.pkl. Usar spy["low"] del Vault.

## BUG 3 — _sensibilidad_timing
shift(k) sobre pivotes MIN/MAX alternantes no es "k barras después".
FIX: retraso en BARRAS continuas. Para cada señal en T0 y k:
  forward_k = (Close[T1] − Close[T0+k]) / Close[T0+k]

## BUG 4 — delta_media
Baseline compara señal MIN vs TODOS los pivotes (incluye MAX).
FIX: baseline homogéneo. Si señal es MIN-only, baseline = MIN sin señal.

## Menores
- Quitar import de spearmanr (no se usa).
- Arreglar deprecación: shift(k).fillna(False) → shift(k, fill_value=False).
- --horizontes está en docstring pero no en argparse — agregarlo o quitarlo.

## PROHIBIDO
- NO tocar @_registrar ni las señales (credit_easing_k1, sorpresa_total).
- NO tocar _pctiles, _wins_losses, _bootstrap_ci.
- NO tocar seed (42) ni bootstrap (3000).
- NO tocar fact stores ni quants_obs.pkl.

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal credit_easing_k1
Debe dar: N=112, mean≈+0.0519, WR≈0.9375 (edge original intacto).
costo_tarde, timing_temprano, sensibilidad ahora con valores correctos por-trade.