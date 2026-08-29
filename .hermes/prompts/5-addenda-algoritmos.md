# PROMPT — 5 Addenda para medir_senal.py + forense_precursores.py
## Enriqueciendo nuestros algoritmos con las fortalezas de fact_store_v3

**Para:** Gemini (Opus)
**De:** Hermes (deepseek/deepseek-v4-pro)
**Fecha:** 20-Ago-2026
**Prioridad:** P1
**Estado:** NUEVO

---

## 0. CONTEXTO

Esta es una auditoría cruzada entre 3 artefactos del proyecto Botero Trade. El resultado: `fact_store_v3_architecture.md` (1,054 líneas, enriquecido con 7 addenda hoy) tiene 5 fortalezas que nuestros algoritmos de medición (`medir_senal.py`, 1,183 líneas + `forense_precursores.py`, 221 líneas) NO poseen.

**Tu tarea:** Incorporar estas 5 fortalezas como addenda a nuestros algoritmos.

**Archivos de referencia — leer ANTES de escribir:**

| Archivo | Ubicación | Buscar |
|---------|-----------|--------|
| `fact_store_v3_architecture.md` | `.hermes/paraauditar/` | §6.2 (structural_momentum), §6.3 (prev_leg_domino), §8 (divergencia temporal), §15 (guía de empleo), §15.2–15.3 (árboles de decisión) **⚠️ Ver Addendum 0 para correcciones de labels D1** |
| `audit_fact_store_v3_architecture.md` | `.hermes/paraauditar/` | **🔴 OBLIGATORIO.** Auditoría del 20-Ago-2026 contra el código real. 8/11 D1 labels incorrectos en el documento. BSI usa S5TW (20d MA), no S5FI (50d). Addendums 1-7 son `[PROPUESTA]`, no implementados. Leer Secciones 1 (D1 Labels reales), 2 (BSI ticker), 6 (Addendums aspiracionales), 11 (errores menores). |
| `validacion_5_interpretaciones_fact_store.md` | `.hermes/paraauditar/` | **🔴 OBLIGATORIO.** Claude Opus validó 5 interpretaciones contra datos reales (JSON VIX + quants_obs 33 años). Corrige 3 errores graves en las reglas de decisión. Leer COMPLETO antes de implementar. |
| `medir_senal.py` | `research/01_señales_entry_exit/medir_senal.py` | Función `medir()` L640-850, `desglose_d2d3` L820-870, `main()` L1100 |
| `forense_precursores.py` | `research/04_conjuncion_multi_estacion/forense_precursores.py` | `analizar_precursores()` L27-158, `main()` L161-221 |
| `auditoria-cruzada-factstore-vs-algoritmos.md` | `.hermes/paraauditar/` | §5 — Las 5 fortalezas de fact_store_v3 que nos faltan |
| `diagnostico_prompting.md` | `.hermes/casofracaso/` | Template A (L112-131), Template B (L133-143), Template C (L145-153) |

---

## 0. ADDENDUM 0 — Correcciones Fácticas del Documento fact_store_v3 (OBLIGATORIO)

> **Fuente:** `audit_fact_store_v3_architecture.md` — Auditoría del 20-Ago-2026 contra código real.

### 0.1 D1 Labels — Usar los del GENERADOR, no los del documento

El documento `fact_store_v3_architecture.md` §4.2 tiene 8/11 tablas de D1 labels **desincronizadas** con los generadores reales. Solo VIX y VVIX coinciden al 100%. Para CUALQUIER código que compare contra `{station}_sk`, usar los labels que producen los generadores:

