# WALKTHROUGH COMPLETO — Cadena de Medición y Clasificación de Señales (30-Ago-2026)

**Firma:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Trazar cada etapa desde el dato crudo hasta la conclusión de cada señal, verificando que las mediciones son estocásticas (no arbitrarias), que ningún extremo se ignora, y que las clasificaciones son consistentes.
**Principio rector:** *"Dato mata relato — toda afirmación con CI95 + N + distribución. Estación no es clima. Rareza = riqueza."*

---

## ARQUITECTURA GENERAL

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      CADENA DE MEDICIÓN — FLUJO COMPLETO                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MEDIR SEÑAL  (ARNÉS DE MEDICIÓN)  —  el contenedor                        │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  arnes/señales.py    — 31 definiciones de señales (dominio puro) │      │
│  │  arnes/medicion.py   — medir() y medir_cross_overlap()           │      │
│  │  arnes/estadisticas.py  — bootstrap CI95, Fisher, Clopper-Pearson│      │
│  │  arnes/timing.py     — MAE, costo de tarde, sensibilidad         │      │
│  │  arnes/estructura.py — sorpresa, momentum, divergencia           │      │
│  │  arnes/datos.py      — carga de quants_obs.pkl                   │      │
│  │  arnes/registro.py   — @_registrar y catálogo SEÑALES            │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│             │                                                            │
│             ▼                                                            │
│  quants_obs.pkl  (1,590 pivotes × 165 columnas, bins numéricos)         │
│  ─── LA TABLA DE OBSERVACIÓN — consumida por el arnés                    │
│             │                                                            │
│             ├──────────────────────────┬──────────────────────┐          │
│             ▼                          ▼                      ▼          │
│  FASE 2 — 31 SEÑALES en arnes/señales.py (dominio puro)                  │
│             │                                                            │
│             ├──────────────────────────┬──────────────────────┐          │
│             ▼                          ▼                      ▼          │
│  evaluador_vela_a_vela    recompute_triad_v2    audit_overflow_v2       │
│  first-passage × 3 esca  agregación ponderada   anatomía MIN/MAX/ENTRE   │
│  + INDEP + 3D-régimen     × 31 señales          610 combinaciones        │
│             │              Tier A/B/C           │                         │
│             ▼                                   │                         │
│  validador_oos.py                                │                        │
│  walk-forward 10 folds                          │                         │
│             │                                   │                         │
│             ▼                                   ▼                         │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                  CLASIFICACIÓN FINAL                              │   │
│  │  NÚCLEO (OOS) | DIAMANTES (§3.3) | PROPOSED | ACTIVAS | DEGRAD   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## FASE 0: EL ARNÉS DE MEDICIÓN — `medir_senal` (paquete `arnes/`)

**Medir Señal es el contenedor.** No es un paso en la cadena — es el marco completo que define cómo se miden las señales, qué estadísticas se usan, y cómo se cargan los datos.

### 0.1 El paquete `arnes/` (8 módulos)

| Módulo | Responsabilidad | Función principal |
|:-------|:---------------|:------------------|
| `registro.py` | Catálogo de señales y decorador `@_registrar` | `SEÑALES` dict, `_CERTEZA` metadatos |
| `señales.py` | 31 definiciones de señales (dominio puro) | Cada una: `f(df) → pd.Series(bool)` |
| `medicion.py` | Motor de medición completo | `medir()`, `medir_cross_overlap()` |
| `estadisticas.py` | Métricas estadísticas puras | `_pctiles`, `_wins_losses`, `_bootstrap_ci`, `_clopper_pearson_ci`, `_fisher_pvalue` |
| `timing.py` | Métricas temporales | `_mae_intratrade`, `_costo_tarde`, `_sensibilidad_timing` |
| `estructura.py` | Estructuras de mercado | `_surprise_vector`, `_structural_momentum_filter`, `_prev_leg_context`, `_divergence_regime` |
| `datos.py` | Carga de datos | `cargar_datos()` → (df, spy) desde `quants_obs.pkl` |
| `cli.py` | Interfaz de línea de comandos | `--señal`, `--horizontes`, `--bootstrap` |

