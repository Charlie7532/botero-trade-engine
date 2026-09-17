# PROMPT: Corrección Consolidada — Fuente de Verdad Única + Reversión de Rehabilitaciones + Opción C

**Destino:** `arnes/señales.py`, `consultar_inteligencia.py`, `construir_bar_snapshot.py`, `regenerar_fact_stores.py`, `consolidar_ranking.py`
**Fecha:** 03-Sep-2026 (noche)
**Origen:** Auditoría del plan de implementación (08:54) + verificación empírica de la desalineación VAV vs GENERAL.

---

## PARTE 1 — AUDITORÍA: La desalineación VAV vs GENERAL (medida, 2,000 trades idénticos)

Los dos evaluadores **no miden lo mismo**. Verificado ejecutando los mismos 2,000 trades con ambos métodos:

| Escala | VAV (close, sin límite) | GENERAL (OHLC, time-stop C9) | Δ HR | Timeouts GENERAL |
|:-------|:-----------------------:|:--------------------------:|:----:|:----------------:|
| zz25 | 0.580 | 0.545 | +0.035 | 1 |
| zz50 | 0.632 | 0.558 | +0.074 | 630 |
| zz75 | 0.706 | 0.409 | **+0.297** | 1,469 |

**3 causas estructurales:**

| Causa | VAV (`evaluador_vela_a_vela.py`) | GENERAL (`evaluador_general.py`) |
|:------|:---------------------------------|:---------------------------------|
| **Time-stop** | NO — `first_passage()` L149-177 corre hasta la barrera | SÍ — `first_passage_bar()` L117-175 con C9 (80/40/27), timeout=falla |
| **Precio** | close-only | OHLC intrabar (high/low) |
| **Población** | solo pivotes de quants_obs (1,590) | todas las barras (8,453) |

**Consecuencia:** el ranking maestro mezcla `rendimiento_lake` (GENERAL) con `rendimiento_pivotes_vav` (VAV) como si fueran comparables. **No lo son.** Cualquier calificación basada en `rendimiento_lake` de una señal posicional es sospechosa (ver Parte 2).

---

## PARTE 2 — AUDITORÍA: Las 2 señales rehabilitadas están inválidas (3 razones independientes)

`señales.py` L338-342 (`credit_equity_divergence`) y L366-369 (`defensive_rotation_divergence`) fueron rehabilitadas a "VALIDATED Grade A" en la Fase 0. **Las 3 razones por las que es inválido:**

1. **Contradicción interna:** el decorador dice `VALIDATED Grade A` pero el docstring de la función sigue diciendo `[GRADO C 20-Ago-2026]` y `[RETIRADA 20-Ago-2026]`. La misma señal se autodescribe como validada y retirada a la vez.

2. **El "Lift +38%/+32.4%" viene del `rendimiento_lake` (GENERAL), no del VAV.** Verificado en `ranking_maestro.json`: `rendimiento_pivotes_vav` → `mejor_celda: null, fav_neto: null, hit_neto: null, p_value: null`. El VAV **las excluye por P1** (filtran `pivot_type=="MAX"` en el cuerpo = sesgo de posición embebido). No hay medición VAV que respalde el lift.

3. **El lake NO tiene `pivot_type` ni `pivot_date`** (verificado). Estas señales filtran `pivot_type=="MAX"` en su cuerpo → **no pueden disparar en el lake** → su `rendimiento_lake` es un artefacto matemático (señal siempre False → comparación vacía).

**Conclusión:** la rehabilitación (0.4 de Fase 0) fue prematura. Las 2 señales deben **volver a RETIRADA/DEGRADADA** hasta que se evalúen con su medición canónica de pivotes (`medicion_*.json`), como el plan C4 propone para `sv5t_silent_distribution`.

---

## PARTE 3 — CORRECCIONES

### C1 — Revertir las 2 señales a su estado previo (señales.py)

```python
# credit_equity_divergence (L337-342) — REVERTIR a:
@_registrar("credit_equity_divergence",
    validacion="DEGRADADA GRADO C (LIFT≈1.0 — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="EXIT: Techo MAX con spread de crédito acelerando al alza. LIFT(MAX)=1.035x ≈ baseline (82.9%→85.8%) — NO discrimina.",
    tipo="exit", pivot_type="MAX",
    fecha_inicio_valida="2007-04-11", era_valida="POST_2007",
    descripcion="DEGRADADA: divergencia crédito-equity en techos. LIFT≈1.0 = no discrimina vs baseline. Solo monitorear con filtro HH.")

# defensive_rotation_divergence (L365-369) — REVERTIR a:
@_registrar("defensive_rotation_divergence",
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
    fuente="EXIT: Techo MAX con rotación de capital colapsando hacia defensivos (FAST_CRUSH_3D)",
    tipo="exit", pivot_type="MAX",
    descripcion="RETIRADA: en techo, rotación colapsa hacia defensivos. LIFT<1.0 = anti-señal, peor que baseline.")
```

