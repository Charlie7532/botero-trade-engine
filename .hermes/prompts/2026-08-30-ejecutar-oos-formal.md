# PROMPT — Ejecutar Validación OOS Formal (Walk-Forward Anclado)

**Archivo a ejecutar:** `research/10_gate_oos_validation/validador_oos.py`
**Propósito:** Re-evaluar el catálogo v7 sobre la tabla canónica (bins numéricos, población deduplicada) con el evaluador v3 actualizado.
**Incluir:** cascade_reversal como señal candidata a promoción.

---

## PROBLEMA DETECTADO

El validador OOS tiene código a nivel de módulo (sin `if __name__ == "__main__"`), lo que causó que al importarlo desde otro script **se ejecutara automáticamente**. Esto produjo resultados preliminares no controlados.

---

## ACCIÓN REQUERIDA

### Paso 1: Agregar `if __name__ == "__main__"` al validador

**Archivo:** `research/10_gate_oos_validation/validador_oos.py`
**Líneas actuales:** las últimas ~50 líneas contienen la ejecución directa

**Cambio:** Envolver el bloque de ejecución principal (desde la definición de `SEÑALES_A_VALIDAR` hasta el guardado) en:

```python
if __name__ == "__main__":
    # ... todo el código de ejecución ...
```

### Paso 2: Agregar cascade_reversal a la lista de señales a validar

Buscar la lista `SEÑALES_A_VALIDAR` (o equivalente) y agregar:

```python
"cascade_reversal",  # PROPOSED → candidata a NÚCLEO (p=0.000 en first-passage zz25)
```

### Paso 3: Verificar BLANCOS de cascade_reversal en evaluador

Confirmar que `BLANCOS["cascade_reversal"] = "MAX"` existe en el evaluador v3 (línea 84). Si no, agregarlo.

### Paso 4: Ejecutar el validador

```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit:/root/botero-trade/research/10_gate_oos_validation \
  backend/.venv/bin/python research/10_gate_oos_validation/validador_oos.py
```

### Paso 5: Verificar resultados

```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit \
  backend/.venv/bin/python -c "
import json
oos = json.load(open('data/research/signals/validacion_oos_catalogo_v7.json'))
res = oos.get('resultados', {})
for s, r in sorted(res.items()):
    if isinstance(r, dict):
        is_neto = r.get('in_sample_fav_neto', '?')
        oos_neto = r.get('oos_edge_medio_pct', '?')
        folds_p = r.get('oos_folds_positivos', '?')
        folds_t = r.get('oos_folds_totales', '?')
        decay = r.get('decay_oos_vs_is', '?')
        verd = r.get('veredicto', '?')
        print(f'{s:<30} IS={is_neto} OOS={oos_neto} folds={folds_p}/{folds_t} decay={decay} veredicto={verd}')
"
```

---

## RESULTADOS ESPERADOS

| Señal | OOS 23-Ago (v2) | Expectativa hoy (v3) | 
|:------|:----------------:|:--------------------:|
| capitulacion | 🟢 +2.64% | ⚠️ Posible degradación (nuevo BLANCO) |
| pcr_put_panic | 🟢 +2.56% | ⚠️ Posible degradación |
| vvix_entry | 🟢 +2.08% | ⚠️ Posible degradación |
| credit_stress | 🟢 +1.43% | 🟢 Debería mantenerse o mejorar |
| bsi_washed_out | 🟢 +0.99% | ⚠️ Posible degradación |
| **cascade_reversal** | ❌ No evaluada | 🟢 **NUEVA — candidata a promoción** |
| panico_total | Sin folds | Sin folds (N<10) |
| skew_paranoia_exit | Sin folds | Sin folds (N<10) |

---

## FORMATO DE ENTREGA

1. Archivo `research/10_gate_oos_validation/validador_oos.py` con `if __name__` añadido
2. cascade_reversal incluida en la validación
3. JSON `data/research/signals/validacion_oos_catalogo_v7.json` regenerado
4. Tabla comparativa con los resultados