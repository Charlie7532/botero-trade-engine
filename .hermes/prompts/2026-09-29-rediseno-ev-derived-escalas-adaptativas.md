# PROMPT DE DISEÑO — REDISEÑO DE LA SERIE `ev_derived.json` CON ESCALAS GAUSSIANAS ADAPTATIVAS POR TICKER

**Destino:** Agente de Diseño y Arquitectura Cuantitativa (Antigravity: Gemini / Claude guiada)  
**Fecha:** 2026-09-29 (actualizado 2026-09-30 post-fix `e2a2ada`)  
**Preparado por:** Hermes (Auditoría, Enriquecimiento Fáctico y Estructuración de Prompts)  
**Naturaleza:** Prompt de **DISEÑO ARQUITECTÓNICO + ANÁLISIS METROLÓGICO** (no implementa código de producción). Su salida son **dos artefactos formales**: (1) el documento de **DISEÑO (D)** y (2) el **PROMPT DE CONSTRUCCIÓN (P)** listo para despacho autónomo.  

---

## 0. OBJETIVO Y METAS CUANTITATIVAS

Rediseñar y definir la arquitectura de una **nueva serie de Fact Stores `ev_derived.json`** para el subsistema multiescala **Tide / Current / Wave / Multiscale**, resolviendo la deuda de homogeneización global e incorporando:

1. **Escalas Gaussianas ADAPTATIVAS por ticker** (núcleo del rediseño): sustituir los umbrales estáticos globales por cuantiles empíricos adaptados a la distribución de volatilidad y dinámica de pivotes de cada activo individual, cumpliendo estrictamente la **Regla S1 de `gaussian_scale_policy.md`** (cuantiles empíricos sobre datos reales, nunca fórmulas paramétricas $\mu \pm k\sigma$ sobre distribuciones con colas pesadas).
2. **Transferencia metrológica desde las estaciones METAR**: esquemas de datos autodescriptivos (Rule 21), formato vectorial numérico de estados (Rule 24), gestión canónica de overflow ($T1..T5$ en metadatos sin alterar el espacio de estados base), y política de **diamantes estadísticos** ($N < 21$ preservados y catalogados, nunca descartados).
3. **Aprovechamiento de ventajas estructurales de Tide y Wave sobre METAR**: mayor densidad combinatoria ($216$ estados L3 en Tide con nuevo esquema D1×D1×D1 vs $\sim 150$ en METAR), ergodicidad local y repetición natural de estados cinemáticos a lo largo de ciclos de mercado.
4. **Tratamiento homogéneo de señales especiales y confluencia de regímenes**: tratar las configuraciones extremas no como ruido de cola descartable, sino como insumos determinísticos de regímenes de mercado (`market.regime_states` vía `RegimeStatePort`, Rule 15 y 16), convergiendo limpiamente con la telemetría METAR.
5. **Saneamiento integral de la deuda de esquemas y bugs de runtime**: corregir el desfase de documentación en los generadores actuales (donde se declaran "180 estados" habiendo 245 reales en v1), unificar la jerarquía de rollups (invertida entre Tide L3 $\to$ L0 y Wave L1 $\to$ L3), y resolver el `AttributeError` activo de `fatigue_type` en `swing_gate.py`.

**Entregable = DOS piezas:** **(D)** el documento de DISEÑO formal y **(P)** el PROMPT DE CONSTRUCCIÓN self-contained.

---

## 1. CONTEXTO VERIFICADO Y AUDITORÍA FÁCTICA DEL CÓDIGO (Dato Mata Relato)

### 1.1. Series y dimensiones a PRESERVAR (Declaración del Arquitecto)
> *"…siempre manteniendo las variables ya establecidas en las dimensiones."*

La auditoría directa sobre el repositorio arroja la siguiente realidad estructural y muestral:

| Familia | Archivo | Formato de Llave | Estados v1 (actual) | Estados v2 (nuevo) | Muestras ($N$) | Esquema de Campos por Estado |
|---|---|---|:---:|:---:|:---:|---|
| **Tide EV** | `rc_tide_ev_derived.json` | `T{level}\|C{level}\|{vwap_bin}` | **245** L3 (7×7×5)<br>**49** L2<br>**7** L1<br>**1** L0 | **216** L3 (6×6×6)<br>**36** L2<br>**6** L1<br>**1** L0 | **4,554,321** en raw table | `n`, `is_rare_state`, `std_return`, `zz25\|zz50\|zz75` (cada uno con `p_bull`, `p_bear`, `e_ret_max`, `e_ret_min`, `ev_net`, `e_days`, `ev_per_day`, `rr_asymmetry`), `ev_net_global`, `sharpe` |
| **Tide Clásico** | `rc_tide_derived.json` | `T{level}\|C{level}\|{vwap_bin}` | **180** (6 T × 6 C × 5 VWAP) | *(sin cambio planificado)* | $\sim 765,000$ | `identity`, `frequency`, `direction`, `composition`, `turn_risk` (bottom/top 25/50/75), `runs`, `predictive`, `reading` |
| **Wave EV** | `rc_wave_ev_derived.json`<br>`rc_wave_ev_3scales_derived.json` | `L1:W{slope}\|σVc:{bin}\|σc:{bin}\|vel:{trend}` | **444** L1<br>**30** L2<br>**5** L3<br>*(=479 total)* | *(TBD — edges gaussianos)* | Variable por micro-ola | `n`, `is_rare_state`, `p_bull`, `p_bear`, `e_ret_min`, `e_ret_max`, `ev`, `sharpe`, `e_days`, `rr_asymmetry`, `ev_per_day`, `fatigue_buckets` |
| **Multiscale** | `rc_ev_multiscale_tree.json` | `T{..}\|C{..}\|W{..}\|σVc\|σVw\|ΔσVw#FATIGUE` | **25,797** s1_full<br>**996** s3_triad | *(se regenera tras Tide+Wave)* | **791,120** total | `n`, `is_rare_state`, `p_bull_25`, `ev_net_25`, … (flatten per-scale), `ev_net_global`, `std_return`, `sharpe`, `rr_asymmetry` |
| **Normativa Global** | `rc_vol_normalized_thresholds.json` | Percentiles empíricos globales para slopes y vwap | — | *(reemplazado por ticker_gaussian_profiles.json)* | **4,577,585** censo 100% | `tide_slope_norm`, `current_slope_norm`, `wave_slope_norm`, `vwap_sigma_wave`, `rsi_value`, `kalman_velocity` |

#### Hallazgos y Correcciones Fácticas Críticas:
1. **L0 es un diccionario baseline único:** En `rc_tide_ev_derived.json`, `l0_global` no son 8 entradas, sino un único diccionario con 8 campos agregados del mercado completo (`n: 4554321`, `ev_net_global: +0.0247` *(promedio 3 escalas, corregido post-fix `e2a2ada`)*, `sharpe: 0.352`, etc.).
2. **Deuda de Documentación Interna ("180" vs "245"):** En `rc_tide_ev_derived.json`, el bloque `_documentation.state_hierarchy` afirma textualmente: `"L3: Full 3D State... (180 granular micro/macro states)"`. **Esto es falso y constituye una deuda de arrastre.** El archivo real contiene **245 estados L3** (v1). El desfase proviene de que `rc_slope_classifier.py` implementa 7 niveles de pendiente para T y C (`+++, ++, +, ~, -, --, ---`), generando $7 \times 7 \times 5 = 245$ estados. **El sistema v2 adopta 6 bins D1 para T, C y VWAP → 6×6×6 = 216 estados L3.** Esta deuda se resuelve de nacimiento.
3. **Jerarquía Invertida entre Módulos:** En Tide EV, $L3$ es el estado más granular (245→216) y $L1$ el más agregado (7→6). En Wave EV (`generate_wave_ev_real_derived.py` L7 y `rc_wave_ev_derived.json`), **la convención está invertida**: $L1$ es el estado granular (450/479 estados) y $L3$ es el rollup grueso de 6 estados. El rediseño debe estandarizar o aislar esta nomenclatura.
4. **Niveles Reales de Wave:** En `rc_wave_ev_derived.json`, las claves de ola contienen `L1:W+++`, `L1:W++`, `L1:W+`, `L1:W-`, `L1:W--`, `L1:W---`. Existe `W+++`, pero **NO existe `W~`** (6 niveles de ola sin neutro).

---

### 1.2. Origen Fáctico de la Debilidad: El Caso SPY y la Inconsistencia de Umbrales Globales

La debilidad documentada sobre los falsos positivos y la disparidad entre activos no es teórica; proviene de investigaciones empíricas del repositorio:

- **Origen del dato VIX CRISIS_SPIKE ($N=171$):** Documentado en `docs/research/01_señales_entry_exit/medicion_vix_crisis_spike.json`. La señal `vix_crisis_spike` registra exactamente **$n = 171$ episodios activos** en el histórico (97 aciertos, 74 pérdidas, win rate de 56.7%, retorno medio forward de +0.75%).
- **El umbral global P97.72 = 40.7336:** Definido taxativamente en `backend/modules/entry_decision/domain/rules/sigma_overflow.py` (línea 39) como el cuantil empírico global del VIX. En la actualización de taxonomía canónica (`d1_labels_canonical.md`, 2026-08-30), este bin fue homologado de `CRISIS_SPIKE` a `EXTREME_PANIC`.
- **Degradación de señal por falta de escala per-ticker:** En `docs/research/01_señales_entry_exit/wins_losses_entry4_7_REPORT.md` (L67-110, 228-244), se demostró que cuando el VIX entra en `CRISIS_SPIKE` (VIX $\ge 40.7$), la win rate de entradas en techos se degrada en $-23.3$ pp. Al cruzar las 171 alertas globales contra la dinámica real de giros de SPY (verificado en `backend/scripts/per_ticker_forensics_output/SPY_forensics.csv`), **134 alertas fueron falsos positivos de giro** (el mercado continuó cayendo o ya había rebotado días atrás), porque la volatilidad realizada extrema de SPY ($P97.72 \approx 60.9\%$ anualizada equivalente) diverge radicalmente de activos defensivos como KO ($P97.72 \approx 52.6\%$) o híper-volátiles como TSLA ($P97.72 \approx 36.3\%$).
- **La Tensión Global vs Per-Ticker (Information Coefficient):** En pruebas preliminares de cascada, el umbral global arrojó un IC de $+0.412$ frente a $+0.371$ del modelo per-ticker no regularizado sobre SPY. Esto evidencia que un escalado per-ticker ingenuo sufre sobreajuste por muestra pequeña en colas, por lo que **la escala adaptativa requiere regularización bayesiana o cuantiles empíricos agregados por familia**.

---

### 1.3. La Cadena de la Deuda: Trainer $\to$ Generator $\to$ Lookup

La deuda técnica no reside únicamente en la generación del JSON, sino en toda la tubería:

```
[TRAINER: train_tide_ev_real_table.py]
  ├── Lee: engine.channel_snapshots + engine.zigzag_points + market.ohlcv_bars
  ├── Normaliza slope local: slope_norm = slope / max(atr_pct, 0.005) (L245-248)
  ├── ERROR DE FONDO: Clasifica slope_norm usando _classify_one() (L253-254)
  │     └── Compara contra _VOL_TH de rc_vol_normalized_thresholds.json (GLOBALES de 4.58M obs)
  └── Emite: rc_tide_ev_probability_table.json (conteos sesgados por umbrales fijos)

      ↓

[GENERATOR: generate_tide_ev_real_derived.py]
  ├── Lee rc_tide_ev_probability_table.json
  ├── Aplica shrinkage bayesiano L3 -> L2 -> L1 -> L0 (prior_weight=20.0)
  ├── ✅ CORREGIDO (commit e2a2ada, 30-Sep-2026): L63 = `raw_p_bull = n_pos / n_tot`
  ├── DEUDA DOCUMENTAL RESTANTE: _documentation declara "180 estados" habiendo 245 (L157)
  └── Emite: rc_tide_ev_derived.json (REGENERADO post-fix con p_bull=P(MAX))

      ↓

[LOOKUP: rc_tide_ev_lookup.py]
  ├── Lee rc_tide_ev_derived.json
  ├── Resuelve L3 -> fallback L2 -> L1 -> L0
  ├── ✅ CORREGIDO (commit e2a2ada): Docstring actualizado a p_bull = P(MAX)
  └── Emite: RealEVSignal (CARECE de atributo fatigue_type)
```

