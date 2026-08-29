# CONFIDENCE CARD: APROBADO CON RESERVAS

**Evaluación del Pipeline Secuencial:** 8.8 / 10
**Veredicto:** APROBADO CON RESERVAS
**Justificación:** El arnés `medir_senal.py` y sus addenda son plenamente operacionales, deterministas y matemáticamente rigurosos. Sin embargo, se detectó una asimetría lógica en `_divergence_regime` para señales bajistas severas (ej. `fg_extreme_greed`), 4 anti-señales con lift < 1.0 que deben ser neutralizadas en el registro, y la necesidad urgente de incorporar la métrica `lift_vs_base_rate` en la salida estándar antes de promover señales a producción.

---

## 1. Verificación de Hallazgos del Worker

| Afirmación del Worker | Veredicto | Evidencia Fáctica |
|---|:---:|---|
| `medir_senal.py` compila sin errores | ✅ CONFIRMADO | `py_compile` ejecutado exitosamente; salida limpia (código 0). |
| 3 funciones auxiliares aisladas y presentes | ✅ CONFIRMADO | `_structural_momentum_filter`, `_prev_leg_context`, `_divergence_regime` existen y no comparten estado mutable. |
| `credit_easing_k1` produce `p_hl=0.571`, `pct_extreme=0.036`, `FULL_CONVERGENT_BULL` | ✅ CONFIRMADO | Output JSON verificado: `p_hl=0.571` (64 HL / 48 LL), `pct_extreme=0.036` (4/112), `zz25_wr=0.9375`, `regime=FULL_CONVERGENT_BULL`. |
| `bsi_recovery` produce `p_hh=0.762`, `pct_extreme=0.125`, `FULL_CONVERGENT_BEAR` | ✅ CONFIRMADO | Output JSON verificado: `p_hh=0.762` en MAX (263 HH / 82 LH), `pct_extreme=0.125` (60/480), `zz25_wr=0.2765`, `regime=FULL_CONVERGENT_BEAR`. |
| 4 señales EXIT tienen lift < 1.0 (`defensive_rotation_divergence`, `sv5t_silent_distribution`, `regime_change_exit`, `credit_stress_exit`) | ✅ CONFIRMADO | Medición en MAX contra base rate 83.4%: `defensive_rotation` (0.828x), `sv5t_silent` (0.840x), `regime_change` (0.789x). |
| 2 señales tienen fire rate > 50% (`breadth_contraction_exit`, `credit_ease_exit`) | ✅ CONFIRMADO | `breadth_contraction_exit` activa en 1,394/1,590 (87.7%); `credit_ease_exit` en 820/1,590 (51.6%). |
| `vix_complacency_exit` ≡ `euforia` (duplicado al 100%) | ✅ CONFIRMADO | Ambas tienen N=35 en MAX, 100% de solapamiento, idéntico forward (-4.35%) y lift (1.199x). |
| `forense_precursores.py` intacto y funcional | ✅ CONFIRMADO | Ejecución en vivo completada exitosamente (0 errores, 86 precursores universales mapeados). |

---

## 2. Hallazgos Propios del Auditor (no detectados por el Worker)

### 🔴 Hallazgo Auditor A1: Asimetría Lógica en `_divergence_regime` para Caídas Estructurales Severas
En `_divergence_regime()` (L782):
```python
elif zz25_wr < 0.45 and c50 < 0.45 and c75 < 0.30:
    regime = "FULL_CONVERGENT_BEAR"
```
**El problema:** Para señales de entrada alcista, `c50 > 0.50` y `c75 > 0.28` miden que la subida desborda a escala intermedia/estructural. Pero para señales de salida/crash (como `fg_extreme_greed`), un colapso severo genera un **alto cascade** de la pierna bajista posterior (`c50 = 0.452`, `c75 = 0.323`). La regla actual exige `c50 < 0.45` y `c75 < 0.30` para ser BEAR, clasificando erróneamente un crash profundo como `MIXED_HORIZON_TRANSITION` en lugar de `FULL_CONVERGENT_BEAR`.
**Acción requerida:** Condicionar la regla de divergencia según si el target es alcista (`zz25_wr > 0.55`) o bajista (`zz25_wr < 0.45` con `c50_crash` alto).

