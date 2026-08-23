# INFORME AUDITORÍA PROFUNDA + CALIBRACIÓN — Cadena `quants_obs` (23-Ago-2026)

**Firma:** qwen/qwen3.8-max (Hermes)
**Objetivo:** (1) auditoría profunda de toda la cadena buscando más ajustes/correcciones/adiciones;
(2) calibración de `cascade_reversal`; (3) dejar todo documentado para auditoría externa.
**Principio rector:** el propósito es una tabla de observación correcta y reproducible para
medir señales. La fidelidad al one-off es detector de divergencias, no meta.

---

## FASE 1 — AUDITORÍA PROFUNDA (barrido sistemático)

### 1.1 Consumidores de `quants_obs.pkl` (24 scripts mapeados)

| Área | Scripts |
|------|---------|
| Núcleo señales | `arnes/datos.py`, `arnes/timing.py`, `evaluador_vela_a_vela.py`, `medir_senal.py`, `wins_losses_sv5t_vix_bsi_credit.py` |
| Cascade | `cascade_add_one_in.py`, `cascade_station_leave_one_out.py`, `cascade_walkforward_reduccion.py` |
| Estaciones | `credit_easing_pisos.py`, `yield_curve_recesion.py` |
| Conjunción | `distortion_surprise_adelantada.py`, `distortion_test.py`, `pendiente_cat1_natural.py` |
| Metodología LDP | `dispersion_estaciones.py`, `dispersion_triada_walkforward.py`, `ev_station_leave_one_out.py`, `mi_permutation_test.py`, `pbo_cpcv.py`, `quantitative_audit_lopez_de_prado.py` |
| Otros | `detector_regimen_crisis.py`, `builder_quants_obs.py`, `regenerar_quants_obs.py`, `taf_ftt_evpd_audit.py`, `test_anticipacion_temporal.py`, `research_paths.py` |

### 1.2 Verificaciones ejecutadas (con resultado)

| Check | Resultado |
|-------|-----------|
| Columnas referidas en `señales.py` vs tabla nueva | ✅ Ninguna faltante (el bug `cascade_conviction_50` ya fue corregido en v3) |
| Todos los D1 referidos por las señales existen en la tabla nueva | ✅ Ningún D1 ausente |
| Columnas usadas por consumidores clave (`distortion_test`, `taf_ftt_evpd_audit`, `cascade_walkforward_reduccion`) | ✅ Todas existen (`daily_return_pct`, `duration_bars`, `prev_leg_return`, `cascade_50`, `pivot_type`, `abs_prev_leg_return`) |
| Bins D1 por estación (tabla nueva) | ✅ 6 bins Gaussianos en las 11 estaciones (consistente) |

### 1.3 Hallazgos de la auditoría profunda y fixes aplicados

**F5 — Pesos de cascade_conviction hardcoded (encontrado esta sesión):**
El builder usaba `0.66/0.34` hardcoded. Ahora se leen dinámicamente del type_mask del
cal-file (como los μ/σ tras F1). Hoy MIN/MAX tienen pesos idénticos 0.66/0.34, pero un
cambio futuro de calibración ahora se propaga automáticamente. **FIX APLICADO.**

**Constantes verificadas que SÍ deben ser dinámicas (todas lo son ahora):**
- μ/σ de `z_bear` → del cal-file (F1, aplicado 23-Ago temprano)
- μ/σ de `z_dom` → del cal-file (ya era dinámico)
- Pesos `cascade_conviction` → del type_mask (F5, aplicado esta sesión)

**Limitaciones conocidas (documentadas, no son bugs):**
- F4: 236 fechas de pivote duplicadas (propiedad del zigzag; warning activo en el builder)
- El umbral original 0.30 de `cascade_reversal` venía de un doc que confundía
  `cascade_50` (flag binario de proximidad) con convicción — raíz de la descalibración

---

## FASE 2 — CALIBRACIÓN DE `cascade_reversal`

### 2.1 El problema
Con la normalización de producción (μ/σ 0.41/0.3206), el umbral original `c50 < 0.30`
captura el **75.8%** de pivotes = background puro. El tercil_bajo del cal-file (−0.387)
y el cero (0.0) también quedan en background (fire rate >25%).

### 2.2 Barrido de umbrales (resultados completos)

| Umbral | Corte | Fire rate | N | Mejor edge | p |
|--------|-------|:---:|:---:|-----------|:---:|
| original_0.30 | 0.30 | **75.8%** | 1205 | — (background) | — |
| tercil_bajo | −0.387 | >25% | — | SKIPPED (background) | — |
| cero | 0.0 | >25% | — | SKIPPED (background) | — |
| p25 | −0.747 | 25.0% | 397 | +0.14% (zz25\|ALZA) | 0.27 |
| p20 | −0.867 | 20.0% | 318 | +0.09% | 0.40 |
| **p15** | **−0.957** | **15.0%** | **239** | **+0.28% (zz25\|ALZA)** | **0.25** |
| p10 | −1.034 | 10.0% | 159 | +0.25% | 0.31 |

### 2.3 Decisión: umbral p15 (−0.957), CONGELADO

**Criterio de elección:**
1. Fire rate 15% → bajo el umbral de background (20%) del evaluador
2. Mejor edge neto (+0.28%) y mejor hit (72.6%, PF 3.06) del barrido
3. El cuantil se CONGELA como constante fija (recalcularlo por ejecución sería look-ahead)