---

### 1.4. Arquitectura de Consumo en `swing_gate.py` (5 Lookups Paralelos)

En `backend/modules/quality_swing/application/use_cases/swing_gate.py`, la evaluación de cada símbolo ejecuta 5 consultas simultáneas en el dominio:

1. **`lookup_dual_probability()`** (L160) — Matriz dual clásica.
2. **`lookup_tide_signal()`** (L218) — Desde `rc_tide_derived.json` $\to$ emite `TideSignal`.
3. **`lookup_real_ev()`** (L267) — Desde `rc_tide_ev_derived.json` $\to$ emite `RealEVSignal`.
4. **`lookup_multiscale_kinematic_ev()`** (L290) — Desde `rc_ev_multiscale_tree.json` $\to$ emite `MultiscaleEVKinematicSignal`.
5. **`lookup_real_wave_ev()`** (L317) — Desde `rc_wave_ev_derived.json` $\to$ emite `RealWaveEVSignal`.

**Restricción de Integración:** Cualquier alteración en la estructura de salida o contratos de datos impacta estos 5 adaptadores. El rediseño debe preservar backward-compatibility absoluta con los DTOs o definir adaptadores de compatibilidad.

---

### 1.5. Bug Activo de Fatiga (`AttributeError` en Producción)

En `swing_gate.py`, existen referencias erróneas al atributo `fatigue_type` en `_real_ev`:
- **Línea 280:** `fatigue={_real_ev.fatigue_type}` $\to$ Falla silenciosamente atrapado por el bloque `try...except` (L283).
- **Línea 330:** `fatigue={_real_wave_ev.fatigue_type}` $\to$ Funciona correctamente (`RealWaveEVSignal` sí lo implementa).
- **Línea 653:** `if _real_ev and (_real_ev.ev <= -0.0020 or _real_ev.fatigue_type == "FATIGUE_RISK"):` $\to$ **CRASH POTENCIAL EN RUNTIME**. No está dentro de un bloque `try...except`. Si se evalúa la condición de TRIM con `_real_ev` activo, arroja `AttributeError: 'RealEVSignal' object has no attribute 'fatigue_type'`.

**Conflicto de Vocabularios de Fatiga:**
- **Wave EV (`RealWaveEVSignal`):** Usa `ACCUMULATING`, `FATIGUE_RISK`, `STABLE` (derivado de longitud de racha en micro-olas).
- **Multiscale (`MultiscaleEVKinematicSignal`):** Usa `kinematic_trajectory` con valores `ABSORBING` ($\Delta\sigma_{vw} > 0.30$), `EXHAUSTING` ($\Delta\sigma_{vw} < -0.30$), `STABLE`.
- **Tide EV (`RealEVSignal`):** No implementa fatiga.

El rediseño debe resolver este desacople: unificar la taxonomía de fatiga o dotar a `RealEVSignal` de un atributo homogéneo.

---

### 1.6. Hallazgos Empíricos de Divergencia de Horizontes (Knowledge Item `ev-horizon-divergence`)

La relación estadística entre el modelo de ZigZag (ZZ-EV) y el modelo de Triple Barrier (TB-EV) arroja hechos cuantitativos validados:
- **Tasa de acuerdo direccional:** 80% (196 de 245 estados L3 concuerdan en signo).
- **La divergencia se concentra en los extremos VWAP:**
  - En suelo `<<` (`FLOOR`): **31% de divergencia**.
  - En techo `>>` (`CEILING`): **29% de divergencia**.
  - En centro `~` (`NEUTRAL`): **92% de alineamiento** (solo 8% de divergencia).
- **Patrones operativos de divergencia:**
  1. *Patrón A (Rebote Táctico, TB+ / ZZ-):* Ocurre en `<<` con Tide bajista (`T---`, `T--`). El modelo TB captura el rebote de reversión a la media (1-5 días), mientras ZZ proyecta la continuación de la tendencia mayor.
  2. *Patrón B (Hold Estructural, ZZ+ / TB-):* Ocurre en `>>` con Current alcista (`C++`, `C+++`). Los stops mecánicos ajustados de TB fallan por volatilidad en el techo, pero el horizonte amplio de ZZ captura la tendencia secular.
- **Impacto para la Escala Adaptativa:** Un umbral VWAP global estático causa que activos de alta volatilidad residan artificialmente en `<<` y `>>`, distorsionando la detección de divergencia de horizontes. La escala adaptativa por ticker normaliza el espacio VWAP a la varianza real del activo.

---

### 1.7. Coincidencia Empírica de Escalas ZigZag con Amplitud Sectorial S5 (KI `zz-s5-breadth-coincidence`)

Sobre 2,652 giros analizados en 11 sectores durante 5 años, las 3 escalas ZigZag se corresponden de manera exacta con los marcos temporales de amplitud:
- **ZZ 2.5%** $\longleftrightarrow$ **S5_TW** (Amplitud táctica a 20 días): **62.4%** de coincidencia.
- **ZZ 5.0%** $\longleftrightarrow$ **S5_FI** (Amplitud intermedia a 50 días): **77.1%** de coincidencia.
- **ZZ 7.5%** $\longleftrightarrow$ **S5_TH** (Amplitud estructural a 200 días): **85.0%** de coincidencia.
- Los sectores **defensivos/activos** (XLU 95.5%, XLRE 95.2%, **XLF** 94.7% financieras, XLE 94.7% energía — tabla de horizonte 7.5%) presentan coincidencia casi perfecta, mientras que sectores de crecimiento (XLK 68.4%) demandan features cinemáticas complementarias.
- Esto valida empíricamente por qué se deben **preservar mandatoriamente las 3 escalas `zz25`, `zz50` y `zz75`**.

---

### 1.8. ✅ REQUISITOS HEREDADOS DEL P0 (RESUELTO — commit `e2a2ada`, 30-Sep-2026)
El fix de `p_bull` reveló verdades que el **sistema NUEVO debe incorporar de nacimiento**. *(Fix aplicado y verificado: commit `e2a2ada`, 30-Sep-2026. JSONs regenerados.)*
1. **`p_bull = P(MAX) = n_pos/n_tot`** ✅ RESUELTO. Bug original: commit `9823194` (27-Jul-2026). Corregido en `e2a2ada`. → **El generador nuevo DEBE mantener la fórmula explícitamente.**
2. **Decisión de tesis: MOMENTUM** ✅ ADJUDICADA. Con `p_bull=P(MAX)`, el **EV relativo** (E[R]−L0, L0=+0.0247) muestra: `<<` (FLOOR) = **−0.0268**, `>>` (CEILING) = **+0.0228** → **momentum**. El Arquitecto ha declarado: **el sistema EV mide la probabilidad de que el momentum continúe**. El EV absoluto es drift (todo positivo, no discrimina); el relativo discrimina monotónicamente.
3. **Discriminación vía `EV relativo (E[R]−L0)`** MANDATORIO. Valores verificados post-fix:
   - EV por VWAP: `<<` −0.0021 · `<` +0.0184 · `~` +0.0236 · `>` +0.0290 · `>>` +0.0475 (absolutos)
   - EV por T: T--- +0.0134 … T+ +0.0373 (pico) … T+++ +0.0338
   - Gradiente máximo T~→T+ = **+0.0139** (robusto al fix, era +0.0138 pre-fix)
   - El EV relativo se incorpora como campo explícito en el Fact Store v2.
4. **Los UMBRALES D-001..D-015 son THROWAWAY** — no se recalibran sobre las escalas viejas. Se recalibran como parte del sistema nuevo con escalas gaussianas y tesis momentum.

### 1.9. ✅ DECISIONES DE BINS (Arquitecto, 30-Sep-2026)
El análisis de escalas gaussianas (artefacto `analisis_escalas_gaussianas_tide.md`) concluyó con las siguientes decisiones:
1. **T slope → D1 (6 bins):** Captura el gradiente máximo de EV en la zona neutra (T~→T+ = +0.0139). El plateau T+/T++ (ΔEV = −0.0002) confirma que fusionar bins no pierde señal.
2. **C slope → D1 (6 bins):** Mismo argumento. Distribución casi simétrica (skew IQR = 1.033).
3. **VWAP sigma_wave → D1 (6 bins):** Corrección crítica de la distribución patológica (bin `>>` = 34.6% de la población). El EV relativo es perfectamente monotónico por VWAP.
4. **Espacio de estados resultante:** 6 × 6 × 6 = **216 estados L3** (vs 245 actual). Densidad muestral: ~21,085 obs/celda (+13% vs actual). Con pooling F1: 4,554,321 / 216 = ~21,085.
5. **Formato de llave:** La llave cambia de formato para acomodar los 6 bins VWAP. Los 5 lookups de `swing_gate.py` se adaptan como parte de la migración v2.
6. **Percentiles gaussianos canónicos (D1):** `[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]` — 5 edges, 6 bins.
7. **σ-Index firmado como sistema de naming** (propuesta del Arquitecto, 30-Sep-2026): Los bins se identifican por enteros con signo que representan σ: `+3, +2, +1, −1, −2, −3` (6-bin, sin 0) y `+3, +2, 0, −2, −3` (5-bin, con 0 = centro). Los labels son **posicionalmente consistentes** entre esquemas: ±3 siempre significa "más allá de ±2σ", ±2 siempre significa "entre ±1σ y ±2σ". La única diferencia es que 6-bin subdivide el centro (±1σ) en dos bins (±1), mientras 5-bin lo unifica como 0. Ver §10.5 (PC-06) para detalles.

---

## 2. REQUISITO CENTRAL — ESCALA GAUSSIANA ADAPTATIVA POR TICKER

> *"…que la escala Gaussiana sea calculada para cada ticker, antes de proceder a procesarlo y sumarlo a la estadística, entendiendo que hay activos más volátiles… memorizadas en un archivo para que el sistema sea adaptativo a cada símbolo; y contabilizadas estadísticamente de acuerdo a su correspondiente familia una vez sean adecuadamente escaladas."*

El diseño debe descomponer y formalizar esta directiva:

### 2.0-bis. Registro Canónico de Dimensiones (verificado contra JSONs, 01-Oct-2026)

> **Fuente:** Extracción directa de `rc_tide_ev_derived.json`, `rc_wave_ev_derived.json`, `rc_ev_multiscale_tree.json`, `rc_vol_normalized_thresholds.json`, `rc_wave_lookup.py` L174/L206, `rc_multiscale_ev_lookup.py` L88.

