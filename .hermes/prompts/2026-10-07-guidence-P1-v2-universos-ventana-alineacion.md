# GUÍAS / PROMPT #1 (v2) — UNIVERSOS DE ENTRENAMIENTO, VENTANA TEMPORAL Y AUDITORÍA DE ALINEACIÓN
**Fecha:** 07-Oct-2026 · **Alcance:** DEFINIR y AUDITAR. No se modifica ni se borra nada.
**Parte 2 (separada):** ejecutar el cambio, auditarlo y regenerar todo el inventario.

---

## 0. PRINCIPIO (declarado, no negociable)

El pozo contiene **dos naturalezas** que hoy comparten tablas (`market.ohlcv_bars`, `engine.zigzag_points`,
`market.zigzag_legs`):

```
① INSTRUMENTOS      acciones y ETFs — entidades evaluables y entrenables
② SERIES DERIVADAS  S5_*, SV5_*, S5CAP_*, VBI_*, índices, macro, CBOE — INSUMOS DE ANÁLISIS
```

**NO se retiran las piernas de las series derivadas**: sus zigzag SE EMPLEAN
(`optimize_crash_sistemico_intelligence.py` usa S5TH/S5FI/S5TW/SV5TH/SV5FI/SV5TW **y las sectoriales
`S5_{ETF}_*`**). El problema es que **comparten tabla y toda consulta sin filtro las mezcla**.
La solución es **definir universos por naturaleza**, no borrar filas.

---

## 1. EL DISCRIMINADOR DE NATURALEZA (verificado en base)

`market.ticker_metadata.update_source` — **753 tickers en 9 naturalezas:**

| update_source | tickers | composición |
|---|---:|---|
| **`vault_ohlcv_bars`** | **563** | **516 STOCK + 47 ETF + 0 indicadores** ⇒ UNIVERSO DE INSTRUMENTOS |
| `vault_breadth_calc` | 123 | series de amplitud calculadas |
| `none_historical_only` | 51 | 45 INDICATOR + 4 STOCK + 2 sin clase |
| `vault_fred_macro` · `vault_derived` · `vault_cboe_pcr` · `vault_cboe_indices` · `vault_market_indices` · `vault_vix_live` | 16 | macro, derivadas, CBOE, índices |

Filtro canónico complementario (`backend/scripts/_lib/universe.py`): `industry != 'INDICATOR'` AND
`asset_type IN ('STOCK','ETF')` AND `ticker NOT LIKE 'UW_%'` AND `LENGTH(ticker) <= 5` AND `bars >= 250`.

---

## 2. UNIVERSO ACTUAL — MEDIDO

```
· engine.zigzag_points : 566 tickers (519 STOCK + 47 ETF + 0 indicadores) · 1.782.308 puntos · 1962-01-02 → 2026-10-02
     asimetría: AMD 9.006 · WDC 8.962 · MU 8.700 · TER 8.494 · SWKS 8.016   vs   SPY 1.304  (7×)
· market.zigzag_legs   : 613 = 565 STOCK/ETF (3.644.170 piernas) + 48 INDICADORES (401.344 piernas ≈ 9,9 %)
     escritas por rebuild_breadth_history.py y master_synthetic_and_regime_rebuild.py
· market.ticker_metadata: 753 tickers en 9 naturalezas
· APLICACIÓN REAL      : 30 tickers (engine.signal_passports)
⇒ Desalineación medida: se ENTRENA sobre 566 y se APLICA sobre 30 (19×), con cambio de perfil.
```

### 2.bis ARQUITECTURA DE TRANSFERENCIA DE DOMINIO (verificada — es por diseño)

```
CÁLCULO     las series S5/SV5 se construyen EXCLUSIVAMENTE con acciones individuales
            (rebuild_breadth_history.py L10 y L76: asset_type='STOCK', update_source='vault_ohlcv_bars')
ENTRENO     las tríadas se entrenan contra ETFs: SPY + 11 sectoriales + QQQ
            (train_s5v_triad.py L29/L40-50: SECTOR_ETFS + TIERS "Broad":["SPY"], "High-Beta":["QQQ"])
APLICACIÓN  sobre ACCIONES (sizing modifier en EntryGate · ranking sectorial en CIO · contexto en SwingGate)
VALIDACIÓN  s5_empirical_proof.md: (1) coincidencia ZZ-S5 a nivel ETF 77 % (spread 46 pp);
            (2) a nivel ACCIÓN: 15/15 acciones · 68-71 % WR · +4,69 % delta COLD vs HOT · p<0,000001,
                sobre 18.390 observaciones en 5 años; (3) sector vs mercado: COLD+IMPROVING 81,7 % WR
```
⇒ La transferencia es deliberada y validada. **El universo de cada artefacto debe declararse como TRÍO
(cálculo · entrenamiento · aplicación)**, no como un conjunto único.

---

## 3. TABLA S5 vs SV5 — QUÉ MIDE CADA UNA, DÓNDE SE HIBRIDAN Y CON QUÉ LÓGICA

