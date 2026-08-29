# AUDITORÍA CRUZADA — fact_store_v3_architecture.md vs. medir_senal.py + forense_precursores.py
## Alineación, Gaps, y Enriquecimiento
## Botero Trade — 20-Ago-2026

---

## 0. METODOLOGÍA DE AUDITORÍA

```
Cruzamos fact_store_v3_architecture.md (864 líneas, 16 secciones)
contra los 12 factores de éxito extraídos de:

  medir_senal.py          → 6 factores (función pura, distribución completa,
                             baseline homogéneo, tríada zigzag, MAE real,
                             wins/losses separados + CI95)

  forense_precursores.py  → 5 factores (LIFT como métrica, gate n_lose ≥ 3,
                             D1×D2 interacción, cross-señal universalidad,
                             código determinista)

Para cada factor, verificamos:
  ✅ ALINEADO     → fact_store_v3 ya lo contempla
  ⚠️ PARCIAL      → lo menciona pero no lo implementa completamente
  ❌ GAP           → no lo contempla (punto ciego)
  🌟 SUPERA        → fact_store_v3 tiene algo que nuestros algoritmos NO tienen
```

---

## 1. RESULTADOS DEL CRUCE (12 FACTORES × 3 ESTADOS)

### FACTORES DE medir_senal.py

| # | Factor | Estado | Evidencia en fact_store_v3 |
|---|---|---|---|
| 1 | **Función pura = una señal** (@_registrar) | ❌ GAP | No hay mecanismo de registro de señales. Describe fact stores como datos, no como señales registrables. |
| 2 | **Distribución completa (P5/P95)** | ❌ GAP | Solo p_bull, ev_net, e_ret_max/min. Sin percentiles. Sin P5/P95 de la distribución de retornos. |
| 3 | **Baseline homogéneo** (mismo pivot_type) | ⚠️ PARCIAL | Diferencia Fact Store (todos los días) de quants_obs (solo pivotes). Pero no implementa baseline homogéneo por pivot_type. |
| 4 | **Tríada zigzag** (zz25/zz50/zz75 + cascade) | ✅ ALINEADO | Secciones 3, 6, 7. Vector multi-escala. Cascade_overflow medido. 6 patrones inter-escala. |
| 5 | **MAE intra-trade real desde Vault** | ❌ GAP | No menciona MAE, drawdown intra-trade, ni consulta al Vault para precios Low/High. |
| 6 | **Wins/losses separados + CI95** | ❌ GAP | Bayesian Shrinkage reemplaza wins/losses crudos. Sin bootstrap CI95. `p_bull` es shrunk, no crudo. |

### FACTORES DE forense_precursores.py

| # | Factor | Estado | Evidencia en fact_store_v3 |
|---|---|---|---|
| 7 | **LIFT como métrica** (razón de proporciones) | ⚠️ PARCIAL | Sección 3.3 menciona "diamantes estadísticos" pero nunca calcula LIFT = P(estado\|LOSER)/P(estado\|WINNER). Usa Bayesian Shrinkage en vez de LIFT. |
| 8 | **Gate n_lose ≥ 3** (no n_total) | ⚠️ PARCIAL | Confidence Tiers (Sección 13) usan N total. "LOW: 3-5 → solo dirección". PERO Sección 3.3 dice "los diamantes no se descartan". Contradicción interna. |
| 9 | **D1×D2 interacción** (cuarta dimensión) | ✅ ALINEADO | D1×D2×D3 implícito en state_key. Pero no calcula lifts por D1×D2 cross. |
| 10 | **Precursores universales** (cross-señal) | ❌ GAP | No hay agregación cross-estación. Cada fact store es independiente. No hay "universalidad". |
| 11 | **Código determinista** (sin agentes) | ✅ ALINEADO | v3_fact_table_engine.py es determinista. Pero el documento es prosa, no código ejecutable. |

---

## 2. MATRIZ DE ALINEACIÓN (RESUMEN VISUAL)