### 0.2 Flujo dentro del arnés

```
arnes/datos.py → carga quants_obs.pkl → (df, spy)
                      │
                      ▼
arnes/señales.py → define 31 funciones f(df) → máscaras bool
                      │
                      ▼
arnes/medicion.py → medir() aplica cada señal sobre df:
  para cada disparo:
    1. Calcula forward_col (retorno de la pierna siguiente)
    2. _pctiles → distribución completa (P5/P25/P50/P75/P95)
    3. _wins_losses → wins/losses separados
    4. _bootstrap_ci → CI95 (3,000 iteraciones, seed=42)
    5. _lift_vs_baseline → mejora sobre baseline condicionado
    6. _mae_intratrade → máximo dolor intra-trade
    7. _costo_tarde → sensibilidad al retraso
                      │
                      ▼
arnes/estadisticas.py → provee las funciones estadísticas base
arnes/timing.py       → provee métricas de timing
arnes/estructura.py   → provee contexto de régimen
```

---

## FASE 1: LA TABLA DE OBSERVACIÓN — `quants_obs.pkl`

**Consumida por el arnés.** `arnes/datos.py` carga esta tabla y la provee a las 31 señales + evaluador.

### 2.1 Qué contiene
1,590 pivotes × 165 columnas. Cada fila = un pivote del zigzag SPY zz25. Cada columna = una medición en esa fecha exacta.

**Columnas por estación (11 × ~12 ≈ 132):**
- `{st}_val`, `_vel`, `_vol` — series crudas
- `{st}_sk` — state_key numérico (`"4__2__1"`) → D1=4, D2=2, D3=1
- `{st}_d1_bin`, `_d2_bin`, `_d3_bin` — bins individuales
- `{st}_d1_vote` — voto direccional (−1, 0, +1)
- `{st}_zz25_pbull/pbear/ev_net` — métricas del fact store
- `{st}_zk_pbull/pbear` — cinemática zigzag
- `{st}_z_d1`, `_z_d2`, `_z_d3` — z-scores continuos
- `{st}_overflow_tier_d1/2/3` — T1-T5

**Columnas derivadas (~20):**
- `d1_bear_5` — presión bearish sobre Grupo A (conteo de votos negativos / n disponibles)
- `n_stations_a` — estaciones Grupo A disponibles (2-5, documenta structural break BS3)
- `z_bear`, `z_dom` — z-scores para cascade
- `cascade_conviction`, `cascade_conviction_50` — convicción compuesta
- `duration_bars`, `daily_return_pct` — métricas de la pierna saliente
- `pivot_type` — MIN (795) / MAX (795)

**Columnas de zigzag:**
- `cascade_50`, `cascade_75` — proximidad ±3 días a zz50/zz75
- `prev_leg_return`, `abs_prev_leg_return`, `leg_bear`, `next_bear`

### 2.2 Política de medición

| Propiedad | Valor | ¿Arbitrario? |
|:----------|:------|:------------:|
| Bins D1/D2/D3 | 6/5/5 bins Gaussianos → percentiles empíricos expanding | **NO** — empírico, zero look-ahead |
| Edges estáticos | Del cal-file de producción | **NO** — derivados de la población |
| Overflow tiers | T1(3σ-4σ) T2(4σ-5σ) T3(5σ-7σ) T4(7σ-10σ) T5(≥10σ) | **NO** — escala estándar |
| Fallback de NaN | `val=NaN`, `vel=0.0`, `vol=1.0` | **NO** — defaults verificados |
| `d1_bear_5` | `count(v<0) / n_votes` | **NO** — fórmula exacta de producción |
| Estado | Builder en `backend/scripts/generators/`, tests en `backend/tests/`, determinista | |

### 2.3 Limitaciones documentadas
- BS3: 64% de pivotes con <5 estaciones Grupo A
- F4: 236 fechas duplicadas (benigno)
- 62% de FG ausente pre-2011

---

## FASE 1.5: DETECTOR DE DIAMANTES — Extracción de señales extremas desde el lake

**Paso puente entre el dato y el arnés.** Antes de definir las señales en `señales.py`, se ejecutó un barrido exploratorio sobre el lake continuo (8,453 velas) para detectar patrones extremos que luego se codificaron como señales formales.

