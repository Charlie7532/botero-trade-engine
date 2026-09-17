# Agregar lookback por ventana diaria [T0-3, T0+2] a medir_senal.py
# Para identificar qué señales anteceden a una caída (EXIT/warning detection)

## Nueva sección: 4.12 Lookback crash — señales activas en ventana alrededor del pivote
Después de la sección 4.11 (desglose_d2d3), agregar:

```python
    # 4.12 Lookback crash — señales activas en ventana [T0-3, T0+2]
    # Para cada pivote de caída (prev_leg_return < 0), buscar qué señales
    # estaban activas en la ventana diaria alrededor del pivote.
    crash_threshold = 0  # negativo = caída
    ventana_dias = 3  # [T0-3, T0+2]
    
    rep["lookback_crash"] = {}
    crash_pivots = señal & (df["prev_leg_return"] < crash_threshold)
    crash_idx = np.where(crash_pivots.values)[0]
    
    for escala, col_cascade, max_dur in [("zz25", None, 10), ("zz50", "cascade_50", 30), ("zz75", "cascade_75", 60)]:
        if len(crash_idx) == 0:
            continue
        
        # Señales activas en la ventana [T0-ventana_dias, T0+2]
        activas_en_ventana = {sig: 0 for sig in SEÑALES}
        total_crashes_escala = 0
        
        for i in crash_idx:
            t0 = df["pivot_date"].iloc[i]
            t_min = t0 - pd.Timedelta(days=ventana_dias)
            t_max = t0 + pd.Timedelta(days=2)
            
            # Pivotes dentro de la ventana
            ventana = (df["pivot_date"] >= t_min) & (df["pivot_date"] <= t_max)
            if ventana.sum() == 0:
                continue
            
            total_crashes_escala += 1
            
            # Para cada señal, ¿estaba activa en algún pivote de la ventana?
            for sig_name, sig_fn in SEÑALES.items():
                try:
                    sig_serie = sig_fn(df).astype(bool)
                    if sig_serie[ventana].any():
                        activas_en_ventana[sig_name] += 1
                except:
                    pass
        
        if total_crashes_escala > 0:
            rep["lookback_crash"][escala] = {
                "n_crashes": total_crashes_escala,
                "ventana_dias": ventana_dias,
                "señales": {},
            }
            for sig_name, n_activas in sorted(activas_en_ventana.items(), key=lambda x: -x[1]):
                if n_activas >= 3:  # mínimo 3 para reportar
                    pct = n_activas / total_crashes_escala * 100
                    rep["lookback_crash"][escala]["señales"][sig_name] = {
                        "n_crashes_con_senal": n_activas,
                        "pct_crashes": round(pct, 1),
                    }
```

En el stdout, después de Puntería, agregar:
```python
if "lookback_crash" in rep and rep["lookback_crash"]:
    print(f"  Lookback crash [T0-3, T0+2] — señales que anteceden a caídas:")
    for esc, lc in sorted(rep["lookback_crash"].items()):
        print(f"    {esc} (N={lc['n_crashes']}):")
        top = sorted(lc["señales"].items(), key=lambda x: -x[1]["pct_crashes"])[:5]
        for sig_name, info in top:
            print(f"      {sig_name:25s}  {info['pct_crashes']:5.1f}% de caídas")
```

## PROHIBIDO
- NO tocar @_registrar ni las señales
- NO tocar triada, capture_ratio, punteria, offset_entrada, duracion_desglose, estabilidad_decada
- NO tocar seed (42) ni bootstrap (3000)

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal crediteasing_k1
Debe mostrar: "Lookback crash" con las señales que anteceden a las caídas en cada escala