| Estación | Labels CORRECTOS (del generador) |
|----------|----------------------------------|
| **BSI** | `BREADTH_WASHED_OUT`, `OVERSOLD_BREADTH`, `NEUTRAL_LOW_BREADTH`, `NEUTRAL_HIGH_BREADTH`, `EXPANSIVE_BREADTH`, `HYPER_EXPANSIVE_BREADTH` |
| **F&G** | `EXTREME_FEAR`, `FEAR`, `NEUTRAL_FEAR`, `GREED`, `EXTREME_GREED`, `EUPHORIA` |
| **Credit** | `CREDIT_CRISIS`, `CREDIT_STRESS`, `ELEVATED_CREDIT_STRESS`, `STABLE_CREDIT`, `CREDIT_EASE`, `DEEP_CREDIT_EASE` |
| **Rotation** | `DEFENSIVE_CAPITULATION`, `DEFENSIVE`, `NEUTRAL_ROTATION`, `BALANCED`, `CYCLICAL_LEADERSHIP`, `AGGRESSIVE_ROTATION` |
| **PCR** | `EXTREME_CALL_HEAVY`, `BULLISH_PCR`, `NEUTRAL_PCR`, `ELEVATED_PCR`, `HIGH_PUT_PANIC`, `EXTREME_PUT_PANIC` |
| **SV5 Turb** | `QUIET_FLOW`, `LOW_TURBULENCE`, `MODERATE_TURBULENCE`, `HIGH_TURBULENCE`, `ELEVATED_TURBULENCE`, `CRISIS_TURBULENCE` |
| **SKEW** | `LOW_TAIL_RISK`, `NORMAL_TAIL_RISK`, `ELEVATED_TAIL_RISK`, `HIGH_TAIL_RISK`, `TAIL_PARANOIA`, `BLACK_SWAN_PARANOIA` |
| **Yield** | `DEEP_INVERSION`, `MODERATE_INVERSION`, `FLAT_CURVE`, `NORMAL_CURVE`, `STEEPNING_CURVE`, `EXTREME_STEEPNING` |
| **DXY** | `DEEP_DOLLAR_CRUSH`, `WEAK_DOLLAR`, `MODERATE_LOW_DOLLAR`, `MODERATE_HIGH_DOLLAR`, `ELEVATED_DOLLAR_STRESS`, `DOLLAR_SPIKE_CRISIS` |

### 0.2 BSI — Ticker correcto es S5TW, no S5FI

El documento dice S5FI (media 50 días). El generador usa **S5TW** (media 20 días, Tactical). Son indicadores diferentes con interpretaciones distintas. Usar `S5TW` en cualquier referencia a BSI.

### 0.3 Addendums 1-7 en fact_store_v3 — Estado: `[PROPUESTA - NO IMPLEMENTADO]`

Los addenda que agregamos hoy al fact_store_v3 documentan campos que NO existen en los JSONs reales. Los campos `n_wins`, `n_losses`, `mean_win`, `mean_loss`, `p5_ret`, `p95_ret`, `base_rate`, overlap matrix, cross-station aggregation, bootstrap CI95, y N_eff son **especificaciones futuras**. Cualquier código que los busque en los fact stores hoy no los encontrará. El motor `v3_fact_table_engine.py` no los genera.

### 0.4 Otras correcciones menores

- **SKEW D2/D3:** La calibración de SKEW usa datos desde 2011-02-01, no la población histórica completa
- **Confidence Tier thresholds** en field_glossary del JSON: los thresholds reales son ROBUST≥21, HIGH≥11, MODERATE≥6 (no 30/10 como dice el glossary interno)
- **Número de estaciones:** 11 (incluye DXY), no 10 como dice algún docstring
- **DXY generator:** Tiene su propia implementación (700 líneas), no usa el engine compartido `build_v3_dual_layer_fact_store()`

---

## 1. ADDENDUM 1 — Structural Momentum en medir_senal.py

### Objetivo
Agregar clasificación de momentum estructural (HH/HL/LH/LL) como filtro en la sección `desglose_d2d3` de `medir_senal.py`.

### Especificación técnica

