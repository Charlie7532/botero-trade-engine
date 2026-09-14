# US Dollar Index Intelligence — Reference Document

> **Auto-generated**: 2026-09-10T16:45:00Z | **Source**: `dxy_fact_store.json` | **Status**: `VALIDATED (V3 + Sprint 2)`

## 1. Ficha Técnica del Indicador
- **Nombre**: US Dollar Index (`DXY`)
- **Fórmula**: Trade-weighted geometric mean of USD vs 6 currencies (EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='DXY', timeframe='1d').
- **Rango Histórico**: 1993-01-29 → present (6,801 barras diarias / 27.0 años).
- **Categoría METAR**: `CAT1_MACRO` — Indicador de condiciones macro de liquidez global.

---

## 2. Mecánica Intermarket

### DXY ↑ (Dollar Fuerte)
- **Commodities ↓**: Petróleo/Oro en USD → deflación de materias primas
- **EM Carry Trade Stress**: Deuda emergente en USD encarecida → flight-to-quality
- **Global Liquidity Squeeze**: Capital regresa a USD → contracción de liquidez global
- **Corporate Margin Compression**: Multinacionales USA con ingresos overseas sufren FX headwind

### DXY ↓ (Dollar Débil)
- **Commodities ↑**: Import inflation → Oil/Gold cost-push
- **EM Capital Inflow**: Carry trade atractivo → flujos hacia EM
- **Reflation**: Condiciones financieras más laxas globalmente
- **Weaker Import Costs**: Consumidor USA beneficiado

### DXY vs Rates
- **Régimen QT**: DXY↑ + TNX↑ (correlación positiva)
- **Flight-to-Safety**: DXY↑ + TNX↓ (correlación negativa — Treasuries como refugio)
- **No lineal**: La correlación es régimen-dependiente, no constante

---

## 3. Dimensiones Gaussianas

### D1 — Magnitud Puntual (6 bins, 5 edges)
| Bin | Label | Interpretación |
|:---:|---|---|
| 0 | `EXTREME_WEAKNESS` | Dollar en mínimos históricos → EM boom, commodities máximos |
| 1 | `WEAKNESS` | Dollar débil → condiciones financieras laxas |
| 2 | `NEUTRAL_SOFT` | Rango medio-bajo → sin presión significativa |
| 3 | `NEUTRAL_FIRM` | Rango medio-alto → presión moderada sobre EM |
| 4 | `STRENGTH` | Dollar fuerte → stress en carry trades |
| 5 | `EXTREME_STRENGTH` | Dollar en máximos → crisis de liquidez global potencial |

### D2 — Velocidad Cinemática 3d
Cambio absoluto de DXY en 3 días de trading. Clasificado en 5 bins gaussianos.

### D3 — Volatilidad Intra-Indicador
Ratio std(2d)/std(10d). Mide la estabilidad interna del movimiento.

---

## 4. Señales Operativas Clave

- **EXTREME_STRENGTH + FAST_SPIKE**: Posible crisis de liquidez global → STK_BLOCK_CRISIS
- **EXTREME_WEAKNESS + FAST_CRUSH**: Capitulación del USD → inflación importada inminente
- **D2 Flip en extremos**: Señal de reversión de condiciones macro
- **Divergencia DXY vs VIX**: Si DXY↑ sin VIX↑ → stress silencioso en EM (no visible en equity vol)

---

## 5. Notas de Implementación
- **Ticker Vault**: `DXY` en `market.ohlcv_bars`
- **Fact Store**: `dxy_fact_store.json` — 128 estados, V3 dual-layer + Sprint 2 enrichment
- **Generador**: `generate_dxy_fact_table.py` (generador independiente, no usa `build_v3_dual_layer_fact_store`)
- **Sprint 2 fields**: `n_independent`, `ci95_lo/hi`, `p_bh`, `grade`, `tier_rareza`, `caso_de_estudio_§3.3`
