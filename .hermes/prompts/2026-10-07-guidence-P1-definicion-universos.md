# GUÍAS / PROMPT #1 — DEFINICIÓN DE UNIVERSOS (ACTUAL Y PROPUESTO)
**Fecha:** 07-Oct-2026 · **Alcance:** DEFINIR. No se modifica nada, no se borra nada.
**Parte 2 (separada):** ejecutar el cambio, auditarlo y regenerar el inventario.

---

## 0. PRINCIPIO (declarado, no negociable)

El pozo contiene **dos naturalezas** que hoy comparten tablas (`market.ohlcv_bars`,
`engine.zigzag_points`, `market.zigzag_legs`):

```
① INSTRUMENTOS      acciones y ETFs — entidades evaluables y entrenables
② SERIES DERIVADAS  S5_*, SV5_*, S5CAP_*, VBI_*, índices, macro, CBOE — INSUMOS DE ANÁLISIS
```

**NO se retiran las piernas de las series derivadas**: sus zigzag SE EMPLEAN (p. ej.
`optimize_crash_sistemico_intelligence.py` usa S5TH/S5FI/S5TW/SV5TH/SV5FI/SV5TW **y las sectoriales**
`S5_{ETF}_*`). El problema no es que existan: es que **comparten tabla y por eso cualquier consulta sin
filtro las mezcla**. La solución es **definir universos por naturaleza**, no borrar filas.

---

## 1. EL DISCRIMINADOR (verificado en base)

`market.ticker_metadata.update_source` separa las naturalezas con precisión:

| update_source | tickers | composición |
|---|---:|---|
| **`vault_ohlcv_bars`** | **563** | **516 STOCK + 47 ETF + 0 indicadores** ⇒ UNIVERSO DE INSTRUMENTOS |
| `vault_breadth_calc` | 123 | series de amplitud calculadas (todas INDICATOR) |
| `none_historical_only` | 51 | 45 INDICATOR + 4 STOCK + 2 sin clase |
| `vault_fred_macro` | 5 | macro (INDICATOR) |
| `vault_derived` | 4 | derivadas (INDICATOR) |
| `vault_cboe_pcr` · `vault_cboe_indices` | 2 + 2 | CBOE (INDICATOR) |
| `vault_market_indices` | 2 | índices (sin clase) |
| `vault_vix_live` | 1 | INDICATOR |
| **TOTAL metadata** | **753** | |

**Filtro canónico complementario** (`backend/scripts/_lib/universe.py`):
`(industry IS NULL OR UPPER(industry) != 'INDICATOR')` AND `UPPER(asset_type) IN ('STOCK','ETF')`
AND `ticker NOT LIKE 'UW_%'` AND `LENGTH(ticker) <= 5` AND `COUNT(bars) >= 250`.

---

## 2. UNIVERSO ACTUAL — MEDIDO

```
· engine.zigzag_points : 566 tickers (519 STOCK + 47 ETF + 0 indicadores) · 1.782.308 puntos · 1962-01-02 → 2026-10-02
     asimetría interna: AMD 9.006 · WDC 8.962 · MU 8.700 · TER 8.494 · SWKS 8.016   vs   SPY 1.304
     ⇒ el entrenamiento "por universo" está dominado por las acciones más volátiles (7× sobre SPY)

· market.zigzag_legs   : 613 tickers = 565 STOCK/ETF (3.644.170 piernas) + 48 INDICADORES (401.344 piernas)
     ⇒ las derivadas son el 9,9 % de las filas y el 7,8 % de los tickers (613 = 565 + 48, suma exacta)
     escritas por: rebuild_breadth_history.py · master_synthetic_and_regime_rebuild.py
     (NDQ y SPX aparecen en la tabla sin metadata propia; su naturaleza debe resolverse en M-5)

· market.ticker_metadata : 753 tickers en 9 naturalezas distintas (ver §1)

· UNIVERSO DE APLICACIÓN REAL : 30 tickers (engine.signal_passports, 94 filas)
     AAPL ABBV ACN ADP AMZN BRK-B COST GOOGL HD HON IBM INTU JNJ JPM LLY MA MCD META MRK MSFT
     NEE NVDA PEP PG TMO TXN UNH V WMT XOM
```

**⇒ Desalineación medida: se ENTRENA sobre 566 y se APLICA sobre 30** ⇒ factor 19×, con cambio de perfil
(mega-caps defensivas en aplicación vs volátiles/tech en entrenamiento).

---

## 3.bis ARQUITECTURA DE TRANSFERENCIA DE DOMINIO (verificada — es por diseño)

```
CÁLCULO     las series S5/SV5 se construyen EXCLUSIVAMENTE con acciones individuales
            (rebuild_breadth_history.py L10 y L76: asset_type='STOCK', update_source='vault_ohlcv_bars')
ENTRENO     las tríadas se entrenan contra ETFs: SPY + 11 sectoriales + QQQ
            (train_s5v_triad.py L29/L40-50: SECTOR_ETFS + TIERS con "Broad":["SPY"], "High-Beta":["QQQ"])
APLICACIÓN  sobre ACCIONES individuales (sizing modifier en EntryGate · ranking sectorial en CIO ·
            contexto de miedo sectorial en SwingGate)
VALIDACIÓN  s5_empirical_proof.md — 3 estudios: (1) coincidencia ZZ-S5 a nivel ETF (77 %, spread 46 pp);
            (2) validación a nivel ACCIÓN: 15/15 acciones, 68-71 % WR, +4,69 % delta COLD vs HOT,
            p<0,000001, sobre 18.390 observaciones en 5 años; (3) sector vs mercado (COLD+IMPROVING 81,7 % WR)
```

