# CORREGIR 4 PUNTOS CIEGOS de medir_senal.py — Para Claude Opus

## 1. Bootstrap CI en desglose D2/D3
En la sección 4.10 (desglose_d2d3), agregar CI95 bootstrap a cada D2/D3:
```python
# Calcular bootstrap CI de la diferencia entre la mejor y peor rama D2/D3
# Solo reportar como "significativo" si el CI95 no cruza cero
```

## 2. Estabilidad por década
En el reporte, agregar sección:
```python
rep["estabilidad_decada"] = {}
for decada in ['1990', '2000', '2010', '2020']:
    mask_dec = señal & (df['pivot_date'].dt.year.astype(str).str.startswith(decada))
    dec_fwd = fwd[mask_dec & fwd.notna()]
    rep["estabilidad_decada"][decada] = {
        "n": int(len(dec_fwd)),
        "mean": float(np.nanmean(dec_fwd)) if len(dec_fwd) else None,
        "wr": float((dec_fwd > 0).mean()) if len(dec_fwd) else None,
    }
```

## 3. Cross-signal overlap (confluencia entre pares de señales)
Agregar función separada que mida el edge de la intersección de dos señales:
- Para cada par de señales registradas: medir N, forward_mean, WR de la señal A sola, B sola, y A∩B
- Reportar si la confluencia es ADITIVA (+), REDUNDANTE (=) o CANCELATORIA (-)

## 4. Desglose short/long por duration_bars
En triada, agregar desglose por duración:
```python
# Separar señal en pierna corta (≤mediana) y larga (>mediana)
median_dur = df.loc[señal, "duration_bars"].median()
cortas = señal & (df["duration_bars"] <= median_dur)
largas = señal & (df["duration_bars"] > median_dur)
rep["duracion_desglose"] = {
    "cortas": {"n": int(cortas.sum()), "fwd_mean": float(np.nanmean(fwd[cortas])), "wr": float((fwd[cortas]>0).mean())},
    "largas": {"n": int(largas.sum()), "fwd_mean": float(np.nanmean(fwd[largas])), "wr": float((fwd[largas]>0).mean())},
}
```

## PROHIBIDO
- NO tocar @_registrar ni las señales
- NO tocar capture_ratio, triada, punteria, offset_entrada
- NO tocar seed (42) ni bootstrap (3000)
- NO tocar MAE, costo_tarde, sensibilidad_timing

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal credit_stress
Debe mostrar: estabilidad por década + duration_desglose (cortas/largas con forward+WR) + desglose_d2d3 con CI95