# PROMPT — Enmienda: Corrección de 5 hallazgos Opus NO implementados

**Para:** Pipeline Hermes (Worker qwen-2.5-coder-32b → Auditor qwen3.8-max)
**De:** Juan Andrés (Arquitecto) vía Gemini → Hermes
**Fecha:** 20-Ago-2026
**Prioridad:** P0 (CORRECTIVO)
**Estado:** NUEVO

---

## 0. EL PROBLEMA

El 20-Ago-2026 Claude Opus auditó los 5 addenda implementados en `medir_senal.py` y encontró **7 hallazgos** (PC1-PC7). Hermes verificó **5 de ellos como confirmados** contra datos reales. El prompt original los marcó como "OBLIGATORIO INCORPORAR". Sin embargo, **ninguno de los 5 fue corregido en el código** — solo quedaron documentados en el reporte.

**Impacto:** el arnés contiene 4 señales EXIT que son PEOR que el baseline (lift<1.0), 2 que son ruido puro (fire rate>50%), un duplicado 100%, métricas inconsistentes (RandomState/ default_rng), y falta la métrica de LIFT.

**Este prompt corrige esos 5 hallazgos en el código. No es una auditoría nueva. Es una enmienda quirúrgica.**

---

## 1. LOS 5 HALLAZGOS A CORREGIR (datos verificados)

| # | Hallazgo | Evidencia | Corrección requerida |
|---|----------|-----------|---------------------|
| H1 | **4 señales EXIT tienen lift<1.0** (peor que baseline) | defensive_rotation=0.828x, sv5t_silent=0.840x, regime_change=0.789x, credit_ease=0.954x | **Retirar** del registro activo — cambiar `validacion` a `"RETIRADA (lift<1.0)"` y docstring a `[RETIRADA 20-Ago-2026: lift<1.0 vs baseline MAX 83.4%]` |
| H2 | **2 señales EXIT tienen fire rate > 50%** (ruido de régimen) | breadth_contraction 87.7%, credit_ease 51.6% | **Retirar** — breadth_contraction_exit dispara en 88% de pivotes (no es señal). credit_ease_exit ya está en H1 por lift<1.0 |
| H3 | **vix_complacency_exit ≡ euforia** (100% overlap) | N=41 idéntico, 100% overlap en pivotes MAX | **Consolidar** — eliminar `vix_complacency_exit` (es subconjunto idéntico de euforia). La definición de euforia ya cubre VIX en DEEP_COMPLACENCY/LOW_VOL |
| H4 | **Falta LIFT vs base rate** en output de medir() | forense_precursores.py lo tiene; medir_senal.py no | **Agregar** métrica `lift_vs_baseline` al JSON de salida. Fórmula: `lift = P(cae|señal) / P(cae|¬señal)` condicionado por pivot_type |
| H5 | **RandomState vs default_rng** inconsistencia | L466 usa default_rng; L1060, L1087 usan RandomState | **Unificar** a `np.random.default_rng(seed)` en las 3 ocurrencias |

### H4 — Fórmula exacta de LIFT

```python
# ─── LIFT vs baseline condicionado por pivot_type ───
def _lift_vs_baseline(señal, fwd, df):
    """Calcula lift = P(cae | señal) / P(cae | ¬señal) condicionado por pivot_type."""
    pivot_types = df.loc[señal, "pivot_type"].unique()
    lifts = {}
    for pt in pivot_types:
        mask_pt = df["pivot_type"] == pt
        mask_activa = señal & mask_pt & fwd.notna()
        mask_no_activa = (~señal) & mask_pt & fwd.notna()
        n_act = mask_activa.sum()
        n_noact = mask_no_activa.sum()
        if n_act < 3 or n_noact < 3:
            continue
        p_cae_act = float((fwd[mask_activa] <= 0).mean())
        p_cae_noact = float((fwd[mask_no_activa] <= 0).mean())
        lift = p_cae_act / p_cae_noact if p_cae_noact > 0 else 999.0
        lifts[pt] = {
            "n_activa": int(n_act), "n_no_activa": int(n_noact),
            "pct_cae_activa": round(p_cae_act * 100, 1),
            "pct_cae_no_activa": round(p_cae_noact * 100, 1),
            "lift": round(lift, 3),
            "interpretacion": ">1.0=señal real, <1.0=anti-señal, ≈1.0=ruido"
        }
    return lifts
```

Insertar en `medir_senal.py` antes de `medir()`. Llamar al final de `medir()`: `rep["lift_vs_baseline"] = _lift_vs_baseline(señal, fwd, df)`.

---

## 2. PIPELINE DE EJECUCIÓN

