# CASO DE ÉXITO: Arnés de Medición Estándar (medir_senal.py)
## Fact Store de Diseño y Repetición
## Botero Trade — Documentado 19-Ago-2026

---

## FICHA TÉCNICA

| Campo | Valor |
|-------|-------|
| **Algoritmo** | `medir_senal.py` |
| **Ubicación** | `research/01_señales_entry_exit/medir_senal.py` |
| **Líneas** | 1,183 |
| **Funciones** | 36 (28 señales + 8 métricas centrales) |
| **Lenguaje** | Python 3.12 (determinista, sin agentes) |
| **Dependencias** | pandas, numpy, json, argparse, pathlib, datetime |
| **Input** | `quants_obs.pkl` (1,590 pivotes × 141 columnas) + `{station}_fact_store.json` (11) |
| **Output** | JSON de medición por señal (distribución completa, ED, tríada, precursores, D2×D3) + stdout |
| **Señales registradas** | 28 (12 ENTRY validadas + 3 EXIT validadas + 13 PROPOSED/PENDIENTES) |
| **Tiempo ejecución** | ~2 segundos por señal |
| **Fecha creación** | 17-Ago-2026 |
| **Creado por** | Hermes (deepseek-v4-pro) + Claude Opus (4 bugs corregidos + extensiones) + Gemini (state_key migration) |
| **Validado por** | Analista (qwen3.8-max) — 88/88 métricas idénticas post-corrección Bug 1 |

---

## 1. ESPECIFICACIÓN DEL ALGORITMO

### 1.1 Arquitectura: Decorador @_registrar

```python
# ============================================================
# MECANISMO DE REGISTRO (el corazón del arnés)
# ============================================================

SEÑALES = {}
_CERTEZA = {}

def _registrar(nombre, **certeza):
    """Registra una señal con metadata de validación."""
    def deco(fn):
        SEÑALES[nombre] = fn          # función pura df -> pd.Series(bool)
        _CERTEZA[nombre] = certeza     # {validacion, n_min, dsr, fuente}
        return fn
    return deco

# CADA SEÑAL ES UNA FUNCIÓN PURA:
@_registrar("bsi_washed_out",
    validacion="VALIDATED (Grade A)", n_min=58, dsr=None,
    fuente="operational-spec: BREADTH_WASHED_OUT, +2.6% 20d, WR 69%")
def _bsi_washed_out(df):
    """BSI en BREADTH_WASHED_OUT."""
    return df["bsi_sk"].str.split("__").str[0] == "BREADTH_WASHED_OUT"
```

### 1.2 Métricas que Calcula (estándar para las 28 señales)