```
                    medir_senal  forense     fact_store_v3
                    ───────────  ───────     ─────────────
Función pura         ✅           —           ❌ GAP
Distribución P5/P95  ✅           —           ❌ GAP
Baseline homogéneo   ✅           —           ⚠️ PARCIAL
Tríada zigzag        ✅           —           ✅ ALINEADO
MAE real Vault       ✅           —           ❌ GAP
Wins/losses + CI95   ✅           —           ❌ GAP
LIFT métrica         —           ✅           ⚠️ PARCIAL
Gate n_lose ≥ 3      —           ✅           ⚠️ PARCIAL (contradictorio)
D1×D2 interacción    —           ✅           ✅ ALINEADO
Cross-señal univ.    —           ✅           ❌ GAP
Código determinista  —           ✅           ✅ ALINEADO
```

**Resultado:**
- ✅ ALINEADO: 3/11 factores
- ⚠️ PARCIAL: 4/11 factores
- ❌ GAP: 4/11 factores
- — (no aplica): los factores son específicos de cada algoritmo

---

## 3. LOS 4 GAPS CRÍTICOS (lo que fact_store_v3 NO contempla)

### 🔴 GAP 1: Sin distribución completa de retornos (P5/P95)

```
QUÉ DICE fact_store_v3:
  "p_bull = Bayesian Shrinkage sobre n_pos / (n_pos + n_neg)"
  "e_ret_max = mean(r | r > 0)"
  → Solo media + probabilidad. Sin percentiles. Sin colas.

QUÉ HACE medir_senal.py:
  _pctiles(act) → P5, P25, P50, P75, P95
  _wins_losses(act) → n_wins, n_losses, mean_win, mean_loss, profit_factor

POR QUÉ ES UN GAP:
  Un estado con p_bull=0.55 y ev_net=+0.02 puede tener:
    P5 = -15% (cola izquierda catastrófica)
    P95 = +8% (upside limitado)
  Sin la distribución completa, NO SABES el riesgo real.
  La asimetría (mean_win vs mean_loss) es INVISIBLE sin wins/losses separados.

IMPACTO: Las decisiones basadas solo en p_bull + ev_net son INCOMPLETAS.
         Señales con buena media pero cola izquierda catastrófica
         parecen "buenas" cuando no lo son.
```

### 🔴 GAP 2: Sin bootstrap CI95

```
QUÉ DICE fact_store_v3:
  "confidence_tier basado en N absoluto: ROBUST ≥21, HIGH ≥11, ..."
  → Clasificación por N, no por intervalo de confianza.

QUÉ HACE medir_senal.py:
  _bootstrap_ci(np.mean, data, n_iter=3000, seed=42)
  → CI95 = [lower, upper]
  → Si CI95 cruza cero → NO significativo, aunque N=100

POR QUÉ ES UN GAP:
  N=100 con CI95 que cruza cero → NO confiable
  N=8 con CI95 tight que no cruza cero → confiable
  El tier por N absoluto es una HEURÍSTICA, no una validación.

  Ejemplo real: credit_easing_k1 N=112 → CI95 [+4.41%, +6.01%] → CONFIABLE
                capitulacion N=82 → CI95 [-0.46%, +3.29%] → NO CONFIABLE
  Ambas tienen tier "ROBUST" por N, pero solo una pasa CI95.

IMPACTO: Sin CI95, el confidence_tier puede clasificar como "ROBUST"
         señales que NO son estadísticamente significativas.
```

### 🔴 GAP 3: Sin métricas de trayectoria (MAE, costo tarde, sensibilidad timing)

```
QUÉ DICE fact_store_v3:
  "ftt_bull_days" → cuánto tarda en llegar al techo
  "ftt_bear_days" → cuánto tarda en llegar al piso
  → Solo duración esperada. Sin drawdown. Sin costo de timing.

QUÉ HACE medir_senal.py:
  _mae_intratrade(spy, señal, df)    → MAE real desde Vault (Low/High)
  _costo_tarde(spy, señal, df, k=1)  → costo de esperar 1 barra
  _sensibilidad_timing(spy, señal, df, ks=[0,1,2,3,5]) → edge a ±k barras

POR QUÉ ES UN GAP:
  "La pierna tarda 12 días en llegar al techo" no te dice:
    - ¿Cuánto drawdown sufro en esos 12 días? (MAE)
    - ¿Cuánto pierdo si entro 1 día tarde? (costo_tarde)
    - ¿El edge sobrevive si entro 3 barras después del pivote? (sensibilidad)

  El usuario lo dijo explícitamente:
  "No evaluaron el riesgo o drawdown de comprar temprano o tarde"

IMPACTO: Sin MAE, el fact store no puede responder "¿cuánto pierdo
         en el peor momento de este trade?" — que es la pregunta
         que todo trader necesita responder.
```

