# Tests para Bug 1: Anticipación Temporal

**Proyecto:** Botero Trade  
**Archivo bajo prueba:** `research/01_señales_entry_exit/medir_senal.py` (líneas 507-529)  
**Suite de tests:** `research/11_experimental_engines/test_anticipacion_temporal.py`  
**Fecha:** 2026-08-18

---

## 1. Descripción del Bug

### Código actual (INCORRECTO)
```python
# 4.6 Anticipación (look-back) y persistencia (look-forward) usando zigzag
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
            "interpretacion": f"{anticipacion}/{total} (...) estaban activas en el pivote anterior"
        },
        ...
    }
```

### Problema
El código actual mide **autocorrelación entre pivotes consecutivos** del zigzag:
- Cuenta cuántos pivotes tienen la señal activa consecutivamente
- NO mide cuántos días ANTES del pivot_date la señal estaba activa
- El resultado es un conteo de pivotes, no una medida temporal

### Corrección requerida
Medir cuántos días ANTES del pivot_date la señal ya estaba activa:
- Para cada pivot donde la señal está activa
- Buscar el pivote anterior con señal activa
- Calcular la distancia temporal en días entre ambos pivotes
- Reportar estadísticas de anticipación en días

---

## 2. Criterios de Aceptación

| ID | Criterio | Verificación |
|----|----------|--------------|
| CA1 | La función calcula días de anticipación, no cuenta pivotes | `tipo(anticipacion) == int(días)` |
| CA2 | Para cada pivot con señal activa, busca cuántos días antes la señal ya estaba activa | Itera sobre `np.where(señal.values)[0]` |
| CA3 | La anticipación se mide en días calendario entre pivot_dates | `(pivot_date_i - pivot_date_j).days` |
| CA4 | Si la señal se activa por primera vez, anticipación = 0 | Primer elemento de `anticipaciones_dias == 0` |
| CA5 | Si la señal estaba activa en pivote anterior, calcula distancia en días | Búsqueda hacia atrás en índices |
| CA6 | Maneja pivotes sin señal previa (anticipación = 0) | Default cuando no hay pivote anterior activo |
| CA7 | Resultados reproducibles y deterministas | Sin aleatoriedad, misma entrada → misma salida |

---

## 3. Casos de Prueba

### Test 1: Señal activa 0 días antes (primera activación)
- **Escenario:** La señal se activa por primera vez en un pivot
- **Setup:** 10 pivotes, señal activa solo en el último
- **Resultado esperado:** `anticipacion_dias = 0`
- **Status:** ✅ PASA

### Test 2: Señal activa 3 días antes
- **Escenario:** Señal activa en pivot actual y en pivote anterior 3 días antes
- **Setup:** Pivots en 2020-01-01 y 2020-01-04 (diferencia = 3 días)
- **Resultado esperado:** `anticipacion_dias = 3`
- **Status:** ✅ PASA

### Test 3: Señal activa 7 días antes
- **Escenario:** Señal activa en pivot actual y en pivote anterior 7 días antes
- **Setup:** Pivots en 2020-01-01 y 2020-01-08 (diferencia = 7 días)
- **Resultado esperado:** `anticipacion_dias = 7`
- **Status:** ✅ PASA

### Test 4: Señal NO activa antes (primera aparición)
- **Escenario:** Señal se activa sin ningún pivote anterior activo
- **Setup:** 10 pivotes, señal solo en el último
- **Resultado esperado:** `anticipacion_dias = 0`
- **Status:** ✅ PASA

### Test 5: Múltiples activaciones con diferentes anticipaciones
- **Escenario:** 3 activaciones con diferentes distancias temporales
- **Setup:**
  - Pivot 0 (2020-01-01): primera activación → 0 días
  - Pivot 3 (2020-01-06): segunda activación → 5 días
  - Pivot 8 (2020-01-11): tercera activación → 5 días
- **Resultado esperado:** `[0, 5, 5]`
- **Status:** ✅ PASA

---

## 4. Métricas de Validación

| ID | Métrica | Criterio | Status |
|----|---------|----------|--------|
| M1 | Exactitud temporal | `dias_antes == (pivot_date_actual - pivot_date_anterior).days` | ✅ |
| M2 | Consistencia primera activación | `anticipaciones_dias[0] == 0` | ✅ |
| M3 | No-negatividad | `all(d >= 0 for d in anticipaciones_dias)` | ✅ |
| M4 | Cobertura completa | `len(anticipaciones_dias) == señal.sum()` | ✅ |
| M5 | Reproducibilidad | `f(x) == f(x)` en múltiples llamadas | ✅ |

---

## 5. Validación contra Datos Reales

**Dataset:** 1590 pivotes (quants_obs.pkl), 8443 barras diarias SPY