### 1.5.1 Pipeline de extracción

```
continuous_metar_lake.parquet (8,453 × 257)
        │
        ▼
extract_overflows_vela_a_vela.py  →  13,071 overflows ≥2σ (3,354 ≥3σ)
        │                             53.7% ocurren fuera de pivotes (ENTRE)
        ▼
audit_overflow_candle_anatomy.py (V1)  →  Diamantes sin segregar MIN/MAX
        │                              Bug: mezclaba pisos y techos
        ▼
audit_overflow_candle_anatomy_v2.py (V2) → 610 combinaciones segregadas MIN/MAX/ENTRE
        │                              Tiers A/B/C + body+wick+tail+range+relvol
        ▼
Detector de régimen de crisis (detector_regimen_crisis.py) → ±3σ overflows como régimen
        │                              79 episodios de crisis en 33 años
        ▼
Auditoría de confluencia vectorial (audit_vector_confluence.py) → Panic/Euphoria Scores
        │                              ≥4 canales = WR 63.7% en pivotes, 65% en ENTRE
        ▼
SE CODIFICAN COMO SEÑALES en arnes/señales.py
```

### 1.5.2 Hallazgos que alimentaron las señales

| Hallazgo | Fuente | Se convirtió en |
|:---------|:-------|:----------------|
| VIX.d2 ≥4σ + MIN = 80% WR[+1] | anatomía V2 | Señales V2 + validación capitulacion |
| BSI.d2 2σ-3σ + MIN = 76% WR | anatomía V2 | Señales V2 + validación bsi_washed_out |
| SKEW.d3 2σ-3σ + MAX = 13% WR | anatomía V2 | Señal stealth_tail_hedging (D3 de SKEW) |
| SKEW.d1 t-1 + MIN = 80% WR | anatomía V2 | Precursor → validación panico_total |
| Confluencia ≥4 canales = 63.7% WR | confluencia | Regla operativa para el prompt maestro |
| 79 episodios de crisis ±3σ | detector régimen | Marco de validación de diamantes |
| 53.7% de overflows fuera de pivotes | extract overflows | Justificación del lake continuo |

### 1.5.3 El detector de régimen de crisis

El `detector_regimen_crisis.py` identifica **regímenes de crisis medibles** (no ventanas fijas):

- Inicia: cuando cualquier estación supera ±3σ (overflow sistémico)
- Termina: cuando el z-score cae por debajo de 2σ (deterioro) o hay transición de régimen
- Resultado: 79 episodios en 33 años, duración media 26 días, mediana 13 días
- **Útil para:** validar que los diamantes realmente ocurren en crisis y no son artefactos estadísticos

**Validación:** 11/11 disparos de `panico_total` caen dentro de episodios de crisis ±3σ. 8/10 de `skew_paranoia_exit` también. No es coincidencia — es confirmación empírica del protocolo diamante.

---

## FASE 2: LAS SEÑALES DEL ARNÉS — `arnes/señales.py` (31 definiciones)

### 2.1 Método de definición

Cada señal es una función pura: `f(df) → pd.Series(bool)`.
No hay estado global, no hay sesgo de selección, no hay parámetros ocultos.

```python
@_registrar("panico_total",
    validacion="DIAMANTE §3.3", n_min=11, dsr=None,
    tipo="entry", pivot_type="BOTH",
    descripcion="VIX y SKEW ambos en D1 extremo — pánico institucional.")
def _panico_total(df):
    vix_d1 = _get_dim(df, "vix", 0)     # D1 = bin numérico
    skew_d1 = _get_dim(df, "skew", 0)   # D1 = bin numérico
    return (vix_d1 >= 4) & (skew_d1 >= 4)
```

### 2.2 Clasificación por tipo (no arbitraria)

| Tipo | Naturaleza | Medición | Ejemplos |
|:----|:-----------|:---------|:---------|
| **ENTRY** | Favorable = subida | `first_passage(scale, blanco="MIN")` | capitulacion, pcr_put_panic, bsi_washed_out |
| **EXIT** | Favorable = caída | `first_passage(scale, blanco="MAX")` | euforia, stealth_tail_hedging |
| **BOTH** | Aplica en MIN y MAX | Se evalúa en ambas direcciones | capitulacion_v2, euforia_v2 |

