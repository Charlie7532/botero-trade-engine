# AUDITORÍA — Etapa Evaluador v6 + Régimen de Crisis + Semivida + Refactor

**Auditor:** Claude Opus
**Solicitante:** Juan Andrés (Arquitecto) vía Hermes (qwen/qwen3.8-max)
**Fecha:** 22-Ago-2026
**Objetivo:** Auditar el trabajo de la etapa antes del siguiente paso. El evaluador v6 ya pasó 4 rondas de auditoría Gemini; esta auditoría es independiente y debe buscar lo que Gemini no vio. Los demás componentes son NUEVOS y no han sido auditados nunca.

---

## 0. REGLAS DE LA CASA (obligatorias)

1. **Dato mata relato.** Verifica cada afirmación corriendo el código o consultando los JSONs citados. No aceptes el reporte por fe.
2. **Lenguaje probabilístico.** Toda conclusión con N, CI95 o p-value. Prohibido lenguaje absoluto ("siempre", "garantiza").
3. **Protocolo Diamante (§3.3 fact store):** N bajo ≠ descartable. Tiers: ANECDOTAL(1-2), LOW(3-5), MODERATE(6-10), HIGH(11-20), ROBUST(21+). Diamante = N<21, se reporta tasa cruda sin shrinkage agresivo.
4. **Taxonomía de sesgos a aplicar** (cada componente, en orden):
   - Sesgo de posición (saber ex-post el pivote; el pivote se confirma 2-150 barras después)
   - Sesgo de estructura de escala (el zigzag garantiza el movimiento de su umbral)
   - Contaminación del baseline (¿incluye los pivotes de la propia señal?)
   - Look-ahead (¿la decisión usa información del futuro?)
   - Multiplicidad (miles de tests sin corrección → falsos positivos)
   - Filtro de pivot_type embebido (sesgo de posición por definición)
5. **Ambiente:** `/root/botero-trade`, intérprete `backend/.venv/bin/python`, `PYTHONPATH=/root/botero-trade`. Los scripts corren (verificado). Los datos están en `data/research/`.

---

## 1. CONTEXTO DE LA ETAPA

Cuatro componentes producidos el 22-Ago-2026:

| # | Componente | Estado de auditoría |
|---|-----------|---------------------|
| A | Evaluador vela a vela v6 (ranking final de señales) | 4 rondas Gemini previas; re-verificación independiente |
| B | Detector de régimen de crisis (máquina de estados ±3σ) | **NUNCA auditado** |
| C | Semivida de absorción VIX / hipótesis de amortiguamiento | **NUNCA auditado** |
| D | Refactor del God file `medir_senal.py` (1,497 líneas → paquete `arnes/`) | **NUNCA auditado** |

Archivos:
- `research/01_señales_entry_exit/evaluador_vela_a_vela.py` (441 líneas) + `data/research/signals/evaluacion_vela_a_vela_v6_final.json`
- `research/01_señales_entry_exit/detector_regimen_crisis.py` (~440 líneas) + `data/research/signals/regimen_crisis_diamantes.json`
- `scratch/amortiguacion_vix.py`, `scratch/senal_d3_semivida.py`, `scratch/structural_break_gfc.py`
- `research/01_señales_entry_exit/arnes/` (8 módulos) + fachada `medir_senal.py` (60 líneas) + backup `_deprecated/medir_senal_godfile_1497L_backup.py`
- Reporte: `docs/research/00_cross_cutting/regimen_crisis_semivida_d3_REPORT.md`

---

## 2. COMPONENTE A — EVALUADOR VELA A VELA v6

### Lo que hace
Para cada señal evaluable (sin filtro `pivot_type`, sin RETIRADA/DEGRADADA, fire rate ≤20%): dispara en la fecha del pivote de quants_obs, mide **first-passage bilateral** por 3 escalas (zz25/zz50/zz75 = umbral 2.5%/5%/7.5%): ¿el precio cruza antes el umbral favorable o el adverso? Baseline = todos los pivotes del mismo tipo en la misma celda (escala×régimen) EXCLUÍDOS los de la señal. Métricas: favorable neto, hit rate vs baseline hit (p binomial unilateral), PF, EV/barra, INDEP (independencia informacional: % de fallos no vistos por ninguna hermana en ±5 días calendario), confidence_tier.

