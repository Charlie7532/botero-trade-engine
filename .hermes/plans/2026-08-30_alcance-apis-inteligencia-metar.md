# Prompt Maestro: Rediseño del Alcance de APIs — Inteligencia METAR

> **Propósito:** Las APIs actuales (`/api/metar/*`, `/api/sigmet/*`, `/api/notam/*`) exponen datos crudos de las 11 estaciones pero NO comunican la inteligencia diferencial que el sistema METAR ya produce. Este documento define qué deben exponer para que un frontend (o cualquier consumidor) reciba **edge procesado**, no datos sin contexto.
>
> **Arquitecto:** Juan Andrés Botero
> **Fecha:** 30-Ago-2026
> **Filosofía:** Dato mata relato. Cada endpoint debe responder una pregunta de inversión, no mostrar una tabla de números.

---

## Diagnóstico: Estado Actual vs Inteligencia Disponible

### Lo que las APIs expone HOY

| Endpoint | ¿Qué devuelve? | Problema |
|---|---|---|
| `GET /api/metar/{station}` | D1/D2/D3 crudos + TAF (p_bull, ev_net) | No dice si el D2 está acelerando o resolviendo — el timing no se comunica |
| `GET /api/metar/all` | 11 estaciones en paralelo | Muestra estaciones aisladas, no la confluencia vectorial entre ellas |
| `GET /api/metar/convergence` | ConvergenceReport (parcial) | Cascade Conviction enterrado, sin endpoint propio |
| `GET /api/sigmet/active` | Hazard bulletins | Solo condiciones extremas binarias |
| `GET /api/notam/*` | Incidentes operativos | OK — notam es notam |

### Inteligencia VALIDADA que NO se comunica

| # | Inteligencia | Sustento | Dónde vive | Lo que la API debería exponer |
|---|---|---|---|---|
| **I1** | **Cascade Conviction** | IC +0.43 IS, +0.35 OOS, PBO 0% | `convergence_compositor.py` | `{ score, bear_weight, domino_weight, d1_vote, type_mask, conviction_status }` |
| **I2** | **σ-Overflow T1-T5** | Tiers homologados en taxonomía | `sigma_overflow.py` classifica pero no expone tier | `{ station, dim, z_score, tier: "T1"..."T5", hazard_type }` |
| **I3** | **Confluencia vectorial** | 1 canal = 52-59% WR, 4+ canales = 72-82% WR | Hallazgo 29-Ago, no en producción | `{ confluence_count, stations_in_overflow[], signal_quality: "noise"|"emerging"|"diamond" }` |
| **I4** | **Timing D2** | VIX D2>0 = short 3× más fuerte, 0 wipeouts | Validado en `timing_derisking.py` | `{ station, d2_direction: "building"|"resolving", delta_3d, timing_multiple }` |
| **I5** | **Rareza §3.3** | N<21 = diamante, CI95 Clopper-Pearson, sin Bonferroni | Protocolo §3.3 en walkthrough | `{ station, current_n, classification: "normal"|"diamond"|"ultra_rare", p_value, ci95 }` |
| **I6** | **Lead-Lag inter-estación** | SKEW lidera 27d, BSI 22d, VVIX 2ª deriv | Múltiples sesiones OOS | `{ leader_matrix: [{ leader: "SKEW", lag: "VIX", days: 27 }] }` |
| **I7** | **Señales activas** | 31 señales medidas, walk-forward OOS | `signal_cataloger.py`, `validacion_oos_catalogo_v7.json` | `{ name, status: "FIRED"|"STALK"|"SLEEPING", conviction, edge_defensivo, wr }` |
| **I8** | **Polaridad asimétrica** | Capitulación WR 73-83% MIN, Euforia SHORT ≤30% ENTRE | `analisis_estrategico_integracion_vector.md` | `{ panic_score, euphoria_score, asymmetry_ratio, pivot_type }` |
| **I9** | **Estructural break era** | GFC 2009-03-09 cambió el régimen | User define eras entre crisis | `{ current_era: "pre_qe"|"post_qe", signal_stability: "stable"|"degrading" }` |

---

## Especificación: Nuevos Endpoints de Inteligencia

### Grupo 1: METAR — Inteligencia de Estaciones (expandir)

#### `GET /api/metar/{station}` → Ampliar con timing + rareza

```json
{
  "metar_id": "METAR-VIX-2026-08-30",
  "station": "vix",
  "value": 31.2,
  "state_key": "4__3__3",
  "d1_bin": 4,
  "d1_label": "PANIC",
  "d1_vote": -1,
  "d2_bin": 3,
  "d2_direction": "building",
  "d2_velocity_3d": 2.1,
  "d3_bin": 3,
  "overflow_tier": { "d1": "T2", "d2": null, "d3": null },
  "z_scores": { "d1": 4.2, "d2": 1.8, "d3": 1.4 },
  "rarity": {
    "current_n": 34,
    "classification": "diamond",
    "ci95_lo": 0.55,
    "ci95_hi": 0.88,
    "p_raw": 0.003
  },
  "taf": {
    "zz25": { "p_bull": 0.37, "ev_net": -1.2, "e_days": 4.5, "ev_per_day": -0.27 },
    "zz50": { "p_bull": 0.22, "ev_net": -2.8, "e_days": 7.1, "ev_per_day": -0.39 }
  },
  "lead_lag": {
    "leads": [],
    "lagged_by": ["skew", "bsi"]
  }
}
```