**Cada señal tiene `tipo` y `pivot_type` en el decorador.** Ninguna puede ser ambigua.

### 2.3 Las 31 señales — clasificación completa

#### 🟢 NÚCLEO ROBUSTO (5) — OOS validado

| Señal | Condición (bins) | N | Edge zz75 | OOS edge | Decay |
|:------|:-----------------|:-:|:--------:|:--------:|:----:|
| `capitulacion` | VIX≥3 + BSI==0 | 57 | +3.1% | +2.64% | 0.77 |
| `pcr_put_panic` | PCR==5 | 70 | +4.5% | +2.56% | 0.63 |
| `vvix_entry` | VVIX==5 | 69 | +4.5% | +2.08% | 0.67 |
| `credit_stress` | Credit≤1 | 101 | +3.4% | +1.43% | 0.42 |
| `bsi_washed_out` | BSI==0 | 117 | +5.4% | +0.99% | 0.57 |

**Política:** OOS walk-forward anclado (10 folds, mínimo 5 años de train, 3 años de test). Ninguna señal negativa en OOS.

#### 💎 DIAMANTES §3.3 (2) — N<21, nunca degradar

| Señal | Condición | N | p_raw | CI95 CP | Contexto |
|:------|:----------|:-:|:-----:|:-------:|:---------|
| `panico_total` | VIX≥4 + SKEW≥4 | 11 | 7/7=100% | [0.59, 1.0] | 11/11 en crisis ±3σ |
| `skew_paranoia_exit` | SKEW==5 | 10 | 5/6=83% | [0.36, 0.99] | 8/10 en crisis ±3σ |

**Política:** §3.3 — p_raw + CI95 Clopper-Pearson + análisis individual (`diamantes_analisis_individual.json`). **Prohibido** degradar por N bajo. Rareza = riqueza.

#### 🟡 PROPOSED (1)

| Señal | Condición | N | Edge | p | Nota |
|:------|:----------|:-:|:---:|:-:|------|
| `cascade_reversal` | c50 < −0.957 | 240 | +0.28% fijo / +0.44% rolling | 0.25 | Edge sobrevive walk-forward pero p>0.05 |

**Política:** Calibrada con umbral congelado (cuantil p15, no recalculado = no look-ahead). Barrido de umbrales documentado en `calibracion_cascade_reversal.json`.

#### 🆕 SEÑALES V2 (3) — vectoriales D1+D2

| Señal | Condición | N | Edge zz75 | Patrón |
|:------|:----------|:-:|:--------:|:------:|
| `capitulacion_v2` | VIX≥3 + BSI==0 + BSI.D2∈{0,1} | 20 | +4.1% | CONV BULL |
| `euforia_v2` | BSI≥4 + BSI.D2≥3 | 48 | −6.1% | CONV BEAR |
| `vix_crisis_spike_v2` | VIX==5 + VIX.D2≥3 | 61 | +3.4% | CONV BULL |

**Política:** Añaden cinemática D2 sobre las señales V1 base. El D2 es `diff(3)` — velocidad de 3 días, no arbitrario.

#### ⚪ ACTIVAS SIN OOS (8)

| Señal | Condición | N | Edge | p | Nota |
|:------|:----------|:-:|:---:|:-:|------|
| `vix_crisis_spike` | VIX==5 | 121 | +3.2% | 0.08 | Cerca de significancia |
| `euforia` | VIX≤1 + BSI≠0 | 41 | −5.6% | — | Convergencia bear |
| `fg_extreme_fear` | FG==0 | 40 | +4.8% | — | Edge documentado |
| `fg_extreme_greed` | FG==5 | 29 | −4.9% | — | Edge documentado |
| `sorpresa_total` | surprise > P67 | 526 | +0.9% | 0.07 | Shannon surprise |
| `stealth_tail_hedging` | VIX≤2 + SKEW.D3≥3 | 31 | −2.4% | 0.14 | Convergencia bear |
| `sub_reaccion` | VIX≥3 + BSI≠0 | 667 | — | 1.0 | **No funciona** — edge plano |
| `dxy_bearish` | DXY==5 | 35 | — | 0.99 | **No funciona** — edge plano |

