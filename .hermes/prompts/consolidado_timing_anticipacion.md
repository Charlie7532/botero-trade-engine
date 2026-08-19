# CONSOLIDADO — Timing, anticipación, puntería y limpieza de medir_senal.py
# Para Claude Opus. Cuatro cambios en un solo prompt.

## 1. ELIMINAR --horizontes (ruido que no pertenece a la tríada)
Eliminar del archivo scratch/medir_senal.py:
- El argumento --horizontes del argparse en main()
- La variable horizontes y su parsing
- La sección 4.7 (timing_optimo) y la sección 4.5 (horizontes multi-día)
- Las líneas del stdout que imprimen timing_optimo
- El parámetro horizontes_dias de la función medir()
- Las claves "horizontes" y "timing_optimo" del JSON de salida

## 2. REEMPLAZAR persistencia_cluster por anticipación zigzag (look-back/look-forward)
Buscar el bloque "# 4.8 Persistencia/Cluster" y reemplazar por:

```python
    # 4.8 Anticipación (look-back) y persistencia (look-forward) usando zigzag
    señal_shift1 = señal.shift(1, fill_value=False)
    señal_shift_1 = señal.shift(-1, fill_value=False)
    
    if señal.sum() > 0:
        anticipacion = int((señal & señal_shift1).sum())
        persistencia = int((señal & señal_shift_1).sum())
        total = int(señal.sum())
        rep["anticipacion_zigzag"] = {
            "look_back": {
                "n_anticipadas": anticipacion,
                "pct": round(anticipacion / total * 100, 1),
                "interpretacion": f"{anticipacion}/{total} ({100*anticipacion/total:.1f}%) estaban activas en el pivote anterior"
            },
            "look_forward": {
                "n_persisten": persistencia,
                "pct": round(persistencia / total * 100, 1),
                "interpretacion": f"{persistencia}/{total} ({100*persistencia/total:.1f}%) siguen activas en el pivote siguiente"
            },
            "n_total": total,
        }
    else:
        rep["anticipacion_zigzag"] = None
```

En el stdout, reemplazar:
```python
if "anticipacion_zigzag" in rep and rep["anticipacion_zigzag"]:
    az = rep["anticipacion_zigzag"]
    lb = az["look_back"]
    lf = az["look_forward"]
    print(f"  Anticipación: {lb['pct']}% se adelantan 1 pivote")
    print(f"  Persistencia: {lf['pct']}% persisten 1 pivote después")
```

## 3. AGREGAR drawdown por anticipación (entrada temprana) y salida tardía
Después de la sección 4.9 (capture_ratio), agregar sección 4.10:

```python
    # 4.10 Drawdown por anticipación (entrada temprana) y salida tardía
    # Cuando la señal se adelanta (look-back), ¿cuál es el drawdown si entro en el pivote anterior?
    # Cuando la señal persiste (look-forward), ¿cuál es el drawdown si NO salgo en el pivote actual?
    if señal.sum() > 0:
        early_mask = señal_shift1 & señal
        early_fwd = fwd[early_mask & fwd.notna()]
        early_mae = _mae_intratrade(spy, early_mask, df) if spy is not None else []
        late_mask = señal & señal_shift_1
        late_fwd = fwd[late_mask & fwd.notna()]
        late_mae = _mae_intratrade(spy, late_mask, df) if spy is not None else []
        rep["drawdown_anticipacion"] = {
            "entrada_temprana": {
                "n": int(len(early_fwd)),
                "forward_mean": float(np.nanmean(early_fwd)) if len(early_fwd) else None,
                "mae_medio": float(np.nanmean(early_mae)) if early_mae else None,
            },
            "salida_tardia": {
                "n": int(len(late_fwd)),
                "forward_mean": float(np.nanmean(late_fwd)) if len(late_fwd) else None,
                "mae_medio": float(np.nanmean(late_mae)) if late_mae else None,
            },
        }
    else:
        rep["drawdown_anticipacion"] = None
```

