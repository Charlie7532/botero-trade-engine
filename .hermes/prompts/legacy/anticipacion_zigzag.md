# Agregar anticipación zigzag (look-back) + persitencia (look-forward) a medir_senal.py
# Usa el zigzag como estructura de tiempo: pivot anterior = look-back, pivot siguiente = look-forward.

## Reemplazar sección 4.8 (persistencia_cluster) por anticipación_lookback + persistencia_lookforward

Archivo: scratch/medir_senal.py
Buscar el bloque que comienza con "# 4.8 Persistencia/Cluster" y reemplazarlo por:

```python
    # 4.8 Anticipación (look-back) y persistencia (look-forward) usando zigzag
    # Look-back: ¿la señal ya estaba activa en el pivote ANTERIOR?
    # Look-forward: ¿la señal sigue activa en el pivote SIGUIENTE?
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

En el stdout, reemplazar la línea de "Persistencia cluster" por:
```python
if "anticipacion_zigzag" in rep and rep["anticipacion_zigzag"]:
    az = rep["anticipacion_zigzag"]
    lb = az["look_back"]
    lf = az["look_forward"]
    print(f"  Anticipación: {lb['pct']}% se adelantan 1 pivote")
    print(f"  Persistencia: {lf['pct']}% persisten 1 pivote después")
```

## PROHIBIDO
- NO tocar métricas existentes
- NO tocar @_registrar ni las señales
- NO tocar capture_ratio, triada, desglose_d2d3
- NO cambiar seed (42) ni bootstrap (3000)

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal bsi_washed_out
Debe mostrar: Anticipación (look-back) + Persistencia (look-forward) en lugar de "Persistencia cluster"