**Política:** Sin OOS pero con edge documentado. Las que no funcionan (`sub_reaccion`, `dxy_bearish`) se marcan con p≥0.99 — no se ocultan.

#### 🔴 DEGRADADAS (3)

| Señal | Condición | Causa |
|:------|:----------|:-------|
| `breadth_contraction_exit` | BSI<4 | Structural break OOS: pre-2016 −1.48%, post-2016 +1.81% |
| `credit_ease_exit` | Credit<4 | Reliquia pre-QE: +6.99% pre → −2.84% post | 
| `bsi_recovery` | BSI∈{3,4} | Edge colapsó post-2009 |

**Política:** **No eliminadas del código** — se preservan para tracking histórico. Validación del degradado documentada en `ARBOLES_DECISION.md`.

#### ⚫ RETIRADAS (9)

| Señal | Razón |
|:------|:-------|
| `credit_easing_k1` | pivot_type exclusivo (sesgo de posición) |
| `credit_stress_exit` | Duplicado exacto de credit_stress |
| `dxy_spike_exit` | Duplicado exacto de dxy_bearish |
| `pcr_panic_exit` | Duplicado exacto de pcr_put_panic |
| `vix_complacency_exit` | Duplicado exacto de euforia |
| `credit_equity_divergence` | Lift≈1.0 — no discrimina |
| `defensive_rotation_divergence` | lift<1.0 — anti-señal |
| `regime_change_exit` | lift<1.0 — anti-señal |
| `sv5t_silent_distribution` | pivot_type MAX exclusivo |

**Política:** Retiradas del ranking, preservadas en código para re-evaluación futura. No se eliminan.

---

## FASE 3: EL EVALUADOR — `evaluador_vela_a_vela.py`

### 2.1 Método: First-Passage (no arbitrario)

Para cada disparo de señal, se mide qué pasa **desde la fecha del pivote**:

```python
first_passage(prices, t0, scale=0.025/0.05/0.075, blanco="MIN"/"MAX")
```

| Propiedad | Valor | ¿Arbitrario? |
|:----------|:------|:------------:|
| Escalas | zz25 (2.5%), zz50 (5.0%), zz75 (7.5%) | **NO** — las 3 escalas del zigzag oficial |
| Blanco | MIN=ENTRY (favorable=subida), MAX=EXIT (favorable=caída) | **NO** — definido por la semántica de la señal |
| Hit definido | Primer cruce del umbral favorable vs adverso | **NO** — first-passage, no horizonte fijo |
| Baseline | Excluye pivotes donde la señal disparó | **NO** — para no contaminar el baseline con la propia señal |
| Pool de hermanas | F3 elimina señales que disparan en ±5 días calendario | **NO** — ventana fija sí, pero es calendario, no en índice (40% gap es 4x mayor) |

### 2.2 Forensia F3 (INDEP — Independencia Informacional)

Detecta si una señal es redundante con otras del mismo pool:

- `INDEP ≈ 0.0` → la señal nunca dispara sola (ej: `capitulacion` INDEP=0.0 — siempre acompañada de otras crisis)
- `INDEP ≈ 1.0` → la señal dispara completamente sola (ej: `dxy_bearish` INDEP=1.0 — señal aislada)
- **Señales con INDEP > 0.50** son informacionalmente independientes → más valiosas

**Política:** `INDEP` es métrica, no filtro. No se descartan señales por INDEP bajo — se documenta su redundancia.

### 2.3 Perfil 3D-Régimen

Cada señal se evalúa en cada celda `{escala}|{régimen}` donde régimen = dirección de la última pierna confirmada (ALZA/BAJA).

```json
{
  "zz25|ALZA": {"n": 28, "hit_rate": 0.96, "fav_neto": 3.40, ...},
  "zz25|BAJA": {"n": 0, ...},
  ...
}
```

**Política:** Cada celda reporta N, hit_rate, fav_neto, p_value, profit_factor, bars_medio, CI95. **No se promedian celdas.** Se reporta la mejor celda con N≥5.