### 🔴 GAP 4: Sin agregación cross-estación (precursores universales)

```
QUÉ DICE fact_store_v3:
  11 fact stores independientes. Cada uno mide SU indicador.
  Sin mecanismo de agregación cross-estación.

QUÉ HACE forense_precursores.py:
  precursor_counts = defaultdict(list)
  for sig, res in all_results.items():
      for p in res["precursores"]:
          key = f"{p['station']}.{p['dim']}={p['state']}"
          precursor_counts[key].append(...)
  universal = [k for k, v in precursor_counts.items() if len(v) >= 2]

POR QUÉ ES UN GAP:
  credit.D2=ACCELERATING_UP_3D aparece en 5/6 señales → PRECURSOR UNIVERSAL
  Esto NO se puede detectar mirando UN fact store aislado.
  La señal emerge de la CONJUNCIÓN de múltiples estaciones.

  La arquitectura actual de 11 fact stores independientes es CIEGA
  a patrones que cruzan estaciones.

IMPACTO: Sin agregación cross-estación, el sistema no puede detectar
         la señal más valiosa que encontramos: los precursores universales.
```

---

## 4. LOS 4 GAPS PARCIALES (mencionado pero no implementado)

### ⚠️ GAP PARCIAL 1: Bayesian Shrinkage destruye diamantes

```
QUÉ DICE fact_store_v3:
  Sección 6: "Bayesian Laplace Shrinkage (m=10)"
  "Con N=3: credibilidad = 23% → 77% del prior neutro (0.50 o 0)"
  Anti-patrón #8: "NO aplicar Bayesian Shrinkage ciego a diamantes"

CONTRADICCIÓN:
  La Sección 6 DEFINE el shrinkage como comportamiento DEFAULT.
  El Anti-patrón #8 ADVIERTE no usarlo en diamantes.
  → El documento se contradice a sí mismo.

QUÉ HACE forense_precursores.py:
  LIFT = p_lose / p_win (crudo, sin shrinkage)
  Si p_win es ~0 → cap a 10.0
  NUNCA aplica shrinkage a estados low-N

CORRECCIÓN:
  Separar en DOS campos:
    p_bull_raw = n_pos / n_tot          ← para decisiones (diamantes)
    p_bull_shrunk = (n_pos+m*0.5)/(n_tot+m) ← para comparación (estados poblados)
  Reportar AMBOS. Decidir con el RAW.
```

### ⚠️ GAP PARCIAL 2: Confidence Tiers sin CI95

```
QUÉ DICE fact_store_v3:
  Sección 13: Tiers por N absoluto (ROBUST ≥21, HIGH ≥11, ...)

QUÉ FALTA:
  Complementar cada tier con CI95 bootstrap.
  Un estado ROBUST (N≥21) con CI95 que cruza cero → NO es robusto.
  Un estado LOW (N=3-5) con CI95 tight → puede ser MÁS robusto que uno ROBUST.

CORRECCIÓN:
  Agregar bootstrap CI95 a los confidence tiers.
  Tier final = min(tier_N, tier_CI95).
```

### ⚠️ GAP PARCIAL 3: Diferencia Fact Store vs quants_obs documentada pero no operacionalizada

```
QUÉ DICE fact_store_v3:
  Sección 1: "Si divergen >20%, investigar el sesgo de selección por pivot_type"
  → Mención correcta pero sin protocolo.

QUÉ FALTA:
  Un protocolo de reconciliación:
    1. Medir señal en quants_obs (ground truth)
    2. Consultar mismo estado en fact store (prospección)
    3. Si Δ > 20%:
       a. ¿El fact store tiene N bajo? → priorizar quants_obs
       b. ¿El quants_obs tiene sesgo de pivot_type? → ajustar baseline
       c. ¿Ambos tienen N suficiente? → investigar divergencia
    4. Documentar la divergencia como hallazgo

CORRECCIÓN:
  Agregar Sección 1.2: Protocolo de Reconciliación Fact Store ↔ quants_obs
```

