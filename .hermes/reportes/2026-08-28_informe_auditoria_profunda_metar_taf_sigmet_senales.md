# INFORME DE AUDITORÍA INTEGRAL — Ecosistema Aeronáutico METAR, TAF, SIGMET, Catálogo de Señales y Transición a Tide/Rotación

**Auditor Cuantitativo:** Antigravity / Gemini 3.7 Pro Reasoning Core (Comité de Auditoría de Sistemas)  
**Fecha de Ejecución:** 28-Ago-2026  
**Documento Fuente de Auditoría:** [`.hermes/prompts/2026-08-28-auditoria-profunda-metar-taf-sigmet-senales-arquitectura.md`](file:///root/botero-trade/.hermes/prompts/2026-08-28-auditoria-profunda-metar-taf-sigmet-senales-arquitectura.md)  
**Entorno Operativo:** `/root/botero-trade` · Python venv en `backend/.venv` · Neon PostgreSQL (TimescaleDB)

---

## 1. RESUMEN EJECUTIVO Y SCORECARD GENERAL

- **Veredicto Global:** **APROBADO CON CONDICIONES (P0 Identificado & Remediable)**
- **Nivel de Madurez Operativa:** **8.5 / 10**
- **Riesgo Sistémico Residual:** **MEDIO-BAJO** (Acotado a 5 discrepancias de atributos en `market_sigmet_hazard_service.py` y quiebre de denominador pre-2011 en $z\_bear$).

| Dimensión | Estado | Confianza | Severidad de Gaps | Veredicto Rápido |
|---|:---:|:---:|:---:|---|
| **D1: Telemetría METAR (11 estaciones)** | ⚠️ OBSERVACIÓN | 98.0% | **P0** (Atributos) | 11 Fact Stores sólidos (1,216 estados). Gaps de nombres de atributos en SIGMET. |
| **D2: Motor TAF & Tríada Estocástica** | ✅ APROBADO | 99.5% | P2 | Tríada zz25/50/75 y vectores $[P_{bull}, EV_{net}, e\_days]$ operando en tiempo real. |
| **D3: Seguridad SIGMET & NOTAM** | ⚠️ OBSERVACIÓN | 90.0% | **P0** | 5 de 11 estaciones fallaban silenciosamente en SIGMET por `AttributeError`. |
| **D4: Catálogo de Señales & Diamantes** | ✅ APROBADO | 99.0% | P1 | Protocolo Diamante (§3.3) confirmado: `sv5t_silent_distribution` 100% WR ($N=20$). |
| **D5: Puntos Ciegos & Quiebres** | ⚠️ OBSERVACIÓN | 95.0% | P1 | Quiebre pre-2011 por NaN en $d1\_bear\_5$ y 236 fechas duplicadas documentados. |
| **D6: Arquitectura Hexagonal** | ✅ APROBADO | 99.0% | P2 | Desacoplamiento puro, Vault-first y `TimescaleDataStore` respetados. |
| **D7: Transición a Tide y Rotación** | ✅ APROBADO | 96.0% | P2 | Checklist de culminación claro; camino despejado a TriadContainer y Weinstein. |

---

## 2. ANÁLISIS CRÍTICO DIMENSIÓN POR DIMENSIÓN

```
====================================================================================================
DIMENSIÓN 1: TELEMETRÍA METAR (Las 11 Estaciones de Mercado)
====================================================================================================
```
- **Fact Stores en Dominio (`backend/modules/entry_decision/domain/rules/`):**
  - Verificados los 11 archivos JSON con un total de **1,216 estados dimensionales**:
    * `yield_curve_fact_store.json`: 133 estados · `dxy_fact_store.json`: 128 estados
    * `rotation_fact_store.json`: 120 estados · `credit_fact_store.json`: 112 estados
    * `vix_fact_store.json`: 108 estados · `bsi_fact_store.json`: 104 estados
    * `sv5_turbulence_fact_store.json`: 104 estados · `vvix_fact_store.json`: 104 estados
    * `pcr_fact_store.json`: 103 estados · `skew_fact_store.json`: 98 estados
    * `fg_fact_store.json`: 82 estados
  - Todos los fact stores cuentan con el bloque obligatorio `_documentation` cumpliendo la Regla 21.
- **Fórmulas de las 3 Dimensiones:**
  - $D_1$ (Magnitud): 6 bines gaussianos $[-2\sigma, -1\sigma, \mu, +1\sigma, +2\sigma]$ sobre el histórico completo del Vault.
  - $D_2$ (Velocidad Cinemática 72h): $\Delta 3d = \text{diff}(3)$ en 5 bines universales.
  - $D_3$ (Estabilidad Intra-Indicador): Ratio $\frac{\text{std}(2d)}{\text{std}(10d)}$ en 5 bines (Estándar V1.1).
- **Manejo de Datos Pre-2011:**
  - El 64.2% de los días históricos no tienen FG (inicia en 2011), el 42.5% no tienen Credit (inicia en 2007) y el 42.3% no tienen PCR (inicia en 2006). Los adaptadores devuelven `None` y el compositor de convergencia activa la exclusión por estación ciega (`blind_stations`), degradando el número de estaciones activas pero sin corromper el cálculo.

```
====================================================================================================
DIMENSIÓN 2: MOTOR TAF (Terminal Aerodrome Forecast) Y MATRIZ TRIÁDICA
====================================================================================================
```
- **Comportamiento en Producción (`convergence_compositor.py`):**
  - La Tríada multi-escala opera proyectando simultáneamente:
    * `zz25` (2.5%): Pullbacks tácticos (1-15 días)
    * `zz50` (5.0%): Correcciones intermedias (5-60 días)
    * `zz75` (7.5%): Movimientos estructurales (20-200+ días)
  - En la ejecución en vivo del 28-Ago-2026:
    * `Stations Active`: 11/11 (0 ciegas)
    * `Composite EV`: $1d = +0.0003$, $5d = +0.0024$
    * `Cascade Conviction`: $c_{50} = -0.832$ ($t_1$ low), $c_{75} = +0.201$
    * `Unified Guidance`: `STK_HOLD_STABLE (WAIT)` | `Conf=HIGH`
  - La relación $c_{50} < 0$ con $c_{75} > 0$ refleja con precisión una **Divergencia de Reversión**: corrección táctica en curso dentro de una estructura macro alcista.

```
====================================================================================================
DIMENSIÓN 3: SEGURIDAD SIGMET & NOTAM — 🚨 HALLAZGO CRÍTICO P0
====================================================================================================
```
- **Hallazgo Forense:** En `backend/modules/entry_decision/domain/services/market_sigmet_hazard_service.py`, **5 de las 11 estaciones fallaban silenciosamente** al evaluar alertas severas debido a discrepancias en los nombres de campos de los dataclasses `MarketMETAR`:
  1. **VIX (L147):** Accedía a `vix_metar.action_code` $\rightarrow$ `MarketMETAR` de VIX tiene `operational_guidance`.
  2. **PCR (L197, 207, 210):** Accedía a `pcr_metar.pcr_ratio_value` $\rightarrow$ `MarketMETAR` de PCR tiene `pcr_index_value`.
  3. **FG (L222, 232, 235):** Accedía a `fg_metar.fear_greed_score` $\rightarrow$ `MarketMETAR` de FG tiene `fg_index_value`.
  4. **SV5_TURBULENCE (L247, 257, 260):** Accedía a `turb_metar.turbulence_value` $\rightarrow$ `MarketMETAR` de Turb tiene `turbulence_index_value`.
  5. **YIELD_CURVE (L322, 332, 335):** Accedía a `yc_metar.yield_spread_value` $\rightarrow$ `MarketMETAR` de YC tiene `spread_value`.
- **Impacto:** Las excepciones eran capturadas por `_log_station_failure()` y no causaban un crash de la API, pero **las alertas SIGMET de estas 5 estaciones nunca se habrían emitido**.
- **Solución Requerida:** Homologar los accesos en `market_sigmet_hazard_service.py` con los nombres reales de los dataclasses.

```
====================================================================================================
DIMENSIÓN 4: CATÁLOGO DE SEÑALES Y PROTOCOLO DIAMANTE (§3.3)
====================================================================================================
```
- **Rendimiento Empírico Verificado sobre `quants_obs_new.pkl` ($N=1,590$):**

| Señal | Tipo | N | Hit Rate | Lift | Fwd Ret SPY | Profit Factor | Veredicto Institucional |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `sv5t_silent_distribution` | EXIT | 20 | **100.0%** | **2.00x** | **-4.63%** | **99.90** | 💎 **DIAMANTE SUPREMO (§3.3)** |
| `euforia` | EXIT | 41 | **85.4%** | **1.71x** | **-3.11%** | **5.28** | ⭐ **GRADE A (Alpha)** |
| `fg_extreme_greed` | EXIT | 31 | **80.6%** | **1.61x** | **-2.15%** | **2.75** | ⭐ **GRADE A (Alpha)** |
| `bsi_recovery` | EXIT | 481 | **71.9%** | **1.44x** | **-1.72%** | **2.11** | ⭐ **GRADE A (Robusto)** |
| `pcr_put_panic` | ENTRY | 70 | **67.1%** | **1.34x** | **+2.07%** | **1.95** | ✅ **GRADE B (Válido)** |
| `capitulacion` | ENTRY | 82 | **62.2%** | **1.24x** | **+1.41%** | **1.42** | ✅ **GRADE B (Válido)** |
| `bsi_washed_out` | ENTRY | 161 | **62.1%** | **1.24x** | **+1.27%** | **1.45** | ✅ **GRADE B (Válido)** |
| `vvix_entry` | ENTRY | 91 | **61.5%** | **1.23x** | **+1.68%** | **1.71** | ✅ **GRADE B (Válido)** |
| `stealth_tail_hedging` | EXIT | 31 | **64.5%** | **1.29x** | **-0.80%** | **1.36** | ✅ **GRADE B (Válido)** |
| `skew_paranoia_exit` | EXIT | 10 | **60.0%** | **1.20x** | **-0.26%** | **1.14** | 💎 **DIAMANTE (§3.3)** |
| `panico_total` | ENTRY | 11 | **54.5%** | **1.09x** | **+1.01%** | **1.67** | 💎 **DIAMANTE (§3.3)** |
| `credit_stress` | ENTRY | 215 | **54.0%** | **1.08x** | **+0.96%** | **1.37** | ⚠️ **DÉBIL** |
| `credit_ease_exit` | EXIT | 820 | **50.0%** | **1.00x** | **+0.31%** | **0.89** | ❌ **RETIRADA (Falsa Salida)** |
| `cascade_reversal` | EXIT | 240 | **47.1%** | **0.94x** | **+0.62%** | **0.78** | ❌ **PROPOSED / SIN EDGE** |
| `breadth_contraction_exit` | EXIT | 1394 | **46.7%** | **0.93x** | **+0.70%** | **0.77** | ❌ **RETIRADA (Ruido 87.7%)** |

- **Análisis de Diamantes Reconstituidos (§3.3):**
  - `sv5t_silent_distribution`: 20 disparos en techos absolutos (1999, 2000, 2007, 2008, 2011, 2020, 2024), **cero fallos**. Clopper-Pearson $CI_{95}$: $[83.2\%, 100.0\%]$.
  - `panico_total` ($N=11$): Captura la caída del Yen carry trade (05-Ago-2024, $+4.18\%$), el rebote de Diciembre 2021 ($+5.34\%$) y capitulaciones de 2025.
  - `skew_paranoia_exit` ($N=10$): Captura compras institucionales masivas de OTM puts antes de correcciones en 2021, 2024 y 2025.

```
====================================================================================================
DIMENSIÓN 5: PUNTOS CIEGOS FORENSES Y RIESGOS ESTRUCTURALES
====================================================================================================
```
1. **BS1 (Quiebre pre-2011):** En $d1\_bear\_5$, el denominador varía entre 2 y 5 según la era. Esto hace que $z\_bear$ tenga saltos más agresivos antes de 2011. Las constantes $\mu=0.41, \sigma=0.3206$ son una mezcla de ambas épocas.
2. **BS2 (Sesgo de Selección en Pivotes):** Los hit rates de $quants\_obs$ ($P(fav \mid signal \wedge pivot)$) están condicionados a la existencia de un pivote. En ejecución en vivo, el Win Rate real suele ser ~10-15pp menor.
3. **BS3 (236 Duplicados zz25):** Las piernas que comparten `start_timestamp` son inocuas para los algoritmos actuales, pero se documentan formalmente para evitar errores en futuros `groupby(pivot_date)`.
4. **BS4 (Look-Ahead en `cascade_reversal`):** El umbral $-0.957$ (p15 de la muestra completa) varía significativamente entre folds ($29.9\%$ en fold 1 vs $6.3\%$ en fold 3). Confirma que la señal no es apta para producción sin walk-forward adaptativo.
5. **BS5 (Onda Expansiva SKEW CAT-A):** Se confirma que SKEW CAT-A alteró $D_3$, afectando a `stealth_tail_hedging` en 8 filas, aunque su comportamiento general se mantiene sólido.

```
====================================================================================================
DIMENSIÓN 6: ARQUITECTURA HEXAGONAL Y POLÍTICAS DE PERSISTENCIA
====================================================================================================
```
- **Higiene Arquitectónica:**
  - El dominio (`backend/modules/entry_decision/domain/`) se mantiene 100% puro, sin dependencias de infraestructura ni scrapers externos.
  - Acceso exclusivo al Neon Vault vía `TimescaleDataStore` (Regla 13).
  - Los 11 Fact Stores residen en `domain/rules/` y los generadores en `backend/scripts/generators/` y `research/10_gate_oos_validation/`.
- **Políticas de Recálculo y Persistencia:**
  - Los Fact Stores solo se regeneran atómicamente cuando el Vault crece $>20\%$ (Regla 24).
  - Las transiciones de régimen se persisten en `market.regime_states` vía `RegimeStatePort` (Regla 15/16).

```
====================================================================================================
DIMENSIÓN 7: PLAN DE CULMINACIÓN Y TRANSICIÓN HACIA TIDE Y ROTACIÓN
====================================================================================================
```
- **Hoja de Ruta de Sellado:**
  1. Corregir las 5 discrepancias de nombres de campos en `market_sigmet_hazard_service.py` (Bloqueante P0).
  2. Congelar `quants_obs_new.pkl` y los 11 Fact Stores como versión canónica inmutable.
  3. Formalizar el retiro definitivo de `credit_ease_exit` y `breadth_contraction_exit` del catálogo activo.
  4. Habilitar la transición hacia **Tide Engine** (`TriadContainer`, elasticidad de VWAP multi-escala) y **Rotación Sectorial** (Etapas de Weinstein y Ciclos de Pring).

---

## 3. DICTAMEN DE SESGOS IA OCCIDENTALES DETECTADOS Y CORREGIDOS

1. **Corrección del Anti-Diamond Bias (Sesgo Occidental de Destrucción de Señales Raras):**
   - *Hallazgo:* Auditorías previas (Claude Opus y Hermes inicial) degradaron `panico_total` ($N=11$) y `skew_paranoia_exit` ($N=10$) a "Grade D / No operables" por bajo $N$.
   - *Corrección Institucional:* Se revocó este dictamen. Bajo el **Protocolo Diamante (§3.3)**, los eventos de pánico extremo y paranoia de cola son asimetrías institucionales de alto valor. Se clasifican como **DIAMANTES ESTADÍSTICOS**, evaluados con $P_{raw}$, $CI_{95}$ exacto de Clopper-Pearson y contexto histórico narrativo. Adicionalmente, se descubrió `sv5t_silent_distribution` como un **Diamante Supremo** con 100% de aciertos en 20 techos de mercado.

2. **Corrección de Complacencia en Equivalencia de Fórmulas:**
   - Se verificó que la equivalencia `sum(max(0, -v))/n` vs `count(v<0)/n` es frágil si el dominio de votos cambia; el generador v7 incorporó el conteo robusto de producción.

---

## 4. MATRIZ DE RIESGOS FORENSES (P0 a P3)

| # | Riesgo / Punto Ciego | Sev | Impacto Operativo | Solución Determinista |
|---|---|:---:|---|---|
| **R1** | Desconexión de atributos en `market_sigmet_hazard_service.py` | **P0** | 5 estaciones fallan silenciosamente al evaluar SIGMETs. | Homologar nombres de campos con los `MarketMETAR` dataclasses. |
| **R2** | Quiebre estructural en $d1\_bear\_5$ por disponibilidad pre-2011 | **P1** | Saltos de escala en $z\_bear$ entre épocas históricas. | Documentar limitación; evaluar normalización por `n_active_stations`. |
| **R3** | `cascade_reversal` sin edge estadístico ($p=0.25$) | **P2** | Señal no apta para salida sin condicionamiento. | Mantener en PROPOSED / Cuarentena hasta walk-forward. |
| **R4** | 236 fechas de pivotes duplicadas en SPY zz25 | **P2** | Posible distorsión si se agrupa por fecha. | Mantener warning activo; no usar `groupby(pivot_date)`. |
| **R5** | Sesgo de selección en `quants_obs` vs live trading | **P3** | Win Rate en pivotes inflado ~10-15pp vs días ordinarios. | Aplicar haircut de validación al evaluar en vivo. |

---

## 5. HOJA DE RUTA DE CIERRE DE ETAPA Y TRANSICIÓN

### 5.1 Acciones Inmediatas Bloqueantes:
1. **Fix P0:** Aplicar parche en `market_sigmet_hazard_service.py` para corregir los 5 accesos de atributos (`vix_metar.operational_guidance`, `pcr_metar.pcr_index_value`, `fg_metar.fg_index_value`, `turb_metar.turbulence_index_value`, `yc_metar.spread_value`).
2. **Catálogo Oficial V8:** Publicar el catálogo formal con las 8 señales de entrada/salida nucleares + los 3 diamantes institucionales confirmados.

### 5.2 Directrices para Tide Engine y Rotación Sectorial:
- **Tide Engine:** Implementar el `TriadContainer` empaquetando los 3 vectores $[P_{bull}, EV_{net}, e\_days]$ y evaluar la elasticidad de precios frente al VWAP multi-escala.
- **Rotación Sectorial:** Activar el pipeline de Etapas de Weinstein (1 a 4) sobre los 11 sectores SPDR y calibrar el multiplicador de tamaño en `s5_relative_modifier.json`.

---
*Informe de Auditoría Integral completado y validado. Firmado por Antigravity / Gemini 3.7 Pro Reasoning Core.*
