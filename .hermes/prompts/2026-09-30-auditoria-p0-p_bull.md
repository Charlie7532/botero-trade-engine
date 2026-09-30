# PROMPT DE AUDITORÍA — P0 BLOQUEANTE: El `p_bull` cruzado (fuente de verdad y procedencia)

**Destino:** agente auditor (Antigravity: Gemini / Claude guiada)
**Fecha:** 2026-09-30
**Preparado por:** Hermes (guiar / auditar / construir prompts — NO programar)
**Naturaleza:** **AUDITORÍA** (diagnostica y determina la fuente de verdad; NO implementa el fix).
**Prioridad:** **BLOCKER** — bloquea el rediseño de escalas, los regímenes y la confluencia METAR.

---

## 0. OBJETIVO

Determinar **la fuente de verdad** del campo `p_bull` (y su simétrico `p_bear` y el `ev_net` derivado), **auditar la procedencia** de los Fact Stores, y **especificar la corrección + el orden de regeneración**. Tres preguntas:

1. ¿`p_bull` debe ser **P(MAX)** (`n_pos/n_tot`, como manda el KI) o **P(MIN)** (`n_neg/n_tot`, como está en el código/datos)?
2. ¿Los JSON actuales (`rc_tide_ev_derived.json`, `rc_ev_multiscale_tree.json`, `rc_multiscale_regime_rules.json`) se regeneraron **con el bug o con la corrección**?
3. ¿Cuál es el **impacto cuantificado** y qué se debe regenerar, en qué orden?

**No implementes el fix** en esta etapa: diagnostica, decide y especifica.

---

## 1. CONTEXTO — La contradicción (verificada, no relato)

### 1.1. Lo que dice el KI `ev-horizon-divergence` (validado 2026-07-28)
Ruta: `/root/.gemini/antigravity-ide/knowledge/ev-horizon-divergence/artifacts/empirical_rules.md`
> **Regla 1:** *"p_bull = P(next pivot = MAX) = n_pos / n_tot. **NUNCA** usar `n_neg / n_tot`… El bug original cruzaba `P(piso) × E[retorno al techo]`, inflando el EV en ~3pp."*
> **Regla 7:** *"`generate_tide_ev_real_derived.py` (**FIXED L63**) … `rc_tide_ev_derived.json` ✅ **REGENERADO 2026-07-28**"*; *"`generate_multiscale_ev_derived.py` (**FIXED L60**)"*.

### 1.2. Lo que dice el CÓDIGO real (verificado 29-30 Sep)
```python
# generate_tide_ev_real_derived.py  L63:  raw_p_bull = n_neg / n_tot  # P(floor / bottom MIN)
# generate_multiscale_ev_derived.py L60:  raw_p_bull = n_neg / n_tot
```
→ **La corrección declarada por el KI NO está en el código.** Ambos generadores usan `n_neg/n_tot`.

### 1.3. Lo que dicen los DATOS (verificado)
`rc_tide_ev_derived.json` → `p_bull` **= `n_neg/n_tot` = P(MIN)** (coincidencia exacta: en `T~|C~|~`, `p_bull`=0.4556 = `n_neg/tot`; en otros estados difiere solo por el shrinkage bayesiano hacia el padre).

### 1.4. El impacto ya medido (ejercicio de Hermes, 30-Sep)
Recalculando el EV con la fórmula corregida (P(MAX)) vs la actual (P(MIN)), **la conclusión se INVIERTE**:

| Bin VWAP | EV ACTUAL (cruzado) | EV CORREGIDO (P(MAX)) |
|---|---:|---:|
| `<<` | **+0.0576** | **−0.0023** |
| `>>` | **−0.0298** | **+0.0479** |

→ La "señal" de reversión al VWAP **cambia de signo**. Es la trampa *"drift alcista secular inflando el EV"*.

---

## 2. TAREAS