### Ranking v6 (15 señales, mejor celda por señal)
| Señal | Celda | N | Neto | p-val | INDEP |
|-------|-------|:---:|:---:|:---:|:---:|
| pcr_put_panic | zz75\|BAJA | 28 | +4.04% | 0.0015 | 21% |
| credit_stress | zz75\|ALZA | 101 | +3.42% | 0.0000 | 38% |
| capitulacion | zz25\|BAJA | 28 | +3.40% | 0.0020 | 0% |
| panico_total | zz75\|BAJA | 18 | +3.16% | 0.0402 | 38% |
| vvix_entry | zz75\|ALZA | 45 | +3.11% | 0.0070 | 11% |
| skew_paranoia_exit 💎RESCATADA | zz75\|ALZA | 16 | +2.84% | 0.0905 | 71% |
| fg_extreme_greed | zz50\|BAJA | 8 | +2.52% | 0.1737 | 70% |
| stealth_tail_hedging | zz50\|ALZA | 20 | +2.49% | 0.0572 | 55% |
| bsi_washed_out | zz25\|BAJA | 65 | +1.73% | 0.0040 | 18% |
| bsi_recovery | zz75\|BAJA | 162 | +1.50% | 0.0058 | 62% |
| credit_ease_exit 🆕RESCATADA | zz75\|ALZA | 440 | +1.54% | 0.0013 | 24% |
| breadth_contraction_exit 🆕RESCATADA | zz75\|ALZA | 709 | +0.84% | 0.0008 | 49% |
| sub_reaccion ❌ | zz25\|BAJA | 337 | −0.51% | 0.9996 | 59% |
| dxy_bearish ❌ | zz25\|BAJA | 17 | −1.69% | 0.9869 | 100% |

### Test de structural break (quiebre 2009-03-09, baseline separado por período, Fisher)
- credit_ease_exit: +6.99% PRE → **−2.84% POST (p=0.0000)** → **re-retirada como reliquia de era** (había sido rescatada antes del test)
- credit_stress: −4.45% PRE → +5.28% POST (nació con la era QE)
- breadth_contraction_exit: −0.28% PRE → +1.15% POST (mejora)
- bsi_recovery: hit 15% en 2020s en su mejor celda (p agregado 0.006 arrastrado por 2000-2010)

### Decisiones tomadas
- 3 rescates (skew_paranoia_exit por decisión del arquitecto con INDEP=71%; credit_ease_exit y breadth_contraction_exit por p<0.001), luego credit_ease_exit re-retirada por el break test.
- sub_reaccion y dxy_bearish candidatas a retiro (edge negativo).

### Preguntas para Opus (componente A)
1. El disparo ocurre en `pivot_date` de quants_obs (la fecha del pivote, NO la de confirmación). El trader no sabe ese día que es pivote — solo conoce el estado D1/D2/D3. ¿Es el diseño correcto o reintroduce sesgo de posición? (Nota: el régimen usa solo pivotes CONFIRMADOS, y el baseline es de la misma celda.)
2. ¿El first-passage bilateral elimina de raíz el artefacto de alternancia (hit=100% por geometría)? ¿Hay caso borde donde el precio cruce ambos umbrales en la misma barra?
3. El p binomial usa como probabilidad nula el hit rate del baseline de la misma celda. ¿Es válido ese nulo con N_eff bajo (disparos en la misma pierna no independientes)? ¿Qué corrección propondrías?
4. INDEP: fallo único = ninguna hermana (fire rate ≤20%, sin duplicados) disparó en ±5 días calendario. ¿El umbral de 20% y la ventana de 5 días son defendibles o arbitrarios?
5. Rescate de skew_paranoia_exit con p=0.0905 y N=16: el arquitecto lo decidió por INDEP=71%. ¿Es razonable como criterio de rescate o debería exigirse significancia?

---

## 3. COMPONENTE B — DETECTOR DE RÉGIMEN DE CRISIS (NUEVO, sin auditar)