```python
# ─── ADDENDUM 1: Structural Momentum Filter ───
# Insertar en medir_senal.py, función medir(), después de desglose_d2d3

# Para cada pivote, clasificar momentum estructural usando los campos de quants_obs:
# (Nota: estos campos ya existen en quants_obs.pkl — usarlos directamente)

rep["structural_momentum"] = {}

# Para señales de ENTRY (pivot_type == MIN): clasificar HL vs LL
if señal[pivot_type == "MIN"].sum() > 0:
    min_pivots = df[señal & (df["pivot_type"] == "MIN")]
    # HL = Higher Low → el pivote MIN actual es más alto que el MIN anterior
    hl_mask = min_pivots["prev_leg_return"].shift(1) > 0  # pierna anterior fue alcista
    n_hl = int(hl_mask.sum())
    n_ll = int((~hl_mask).sum())
    n_entry_total = n_hl + n_ll
    
    if n_entry_total > 0:
        rep["structural_momentum"]["entry"] = {
            "n_hl": n_hl, "n_ll": n_ll,
            "p_hl": round(n_hl / n_entry_total, 3),
            "mean_return_hl": round(float(min_pivots.loc[hl_mask, "prev_leg_return"].mean()), 4) if n_hl > 0 else None,
            "mean_return_ll": round(float(min_pivots.loc[~hl_mask, "prev_leg_return"].mean()), 4) if n_ll > 0 else None,
            "interpretacion": "HL = comprable (estructura alcista). LL = TRAMPA (estructura bajista)."
        }

# Para señales de EXIT (pivot_type == MAX): clasificar LH vs HH
if señal[pivot_type == "MAX"].sum() > 0:
    max_pivots = df[señal & (df["pivot_type"] == "MAX")]
    lh_mask = max_pivots["prev_leg_return"].shift(1) < 0  # pierna anterior fue bajista
    n_lh = int(lh_mask.sum())
    n_hh = int((~lh_mask).sum())
    n_exit_total = n_lh + n_hh
    
    if n_exit_total > 0:
        rep["structural_momentum"]["exit"] = {
            "n_lh": n_lh, "n_hh": n_hh,
            "p_lh": round(n_lh / n_exit_total, 3),
            "mean_return_lh": round(float(max_pivots.loc[lh_mask, "prev_leg_return"].mean()), 4) if n_lh > 0 else None,
            "mean_return_hh": round(float(max_pivots.loc[~lh_mask, "prev_leg_return"].mean()), 4) if n_hh > 0 else None,
            "interpretacion": "LH = deterioro (estructura bajista). HH = CONTINUACIÓN (estructura alcista)."
        }

# NOTA: La implementación real debe verificar qué columnas de quants_obs contienen
# structural_momentum. Si no están en quants_obs.pkl, calcularlos desde pivot_type y prev_leg_return.
```

### Criterio de aceptación
- [ ] `medir_senal.py --señal credit_easing_k1` produce `rep["structural_momentum"]["entry"]` con n_hl, n_ll, p_hl
- [ ] `medir_senal.py --señal bsi_recovery` produce `rep["structural_momentum"]["exit"]` con n_lh, n_hh, p_lh
- [ ] Una señal que solo se activa en MIN produce solo `entry`, sin `exit`
- [ ] El JSON de salida incluye `structural_momentum` como sección nueva

---

## 2. ADDENDUM 2 — Prev Leg Domino (Lookback) en medir_senal.py

### Objetivo
Agregar contexto de la pierna PREVIA: ¿venimos de un crash (>P90) o de un drift normal?

### Especificación técnica

```python
# ─── ADDENDUM 2: Prev Leg Domino ───
# Insertar en medir_senal.py, función medir(), después de structural_momentum

rep["prev_leg_context"] = {}

# Calcular distribución de |prev_leg_return| para TODOS los pivotes
abs_prev_leg = df["prev_leg_return"].abs()
p90_threshold = float(np.percentile(abs_prev_leg.dropna(), 90))

# Para pivotes donde la señal está activa, medir cuántos vinieron de pierna extrema (>P90)
prev_leg_activo = abs_prev_leg[señal].dropna()
n_extreme = int((prev_leg_activo > p90_threshold).sum())
n_normal = int((prev_leg_activo <= p90_threshold).sum())

rep["prev_leg_context"] = {
    "p90_threshold_abs_return": round(p90_threshold, 4),
    "n_extreme_prev_leg": n_extreme,
    "n_normal_prev_leg": n_normal,
    "pct_extreme": round(n_extreme / len(prev_leg_activo), 3) if len(prev_leg_activo) > 0 else 0,
    "mean_return_extreme_prev": round(float(prev_leg_activo[prev_leg_activo > p90_threshold].mean()), 4) if n_extreme > 3 else None,
    "mean_return_normal_prev": round(float(prev_leg_activo[prev_leg_activo <= p90_threshold].mean()), 4) if n_normal > 3 else None,
    "interpretacion": ">50% extreme = señal activada después de crash → edge AMPLIFICADO históricamente"
}

# Separar forward de la señal por contexto de pierna previa
if n_extreme >= 3 and n_normal >= 3:
    fwd_extreme = fwd[señal & (abs_prev_leg > p90_threshold)]
    fwd_normal = fwd[señal & (abs_prev_leg <= p90_threshold)]
    
    rep["prev_leg_context"]["forward_extreme_prev"] = {
        "n": n_extreme, "mean": round(float(fwd_extreme.mean()), 4),
        "win_rate": round(float((fwd_extreme > 0).mean()), 3)
    }
    rep["prev_leg_context"]["forward_normal_prev"] = {
        "n": n_normal, "mean": round(float(fwd_normal.mean()), 4),
        "win_rate": round(float((fwd_normal > 0).mean()), 3)
    }
```