#### `GET /api/metar/all` → Ampliar con confluencia + polaridad

```json
{
  "registered_count": 11,
  "active_count": 11,
  "metars": { /* 11 stations con el shape de arriba */ },
  "confluence": {
    "total_stations_in_overflow": 4,
    "confluence_count": 4,
    "signal_quality": "diamond",
    "stations_in_overflow": ["vix", "skew", "vvix", "pcr"],
    "panic_score": 7,
    "euphoria_score": 1
  }
}
```

### Grupo 2: Convergencia / Cascade Conviction (NUEVO)

#### `GET /api/metar/cascade`

```json
{
  "timestamp_utc": "2026-08-30T15:00:00Z",
  "conviction_score": 0.74,
  "bear_weight": 0.66,
  "domino_weight": 0.34,
  "d1_vote": -1,
  "directional_bias": "bearish",
  "type_mask": "MIN",
  "validated": {
    "ic_is": 0.4313,
    "ic_oos": 0.3481,
    "pbo": 0.0,
    "last_calibration": "2026-08-01"
  }
}
```

#### `GET /api/metar/convergence` → Expandir con TAF agregado

```json
{
  "cascade": { /* cascade shape above */ },
  "taf_aggregate": {
    "bullish_stations": 2,
    "bearish_stations": 7,
    "neutral_stations": 2,
    "consensus": "bearish"
  },
  "timing": {
    "d2_building_stations": ["vix", "vvix", "skew"],
    "d2_resolving_stations": ["pcr", "credit"],
    "fastest_station": "vvix",
    "fastest_delta_3d": 4.8
  }
}
```

### Grupo 3: Overflow / Confluencia (NUEVO)

#### `GET /api/metar/overflow`

```json
{
  "timestamp_utc": "2026-08-30T15:00:00Z",
  "confluence_count": 4,
  "tiers_by_station": {
    "vix": { "d1": { "tier": "T2", "z_score": 4.2 }, "d2": null, "d3": null },
    "skew": { "d1": { "tier": "T1", "z_score": 3.4 }, "d2": null, "d3": null }
  },
  "historical_context": {
    "current_confluence_percentile": 92,
    "last_time_this_high": "2026-03-15",
    "avg_wr_at_this_level": 0.74
  }
}
```

#### `GET /api/metar/overflow/confluence` → El hallazgo vectorial

```json
{
  "n_stations_in_overflow": 4,
  "signal_quality": "diamond",
  "expected_wr_range": [0.72, 0.82],
  "stations": ["vix", "skew", "vvix", "pcr"],
  "operational_guidance": "STK_ACCUMULATE_STRUCTURAL"
}
```

### Grupo 4: Señales Activas (NUEVO)

#### `GET /api/signals/active`

```json
{
  "active_signals": [
    {
      "name": "capitulacion",
      "status": "FIRED",
      "conviction": 0.83,
      "edge_defensivo": 6.86,
      "edge_ofensivo": 1.4,
      "wr": 65.9,
      "precursor": "credit.D2=ACCELERATING_UP_3D",
      "n_lose": 3,
      "oos_validated": true
    }
  ],
  "staliking_signals": [
    {
      "name": "pcr_put_panic",
      "status": "STALK",
      "conviction": 0.31,
      "degrading": true,
      "note": "WR cayó 76%→56% en 2020s"
    }
  ]
}
```

### Grupo 5: Lead-Lag (NUEVO)

#### `GET /api/metar/leadlag`

```json
{
  "timestamp_utc": "2026-08-30T15:00:00Z",
  "lead_lag_matrix": [
    { "leader": "skew", "lag": "vix", "lead_days": 27, "spearman_r": 0.42, "p_value": 0.001 },
    { "leader": "bsi", "lag": "vix", "lead_days": 22, "spearman_r": 0.38, "p_value": 0.003 },
    { "leader": "vvix", "lag": "vix", "lead_days": 5, "spearman_r": 0.31, "p_value": 0.01 }
  ],
  "current_regime": {
    "leaders_pulling": ["skew"],
    "leaders_stalling": [],
    "anomaly_detected": false
  }
}
```

### Grupo 6: Estructural Break / Eras (NUEVO)

#### `GET /api/metar/era`

```json
{
  "current_era": "post_qe",
  "era_start_date": "2009-03-09",
  "signals_stability": {
    "stable": ["capitulacion", "credit_easing_k1", "bsi_washed_out"],
    "degrading": ["pcr_put_panic"],
    "retired": ["dxy_bearish"]
  },
  "structural_break_dates": [
    { "event": "GFC", "date": "2009-03-09", "type": "major" },
    { "event": "COVID", "date": "2020-03-23", "type": "minor" }
  ]
}
```