---

## FASE 4: VALIDACIÓN OOS — `validador_oos.py`

### 3.1 Método: Walk-Forward Anclado (no arbitrario)

```python
10 folds cronológicos
Mínimo: 5 años de train
Test: ~3 años por fold
En cada fold: la mejor celda se elige SOLO con datos train (sin mirar test)
```

| Propiedad | Valor |
|:----------|:------|
| Folds | 10 |
| Mínimo train | 1,825 días (5 años) |
| Test por fold | 1,095 días (~3 años) |
| Selección | Mejor celda `escala×régimen` en train |
| Baseline | Baseline por celda (mismo régimen, misma escala, SIN la señal) |
| Veredicto | 🟢 SE REPITE OOS | 🟡 OOS positivo inestable | 🔴 OOS negativo |

### 3.2 Resultados (catálogo v7)

| Señal | IS | OOS | Decay | Folds+ | Ver |
|:------|:--:|:---:|:-----:|:------:|:--:|
| capitulacion | +3.40% | **+2.64%** | 0.77 | 2/2 | 🟢 |
| pcr_put_panic | +4.04% | **+2.56%** | 0.63 | 3/4 | 🟢 |
| vvix_entry | +3.11% | **+2.08%** | 0.67 | 2/3 | 🟢 |
| credit_stress | +3.42% | **+1.43%** | 0.42 | 3/4 | 🟢 |
| bsi_washed_out | +1.73% | **+0.99%** | 0.57 | 5/6 | 🟢 |
| breadth_contraction_exit | +0.84% | +0.17% | 0.20 | 5/10 | 🟡 → **DEGRADADA** |

**Ninguna señal del núcleo fue negativa en OOS.** La única degradada (`breadth_contraction_exit`) se degradó por structural break interno (Opus H6: pre-2016 −1.48%, post-2016 +1.81%).

---

## FASE 5: MEDICIÓN TRIÁDICA — `recompute_signals_fact_store_triad_v2.py`

### 4.1 Método: Agregación Ponderada (no Top-1)

Cada señal tiene múltiples state_keys activos. En vez de elegir el más frecuente (Top-1 bias, omitía 56% de la distribución), se usa **agregación ponderada**:

```python
E[zz25] = Σ w_i · p_bull_i / Σ w_i    # sobre todos los state_keys activos
         donde w_i = n_i (frecuencia del state_key)
```

**Política:** **No arbitrario.** El peso de cada state_key es su frecuencia empírica en el fact store.

### 4.2 Matriz multi-estación

Cada señal declara explícitamente qué estaciones la componen:

| Señal | Estación 1 | Estación 2 | Estación 3 |
|:------|:---------:|:---------:|:---------:|
| capitulacion | vix | bsi | — |
| panico_total | vix | skew | — |
| euforia | vix | bsi | — |
| stealth_tail_hedging | vix | skew | — |

**Política:** **No se omiten estaciones.** `capitulacion` mide VIX + BSI explícitamente. No se ignoran dimensiones.

### 4.3 Patrones inter-escala detectados

| Patrón | Firma | Señales que lo muestran |
|:-------|:------|:------------------------|
| **Convergencia alcista** | p_bull(zz25)≈p_bull(zz75)>0.55 | capitulacion, bsi_washed_out, vvix_entry |
| **Asimetría creciente** | EV(zz25) < EV(zz50) < EV(zz75) | capitulacion (+0.2→+0.7→+3.1%), bsi (+0.7→+2.8→+5.8%) |
| **Convergencia bajista** | p_bull(zz25≈zz75)<0.45 | euforia, bsi_recovery, stealth |
| **Divergencia (agotamiento)** | zz25 sube, zz75 baja | — no detectada en señales validadas |

---

## FASE 6: ANATOMÍA DE VELAS — `audit_overflow_candle_anatomy_v2.py`

### 5.1 Método

Para cada overflow (|z|≥2σ) en cada estación × dimensión × día:

1. Clasificar el slot temporal relativo al pivote más cercano (t-2, t-1, t=0, t+1, t+2, ENTRE)
2. Segregar por pivot_type (MIN/MAX/ENTRE)
3. Medir: WR[+1], body_when_green/red, **wick**, **tail**, **range**, **relvol**