### Criterio de aceptación
- [ ] `medir_senal.py --señal credit_easing_k1` produce `rep["prev_leg_context"]` con p90_threshold, pct_extreme
- [ ] Si n_extreme ≥ 3 Y n_normal ≥ 3, se reporta forward desglosado por contexto
- [ ] credit_easing_k1 post-crash (>P90) debería mostrar edge AMPLIFICADO vs normal
- [ ] La sección usa el MISMO forward que el resto del arnés (consistencia)

---

## 3. ADDENDUM 3 — Regímenes de Divergencia Temporal en medir_senal.py

### Objetivo
Clasificar convergencia/divergencia entre las 3 escalas zigzag. ¿El edge es convergente (las 3 escalas dicen lo mismo) o divergente (una escala contradice a las otras)?

### Especificación técnica

```python
# ─── ADDENDUM 3: Temporal Divergence Regime ───
# Insertar en medir_senal.py, función medir(), después de prev_leg_context

# Clasificar el régimen de divergencia basado en los cascade rates
c50 = rep["triada"]["cascade_50"]["rate_activa"]
c75 = rep["triada"]["cascade_75"]["rate_activa"]
zz25_wr = rep["triada"]["zz25"]["win_rate"]

rep["divergence_regime"] = {}

# Clasificación basada en cascade rates (ya calculados por la tríada)
if zz25_wr > 0.55 and c50 > 0.55 and c75 > 0.30:
    regime = "FULL_CONVERGENT_BULL"
    interpretacion = "Las 3 escalas confirman: la señal es ALCISTA en retracción, corrección y depresión."
elif zz25_wr < 0.45 and c50 < 0.45 and c75 < 0.30:
    regime = "FULL_CONVERGENT_BEAR"
    interpretacion = "Las 3 escalas confirman: la señal es BAJISTA en todas las dimensiones."
elif zz25_wr > 0.50 and c50 < 0.45:
    regime = "TACTICAL_ONLY"
    interpretacion = "La señal funciona en retracción (zz25) pero NO escala a corrección (zz50). Movimiento táctico contenido."
elif zz25_wr < 0.50 and c50 > 0.55:
    regime = "STRUCTURAL_BUILDUP"
    interpretacion = "La señal es ambigua en retracción pero SÍ escala a corrección. El mercado se está preparando para un movimiento mayor."
elif c50 > 0.55 and c75 < 0.30:
    regime = "CORRECTION_CONTAINED"
    interpretacion = "Corrección intermedia pero NO depresión. El movimiento se contiene en zz50."
else:
    regime = "MIXED_HORIZON_TRANSITION"
    interpretacion = "Las escalas no convergen — transición entre regímenes."

rep["divergence_regime"] = {
    "regime": regime,
    "interpretacion": interpretacion,
    "zz25_wr": zz25_wr,
    "cascade_50_rate": c50,
    "cascade_75_rate": c75
}
```

### Criterio de aceptación
- [ ] credit_easing_k1 (WR=93.8%, cascade_50≈77%) → `TACTICAL_ONLY` o `FULL_CONVERGENT_BULL`
- [ ] sub_reaccion (WR=50.2%, cascade bajo) → `MIXED_HORIZON_TRANSITION`
- [ ] El campo `divergence_regime` aparece en el JSON de salida
- [ ] La clasificación usa las métricas YA calculadas por la tríada (no recalcula)

---

## 4. ADDENDUM 4 — Guía de Empleo en medir_senal.py

