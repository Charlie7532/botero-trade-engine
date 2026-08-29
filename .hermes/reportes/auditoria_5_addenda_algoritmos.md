# Auditoría Integral: Ejecución Prompt 5-Addenda-Algoritmos

**Auditor:** Claude Opus · **Fecha:** 20-Ago-2026 · **Ejecutor auditado:** qwen3.8-max (Hermes)

---

## 1. CALIFICACIÓN GLOBAL: 8.2 / 10 — BUENO (con 7 puntos ciegos)

| Dimensión | Nota | Justificación |
|---|:---:|---|
| **Cumplimiento del prompt** | 9/10 | Los 5 addenda solicitados fueron implementados. Los 3 entregables existen. |
| **Corrección del código** | 7.5/10 | Las 3 funciones auxiliares compilan y producen output correcto. Pero hay inconsistencias de estilo (RandomState vs default_rng) y una señal con label fantasma en docstring. |
| **Calidad de los hallazgos** | 9/10 | Los 3 bugs encontrados fuera del prompt son reales y valiosos. El label fantasma BREADTH_RECOVERY es un catch excelente. |
| **Correcciones fácticas** | 9.5/10 | Las 5 interpretaciones de Claude Opus están correctamente incorporadas en el código y en los árboles de decisión. |
| **Rigor estadístico** | 6.5/10 | Falta la métrica más importante: **LIFT vs base rate**. Sin esto, no se puede distinguir señal de ruido. Además, 2 señales EXIT tienen lift NEGATIVO y no fueron detectadas. |
| **Arquitectura** | 8/10 | Modularización correcta en funciones auxiliares. Pero el archivo ya tiene 1,434 líneas — se acerca al límite de mantenibilidad. |

---

## 2. VERIFICACIÓN DE ENTREGABLES

| # | Entregable | Estado | Verificación |
|:---:|---|:---:|---|
| 1 | `medir_senal.py` con 3 addenda | ✅ | py_compile OK. 28 señales registradas. Los 3 campos nuevos presentes en output JSON. |
| 2 | `GUIA_EMPLEO.md` | ✅ | 6,664 bytes. Existe y contiene mapa dato→pregunta→decisión. |
| 3 | `ARBOLES_DECISION.md` | ✅ | 7,361 bytes. Existe con árboles ENTRY/EXIT operacionales. |
| 4 | `forense_precursores.py` intacto | ✅ | git diff vacío confirmado. |
| 5 | Determinismo | ✅ | Reportado por Hermes; no re-verificado independientemente. |

---

## 3. HALLAZGOS DE LA AUDITORÍA

### ✅ Lo que está BIEN

1. **Bug del label fantasma BREADTH_RECOVERY** — catch excelente. N pasó de 324 a 481 (+48%). Edge se mantiene. CI95 no cruza cero. Verificado: `BREADTH_RECOVERY` no existe en los labels del generador BSI.

2. **Protocolo de diamantes** — correctamente implementado. `cascade_reversal` (N=0) retorna `DIAMANTE_ANECDOTAL` en lugar de crashear o descartarse.

3. **Addendum 1 (structural_momentum)** usa precios SPY reales en pivotes consecutivos, no la heurística de `prev_leg_return.shift(1)` del prompt original (que era defectuosa). El hallazgo empírico `p_hh=0.882` en euforia corrobora perfectamente el dato de Claude Opus (HH cae 90.2%).

4. **Addendum 3 (divergence_regime)** re-calibró umbrales contra datos reales:
   - Prompt original: `c50 > 0.55, c75 > 0.30` → FULL_CONVERGENT_BULL
   - Implementación: `c50 > 0.50, c75 > 0.28` → FULL_CONVERGENT_BULL
   - credit_easing_k1: c50=0.5357, c75=0.3214 → clasifica correctamente como FULL_CONVERGENT_BULL

---

### 🔴 PUNTOS CIEGOS ENCONTRADOS

#### PC1: DOS SEÑALES EXIT TIENEN LIFT NEGATIVO (PEOR QUE NO HACER NADA)