**Política:** **No se mezclan pisos y techos** (como se hacía en V1). Cada diamante tiene pivot_type explícito.

### 5.2 Diamantes encontrados (610 combinaciones → ~40 válidos)

| Canal | σ | Slot | Pivote | N | WR[+1] | EV[+1] | Tier |
|:------|:-:|:----:|:------:|:-:|:-----:|:-----:|:----:|
| VIX.d2 | ≥4σ | t=0 | **MIN** | 30 | 80% | +1.68% | **A** |
| BSI.d2 | 2σ-3σ | t=0 | **MIN** | 53 | 76% | +0.41% | **A** |
| VIX.d1 | ≥4σ | t=0 | **MIN** | 31 | 74% | +1.73% | **A** |
| VVIX.d1 | 2σ-3σ | t=0 | **MIN** | 41 | 73% | +0.87% | **A** |
| Rotation.d1 | 2σ-3σ | t=0 | MIN | 40 | 75% | +0.92% | **A** |
| SKEW.d1 | 2σ-3σ | t-1 | MIN | 10 | 80% | +2.51% | **B** |
| SKEW.d3 | 2σ-3σ | t=0 | MAX | 30 | **13%** | — | **A** (bajista) |
| BSI.d2 | 2σ-3σ | t=0 | MAX | 34 | **29%** | — | **A** (bajista) |

### 5.3 Hallazgos clave

1. **Todos los diamantes alcistas robustos (Tier A) ocurren en pisos MIN.** Ninguno en MAX.
2. **Los diamantes bajistas se concentran en techos MAX** con WR 13-29% (muy confiables).
3. **ENTRE (101 combinaciones):** La confluencia ≥5 canales da WR 65% — funciona fuera de pivotes.
4. **Precursores (t-1, t-2):** SKEW.d1 en t-1 predice pisos MIN con 80% WR.

---

## FASE 7: POLÍTICAS DE MEDICIÓN — VERIFICACIÓN DE NO-ARBITRARIEDAD

### 6.1 Medición estocástica (no determinismo arbitrario)

| Componente | Método | ¿Estocástico/empírico? | ¿O tiene sesgo? |
|:-----------|:-------|:----------------------:|:----------------|
| Bins D1/D2/D3 | Expanding rank (percentil empírico) | ✅ Empírico (sin asumir normalidad) | Zero look-ahead bias |
| CI95 | Bootstrap 3,000 iteraciones (seed=42) | ✅ Estocástico con semilla fija | Determinista por seed |
| CI95 diamantes | Clopper-Pearson exacto | ✅ Exacto (distribución binomial) | Sin bootstrap |
| Fisher p-value | Exacto para tablas 2×2 | ✅ Exacto | Sin aproximaciones |
| Walk-forward | 10 folds temporales | ✅ Empírico (datos no vistos) | Sin data snooping |
| Deflated Sharpe | López de Prado (DSR) | ✅ Corrige múltiples comparaciones | Sin Bonferroni naive |

### 6.2 Lo que está PROHIBIDO (y se cumple)

| Práctica | ¿Se hace? | Evidencia |
|:---------|:---------:|:---------|
| Bonferroni sobre diamantes | **NO** | §3.3 explícitamente prohíbe |
| Descartar señales por N < 21 | **NO** | §3.3: rareza=riqueza, nunca degradar |
| Horizonte fijo 20d como métrica causal | **NO** | E.9 del prompt maestro lo prohíbe |
| Sesgo de posición (pivot_type filter) | **NO** — se detecta en P1 del evaluador | Señales que filtran por pivot_type se marcan |
| Shrinkage bayesiano en p_bull | Se aplica en fact stores | Documentado como conservador (p_bull shrinkage) |
| Agregar escalas fijas por señal | **NO** — lectura dinámica multi-escala | Cada señal lee zz25/zz50/zz75 simultáneamente |

### 6.3 Señales contrarias (conflictivas identificadas)