### Objetivo
Crear un archivo `research/01_señales_entry_exit/GUIA_EMPLEO.md` que mapee cada campo del JSON de medición a la pregunta que responde y la decisión que informa. Siguiendo el formato de fact_store_v3 §15.1.

### Especificación técnica

```markdown
# GUÍA DE EMPLEO — medir_senal.py
## Mapa Dato → Pregunta → Decisión

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `activa.dist.mean` | ¿Cuál es el retorno forward medio? | Edge esperado de la señal | credit_easing: +5.19% → señal ofensiva fuerte |
| `activa.dist.p5` | ¿Cuál es el peor escenario (P5)? | Sizing máximo de posición | P5 < −10% → sizing reducido |
| `activa.wl.mean_win` | ¿Cuánto gano cuando acierto? | Target de profit | mean_win > +5% → buscar +5% de retorno |
| `activa.wl.mean_loss` | ¿Cuánto pierdo cuando fallo? | Stop loss implícito | mean_loss < −8% → stop en −8% |
| `activa.ci_mean` | ¿Es significativo el edge? | GO/NO-GO de la señal | CI95 cruza cero → NO GO |
| `triada.zz25.mean` | ¿Retorno de la pierna completa? | Retorno esperado del trade | +1.42% → trade pequeño |
| `triada.cascade_50.delta` | ¿La señal predice corrección? | ¿Mantener o salir en corrección? | delta > +20pp → mantener |
| `triada.cascade_75.delta` | ¿La señal predice depresión? | ¿La señal atrapa crashes? | delta > +30pp → excelente |
| `triada.duracion_bars.mean` | ¿Cuánto dura la pierna? | Horizonte del trade | Duración 3-5 barras → trade táctico |
| `capture_ratio.ratio` | ¿Qué fracción de la pierna capturo? | Eficiencia de entrada | Ratio > 0.3 → buena captura |
| `mae_intratrade.mean_mae` | ¿Drawdown máximo durante el trade? | Tolerancia al dolor | MAE > −8% → incómodo pero aceptable |
| `costo_tarde.mean_opp_cost` | ¿Cuánto pierdo si espero 1 barra? | Urgencia de entrada | Costo > 1% → entrar rápido |
| `anticipacion_zigzag.median_dias` | ¿Cuántos días antes se anticipa? | Ventana de preparación | Mediana 2 días → preparar con 2d de anticipación |
| `estabilidad_decada.*.wr` | ¿La señal es estable en el tiempo? | Confianza en forward test | WR consistente ±10pp → confiable |
| `desglose_d2d3.*.best.mean` | ¿Cuál es el mejor sub-estado D2/D3? | Filtro de entrada | Solo entrar si D2/D3 está en "best" |
| `structural_momentum.entry.p_hl` | ¿Pisos son HL (comprables) o LL (trampas)? | Timing de entrada | p_hl > 0.55 → entrar. p_hl < 0.45 → esperar |
| `prev_leg_context.pct_extreme` | ¿Venimos de un crash (>P90)? | Amplificación del edge | pct_extreme > 50% → edge AMPLIFICADO |
| `divergence_regime.regime` | ¿Las escalas convergen o divergen? | Convicción del trade | CONVERGENT → alta convicción. DIVERGENTE → cautela |
| `lookback_crash.*` | ¿La señal precedió crashes pasados? | Capacidad de predicción de crashes | N_lose ≥ 3 con lift > 1.5 → PRECURSOR |
```

### Criterio de aceptación
- [ ] Archivo `research/01_señales_entry_exit/GUIA_EMPLEO.md` existe
- [ ] Contiene TODOS los campos principales del JSON de medir_senal.py
- [ ] Cada fila tiene: Campo → Pregunta → Decisión → Ejemplo concreto
- [ ] Los campos nuevos (structural_momentum, prev_leg_context, divergence_regime) están incluidos
- [ ] No excede 150 líneas (referencia rápida, no enciclopedia)

---

## 5. ADDENDUM 5 — Árboles de Decisión Operacionales

### Objetivo
Crear un archivo `research/01_señales_entry_exit/ARBOLES_DECISION.md` que integre los 3 sistemas (medir_senal → forense_precursores → fact_store) en árboles de decisión concretos.

### Especificación técnica

