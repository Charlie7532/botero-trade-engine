# Auditoría del Ejercicio de Señales EXIT — Código y Metodología

**Fecha:** 19-Ago-2026 · **Auditor:** Gemini (Opus) · **Objeto:** [`medir_senal.py`](file:///root/botero-trade/research/01_señales_entry_exit/medir_senal.py) + análisis ad-hoc

---

## 1. Calidad del Código de Hermes (Score: 8.5/10)

### ✅ Lo que está bien hecho

| Aspecto | Evaluación |
|---|---|
| **Registro determinista** (`@_registrar` con metadata) | Excelente. Cada señal lleva `validacion`, `n_min`, `dsr`, `fuente`. Reproducible. |
| **Bootstrap CI95** con seed fija | Correcto. `np.random.default_rng(seed)` garantiza reproducibilidad. |
| **Baseline condicionado** por `pivot_type` (L591-598) | Diseño inteligente: evita mezclar piernas alcistas con bajistas en la referencia. |
| **13 métricas por señal** (dist, WL, CI, MAE, timing, tríada, anticipación, capture, puntería, offset, lookback, D2×D3, década) | Harness institucional serio. No le falta nada al reporte individual. |
| **Pre-vectorización de masks** en lookback crash (L931-937) | Corregido: todas las señales se pre-computan una sola vez antes del bucle. |
| **Separación de wins/losses** con profit factor | Correcto: `_wins_losses()` calcula gross_win / gross_loss, no promedio simple. |

### ⚠️ Problemas de Ingeniería Detectados

#### P1: Mezcla de `RandomState` y `default_rng` (INCONSISTENCIA)

```python
# L463: Bootstrap CI usa el RNG moderno (correcto)
rng = np.random.default_rng(seed)

# L824, L852: D2×D3 CI usa el RNG legacy (inconsistente)
rng = np.random.RandomState(seed)
```

**Impacto:** Bajo (ambos son deterministas con seed fija), pero es una inconsistencia que debería unificarse en `default_rng` para todo el archivo.

#### P2: Import dentro de función (`datetime` en L923)

```python
# L923 — import dentro de medir(), se ejecuta en cada llamada
import datetime as _dt
```

**Recomendación:** Mover al bloque de imports global (L22-29).

#### P3: Ruta redundante de OBS_PKL (L33-35)

```python
OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"
if not OBS_PKL.exists():
    OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"  # ← Misma ruta
```

**Impacto:** Código muerto. El `if` nunca cambia nada. Probablemente era un fallback que se copió mal.

#### P4: Nombre de paquete con caracteres especiales

El directorio `research/01_señales_entry_exit/` contiene `01_` (número al inicio) y `ñ`. Esto impide importación Python estándar con `from research.01_señales_entry_exit import...` — requiere `importlib.util`. No es bloqueante para uso como script CLI, pero dificulta integración futura en tests.

---

## 2. Puntos Ciegos Metodológicos (Lo Crítico)

### 🔴 PUNTO CIEGO 1: El 16.6% de pivotes MAX tienen `next_leg > 0`

```
MAX PIVOTS BREAKDOWN:
  Total MAX: 795
  Next leg DOWN (correct zigzag): 662 (83.3%)
  Next leg UP (zigzag artifact):  132 (16.6%)   ← ¡No son techos reales!
```

**¿Qué significa?** El ZigZag de 2.5% a veces marca un MAX que es seguido por otro MAX más alto (porque la caída intermedia fue < 2.5%). Esos 132 pivotes MAX son **techos falsos del ZigZag**, no techos de mercado.

**Impacto en nuestro ejercicio:**
- Cuando medimos señales de EXIT en pivotes MAX, el 16.6% de ellos NO preceden una caída real. Esto **diluye** el edge medido.
- Señales como `credit_equity_divergence` que reportan WR 14.2% (alcista) = 85.8% de acierto en caídas, en realidad están midiendo contra un baseline que incluye esos 132 MAX→UP.
- **El edge REAL de las señales es probablemente aún mejor** de lo que medimos, porque estamos penalizándolas con falsos techos.

**Recomendación:** Separar el análisis en (a) MAX→DOWN (techos reales, $N=662$) y (b) MAX→UP (falsos techos, $N=132$). Verificar si las señales tienen poder predictivo para distinguir entre ambos.

---

### 🔴 PUNTO CIEGO 2: Las señales `bsi_recovery` y `stealth_tail_hedging` disparan en MIN

```
SIGNAL CONTAMINATION ON MIN PIVOTS:
  bsi_recovery                : N=324 | on MAX: 229 (71%) | on MIN: 95 (29%)
  stealth_tail_hedging        : N=31  | on MAX: 20  (65%) | on MIN: 11 (35%)
  euforia                     : N=41  | on MAX: 35  (85%) | on MIN:  6 (15%)
  vix_complacency_exit        : N=41  | on MAX: 35  (85%) | on MIN:  6 (15%)
```

**¿Qué significa?** `bsi_recovery` no filtra por `pivot_type == "MAX"`. Dispara en 95 pisos (MIN) donde la señal es irrelevante como EXIT (estás en un piso, no en un techo). Esos 95 casos diluyen el edge de la señal.

- `stealth_tail_hedging` tampoco filtra por MAX → el 35% de sus activaciones son en pisos, donde VIX bajo + SKEW alto puede significar "complacencia antes de rebote", no "techo".
- Las 3 señales nuevas que **yo** añadí (`credit_equity_divergence`, `defensive_rotation_divergence`, `sv5t_silent_distribution`) SÍ filtran correctamente por `is_max = df["pivot_type"] == "MAX"` → 100% en MAX, 0% en MIN. ✅

**Impacto:** El edge de `bsi_recovery` ($-1.63\%$, WR 29%) está **contaminado** por 95 activaciones en MIN que probablemente tienen retorno positivo (el mercado sube desde un piso). El edge real de `bsi_recovery` en SOLO techos es probablemente **más negativo** (mejor como EXIT).

**Recomendación:** Medir `bsi_recovery` filtrado SOLO en MAX para obtener el edge limpio.

---

### 🔴 PUNTO CIEGO 3: Cobertura temporal parcial — 3 estaciones NO existen antes del 2000

```
NaN COVERAGE POR DÉCADA:
  fg (Fear & Greed)     : 100% NaN en 1990s, 100% NaN en 2000s (solo existe desde ~2011)
  credit (HYG/LQD)      : 100% NaN en 1990s, 57% NaN en 2000s (solo completo desde ~2007)
  pcr (Put/Call Ratio)   : 100% NaN en 1990s, 57% NaN en 2000s
  vvix                   : 100% NaN en 1990s, 56% NaN en 2000s
  sv5_turbulence         : 77% NaN en 1990s (solo desde ~1999)
  rotation               : 75% NaN en 1990s
```

**¿Qué significa?** La señal `credit_equity_divergence` (EXIT GRADO A, $N=120$) **no puede activarse** en ningún pivote antes del 2007 porque `credit_sk` es NaN. Esto tiene consecuencias:

1. **El N=120 no cubre los techos de los 1990s** (burbuja dotcom, LTCM). Esos techos están en la categoría "no detectadas".
2. **La "cobertura del 73.4%"** del Sistema Protector Total V2 es optimista para la era 1993-2006, donde solo VIX, BSI, SKEW, y yield_curve tienen datos.
3. **Fear & Greed** (`fg_extreme_greed`) solo cubre 2011-2026 (15 años de 33). Su $N=31$ es representativo solo de la era post-GFC.

**Recomendación:** Segmentar la cobertura del sistema por era:
- **Era Pre-Crédito (1993-2006):** Solo VIX + BSI + SKEW + Yield Curve → ¿cuánto cubren?
- **Era Completa (2007-2026):** Todas las estaciones → ¿cuánto cubren?

---

### 🟡 PUNTO CIEGO 4: No medimos la VELOCIDAD de deterioro (cuánto cae antes de que podamos salir)

El ejercicio de timing mide **si** la señal estaba activa en la ventana $[-5d, +5d]$, pero NO mide:

1. **¿Cuánto cayó el SPY entre $T_0$ (techo real) y el día en que la señal se activa?** Si la señal se activa en $T_0 + 2$ pero el SPY ya cayó -3.5%, el valor operativo es limitado.
2. **¿Cuál es el MAE intra-día entre la activación y la ejecución real?** Incluso con señal a $T_0$, el mercado puede haber abierto con gap down.

**Impacto:** Hay una diferencia entre "detección" y "acción ejecutable". El histograma de offsets muestra distribución bastante uniforme entre $-5d$ y $+5d$ (fuera de $T_0$), lo que sugiere que muchas detecciones en la ventana son **coincidencia**, no causalidad.

---

### 🟡 PUNTO CIEGO 5: No hay test de Correlación Temporal / Clustering de señales

Las señales de techo tienden a **agruparse** en los mismos eventos macro (2000, 2007-08, 2020, 2022). Si 50 de los 120 disparos de `credit_equity_divergence` ocurrieron en los 6 meses alrededor de la GFC, la muestra efectiva no es $N=120$ sino $N \approx 15\text{-}20$ "eventos independientes".

**Recomendación:** Calcular el **Deflated Sharpe Ratio** o aplicar **PurgedKFold** temporal (ya lo tienen como infraestructura) a las señales EXIT, no solo a las ENTRY.

---

### 🟡 PUNTO CIEGO 6: No hay medición de la URGENCIA de la señal

Hay señales que se activan **días antes** del techo (anticipación) y otras que se activan **el mismo día**. Operativamente, estas requieren respuestas diferentes:

- **Anticipación 3-5d:** Tiempo para reducir posición gradualmente (TRIM 25%-33%).
- **En punto $T_0$:** Salida táctica completa.
- **Post-techo $T_0+1$ a $+2$:** Salida de emergencia con micro-drawdown.

El sistema actual trata a todas como equivalentes.

---

## 3. Lo que Falta y Deberíamos Incluir

### A. Señales Faltantes (Estaciones no explotadas para EXIT)

| Estación | EXIT por Silencio/Contradicción | Status |
|---|---|---|
| **Yield Curve** (0.1% NaN, 33 años!) | Inversión de curva + velocidad D2 negativa en techo MAX. Históricamente precede recesiones y bear markets por 12-18 meses. | ❌ **No medida** |
| **VVIX** (D1 = LOW_VVIX en techo) | Complacencia en la volatilidad de la volatilidad. Cuando ni siquiera los creadores de mercado compran cobertura. | ❌ **No medida** |
| **DXY** (Fortaleza del dólar en techo) | Capital fluyendo a refugio (USD) mientras equity está en máximos. Divergencia clásica. | ❌ **No medida** |

> [!IMPORTANT]
> La **curva de rendimientos** (`yield_curve_sk`) tiene solo 0.1% de NaN — cubre los 33 años completos. Es la estación con mejor cobertura histórica y la más probada como predictor de recesiones. No haberla incluido como señal EXIT es el punto ciego más grande.

### B. Mediciones Pendientes Críticas

1. **`bsi_recovery` filtrado SOLO en MAX:** Recalcular edge sin la contaminación de los 95 disparos en MIN.
2. **Cobertura por era:** ¿Cuánto cubre el sistema en la era 1993-2006 vs 2007-2026?
3. **Clustering temporal:** ¿Cuántos eventos macro independientes cubren los $N=120$ de `credit_equity_divergence`?
4. **Señal combinada Yield Curve + Crédito:** La inversión de curva + deterioro de crédito es la combinación más poderosa históricamente para anticipar bear markets.

---

## 4. Resumen Ejecutivo

| Dimensión | Score | Comentario |
|---|:---:|---|
| **Calidad del harness (`medir_senal.py`)** | **8.5/10** | Profesional e institucional. 13 métricas completas. Bugs menores (RandomState inconsistente, import inline, path redundante). |
| **Rigor de las nuevas señales de techo** | **9.0/10** | Las 3 señales GRADO A son sólidas: filtran por MAX, baja correlación mutua (ρ < 0.25), CI95 no cruzan cero. |
| **Completitud del ejercicio** | **7.0/10** | Falta segmentar por era, medir yield curve como EXIT, limpiar contaminación de `bsi_recovery` en MIN, y verificar clustering temporal. |
| **Interpretación del resultado de cobertura** | **7.5/10** | El "73.4% de detección" es optimista: incluye la era 2007+ donde credit/FG existen, y no mide si la detección es accionable (drawdown ya sufrido antes de la señal). |

> [!WARNING]
> **La métrica de cobertura más honesta** debería ser: *"De las caídas en la era 2007-2026 (donde todas las estaciones existen), ¿cuántas detectamos?"* — y por separado — *"De las caídas en la era 1993-2006 (solo VIX/BSI/SKEW/Yield), ¿cuántas detectamos?"*