**Doctrina (textual del propio calculador `volume_breadth_calculator.py` L17-28):**
> *"SV5 measures CONVICTION / PARTICIPATION, NOT direction… SV5 alone is DIRECTIONLESS. Never interpret
> SV5 rising as bullish or SV5 falling as bearish without checking the corresponding S5."*

```
S5  = amplitud de PRECIO   → DIRECCIÓN
SV5 = amplitud de VOLUMEN  → CONVICCIÓN / PARTICIPACIÓN (sin dirección)
```

**Matriz de lectura que el sistema implementa (2×2 anidada):**

| | SV5 ↗ | SV5 ↘ |
|---|---|---|
| **S5 ↗** | Rally con convicción | Rally sin convicción (vulnerable) |
| **S5 ↘** | Venta con convicción | Deriva apática |

**Dónde se hibridan (medido por grep S5/SV5):**

| Archivo | S5 | SV5 | Híbrida | Papel |
|---|---:|---:|---|---|
| `volume_breadth_calculator.py` | 6 | 14 | **⚠ SÍ** | el núcleo: define ambas y la matriz 2×2 |
| `quality_entry_gate.py` | 1 | 11 | **⚠ SÍ** | el gate: reglas conjuntas (S5_TH + S5_FI + SV5_TW) con WR publicados |
| `optimize_crash_sistemico_intelligence.py` | 1 | 1 | **⚠ SÍ** | detector de crash: cruza ambas |
| `train_s5_triad.py` | 13 | 0 | no | tríada de precio |
| `train_s5v_triad.py` | 0 | 3 | no | tríada de volumen |
| `generate_sv5_turbulence_fact_table.py` | 0 | 3 | no | turbulencia de volumen |
| `generate_bsi_fact_table.py` | 5 | 0 | no | BSI: sólo precio |

**Reglas híbridas del gate (con WR declarado) que hay que evaluar:**
```
· Super-Patrón de Re-Absorción Alcista : S5_TH >= 60% + S5_FI <= 45% + SV5_TW >= 60%  → 86.9 % WR Buy
· Gatillo de Capitulación en Suelo    : S5_TH <= 25% + SV5_TW >= 60%                  → 82.8 % WR Buy
· Antena Pre-Crash                    : SV5_FI > S5_FI durante >= 10 días (inversión persistente)
· V25                                 : SV5_TW >= 50 % en PULLBACK_ALCISTA (+26.27 acc)
· Bins separados: S5_EDGES y SV5_EDGES (dos conjuntos propios) + anidamiento conjunto S5xSV5
```

**Lo que hay que evaluar de esta hibridación (a adjudicar):**
```
H-1  ¿Los WR de las reglas híbridas (86.9 % / 82.8 %) se midieron sobre ETFs o sobre acciones?
     ¿Y siguen vigentes tras el rebuild (ventana, población)?  ⇒ son las reglas más rentables del gate.
H-2  ¿El anidamiento S5xSV5 (bins conjuntos) se recalibró tras el rebuild o quedó con los edges viejos?
H-3  ¿La hibridación es coherente en los tres archivos o cada uno la implementa distinto?
H-4  ¿SV5_TW de las reglas es el mismo objeto que SV5TW del fact store / la serie del pozo?
```

---

## 4. VENTANA TEMPORAL DE ENTRENAMIENTO — ACTUAL Y PROPUESTA

```
MEDIDO HOY (lo que hay):
· engine.zigzag_points      : 1962-01-02 → 2026-10-02   (64 años)
· market.zigzag_legs        : SPY hasta 2026-09-21
· series derivadas en legs  : S5TH 1980-12-30 → 2026-08-01 · S5FI 1980-05-27 → 2026-07-28
                              S5CAP_XLB_TW 2020-01-02 → 2026-07-31
· signal_passports          : 30 tickers (ventana por ticker)
· s5_empirical_proof        : "18.390 observaciones en 15 acciones durante 5 AÑOS"
· quants_obs                : 1.584 pivotes (era 1.354 en agosto ⇒ la población cambió)

PROPUESTO (a adjudicar por artefacto):
· la ventana debe declararse junto al universo, en el mismo bloque de procedencia
· y debe distinguir: ventana de ENTRENAMIENTO · de VALIDACIÓN · de APLICACIÓN
· el sesgo de membresía (P4) obliga a declarar desde qué año la muestra es comparable
  (1980: 158 tickers · 2000: 353 · 2008: 416 · 2026: 506 — cifras del plan, por reverificar)
```

---

## 5. UNIVERSO + VENTANA PROPUESTOS POR USO (a adjudicar)