```markdown
# ÁRBOLES DE DECISIÓN OPERACIONALES
## Integrando medición + precursores + momentum

---

## ÁRBOL A: ENTRY (Señal de Compra)

```
¿Señal ENTRY activa? (medir_senal)
│
├─ NO → Esperar. Sin señal no se opera.
│
└─ SÍ → Consultar contexto:
    │
    ├─ ¿CI95 cruza cero? → NO → ABORTAR (edge no significativo)
    │
    ├─ ¿D2 = ACCELERATING_UP_3D? (forense_precursores)
    │   └─ SÍ → El precursor universal #1 de crash está activo.
    │       → REDUCIR TAMAÑO 50%. Entrar solo si:
    │         - structural_momentum dice HL (no LL)
    │         - cascade_50_rate < 0.50 (corrección improbable)
    │
    ├─ ¿D2 = FAST_CRUSH_3D? (forense_precursores)
    │   └─ SÍ → Sign flip: el edge se INVIERTE.
    │       → NO ENTRAR. Esperar a que D2 cambie a STABLE o DECEL_DOWN.
    │
    ├─ ¿prev_leg_context.pct_extreme > 50%?
    │   └─ SÍ → Venimos de un crash (>P90 pierna previa).
    │       → Edge históricamente AMPLIFICADO post-crash.
    │       → TAMAÑO NORMAL o AUMENTADO si structural_momentum = HL.
    │
    ├─ ¿structural_momentum.entry.p_hl < 0.45?
    │   └─ SÍ → Los pisos están haciendo Lower Lows (LL).
    │       → TRAMPA BAJISTA. NO ENTRAR aunque la señal diga que sí.
    │
    ├─ ¿divergence_regime = FULL_CONVERGENT_BULL?
    │   └─ SÍ → Las 3 escalas confirman tendencia alcista.
    │       → TAMAÑO MÁXIMO. Convicción alta.
    │
    └─ ¿divergence_regime = TACTICAL_ONLY?
        └─ SÍ → La señal funciona en zz25 pero no escala.
            → TAMAÑO REDUCIDO. Trade táctico. Salir en cascade_50.
```

## ÁRBOL B: EXIT (Señal de Venta)

```
¿Señal EXIT activa? (medir_senal)
│
├─ NO → Mantener posiciones. Sin señal de salida.
│
└─ SÍ → Consultar contexto:
    │
    ├─ ¿CI95 cruza cero? → NO → ABORTAR (edge no significativo)
    │
    ├─ ¿Es euforia (edge −2.99%, WR 14.6%)?
    │   └─ SÍ → Señal de techo más fuerte del sistema.
    │       → SALIR. Cerrar 100% de la posición.
    │
    ├─ ¿Es bsi_recovery (edge −1.63%, WR 29.0%)?
    │   └─ SÍ → BSI saliendo de washed_out = fin de pierna alcista.
    │       → REDUCIR 50%. Mantener 50% hasta confirmación.
    │
    ├─ ¿Es fg_extreme_greed (edge −1.92%, WR 19.4%)?
    │   └─ SÍ → Codicia extrema.
    │       → REDUCIR 70%. FG greed es modulador de régimen, no señal pura.
    │
    ├─ ¿structural_momentum.exit.p_hh > 0.55?
    │   └─ SÍ → 🔴 Los techos están haciendo Higher Highs.
    │       → DATO FÁCTICO: HH cae 90.2% de las veces (33 años SPY, N=429).
    │       → AMPLIFICAR la señal EXIT. El mercado está en clímax de distribución.
    │       → Acción: SALIR 100% o REDUCIR AGRESIVAMENTE.
    │
    ├─ ¿structural_momentum.exit.p_lh > 0.55?
    │   └─ SÍ → Los techos están haciendo Lower Highs (deterioro visible).
    │       → La señal EXIT es CONFIRMADA pero con menos urgencia que HH.
    │       → %Cae=75.3% — señal confiable pero no extrema.
    │
    └─ ¿divergence_regime = FULL_CONVERGENT_BEAR?
        └─ SÍ → Las 3 escalas confirman tendencia bajista.
            → SALIR TODO. Convicción máxima.