---

## Estrategia de Implementación

### Fase 1: Backend Services (2-4 días)

1. **Migrar `sigma_overflow.py` a `classify_overflow_tier()`**
   - Agregar función que retorna tier (T1-T5), no solo UPPER/LOWER
   - Integrar en cada metar service

2. **Crear `confluence_service.py`**
   - Lee todas las 11 estaciones, cuenta cuántas están en overflow
   - Mapea al WR conocido por nivel de confluencia
   - Expone `panic_score` y `euphoria_score`

3. **Crear `rarity_service.py`**
   - Por cada estación, trackea N de observaciones en ese state_key
   - Clasifica según §3.3: N<21 diamente, N<10 ultra-raro
   - Expone CI95 Clopper-Pearson + p_raw (sin Bonferroni)

4. **Crear `lead_lag_service.py`**
   - Matriz de Spearman cross-correlación entre estaciones
   - Pre-computada semanalmente (no en vivo)

5. **Exponer `signal_cataloger.py` como servicio**
   - Endpoint que lee `validacion_oos_catalogo_v7.json`
   - Filtra señales activas vs durmiendo vs retiradas

6. **Crear `cascade_conviction_service.py`**
   - Endpoint dedicado para cascade conviction
   - Expone score, pesos, type_mask, métricas de validación

### Fase 2: Nuevos Endpoints API (1-2 días)

| Nuevo Endpoint | Backend Service |
|---|---|
| `GET /api/metar/cascade` | `cascade_conviction_service.py` |
| `GET /api/metar/overflow` | `confluence_service.py` + `sigma_overflow.py` |
| `GET /api/metar/overflow/confluence` | `confluence_service.py` |
| `GET /api/metar/leadlag` | `lead_lag_service.py` |
| `GET /api/metar/era` | `era_service.py` (NUEVO) |
| `GET /api/signals/active` | `signal_cataloger_service.py` (NUEVO) |

### Fase 3: Ampliar Endpoints Existentes (1 día)

| Endpoint Existente | Lo que se añade |
|---|---|
| `GET /api/metar/{station}` | `overflow_tier`, `rarity`, `d2_direction`, `lead_lag` |
| `GET /api/metar/all` | `confluence`, `panic_score`, `euphoria_score` |
| `GET /api/metar/convergence` | `timing`, `taf_aggregate`, cascade expandido |

### Fase 4: Frontend — Componentes UI (2-3 días)

| Componente | Endpoint que consume |
|---|---|
| **Cascade Gauge** (score + bias) | `GET /api/metar/cascade` |
| **Confluence Radar** (cuántas estaciones en overflow) | `GET /api/metar/overflow/confluence` |
| **Timing D2 Indicator** (building vs resolving por estación) | `GET /api/metar/{station}` → `d2_direction` |
| **Rarity Badge** (diamante vs normal por estación) | `GET /api/metar/{station}` → `rarity` |
| **Señales Activas Panel** | `GET /api/signals/active` |
| **Lead-Lag Graph** (Gráfico de quién lidera a quién) | `GET /api/metar/leadlag` |
| **Era Banner** (era actual + señales estables/degradando) | `GET /api/metar/era` |

---

## Anti-Patrones (NUNCA hacer)

1. ❌ Exponer `metar.to_dict()` sin añadir las capas de inteligencia
2. ❌ Calcular confluencia, rareza o lead-lag en el frontend — debe venir del backend
3. ❌ Mostrar state_key crudo `"4__3__3"` sin tooltip de qué significa
4. ❌ Ignorar la asimetría piso/techo (capitulación ≠ euforia)
5. ❌ Aplicar Bonferroni a señales con N<21 (§3.3)
6. ❌ Tratar señales en era post-QE con thresholds pre-QE
7. ❌ No incluir el `d2_direction` — sin él el timing está ciego

---

## Verificación

Antes de dar por implementado:

- [ ] Cada endpoint nuevo responde con 200 + schema correcto
- [ ] `GET /api/metar/overflow/confluence` retorna WR esperado según N canales
- [ ] `GET /api/metar/{vix}` incluye `d2_direction`, `overflow_tier`, `rarity`
- [ ] `GET /api/signals/active` retorna solo señales validadas OOS
- [ ] Tests existentes en `test_metar_router.py` siguen pasando
- [ ] 244/244 tests del suite completo pasan

---

## Open Questions

1. **Lead-lag:** ¿Se computa en vivo (cada llamada API) o se cachea semanalmente? **Respuesta:** Semanalmente — no cambia en días.
2. **Confluencia histórica:** ¿Guardamos percentil de confluencia para saber "última vez que pasó esto"? **Respuesta:** Sí — tabla en Neon con timestamp + confluence_count.
3. **Señales activas:** ¿Endpoint público o requiere auth? **Respuesta:** Solo interno por ahora.
4. **Eras:** ¿Quién define el structural break? ¿Manual (Juan Andrés) o algoritmo de detección? **Respuesta:** Manual por ahora — algoritmo detection como V2.