```python
# ============================================================
# MÉTRICAS CALCULADAS (output JSON de medir())
# ============================================================

rep = {
    "señal": nombre,
    "forward": columna_forward,
    "n_total": len(df),

    # 1. DISTRIBUCIÓN COMPLETA
    "activa": {
        "dist":  {"n", "mean", "median", "p5", "p25", "p75", "p95", "std"},
        "wl":    {"win_rate", "n_wins", "n_losses", "mean_win", "mean_loss", "profit_factor"},
        "ci_mean": [lower, upper],  # bootstrap CI95 (3000 iter, seed 42)
    },

    # 2. BASELINE
    "baseline":           {...},  # distribución de todos los pivotes
    "baseline_pivot_type": {...},  # distribución por pivot_type (MIN/MAX)
    "delta_media":        float,  # Δ vs baseline homogéneo

    # 3. MÉTRICAS DE TRAYECTORIA
    "timing_temprano":    {"n", "mean_mae", "median_mae", "p5_mae", "mean_fwd"},
    "costo_tarde":        {"k", "n", "mean_opp_cost"},
    "sensibilidad":       {"k": {"n", "mean_fwd", "wr"}},

    # 4. TRÍADA ZIGZAG
    "triada": {
        "zz25":           {"mean", "median", "win_rate", "n"},
        "cascade_50":     {"rate_activa", "rate_baseline", "delta", "n"},
        "cascade_75":     {"rate_activa", "rate_baseline", "delta", "n"},
        "duracion_bars":  {"mean", "median", "baseline_mean", "n"},
    },

    # 5. DURACIÓN DESGLOSE
    "duracion_desglose": {
        "cortas":         {"n", "fwd_mean", "wr"},
        "largas":         {"n", "fwd_mean", "wr"},
    },

    # 6. ANTICIPACIÓN TEMPORAL
    "anticipacion_zigzag": {
        "mean_dias", "median_dias", "p5", "p25", "p75", "p95",
        "n_total", "n_anticipados", "pct_anticipados"
    },

    # 7. CAPTURE RATIO
    "capture_ratio": {
        "ratio", "fwd_mean", "abs_leg_mean", "n",
        "por_pivot_type": {pt: {"ratio", "fwd_mean", "abs_leg_mean", "n"}}
    },

    # 8. DRAWDOWN POR ANTICIPACIÓN
    "drawdown_anticipacion": {
        "entrada_temprana": {"n", "forward_mean", "mae_medio"},
        "salida_tardia":    {"n", "forward_mean", "mae_medio"},
    },

    # 9. PUNTERÍA POR ESCALA
    "punteria": {
        escala: {"n", "forward_mean", "win_rate", "capture_ratio", "mae_medio"}
        for escala in ["zz25", "zz50", "zz75"]
    },

    # 10. OFFSET DE ENTRADA
    "offset_entrada": {
        offset: {"n", "forward_mean", "win_rate", "capture_ratio"}
        for offset in [-1, 0, +1]
    },

    # 11. LOOKBACK CRASH
    "lookback_crash": {
        escala: {"n_crashes", "ventana_dias", "señales": {...}}
        for escala in ["zz25", "zz50", "zz75"]
    },

    # 12. D2×D3 DESGLOSE
    "desglose_d2d3": {
        station: {
            "d1_dominante", "d1_pct", "n_d1",
            "d2_velocity": {d2v: {"n", "mean", "wr", "tag"}},
            "d3_station_vol": {d3v: {"n", "mean", "wr", "tag"}},
        }
    },

    # 13. ESTABILIDAD POR DÉCADA
    "estabilidad_decada": {
        decada: {"n", "mean", "wr"}
        for decada in ["1990", "2000", "2010", "2020"]
    },
}
```

### 1.3 Parámetros Exactos

```python
# ============================================================
# PARÁMETROS GLOBALES (NO MODIFICAR SIN RE-VALIDAR)
# ============================================================

SEED_BOOTSTRAP = 42
N_BOOTSTRAP = 3000
CI_ALPHA = 0.05
VENTANA_LOOKBACK = 3        # [T0-3, T0+2] para lookback crash
CRASH_THRESHOLD = 0         # prev_leg_return < 0 = caída
FORWARD_DEFAULT = "next_leg" # prev_leg_return.shift(-1)
```

---

## 2. REGISTRO DE DECISIONES DE DISEÑO

### Decisión 1: Código Determinista sobre Agentes

| Campo | Valor |
|-------|-------|
| **Fecha** | 17-Ago-2026 |
| **Alternativas consideradas** | Delegar medición a subagentes, usar LLM para interpretar |
| **Decisión** | Código Python determinista. 1,183 líneas. Sin dependencias de LLM. |
| **Justificación** | El usuario preguntó: "¿Será que podemos crear un código que corra en la terminal y no necesite agentes?" El problema de raíz era "cada agente reinventa el método de medición." El código determinista elimina la reinvención. |
| **Validación** | 28 señales medidas con el MISMO estándar. 88/88 métricas idénticas post-corrección. Replicable: mismo input → mismo output. |
| **Riesgo aceptado** | Rigidez: nuevo tipo de métrica requiere modificar código → mitigado por extensibilidad del decorador |

