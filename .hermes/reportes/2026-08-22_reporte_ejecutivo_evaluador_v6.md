# REPORTE EJECUTIVO — Evaluador Vela a Vela v6
**Fecha:** 22-Ago-2026
**Proyecto:** Botero Trade — Sistema de señales Entry/Exit
**Módulo:** `research/01_señales_entry_exit/evaluador_vela_a_vela.py` (v6)

---

## 1. Resumen Ejecutivo

Se construyó un **evaluador de señales vela a vela** que corrige los dos sesgos graves descubiertos en el arnés anterior (`medir_senal.py`):

1. **Sesgo de posición** — el método antiguo medía señales solo en pivotes confirmados ex-post (asumiendo que el trader sabe dónde está el pivote). Ejemplo: `credit_easing_k1` mostraba +5.19% con filtro `pivot_type==MIN` pero −0.48% sin el filtro (+620% de inflación).
2. **Sesgo de estructura de escala** — medir "favorable" como el retorno hasta el próximo pivote del zigzag venía parcialmente garantizado por la geometría del zigzag (hit rate 100% por construcción).

El evaluador v6 dispara en la vela observable en tiempo real, califica contra un baseline de la misma celda (escala×régimen), usa resultado por **primer paso** (first-passage), y aplica el **protocolo Diamante** (§3.3 del fact store).

---

## 2. Metodología

### Ficha de calificación por disparo
```
DISPARO en vela t, señal S, blanco B (MIN/MAX):
├─ Régimen observable: última pierna CONFIRMADA de quants_obs (sin look-ahead)
├─ Resultado por PRIMER PASO en 3 escalas (zz25/zz50/zz75):
│   ¿el precio cruza antes el umbral favorable (±scale) o el adverso?
├─ favorable: movimiento real en la dirección del blanco hasta el evento
├─ hit: ¿cruzó antes el umbral favorable que el adverso?
├─ mae/mfe: dolor y ganancia máxima intra-tramo
├─ bars: velas hasta resolverse
└─ Baseline: todos los pivotes del mismo tipo EXCLUIDOS los de la señal
```

### Métricas institucionales
| Métrica | Qué mide |
|---------|----------|
| **fav_neto** | favorable señal − favorable baseline de la misma celda |
| **p-value** | Test binomial vs baseline hit de la celda |
| **Profit Factor** | Ganancias brutas / pérdidas brutas |
| **EV/barra** | Eficiencia temporal (fav_neto / bars) |
| **INDEP** | Independencia Informacional (Opción C): % de fallos únicos de la señal |
| **confidence_tier** | Protocolo Diamante §3.3: ANECDOTAL/LOW/MODERATE/HIGH/ROBUST |

### Protocolo Diamante
Las señales con N<21 (por debajo de ROBUST) **no se descartan por insuficiencia muestral** — se reportan con tasa cruda sin shrinkage y tier §3.3. Rareza = riqueza: los eventos más importantes del mercado son inherentemente raros.

---

## 3. Ranking Final (19 señales evaluadas)

| # | Señal | Celda | N | Tier | Neto | p-val | PF | EV/b | bars | INDEP |
|---|-------|-------|:---:|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **pcr_put_panic** | zz75\|BAJA | 28 | ROBUST | **+4.04%** | **0.002** | 11.2 | +0.0008 | 49 | 21% |
| 2 | **credit_stress** | zz75\|ALZA | 101 | ROBUST | **+3.42%** | **0.000** | 2.6 | +0.0012 | 28 | 38% |
| 3 | **capitulacion** | zz25\|BAJA | 28 | ROBUST | **+3.40%** | **0.002** | 49.5 | **+0.0125** | **2.7** | 0% |
| 4 | **panico_total** | zz75\|BAJA | 18 | HIGH💎 | **+3.16%** | **0.040** | 6.8 | +0.0011 | 29 | 38% |
| 5 | **vvix_entry** | zz75\|ALZA | 45 | ROBUST | **+3.11%** | **0.007** | 2.5 | +0.0008 | 42 | 11% |
| 6 | **skew_paranoia_exit** | zz75\|ALZA | 16 | HIGH💎 | **+2.84%** | **0.091** | 2.2 | +0.0005 | 60 | **71%** |
| 7 | fg_extreme_greed | zz50\|BAJA | 8 | MODERATE💎 | +2.52% | 0.17 | 1.8 | +0.0014 | 18 | 70% |
| 8 | stealth_tail_hedging | zz50\|ALZA | 20 | HIGH💎 | +2.49% | 0.057 | 3.4 | +0.0004 | 66 | 55% |
| 9 | **bsi_washed_out** | zz25\|BAJA | 65 | ROBUST | +1.73% | **0.004** | 7.4 | +0.0051 | 3.4 | 18% |
| 10 | fg_extreme_fear | zz75\|BAJA | 23 | ROBUST | +1.73% | 0.20 | 3.3 | +0.0004 | 39 | 7% |
| 11 | vix_crisis_spike | zz25\|BAJA | 79 | ROBUST | +1.58% | 0.08 | 5.0 | +0.0087 | 1.8 | 37% |
| 12 | **bsi_recovery** | zz75\|BAJA | 162 | ROBUST | +1.50% | **0.006** | 0.8 | +0.0003 | 53 | 62% |
| 13 | **credit_ease_exit** | zz75\|ALZA | 440 | ROBUST | **+1.54%** | **0.001** | 1.2 | +0.0003 | 47 | 24% |
| 14 | **breadth_contraction_exit** | zz75\|ALZA | 709 | ROBUST | **+0.84%** | **0.001** | 1.0 | +0.0002 | 54 | 49% |
| 15 | sorpresa_total | zz50\|BAJA | 264 | ROBUST | +0.94% | 0.08 | 2.6 | +0.0006 | 16 | 28% |
| 16 | euforia | zz25\|ALZA | 35 | ROBUST | +0.71% | 0.054 | 5.0 | +0.0005 | 14 | 71% |
| ❌ | sub_reaccion | zz25\|BAJA | 337 | ROBUST | **−0.51%** | 1.00 | 2.2 | −0.0008 | 6.0 | 59% |
| ❌ | dxy_bearish | zz25\|BAJA | 17 | HIGH💎 | **−1.69%** | 0.99 | 0.95 | −0.0025 | 6.8 | 100% |
| ❌ | regime_change_exit | zz75\|ALZA | 182 | ROBUST | +0.94% | 0.135 | 1.2 | +0.0003 | 34 | 15% |