```

## Tabla de Señales EXIT con Árbol

| Señal | Edge | WR | Árbol de Decisión |
|-------|------|-----|-------------------|
| euforia | −2.99% | 14.6% | SALIR 100% — techo más fuerte del sistema |
| bsi_recovery | −1.63% | 29.0% | REDUCIR 50% + verificar structural_momentum.exit |
| fg_extreme_greed | −1.92% | 19.4% | REDUCIR 70% — FG es modulador, no señal pura |
| vix_complacency_exit | PENDIENTE | PENDIENTE | PENDIENTE — medir primero |
| credit_ease_exit | PENDIENTE | PENDIENTE | PENDIENTE — medir primero |

## Tabla de Señales ENTRY con Árbol

| Señal | Edge | WR | D2 Sign Flips | Árbol de Decisión |
|-------|------|-----|---------------|-------------------|
| credit_easing_k1 | +5.19% | 93.8% | FAST_CRUSH: NO ENTRAR | Entrar solo si structural_momentum = HL |
| bsi_washed_out | +1.42% | 65.8% | D2 FAST_CRUSH: −1.74% | Entrar con D2=DECEL_DOWN (+5.17%) |
| capitulacion | +1.40% | 65.9% | D3 VOL_EXP: −0.67% | Entrar con D3=VOL_COMPR (+5.42%) |
| pcr_put_panic | +2.70% | 71.4% | D2 FAST_CRUSH: −2.19% | Entrar con D2=STABLE_CONT (+5.38%) |
```

### Criterio de aceptación
- [ ] Archivo `research/01_señales_entry_exit/ARBOLES_DECISION.md` existe
- [ ] Contiene Árbol A (ENTRY) y Árbol B (EXIT) con TODOS los pasos de decisión
- [ ] Cada rama del árbol cita la MÉTRICA exacta de medir_senal.py que la justifica
- [ ] Las 4 tablas de señales incluyen edge, WR, D2 sign flips (cuando aplica), y acción concreta
- [ ] Los árboles son OPERACIONALES: respuesta final es SALIR/REDUCIR/MANTENER/ENTRAR/NO ENTRAR con sizing
- [ ] Integra los 3 sistemas: medir_senal (medición) + forense_precursores (precursores) + fact_store_v3 (structural_momentum, prev_leg, divergencia)

---

## LÍMITES DEL SCOPE

Toda la atención se concentra exclusivamente en lo siguiente:

- ✅ **Aislar** addenda 1-3 en funciones auxiliares (`_structural_momentum_filter()`, `_prev_leg_context()`, `_divergence_regime()`) si la integración directa en `medir()` presenta conflictos de compilación
- ✅ **Proteger** `forense_precursores.py` — solo se consulta para el árbol de decisión (Addendum 5), permanece intacto
- ✅ **Respetar** `quants_obs.pkl` tal como está generado, usando sus columnas sin recalcular
- ✅ **Preservar** `fact_store_v3_architecture.md` — ya recibió 7 addenda hoy y se mantiene estable
- ✅ **Limitar** el alcance a nuevas métricas y documentación — las 28 señales registradas permanecen sin cambios
- ✅ **Conservar** la estructura `research/01_señales_entry_exit/` y `research/04_conjuncion_multi_estacion/` exactamente como existen

---

## AUTOTEST (obligatorio antes de entregar)

El agente debe responder estas 5 preguntas. Si alguna respuesta es incorrecta, DETENERSE y corregir antes de continuar.

> **NOTA 20-Ago-2026:** Claude Opus validó estas 5 interpretaciones contra el JSON real del fact store VIX + quants_obs (33 años SPY). Las respuestas correctas están CORREGIDAS con los hallazgos fácticos.

1. ¿Qué mide `structural_momentum.entry.p_hl`?
   → **CORREGIDO (⚠️ PARCIAL):** Proporción de pisos con `p_continuation > 0.5` en `up_legs` del fact store. PERO `p_continuation` y `p_bull` son ORTOGONALES (r=0.015 en VIX fact store). Un estado puede tener p_continuation=0.73 (muchos HL) pero p_bull=0.45 (el mercado cae). NO asumir que HL alto implica edge alcista alto. Son ejes independientes. Reportar ambos por separado.