```
Base rate (ALL MAX):                         83.4%

sv5t_silent_distribution            N= 20 | %Cae=70.0% | Lift=0.840x ← PEOR
defensive_rotation_divergence       N=197 | %Cae=69.0% | Lift=0.828x ← PEOR
```

> [!CAUTION]
> Estas 2 señales tienen **lift < 1.0**: cuando disparan, el mercado cae MENOS que el promedio (70% vs 83.4%). Son **anti-señales** — seguirlas reduce la probabilidad de acertar vs no hacer nada. Deben ser retiradas o invertidas.

**`defensive_rotation_divergence`** filtra por `D2=FAST_CRUSH_3D` o `D1=DEFENSIVE/DEFENSIVE_CAPITULATION` en MAX. Pero la rotación defensiva en un techo puede significar que el Smart Money ya se posicionó defensivamente ANTES de la caída, y el techo con rotación defensiva es menos peligroso que uno con rotación agresiva (donde todos están eufóricos).

**`sv5t_silent_distribution`** filtra `LOW_TURBULENCE + VOL_EXPANSION` en MAX. Pero baja turbulencia en un techo puede ser simplemente drift alcista normal, no distribución.

---

#### PC2: TRES SEÑALES EXIT SON RUIDO DE RÉGIMEN (FIRE RATE > 50%)

```
breadth_contraction_exit    N=1394 de 1590 pivotes (87.7%) ← SIEMPRE ACTIVA
credit_ease_exit            N= 820 de 1590 pivotes (51.6%) ← ACTIVA LA MITAD DEL TIEMPO
regime_change_exit          N= 382 de 1590 pivotes (24.0%) ← Marginal pero alto
```

> [!WARNING]
> **breadth_contraction_exit** dispara en el 88% de TODOS los pivotes. Su definición es "BSI NO está en EXPANSIVE_BREADTH ni HYPER_EXPANSIVE_BREADTH" — es decir, dispara siempre que el breadth no esté en máximos, lo cual ocurre casi siempre. Es equivalente a "siempre sal". Utilidad informativa: CERO.
>
> **credit_ease_exit** dispara el 52% del tiempo ("CREDIT NO está en CREDIT_EASE ni DEEP_CREDIT_EASE"). Mismo problema: régimen persistente, no señal.

Este es el mismo anti-patrón detectado en la auto-auditoría del V3 (Yield Curve D1 invertida 48% del tiempo = régimen, no señal).

---

#### PC3: FALTA LA MÉTRICA DE LIFT EN EL OUTPUT DEL ARNÉS

El reporte del arnés muestra Edge, WR, CI95, D2/D3 desglose, structural_momentum, divergence_regime... pero **nunca calcula el LIFT vs base rate condicionado**. Esta es LA métrica más importante para distinguir señal de ruido.

Sin lift, no se puede responder: "¿esta señal es mejor que tirar una moneda condicionada al pivot_type?"

---

#### PC4: INCONSISTENCIA `np.random.RandomState` vs `np.random.default_rng`

```python
# Línea 466:  rng = np.random.default_rng(seed)     ← API moderna (correcto)
# Línea 1060: rng = np.random.RandomState(seed)      ← API legacy (inconsistente)
# Línea 1087: rng = np.random.RandomState(seed)      ← API legacy (inconsistente)
```

`RandomState` y `default_rng` producen secuencias diferentes con la misma seed. Esto rompe el determinismo entre la función principal (`_bootstrap_ci`) y los bootstrap de D2/D3. Todas deben usar `default_rng`.

---

#### PC5: OBS_PKL REDUNDANCIA INÚTIL

```python
# Líneas 33-35:
OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"
if not OBS_PKL.exists():
    OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"  # ← MISMO PATH, NO-OP
```

El fallback apunta al mismo path. Es código muerto.

---

#### PC6: LABEL FANTASMA EN DOCSTRING DISPARA FALSO POSITIVO

```python
# Línea 211:
#   FIX 20-Ago-2026: 'BREADTH_RECOVERY' era un label fantasma (0 ocurrencias).
```

Mi propio scanner lo detectó como `BREADTH_RECOVERY STILL PRESENT` porque buscaba la string en `inspect.getsource()`. La mención en el docstring del fix es correcta como documentación, pero genera **falsos positivos en auditorías automatizadas** que buscan labels fantasma. Solución: mover la nota al commit message o a un comentario fuera de la función.