| Señal | Tipo catalogado | Tríada muestra | Implicación |
|:------|:--------------:|:-------------:|:-----------|
| `credit_easing_k1` | **entry** | CONV **BEAR** (p_bull=0.46, EV=−0.3%) | Catalogada como entry pero la tríada es bajista. Posible reclasificación necesaria. |
| `regime_change_exit` | **exit** | CONV **BULL** (p_bull=0.60, EV=+4.8%) | Catalogada como exit pero muestra convergencia alcista. Ya retirada por lift<1.0. |
| `skew_paranoia_exit` | **entry** | CONV **BEAR** (p_bull=0.45, EV=−3.6%) | Reclasificada como entry pero la tríada ponderada es bajista. N=10 — evidencia insuficiente. |

**Política:** Estas señales están identificadas y documentadas. No se ocultan. La señal conflictiva se marca con ⚠️ en el fact sheet.

---

## FASE 8: VERIFICACIÓN END-TO-END (30-Ago-2026)

### 7.1 Tests automatizados

| Suite | Tests | Estado |
|:------|:----:|:------:|
| Taxonomy integrity | 46 | ✅ 46 passed |
| Suite completa | 303 | ✅ 303 passed (51s) |

### 7.2 Compuertas de propósito

1. **`generate_quants_obs.py`** — si las 31 señales NO disparan, **no guarda el pickle**
2. **`generar_quants_obs.py`** — manifiesto de fidelidad contra referencia histórica (detector de deriva)
3. **`evaluador_vela_a_vela.py`** — P1: detecta señales con `pivot_type` en el código (sesgo de posición)

### 7.3 Trazabilidad completa

```
quants_obs.pkl (165 cols, bins numéricos)
  → 31 señales (arnes/señales.py con _get_dim)
    → evaluador_vela_a_vela.py: first-passage x3 escalas + INDEP
      → evaluacion_TABLA_NUEVA.json (perfil 3D-régimen por señal)
      → validador_oos.py: walk-forward 10 folds
        → validacion_oos_catalogo_v7.json
      → recompute_signals_fact_store_triad_v2.py: agregación ponderada
        → signals_triad_fact_sheet_v2.json
      → audit_overflow_candle_anatomy_v2.py: anatomía MIN/MAX/ENTRE
        → overflow_candle_anatomy_v2.json
```

---

## ANEXO: POLÍTICAS DE CLASIFICACIÓN — REGLAS EXPLÍCITAS

### A. Clasificación por confianza

| Tier | N | Método de validación | Bonferroni |
|:----:|:-:|:---------------------|:----------:|
| **A** | ≥30 | DSR + Walk-forward OOS + CI95 Clopper-Pearson | **NO aplica** |
| **B** | 10-29 | Exact Binomial Test + CI95 Clopper-Pearson | **NO aplica** |
| **C (diamante §3.3)** | <21 | p_raw + CI95 CP + análisis individual + contexto macro | **PROHIBIDO** |

### B. Clasificación por estado operativo

| Estado | Significado | Acción |
|:-------|:------------|:-------|
| **NÚCLEO** | OOS validado, decay < 1.0 | Operación principal con descuento 30-40% |
| **DIAMANTE** | §3.3: N<21, rareza=riqueza | Alertas de crisis, verificación de régimen |
| **PROPOSED** | Edge documentado, p>0.05 | No operar. Monitorear. |
| **ACTIVA** | Sin OOS, edge documentado | Uso condicional con cautela |
| **DEGRADADA** | Structural break confirmado | NO USAR |
| **RETIRADA** | Lift<1.0 o duplicado exacto | No rankear. Preservar para re-evaluación. |

### C. Prohibiciones explícitas

1. ❌ **NO** degradar por N bajo (Anti-patrón #7)
2. ❌ **NO** aplicar Bonferroni a señales o diamantes
3. ❌ **NO** mezclar MIN y MAX en la misma medición
4. ❌ **NO** usar horizonte fijo 20d como métrica causal
5. ❌ **NO** ocultar señales que no funcionan (se marcan con p=1.0 y punto)
6. ❌ **NO** elegir escala fija por señal (lectura dinámica obligatoria)
7. ❌ **NO** promediar celdas — reportar la mejor celda con N≥5