En el stdout, después de Anticipación/Persistencia:
```python
if "drawdown_anticipacion" in rep and rep["drawdown_anticipacion"]:
    et = rep["drawdown_anticipacion"].get("entrada_temprana", {})
    st = rep["drawdown_anticipacion"].get("salida_tardia", {})
    if et.get("forward_mean") is not None:
        print(f"  Entrada temprana: forward={et['forward_mean']:+.4f}  MAE={et.get('mae_medio',0):+.4f}  (N={et['n']})")
    if st.get("forward_mean") is not None:
        print(f"  Salida tardía:    forward={st['forward_mean']:+.4f}  MAE={st.get('mae_medio',0):+.4f}  (N={st['n']})")
```

## 4. AGREGAR puntería por escala zigzag + offset de entrada
Después de la sección 4.10, agregar sección 4.11:

```python
    # 4.11 Puntería por escala zigzag: capture ratio por zz25/zz50/zz75
    # Para cada señal, medir a qué escala de la tríada impacta más:
    # zz25 (retracción 2.5%), zz50 (corrección 5%), zz75 (depresión 7.5%)
    rep["punteria"] = {}
    for escala, col_cascade, objetivo in [("zz25", None, 0.025), ("zz50", "cascade_50", 0.05), ("zz75", "cascade_75", 0.075)]:
        if escala == "zz25":
            mask = señal & fwd.notna()
            lag = fwd[mask]
        else:
            mask = señal & (df[col_cascade] == 1) & fwd.notna()
            lag = fwd[mask]
        if len(lag) >= 5:
            rep["punteria"][escala] = {
                "n": int(len(lag)),
                "forward_mean": float(np.nanmean(lag)),
                "win_rate": float((lag > 0).mean()),
                "capture_ratio": float(np.nanmean(lag) / objetivo),
                "mae_medio": float(np.nanmean(_mae_intratrade(spy, mask, df))) if spy is not None else None,
            }
    
    # 4.12 Offset de entrada: capture ratio si entro ±1 barra del pivote
    # Documentar estadísticamente si entrar antes/después mejora el capture
    if spy is not None:
        rep["offset_entrada"] = {}
        for offset in [-1, 0, 1]:
            off_mask = señal.values.copy()
            if offset != 0:
                off_mask = np.roll(off_mask, -offset)
            off_mask = pd.Series(off_mask, index=señal.index).astype(bool)
            off_fwd = fwd[off_mask & fwd.notna()]
            if len(off_fwd) >= 5:
                leg_mean = float(np.nanmean(np.abs(df.loc[señal, "prev_leg_return"])))
                rep["offset_entrada"][f"{offset:+d}"] = {
                    "n": int(len(off_fwd)),
                    "forward_mean": float(np.nanmean(off_fwd)),
                    "win_rate": float((off_fwd > 0).mean()),
                    "capture_ratio": float(np.nanmean(off_fwd) / leg_mean) if leg_mean > 0 else 0,
                }
```

En el stdout, después de Capture ratio:
```python
if "punteria" in rep and rep["punteria"]:
    for esc, p in sorted(rep["punteria"].items()):
        print(f"  Puntería {esc}: capture={p['capture_ratio']:.2f}  WR={p['win_rate']:.1%}  MAE={p.get('mae_medio',0):+.4f}  (N={p['n']})")
if "offset_entrada" in rep and rep["offset_entrada"]:
    for off, v in sorted(rep["offset_entrada"].items()):
        print(f"  Offset {off}: capture={v['capture_ratio']:.2f}  forward={v['forward_mean']:+.4f}  WR={v['win_rate']:.1%}  (N={v['n']})")
```

## 5. MANTENER todo lo demás intacto
- capture_ratio (sección 4.9) — NO tocar
- desglose_d2d3 (sección 4.10 o 4.11) — NO tocar
- triada (sección 4.6) — NO tocar
- @_registrar y las señales — NO tocar
- seed (42) y bootstrap (3000) — NO tocar
- MAE, costo_tarde, sensibilidad_timing — NO tocar

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal bsi_washed_out
NO debe mostrar "Timing óptimo" ni "Horizontes" ni "Persistencia cluster".
DEBE mostrar: Tríada, cascade, Anticipación (look-back), Persistencia (look-forward), 
Entrada temprana (forward+MAE), Salida tardía (forward+MAE),
Puntería zz25/zz50/zz75 (capture_ratio, WR, MAE), Capture ratio, MAE, costo retraso.