**Y alinear el docstring de la función con el decorador** (ambos deben decir RETIRADA/DEGRADADA, no VALIDATED).

**Nota:** la rehabilitación queda **pendiente** de la medición canónica de pivotes (C4 del plan de rescate de diamantes). Cuando `medicion_*.json` confirme el lift con la metrología correcta, se rehabilita con evidencia.

### C2 — Método de medición único + ancla según naturaleza de la señal (CORRECCIÓN de la Regla Canónica)

**Regla canónica (REVISADA 03-Sep según tu corrección):** NO existe un "evaluador que prevalece" ni un "evaluador que nunca califica". Hay **UN método de medición** — first-passage **sin time-stop** (el movimiento termina cuando cambia de régimen del zz, no en velas fijas) — y la única diferencia es el **ancla del disparo**, que se elige según la naturaleza de la señal.

**Precisión clave (verificada en el código):** el VAV y el GENERAL **usan el MISMO medidor** (`first_passage` / `first_passage_bar` — ambos caminan por todas las velas midiendo el primer toque de barrera). **No hay dos metrologías de medición.** La diferencia es el **ancla del disparo**:

| Dimensión | VAV (`evaluador_vela_a_vela`) | GENERAL (`evaluador_general`) |
|:----------|:----|:--------|
| **Dónde dispara** | Solo en pivotes (`df` = quants_obs) | En cualquier barra detectada (lake completo) |
| **Primer bar del episodio** | El pivote | La primera barra activa |
| **Qué captura** | Señales en puntos de **giro** | Señales en **cualquier momento** (incl. momento/continuo) |
| **Baseline** | Pivotes del mismo tipo (P5) | Incondicional (era) |

**Rol correcto de cada uno (ambos califican, según el ancla):**

| Naturaleza de la señal | Ancla correcta | Fuente de calificación que prevalece |
|:-----------------------|:----------------|:-------------------------------------|
| De **giro/reversión** (marca techo/suelo) | Pivote | VAV |
| De **momento/continuo** (ej. complacencia, dispara en cualquier barra) | Continuo | GENERAL |

Para el rendimiento operativo real, el GENERAL es más representativo porque captura la señal donde sea que dispare. El **descubrimiento** (VAV) y la **verificación continua** (GENERAL) son **dos etapas del mismo flujo de calificación**, no frameworks rivales.

**Criterios unificados que SÍ prevalecen (para ambas anclas):**
1. **Método de medición único:** first-passage **sin time-stop** (se elimina C9 80/40/27). `resuelto:False` = censura de borde, **excluido** del HR, no pérdida. Se reporta `resolution_rate`.
2. **PRECIO: OHLC intrabar ESTANDARIZADO (DECISIÓN TOMADA 03-Sep).** El toque de barrera se detecta dentro de la vela (`high`/`low`), no solo al cierre. Es el criterio de resolución real de barrera. **Se estandariza en AMBOS evaluadores** (VAV y GENERAL) reemplazando el `close-only` del VAV.
   - **Impacto medido (3,000 trades, sin time-stop):** OHLC produce ~2.6–2.9pp MENOS de HR que close (zz25: 0.585→0.559; zz50: 0.644→0.615; zz75: 0.695→0.666). OHLC es más exigente: detecta la barrera adversa intrabar antes que el close.
   - **Consecuencia:** el `bar_augment` actual (close: 0.5829/0.6382/0.7007) queda **obsoleto** y se regenera con OHLC.
   - **Umbral de equivalencia redefinido:** ya NO ±1pp contra el VAV en close. La equivalencia es INTERNA (pivote vs continuo) sobre OHLC estandarizado.
3. **`bars`, `mae_p90`, `mae_p95`, `rr_celda`** reportados por celda como dato descriptivo, no como corte. `rr < 1 → celda NO operable`.
4. **Ranking:** etiquetar `rendimiento_lake` como `ancla:continuo` y `rendimiento_pivotes_vav` como `ancla:pivote`. NO promediarlos ni elegir el mejor entre ellos. Reportar el ancla correspondiente a la naturaleza de cada señal.

### C3 — Reformular C3 del plan a Opción C pura (ya decidida)

El plan de Opus (08:54) implementa **Opción B** (`time_stop_celda = P90(bars)`), que contradice la **Opción C** decidida. Corregir:

```python
# OPCIÓN C (definitiva) — first-passage sin time-stop, OHLC intrabar estandarizado:
#   La medición usa high/low para detectar el toque de barrera (no close-only).
#   Unificar en ambos evaluadores (VAV y GENERAL) al MISMO criterio OHLC.
#   hit  → tocó primero la barrera favorable (high>=+scale o low<=-scale, intrabar)
#   loss → tocó primero la barrera adversa
#   resuelto:False → no tocó ninguna barrera → EXCLUIDO del HR (no es pérdida)
#   bars = event_i + 1  (duración real, sin techo)
#   resolution_rate = resueltos/total  (obligatorio por escala)
#   bars_medio + bars_p90 por celda  (reportados como dato, no como corte)
#   rr_celda = mfe_medio/|mae_medio|  (rr < 1 → celda NO operable)
```