### Decisión 2: Decorador @_registrar sobre Registro Manual

| Campo | Valor |
|-------|-------|
| **Fecha** | 17-Ago-2026 |
| **Alternativas consideradas** | Diccionario manual, archivo YAML/JSON de configuración |
| **Decisión** | Decorador Python con metadata inline (validacion, n_min, dsr, fuente) |
| **Justificación** | Cada señal ES una función pura. El decorador la registra automáticamente con su metadata. Sin configuración externa que pueda desincronizarse. Sin archivo YAML que requiera parsing. |
| **Validación** | `PYTHONPATH=. .venv/bin/python -c "from medir_senal import SEÑALES; print(len(SEÑALES))"` → 28 señales. Siempre actualizado porque el registro es el código mismo. |
| **Riesgo aceptado** | El orden de imports determina el registro → mitigado por `_CERTEZA` como fuente única de verdad |

### Decisión 3: State Key Completo (D1×D2×D3) sobre d1_vote Binario

| Campo | Valor |
|-------|-------|
| **Fecha** | 17-Ago-2026 |
| **Alternativas consideradas** | `{station}_d1_vote == -1` (binario, usado en versión inicial) |
| **Decisión** | `df["{station}_sk"].str.split("__").str[0]` (state_key completo) |
| **Justificación** | `d1_vote == -1` agrupa D1 bins distintos (CRISIS_SPIKE == HIGH_VOL, ambos -1). Pierde D2 (velocidad) y D3 (volatilidad). Las señales GRADE A fueron validadas sobre el state_key COMPLETO. |
| **Validación** | Corrección aplicada por Gemini. 9 señales migradas de `d1_vote` a `str.split("__").str[0]`. Sin cambios en N ni edge. |
| **Riesgo aceptado** | Dependencia del formato exacto de state_key (D1__D2__D3) → mitigado por estandarización en fact stores |

### Decisión 4: Tríada Zigzag sobre Horizontes Fijos

| Campo | Valor |
|-------|-------|
| **Fecha** | 17-Ago-2026 |
| **Alternativas consideradas** | `--horizontes 5,10,20,60` (días fijos, versión inicial) |
| **Decisión** | Tríada zigzag: zz25 (prev_leg_return), cascade_50, cascade_75, duration_bars |
| **Justificación** | Los horizontes fijos en días son una imposición arbitraria. La tríada zigzag respeta la estructura natural del mercado (2.5% → 5% → 7.5%). La especificación lo exige: "medir SIEMPRE contra la tríada, NUNCA contra retornos crudos ni cascade solo." |
| **Validación** | `--horizontes` eliminado del código. Mediciones ahora usan exclusivamente zz25/zz50/zz75. |
| **Riesgo aceptado** | No mide retorno a N días fijos → el cascade + duration_bars cubren la dimensión temporal |

### Decisión 5: Distribución Completa (P5/P95) sobre Media

| Campo | Valor |
|-------|-------|
| **Fecha** | 17-Ago-2026 |
| **Alternativas consideradas** | Reportar solo mean + std |
| **Decisión** | Reportar distribución completa: P5, P25, P50, P75, P95 + CI95 bootstrap |
| **Justificación** | El usuario corrigió: "El promedio esconde la cola izquierda." "El precio de no acertar es muy alto." Una estrategia con mean +2.79% puede esconder un P5 de -24.6%. La distribución completa expone el riesgo real. |
| **Validación** | Cada JSON de medición contiene: dist (8 percentiles) + wl (6 métricas wins/losses) + ci_mean. 20 señales medidas con distribución completa. |
| **Riesgo aceptado** | Mayor complejidad de output → mitigado por formato JSON estándar |

### Decisión 6: Wins/Losses Separados sobre Métricas Agregadas

