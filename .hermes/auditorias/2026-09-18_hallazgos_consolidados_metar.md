# AUDITORÍA CONSOLIDADA — Hallazgos Verificados del Motor METAR (tema en progreso)

> **Fecha:** 2026-09-18 · **Estado:** BITÁCORA VIVA — se enriquece tema a tema
> **Principio:** Dato mata relato. Todo hallazgo aquí fue VERIFICADO con datos (no relato ni narrativa).
> **Cita rectora:** "Los indicadores NO dan instrucciones de cómo operar. Emiten HECHOS. La decisión sale del compositor + Entry Gate."

---

## ÍNDICE DE PUNTOS DE AUDITORÍA ABIERTOS

| # | Tema | Hallazgo verificado | Prioridad | Estado |
|:-:|:-----|:--------------------|:---------:|:-------:|
| **A** | CAT mismatch de `fg` (station_profiles cat=2 vs family CAT3_ACTION) | 1 solo mismatch de 11. Aproblable (identidad, no lógica) | 🟡 Media | ✅ Verificado |
| **B** | Inconsistencia de escala: `sgs` (ratio) vs `scale_gradient` (diferencia) | 14.4% de estados cambian de clasificación según definición | 🔴 CRÍTICA | ✅ Verificado |
| **C** | `timing_mode=NOISE` es artefacto de umbral per-slot n≥5 | 96% de intermedias (5-9) con coherencia alta quedan NOISE; contradice signal_class FLOOR | 🔴 CRÍTICA | ✅ Verificado |
| **D** | Señales intermedias (5-9) NO degradadas por la concordancia | NOISE% 8.4% (la menor); FLOOR 68% — el discriminator las clasifica bien | 🟢 Info | ✅ Verificado |
| **E** | Coherencia temporal de señales intermedias | 38% en rango, 35.6% fuera, 26% mixto — el 38% es señal con patrón, no ruido | 🟢 Info | ✅ Verificado |
| **F** | Fallback NO_TIMING_DATA | 0 de 1189 estados → teórico, no se dispara | 🟢 Info | ✅ Verificado |
| **G** | Umbrales de concordancia vs datos | Coherentes (monotonicidad score→HR), pero validación circular (reusa la función) | 🟡 Media | ⚠️ Parcial |
| **H** | `floor_sgs=0.0` sospechoso | bsi con hr alto da sgs=0.0 → posible mal cómputo N bajo | 🟠 Alta | ⏳ Pendiente |

---

## DETALLE DE CADA HALLAZGO (evidencia, no conclusión)

### A. CAT mismatch `fg`
**Hecho:** `station_profiles['fg'].cat=2` (CAT2_SENTIMENT) pero `family_sequence.STATION_CATEGORIES['fg']=CAT3_ACTION`.
**Impacto verificado:** family usa SU PROPIO `STATION_CATEGORIES` (L381) → la secuencia trata a fg como acción (correcto). El `cat` de profiles solo sale como `station_cat` (rotulado) en el output del discriminator (L846). **No es bug de decisión — es inconsistencia de identidad/rotulado.**
**Decisión sugerida:** alinear `fg→cat=3` (su rol real: confirmador de bsi tras vix/pcr). Riesgo bajo.

### B. Inconsistencia de escala (sgs vs scale_gradient)
**Hecho:** dos definiciones coexisten:
- `sgs = (hr75-hr25)/hr25` (ratio) — timing_context.py L317
- `scale_gradient = hr75-hr25` (diferencia) — signal_discriminator.py L1298
**Medido:** 158/1101 estados (14.4%) cambian STRUCTURAL/TACTICAL/FLAT según cuál se use. bsi 23.4%, yield 18.2%.
**Riesgo:** el sistema se contradice — una parte dice STRUCTURAL, otra FLAT, para el mismo estado.