2. ¿Qué significa `prev_leg_context.pct_extreme > 50%`?
   → **CORREGIDO (⚠️ INALCANZABLE):** El umbral `>50%` NUNCA se cruza en el VIX fact store (0 de 47 estados). El máximo histórico es sustancialmente inferior. Si se usa como regla de decisión, NUNCA DISPARARÁ. CORRECCIÓN: bajar el umbral a `> 20%` o `> 30%` para que sea operativo. Verificar en otras estaciones (BSI, Credit) donde los crashes son más frecuentes y el umbral puede ser distinto por estación.

3. ¿Cuál es la diferencia entre `FULL_CONVERGENT_BULL` y `TACTICAL_ONLY`?
   → **CORREGIDO (✅ CONCEPTO DERIVADO):** `FULL_CONVERGENT_BULL` y `TACTICAL_ONLY` NO son campos explícitos del fact store JSON. Son CONCEPTOS DERIVADOS que el consumer debe calcular comparando `p_bull` en las 3 escalas (zz25/zz50/zz75). El fact store almacena datos crudos por escala; la lógica de convergencia es responsabilidad del código que lo consume. El addendum 3 debe implementar esta lógica de derivación, no asumir que el campo existe.

4. ¿Decisión si D2=ACCELERATING_UP_3D y structural_momentum=LL (Lower Lows)?
   → ✅ **CONFIRMADO CORRECTO:** NO ENTRAR. Esta es la combinación más peligrosa del sistema: el vector cinemático dice "peligro acelerándose" y el vector de momentum dice "pisos cada vez más bajos". Doble confirmación de régimen bajista. Verify contra datos: en estados donde ambas condiciones coinciden, el forward return debería ser consistentemente negativo.

5. ¿Decisión si structural_momentum.exit.p_hh > 0.55 (Higher Highs en techos)?
   → 🔴 **CORREGIDO — LA RESPUESTA ORIGINAL ERA INCORRECTA Y PELIGROSA:**

   **Dato fáctico (33 años SPY, 793 techos MAX):**
   ```
   HH (Higher High): N=429 | %Cae=90.2% | Fwd=-3.26%
   LH (Lower High):  N=364 | %Cae=75.3% | Fwd=-2.91%
   ```

   Los Higher Highs caen el **90.2%** de las veces — MÁS que los Lower Highs (75.3%). Ignorar una señal EXIT porque "estamos haciendo Higher Highs" es exactamente la trampa: la inercia alcista genera confianza, y esa confianza es la liquidez de salida que usa el Smart Money para distribuir.

   **Respuesta CORRECTA:**
   ```
   SI structural_momentum.exit.p_hh > 0.55:
       → AMPLIFICAR la señal EXIT (NO ignorarla)
       → El mercado está en el clímax de distribución alcista
       → %Cae=90.2% — casi certeza de caída
       → Acción: SALIR o REDUCIR AG RESIVAMENTE
   ```

   La regla del árbol de decisión Addendum 5 DEBE CORREGIRSE para reflejar este hallazgo.

---

## VERIFICACIÓN

```bash
# 1. Ejecutar medir_senal.py con señal de prueba
cd /root/botero-trade
PYTHONPATH=/root/botero-trade .venv/bin/python \
  research/01_señales_entry_exit/medir_senal.py --señal credit_easing_k1

# 2. Verificar que el JSON contiene:
grep -l "structural_momentum" research/01_señales_entry_exit/medicion_credit_easing_k1.json
grep -l "prev_leg_context" research/01_señales_entry_exit/medicion_credit_easing_k1.json
grep -l "divergence_regime" research/01_señales_entry_exit/medicion_credit_easing_k1.json

# 3. Verificar archivos creados
ls -la research/01_señales_entry_exit/GUIA_EMPLEO.md
ls -la research/01_señales_entry_exit/ARBOLES_DECISION.md

# 4. Ejecutar forense_precursores.py (debe seguir funcionando sin cambios)
PYTHONPATH=/root/botero-trade .venv/bin/python \
  research/04_conjuncion_multi_estacion/forense_precursores.py
```

---

## ENTREGABLES

1. `research/01_señales_entry_exit/medir_senal.py` — **modificado** con 3 addenda (structural_momentum, prev_leg_context, divergence_regime)
2. `research/01_señales_entry_exit/GUIA_EMPLEO.md` — **nuevo** (Addendum 4)
3. `research/01_señales_entry_exit/ARBOLES_DECISION.md` — **nuevo** (Addendum 5)

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 20-Ago-2026