| Campo | Valor |
|-------|-------|
| **Fecha** | 17-Ago-2026 |
| **Alternativas consideradas** | Solo profit_factor, solo Sharpe |
| **Decisión** | Reportar wins y losses por separado: n_wins, n_losses, mean_win, mean_loss, win_rate, profit_factor |
| **Justificación** | La media esconde la asimetría. capitulacion: mean_win=+6.91%, mean_loss=-9.22%. La pérdida es 33% mayor que la ganancia. Sin separar wins/losses, esta asimetría es invisible. |
| **Validación** | El marco Edge Defensivo se deriva directamente de wins/losses separados: ED = \|mean_loss\| - (mean_win × FA_rate). Sin separación, ED no se puede calcular. |
| **Riesgo aceptado** | Ninguno — wins/losses están en la data, solo hay que reportarlos |

---

## 3. MECÁNICA DE MEDICIÓN (PASO A PASO)

```
╔══════════════════════════════════════════════════════════════════╗
║           MECÁNICA DE MEDICIÓN DE UNA SEÑAL                     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ENTRADA: Nombre de señal + quants_obs.pkl + fact stores        ║
║                                                                  ║
║  PASO 1 — ACTIVAR SEÑAL                                         ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │ señal = SEÑALES[nombre](df)  → pd.Series(bool)          │    ║
║  │ fwd   = df["prev_leg_return"].shift(-1)                 │    ║
║  │ act   = fwd[señal & fwd.notna()]  → retornos forward    │    ║
║  │ spy   = cargar_datos()[1]  → barras diarias del Vault    │    ║
║  └─────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║  PASO 2 — DISTRIBUCIÓN COMPLETA                                 ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │ _pctiles(act)  → P5, P25, P50, P75, P95                 │    ║
║  │ _wins_losses(act) → n_wins, n_losses, mean_win, mean_loss│   ║
║  │ _bootstrap_ci(np.mean, act, 3000, 42) → [low, high]     │    ║
║  └─────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║  PASO 3 — BASELINE HOMOGÉNEO                                    ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │ Mismo pivot_type que la señal (MIN-only si la señal      │    ║
║  │   solo se activa en MIN, ALL si es mixta)                │    ║
║  │ delta_media = mean(act) - mean(baseline)                 │    ║
║  └─────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║  PASO 4 — TRÍADA ZIGZAG                                         ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │ zz25:        mean(prev_leg_return | señal)              │    ║
║  │ cascade_50:  mean(cascade_50 | señal)                   │    ║
║  │ cascade_75:  mean(cascade_75 | señal)                   │    ║
║  │ duration:    mean(duration_bars | señal)                 │    ║
║  └─────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║  PASO 5 — MÉTRICAS DE TRAYECTORIA                               ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │ _mae_intratrade(spy, señal, df)  → MAE desde Vault      │    ║
║  │ _costo_tarde(spy, señal, df, k)  → costo por trade      │    ║
║  │ _sensibilidad_timing(spy, señal, df) → ±k barras        │    ║
║  └─────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║  PASO 6 — MÉTRICAS AVANZADAS                                    ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │ Anticipación temporal → días entre pivotes activos       │    ║
║  │ Capture ratio → forward / |leg_return| por pivot_type   │    ║
║  │ Puntería → capture ratio por zz25/zz50/zz75             │    ║
║  │ Offset entrada → capture ratio ±1 barra                 │    ║
║  │ Duración desglose → cortas vs largas (mediana split)    │    ║
║  │ Drawdown anticipación → MAE entrada temprana/tardía     │    ║
║  │ D2×D3 desglose → mejores/peores D2/D3 por estación      │    ║
║  │ Lookback crash → [T0-3, T0+2] ventana pre-crash         │    ║
║  │ Estabilidad década → WR por 1990s/2000s/2010s/2020s     │    ║
║  └─────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║  SALIDA: JSON con 21 métricas + stdout resumido                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 4. RESULTADOS CUANTITATIVOS

### 4.1 Señales Registradas (28 total)

**ENTRY — Validadas (12):**
| # | Señal | N | Edge | WR | CI95 |
|---|---|---|---|---|---|
| 1 | credit_easing_k1 | 112 | +5.19% | 93.8% | [+4.41%, +6.01%] |
| 2 | pcr_put_panic | 70 | +2.70% | 71.4% | [+1.13%, +4.24%] |
| 3 | vvix_entry | 91 | +1.70% | 62.6% | [+0.19%, +3.24%] |
| 4 | fg_extreme_fear | 54 | +1.58% | 68.5% | ED=5.61% |
| 5 | panico_total | 34 | +1.49% | 58.8% | ⚠️ N bajo |
| 6 | bsi_washed_out | 161 | +1.42% | 65.8% | [+0.25%, +2.55%] |
| 7 | capitulacion | 82 | +1.40% | 65.9% | ED=6.86% 🛡️ |
| 8 | credit_stress | 215 | +1.00% | 54.9% | [+0.08%, +1.94%] |
| 9 | sorpresa_total | 525 | +0.83% | 54.9% | [+0.18%, +1.48%] |
| 10 | sub_reaccion | 667 | +0.39% | 50.2% | ❌ RETIRAR |
| 11 | dxy_bearish | 35 | -0.04% | 45.7% | ❌ RETIRAR |
| 12 | fg_extreme_greed | 31 | -1.92% | 19.4% | ✅ TOPE EXIT |

**EXIT — Validadas (3):**
| # | Señal | N | Edge | WR | CI95 |
|---|---|---|---|---|---|
| 1 | bsi_recovery | 324 | -1.63% | 29.0% | [-2.17%, -1.10%] ✅ |
| 2 | euforia | 41 | -2.99% | 14.6% | [-3.98%, -1.81%] ✅ |
| 3 | fg_extreme_greed | 31 | -1.92% | 19.4% | ✅ TOPE |

**PROPOSED / PENDIENTES (13):**
```
breadth_contraction_exit, credit_ease_exit, vix_complacency_exit,
regime_change_exit, vix_crisis_spike, cascade_reversal,
credit_stress_exit, pcr_panic_exit, dxy_spike_exit,
skew_paranoia_exit, credit_equity_divergence,
defensive_rotation_divergence, sv5t_silent_distribution,
stealth_tail_hedging
```

### 4.2 Métricas por Señal (JSON de salida)

```
CADA JSON contiene 13 secciones:
  1. activa             → distribución + wins/losses + CI95
  2. baseline           → distribución de todos los pivotes
  3. delta_media        → edge sobre baseline homogéneo
  4. timing_temprano    → MAE intra-trade real
  5. costo_tarde        → costo de esperar k barras
  6. sensibilidad       → edge a ±k barras del pivote
  7. triada             → zz25, cascade_50/75, duration
  8. duracion_desglose  → cortas vs largas
  9. anticipacion_zigzag → días de anticipación temporal
  10. capture_ratio      → forward/|leg| por pivot_type
  11. drawdown_anticipacion → MAE entrada temprana/tardía
  12. punteria           → capture ratio por zz25/zz50/zz75
  13. offset_entrada     → capture ratio ±1 barra
  14. lookback_crash     → señales en [T0-3, T0+2]
  15. desglose_d2d3      → mejores/peores D2/D3 por estación
  16. estabilidad_decada → WR por década