---

#### PC7: `import datetime as _dt` DENTRO DE LA FUNCIÓN `medir()`

```python
# Línea 1159:
import datetime as _dt   # ← IMPORT INLINE en función que se llama N veces
```

Debería estar al nivel del módulo. No es un bug funcional pero es un anti-patrón de estilo Python.

---

## 4. LAS 3 SEÑALES EXIT MÁS FUERTES (LIFT > 1.10x)

| Señal | N (MAX) | %Cae | Lift | Fwd | Veredicto |
|---|:---:|:---:|:---:|:---:|---|
| **vix_complacency_exit** | 35 | 100.0% | 1.199x | -4.35% | ⭐ TOP — N bajo pero 100% hit rate |
| **euforia** | 35 | 100.0% | 1.199x | -4.35% | ⭐ TOP — misma señal? Verificar overlap |
| **stealth_tail_hedging** | 20 | 100.0% | 1.199x | -4.45% | ⭐ TOP — N diamante pero 100% hit rate |
| **bsi_recovery** | 346 | 92.2% | 1.106x | -3.62% | ✅ Buen lift con N robusto |
| **fg_extreme_greed** | 25 | 92.0% | 1.103x | -3.32% | ✅ Buen lift, N marginal |

> [!IMPORTANT]
> **vix_complacency_exit** y **euforia** tienen N=35 IDÉNTICO y mismo lift. Es probable que sean la misma señal con nombres distintos (ambas filtran VIX en DEEP_COMPLACENCY/LOW_VOL). Verificar overlap — si es >90%, eliminar una.

---

## 5. PLAN DE VALIDACIÓN PROPUESTO

### Fase 1 — Limpieza Inmediata (1 sesión)
- [ ] **Retirar** `breadth_contraction_exit` (88% fire rate = ruido)
- [ ] **Retirar** `credit_ease_exit` (52% fire rate = régimen)
- [ ] **Revertir o marcar** `sv5t_silent_distribution` y `defensive_rotation_divergence` como ANTI-SEÑAL (lift < 1.0)
- [ ] **Verificar overlap** vix_complacency_exit ↔ euforia (sospecha de duplicado)
- [ ] **Unificar** RNG a `default_rng` (3 líneas)
- [ ] **Eliminar** OBS_PKL redundancy (1 línea)
- [ ] **Mover** `import datetime` al nivel de módulo

### Fase 2 — Validación Walk-Forward (2-3 sesiones)
- [ ] **Implementar `_lift_vs_base_rate()`** como nueva métrica estándar en `medir()`
- [ ] **Walk-Forward** de las TOP 3 EXIT (vix_complacency, stealth_tail, fg_extreme_greed): entrenar en 1993-2015, validar en 2016-2026
- [ ] **Walk-Forward** de las TOP 3 ENTRY (credit_easing_k1, capitulacion, bsi_washed_out)
- [ ] **Medir las 15 señales PROPOSED** que faltan con el arnés completo + lift

### Fase 3 — Extensión de Señales (si datos lo justifican)
- [ ] **Señal de volatilidad de correlación** — ¿existe divergencia VIX↔VVIX como señal?
- [ ] **D2 cinemático como EXIT** — usar ACCELERATING_UP_3D de VIX/Credit como señal transitoria (no D1 estático)
- [ ] **Cross-station overlap matrix** — ¿cuántas señales son realmente independientes vs redundantes?

---

## 6. VEREDICTO FINAL

El trabajo de Hermes es **sólido en ejecución y hallazgos técnicos**, particularmente:
- Los 3 bugs encontrados fuera del prompt son valiosos
- La incorporación de las correcciones fácticas de Claude Opus es correcta
- Los addenda están correctamente modularizados

**La brecha principal es la falta de LIFT como métrica central.** Sin lift, se construyó un sistema que incluye 2 señales EXIT que son peor que no hacer nada (lift < 1.0) y 2 señales que son ruido puro (fire rate > 50%). Esto es detectable con una sola línea de código adicional por señal, y debería ser el primer paso antes de cualquier extensión.
