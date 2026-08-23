# AUTOAUDITORÍA GUIADA POR PROPÓSITO — Generación correcta de `quants_obs`
**Fecha:** 22-Ago-2026 · **Firma:** qwen/qwen3.8-max (Hermes)
**Principio rector:** el fin es una tabla **correcta según la lógica de producción y reproducible**.
La fidelidad al one-off del 17-Ago es un *detector de divergencias*, NO la meta.

---

## 1. EL PROPÓSITO (define todo lo demás)

`quants_obs` es la **tabla de observación canónica** del sistema de señales: para cada
pivote confirmado del zigzag SPY (un giro de mercado), captura el **estado dimensional
instantáneo de las 11 estaciones** más la convicción del cascade. Es la matriz de features
sobre la que se mide el edge real de cada señal de entry/exit.

**Si el zigzag está mal calculado o desalineado, falla todo el sistema** — los pivotes son
la columna vertebral. Por eso la prioridad #1 es que los pivotes sean correctos y reproducibles.

## 2. CONJUNTO ESENCIAL — qué consume realmente el sistema (mapa verificado)

Auditado sobre `evaluador_vela_a_vela.py` y las 39 definiciones de señales en `arnes/señales.py`:

| Tier | Columnas | Quién las consume | Criticidad |
|------|----------|-------------------|-----------|
| **T0 (sagrado)** | `pivot_date`, `pivot_type` | Evaluador (régimen), TODAS las señales | **CRÍTICO** — si fallan, falla todo |
| **T0 (geometría)** | `leg_bear`, `prev_leg_return`, `duration_bars`, `daily_return_pct` | Evaluador, análisis de duración | CRÍTICO |
| **T1 (input de señales)** | `{st}_sk` × 11 | Las 39 señales leen **solo D1** (`sk.split("__")[0]`) | CRÍTICO |
| **T1** | `credit_val` | `credit_easing` | Alto |
| **T1** | `pivot_type` | Señales condicionadas al tipo de pivote | Alto |
| **T2 (analítica)** | `cascade_conviction`, **`cascade_conviction_50`** | `cascade_reversal` | Medio |
| **T3 (bajo consumo)** | `_zk_pbull/pbear`, `_zz25_pbull/pbear`, `_ev_net`, `_n`, `_d1_vote`, `_vel`, `_vol`, `z_bear`, `z_dom`, `mean_zk_pbull_*`, `cascade_50/75`, `d1_bear_5` | Forensia / cascade / OOS | Bajo |

**Conclusión:** la tabla DEBE servir correctamente T0 + T1. T2 debe funcionar para que
`cascade_reversal` no sea inerte. T3 se preserva por compatibilidad de esquema pero su
deriva histórica es aceptable (CAT-B).

## 3. AUDITORÍA DE FÓRMULAS — especificación correcta por columna

### T0 — Pivotes y geometría (verificado 100%)
| Columna | Fórmula correcta | Fuente | Match original |
|---------|------------------|--------|:---:|
| `pivot_date`, `pivot_type` | `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")` | Producción | 100% |
| `leg_bear` | `(pivot_type == "MAX")` | derivada | 100% |
| `prev_leg_return` | Del repositorio | Producción | 100% |
| `duration_bars` | Duración CALENDARIO de la pierna que ARRANCA en el pivote, piso 1 día | ZigzagLeg | 100% |
| `daily_return_pct` | Retorno de esa pierna (%) ÷ duración | ZigzagLeg | 100% |
| `cascade_50/75` | Proximidad ±3 días a un pivote zz50/zz75 (NO pertenencia) | DB | 99.9% |

### T1 — Estado dimensional (la decisión arquitectónica clave)
| Columna | Fórmula correcta | Política |
|---------|------------------|----------|
| `{st}_val` | Serie del Vault, alineación por FECHA EXACTA | 100% (PCR verificado) |
| `{st}_vel` | `diff(3)`, fuera de rango = 0.0 | 100% (PCR verificado) |
| `{st}_vol` | `std(2)/std(10)`, fuera de rango = 1.0 | 100% (PCR verificado) |
| `{st}_sk` | **LookupAdapter de producción con edges estáticos** | DECISIÓN CAT-A |
| `{st}_n`, `_d1_vote` | Del adapter (`state.n`, `d1_directional_vote(sk)`) | derivados |