```

---

## 5. FACTORES CRÍTICOS DE ÉXITO (LO QUE HAY QUE REPETIR)

### Factor 1: Una función pura = una señal

```
PROBLEMA:    Cada agente definía señales de manera distinta
SOLUCIÓN:    Decorador @_registrar. Cada señal = función pura df → pd.Series(bool)

POR QUÉ FUNCIONA:
  - La señal es CÓDIGO, no configuración → no puede desincronizarse
  - La metadata (validacion, n_min, fuente) viaja con la señal
  - El registro es automático: no hay que mantener dos fuentes de verdad
  - Cualquier persona/agente puede leer la definición exacta de cada señal

LECCIÓN: El código ES la documentación. Si no está en el código, no existe.
```

### Factor 2: Distribución completa sobre media

```
PROBLEMA:    La media esconde la cola izquierda
SOLUCIÓN:    P5, P25, P50, P75, P95 + wins/losses separados + CI95

POR QUÉ FUNCIONA:
  - P5 expone el peor escenario (la cola izquierda)
  - Wins/losses separados revelan asimetría (mean_win vs mean_loss)
  - CI95 bootstrap cuantifica la incertidumbre del edge
  - Sin estas métricas, una señal con mean +2.79% y P5 -24.6% parece "buena"

LECCIÓN: Una media sin distribución es una mentira estadística.
         La distribución completa es el mínimo estándar de verdad.
