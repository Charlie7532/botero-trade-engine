# Agregar anticipación y capture_ratio a medir_senal.py
# Basado en: especificación §9 (evaluador)

## Qué agregar (sin romper nada existente)
1. anticip_barras: ¿cuántas barras ANTES del pivote la señal está activa? 
   Para cada señal: medir si la señal ya estaba activa 1, 2, 3, 5 barras antes del pivote.
   Reportar: cuántas barras antes se adelantó la señal, y el % de la señal adelantada.
2. capture_ratio: ¿cuánto de la pierna zz25 capturó la señal?
   capture_ratio = signal_forward_return / leg_return
   Si la señal captura +1.42% y la pierna zz25 da +2.5%, capture_ratio = 0.57.

## Implementación
Dentro de la función medir(), después de la sección 4.7 (timing_optimo), agregar:

```python
# ──────────────
# 4.9 Anticipación (barras antes del pivote que la señal ya estaba activa)
# ──────────────
# Para cada señal, ¿cuánto antes estaba activa?
# Evaluar: 1, 2, 3, 5 pivotes antes, qué % de la señal ya estaba activa?
anticip = {}
for k in [1, 2, 3, 5]:
    adelantada = señal.shift(-k).fillna(False)
    if adelantada.sum() > 0:
        coincidencia = (señal & adelantada).sum()
        pct = float(coincidencia / señal.sum()) if señal.sum() > 0 else 0.0
        anticip[f"{k}_antes"] = {
            "n_senal_coincide": int(coincidencia),
            "pct_adelantada": float(pct * 100),
        }
rep["anticipacion"] = anticip

# ──────────────
# 4.10 Capture ratio: cuánto de la pierna zz25 capturó la señal
# ──────────────
# capture_ratio = forward_retorno / leg_return
# La pierna zz25 es el retorno de la pierna que empieza en el pivote
# Usar la duración media de la pierna (duration_bars) como referencia
zz25_act = act  # forward return de la señal
zz25_leg = df.loc[señal, "prev_leg_return"].dropna()  # retorno de la pierna
if len(zz25_act) > 0 and len(zz25_leg) > 0:
    # Capture ratio: media del forward / media de la pierna
    cr = float(np.nanmean(zz25_act) / np.nanmean(zz25_leg)) if np.nanmean(zz25_leg) != 0 else 0.0
    rep["capture_ratio"] = {
        "ratio": float(cr),
        "signal_mean": float(np.nanmean(zz25_act)),
        "leg_mean": float(np.nanmean(zz25_leg)),
        "n": int(len(zz25_act)),
    }
else:
    rep["capture_ratio"] = None
```

En el stdout, después de "Tríada ZigZag", agregar:
```python
if "anticipacion" in rep and rep["anticipacion"]:
    a_key = list(rep["anticipacion"].keys())[0]
    a_val = rep["anticipacion"][a_key]
    print(f"  Anticipación: {a_val['pct_adelantada']:.1f}% se adelanta {a_key}")
if "capture_ratio" in rep and rep["capture_ratio"]:
    cr = rep["capture_ratio"]
    print(f"  Capture ratio: {cr['ratio']:.2f} (signal {cr['signal_mean']:+.4f} / leg {cr['leg_mean']:+.4f})")
```

## PROHIBIDO
- NO tocar métricas existentes
- NO tocar @_registrar ni las señales
- NO tocar triada, timing_optimo ni horizontes
- NO cambiar seed (42) ni bootstrap (3000)

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal bsi_washed_out --horizontes 5,10,20,60
Debe mostrar: Anticipación + Capture ratio además de lo que ya mostraba