### Lo que hace
Detecta overflows ±3σ con la función OFICIAL de la capa SIGMET (`backend/modules/entry_decision/domain/rules/sigma_overflow.py::validate_overflow`, parámetros μ/σ fijos por estación×dimensión) sobre las filas de quants_obs (fechas de pivote, NO barras diarias). Taxonomía SIGMET: OVERFLOW_MULTI (≥2 dims el mismo día), EXTREMO (>4σ), MODERADO. Analiza contención: un overflow está contenido si alguna señal activa dispara en los +5 días. Construye una máquina de estados del régimen de crisis.

### Resultados
- 952 overflows (512 MULTI, 359 MODERADO, 81 EXTREMO; 724 UPPER / 228 LOWER)
- Contención por dimensión: D1 97%, D2 83%, **D3 53%** → 198 overflows (21%) no contenidos, 56% de ellos D3 → "punto ciego D3"
- Máquina de estados: 79 episodios, duración media 26d / mediana 13d / P95 74d, 16.9% del tiempo en crisis. Validación: 8/8 crisis históricas detectadas (LTCM, dot-com, GFC, flash 2014, volmageddon, pandemia, yen carry, aranceles 2025).

### Código de la máquina de estados (auditar línea por línea)
```python
ESTACIONES_REVERSIVAS = ["vix", "vvix", "skew", "credit"]
# deterioro_dias = mediana medida por estación (vix 9, vvix 8, skew 13, credit 42)
# INICIO: overflow ±3σ en estación reversiva arranca episodio
# Un overflow dentro de [fin_actual + deterioro_max] se integra al episodio activo
# Un overflow después → cierra el episodio (deterioro) y arranca uno nuevo
# fin_real = fin + deterioro_max de las estaciones activas
```

### Compromisos conocidos (declarados, auditar si son aceptables)
1. **Granularidad de pivote, no diaria:** los overflows se detectan solo en las 1,590 fechas de pivote, no en las 8,448 barras diarias. Un overflow que ocurre entre pivotes es invisible. El equipo lo sabe y lo marca como pendiente.
2. **`deterioro_dias` son medianas fijas** (9/8/13/42): medidas empíricamente, pero fijas al fin — el arquitecto había ordenado "no suponer, medir". ¿Es un compromiso aceptable mientras no haya serie diaria en quants_obs, o hay mejor alternativa con los datos actuales?
3. **Estaciones de nivel excluidas** (yield_curve, dxy no revierten: 7,000+ días fuera de escala): tratadas como quiebre de era, no como crisis.

### Preguntas para Opus (componente B)
1. ¿La máquina de estados tiene look-ahead? (El `fin_previsto` usa deterioro_dias conocido: ¿eso contamina la detección en tiempo real?)
2. La contención (+5 días) mide "la señal disparó después del overflow". Pero las señales de la familia pánico disparan EN los mismos pivotes del overflow. ¿La contención es información genuina o identidad tautológica (vix|d1|UPPER ↔ vix_crisis_spike es el mismo evento)?
3. El "punto ciego D3" (53% de contención vs 97% de D1): ¿es un hallazgo real o un artefacto de que las señales se definieron históricamente sobre D1/D2?
4. La validación "8/8 crisis detectadas" usa crisis elegidas a posteriori. ¿Qué prueba propondrías contra el overfitting narrativo?
5. μ/σ fijos por estación (STATION_MU_SIGMA): si el régimen de una estación cambia (yield_curve lo hizo), los z-scores quedan descalibrados. ¿Cómo auditar la vigencia de esos parámetros?

---

## 4. COMPONENTE C — SEMIVIDA DE ABSORCIÓN VIX (NUEVO, sin auditar)

### Lo que se midió
13 episodios de crisis del VIX (z cruza +3σ → decae bajo +2σ) sobre la serie diaria (1990-2026, Timescale). Ajuste exponencial post-pico (modelo OU, primer orden): `ln(VIX−μ) = ln(x0−μ) − κt`, semivida = ln2/κ.

### Resultados
- Semivida mediana **8.2 días** (P25=6.0, P75=11.4); GFC 112d, pandemia 15.7d → bimodal
- Hipótesis ζ (segundo orden amortiguado) **rechazada**: ACF1 de residuos positiva (GFC +0.83), 0 cruces del nivel de reposo, overshoot bajo reposo 0/11 episodios
- Auditoría del ajuste: sensibilidad 34% al mover +2 barras el inicio; GFC y 2020 mejoran con 2 fases (BIC)
- Hipótesis D3→absorción: dirección esperada (29 vs 9 barras) pero Fisher p=0.79, Spearman rho=−0.02 → **abierta, N insuficiente** (diamante LOW-MODERATE)