```
WORKER (qwen-2.5-coder-32b)
  │
  ├─ H1: Retirar 4 señales EXIT con lift<1.0
  ├─ H2: Retirar 1 señal con fire rate>50% (breadth_contraction)
  ├─ H3: Consolidar vix_complacency_exit → euforia
  ├─ H4: Implementar _lift_vs_baseline() + integrar en medir()
  ├─ H5: Unificar RandomState → default_rng
  └─ Verificar: ejecutar al menos 3 señales para confirmar regresión cero
        │
        ▼
   plan_worker.json
        │
        ▼
AUDITOR (qwen3.8-max)
  │
  ├─ Verificar que las 5 correcciones se aplicaron
  ├─ Confirmar regresión cero (métricas clave idénticas)
  ├─ Verificar que el LIFT se calcula correctamente
  ├─ Buscar errores en las correcciones
  └─ Emitir Confidence Card
        │
        ▼
   reporte_auditor.md
```

---

## 3. FASE 1 — WORKER (qwen-2.5-coder-32b)

**Perfil:** `worker` — modelo codec. Aplica cambios quirúrgicos. No razona sobre dominio financiero.

**Archivo a modificar:** `research/01_señales_entry_exit/medir_senal.py` (1,433 líneas)

### Cambios exactos a realizar

#### Cambio 1 (H1): Retirar 4 señales EXIT

```python
# ─── SEÑAL: defensive_rotation_divergence ───
# Buscar: @_registrar("defensive_rotation_divergence"
# Reemplazar línea validacion por:
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
# Agregar al inicio del docstring:
    """[RETIRADA 20-Ago-2026: lift=0.828x vs baseline MAX 83.4%.
     Peor que no hacer nada. Anti-señal.] ...

# Repetir para: sv5t_silent_distribution, regime_change_exit, credit_ease_exit
```

#### Cambio 2 (H2): Retirar breadth_contraction_exit

```python
# Buscar: @_registrar("breadth_contraction_exit"
# Reemplazar línea validacion por:
    validacion="RETIRADA (fire rate 87.7% — 20-Ago-2026 Opus PC2)", n_min=None, dsr=None,
```

#### Cambio 3 (H3): Consolidar vix_complacency_exit → euforia

```python
# Buscar: @_registrar("vix_complacency_exit"
# Reemplazar línea validacion por:
    validacion="RETIRADA (duplicado 100% overlap con euforia — 20-Ago-2026 Opus PC3)", n_min=None, dsr=None,
```

#### Cambio 4 (H4): Implementar _lift_vs_baseline()

Insertar la función (ver §1, fórmula exacta) antes de `medir()`. Agregar llamada al final de `medir()`:

```python
# 4.17 LIFT vs baseline condicionado (ADDENDUM 9 — 20-Ago-2026)
rep["lift_vs_baseline"] = _lift_vs_baseline(señal, fwd, df)
```

#### Cambio 5 (H5): Unificar RandomState → default_rng

```python
# Buscar: rng = np.random.RandomState(seed)  (debe haber 2 ocurrencias, L1060 y L1087 aprox)
# Reemplazar por: rng = np.random.default_rng(seed)
```

### Verificación post-cambios

```bash
cd /root/botero-trade
# 1. Compilar
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -m py_compile research/01_señales_entry_exit/medir_senal.py

# 2. Ejecutar 3 señales (ENTRY, EXIT, neutra)
for s in credit_easing_k1 bsi_recovery sub_reaccion; do
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal $s --out /tmp/enmienda_$s.json
done

# 3. Verificar regresión: métricas clave idénticas a JSON histórico
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import json
old = json.load(open('data/research/signals/medicion_credit_easing_k1.json'))
new = json.load(open('/tmp/enmienda_credit_easing_k1.json'))
for k in ['activa','baseline','delta_media','triada','capture_ratio','estabilidad_decada']:
    assert json.dumps(old[k], sort_keys=True, default=str) == json.dumps(new[k], sort_keys=True, default=str), f'REGRESIÓN en {k}'
print('✅ Regresión CERO')
"

# 4. Verificar que LIFT aparece en el JSON
grep -l "lift_vs_baseline" /tmp/enmienda_credit_easing_k1.json

# 5. Verificar que RandomState fue eliminado
grep -c "RandomState" research/01_señales_entry_exit/medir_senal.py  # debe ser 0

# 6. Verificar que las 5 señales retiradas siguen registradas pero con validacion="RETIRADA"
grep "RETIRADA" research/01_señales_entry_exit/medir_senal.py | wc -l  # debe ser ≥5
```

**Formato de entrega:** `.hermes/reportes/2026-08-20_enmienda_worker.json` con:
```json
{
  "cambios_aplicados": ["H1","H2","H3","H4","H5"],
  "verificacion": {"compila": true, "regresion_cero": true, "lift_presente": true},
  "señales_retiradas": ["defensive_rotation_divergence", "sv5t_silent_distribution", "regime_change_exit", "credit_ease_exit", "breadth_contraction_exit", "vix_complacency_exit"],
  "random_state_unificado": true
}
```

---

## 4. FASE 2 — AUDITOR (qwen3.8-max)

**Perfil:** `auditor` — generalista analítico. Verifica las correcciones del worker y emite Confidence Card.

**Input:** `.hermes/reportes/2026-08-20_enmienda_worker.json` + `medir_senal.py` modificado

### Tareas