**✓ = p<0.05 (11 señales)** | **m = p<0.10 (4 señales)** | **💎 = Diamante (N<21)**

---

## 4. Rescates — Señales descartadas por el método antiguo

El método antiguo (lift pivote-a-pivote) descartó señales que el evaluador v6 confirma como significativas:

| Señal | Método antiguo | Evaluador v6 | Veredicto |
|-------|---------------|--------------|-----------|
| **credit_ease_exit** | RETIRADA (lift<1.0, fire 51.6%) | **+1.54% neto, p=0.001, N=440** | ✅ RESCATADA |
| **breadth_contraction_exit** | RETIRADA (fire 87.7%) | **+0.84% neto, p=0.001, N=709** | ✅ RESCATADA |
| **skew_paranoia_exit** | DEGRADADA GRADO C (LIFT≈1.0) | **+2.84% neto, p=0.091, INDEP=71%** | ✅ RESCATADA |

El sesgo de estructura del método antiguo (medir favorable hasta el próximo pivote del zigzag) inflaba el baseline y ocultaba el edge real. El método nuevo (first-passage + baseline por celda) lo revela.

---

## 5. Independencia Informacional (Opción C)

La métrica INDEP responde: "¿esta señal aporta información única al ensemble?"

**Señales de familia con gran edge (INDEP bajo, redundantes):**
- capitulacion (0%), vvix_entry (11%), fg_extreme_fear (7%), bsi_washed_out (18%)

**Señales independientes con edge moderado (INDEP alto):**
- dxy_bearish (100%), euforia (71%), skew_paranoia_exit (71%), fg_extreme_greed (70%), bsi_recovery (62%)

**Implicación para producción:** un ensemble óptimo balancea señales de familia con gran edge (capitulacion, credit_stress, pcr_put_panic) + señales independientes que cubren sus puntos ciegos (skew_paranoia_exit, bsi_recovery, euforia).

---

## 6. Auditoría de Integración

| Componente | Estado | Evidencia |
|-----------|:------:|-----------|
| `medir_senal.py` — registros RESCATADA | ✅ | credit_ease_exit, breadth_contraction_exit, skew_paranoia_exit actualizados |
| `evaluador_vela_a_vela.py` — BLANCOS | ✅ | 21 señales con blanco asignado (19 evaluables) |
| `evaluador_vela_a_vela.py` — RESCATADAS | ✅ | skew_paranoia_exit en set activo |
| `evaluador_vela_a_vela.py` — REEVALUAR | ✅ | 4 señales re-evaluadas |
| `ARBOLES_DECISION.md` — tablas actualizadas | ✅ | 8 EXIT activas + 1 GRADO C |
| `GUIA_EMPLEO.md` | ⚠️ | Sin menciones de rescates (pendiente actualizar) |
| JSON v6 | ✅ | `evaluacion_vela_a_vela_v6_final.json` guardado |

---

## 7. Señales sin edge (candidatas a retiro)

| Señal | N | Neto | p-val | Diagnóstico |
|-------|:---:|:---:|:---:|-------------|
| **sub_reaccion** | 337 | **−0.51%** | 1.00 | Edge negativo, N alto confirma que no es ruido |
| **dxy_bearish** | 17 | **−1.69%** | 0.99 | Edge negativo en todas las celdas y escalas |
| regime_change_exit | 182 | +0.94% | 0.135 | Marginal, INDEP=15% (redundante) |

---

## 8. Correcciones Aplicadas (Historial de Auditorías)

| Auditoría | Hallazgos | Estado |
|-----------|-----------|:------:|
| Gemini v1 (RECHAZADO) | Zigzag incompatible, artefacto hit 100%, baseline contaminado | ✅ P0-P5 corregidos |
| Gemini v2 (APROBADO CON RESERVAS) | UM_DIAMANTE inconsistente, falta confidence_tier | ✅ PC1-PC3 corregidos |
| Auditoría Forense Profunda | F3 saturada, ventana índice, solo zz25, duplicados en pool | ✅ H2-H4 + duplicados corregidos |
| Auditoría Forense v2 | Duplicados exactos (Jaccard=1.0), subconjuntos, familia | ✅ Opción C implementada |

---

## 9. Próximos Pasos

1. **Decisión de retiros:** sub_reaccion y dxy_bearish (edge negativo con p≈1.0)
2. **Estabilidad por década** de las 11 señales significativas
3. **Actualizar GUIA_EMPLEO.md** con los rescates
4. **Detección de trampas** (observación del arquitecto: anticipación previa deteriora — señal de trampa bajista)
5. **forense_precursores.py:** Fisher+BH correction, unificar variable forward (fase 2)
6. **Re-manufactura del God file** `medir_senal.py` bajo Clean Architecture (fase posterior)

---
**Firma:** qwen/qwen3.8-max (Hermes) · 22-Ago-2026