### ⚠️ GAP PARCIAL 4: Anti-patrón #6 sobre Win Rate es correcto pero incompleto

```
QUÉ DICE fact_store_v3:
  Anti-patrón #6: "Tratar Win Rate como métrica. El WR del ZigZag tiene
  sesgo estructural: pisos siempre 'ganan'. No es métrica válida."

ES CORRECTO para quants_obs (pivotes ZigZag).
Pero NO aplica al fact store (todos los días, sin sesgo de pivot_type).

QUÉ FALTA:
  El fact store SÍ puede usar WR como métrica válida porque NO filtra
  por pivot_type. La advertencia debe ser específica a quants_obs.

CORRECCIÓN:
  "Anti-patrón #6 (corregido): Tratar Win Rate de quants_obs como métrica.
   En quants_obs, los pivotes MIN siempre 'ganan' (la pierna siguiente sube)
   por estructura del ZigZag. En el fact store, el WR es válido porque
   incluye TODOS los días sin filtrar por pivot_type."
```

---

## 5. LO QUE fact_store_v3 TIENE QUE NOSOTROS NO TENEMOS 🌟

### 🌟 FORTALEZA 1: Structural Momentum (HH/HL/LH/LL)

```
El fact store clasifica la ESTRUCTURA de la tendencia:
  - Higher Highs / Higher Lows → UPTREND
  - Lower Highs / Lower Lows → DOWNTREND
  - Divergencias → TRANSICIÓN

Nuestros algoritmos NO miden esto.
medir_senal.py mide retorno forward, no estructura de tendencia.
forense_precursores.py mide estados pre-crash, no momentum estructural.

ACCIÓN: Incorporar structural_momentum como filtro en nuestras señales.
        "Señal ENTRY + HL (Higher Lows) → convicción ALTA"
        "Señal ENTRY + LL (Lower Lows) → TRAMPA, no entrar"
```

### 🌟 FORTALEZA 2: Prev Leg Domino (contexto de la pierna anterior)

```
El fact store mide el TAMAÑO y TIPO de la pierna que precedió al estado:
  - ¿Venimos de un crash (>P90) o de un drift normal?
  - ¿La pierna previa fue alcista o bajista?
  - ¿Las piernas previas grandes tienen mayor tasa de cascada?

Nuestros algoritmos miden anticipación temporal (días antes del pivote)
pero NO el contexto de la pierna anterior.

ACCIÓN: Incorporar prev_leg_domino como contexto en medir_senal.py.
        "credit_easing_k1 + pierna previa extrema → edge AMPLIFICADO"
```

### 🌟 FORTALEZA 3: Regímenes de Divergencia Temporal

```
El fact store clasifica convergencia/divergencia entre horizontes (1d/3d/5d):
  - FULL_CONVERGENT_BULL:   los 3 horizontes son alcistas
  - TACTICAL_REBOUND_IN_BEAR: 1d up, 5d down (trampa alcista)

Nuestros algoritmos miden la tríada zigzag (zz25/zz50/zz75) pero
NO clasifican divergencia entre escalas.

ACCIÓN: Agregar clasificación de divergencia temporal a medir_senal.py.
        "cascade_50=0 + cascade_75=0 → CONVERGENTE (no escala)"
        "cascade_50=1 + cascade_75=0 → DIVERGENTE (corrección contenida)"
        "cascade_50=1 + cascade_75=1 → CONVERGENTE (overflow total)"
```

### 🌟 FORTALEZA 4: Guía de Empleo (Dato → Pregunta → Decisión)

```
Sección 15: Cada campo del fact store está mapeado a:
  - Qué pregunta responde
  - Qué decisión informa
  - Quién es el consumidor

Nuestros algoritmos generan datos pero NO documentan su empleo.
Los 21 campos del JSON de medir_senal.py no tienen un mapa Dato→Decisión.

ACCIÓN: Crear guía de empleo para los 21 campos de medir_senal.py
        siguiendo el mismo formato de la Sección 15.
```

### 🌟 FORTALEZA 5: Árboles de Decisión Operacionales