**DECISIÓN CAT-A sobre skew:** el one-off original produjo bins D1 **solapados** en SKEW
(NORMAL_TAIL_RISK 109-120 cruza ELEVATED_TAIL_RISK 113-120), imposibles con umbral estático.
Se probó la hipótesis trailing (cuantiles recalculados en ventanas 252/504/756/1000): **rechazada**,
máximo 41.9%. El clasificador original es irreproducible y no corresponde a ninguna lógica de
producción conocida → **se dictamina CAT-A (artefacto no reproducible del one-off)**. La tabla
correcta usa los edges estáticos del `SkewLookupAdapter` (lógica de producción) y **documenta**
la divergencia. NO se clona el fantasma.

### T2 — Cascade (incluye el bug descubierto)
| Columna | Fórmula correcta | Estado |
|---------|------------------|--------|
| `z_dom` | `(abs_prev_leg_return − 0.0532)/0.035` (cal-file) | 100% |
| `z_bear` | `(d1_bear_5 − μ)/σ`; el original usó μ=0.3299 σ=0.2856 (no existen en ningún archivo) | CAT-B |
| `cascade_conviction` | `0.66·z_bear + 0.34·z_dom` | Fórmula 100% |
| **`cascade_conviction_50`** | **NO EXISTE en el pickle** | **CAT-A — BUG REAL** |

**BUG DESCUBIERTO:** la señal `cascade_reversal` lee `df["cascade_conviction_50"] < 0.30`,
pero el pickle solo tiene `cascade_conviction` (z-score compuesto, rango ±8) y `cascade_50/75`
(flags binarios de proximidad). El guard `if "cascade_conviction_50" not in df.columns: return False`
hace que la señal **nunca dispare, en silencio**. Esto es un bug real de la herramienta, no una
divergencia histórica: **la columna debe existir y estar bien definida para que el propósito se cumpla.**

### T3 — Derivadas de bajo consumo (deriva histórica aceptable)
`{st}_zk_pbull/pbear` (bloque `zigzag_kinematic.zz25`, 100%), `{st}_zz25_pbull/pbear`,
`{st}_ev_net` (bloque plano `zz25`, 80-94% — regenerado post-17-Ago), `d1_bear_5`,
`mean_zk_pbull_A/11`. → **CAT-B: se acepta documentar la divergencia.**

## 4. EL PROBLEMA A RESOLVER (declaración formal)

**Problema:** construir una herramienta que genere `quants_obs` de forma **correcta según la
lógica de producción y reproducible**, de modo que:
1. Los pivotes (columna vertebral) sean los del zigzag oficial, reproducibles al 100%.
2. El estado dimensional (`_sk` de las 11 estaciones) siga la clasificación de producción.
3. `cascade_conviction_50` exista y esté definida, para que `cascade_reversal` no sea inerte.
4. Toda divergencia respecto al one-off quede clasificada (CAT-A/B/C) y documentada.

**No es el problema** replicar byte-a-byte el one-off (incluye un clasificador skew irreproducible
y μ/σ de `z_bear` que no existen en ningún archivo — ambos artefactos, no verdades).

## 5. DECISIONES DE ARQUITECTURA (la herramienta correcta)

1. **Pivotes** → `ZigzagLegRepository` (producción). Sagrado.
2. **`_sk`** → LookupAdapters de producción, edges estáticos. Se documenta la divergencia de skew (CAT-A).
3. **`_val/_vel/_vol`** → Vault, alineación fecha exacta, defaults vel=0/vol=1.
4. **`duration_bars`, `daily_return_pct`** → pierna saliente, duración calendario.
5. **`cascade_conviction`** → fórmula verificada; **se añade `cascade_conviction_50`** correctamente definida.
6. **Se mantiene el esquema de 141 columnas** (compatibilidad) + un **manifiesto de divergencias**
   que clasifica cada columna en CAT-A/B/C con su match y su política.
7. **Compuerta de fidelidad** como detector de divergencias, no como meta de aceptación.