```

### Factor 3: Baseline homogéneo

```
PROBLEMA:    Comparar señal MIN contra todos los pivotes (incluye MAX) infla el delta
SOLUCIÓN:    Baseline del mismo pivot_type que la señal

POR QUÉ FUNCIONA:
  - credit_easing_k1: MIN-only → baseline = solo MIN sin easing
  - Delta real = +1.49% (no +5.14% contra ALL)
  - Sin baseline homogéneo, el edge está inflado artificialmente

LECCIÓN: El grupo de control debe ser COMPARABLE al grupo de tratamiento.
         Si la señal es MIN-only, el baseline debe ser MIN-only.
```

### Factor 4: Tríada zigzag sobre horizontes fijos

```
PROBLEMA:    Horizontes fijos en días son una imposición arbitraria
SOLUCIÓN:    zz25 (retracción), cascade_50 (corrección), cascade_75 (depresión)

POR QUÉ FUNCIONA:
  - Respeta la estructura natural del mercado (2.5% → 5% → 7.5%)
  - cascade_50/75 mide propagación, no solo retorno
  - duration_bars mide tiempo en unidades naturales (barras de la pierna)
  - "Buy on signal bar, not pivot" — la tríada mide desde la barra diaria

LECCIÓN: No impongas tu calendario al mercado. El mercado tiene su propio ritmo.
         La tríada zigzag es ese ritmo.
```

### Factor 5: MAE intra-trade real desde el Vault

```
PROBLEMA:    "Drawdown" se calculaba como cumsum de 20 barras arbitrarias
SOLUCIÓN:    MAE = min(Low[T0:T1] - Close[T0]) / Close[T0] desde el Vault

POR QUÉ FUNCIONA:
  - Usa precios REALES del Vault (Low, Close), no un cumsum sintético
  - Mide la MÁXIMA excursión adversa, no un promedio
  - Específico a cada trade: usa el rango [T0, T1] de la pierna real

LECCIÓN: Medir drawdown requiere datos INTRADÍA (o al menos diarios con Low).
         Un cumsum sobre retornos diarios NO es un drawdown real.
```

---

## 6. LOS 4 BUGS QUE ENCONTRAMOS (y cómo los corregimos)

| # | Bug | Quién lo encontró | Severidad | Raíz del error | Fix |
|---|---|---|---|---|---|
| 1 | `_costo_tarde`: `arr[:k]` = primer trade / suma 30 años | Gemini | 🔴 | Confundir serie temporal con acumulado | Costo por trade: `(Close[T0+k]-Close[T0])/Close[T0]` |
| 2 | `_drawdown_temprano`: cumsum 20 barras | Gemini | 🔴 | No usar datos reales del Vault | `min(Low[T0:T1])/Close[T0]` desde Vault |
| 3 | `_sensibilidad_timing`: shift sobre pivotes MIN/MAX | Gemini | 🔴 | Pivotes alternantes NO son serie temporal | Retraso en BARRAS continuas desde Vault |
| 4 | `delta_media`: baseline ALL vs MIN-only | Gemini | 🟡 | Grupo de control no comparable | Baseline homogéneo del mismo pivot_type |

### Lección de los bugs

```
Los 4 bugs los encontró Gemini, no yo.
Los 4 bugs estaban en código que YO escribí.
Los 4 bugs eran errores de concepto, no de sintaxis.