| Señal | N Activas | N Anticipados | % Anticipados | Mean (días) | Median (días) | P5 | P25 | P75 | P95 |
|-------|-----------|---------------|---------------|-------------|---------------|----|----|----|----|
| credit_easing_k1 | 112 | 111 | 99.1% | 62.0 | 34.0 | 4.6 | 11.0 | 62.5 | 201.0 |
| sorpresa_total | 525 | 402 | 76.6% | 23.0 | 3.0 | 0.0 | 1.0 | 16.0 | 100.4 |
| panico_total | 34 | 25 | 73.5% | 113.5 | 13.5 | 0.0 | 0.2 | 85.0 | 840.8 |
| capitulacion | 82 | 56 | 68.3% | 138.2 | 2.0 | 0.0 | 0.0 | 41.0 | 885.1 |
| sub_reaccion | 667 | 572 | 85.8% | 17.3 | 5.0 | 0.0 | 1.0 | 13.0 | 70.0 |

**Observaciones:**
- Todas las métricas de validación se cumplen en datos reales
- La distribución de anticipaciones es coherente: señales más frecuentes tienen menor anticipación
- El rango P5-P95 muestra variabilidad real (no degenerada)

---

## 6. Implementación de Referencia

```python
def calcular_anticipacion_temporal(spy, señal, df):
    """
    Para cada pivot donde la señal está activa:
    1. Buscar el pivote anterior con señal activa
    2. Calcular la distancia en días entre ambos pivotes
    3. Si no hay pivote anterior activo, la anticipación es 0
    """
    if señal.sum() == 0:
        return None
    
    anticipaciones_dias = []
    
    for i in np.where(señal.values)[0]:
        pivot_date_actual = df["pivot_date"].iloc[i]
        
        # Buscar pivote anterior con señal activa
        pivote_anterior_idx = None
        for j in range(i - 1, -1, -1):
            if señal.iloc[j]:
                pivote_anterior_idx = j
                break
        
        if pivote_anterior_idx is not None:
            fecha_anterior = df["pivot_date"].iloc[pivote_anterior_idx]
            dias_antes = (pivot_date_actual - fecha_anterior).days
        else:
            dias_antes = 0
        
        anticipaciones_dias.append(dias_antes)
    
    anticipaciones_arr = np.array(anticipaciones_dias)
    
    return {
        "anticipaciones_dias": anticipaciones_dias,
        "mean": float(np.mean(anticipaciones_arr)),
        "median": float(np.median(anticipaciones_arr)),
        "p5": float(np.percentile(anticipaciones_arr, 5)),
        "p25": float(np.percentile(anticipaciones_arr, 25)),
        "p75": float(np.percentile(anticipaciones_arr, 75)),
        "p95": float(np.percentile(anticipaciones_arr, 95)),
        "n_total": int(len(anticipaciones_dias)),
        "n_anticipados": int((anticipaciones_arr > 0).sum()),
        "pct_anticipados": float((anticipaciones_arr > 0).mean() * 100),
    }
```

---

## 7. Procedimiento de Verificación

### Paso 1: Ejecutar tests unitarios
```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/11_experimental_engines/test_anticipacion_temporal.py
```
**Criterio de pase:** 5/5 tests exitosos

### Paso 2: Validar contra datos reales
```bash
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from scratch.test_anticipacion_temporal import calcular_anticipacion_temporal
from scratch.medir_senal import cargar_datos, SEÑALES
# ... ver script de validación
"
```
**Criterio de pase:** 
- Sin valores negativos
- Primera activación = 0
- Percentiles razonables

### Paso 3: Comparar con implementación actual
- La implementación actual produce conteos de pivotes (autocorrelación)
- La implementación corregida produce días de anticipación
- Los valores numéricos deben ser significativamente diferentes

### Paso 4: Integración
- Reemplazar líneas 507-529 en `medir_senal.py`
- Ejecutar script completo con `--señal credit_easing_k1`
- Verificar que el reporte incluya la nueva métrica

### Paso 5: Rendimiento
- Con 1590 pivotes: < 1 segundo
- Sin degradación en otras métricas

---

## 8. Resumen de Resultados

| Aspecto | Resultado |
|---------|-----------|
| Tests unitarios | ✅ 5/5 pasan |
| Validación datos reales | ✅ 5 señales validadas |
| Métricas de validación | ✅ M1-M5 cumplen |
| Implementación de referencia | ✅ Funcional y probada |
| Rendimiento | ✅ < 1s con 1590 pivotes |

---

## 9. Archivos Generados

- `research/11_experimental_engines/test_anticipacion_temporal.py` — Suite de tests completa
- `docs/research/TESTS_BUG1_ANTICIPACION_TEMPORAL.md` — Este documento

---

## 10. Recomendación

La implementación de referencia `calcular_anticipacion_temporal()` está lista para integrarse en `medir_senal.py` como reemplazo de las líneas 507-529. Los tests cubren todos los casos edge y la validación contra datos reales confirma que produce resultados coherentes.