**Resultado honesto:** la señal dispara 239-240 veces con edge +0.28% pero **p=0.25 —
NO es estadísticamente significativa**. El gradiente direccional es real (edge negativo
consistente en régimen BAJA, −1.2% a −2.4%), pero no hay potencia para promoción.
**Estado: PROPOSED con calibración honesta; requiere validación OOS/walk-forward antes
de cualquier promoción.**

### 2.4 Verificación post-calibración (builder v7)
- Señal disparando: **240 veces** (fire rate 15%)
- zz25|ALZA: n=113, +0.28%, hit 72.6%, p=0.25
- zz25|BAJA: n=127, −1.24%, hit 21.3% (edge negativo = la señal "falla" en BAJA, consistente con gradiente)

---

## FASE 3 — ESTADO FINAL DE LA CADENA

### 3.1 Builder v7 (post-auditoría profunda)
| Métrica | Valor |
|---------|-------|
| Columnas ≥99.9% match | 101/141 |
| CAT-A / CAT-B / CAT-C | 12 / 37 / **0** |
| Señales disparando | **28/28** (cero inertes) |
| Constantes dinámicas | μ/σ z_bear, μ/σ z_dom, pesos cascade (todos del cal-file) |
| Determinismo | bit-a-bit (verificado por auditoría Opus) |

### 3.2 Fixes acumulados (historial completo de correcciones)

| # | Fix | Sesión | Estado |
|:-:|-----|--------|:---:|
| 1 | `cascade_conviction_50` columna faltante (señal inerte en silencio) | 22-Ago | ✅ |
| 2 | `d1_bear_5` fórmula media→fracción de presión bearish | 22-Ago | ✅ |
| 3 | Alineación `_val/_vel/_vol` ffill→fecha exacta, defaults vel=0/vol=1 | 22-Ago | ✅ |
| 4 | `duration_bars`/`daily_return_pct` → pierna saliente, duración calendario, piso 1 día | 22-Ago | ✅ |
| 5 | `next_bear`/`next_leg_direction` → idénticos a `leg_bear` | 22-Ago | ✅ |
| 6 | `{st}_zk_pbull/pbear` → bloque `zigzag_kinematic.zz25` del fact store | 22-Ago | ✅ |
| F1 | μ/σ z_bear hardcoded→cal-file dinámico (17.9% inversiones de signo→0%) | 23-Ago | ✅ |
| F3 | d1_bear_5 Σ(max(0,−v))→conteo count(v<0) (robustez) | 23-Ago | ✅ |
| F4 | 236 fechas duplicadas documentadas con warning activo | 23-Ago | ✅ |
| F5 | Pesos cascade_conviction hardcoded→type_mask dinámico | 23-Ago | ✅ |
| F6 | Umbral `cascade_reversal` 0.30→−0.957 (calibrado, congelado) | 23-Ago | ✅ |

### 3.3 Decisiones CAT-A confirmadas (auditoría Opus + autoauditoría)
1. **Skew D1 solapado** → edges estáticos de producción, divergencia documentada
2. **OVERSOLD_BREADTH voto −0.5** → escala de producción {−1,0,+1}, divergencia explicada

---

## PARA LA AUDITORÍA EXTERNA — PREGUNTAS ABIERTAS

1. **Reproducibilidad de los pivotes (crítico):** verificar independientemente que los
   1,590 pivotes de `quants_obs_new.pkl` son exactamente los de
   `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")`.

2. **Las 236 fechas duplicadas:** ¿es correcto tratarlas como limitación conocida, o
   debería el zigzag de producción resolverlas (una pierna forward y una backward con
   el mismo start_timestamp)?

3. **`cascade_reversal` sin significancia (p=0.25):** ¿promover con el umbral p15
   congelado como diamante anecdótico, o mantener en PROPOSED hasta OOS? La semántica
   EXIT está documentada pero el edge no alcanza significancia.

4. **Consistencia D1 de señales:** todas las señales leen `sk.split("__")[0]`. Verificar
   que ninguna señal dependa del estado completo D1__D2__D3 (solo D1), confirmando que
   la divergencia CAT-A de skew (bins D1 solapados) afecta solo a `panico_total` y
   `skew_paranoia_exit` (ya cuantificado).

5. **Determinismo del builder:** el auditor Opus verificó hash idéntico en 2 runs.
   ¿Confirmar con un tercer run independiente?

6. **F4 vs F1:** el builder ahora usa μ/σ del cal-file (producción actual). El match
   vs el one-off original en z_bear/cascade es ~0% a propósito. ¿Es este el trade-off
   correcto (consistencia con producción > fidelidad al artefacto)?

## ARTEFACTOS
- `builder_quants_obs.py` (v7, con F5)
- `quants_obs_new.pkl` (1,590 × 142)
- `arnes/señales.py` (cascade_reversal calibrada)
- `manifiesto_divergencias_quants_obs.json`
- `calibracion_cascade_reversal.json`
- `AUTOAUDITORIA_GENERADOR_v5_22AGO.md`, `AUTOAUDITORIA_PROPOSITO_QUANTS_OBS.md`
- `RESPUESTA_AUDITORIA_OPUS_GENERADOR_23AGO.md`
- `evaluacion_TABLA_NUEVA.json`, `evaluacion_TABLA_ORIGINAL.json` (comparación completa)