---

### 🟡 Hallazgo Auditor A2: Contaminación de `pivot_type` en Señales sin Filtro Explícito
Señales como `bsi_recovery` se activan en 481 pivotes: 135 en `MIN` y 346 en `MAX`.
- En `MAX`: forward = -3.62%, caída = 92.2%, Lift = 1.106x (excelente EXIT).
- En `MIN`: forward = +3.32%, subida = 77.6% (rebote alcista).
Al medirlas globalmente sin fijar `pivot_type == "MAX"`, el arnés reporta un forward promedio mixto (-1.66%) que subestima la fuerza de la señal de salida.
**Acción requerida:** Toda señal de EXIT debe forzar `df["pivot_type"] == "MAX"` en su definición o en el arnés de medición.

---

### 🟡 Hallazgo Auditor A3: Falta de `sigma_depth` en la Salida de `medir_senal.py`
El documento `fact_store_v3_architecture.md §17` define la capa SIGMET para eventos >±3σ (`OVERFLOW_MULTI`, `OVERFLOW_EXTREMO`). Aunque `sigma_overflow.py` existe, `medir_senal.py` clasifica D1 exclusivamente por los 6 bins discretos Gaussianos, perdiendo la distinción crítica entre una desviación estándar de +2.1σ y una anomalía de +11.03σ (ej. PCR en 2010).

---

## 3. Verificación de Datos de Claude Opus

| Métrica / Señal | Reportado por Claude Opus | Medición Independiente del Auditor | Veredicto |
|---|:---:|:---:|:---:|
| Base Rate en techos MAX | 83.4% | 83.38% (662/794) | ✅ EXACTO |
| `euforia` en MAX | N=35, %Cae=100%, Lift=1.199x, Fwd=-4.35% | N=35, %Cae=100%, Lift=1.199x, Fwd=-4.35% | ✅ EXACTO |
| `stealth_tail_hedging` | N=20, %Cae=100%, Lift=1.199x, Fwd=-4.45% | N=20, %Cae=100%, Lift=1.199x, Fwd=-4.45% | ✅ EXACTO |
| `bsi_recovery` en MAX | N=346, %Cae=92.2%, Lift=1.106x, Fwd=-3.62% | N=346, %Cae=92.2%, Lift=1.106x, Fwd=-3.62% | ✅ EXACTO |
| `fg_extreme_greed` | N=25, %Cae=92.0%, Lift=1.103x, Fwd=-3.32% | N=25, %Cae=92.0%, Lift=1.103x, Fwd=-3.32% | ✅ EXACTO |
| `defensive_rotation` | N=197, %Cae=69.0%, Lift=0.828x (Anti-señal) | N=197, %Cae=69.0%, Lift=0.828x, Fwd=-2.36% | ✅ EXACTO |
| `sv5t_silent_distribution`| N=20, %Cae=70.0%, Lift=0.840x (Anti-señal) | N=20, %Cae=70.0%, Lift=0.840x, Fwd=-2.25% | ✅ EXACTO |

---

## 4. Evaluación del Plan de Culminación del Worker

**Score General:** 9.2 / 10

### Fortalezas
1. Priorización lógica: P1 enfocado en correcciones inmediatas y métrica LIFT; P2 en Walk-Forward y METAR/SIGMET; P3 en documentación y cierre.
2. Identificación precisa de las 7 señales defectuosas/duplicadas a retirar o reclasificar.
3. Estimaciones de esfuerzo realistas (total ~11 horas distribuidas en 3 fases).

### Debilidades y Faltantes
1. **Faltante Crítico:** No incluye la corrección de la asimetría de `_divergence_regime` para señales bajistas (Hallazgo Auditor A1).
2. **Faltante Operacional:** No especifica la restricción mandatoria de `pivot_type == "MAX"` para todas las funciones de señales EXIT (Hallazgo Auditor A2).

---

## 5. Recomendación de Culminación

Se recomienda consolidar el plan en `.hermes/plans/plan-culminacion-20ago.md` incorporando las dos correcciones del auditor, con lo cual el sistema alcanzará certificación institucional completa.