**Eliminar** `time_stop_celda = P90(bars)` y `mae_limite_celda = P95(MAE)` como cortes. El `P90(bars)` se reporta como dato informativo, no como límite. El `mae_p95` se reporta como referencia de "break of structure" para el risk manager, no como corte del motor.

### C4 — Verificación de equivalencia obligatoria

Antes de aceptar cualquier número del motor, verificar contra el VAV:

```bash
# Para cada señal de prueba (cascade_reversal, panico_total, credit_stress):
#   |HR_motor − HR_VAV| ≤ 1pp por celda en zz25
#   Si zz50/zz75 difieren >±1pp, la causa debe ser documentada (OHLC vs close)
#   y el número NO se usa para calificar hasta resolver la causa.
```

### C5 — Alinear el `evaluador_general` al VAV (misma metrología de medición)

**Corrección conceptual (03-Sep noche):** el VAV NO mide "solo en pivotes". Releído el código:

| Capa | VAV (`evaluador_vela_a_vela.py`) |
|:-----|:----------------------------------|
| **Disparo** | La señal se evalúa sobre `df` = quants_obs (1,354 pivotes). `disparos = pivotes donde la señal es True` |
| **Medición** | `first_passage(prices, t_pos, ...)` con `t_pos = spy_idx.searchsorted(pivot_date)` → **posición en el LAKE (8,453 barras)**. El first_passage **camina por TODAS las velas siguientes** hasta tocar la barrera |
| **Baseline** | Pivotes del mismo tipo (P5), excluyendo los de la señal |

**Conclusión:** el VAV mide el **camino del precio en todas las velas** desde cada pivote de disparo. El pivote es el **ancla** del disparo y del baseline, no el límite de la medición. (Confirmado: `t_pos` es posición en el lake; `first_passage` recorre `prices[t_pos+1:]` = todas las velas.)

**Por tanto, la diferencia VAV vs GENERAL es el DISPARO, no la medición:**

| | VAV | GENERAL |
|:--|:----|:--------|
| **Disparo** | En pivotes (df = quants_obs) | En todas las barras (episodios continuos) |
| **Medición** | Camina todas las velas desde el pivote | Camina todas las velas desde la 1ª barra del episodio |
| **Baseline** | Pivotes del mismo tipo (P5) | Incondicional |

**Alineación del GENERAL (3 cambios para compartir la metrología del VAV):**

```python
# 1. Time-stop C9 → sin límite:  max_barras = None (ya soportado en la firma L119)
# 2. Timeout → resuelto:False excluido (no falla):  alinear a VAV L161-162
# 3. OHLC → close-only:  añadir modo use_close_only=True (el VAV usa solo close)
```

**La diferencia de disparo (pivote vs continuo) NO se alinea — se declara como propósito legítimo:**
- VAV = calificación de señales (ancla a eventos de giro)
- GENERAL = fichas de estado por barra (ancla al continuo)

**Consecuencia para el ranking:** una vez alineado el GENERAL en time-stop/timeout/close, `rendimiento_lake` y `rendimiento_pivotes_vav` **comparten la misma metrología de medición** (first-passage por todas las velas) y solo difieren en el ancla del disparo. El ranking puede reportar ambos con etiqueta clara (`ancla: pivote` vs `ancla: continuo`), pero **no** promediarlos ni elegir el mejor entre ellos sin declarar el ancla.

---

## PARTE 4 — Tabla de trazabilidad

| Corrección | Origen | Evidencia |
|:-----------|:-------|:----------|
| C1 revertir 2 señales | Auditoría 03-Sep noche | Lake sin `pivot_type`; VAV las excluye por P1; docstring contradictorio |
| C2 VAV = fuente única | Desalineación medida | Δ HR hasta +29.7pp en zz75 entre VAV y GENERAL |
| C3 Opción C pura | Decisión del usuario 03-Sep | "El movimiento termina cuando cambia de régimen del zz, no en velas fijas" |
| C4 equivalencia | C6 del prompt de realineamiento | `|HR_motor − HR_VAV| ≤ 1pp` |
| C5 alinear GENERAL | Corrección del usuario 03-Sep | VAV mide el camino del precio en todas las velas; la diferencia es el ancla del disparo |

---

## PARTE 5 — Qué NO se toca

- `evaluador_vela_a_vela.py` y `evaluador_general.py`: canónicos, intactos (solo se declara cuál es la fuente de verdad).
- `sv5t_silent_distribution`: sigue como DIAMANTE SUPREMO, con fallback a `medicion_*.json` (C4 del plan de rescate).
- `_fire` suffix, filtro inception, no-duplicación del lake: conservados.
- El `evaluador_general` sigue existiendo para fichas de estado por barra — solo deja de ser fuente de calificación de señales.