| # | Dimensión | Variable cruda | Archivo(s) v1 | Bins v1 | Tipo de escala v1 | σ-index v2 | Target v2 |
|:-:|:----------|:---------------|:------|:---:|:-------------------|:---:|:---:|
| 1 | **T** (tide_slope_norm) | `slope_norm` Tide 240d | Tide, Multiscale s1/s3 | 7 | Cuantil empírico (p2.5–p97.5) | `±3,±2,±1` | **6-bin gaussiano** |
| 2 | **C** (current_slope_norm) | `slope_norm` Current 60d | Tide, Multiscale s1/s3 | 7 | Cuantil empírico (p2.5–p97.5) | `±3,±2,±1` | **6-bin gaussiano** |
| 3 | **W** (wave_slope_norm) | `slope_norm` Wave 15d | Wave (L3/L2/L1), Multiscale s1/s3 | 6¹ | Cuantil empírico (p2.5–p97.5) | `±3,±2,±1` | **6-bin gaussiano** |
| 4 | **VWAP** (vwap_sigma_wave) | `sigma_vwap` (σ vs VWAP Wave) | Tide² | 5 | Estático fijo (±0.30, ±1.0) | `±3,±2,±1` | **6-bin gaussiano** |
| 5 | **σVc** | `sigma_vwap_current` | Wave (L2/L1) | 5 | Cuantil empírico (p2.5–p97.5) | `±3,±2,0` | **5-bin gaussiano** |
| 6 | **σc** | `sigma_current` | Wave (L1) | 5 | Cuantil empírico (p2.5–p97.5) | `±3,±2,0` | **5-bin gaussiano** |
| 7 | **σVw** | `sigma_vwap_wave` | Multiscale s1 (dim 4) | 5 | Cuantil empírico (p2.5–p97.5) | `±3,±2,0` | **5-bin gaussiano** |
| 8 | **ΔσVw** | `delta_sigma_vwap_wave` | Multiscale s1 (dim 5) | 5 | Cuantil empírico (p2.5–p97.5) | `±3,±2,0` | **5-bin gaussiano** |
| 9 | **vel** (vel_σVw) | `vel_svw` (velocidad de σVw) | Wave (L1, dim 3) | 3 | **Direccional** (threshold ±0.091) | `+1,0,−1` | **3-estado sign-index** |
| 10 | **traj** (#FATIGUE) | `delta_svw` (Δ de σVw) | Multiscale s1/s3 (sufijo #) | 3 | **Direccional** (threshold ±0.30) | `+1,0,−1` | **3-estado sign-index** |

> **Notas verificadas:**
> 1. W en Wave EV tiene 6 bins (sin `W~`); W en Multiscale s3 tiene 7 bins (`W~` presente). Ambos migran a 6-bin gaussiano v2.
> 2. VWAP aparece solo en Tide EV, no en Wave ni Multiscale.
> 3. **⚠️ Corrección crítica:** ΔσVw (dim 5, 5-bin cuantil `<</</../>/>>`) y traj/FATIGUE (sufijo #, 3-estado `ABSORBING/STABLE/EXHAUSTING`) son **dimensiones separadas** derivadas de variables relacionadas pero con binning distinto. ΔσVw usa cuantiles empíricos; FATIGUE usa threshold fijo ±0.30 sobre `delta_svw`.
> 4. Las dimensiones cuantiles (filas 1–8) reciben escalas gaussianas per-ticker (σ-index firmado). Las dimensiones direccionales (filas 9–10) preservan su threshold fijo — son derivadas, no cuantiles.
> 5. El Multiscale s1_full tiene 7 dimensiones efectivas: T×C×W×σVc×σVw×ΔσVw × FATIGUE (6 cuantiles + 1 direccional). El s3_triad colapsa a 4: T×C×W × FATIGUE.

### 2.0-ter. Auditoría de Umbrales de Velocidad — vel (Wave) y traj/FATIGUE (Multiscale) (01-Oct-2026)

> **Hallazgo:** Las dimensiones vel y traj/FATIGUE consumen la **misma variable cruda** en producción (`swing_gate.py` L297: `delta_svw=_vel_svw`), pero usan **umbrales radicalmente distintos** con provenance diferente.

**Trazabilidad verificada por archivo:**

| Aspecto | vel (Wave) | traj/FATIGUE (Multiscale) |
|:--------|:-----------|:--------------------------|
| **Clasificador** | `_classify_vel_svw()` en `rc_wave_lookup.py` L206 | `classify_kinematic_trajectory()` en `rc_multiscale_ev_lookup.py` L88 |
| **Umbral hardcoded** | `(-0.091, 0.091)` — `rc_wave_lookup.py` L174 | `±0.30` — `rc_multiscale_ev_lookup.py` L50 |
| **Umbral vivo (si aplica)** | `(-0.058381, 0.123438)` — `rc_wave_derived.json` vel_thresholds | ❌ Ninguno — ±0.30 es el ÚNICO |
| **Carga dinámica** | ✅ `_load_wave()` L229-234 sobreescribe desde `vel_thresholds` en metadata | ❌ No hay carga dinámica |
| **Calibración** | P33/P67 de `obs_vel_svw` (Kalman) excl. zeros — `train_wave_table.py` L535-553 | Sin calibración empírica documentada |
| **Trainer: variable** | `obs_vel_svw` (Kalman) directo de DB | `σVw_t0 - σVw_{t-2}` (diferencia de posición, no Kalman) — `train_multiscale_kinematic_ev_tree.py` L282 |
| **Producción: variable** | `_vel_svw` = `obs_vel_svw` (Kalman) — `swing_gate.py` L806,L150 | `_vel_svw` = **misma variable** — `swing_gate.py` L297 |

**Percentiles LIVE de `obs_vel_svw` (Kalman) — medido contra `engine.channel_snapshots`:**
```
P33 = -0.130758    P50 = -0.004765    P67 = +0.120383    (N = 405, excluyendo zeros)
```

**Diagnóstico (3 defectos verificados):**

1. **⚠️ Umbral prestado:** El `±0.30` del Multiscale **NO es un percentil de `delta_svw` ni de `obs_vel_svw`**. Es el edge `~/>`  de la dimensión VWAP position (`vwap_sigma_wave_position` en Wave EV: "NEUTRAL = ±0.30"). Un umbral de **posición** aplicado a una **velocidad** — sin justificación empírica.

2. **⚠️ Train-Serve Skew:** El trainer del Multiscale computa `delta_svw = σVw_t - σVw_{t-2}` (diferencia discreta de posiciones). En producción, `swing_gate.py` pasa `obs_vel_svw` (Kalman velocity) — una variable **distinta** con distribución diferente. El ±0.30 fue calibrado (si acaso) para la primera, pero se aplica a la segunda.

3. **⚠️ Fallback stale:** `_VEL_SVW_TH = (-0.091, 0.091)` en `rc_wave_lookup.py` L174 es el valor original EMA. El trainer de Wave lo sobreescribe dinámicamente a `(-0.058, +0.123)` vía P33/P67 Kalman, pero `rc_wave_ev_derived.json` **no contiene `vel_thresholds`** (solo `rc_wave_derived.json` y `rc_wave_probability_table.json` lo tienen). Si `rc_wave_ev_lookup.py` carga el JSON ev_derived, usará el fallback stale.

**Ratio de discrepancia:** `|±0.30| / |P33| ≈ 2.3×`, `|±0.30| / |P67| ≈ 2.5×`. El Multiscale clasifica como STABLE (neutro) observaciones que Wave clasificaría como ▲ o ▼ (extremas). Esto infla artificialmente STABLE en el Multiscale.

**Directivas para v2 (sin cambiar nro. de estados):**

1. **Umbral ÚNICO canónico:** vel (Wave) y traj (Multiscale) deben compartir el mismo umbral calibrado a la misma variable. Si la variable es `obs_vel_svw` (Kalman), el umbral debe ser P33/P67 de `obs_vel_svw` — no ±0.30.
2. **Eliminar train-serve skew:** El trainer del Multiscale debe usar `obs_vel_svw` (Kalman), no `σVw_t - σVw_{t-2}`, para alinear con producción.
3. **Per-ticker adaptativo (opcional):** Si vel/traj adoptan tratamiento gaussiano, los thresholds salen de `ticker_gaussian_profiles.json` (P33/P67 per-ticker). Si se mantiene como 3-estado con threshold fijo, el threshold debe ser empírico global (P33/P67 del censo).
4. **vel sigue siendo 3-estado** — lo que cambia es la calibración del umbral, no la dimensionalidad.
5. **`vel_thresholds` debe propagarse** a `rc_wave_ev_derived.json` — hoy solo está en `rc_wave_derived.json`.

**⚠️ Defecto RAÍZ de la dimensión de velocidad (verificado 01-Oct-2026):**

`obs_vel_svw` existe en solo **17 de 562 tickers** (3.0%) en `engine.channel_snapshots`. Los 17 tickers son: AAPL, AMZN, COST, HD, HON, IBM, JNJ, JPM, MCD, MRK, MSFT, PEP, PG, QQQ, SPY, WMT, XOM. El rango de datos es **2026-07-15 a 2026-10-01** (~78 días, 422 observaciones totales, ~25 barras/ticker). El Observer (Kalman) no se backfilleó sobre el universo.

**Consecuencias verificadas:**

| # | Consecuencia | Evidencia |
|:-:|:-------------|:----------|
| a | Los P33/P67 se calibraron sobre un **demo de ~25 barras/ticker × 17 tickers** — no un censo | `train_wave_table.py` L540-545: query WHERE `obs_vel_svw IS NOT NULL AND != 0` → 422 filas |
| b | En producción, `_vel_svw = 0.0` para el **97% de los tickers** (545/562) | `swing_gate.py` L798-806: default `(0.0, 0.0)` → vel siempre clasificado como `~` |
| c | El trainer cae a `EMA(5).diff()` mientras los umbrales provienen del Kalman | `train_wave_table.py` L286-289: fallback a EMA(5).diff() cuando `obs_vel_svw IS NULL`; umbrales P33/P67 de Kalman → calibración ≠ aplicación |
| d | El Multiscale usa `σVw_t - σVw_{t-2}` en training pero `obs_vel_svw` en producción | `train_multiscale_kinematic_ev_tree.py` L282 vs `swing_gate.py` L297 → train-serve skew |
| e | La calibración per-ticker de vel/traj es **imposible** con los datos actuales | 17 tickers × ~25 barras → insuficiente para percentiles per-ticker |

**Directivas propuestas (a adjudicar por el Arquitecto — NO decidir):**

1. Ejecutar el backfill del Observer sobre los 562 tickers × histórico completo.
2. Recalcular P33/P67 sobre el CENSO (post-backfill).
3. Unificar el umbral de vel (Wave) y traj (Multiscale) — es la misma variable.
4. Propagar `vel_thresholds` a `rc_wave_ev_derived.json`.
5. Mientras no exista backfill, la calibración de la velocidad no puede ser per-ticker.

> **Nota de trazabilidad del umbral fallback:** `rc_wave_ev_lookup.py` importa `_classify_vel_svw` DE `rc_wave_lookup.py` (L98), que carga `rc_wave_derived.json`. Este archivo SÍ contiene `vel_thresholds = {lower: -0.058381, upper: 0.123438}`, y `_load_wave()` (L229-234) los sobreescribe al fallback `(-0.091, 0.091)` de L174. Por tanto, **en flujo normal el umbral vivo funciona** — el fallback stale `(-0.091, 0.091)` solo se activa si `rc_wave_derived.json` no se carga.


### 2.1. Derivación Matemática Per-Ticker (Cumplimiento Regla S1)
La **Regla S1 de `gaussian_scale_policy.md`** prohíbe el uso de fórmulas paramétricas ($\mu \pm k\sigma$) sobre series financieras no normales con colas pesadas. La calibración per-ticker debe basarse en **cuantiles empíricos** sobre el histórico disponible del activo en el Neon Vault.

Se deben evaluar formalmente 3 formulaciones matemáticas. **Los edges para T, C y VWAP son los 5 percentiles D1 gaussianos canónicos** `[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]` generando **6 bins** cada uno:
- **Opción A (Cuantiles Empíricos Per-Ticker Directos):** Para cada ticker $i$ y canal $k \in \{T, C, W, VWAP\}$, calcular el vector de percentiles empíricos D1 sobre su propia serie histórica:
  $$\mathbf{Q}_i = \text{Quantile}\left( X_{i,k}, [0.0228, 0.1587, 0.5000, 0.8413, 0.9772] \right)$$
- **Opción B (Transformada Gaussiana Canónica vía Percentile Rank / Probability Integral Transform):**
  Calcular el rank empírico $U_{i,t} = \frac{\text{Rank}(X_{i,t})}{N_i + 1}$ y mapearlo a normalidad estándar:
  $$Z_{i,t} = \Phi^{-1}(U_{i,t})$$
  Luego clasificar contra los umbrales fijos estándar $[-1.96, -0.99, 0.0, +0.99, +1.96]$. Esto homogeniza matemáticamente todos los activos al mismo espacio latente $\mathcal{N}(0, 1)$.
- **Opción C (Regularización Bayesiana / Shrinkage de Umbrales):**
  $$\mathbf{Q}_{i, \text{shrunk}} = \frac{N_i}{N_i + K} \mathbf{Q}_i + \frac{K}{N_i + K} \mathbf{Q}_{\text{global}}$$
  Evita que activos con pocas muestras ($N_i < 1,000$ barras) sufran distorsión en sus percentiles extremos.

### 2.2. Momento y Pipeline de Transformación
La observación individual $(X_{i,t})$ se normaliza contra el perfil adaptativo del ticker **en tiempo de entrenamiento** *antes* de mapearla al estado discreto.
- ¿Altera la escala adaptativa la **clave de estado**?
  - *Sí:* Un valor de pendiente que globalmente sería `T++` para un activo hipervolátil se reclasifica como `T+` porque para su distribución particular no es un evento de cola. La llave de estado pasa a representar **intensidad relativa al activo**, logrando comparabilidad universal entre activos.

### 2.3. Persistencia y Memorización (`ticker_gaussian_profiles.json`)
Definir la estructura del archivo de calibración persistente:
- **Estructura propuesta (actualizada para D1 6-bin en T, C, VWAP + overflow anchors + inception):**
  ```json
  {
    "_metadata": {
      "calibrated_at": "2026-09-30T00:00:00Z",
      "methodology": "empirical_quantiles_expanding_window",
      "scale_type": "D1_gaussian_6bin",
      "percentiles": [0.0228, 0.1587, 0.5000, 0.8413, 0.9772],
      "overflow_anchors": [0.00135, 0.99865],
      "n_tickers": 531
    },
    "profiles": {
      "SPY": {
        "inception_date": "1993-01-29",
        "n_bars": 8420,
        "min_valid_date": "1994-01-29",
        "tide_slope_norm": {"p0_135": -11.20, "p2_28": -5.12, "p15_87": -2.80, "p50": 1.85, "p84_13": 4.20, "p97_72": 9.95, "p99_865": 16.80},
        "current_slope_norm": {"p0_135": -22.40, "p2_28": -9.30, "p15_87": -5.10, "p50": 2.10, "p84_13": 5.90, "p97_72": 16.20, "p99_865": 28.50},
        "vwap_sigma_wave": {"p0_135": -2.80, "p2_28": -1.85, "p15_87": -0.92, "p50": 0.02, "p84_13": 0.95, "p97_72": 1.90, "p99_865": 2.65},
        "wave_slope_norm": {"p0_135": -18.90, "p2_28": -12.10, "p15_87": -5.80, "p50": 2.97, "p84_13": 11.40, "p97_72": 22.50, "p99_865": 35.20}
      }
    }
  }
  ```
  > **Nota:** Los 7 percentile anchors (P0.135 a P99.865) cubren ±3σ: los 5 internos (P2.28–P97.72) definen los 6 bins D1; los 2 extremos (P0.135 y P99.865) habilitan el cálculo de z-score de overflow (ver §10.1, PC-02). Se incluyen `inception_date`, `n_bars`, `min_valid_date` para la política de inception (ver §10.2, PC-03).
- **Ubicación en Clean Architecture:** `backend/modules/quality_swing/domain/rules/ticker_gaussian_profiles.json`.
- **Gobernanza:** Archivo estático versionado en git, regenerado mediante script por evento o cadencia trimestral.
- **Ruta canónica:** `backend/modules/quality_swing/domain/rules/ticker_gaussian_profiles.json`.

> **⚠️ Auditoría de cobertura dimensional (01-Oct-2026):** El schema actual define anchors per-ticker para **4 de 10 dimensiones** del sistema. Las 6 restantes NO tienen entrada en el perfil ni scope declarado. Esta tabla documenta el estado y la decisión de scope por dimensión:

**Tabla de Scope por Dimensión (verificada contra §2.0-bis):**

| # | Dimensión | Familia | Calibración | Schema per-ticker | Fuente actual | Justificación |
|:-:|:----------|:-------:|:-----------:|:-----------------:|:--------------|:--------------|
| 1 | **T** (tide_slope_norm) | 6-bin | **Per-ticker** | ✅ 7 anchors (p0.135–p99.865) | `channel_snapshots` (8K+ barras/ticker) | Variable de escala → cuantiles empíricos per-ticker (Rule S1) |
| 2 | **C** (current_slope_norm) | 6-bin | **Per-ticker** | ✅ 7 anchors | Ídem | Ídem |
| 3 | **W** (wave_slope_norm) | 6-bin | **Per-ticker** | ✅ 7 anchors | Ídem | Ídem |
| 4 | **VWAP** (vwap_sigma_wave) | 6-bin | **Per-ticker** | ✅ 7 anchors | Ídem | Ídem |
| 5 | **σVc** | 5-bin | **Global** | ❌ No incluido | `rc_vol_normalized_thresholds.json` (4.57M obs) | Censo completo ya disponible; per-ticker posible pero no prioritario |
| 6 | **σc** | 5-bin | **Global** | ❌ No incluido | Ídem | Ídem |
| 7 | **σVw** | 5-bin | **Global** | ❌ No incluido | Ídem | Ídem |
| 8 | **ΔσVw** | 5-bin | **Global** | ❌ No incluido | Ídem | Ídem |
| 9 | **vel** (vel_σVw) | 3-estado | **Global** (P33/P67) | ❌ No aplica (no cuantil) | `obs_vel_svw` Kalman (422 obs, 17 tickers — ver §2.0-ter) | Threshold direccional, no cuantil percentil |
| 10 | **traj** (#FATIGUE) | 3-estado | **Global** (±0.30 hardcoded) | ❌ No aplica (no cuantil) | Sin calibración empírica (ver §2.0-ter) | Threshold direccional prestado de VWAP position |

> **Naturaleza de los valores de ejemplo (SPY):** Los valores de percentiles en el ejemplo JSON anterior (L276-279) son **ILUSTRATIVOS, NO medidos**. SPY tiene 8,231 barras en `engine.channel_snapshots` (1994-01-18 a 2026-10-01) → la calibración real es factible pero NO se ha ejecutado. Los valores deben reemplazarse por cifras medidas cuando se implemente el calibrador.



### 2.4. Contabilización por FAMILIA
Una vez clasificada la observación en su estado relativo, se acumula en el Fact Store. El diseño debe formalizar qué constituye una "Familia":

| Modelo de Familia | Definición Operativa | Pros | Contras | Densidad Muestral Esperada ($N$ medio / celda, 216 estados) |
|---|---|---|---|:---:|
| **F1: Pooling Universal (Estado Compartido)** | Un único pool de **216** estados donde cada ticker entra con su estado normalizado per-ticker. | Máximo soporte muestral; varianza mínima en probabilidades; respeta Rule 14. | Asume que un bin 5 normalizado tiene idéntico payoff en Utilities que en Tech. | **$\sim 21,100$** obs / celda ($4.55\text{M} / 216$) |
| **F2: Clustering por Sector GICS (11 Sectores)** | 11 tablas independientes (o dimensión sectorial en llave). | Captura dinámicas macrosectoriales y rotación. | Fragmentación: $216 \times 11 = 2,376$ celdas. Incrementa estados raros. | **$\sim 1,916$** obs / celda |
| **F3: Clases de Volatilidad (4 Cuartiles ATR%)** | Tickers agrupados en: LOW_VOL, MED_VOL, HIGH_VOL, ULTRA_VOL según su mediana de `atr_pct`. | Agrupa activos con cinemática similar sin sesgo por industria. | Fronteras de cuartil arbitrarias; saltos de clase en rebalanceos. | **$\sim 5,270$** obs / celda |
| **F4: Per-Ticker Puro (Sin Pooling)** | Cada ticker tiene su propia tabla de 216 estados. | Máxima especificidad. | **Estadísticamente inviable:** 500 tickers $\times$ 9,000 barras $\to$ $N$ insuficiente en colas ($< 20$ obs/celda). Ruido total. | **$< 20$** obs / celda (Inviable) |

**El diseño debe fundamentar la elección (o combinación híbrida de F1 + modificadores de F2/F3).**

### 2.5. Preservaciones Obligatorias
- **Escalas ZigZag canónicas:** Mantener intactas `zz25` (2.5%), `zz50` (5.0%) y `zz75` (7.5%).
- **Formato de claves (σ-index firmado):** La clave v2 usa σ-index firmado: `"3__1__-2"` (Rule 24, numérico) con label auxiliar `"T+3|C+1|V-2"` (humano). El σ-index codifica dirección (signo) y magnitud (|valor|) en unidades de σ. Para 6-bin: `+3,+2,+1,−1,−2,−3` (sin 0). Para 5-bin: `+3,+2,0,−2,−3` (0 = centro). Los labels son posicionalmente consistentes: ±3 y ±2 refieren a la misma posición gaussiana en ambos esquemas. Los 5 lookups de `swing_gate.py` se adaptan como parte de la migración v2.
- **Separación Hechos vs Directivas:** Los JSON contienen strictly mediciones empíricas (`p_bull`, `ev`, `sharpe`, `n`); las decisiones tácticas (`ACCUMULATE`, `TRIM`, `BUY_DIP`) residen exclusivamente en los adaptadores puros de dominio (`rc_tide_ev_lookup.py`).
- **Tesis MOMENTUM:** El sistema EV mide la probabilidad de que el momentum continúe. `p_bull = P(MAX) = n_pos/n_tot`. El EV relativo (`ev_rel = ev_net - L0_baseline`) es el campo discriminante principal.
- **Campo `ev_rel` obligatorio en v2:** Cada estado debe incluir `ev_rel` = `ev_net` − L0 del mismo scale (zz25/50/75). Sin este campo, el EV absoluto no discrimina por drift secular.
- **Taxonomy completa (Rule 21):** Todo JSON v2 debe incluir `_documentation.taxonomy` con `sigma_labels`, `percentiles`, `value_edges_global` por dimensión (ver §10.4, PC-05).

## 3. ANÁLISIS MULTI-PUNTO DE VISTA OBLIGATORIO (8 Lentes)

El entregable de diseño **(D)** debe recorrer exhaustivamente estos 8 lentes, detallando ventajas, riesgos y decisiones:

1. **Lente Estadístico y Metrológico:**
   - Comparación formal de sesgo y varianza: pooling global vs per-ticker.
   - De-clustering temporal y embargo: corrección por autocorrelación serial de pivotes ZigZag adyacentes.
   - Shrinkage Bayesiano jerárquico ($L3 \to L2 \to L1 \to L0$) con ponderador de prior adaptativo.
   - Manejo de intervalos de confianza (CI 95%) y tratamiento formal de muestras bajas ($N < 21$ catalogadas como **Diamantes**, nunca purgadas).
   - Resolución de la tensión del Information Coefficient ($+0.412$ vs $+0.371$).
2. **Lente de Esquemas y Contratos de Datos (Rule 21 y 24):**
   - Especificación completa del bloque `_documentation` con `model_purpose`, `return_formula`, `state_hierarchy`, `taxonomy`, `field_glossary` y `signal_interpretation_policy`.
   - Tratamiento de Overflow: adopción de la escala canónica $T1..T5+$ en metadatos sin desbordar el espacio discreto.
   - Corrección de la deuda documental: erradicar las referencias a "180 estados" y homogenizar la definición de `p_bull` como $P(\text{MAX})$.
3. **Lente METAR $\to$ Tide/Wave (Isomorfismo vs Geometría Propia):**
   - Qué adoptar: percentiles Gaussianos canónicos $[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]$, rigor en fechas de incepción y persistencia de estados.
   - Qué NO adoptar: evitar forzar el esquema 1D de METAR ($D1 \times D2 \times D3$) en la geometría multicanal de Tide/Wave ($T \times C \times W \times \text{VWAP}$).
   - Explotar la ventaja de repetición y ergodicidad de estados cinemáticos.
4. **Lente Arquitectónico y de Integración en el Pipeline:**
   - Resolución de la duda del Arquitecto: *¿Corresponde construir una serie paralela para conectar posteriormente?*
   - Análisis de convivencia: `rc_tide_ev_derived_v2.json` en paralelo vs reemplazo atómico con script de rollback.
   - Impacto y compatibilidad hacia atrás en los 5 lookups de `swing_gate.py` (§1.4).
5. **Lente de Regímenes y Confluencia de Señales Especiales:**
   - Integración formal con `market.regime_states` a través de `RegimeStatePort` (Rule 15, 16, 17).
   - Tratamiento disciplinado de señales extremas (confluencias raras de colas no son outliers, son gatillos de régimen).
6. **Lente de Robustez y Riesgos Cuantitativos:**
   - Blindaje contra Look-Ahead Bias: ventanas de estimación estrictamente causales ($t \le \tau$).
   - Mitigación del sesgo de régimen secular (bull run post-2020 inflando el EV).
   - Plan de validación Out-Of-Sample (Walk-Forward con purga de embargos).
7. **Lente de Estacionariedad Temporal de Cuantiles Per-Ticker:**
   - Evaluación de ventanas: Censo completo histórico vs Ventanas móviles (Rolling 3-5 años).
   - Gestión de rupturas estructurales en activos que mutan de perfil de volatilidad (ej. TSLA pre/post-inclusión en S&P 500, NVDA pre/post-boom de IA).
8. **Lente de Dinámica de Horizontes (Horizon Divergence en Extremos VWAP):**
   - Incorporación de las reglas de divergencia (ZZ-EV abierto vs TB-EV 10d).
   - Preservación de la precisión en los extremos `<<` y `>>`, evitando que la adaptación por ticker enmascare situaciones de estrés de liquidez.

---

## 4. ESPECIFICACIÓN DE ENTREGABLES FORMALES

El agente que ejecute este prompt debe generar exactamente **DOS artefactos**:

### Artefacto 1: Documento de DISEÑO ARQUITECTÓNICO (D)
Documento Markdown estructurado que contenga:
- **Especificación formal del nuevo esquema de datos** para Tide EV, Wave EV y Multiscale, con tablas de deltas exactas respecto al código actual.
- **Formulación matemática rigurosa** del proceso de calibración adaptativa per-ticker.
- **Definición operativa y cuantitativa de "Familia"** con la distribución esperada de muestras por celda.
- **Especificación de persistencia** (`ticker_gaussian_profiles.json`), protocolo de regeneración y costos computacionales.
- **Matriz de decisiones arquitectónicas:** Tabla con Opción Elegida, Alternativa Descartada, Justificación Matemática y Riesgo Aceptado.
- **Plan de migración y mitigación de fallos:** Estrategia para los 5 lookups de `swing_gate.py` y resolución del bug `fatigue_type`.

### Artefacto 2: PROMPT DE CONSTRUCCIÓN AUTÓNOMO (P)
Prompt de ejecución self-contained listo para despachar al agente implementador, conteniendo:
- 🔴 **Archivos de Referencia Obligatorios** con líneas de inspección precisas.
- **Límites de Scope Positivos y Negativos**.
- **Criterio de Aceptación** mediante checkboxes atómicos y verificables.
- **Banco de Autotests con comandos Bash ejecutables** que validen matemáticamente la salida antes de declarar éxito.

---

## 5. ARCHIVOS DE REFERENCIA Y MAPA DE DEPENDENCIAS

### 🔴 Obligatorios (De obligada consulta previa al diseño)
| Archivo | Rol en el Sistema | Aspecto Clave a Inspeccionar |
|---|---|---|
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json` | Fact Store Tide EV activo | Verificar 245 estados L3 reales vs texto de 180 en `_documentation`. |
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_probability_table.json` | Tabla de frecuencias base | Muestras brutas ($4.55\text{M}$) y estructura de sumas `zz25/50/75`. |
| `backend/modules/quality_swing/domain/rules/rc_vol_normalized_thresholds.json` | Umbrales globales de volatilidad | Percentiles estáticos globales para slopes y vwap. |
| `backend/modules/quality_swing/domain/rules/rc_slope_classifier.py` | Clasificador de slopes en dominio | L78-102: Mecánica de clasificación de 7 niveles T/C y 6 niveles W. |
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_lookup.py` | Adaptador de consulta de dominio | Contrato `RealEVSignal` y docstrings desfasados. |
| `backend/scripts/trainers/train_tide_ev_real_table.py` | Script de entrenamiento | L253-254: Aplicación de umbrales globales que originan la deuda. |
| `backend/scripts/generators/generate_tide_ev_real_derived.py` | Generador con Shrinkage | L62-63 (`p_bull`), L156-186 (`_documentation` desactualizada). |
| `.agents/references/metar/gaussian_scale_policy.md` | Política Gaussiana institucional | Regla S1 (cuantiles empíricos) y definición canónica de extremos. |
| `backend/modules/entry_decision/domain/rules/sigma_overflow.py` | Módulo de validación de overflow | L36-52: Edges empíricos por estación (VIX $P97.72 = 40.7336$). |

### 🟡 Secundarios y Contextuales
| Archivo | Rol en el Sistema | Aspecto Clave a Inspeccionar |
|---|---|---|
| `backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json` | Fact Store Wave EV | Jerarquía invertida (L1 granular, L3 rollup) y ausencia de `W~`. |
| `backend/modules/quality_swing/domain/rules/rc_wave_ev_lookup.py` | Adaptador Wave EV | Implementación de `fatigue_type` (`ACCUMULATING`, `FATIGUE_RISK`). |
| `backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json` | Árbol multiescala 6D | Estructura de 25,797 estados y sufijos `#FATIGUE`. |
| `backend/modules/quality_swing/domain/rules/rc_multiscale_ev_lookup.py` | Adaptador Multiescala | Función `classify_kinematic_trajectory` (`ABSORBING`, `EXHAUSTING`). |
| `backend/modules/quality_swing/application/use_cases/swing_gate.py` | Caso de uso orquestador | L280, L330, L653: Bug de `fatigue_type` e integración de 5 lookups. |
| `docs/research/01_señales_entry_exit/medicion_vix_crisis_spike.json` | Auditoría de señal VIX | Datos empíricos de las 171 alertas globales y tasa de acierto. |
| `backend/scripts/per_ticker_turn_forensics.py` | Script forense per-ticker | Análisis de LIFT empírico sobre pivotes ZigZag individuales. |

---

## 6. LÍMITES DEL SCOPE

### Lo que este diseño DEBE hacer:
- ✅ Preservar las variables dimensionales establecidas: Tide (`T|C|σVw`), Wave (`W|σVc|σc|vel`), Multiscale (6D + Fatiga).
- ✅ Preservar mandatoriamente las 3 escalas ZigZag canónicas: `zz25`, `zz50` y `zz75`.
- ✅ Diseñar un mecanismo adaptativo basado en cuantiles empíricos (Regla S1), erradicando fórmulas paramétricas $\mu \pm k\sigma$.
- ✅ Establecer una política explícita de Diamantes Estadísticos para $N < 21$ (conservar, etiquetar rareza, nunca descartar).
- ✅ Unificar o armonizar la jerarquía de niveles rollups entre Tide y Wave.
- ✅ Diseñar la solución formal al bug de `fatigue_type` en `swing_gate.py`.
- ✅ Definir la estrategia de despliegue como **serie versionada con puntero atómico** (v2 se genera → se valida → se activa atómicamente al mover el puntero, sin ventana dual de dos vivos).
- ✅ Adoptar el espacio 6×6×6 = **216 estados L3** con escala D1 gaussiana para T, C y VWAP.
- ✅ Declarar tesis MOMENTUM y emitir campo `ev_rel` (EV relativo a L0) en el Fact Store.
- ✅ Adaptar los 5 lookups de `swing_gate.py` al nuevo formato de llave (6 bins por dimensión).

### Lo que este diseño NO DEBE hacer:
- ❌ NO modificar código de producción durante esta etapa de diseño.
- ❌ NO introducir lógica de trading o señales tácticas dentro de los archivos JSON (estricta separación Hechos vs Directivas).
- ❌ NO proponer modelos paramétricos gaussianos teóricos que asuman normalidad en variables con colas pesadas.
- ❌ NO eliminar estados con bajo $N$.
- ❌ NO recalibrar umbrales D-001..D-015 sobre las escalas viejas (son throwaway — se recalibran con el sistema nuevo).

---

## 7. CRITERIO DE ACEPTACIÓN

El trabajo se considerará completo y aprobado únicamente cuando:
- [ ] Existan los dos artefactos: **(D) Documento de Diseño** y **(P) Prompt de Construcción**.
- [ ] La **fórmula de derivación adaptativa per-ticker** esté matemáticamente definida bajo cuantiles empíricos.
- [ ] Se defina la estructura exacta del archivo de calibración `ticker_gaussian_profiles.json`.
- [ ] Esté formalizada la definición de **"Familia"** con sustento cuantitativo de densidad muestral ($N/\text{celda}$).
- [ ] Se documente la transición de 245 estados (v1, 7×7×5) a **216 estados** (v2, 6×6×6 D1 gaussiano) y la armonización de jerarquías Tide vs Wave.
- [ ] Se proponga una solución integral al bug de runtime `fatigue_type` en `swing_gate.py`.
- [ ] Se analicen exhaustivamente los **8 lentes obligatorios** de la Sección 3.
- [ ] El Prompt de Construcción **(P)** contenga un banco de comandos de verificación Bash ejecutables y criterios atómicos.

---

## 8. AUTOTEST Y BANCO DE COMANDOS DE VERIFICACIÓN FÁCTICA

Antes de concluir la propuesta, el agente debe ejecutar y verificar estos comandos en el entorno:

1. **Verificar estados reales de Tide EV v1 (245 L3, con deuda documental de 180) y p_bull corregido:**
   ```bash
   python3 -c "import json; d=json.load(open('backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json')); print(f'L3={len(d[\"l3_full_state\"])} L2={len(d[\"l2_mid_macro\"])} L1={len(d[\"l1_macro\"])} L0_type={type(d[\"l0_global\"]).__name__}'); print('p_bull L0 zz50:', d['l0_global']['zz50']['p_bull']); print('Doc text:', d['_documentation']['state_hierarchy']['L3'])"
   # Salida esperada: L3=245 L2=49 L1=7 L0_type=dict
   # p_bull L0 zz50: 0.5696 (>0.50 = sesgo alcista secular, P(MAX) correcto)
   # Evidencia de deuda: Doc text menciona '(180 granular micro/macro states)'
   ```

2. **Verificar jerarquía invertida y estados en Wave EV:**
   ```bash
   python3 -c "import json; d=json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json')); slopes = set(k.split('|')[0] for k in d['states'].keys()); print('Wave L1 states:', len(d['states'])); print('Wave prefixes:', sorted(slopes)[:6])"
   # Salida esperada: Wave L1 states=479. Prefijos contienen L1:W+++, L1:W++, L1:W+, etc. (NO contiene W~)
   ```

3. **Verificar umbrales globales de entrenamiento (origen de la deuda en Trainer):**
   ```bash
   grep -n "_classify_one" backend/scripts/trainers/train_tide_ev_real_table.py
   # Salida esperada: Líneas 29 y 253-254 utilizando el clasificador global
   ```

4. **Verificar existencia del bug de `fatigue_type` en `swing_gate.py`:**
   ```bash
   grep -c "fatigue_type" backend/modules/quality_swing/domain/rules/rc_tide_ev_lookup.py
   # Salida esperada: 0 (RealEVSignal no tiene fatigue_type)
   grep -n "fatigue_type" backend/modules/quality_swing/application/use_cases/swing_gate.py
   # Salida esperada: Líneas 280, 330 y 653 (L653 susceptible a crash directo)
   ```

5. **Verificar edge global empírico del VIX ($P97.72 = 40.7336$):**
   ```bash
   python3 -c "from backend.modules.entry_decision.domain.rules.sigma_overflow import STATION_EMPIRICAL_EDGES; print('VIX D1 p9772:', STATION_EMPIRICAL_EDGES['vix']['d1']['p9772'])"
   # Salida esperada: VIX D1 p9772: 40.7336
   ```

6. **Verificar episodios históricos de la señal VIX CRISIS_SPIKE ($N=171$):**
   ```bash
   python3 -c "import json; d=json.load(open('docs/research/01_señales_entry_exit/medicion_vix_crisis_spike.json')); print('Activa n:', d['activa']['dist']['n'], 'Baseline n:', d['baseline']['dist']['n'])"
   # Salida esperada: Activa n: 171 Baseline n: 1418
   ```

---

## 9. SÍNTESIS DE DECISIONES CLAVE Y HOJA DE RUTA

### 9.1. Decisiones YA TOMADAS por el Arquitecto (30-Sep-2026)

| # | Decisión | Resolución | Fundamento |
|:-:|:---------|:-----------|:-----------|
| D-P0 | p_bull formula | ✅ `P(MAX) = n_pos/n_tot` | Commit `e2a2ada`, JSONs regenerados |
| D-TESIS | Momentum vs Reversión | ✅ **MOMENTUM** | EV relativo monotónico: CEILING paga (+0.0228 rel), FLOOR pierde (−0.0268 rel) |
| D-T | T slope bins | ✅ **D1 (6 bins)** | Gradiente máximo T~→T+ = +0.0139 robusto al fix |
| D-C | C slope bins | ✅ **D1 (6 bins)** | Mismo argumento, distribución simétrica |
| D-VWAP | VWAP bins | ✅ **D1 (6 bins)** | Corrección patológica >> = 34.6%. EV monotónico |
| D-SPACE | Espacio L3 | ✅ **216** (6×6×6) | +13% densidad muestral vs 245 |
| D-KEY | Formato de llave | ✅ **Evoluciona** | Los 5 lookups se adaptan en la migración v2 |
| D-SIGMA | σ-Index firmado | ✅ **+3,+2,+1,−1,−2,−3** (6-bin) / **+3,+2,0,−2,−3** (5-bin) | Resuelve ambigüedad dirección/magnitud de METAR 0-5; labels posicionalmente consistentes entre esquemas; corrige bug T~ (§10.5) |
| D-DEPLOY | Estrategia de despliegue | ✅ **Serie versionada + puntero atómico** | No paralelo dual ni reemplazo destructivo |
| D-UMBRALES | D-001..D-015 | ✅ **Throwaway** | Se recalibran sobre el sistema nuevo |

### 9.2. Decisiones PENDIENTES para el Documento de Diseño (D)

El documento **(D)** debe cerrar respondiendo con claridad prístina a las preguntas restantes:

1. **¿Qué es formalmente "Familia"?**  
   Declarar si se adopta el pooling universal normalizado (F1), clustering sectorial (F2), o clases de volatilidad por cuartiles ATR (F3), sustentando el balance entre especificidad y significancia estadística ($N/\text{celda}$, ahora sobre 216 estados).
2. **¿Opción A, B o C para la calibración per-ticker?**  
   Evaluar cuantiles directos (A), Probability Integral Transform (B), o shrinkage bayesiano (C). Considerar la tensión IC global (+0.412) vs per-ticker (+0.371).
3. **¿Cómo se resuelve `fatigue_type`?**  
   Dictaminar si Tide EV incorpora una matriz de rachas cinemáticas o si se estandariza una propiedad unificada en el contrato de dominio para subsanar de inmediato el bug de runtime.
4. **¿Cuál es el estatus de las cifras de validación?**  
   Confirmar que la alerta de 134/171 falsos positivos y el edge 40.7 quedan plenamente sustentados por `medicion_vix_crisis_spike.json` y `sigma_overflow.py`, eliminando cualquier catalogación de rumor provisional.

---

## 10. INVENTARIO DE PUNTOS CIEGOS IDENTIFICADOS (Auditoría METAR → Tide, 30-Sep-2026)

> Fuente: Comparación sistemática de la arquitectura METAR (11 estaciones, `gaussian_scale_policy.md`, `sigma_overflow.py`, `metar_classifier.py`, `inception_policy.md`) contra el subsistema Tide/Wave/Multiscale. Los gaps se priorizan P0 (bloqueante) a P3 (diferible).

### 10.1. 🔴 PC-02: OVERFLOW / BLOW-OFF — Sistema Inexistente en Tide (P0)

**Gap:** Con D1 6-bin, un `T+3` a +2.3σ y uno a +8σ reciben el **mismo bin y el mismo EV**. METAR resuelve esto con una capa paralela graduada T1–T5 (3σ a ≥10σ) en `sigma_overflow.py` — Tide no tiene nada equivalente.

**Evidencia:**
- `sigma_overflow.py` L303–349: `validate_overflow()` retorna `(sigma_depth, "UPPER"/"LOWER"/None)`.
- `classify_overflow_tier()` L352–380: escala T1 (3–4σ WARNING) → T5 (≥10σ SYSTEMIC).
- `STATION_EMPIRICAL_EDGES` contiene P0.135 y P99.865 (±3σ) para el cálculo de z-score → **Tide NO tiene estos anclas en `ticker_gaussian_profiles.json`**.

**Lo que falta:**
1. `ticker_gaussian_profiles.json` debe incluir las anclas **P0.135 y P99.865** (±3σ) además de los 5 edges D1 (P2.28 a P97.72). Sin ellas, no se puede calcular z-score de overflow.
2. Función `validate_slope_overflow(ticker, channel, slope_norm)` análoga a `validate_overflow()`.
3. Campos `sigma_depth` + `overflow_flag` en `RealEVSignal` para que `swing_gate.py` pueda distinguir T+3 moderado de T+3 extremo.
4. Protocolo operacional: T1 → mantener, T2 → bloquear entradas, T3+ → circuit breaker.

**Acción recomendada:** Incorporar al Prompt de Construcción (P) la creación de una capa paralela de overflow adaptada a slopes. No modifica el Fact Store — opera sobre z-score crudo.

---

### 10.2. 🔴 PC-03: Política de Inception No Definida para Tickers (P0)

**Gap:** METAR tiene `inception_policy.md` estricta: "una estación NO existe antes de su `fecha_inicio_valida`". Para Tide con ~531 tickers, los cuantiles per-ticker de IPOs recientes o tickers con historial corto serán ruidosos.

**Evidencia:**
- `inception_policy.md` L11: "Cualquier disparo con fecha < `fecha_inicio_valida` se EXCLUYE".
- `inception_policy.md` L86-91: expanding window con `min_periods=252` (1 año de warm-up).
- Sin inception, un ticker con 100 barras tiene percentiles P2.28 basados en **~2 observaciones** → ruido total.

**Lo que falta:**
1. **Inception per-ticker:** `ticker_gaussian_profiles.json` debe incluir `inception_date` y `n_bars`.
2. **Umbral mínimo:** definir `N_min` de barras para confiar en cuantiles per-ticker (propuesta: 252 barras = 1 año). Para tickers con N < N_min, usar shrinkage al perfil global o del sector.
3. **Filtro pre-inception:** observaciones anteriores al inception del ticker se excluyen del conteo EV.
4. **Fórmula:** `fecha_valida(ticker) = max(inception_date(ticker), primera_barra_en_vault(ticker) + N_min_warmup)`.

**Acción recomendada:** Añadir al §2.3 la estructura de inception dentro de `ticker_gaussian_profiles.json`, y al §2.1 la política de shrinkage para tickers jóvenes.

---

### 10.3. 🟡 PC-01: Desaparición del Estado Neutro `T~` (P1)

**Gap:** v1 tiene `T~` (P25–P75, 50% de la población). v2 con D1 6-bin lo elimina — el rango se divide en `T-1` (P15.87–P50, 34.13%) y `T+1` (P50–P84.13, 34.13%).

**Hallazgo positivo (bug corregido):** `SlopeState.tide_sign` en `rc_slope_classifier.py` L53-54 usa `"+" in level`. Para `T~`, esto devuelve `sign=-1` (bearish), lo cual es un **bug semántico** — neutral no es bearish. v2 lo corrige: `T-1` → sign=-1, `T+1` → sign=+1 (correcto).

**Riesgo residual:** Si algún consumidor downstream depende de "hay un estado neutral" como concepto lógico (ej. "cuando T~, no operar"), esa lógica necesita migración a "cuando `|T_bin| <= 1`, considerar neutral".

**Acción recomendada:** Documentar en el diseño como decisión consciente. El mapping explícito:
```
v1: T---(-2.5%) T--(-7.5%) T-(-15%) T~(50%) T+(15%) T++(7.5%) T+++(2.5%)
v2: T-3(2.28%)  T-2(13.59%) T-1(34.13%) T+1(34.13%) T+2(13.59%) T+3(2.28%)
```

---

### 10.4. 🟡 PC-05: `_documentation.taxonomy` Ausente en Tide EV (P1)

**Gap:** METAR cumple Rule 21 con un bloque `taxonomy` completo que mapea bin_index → label + value_edges. Tide EV v1 no tiene esto — solo tiene `field_glossary` parcial.

**Transferencia mandatoria para v2:**
```json
"taxonomy": {
    "d1_tide": {
        "n_bins": 6,
        "sigma_labels": ["-3", "-2", "-1", "+1", "+2", "+3"],
        "percentiles": [0.0228, 0.1587, 0.5000, 0.8413, 0.9772],
        "value_edges_global": [-7.11, -3.79, 2.49, 5.89, 13.10],
        "note": "Per-ticker edges in ticker_gaussian_profiles.json"
    },
    "d1_current": { "n_bins": 6, "sigma_labels": ["-3", "-2", "-1", "+1", "+2", "+3"], ... },
    "d1_vwap": { "n_bins": 6, "sigma_labels": ["-3", "-2", "-1", "+1", "+2", "+3"], ... },
    "state_key_format": "{T_sigma}|{C_sigma}|{V_sigma}"
}
```

**Acción recomendada:** Mandatar en el Prompt de Construcción (P) la emisión de `taxonomy` completa en todo JSON generado.

---

### 10.5. 🟡 PC-06: Formato de State Key — σ-Index Firmado (P1, propuesta del Arquitecto)

**Gap original:** METAR usa claves numéricas `"5__3__3"` (Rule 24); Tide usa textuales `"T+++|C+++|>>"`. El índice 0–5 carece de dirección/magnitud.

**Propuesta del Arquitecto (30-Sep-2026):** Reemplazar por **enteros con signo que representan σ**, basado en la experiencia de problemas de interpretación con la escala 0-5 de METAR:
- **6 bins (T, C, VWAP):** `+3, +2, +1, −1, −2, −3` (sin 0 — no hay neutro).
- **5 bins (D2/D3 si se añaden, o dimensiones Wave):** `+3, +2, 0, −2, −3` (0 = centro unificado ±1σ).

**Regla de consistencia posicional:** Un σ-index dado **siempre refiere a la misma posición gaussiana** independientemente del esquema:
- `±3` = siempre "más allá de ±2σ" (colas, 2.28% cada una)
- `±2` = siempre "entre ±1σ y ±2σ" (13.59% cada uno)
- `±1` = solo en 6-bin: "entre mediana y ±1σ" (34.13% cada uno)
- `0` = solo en 5-bin: "centro unificado −1σ a +1σ" (68.27%)

**Ventajas verificadas:**
1. **Signo = dirección; |valor| = magnitud en σ** → cero ambigüedad.
2. **Elimina la lógica de parsing** (`"+" in level`) → comparaciones `> 0`, `abs()`, orden trivial.
3. **Corrige el bug de `T~`** (PC-01): el signo surge del número, no de parsear texto.
4. **Numérico (Rule 24) CON semántica σ** — superior a un índice 0..5 ciego.

**Formato de clave propuesto:**
```
Clave primaria (numérica, Rule 24): "3__1__-2"   (T=+3σ, C=+1σ, V=-2σ)
Label auxiliar (humano):             "T+3|C+1|V-2"
```

**Mapping explícito bin ↔ σ-index (posicionalmente consistente):**
| Bin gaussiano | Rango percentil | σ-index (6-bin) | σ-index (5-bin) | Posición gaussiana |
|:---:|:---:|:---:|:---:|:---|
| 0 | < P2.28 (<−2σ) | **−3** | **−3** | Cola inferior (más allá de −2σ) |
| 1 | P2.28–P15.87 (−2σ a −1σ) | **−2** | **−2** | Moderado bajo |
| 2 | P15.87–P50 (−1σ a μ) | **−1** | **0** ← centro unificado | Centro bajo / Centro |
| 3 | P50–P84.13 (μ a +1σ) | **+1** | → **0** (centro unificado ±1σ) | Centro alto |
| 4 | P84.13–P97.72 (+1σ a +2σ) | **+2** | **+2** | Moderado alto |
| 5 | P97.72+ (>+2σ) | **+3** | **+3** | Cola superior (más allá de +2σ) |

> **Regla:** Los labels ±3 y ±2 **significan lo mismo** en ambos esquemas. La única diferencia es el tratamiento del centro: 6-bin lo subdivide en ±1 (debajo/arriba de la mediana); 5-bin lo unifica como 0 (dentro de ±1σ). Esto elimina la ambigüedad que causaba problemas en METAR con la escala 0–5, donde un "2" no comunicaba ni dirección ni posición gaussiana.

**Acción recomendada:** Adoptar el σ-index firmado como base del `taxonomy` y de la llave v2. El `SlopeState` pasa de strings a enteros con signo.

**Ámbito de aplicación del σ-index — 3 familias de dimensiones:**

| Familia | Dimensiones | Escala σ-index | Valores | Ejemplo de clave |
|:--------|:------------|:--------------:|:--------|:-----------------|
| **Cuantil 6-bin** | T, C, VWAP (v2) | `+3,+2,+1,−1,−2,−3` | Cuantiles gaussianos D1, sin neutro | `T+3`, `V-2` |
| **Cuantil 5-bin** | σVc, σc (Wave) | `+3,+2,0,−2,−3` | Cuantiles gaussianos D1, con centro | `σVc+2`, `σc0` |
| **Direccional 3-estado** | vel (Wave), traj/FATIGUE (Multiscale) | `+1, 0, −1` | Signo de dirección, no cuantiles | `vel+1` = ▲, `vel0` = ~, `vel-1` = ▼ |

**Regla:** El σ-index firmado (`±2/±3`) aplica **exclusivamente** a las dimensiones basadas en cuantiles empíricos. Las dimensiones de 3 estados direccionales (`vel`: `{▼, ~, ▲}`; `traj/FATIGUE`: `{ABSORBING, STABLE, EXHAUSTING}`) usan un **sign-index** `{−1, 0, +1}` como alias numérico:
- `▲` / `ABSORBING` = **+1** (aceleración / absorción)
- `~` / `STABLE` = **0** (continuación estable)
- `▼` / `EXHAUSTING` = **−1** (desaceleración / agotamiento)

Los símbolos originales (`▲/~/▼`, `ABSORBING/STABLE/EXHAUSTING`) se preservan como labels semánticos en la `taxonomy` del JSON. El sign-index es el valor numérico de la clave.

**Verificación empírica del sign-index direccional (medido, 01-Oct-2026):**

| Dim | Estado | Sign-index | N | Pop% | EV₅₀ | p_bull₅₀ |
|:----|:-------|:---:|---:|:---:|:---:|:---:|
| **vel** | ▼ | −1 | 294,922 | 38.9% | **+0.0505** | 0.6336 |
| **vel** | ~ | 0 | 243,676 | 32.1% | +0.0040 | 0.4738 |
| **vel** | ▲ | +1 | 220,461 | 29.0% | **−0.0112** | 0.4108 |
| **traj** | ABSORBING | +1 | 264,681 | 33.5% | **+0.0434** | 0.7064 |
| **traj** | STABLE | 0 | 262,919 | 33.2% | +0.0264 | 0.5846 |
| **traj** | EXHAUSTING | −1 | 263,520 | 33.3% | **+0.0091** | 0.4185 |

> Fuente: `rc_wave_ev_derived.json` (759,059 obs) y `rc_ev_multiscale_tree.json` (791,120 obs). EV ponderado por n.

**Veredicto por hipótesis:**

| # | Hipótesis | Resultado | Evidencia |
|:-:|:----------|:---------:|:----------|
| H1 | "El 0 es raro" | ❌ **REFUTADA** | vel ~ = 32.1%, STABLE = 33.2% — ambos ~⅓ de la población |
| H2 | "El 0 discrimina (EV monotónico)" | ✅ **CONFIRMADA** | vel: ▼(+0.0505) > ~(+0.0040) > ▲(−0.0112). traj: ABS(+0.0434) > STB(+0.0264) > EXH(+0.0091) |
| H3 | "sign +1 = mayor EV en TODAS las dims" | ❌ **REFUTADA** | traj: ALINEADO (ABS=+1 paga más). vel: **INVERTIDO** (▲=+1 paga **menos**) |

**Conclusión semántica del sign-index:** El sign-index `{−1, 0, +1}` representa la **dirección de la característica**, NO la dirección del EV. Esto debe documentarse explícitamente por dimensión:

| Dimensión | +1 significa | −1 significa | ¿EV alineado al signo? | Causa física |
|:----------|:-------------|:-------------|:---:|:-------------|
| **traj/FATIGUE** | ABSORBING (absorción de volumen) | EXHAUSTING (agotamiento) | ✅ SÍ | Absorción = acumulación institucional → momentum continúa |
| **vel** | ▲ (wave slope acelerando ↑) | ▼ (wave slope desacelerando/revirtiendo) | ❌ **NO — INVERTIDO** | ▲ = precio ya se movió → agotamiento cinemático; ▼ = precio comprimido → oportunidad de reversión |

> **Regla para consumidores:** El sign-index NO implica "comprar si positivo". Para `traj`, signo positivo = momentum favorable. Para `vel`, signo positivo = **momentum agotado** (EV negativo). Los adaptadores de dominio (`rc_wave_ev_lookup.py`, `rc_multiscale_ev_lookup.py`) interpretan el EV directamente del Fact Store — el sign-index es solo una coordenada de estado, no una señal de trading.

---

### 10.6. 🟡 PC-09: Naming VWAP — Distribución Patológica Corregida (P1)

**Gap:** Los labels `<</</../>/>>` cambian radicalmente de significado con D1 6-bin.

**Distribución real v1 (verificada contra JSON):**
| Bin v1 | Label | N | Pop% |
|:---:|:---:|---:|:---:|
| 0 | `<<` | 978,058 | **21.5%** |
| 1 | `<` | 650,908 | **14.3%** |
| 2 | `~` | 567,952 | **12.5%** |
| 3 | `>` | 782,408 | **17.2%** |
| 4 | `>>` | 1,574,995 | **34.6%** |

Con D1 6-bin, cada bin tiene distribución gaussiana estándar (2.28/13.59/34.13/34.13/13.59/2.28%). Los labels `<</>>`  pierden su significado original.

**Resolución:** Con la adopción del σ-index firmado (PC-06), los labels VWAP se unifican al mismo esquema que T/C:
- v2 VWAP: `V-3, V-2, V-1, V+1, V+2, V+3`
- Consistencia total con T/C — no se necesitan labels especiales para VWAP.

**Acción recomendada:** Reemplazar los labels `<</</../>/>>` por σ-index firmado `V{±n}`. Documentar la correspondencia en la taxonomy del JSON.

---

### 10.7. 🟡 PC-07: Expanding Window vs Población Fija — Look-Ahead Bias (P2)

**Gap:** METAR usa expanding window con `min_periods=252` para calibrar cuantiles, eliminando look-ahead bias. El prompt propone cuantiles fijos sobre la población completa (look-ahead implícito en backtesting).

**Impacto empírico:** Para D1 con bins anchos (34% centro), el look-ahead sesga poco. Para extremos (P2.28 = 2.28%), un evento extremo futuro (COVID 2020) desplaza el edge y reclasifica pasado.

**Opciones:**
1. **Fixed population** (más simple, producción) — sesgo aceptable si N >> 1000.
2. **Expanding window** (METAR) — sin look-ahead, pero más costoso.
3. **Híbrido:** fixed para producción, expanding para backtesting riguroso.

**Acción recomendada:** Documentar la política como decisión consciente. No bloquea v2 pero afecta rigurosidad de backtesting.

---

### 10.8. 🟡 PC-08: Cascade entre Escalas ZZ — Concepto No Medido en Tide (P2)

**Gap:** METAR mide la tasa de overflow zz25→zz50 (~40%) y zz25→zz75 (~25-30%) con campos `cascade_rate`, `p_extreme_prev`, `prev_leg_domino`. Tide EV mide las 3 escalas ZZ por separado pero **no mide si la pierna actual tiende a escalar**.

**Valor operacional:** La pregunta "este pullback de -3% se va a convertir en una corrección de -8%?" es la de mayor valor para swing trading.

**Acción recomendada:** Candidato para v2.1 — registrar como gap sin resolver en v2. El Fact Store v2 podría incluir `cascade_rate_50` y `cascade_rate_75` por estado como campos opcionales.

---

### 10.9. 🟡 PC-10: Naming T/C — Labels `+++/++/+/-/--/---` (P2)

**Evaluación:** Con la adopción del σ-index firmado (PC-06), los labels textuales `+++/++/+/-/--/---` se reemplazan por σ-index:
```
v1: T---  T--  T-  T~  T+  T++  T+++
v2: T-3   T-2  T-1     T+1 T+2  T+3
```

Los labels textuales se preservan como **campo auxiliar humanamente legible** en la taxonomy del JSON, pero la clave primaria es el σ-index.

**Acción recomendada:** ✅ Resuelto por PC-06.

---

### 10.10. 🟡 PC-04: D2 (Velocidad) y D3 (Estabilidad) No Existen en Tide (P2)

**Gap:** METAR clasifica en 3 dimensiones independientes (D1×D2×D3 = 150 estados). Tide solo tiene D1 (magnitud de pendiente).

**Trade-off cuantitativo:** Añadir D2×D3 expandiría 216 → 216×5×5 = **5,400 estados** (~843 obs/celda con F1). Viable estadísticamente pero pierde densidad.

**Alternativa pragmática:** No añadir D2/D3 como dimensiones del Fact Store. Usar como **modificadores paralelos** en `RealEVSignal` sin multiplicar estados:
- `slope_acceleration`: señal de que la pendiente se está acelerando o desacelerando (D2-like).
- `slope_stability`: señal de que la pendiente es estable o errática (D3-like).

**Acción recomendada:** Documentar como decisión consciente de NO incluir en v2. Candidato para evaluación post-v2.

---

### 10.11. 🟡 PC-11: Cadencia de Recalibración No Definida (P2)

**Gap:** METAR tiene Rule S6/S8 con cadencia mensual. Para `ticker_gaussian_profiles.json` con 531 tickers, no hay cadencia definida.

**Propuesta:**
- **Trimestral:** regeneración completa de perfiles per-ticker.
- **Por evento:** split, reverse split, IPO, salida del SP500, cambio estructural.
- **Semanal (CI):** test de integridad taxonómica (análogo a `test_taxonomy_integrity.py` de METAR).

**Acción recomendada:** Definir en el Prompt de Construcción (P) la cadencia y los scripts de regeneración.

---

### 10.12. 🟢 PC-12: Transition Tracking vía `RegimeStatePort` No Conectado (P3)

**Gap:** Rule 15 (Stateful-First) exige que todo clasificador que emita un estado discreto persista transiciones. Tide EV no persiste transiciones de slope regime — solo clasifica puntualmente.

**Acción recomendada:** Deuda de infraestructura paralela. No bloquea v2. Post-v2 el `swing_gate.py` debería persistir transiciones T-3→T+1 en `market.regime_states`.

---

## 11. PATRONES TRANSFERIBLES DESDE METAR (6)

### PT-01: Clasificador Centralizado (`metar_classifier.py` → `tide_classifier_v2.py`)

METAR tiene un único `metar_classifier.py` (72 líneas) con `classify_bin()`, `make_state_key()`, `decode_state_key()`, `resolve_label()`. Tide v1 tiene `rc_slope_classifier.py` (142 líneas) con lógica hardcodeada.

**Transferencia:** Crear un `tide_classifier_v2.py` análogo que:
- Reciba edges per-ticker desde `ticker_gaussian_profiles.json`.
- Clasifique `slope_norm` en σ-index firmado (−3 a +3).
- Genere state key numérica: `"3__1__-2"`.
- Resuelva labels: `"T+3|C+1|V-2"`.

### PT-02: `_documentation.taxonomy` (Rule 21)

Ver PC-05. Transferir la estructura exacta de METAR con la extensión σ-index.

### PT-03: Diamantes Estadísticos — Protocolo Formalizado

Transferir el protocolo de METAR (`fact_store_v3_architecture.md` §3.3) con tiers ANECDOTAL/LOW/MODERATE/HIGH/ROBUST y correspondencia con el shrinkage bayesiano:

| N | Tier | Shrinkage a L2 (prior_weight) |
|:---:|:------|:---:|
| 1-2 | ANECDOTAL | 100% |
| 3-5 | LOW | 80% |
| 6-10 | MODERATE | 50% |
| 11-20 | HIGH | 20% |
| 21+ | ROBUST | 0% (datos propios) |

### PT-04: Capa Paralela de Overflow para Slopes

Ver PC-02. Transferir la arquitectura de `sigma_overflow.py` adaptada a pendientes per-ticker, con anclas P0.135/P99.865 en el perfil de calibración.

### PT-05: Inception Policy Adaptada a Tickers

Ver PC-03. Incluir `inception_date`, `n_bars`, `min_valid_date` en `ticker_gaussian_profiles.json`.

### PT-06: Regeneración Atómica (Rule S8/S9)

Definir el pipeline de regeneración en orden estricto (análogo a METAR Rule S9):
```bash
# 1. Calibrar perfiles per-ticker → ticker_gaussian_profiles.json
# 2. Reentrenar tabla de probabilidad → rc_tide_ev_probability_table_v2.json
# 3. Derivar con shrinkage → rc_tide_ev_derived_v2.json
# 4. Verificar integridad → tests de regresión
# 5. Flip atómico del puntero v1 → v2
```

---

## ANEXO A — AUDITORÍA FÁCTICA DEL PROMPT (Hermes · 2026-09-29)

> Verificación **ejecutada** contra el repo (dato mata relato), de todos los agregados de las dos revisiones. Veredicto por afirmación.

### ✅ VERIFICADO (sustentado — se conserva)

| Afirmación | Evidencia (ejecutada) |
|---|---|
| Tide EV = **245 L3 / 49 L2 / 7 L1**, `l0_global` = **dict único** (n=4.554.321) | `json.load` del archivo ✓ |
| `_documentation.state_hierarchy.L3` dice **"(180 granular micro/macro states)"** = **deuda** | Lectura del campo ✓ |
| **T~ / C~** existen → **7 niveles** T y C → 7×7×5=245 | `set(k.split('|')[0])` ✓ |
| `rc_tide_derived.json` = **180** (6 niveles, sin `~`) | conteo ✓ |
| Wave EV = **479 total**, **sin `W~`** | conteo por prefijo ✓ |
| `rc_vol_normalized_thresholds.json` = 6 campos (`tide/current/wave_slope_norm`, `vwap_sigma_wave`, `rsi_value`, `kalman_velocity`) | keys ✓ |
| **VIX D1 P97.72 = 40.7336**; `STATION_EMPIRICAL_EDGES['vix']['d1']['p9772']` accesible | import ✓ |
| `medicion_vix_crisis_spike.json`: **activa n=171**, baseline n=1418 | json ✓ |
| `SPY_forensics.csv`, `gaussian_scale_policy.md` **existen** | find ✓ |
| `swing_gate.py`: 5 lookups en **L160/218/267/290/317** | grep ✓ |
| `rc_tide_ev_lookup.py` docstring: `p_bull # P(next = MIN / floor)` (L33) | lectura ✓ |
| **KI `ev-horizon-divergence`**: 80% (196/245); FLOOR 31%; NEUTRAL 8%/92%; CEILING 29% | KI `empirical_rules.md` ✓ |
| **KI `zz-s5-breadth-coincidence`**: 2.652 giros; 62.4% / 77.1% / 85.0%; XLU 95.5 / XLRE 95.2 / XLF 94.7 / XLE 94.7 / XLK 68.4 | KI `coincidence_study.md` ✓ |
| Tensión IC **global +0.412 vs per-ticker +0.371** | `per-ticker-calibration-design.md` ✓ |

### ✗ CORREGIDO EN ESTE PROMPT (afirmaciones inexactas de las revisiones)

1. **Wave EV = "479 L1 / 30 L2 / 6 L3"** → **FALSO**. Real: **444 L1 / 30 L2 / 5 L3** (479 es el **total**). *(corregido en §1.1)*
2. **"L63 computa correctamente `raw_p_bull = n_pos / n_tot` (P(MAX))"** → **FALSO**. El código real es `raw_p_bull = n_neg / n_tot`. La revisión copió la línea *aspiracional* del KI ("FIXED L63") **sin verificar el archivo**. *(corregido en §1.3)*
3. **"rc_slope_classifier implementa 7 niveles"** → el **docstring/código dice 6 niveles** (L4, L47-49); los **datos** muestran 7. Es **drift doc↔dato**, no implementación explícita de 7. *(matizado)*
4. **"sectores defensivos (XLU, XLRE, XLE)"** → XLE es **Energía** y el 94.7% empata con **XLF (financieras)**; los 95.5/95.2 son de la tabla de **horizonte 7.5%**. *(corregido en §1.7)*

### ✅ HALLAZGO MAYOR — Contradicción KI ↔ Código (P0) → RESUELTO

> **Resuelto en commit `e2a2ada` (30-Sep-2026).** El bug P0 fue corregido en ambos generadores y los JSONs regenerados. Ver auditoría completa en `auditoria_p0_p_bull.md`.

**Estado post-fix:**
```python
# generate_tide_ev_real_derived.py        L63: raw_p_bull = n_pos / n_tot   ← CORREGIDO
# generate_multiscale_ev_derived.py       L60: raw_p_bull = n_pos / n_tot   ← CORREGIDO
```
**Verificación:** `T~|C~|~` p_bull = 0.5444 = P(MAX) (sesgo alcista secular correcto).

### ❓ NO VERIFICADO (marcar como hipótesis hasta comprobar)
- "Tide clásico ≈765.000 muestras".
- "censo 100% = **4.577.585**" (no confirmado; el valor verificado en `l0_global` es **4.554.321** — dos cifras distintas conviven).
- `generate_wave_ev_real_derived.py` L7 (jerarquía invertida) — no inspeccionado.
- `ticker_gaussian_profiles.json` con "n_tickers: 531" — es **propuesta**, no dato.

### ➕ VERIFICADO ADICIONAL (2ª pasada)
- `rc_ev_multiscale_tree.json`: `s1_full`=**25.797**, `s3_triad`=**996**, `n_samples_total`=**791.120** ✓ (cifras del prompt correctas).
- `generate_multiscale_ev_derived.py` **L60** = `raw_p_bull = n_neg / n_tot` ✓ → confirma el P0 en el **2º generador** (ya no es hipótesis).

---

## ANEXO B — EVALUACIÓN DEL ANÁLISIS DE ESCALAS GAUSSIANAS (actualizado post-fix `e2a2ada`)

> Artefacto evaluado: `brain/e8aaefd3-.../analisis_escalas_gaussianas_tide.md` (versión post-fix 30-Sep-2026).

### B.1. Veredicto de exactitud — ALTA (recalculado post-fix)
**Todas** las cifras del artefacto fueron verificadas **exactas** contra los JSONs **regenerados**:
- Distribución T (2.5/7.5/15/**50**/15/7.5/2.5; N exactos: T~ = 2.278.449) ✓ **ROBUSTO**
- Distribución VWAP (`<<` 21.5% / **`>>` 34.6%** = 1.574.995) ✓ **ROBUSTO**
- Medianas: T **+2.492**, C **+2.857**, W **+2.965**, VWAP **+0.380** ✓ **ROBUSTO**
- Edges VWAP **fijos** `[-1.0,-0.3,0.3,1.0]` en `train_tide_ev_real_table.py` L46-57 ✓
- EV por VWAP: `<<` **−0.0021**, `<` +0.0184, `~` +0.0236, `>` +0.0290, `>>` **+0.0475** ✓ **POST-FIX**
- EV por T: T--- +0.0134 … T+ **+0.0373** (pico) … T+++ +0.0338 ✓ **POST-FIX**
- Gradiente máximo `T~→T+` **+0.0139** ✓ **ROBUSTO** (era +0.0138 pre-fix)
→ Artefacto **recalculado y verificado**.

### B.2. ✅ Contaminación P0 RESUELTA
El bug `p_bull = n_neg/n_tot` fue corregido en commit `e2a2ada`. Los JSONs fueron regenerados. El artefacto de análisis fue actualizado con los valores post-fix.

### B.3. Decisiones del Arquitecto (30-Sep-2026)

| Decisión | Resolución |
|:---------|:-----------|
| T slope | **D1 (6 bins)** — gradiente T~→T+ = +0.0139 robusto, plateau T+/T++ confirma fusión |
| C slope | **D1 (6 bins)** — mismo argumento |
| VWAP | **D1 (6 bins)** — corrección de la patología del 34.6%, EV monotónico |
| Tesis | **MOMENTUM** — CEILING paga, FLOOR pierde |
| Llave | **Evoluciona** a 6×6×6 — lookups se adaptan en v2 |
| Despliegue | **Serie versionada + puntero atómico** |
| vel / fatigue | Correctamente excluidas (categóricas, no clasificables por percentiles) ✓ |

### B.4. EV Relativo (E[R] − L0) — Campo discriminante obligatorio
Con tesis MOMENTUM, el EV absoluto (todo positivo por drift) no discrimina. El EV relativo (L0 = +0.0247) sí:
- **Por T:** monotónico de T--- (−0.0113) a T+ (+0.0126), luego plateau
- **Por VWAP:** perfectamente monotónico de `<<` (−0.0268) a `>>` (+0.0228)
- **Frontera EV_rel ≈ 0** está en T~ y VWAP `~` — exactamente donde D1 pone el corte de mediana

### B.5. Sobre la pregunta del Arquitecto (escalas per-ticker: tabla + ajuste en consolidación)
Tu intuición es la correcta y coincide con las Opciones A/C del §2.1:
- **Persistir** `ticker_gaussian_profiles.json` (versionado) es preferible a "on-the-fly" por **auditabilidad/reproducibilidad**; exige protocolo de regeneración + manejo de **incepción** y **rupturas estructurales** por ticker.
- **Ajustar en la consolidación** = normalizar cada observación a su perfil (**Probability Integral Transform**, Opción B) **antes** de sumar, y luego agregar por familia.
- ✅ El P0 `p_bull` **ya está resuelto** — la consolidación puede proceder sobre datos limpios.