### Preguntas para Opus (componente C)
1. El ajuste usa μ/σ de STATION_MU_SIGMA como nivel de reposo. Si el nivel de reposo del VIX cambió entre eras (pre-2010 vs QE vs post-2020), el decaimiento hacia un μ fijo es un modelo mal especificado. ¿Cómo lo auditarías?
2. N=13 episodios, 2 de los cuales son GFC y pandemia (que dominan cualquier estadístico). ¿Tiene sentido reportar "mediana 8.2d" o debería reportarse solo la distribución completa por episodio?
3. El rechazo de ζ se basa en ACF positiva + 0 overshoot. ¿Hay alguna configuración de segundo orden que produzca ACF positiva (sobreamortiguado ζ>1) y que estemos descartando mal? (ζ>1 no oscila — revisar si la conclusión debe ser "rechazamos ζ<1" y no "rechazamos segundo orden").
4. La hipótesis D3 quedó abierta con N=13. El equipo propone re-testear sobre la serie diaria completa. ¿Hay riesgo de data snooping si se busca el umbral D3 óptimo en la misma historia?

---

## 5. COMPONENTE D — REFACTOR DEL GOD FILE (NUEVO, sin auditar)

### Lo que se hizo
`medir_senal.py` (1,497 líneas) → paquete `arnes/` por extracción AST de rangos de línea:
- `datos.py` (33L) carga | `registro.py` (22L) registry | `señales.py` (341L) 28 señales | `estadisticas.py` (88L) | `timing.py` (92L) | `estructura.py` (280L) | `medicion.py` (499L) medir() | `cli.py` (149L)
- `medir_senal.py` quedó como fachada de 60 líneas que re-exporta todo (`from arnes import ...`)
- Original en `_deprecated/medir_senal_godfile_1497L_backup.py`

### Regresión realizada
3 señales (credit_easing_k1, bsi_recovery, euforia), seed=42, bootstrap=3000, JSON completo diff → **0 diferencias** vía paquete y vía fachada CLI. La regresión detectó y corrigió 1 bug: `sorpresa_total` referencia `_surprise_vector` (movido a estructura.py) → NameError en call-time, tragado por un `try/except Exception: pass` en lookback_crash.

### Preguntas para Opus (componente D)
1. La regresión cubrió 3 de 28 señales. ¿Qué señales adicionales elegirías y por qué? (Pista: las que usan helpers cross-módulo o paths especiales.)
2. La fachada re-exporta con `from arnes import *`-style explícito. ¿Hay algún símbolo público del original que NO esté re-exportado? Comparar `dir()` del backup vs la fachada.
3. `arnes/datos.py` define ROOT con `parents[3]`; el original usaba `parent.parent.parent`. Verificar que resuelven al mismo path.
4. El `_registrar` decorador se ejecuta al importar `arnes/señales.py`. ¿El orden de registro y el contenido de `_CERTEZA` son idénticos al original? (Comparar los 28 metadatos.)
5. ¿Hay estado mutable global (caches, dicts) que pueda divergir entre el original y el paquete en ejecuciones repetidas?

---

## 6. SALIDA ESPERADA

```markdown
# AUDITORÍA OPUS — Etapa 22-Ago-2026

## 1. Veredicto general
[APROBADO / APROBADO CON RESERVAS / RECHAZADO] por componente (A/B/C/D)

## 2. Hallazgos por componente
| # | Componente | Hallazgo | Severidad | Evidencia (corrida/dato) | Corrección |

## 3. Respuestas a las 19 preguntas numeradas
[una por una, con verificación empírica cuando aplique]

## 4. Sesgos que Gemini no vio
[esta auditoría es independiente de las 4 rondas previas]

## 5. Recomendaciones priorizadas antes del siguiente paso
[P0 bloqueantes / P1 importantes / P2 mejoras]
```

**Firma del solicitante:** qwen/qwen3.8-max (Hermes) · 22-Ago-2026