### C. `timing_mode=NOISE` artefacto de umbral per-slot
**Hecho:** `timing_mode` default NOISE (L344), solo cambia si UN slot individual tiene `n≥5` con edge>0.15 (L351-361).
**Medido:** de 77 intermedias (5-9) con pct_rango≥60%, **74 (96%) quedan NOISE** porque su N está repartido entre slots.
**Contradicción:** bsi `0__0__3` (HR75=100%, pct_rango=100%) = STRUCTURAL_FLOOR pero timing_mode=NOISE.
**Causa raíz:** el umbral per-slot n≥5 es demasiado estricto para señales intermedias; el `pct_en_rango` ya mide coherencia y se ignora para el modo.

### D. Señales intermedias (5-9) bien tratadas por concordancia
**Medido:** NOISE 8.4% (la banda MENOR), FLOOR 68.3%, TRAP 21.8%. Contra la hipótesis de que N bajo→ruido, las 5-9 son las MÁS "puras" (claro floor o claro trap, poco gris).

### E. Coherencia temporal (5-9)
**Medido:** pct_en_rango: 38% ≥60% (patrón), 36% <40% (disperso), 26% mixto. **El 38% con patrón es señal real sin interpretar** (filosofía rareza=riqueza), no ruido.

### F. Fallback NO_TIMING_DATA
**Medido:** 0 de 1189 estados sin `first_passage` en floor/ceiling. El fallback rules-JSON existe pero no se dispara en la práctica.

### G. Umbrales de concordancia (validados parcialmente)
**Medido:** monotonicidad score→HR75 coherente (0/7→75-80%, 7/7→6-22%). **PERO** la validación reusó `_compute_floor_concordance` (circular) — no es auditoría independiente. Pendiente validar con implementación independiente.

### H. `floor_sgs=0.0` sospechoso (PENDIENTE)
**Observación:** bsi `0__0__3` con hr75 y hr25 altos da `floor_sgs=0.0` → sugiere hr25=hr75 o mal cómputo con N bajo. **A VERIFICAR.**

---

## EJE DE DECISIÓN TRANSVERSAL (el criterio para todos)
**Coherencia temporal posicional** (definición CORREGIDA — 3 categorías, no 2): qué proporción de los episodios de una señal caen dentro de ±2 velas de un pivote zigzag (`pct_en_rango`), y qué proporción caen FUERA (ENTRE, lejos de giros).

⚠️ **"Fuera de rango" NO es sinónimo de ruido.** Una señal puede estar mayoRmente FUERA DE RANGO y ser legítima — señal de CONTINUACIÓN en la dirección (tendencia/persistencia) o de FUERZA de movimiento. La clasificación correcta es por la MAYORÍA relativa:

| Categoría | Criterio | Interpretación |
|:----------|:---------|:---------------|
| **EN RANGO (↓)** | mayoría dentro de ±2 velas de giros | Señal de GIRO (anticipa/exacta/confirma inversión) — canario, pivote, institucional |
| **FUERA DE RANGO (→)** | mayoría en ENTRE, lejos de giros | Señal de CONTINUACIÓN / FUERZA DE MOVIMIENTO (tendencia, régimen persistente) — señal real, NO ruido |
| **ERRÁTICA (ruido)** | NI dentro NI fuera — dispersa sin patrón dominante | **Ruido genuino** (si ni agrupa en giros ni agrupa en continuación) |

**Regla operativa:** el `timing_mode` NO debe etiquetar como NOISE una señal que muestra UNA mayoría clara — ni en giros (en rango) ni de continuación (fuera). Solo es ruido si es **errática** (no predomina ni dentro ni fuera). Clasificar por:
- En rango mayoro → patrón de giro (ANTICIPATION/EXACT/CONFIRMATION por slot modal)
- Fuera mayoro → CONTINUACIÓN (dirección/fuerza)
- Sin mayoría → NOISE

## PENDIENTES PARA INTEGRAR AL PROMPT (Frente A + refinamiento C)
- **Frente A** (integración del módulo): APIs 100% operativas (metar/sigmet/notam/taf); Q4 eliminado por decisión del arquitecto; Q2-parte Gates eliminado.
- **Coherencia corregida**: 3 categorías (en-rango=giro, fuera=continuación/fuerza, errática=ruido); "fuera de rango" ≠ ruido.