### TAREA 1 — Adjudicar la fórmula correcta (con razonamiento de fuente)
1. Leer el KI completo (`empirical_rules.md`) y los 2 generadores + el lookup + los docstrings.
2. Determinar, **desde la definición económica**, qué debe ser `p_bull`:
   - Si `ev_net = p_bull × e_ret_max + p_bear × e_ret_min` debe ser **el retorno esperado E[R]**, entonces `p_bull = P(MAX)=n_pos/n_tot` (el resultado es la media de los retornos) → **confirma el KI**.
   - Si `p_bull` debe ser una **señal de posicionamiento** (`≈ P(piso)−P(techo)`), entonces `n_neg/n_tot` es intencional y **el KI estaría equivocado**.
3. **Declarar cuál es la fuente de verdad con argumento de fuente** (no preferencia). Investigar en los hilos históricos (`dda7ae62`, `68bcd487`) y en `mathematical_expectation_manifesto.md` / `scientific_fact_tables_and_heaven_hell_bifurcation.md` / `mathematical_expectation_manifesto.md` (brain de 68bcd487) qué definición se pactó.

### TAREA 2 — Auditar la procedencia de los Fact Stores
1. ¿`rc_tide_ev_derived.json` fue regenerado el 2026-07-28 como dice el KI? Verificar `_documentation`, `version`, `git log` del archivo, y la fecha de modificación.
2. Lo mismo para `rc_ev_multiscale_tree.json` y `rc_multiscale_regime_rules.json`.
3. Determinar si el contenido actual es **pre-fix** (buggy) o **post-fix** (corregido). *(El dato ya dictamina: `p_bull = P(MIN)`. Falta probar si eso llegó por regeneración o quedó del estado previo.)*
4. **¿Hubo una corrección que se perdió?** Buscar en git el commit que tocó L63/L60 y si fue revertido. (Patrón conocido en este repo: `65917ba`/`9ee684f` perdieron los `.md` de diseño.)

### TAREA 3 — Cuantificar el impacto y el alcance
1. Reproducir la inversión de EV (usar `rc_tide_ev_probability_table.json` RAW: `n_pos`, `n_neg`, `sum_max`, `sum_min` por escala).
2. Enumerar **todos los campos afectados**: `p_bull`, `p_bear`, `ev_net`, `sharpe`, `ev_per_day` (¿y `rr_asymmetry`, `e_ret_*`, `e_days`? — el KI dice que estos NO).
3. Enumerar **todos los consumidores afectados**: `rc_tide_ev_lookup.py` (→ `RealEVSignal`), `rc_swing_ev_decision_engine.py`, los 5 lookups de `swing_gate.py`, y las reglas de decisión (D-001..D-015).
4. Estimar el **impacto operativo** (¿cambian las decisiones ACCUMULATE/TRIM/HARVEST?).

### TAREA 4 — Especificar la corrección y su orden (SIN implementar)
1. Corrección exacta de L63/L60 (y de los `field_glossary`/docstrings desfasados).
2. **Orden de regeneración** (del KI Regla 7): `train_tide_ev_real_table` → `generate_tide_ev_real_derived` → `train_multiscale_regime_ml` → `generate_multiscale_ev_derived`.
3. Protocolo de verificación (que el nuevo `p_bull` coincida con `n_pos/n_tot`, no con `n_neg/n_tot`).
4. Plan de convivencia/rollback (¿regenerar in-place o v2 paralela?) — ver P-004/P-007.

### TAREA 5 — Plan de migración de hallazgos (responde la preocupación del Arquitecto)
> *"¿Cómo actualizamos los hallazgos que ya tenemos para trasladarlos a las nuevas escalas y formatos?"* (registrado como **P-010** en `PROPOSALS.md`)
1. Inventariar los hallazgos ya validados que dependen de estas escalas/formatos (KI `ev-horizon-divergence`, KI `zz-s5-breadth-coincidence`, heatmap EV, gradientes, D-001..D-015).
2. Para cada uno: ¿**sobrevive** el cambio (de escala y/o de fórmula), o hay que **re-medirlo**?
3. Proponer el **puente de homologación viejo↔nuevo** (remapeo de bins / re-medición / re-anclaje) para no perder lo aprendido.

---

## 3. FUERA DE SCOPE (registrado, NO se aborda aquí)
- **P-008** Heterogeneidad de historial por ticker (ventana/incepción/N_min) — anotado en `PROPOSALS.md`.
- **P-009** Registro/interpretación/excepción de Overflow / Blowoff — anotado en `PROPOSALS.md`.
- Diseño de escalas adaptativas per-ticker (espera al P0).
- Implementación del fix.