```
Secciones 15.2 y 15.3: Árboles de decisión para EXIT y ENTRY.
  - Si p_bull < 0.30 → ALTA CONVICCIÓN → SALIR
  - Si cascade_rate_t3 > 0.50 → SALIR URGENTE
  - Si structural_momentum muestra LH → SALIR

Nuestros algoritmos miden señales pero NO producen árboles de decisión.

ACCIÓN: Construir árboles de decisión que integren:
        señal medir_senal + precursores forense + structural_momentum fact_store
```

---

## 6. PLAN DE ENRIQUECIMIENTO (qué agregar a fact_store_v3)

### Addendum 1: Bootstrap CI95 en Confidence Tiers

```markdown
## 13.1 Confidence Tiers with Bootstrap CI95

Los tiers por N absoluto son una heurística. La validación definitiva requiere:

| Tier | N | Condición CI95 | Interpretación |
|------|---|----------------|----------------|
| CONFIRMED | ≥21 | CI95 no cruza cero Y ancho < 5pp | Señal completamente validada |
| ROBUST | ≥21 | CI95 no cruza cero | Señal robusta |
| DIRECTIONAL | ≥21 | CI95 cruza cero | Dirección correcta, magnitud incierta |
| DIAMANTE | 3-20 | CI95 no cruza cero | Alta asimetría, evento raro valioso |
| EXPLORATORIO | 3-20 | CI95 cruza cero | Observar, no operar |
| INSUFICIENTE | <3 | — | Sin datos suficientes |

Bootstrap: n_iter=3000, seed=42, block_size=5 (corrige autocorrelación temporal)
```

### Addendum 2: N_eff para señales con clustering

```markdown
## 13.2 Effective Sample Size (N_eff)

Señales que disparan en clusters temporales inflan el N bruto.
Para cada estado, calcular:

  N_eff = N_bruto / (1 + 2 × Σ ρ_k)  donde ρ_k = autocorrelación en lag k

Usar block bootstrap con ventana de 30 días.
Si N_eff / N_bruto < 0.5 → inflación significativa.
Reportar AMBOS: N_bruto y N_eff.
```

### Addendum 3: Wins/Losses Separados + Asimetría

```markdown
## 6.2 Wins/Losses Desglosados

Para cada estado, reportar wins y losses por separado:

| Campo | Fórmula | Interpretación |
|-------|---------|----------------|
| n_wins | count(r > 0) | Número de días/piernas positivas |
| n_losses | count(r ≤ 0) | Número de días/piernas negativas |
| mean_win | mean(r \| r > 0) | Retorno medio cuando gana |
| mean_loss | mean(r \| r < 0) | Retorno medio cuando pierde |
| win_rate | n_wins / (n_wins + n_losses) | Tasa de acierto CRUDA (sin shrinkage) |
| profit_factor | gross_win / gross_loss | Factor de profit |
| asymmetry | mean_win / \|mean_loss\| | >1: gana más de lo que pierde. <1: pierde más de lo que gana |

La asimetría clasifica el PERFIL de cada estado:
  asymmetry > 1.2 → DEFENSIVO (evitar pérdidas es más valioso que buscar ganancias)
  asymmetry < 0.8 → OFENSIVO (buscar ganancias es más valioso que evitar pérdidas)
```

### Addendum 4: Distribución Completa (P5/P95)

```markdown
## 6.3 Distribución Completa de Retornos

Para cada estado, reportar percentiles:

  p5, p25, p50 (median), p75, p95

La distribución completa expone la cola izquierda.
Un estado con p_bull=0.55 y ev_net=+0.02 puede tener:
  P5 = -15% (cola izquierda catastrófica)
  P95 = +8% (upside limitado)

Sin P5, el riesgo de cola es invisible.
```

### Addendum 5: Tasa de Activación Base

```markdown
## 6.4 Tasa de Activación Base

Para cada estado D1, medir en qué porcentaje de TODOS los días se activa:

  base_rate = n_days_in_state / n_total_days

Si base_rate > 50% → el estado NO es una señal, es BACKGROUND.
Si base_rate < 5% → el estado es RARO (potencial diamante).

Ejemplo: BSI Oversold se activa en 68.9% de los pivotes MIN.
         → NO es una señal de piso. Es ruido de fondo.
```

### Addendum 6: Overlap Matrix entre Estados