| Familia | Cálculo | Entrenamiento | Aplicación | Ventana propuesta |
|---|---|---|---|---|
| 8 artefactos RC | — | **los 30** (hoy 566 sin filtro) | acciones (Quality universe, 30) | declarar; alinear a la ventana de aplicación |
| 11 fact stores METAR + 11 timing | — | SPY + macro (correcto) | régimen de mercado | declarar; sólo dxy/vix leen legs |
| Tríada s5 / s5v | amplitud en ACCIONES | **ETFs: SPY + 11 sectoriales + QQQ** | acciones | declarar; es transferencia validada |
| `quants_obs` → timing | — | SPY zz25 (1.584 pivotes) | pivotes de referencia | 1.584 pivotes |
| Compositor de cascada | — | — | SPY (legs por ticker) | as_of_date causal |
| Series derivadas | acciones | — | insumos de análisis | ventana propia por serie (¡ojo: calendario propio!) |

---

## 6. 🔴 AUDITORÍA DE ALINEACIÓN Y DISCRIMINABILIDAD EN `zigzag_legs` (hallazgos medidos)

```
A-1  DISCRIMINABILIDAD: la tabla NO tiene un campo que declare la naturaleza de la fila.
     Hoy sólo se infiere cruzando con ticker_metadata.update_source ⇒ frágil: cualquier consulta
     sin ese join mezcla instrumentos con series derivadas (48 tickers / 401.344 piernas).

A-2  CALENDARIO: las series derivadas tienen CALENDARIO PROPIO, distinto al de SPY:
        S5TH         11.535 barras propias · 3.056 (26,5 %) FUERA del calendario de SPY
        S5FI         11.685 barras propias · 3.206 fuera
        S5CAP_XLB_TW  9.747 barras propias · 1.268 fuera
     ⇒ Un join por timestamp contra SPY desalinea o pierde hasta un cuarto de la serie.
     ⇒ Hay que verificar cómo se alinean hoy los consumidores de esas piernas.

A-3  FRESCURA: las piernas de las series derivadas están CONGELADAS:
        S5TH último leg 2026-08-01 · S5FI 2026-07-28 · S5CAP_XLB_TW 2026-07-31
     vs SPY 2026-09-21 ⇒ quien consuma esas piernas usa datos de 2–3 meses atrás.

A-4  AUSENCIA: SV5TW y VBI_XLK figuran como tickers en `legs` pero NO tienen piernas ⇒
     hay que localizar dónde viven sus zigzag (sus zz SE emplean, según el inventario de consumidores).
```

**Auditoría a ejecutar (entregable de la Parte 1):**
```
· Por cada serie derivada: calendario propio vs el de SPY, y consumidores que hacen join por timestamp.
· ¿Hay filas de legs con timestamp fuera del rango de su propia serie?
· ¿La escala (zz25/50/75) es consistente en todas las naturalezas?
· Construir el mapa de alineación: qué artefacto usa qué serie, con qué calendario y qué ventana.
```

---

## 7. LO QUE FALTA MEDIR

```
M-1  Inventario de consumidores de cada serie derivada (arrancar por crash sistémico).
M-2  Pivotes/piernas que aporta cada naturaleza (dimensionar el sesgo).
M-3  Perfil de los 566 vs los 30 (market cap, sector, volatilidad, historia).
M-4  Sesgo de membresía por año (P4): 1980/2000/2008/2026 — reverificar cifras.
M-5  Discrepancia: points 566 vs vault_ohlcv_bars 563 ⇒ identificar los 3; resolver NDQ/SPX.
M-6  Confirmar el conjunto exacto del Quality universe (30) y si es estable o rota.
M-7  ¿Tienen los 8 RC una validación de transferencia equivalente a la de S5_FI?  Si no, entrenar
     sobre 566 y aplicar a 30 no está respaldado.
M-8  La ventana temporal de cada artefacto: entrenamiento, validación y aplicación — declaradas.
```

## 8. ACEPTACIÓN DE LA PARTE 1

```
· Cada familia con su TRÍO declarado (cálculo · entrenamiento · aplicación) + VENTANA (3 ventanas).
· Cada artefacto con `_metadata` de procedencia: tabla fuente · naturaleza · población · conteo ·
  ventana · hash de la entrada.
· Tabla S5/SV5 publicada con la lógica de hibridación y las reglas híbridas evaluadas (H-1 a H-4).
· Auditoría de alineación de `zigzag_legs` entregada (A-1 a A-4), con el mapa de calendarios.
· Series derivadas definidas como universo propio, conservadas y con sus consumidores identificados.
```

## 9. DECISIONES A ADJUDICAR

```
D-1  Los 8 RC: ¿los 30 exactos · los 30 + histórico de salidas · o stock+ETF ponderado?
D-2  ¿Se acepta y declara el sesgo de membresía, o se recorta la ventana de entrenamiento?
D-3  ¿Se pondera por ticker (AMD no debe pesar 7× SPY) o se agrega sin ponderar?
D-4  ¿Qué campo marca la NATURALEZA de una fila (instrumento vs serie derivada) para que ninguna
     consulta futura las mezcle?
D-5  ¿Se exige validación de transferencia a los 8 RC antes de fijar su universo?
D-6  Ventana: ¿cuál es la ventana mínima comparable, y se recorta V-C a la intersección con V-B?
```