---

## 4. ARCHIVOS DE REFERENCIA

| Archivo | Rol | Prioridad |
|---|---|:---:|
| `/root/.gemini/antigravity-ide/knowledge/ev-horizon-divergence/artifacts/empirical_rules.md` | KI con la Regla 1 (fórmula) y Regla 7 (procedencia) | 🔴 OBLIGATORIO |
| `backend/scripts/generators/generate_tide_ev_real_derived.py` | L63 (fórmula), L156-190 (`_documentation`, `field_glossary`) | 🔴 |
| `backend/scripts/generators/generate_multiscale_ev_derived.py` | L60 | 🔴 |
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json` | Datos (`p_bull`, `ev_net`) | 🔴 |
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_probability_table.json` | RAW (`n_pos`, `n_neg`, `sum_max`, `sum_min`) | 🔴 |
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_lookup.py` | Consumidor + docstring L33 | 🔴 |
| `backend/scripts/trainers/train_tide_ev_real_table.py` | Origen de los conteos | 🟠 |
| `docs/modules/quality_swing/tide/PROPOSALS.md` · `README.md` | Memoria de diseño + pendientes | 🟠 |

---

## 5. LÍMITES DEL SCOPE

- ✅ **Aislar** el diagnóstico en el pipeline Tide-EV / Multiscale-EV.
- ✅ **Proteger** el código de producción — **solo lectura** (este prompt audita, no corrige).
- ✅ **Respetar** las tablas actuales como artefacto a diagnosticar (no regenerar aquí).
- ✅ **Conservar** la separación viejo/nuevo en cada conclusión.
- ✅ **Ejecutar** comandos reales para cada afirmación (verificar ≠ inferir).
- ✅ **Fundamentar** la adjudicación de `p_bull` en definición económica + cita de fuente, no en preferencia.
- ✅ **Reportar** la tabla completa (todos los estados afectados), no solo el caso peor.

---

## 6. CRITERIO DE ACEPTACIÓN

- [ ] Queda **declarada la fuente de verdad** de `p_bull` (P(MAX) vs P(MIN)) con argumento de fuente.
- [ ] Queda **probada la procedencia** de los 3 JSON (regenerados pre/post-fix; ¿se perdió la corrección?).
- [ ] Tabla de **campos afectados** y de **consumidores afectados**.
- [ ] **Impacto operativo** estimado (¿cambian decisiones?).
- [ ] **Corrección + orden de regeneración** especificados (sin implementar).
- [ ] **Plan de migración de hallazgos** (P-010) con veredicto sobrevivir/re-medir por hallazgo.
- [ ] Cada afirmación con `archivo:línea` + comando + output real.

---

## 7. AUTOTEST (obligatorio — ejecutar antes de responder; valores ya verificados)

1. `grep -n "raw_p_bull" backend/scripts/generators/generate_tide_ev_real_derived.py` → L63 = **`n_neg / n_tot`** (buggy).
2. `grep -n "raw_p_bull" backend/scripts/generators/generate_multiscale_ev_derived.py` → L60 = **`n_neg / n_tot`**.
3. Comparar `p_bull` del JSON vs `n_pos/tot` y `n_neg/tot` en `T~|C~|~` → coincide con **`n_neg/tot`** (0.4556).
4. El KI declara "FIXED L63/L60 → n_pos/n_tot" → **contradice** el código → confirmar la contradicción.
5. EV `<<` cruce: actual **+0.0576** vs corregido **−0.0023**; `>>`: **−0.0298** vs **+0.0479**.

Si algo no coincide → detente y corrige la lectura antes de continuar.

---

## 8. ENTREGABLE

Reporte markdown, numerado, con bloques `DIAGNÓSTICO` y `PLAN PROPUESTO (sin aplicar)` separados. **No modifiques código.** Cierra con:
1. La **decisión de fuente de verdad** (`p_bull` = ¿P(MAX) o P(MIN)?) y su fundamento.
2. El **veredicto de procedencia** de los JSON.
3. La **corrección + orden de regeneración**.
4. El **plan de migración de hallazgos** (P-010).