```markdown
## 11.1 Matriz de Overlap entre Señales

Antes de proponer una "nueva capa", medir overlap con capas existentes:

Para cada par de estados (D1_a, D1_b):
  overlap = P(D1_a ∩ D1_b) / P(D1_a ∪ D1_b)

Si overlap > 60% → información REDUNDANTE (no agrega valor).
Si overlap < 20% → información ORTOGONAL (agrega valor).
```

### Addendum 7: Agregación Cross-Estación (Precursores Universales)

```markdown
## 11.2 Precursores Universales (Cross-Estación)

Un estado que aparece como bearish en MÚLTIPLES estaciones independientes
es un precursor universal:

  Para cada state_key D1__D2__D3:
    contar en cuántas estaciones p_bull < 0.40 (bearish)
    Si ≥ 3 estaciones → PRECURSOR UNIVERSAL

 Ejemplo:
   credit: ACCELERATING_UP_3D  → p_bull=0.35 (bearish)
   vix:    CRISIS_SPIKE        → p_bull=0.32 (bearish)
   bsi:    BREADTH_WASHED_OUT  → p_bull=0.28 (bearish)
   → 3/11 estaciones bearish → ALERTA DE CRASH
```

---

## 7. RESUMEN EJECUTIVO

### Alineación actual: 3/11 factores (27%)

```
✅ ALINEADO:    Tríada zigzag, D1×D2×D3, código determinista
⚠️ PARCIAL:    Baseline homogéneo, LIFT/diamantes, confidence tiers,
                diferencia Fact Store vs quants_obs, Win Rate
❌ GAP:         Distribución completa (P5/P95), bootstrap CI95,
                métricas de trayectoria (MAE), cross-señal universal
```

### Lo que fact_store_v3 necesita aprender de nuestros algoritmos (6 addenda):

| # | Addendum | Previene qué fallo |
|---|---|---|
| 1 | Bootstrap CI95 en Confidence Tiers | Clasificar como ROBUST señales con CI95 que cruza cero |
| 2 | N_eff para clustering temporal | N inflado 2.86x-6.96x (fallo Gemini #4) |
| 3 | Wins/Losses separados + asimetría | Media que esconde cola izquierda catastrófica |
| 4 | Distribución completa (P5/P95) | Señales que parecen buenas pero tienen P5 = -24.6% |
| 5 | Tasa de activación base | Constantes tratadas como señales (fallo Gemini #2) |
| 6 | Overlap matrix | Capas redundantes tratadas como nuevas (fallo Gemini #3) |
| 7 | Cross-estación universalidad | Incapacidad de detectar precursores que cruzan estaciones |

### Lo que nuestros algoritmos necesitan aprender de fact_store_v3 (5 fortalezas):

| # | Fortaleza | Enriquece qué |
|---|---|---|
| 1 | Structural Momentum (HH/HL/LH/LL) | Clasificar tendencia → filtrar entradas en LL (trampas) |
| 2 | Prev Leg Domino (lookback) | Contexto de la pierna anterior → edge amplificado post-crash |
| 3 | Regímenes de Divergencia Temporal | Clasificar convergencia/divergencia entre escalas zigzag |
| 4 | Guía de Empleo (Dato→Pregunta→Decisión) | Documentar el empleo de cada campo del JSON de medición |
| 5 | Árboles de Decisión Operacionales | Integrar medición + precursores + momentum en decisiones |

---

## 8. ESTADO FINAL

| Campo | Valor |
|-------|-------|
| **Documento auditado** | `fact_store_v3_architecture.md` (864 líneas) |
| **Documentos de referencia** | `medir_senal.py` (1,183 líneas), `forense_precursores.py` (221 líneas) |
| **Factores cruzados** | 11 |
| **Alineación** | 3/11 (27%) |
| **Gaps encontrados** | 4 críticos + 4 parciales |
| **Fortalezas de fact_store_v3** | 5 que nuestros algoritmos no tienen |
| **Addenda propuestos** | 7 para fact_store_v3 + 5 para nuestros algoritmos |
| **Veredicto** | Ambos sistemas son COMPLEMENTARIOS. Cada uno tiene fortalezas que el otro no tiene. La integración de ambos produciría un sistema más completo que cualquiera por separado. |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 20-Ago-2026
**Archivos cruzados:** `fact_store_v3_architecture.md` × `medir_senal.py` × `forense_precursores.py`