| # | Tarea | Verificación |
|---|-------|-------------|
| A1 | Re-compilar `medir_senal.py` y ejecutar con 3 señales. Verificar que el worker no rompió nada. | py_compile + ejecución |
| A2 | Verificar que las 6 señales retiradas tienen `validacion="RETIRADA"` y el docstring documenta la razón con datos | grep + lectura |
| A3 | Verificar que `lift_vs_baseline` se calcula correctamente: ejecutar credit_easing_k1 y verificar que el LIFT es >1.0 (señal real), luego defensive_rotation (si aún ejecuta) y verificar que <1.0 | Abrir JSON |
| A4 | Verificar que `RandomState` fue eliminado completamente del archivo | grep -c debe ser 0 |
| A5 | Confirmar regresión cero: métricas clave idénticas al JSON histórico de credit_easing_k1 | Comparación byte a byte |
| A6 | Buscar errores introducidos por el worker (¿las señales retiradas rompen algo? ¿el LIFT se calcula para señales con N<3?) | ≥2 hallazgos propios |
| A7 | Emitir Confidence Card: `[APROBADO / APROBADO CON RESERVAS / RECHAZADO]` | Al inicio del reporte |

**Formato de entrega:** `.hermes/reportes/2026-08-20_enmienda_auditor.md`

```markdown
# CONFIDENCE CARD: [APROBADO / APROBADO CON RESERVAS / RECHAZADO]
Justificación: ...

## 1. Verificación de correcciones del worker
| Corrección | Aplicada | Correcta | Evidencia |

## 2. Regresión
| Métrica | Old | New | Match |

## 3. Hallazgos propios
| # | Hallazgo | Severidad | Evidencia |
```

---

## 5. ARCHIVOS DE REFERENCIA

| # | Archivo | Buscar |
|---|---------|--------|
| 1 | `research/01_señales_entry_exit/medir_senal.py` | Archivo a modificar — señales a retirar, LIFT a agregar, RNG a unificar |
| 2 | `.hermes/reportes/auditoria_5_addenda_algoritmos.md` | Hallazgos PC1-PC7 de Claude Opus — fuente de verdad de lo que hay que corregir |
| 3 | `.hermes/reportes/2026-08-20_ejecucion_5-addenda-algoritmos.md` | Lo que se construyó y lo que NO se corrigió |
| 4 | `research/04_conjuncion_multi_estacion/forense_precursores.py` | Referencia de implementación de LIFT (función `analizar_precursores`) |
| 5 | `data/research/signals/medicion_credit_easing_k1.json` | JSON histórico para verificación de regresión |

---

## 6. AUTOTEST (5 preguntas — solo sobre esta enmienda)

| # | Pregunta | Respuesta esperada |
|---|----------|-------------------|
| 1 | ¿Cuántas señales se retiran en esta enmienda? ¿Por qué? | 6: 4 por lift<1.0 + 1 por fire rate>50% + 1 por duplicado |
| 2 | ¿Cuál es la fórmula exacta de `_lift_vs_baseline`? | `lift = P(cae|señal) / P(cae|¬señal)` condicionado por pivot_type |
| 3 | ¿Qué se unifica en H5? ¿A qué API? | `np.random.RandomState(seed)` → `np.random.default_rng(seed)` |
| 4 | ¿Qué métricas NO deben cambiar tras la enmienda? | activa, baseline, delta_media, triada, capture_ratio, estabilidad_decada |
| 5 | ¿Dónde se inserta la llamada a `_lift_vs_baseline`? | Al final de `medir()`, sección 4.17 |

---

## 7. LÍMITES DEL SCOPE

- ✅ **Retirar** las 6 señales identificadas (cambiar `validacion` a `"RETIRADA"`, documentar razón en docstring) — no se eliminan del código, solo se marcan como retiradas
- ✅ **Implementar** `_lift_vs_baseline()` e integrar en `medir()`
- ✅ **Unificar** RandomState → default_rng (2 líneas)
- ✅ **Verificar** regresión cero con al menos 3 señales de referencia
- ✅ **Conservar** todas las demás señales, funciones y métricas sin cambios
- ✅ **Preservar** la estructura del archivo — los cambios son mínimos y localizados

---

## 8. CRITERIOS DE ACEPTACIÓN

- [ ] Worker aplicó los 5 cambios (H1-H5) y verificó regresión cero
- [ ] Auditor confirmó que las 6 señales están marcadas como RETIRADA con razón documentada
- [ ] `lift_vs_baseline` aparece en el JSON de salida y se calcula correctamente
- [ ] `grep -c "RandomState" medir_senal.py` retorna 0
- [ ] Regresión cero confirmada por ambos agentes (métricas clave idénticas)
- [ ] Confidence Card emitida por el auditor

---

## 9. ENTREGABLES

| # | Agente | Entregable | Ubicación |
|---|--------|-----------|-----------|
| 1 | Worker | Código corregido + JSON de verificación | `medir_senal.py` + `.hermes/reportes/2026-08-20_enmienda_worker.json` |
| 2 | Auditor | Reporte + Confidence Card | `.hermes/reportes/2026-08-20_enmienda_auditor.md` |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes) — construido para Juan Andrés
**Fecha:** 20-Ago-2026