⇒ **La transferencia es deliberada y está validada empíricamente.** Por lo tanto:
```
· NO es un defecto que la amplitud se calcule en acciones y las tríadas entrenen en ETFs.
· El "universo" de cada artefacto debe declararse como TRÍO (cálculo · entrenamiento · aplicación),
  no como un único conjunto.
· Lo que SÍ es un problema (medido) es que los artefactos RC entrenen sin filtro sobre 566 tickers
  mientras su dominio de aplicación es de 30, SIN una validación de transferencia equivalente a la
  que sí existe para S5_FI.
```

## 3. UNIVERSO PROPUESTO — POR USO (a adjudicar)

| Artefacto / familia | Uso real | Universo propuesto |
|---|---|---|
| 8 artefactos RC (`rc_wave_probability_table`, `rc_tide_probability_table`, `rc_tide_ev_probability_table`, `rc_ev_multiscale_probability_table`, `rc_wave_multiscale_tree`, `rc_piso_table`, `rc_techo_table`, `rc_zigzag_audit`) | swing timing sobre el Quality universe (30); hoy 4 de ellos entrenan sin filtro (566) | **los 30** (+ opciones: histórico de salidas del índice; o stock+ETF ponderado por ticker) |
| 11 fact stores METAR + 11 timing | régimen de MERCADO (macro), no instrumentos | **SPY + series macro.**  Correcto hoy (sólo `dxy` y `vix` leen legs de SPY) ⇒ limpiar el metadato falso de los otros 9 |
| Tríada `s5` / `s5v` | piso/techo por estado de amplitud | **SPY + 11 sectores + QQQ** ⇒ correcto ⚠ (declararlo en el artefacto) |
| `quants_obs` → timing | pivotes de SPY zz25 | **SPY, 1.584 pivotes** ⇒ correcto |
| Compositor de cascada (producción) | SPY | **legs de SPY** (el repositorio filtra por ticker) ⇒ correcto |
| **Series derivadas** (`S5*`, `SV5*`, `S5CAP*`, `VBI*`, macro, CBOE) | insumos de análisis (crash sistémico, amplitud, régimen) | **universo propio, excluido del de instrumentos.**  Se conservan y se declaran |

---

## 4. LO QUE FALTA MEDIR PARA CERRAR LA DEFINICIÓN

```
M-1  Inventario completo de consumidores de cada SERIE DERIVADA (arrancar por
     optimize_crash_sistemico_intelligence.py y los detectores de crash/régimen).
M-2  Cuántos pivotes/piernas aporta cada naturaleza a `points` y a `legs` (para dimensionar el sesgo).
M-3  Perfil de los 566 vs los 30: market cap, sector, volatilidad, años de historia.
M-4  Sesgo de membresía por año (P4): cuántos de los 566 existían y cotizaban en 1980/2000/2008/2026.
M-5  Discrepancia detectada: `points` tiene 566 tickers y `vault_ohlcv_bars` 563 ⇒ identificar los 3
     de diferencia y su naturaleza.
M-6  Confirmar cuál es el conjunto exacto del "Quality universe" (30 en signal_passports) y si es
     estable o rota.
M-7  ¿Tienen los 8 artefactos RC una validación de transferencia equivalente a la de S5_FI
     (15 acciones / 18.390 obs / p<0,000001)?  Si no la tienen, entrenar sobre 566 y aplicar a 30
     no está respaldado — y eso es un hallazgo, no una preferencia.
```

---

## 5. ACEPTACIÓN DE LA PARTE 1

```
· Cada familia de artefactos tiene declarado su UNIVERSO (naturaleza + población + conteo).
· Cada artefacto de reglas declara en su `_metadata`: tabla fuente · naturaleza · población ·
  tickers/conteo · ventana · hash de la entrada.
· Las series derivadas quedan definidas como universo propio, CON sus consumidores identificados
  (no se retiran, no se ocultan).
· 0 artefactos entrenados sobre una población que no coincide con su dominio de aplicación sin
  declararlo explícitamente.
```

## 6. DECISIONES A ADJUDICAR (parte 1)

```
D-1  Los 8 RC: ¿universo = los 30 exactos · los 30 + histórico de salidas · o stock+ETF ponderado?
D-2  ¿Se acepta el sesgo de membresía (P4) y se declara, o se recorta la ventana de entrenamiento?
D-3  ¿Se pondera por ticker (para que AMD no pese 7× SPY) o se agrega sin ponderar?
D-4  Nomenclatura: ¿cómo se marca en las tablas una fila de naturaleza "serie derivada" para que
     ninguna consulta futura la mezcle? (propuesta: se usa `update_source` + un campo `naturaleza`)
```