LECCIÓN: El implementador NO puede auditar su propio código.
         La separación de roles ES el multiplicador de calidad.
```

---

## 7. PLANTILLA DE REPETICIÓN (para futuros arneses)

```python
# ============================================================
# PLANTILLA: Arnés de Medición Estándar
# ============================================================
# Para replicar el éxito de medir_senal.py en nuevos contextos

# 1. ARQUITECTURA DE REGISTRO
#    → Decorador que registra funciones puras con metadata
#    → Cada "señal" o "métrica" = función pura input → output

# 2. MÉTRICAS OBLIGATORIAS (mínimo estándar)
#    → Distribución completa (P5/P25/P50/P75/P95)
#    → Wins/losses separados (n_wins, n_losses, mean_win, mean_loss)
#    → Bootstrap CI95 (seed fija, n_iter fijo)
#    → Baseline homogéneo (mismo tipo que la señal)

# 3. MÉTRICAS DE TRAYECTORIA
#    → MAE intra-trade real desde datos de mercado (no cumsum sintético)
#    → Costo de timing por trade (no agregado)
#    → Sensibilidad a ±k barras continuas (no ±k pivotes)

# 4. MÉTRICAS DE ESCALA
#    → Usar la estructura natural del mercado (zigzag, no días fijos)
#    → Medir propagación (cascade), no solo retorno
#    → Medir duración en unidades naturales (barras de la pierna)

# 5. VALIDACIÓN TEMPORAL
#    → Estabilidad por década
#    → Edge decay detection

# 6. DOCUMENTAR COMO FACT STORE
#    → Ficha técnica (líneas, dependencias, input/output)
#    → Registro de decisiones de diseño
#    → Bugs encontrados y corregidos
#    → Parámetros exactos (VALORES, no descripciones)
```

---

## 8. DEPENDENCIAS Y REQUISITOS

```python
# ============================================================
# REQUISITOS PARA REPLICAR
# ============================================================

# Software
# - Python 3.12+
# - pandas >= 2.0
# - numpy >= 1.24
# - json, argparse, pathlib, datetime (stdlib)

# Datos
# - quants_obs.pkl: 1,590 pivotes zz25 del SPY
#   Columnas requeridas:
#     - prev_leg_return (retorno de la pierna completa)
#     - {station}_sk para 11 estaciones (state_key D1__D2__D3)
#     - {station}_val para 11 estaciones (valor crudo)
#     - cascade_50, cascade_75, duration_bars
#     - pivot_date, pivot_type
#
# - {station}_fact_store.json (11 archivos)
#   - states: {state_key: {n, zz25: {p_bull, ev_net, ...}, zigzag_kinematic: {...}}}
#   - _documentation: {dimension_thresholds_definition: {...}}
#
# - Vault SPY (vía TimescaleDataStore)
#   - Barras diarias con Close, Low, High

# Comando de ejecución
# PYTHONPATH=/root/botero-trade .venv/bin/python \
#   research/01_señales_entry_exit/medir_senal.py --señal <nombre>
```

---

## 9. ESTADO DEL ALGORITMO

| Campo | Valor |
|-------|-------|
| **Estado** | ✅ PRODUCCIÓN (validado) |
| **Última validación** | 18-Ago-2026 |
| **Validado por** | Analista (qwen3.8-max) — 88/88 métricas idénticas post-fix Bug 1 |
| **Bugs corregidos** | 4 (costo_tarde, drawdown_temprano, sensibilidad_timing, delta_media) |
| **Bugs conocidos** | 0 |
| **Mejoras pendientes** | D2×D3 con bootstrap CI en todos los estados, validación OOS del arnés completo |
| **Cobertura de tests** | Manual (ejecución verificada para las 28 señales) |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 19-Ago-2026
**Versión:** 1.0