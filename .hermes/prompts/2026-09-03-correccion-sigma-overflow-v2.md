# PROMPT: Corrección de `sigma_overflow.py` — Escala Empírica Exportable sin Look-Ahead (v2)

**Fecha:** 03-Sep-2026
**Ejecutor:** Gemini
**Pre-auditado por:** Claude (rechazó v1 por look-ahead; corregido en v2)
**Propósito:** Corregir el cálculo de overflow de `sigma_overflow.py` (μ/σ paramétricos fijos → overflows incorrectos: 13× FP en VIX, ceguera total en FG/BSI/DXY/Yield). **Alcance acotado:** solo overflow/z-scores/SIGMET. Los bins, state keys y fact stores (expanding rank, correctos) NO se tocan.

---

## DECISIONES DE DISEÑO (consensuadas — no abiertas a debate)

### D0 — POLÍTICA GENERAL DE INCEPTION (para TODAS las evaluaciones) 🔴

**Regla canónica:** Una estación/senal **no existe antes de su `fecha_inicio_valida`** (nacimiento). NINGUNA evaluación puede usar datos pre-inception. Esto es **política general** de todo el pipeline, no solo de la calibración del overflow.

**Aplicación obligatoria en TODOS los evaluadores y generadores que tocan señales/disparos/estados:**
- `evaluador_vela_a_vela.py` — ✅ YA aplica (L211-218)
- `evaluador_general.py` — ✅ YA aplica (L273-274, L492-519)
- `construir_bar_snapshot.py` — ❌ **NO aplica — CORREGIR** (genera bar_signals → BUG #2)
- `arnes/medicion.py` — ❌ **NO aplica — CORREGIR** (núcleo de medición de señales)
- `ejercicios_regimen.py` — ❌ **NO aplica — CORREGIR**
- `consultar_inteligencia.py` — ✅ aplica (era_start)
- `consolidar_ranking.py` — ⚠️ verificar

**Reglas:**
1. Cualquier disparo/observación cuya fecha < `fecha_inicio_valida` de la estación se **excluye** de la evaluación (no es falla, es pre-nacimiento).
2. Los cuantiles empíricos, bins, z-scores y stats se computan SOLO sobre la muestra ≤ fecha → usando datos ≥ inception de la estación.
3. Un script que procese señales y NO filtre por inception es un **BUG de política** — debe corregirse.

**Inception dates canónicas (de `_CERTEZA` / registro METAR):**
| Estación | fecha_inicio_valida |
|:---------|:-------------------|
| VIX | 1990-01-02 |
| VVIX | 2006-03-06 |
| PCR | 2006-11-01 |
| F&G | 2011-02-01 |
| SV5_TURBULENCE | 1999-01-04 |
| SKEW | 2011-02-01 |
| CREDIT | 2007-04-11 |
| YIELD_CURVE | 1993-01-29 |
| ROTATION | 1999-01-04 |
| DXY | 1993-01-29 |
| BSI | 1993-01-29 |

### D1 — Población de calibración: data válida desde inception (CORRECCIÓN v2)

Los cuantiles empíricos se computan sobre la **muestra VÁLIDA de cada estación desde su `fecha_inicio_valida`**, EXCLUYENDO el periodo pre-inception (donde la señal no existe o no es válida). **No incluir historia pre-inception.**

Inception dates de referencia (de `_CERTEZA` / registro METAR):
| Estación | fecha_inicio_valida |
|:---------|:-------------------|
| VIX | 1990-01-02 |
| VVIX | 2006-03-06 |
| PCR | 2006-11-01 |
| F&G | 2011-02-01 |
| SV5_TURBULENCE | 1999-01-04 |
| SKEW | **2011-02-01** |
| CREDIT | 2007-04-11 |
| YIELD_CURVE | 1993-01-29 |
| ROTATION | 1999-01-04 |
| DXY | 1993-01-29 |
| BSI | 1993-01-29 |

> Ejemplo (SKEW): su muestra válida empieza en 2011. La calibración usa SOLO datos ≥ 2011-02-01; NO incluye la serie cruda de SKEW de 1990. F&G igual (2011). Esto evita contaminar la calibración con valores pre-inception inválidos.

### D2 — Filosofía expanding / out-of-sample, SIN look-ahead (CORRECCIÓN v2 — bloqueante)

Los cuantiles empíricos NO son de la población completa estática (que reintroduce look-ahead). Se aplican con **filosofía expanding** coherente con los bins:
- **Lake histórico:** `z(t)` se computa usando SOLO los cuantiles de la serie ≤ fecha t (historia pasada, sin ver el futuro).
- **Runtime en vivo:** edges congelados del último recalibración (anual, min 2 años train).
- **Coherencia:** los bins ya usan `expanding().rank(pct=True, min_periods=252)`; el z debe seguir la MISMA filosofía.

> Esto elimina el look-ahead y hace la verificación (eventos históricos) honesta: el umbral de 2015 NO incluye el spike de 2020/2024.

### D3 — D2/D3 por estación independiente

Cada estación computa sus propios cuantiles de velocidad (D2 = diff(3)) y estabilidad (D3 = std(2)/std(10)) sobre SU propia serie válida. NO hay edges compartidos entre estaciones.

### D4 — Método: Piecewise Quantile Scaling

7 cuantiles gaussianos `[P0.135, P2.275, P15.866, P50, P84.134, P97.725, P99.865]` → z `[-3,-2,-1,0,+1,+2,+3]`, interpolación lineal entre anclas, extrapolación lineal en colas (>P99.865, <P0.135).

**Guard de anclas duplicadas (CORRECCIÓN v2 — bloqueante):** D3 (`std(2)/std(10)` con `.fillna(1.0)`) puede acumular masa en 1.0 → anclas duplicadas (P84.134==P97.725==1.0). `compute_empirical_z` DEBE detectar anclas no estrictamente crecientes y manejar ties (saltar/absorber duplicados, o z=0 en tramo degenerado, sin división por cero). Añadir test de D3 flat.

### D5 — Definición de overflow

Un valor es overflow (`|z|>3`) **solo si supera P99.865 o cae bajo P0.135** (0.135% nominal cada cola) en la serie válida desde inception, con filosofía expanding.

### D6 — Compatibilidad de símbolo de módulo (CORRECCIÓN v2 — bloqueante)

**NO eliminar `STATION_MU_SIGMA`.** Mantenerlo como alias de compatibilidad (o actualizar inventario) porque hay ~12 importadores directos de ese símbolo (ambos lake generators, coordinator.py, conjuncion_derisking.py, medicion.py del arnés, scratch/*). La compatibilidad se garantiza a nivel **módulo**, no solo de función.

### D7 — Canonizar el generador del lake (CORRECCIÓN v2)

Hay **dos** generadores que escriben `continuous_metar_lake.parquet`: `backend/scripts/generators/` y `research/01_señales_entry_exit/`. Determinar cuál es canónico y actualizar **ambos** (o eliminar el duplicado stale) para que una sola lógica escriba el parquet. El duplicado stale sobrescribiría con lógica vieja.

### D8 — Alcance acotado (CRÍTICO)

**NO tocar:** bins del lake (`*_d1_bin`), state keys (`*_sk`), edges de los 150 estados, fact stores (expanding rank — correctos). **Solo:** `sigma_overflow.py`, columnas `*_z_*` y overflows del lake, consumidores SIGMET.
**Nota:** `panic_score`/`euphoria_score` derivan de bins → permanecen INTACTOS.

---

## CAMBIOS

### Componente 1 — `backend/modules/entry_decision/domain/rules/sigma_overflow.py`
- Reemplazar `STATION_MU_SIGMA` (más mantenerlo como alias) por cuantiles empíricos de la serie válida desde inception.
- Implementar `compute_empirical_z(val, edges)` con guard de anclas duplicadas.
- Mantener `classify_overflow_tier()` (T1-T5) intacto.
- Mantener `validate_overflow()` con la nueva z.

### Componente 2 — Generador del lake (ambos, ver D7)
- Generar `*_z_*` y `*_ovf*` con cuantiles empíricos desde inception + filosofía expanding.
- NO alterar bins/state keys.

### Componente 3 — `tests/test_sigma_overflow.py`
- Fijar valores numéricos esperados (computed de los edges reales), con casos borde:
  - VIX mediana → z≈0, `(None, None)`
  - VIX 70 (en periodo K) → z≥3 `(UPPER)`
  - FG 95 → z>3 `(UPPER)`, FG 1.5 → z<-3 `(LOWER)`
  - Yield -1.8 → z<-3 `(LOWER)`
  - **D3 flat** (anclas duplicadas) → sin NaN/crash
  - NaN → `(None, None)`
  - Pre-inception (skew antes 2011) → `(None, None)` o excluido

---

## VERIFICACIÓN (obligatoria)

1. `pytest tests/test_sigma_overflow.py -v`
2. `pytest tests/ -q`
3. **Eventos históricos** (con calibración expanding solo-hasta-t, honesta): Lehman 2008, COVID 2020, inversión curva 2022-23, FG 3/95, spike VIX Ago-2024. Confirmar que los DETECTA con datos pasados.
4. Tabla overflows (paramétrico viejo vs empírico expanding) — confirmar 13×→~1 en VIX sinceramente (no por look-ahead).

---

## REGLAS
- **Data válida desde inception** — excluir pre-inception (F&G 2011, SKEW 2011, etc.).
- **Filosofía expanding sin look-ahead** — z(t) usa solo historia hasta t.
- **D2/D3 por estación independiente.**
- **No tocar lo que funciona** — bins/state keys/fact stores intactos.
- **Guard anclas duplicadas** en D3.
- **No eliminar `STATION_MU_SIGMA`** (12 importadores).
- **Canonizar generador del lake** (evitar sobrescritura stale).
- **Dato mata relato** — valores de test computados, no adivinados.
- **Piecewise Quantile Scaling** ya verificado monótono.