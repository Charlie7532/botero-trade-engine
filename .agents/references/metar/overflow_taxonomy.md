# METAR Overflow & Blow-Off Taxonomy

> **Módulo de**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) §17 + §18
> **Status**: `PRODUCTION` | **Last Update**: 29-Ago-2026
> **Relacionados**: [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md), [gaussian_scale_policy.md](file:///root/botero-trade/.agents/references/metar/gaussian_scale_policy.md)
> **Implementación**: [`sigma_overflow.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/sigma_overflow.py)

---

## 1. Principio

Los fact stores clasifican estados en 6 bins D1 con clipping gaussiano a ±2σ. Un `EXTREME_PANIC` a +2.1σ y uno a +11σ reciben el mismo bin. La capa de Overflow/Blow-Off **no toca los fact stores** — opera en paralelo usando el z-score crudo para graduar la severidad.

**Fórmula:** `z_score = (value − μ) / σ` donde `μ, σ` provienen de `STATION_MU_SIGMA`.

---

## 2. Escala Graduada de Severidad (5 Tiers)

| Tier | Rango σ | `hazard_type` | Severidad | Frecuencia | Acción |
|:---:|:---:|---|:---:|---|---|
| **T1** | 3σ – 4σ | `OVERFLOW_MODERADO` | WARNING ⚠️ | ~14.2% | `STK_HOLD_STABLE` |
| **T2** | 4σ – 5σ | `OVERFLOW_EXTREMO` | CRITICAL 🚨 | ~4.1% | `STK_BLOCK_CRISIS` |
| **T3** | 5σ – 7σ | `BLOW_OFF_SEVERE` | EMERGENCY 🔴 | ~1.4% | Circuit Breaker si ≥2 estaciones |
| **T4** | 7σ – 10σ | `BLOW_OFF_EXTREME` | CATASTROPHIC ⛔ | ~0.35% | Supervivencia + contrarian post |
| **T5** | ≥ 10σ | `BLOW_OFF_SYSTEMIC` | SYSTEMIC 💀 | ~0.15% | Preservación capital absoluta |

> Las frecuencias son sobre cualquier canal (11 estaciones × 3 dimensiones = 33 canales).

---

## 3. Tipos SIGMET Existentes (implementados)

`_check_overflow_sigmet()` en `market_sigmet_hazard_service.py` emite:

| Condición | `hazard_type` | Severidad |
|---|---|:---:|
| ≥2 dimensiones >±3σ simultáneamente | `OVERFLOW_MULTI` — Black Swan Anomaly | CRITICAL 🚨 |
| max(sigma_depth) > 4σ | `OVERFLOW_EXTREMO` | CRITICAL 🚨 |
| 3σ < max(sigma_depth) ≤ 4σ | `OVERFLOW_MODERADO` | WARNING ⚠️ |

**Identificador:** `SIGMET-{TIER}-{station}-{dimension}-{fecha}-{depth}σ`

---

## 4. Evidencia Empírica (Vault, 1993-2026)

### T3: BLOW_OFF_SEVERE (5σ – 7σ) — ~120 eventos en 33 años
```
VIX_D1:   max=8.18σ   (44 días ≥5σ)  — pánico sostenido multi-día
VIX_D2:   max=11.11σ  (40 días ≥5σ)  — velocidad de spike extrema
PCR_D1:   max=12.61σ  (15 días ≥5σ)  — capitulación en opciones
Credit_D2: max=8.64σ  (22 días ≥5σ)  — velocidad de estrés crediticio
```

### T4: BLOW_OFF_EXTREME (7σ – 10σ) — ~30 eventos en 33 años
```
VIX_D1:    8 días ≥7σ   — solo GFC 2008 y COVID 2020
PCR_D1:   12 días ≥7σ   — capitulación institucional completa
Credit_D2: 7 días ≥7σ   — desplome crediticio sistémico
```

### T5: BLOW_OFF_SYSTEMIC (≥10σ) — 13 eventos en 33 años
```
PCR_D1:      6 días ≥10σ  — put/call en territorio sin precedentes
PCR_D2:      4 días ≥10σ  — aceleración extrema del pánico
VIX_D2:      2 días ≥10σ  — velocidad de spike solo en GFC/COVID
Rotation_D2: 1 día  ≥10σ  — rotación sectorial violenta
```

---

## 5. Blow-Off vs Overflow

| | Overflow (T1-T2) | Blow-Off (T3-T5) |
|---|---|---|
| **Qué mide** | Fuera de campana gaussiana | Evento de cola extrema |
| **Analogía** | Tormenta severa (80+ km/h) | Huracán categoría 5 (200+ km/h) |
| **Duración** | 1-3 días | Clusters de 5-15 días |
| **Señal** | Reducir exposición | Circuit breaker + acumulación contrarian post |

---

## 6. Protocolo Operacional

```
T1 (3-4σ): METAR flag ⚠️ | Gate: mantener, no añadir | URGENCY_NORMAL
T2 (4-5σ): SIGMET emitido | Gate: bloquear entradas  | URGENCY_HIGH
T3 (5-7σ): SIGMET elevado | CIO: reducir 25-50%     | URGENCY_EMERGENCY
T4 (7-10σ): Circuit Breaker | CIO: solo coberturas   | URGENCY_EMERGENCY
T5 (≥10σ): NOTAM infra    | CIO: preservación total  | URGENCY_EMERGENCY
```

---

## 7. Reglas

1. **T3-T5 son extensión, no reemplazo.** T1 y T2 mantienen nombres y lógica existente.
2. **Blow-Off cluster:** ≥3 días consecutivos en T3+ → protocolos de supervivencia hasta 5 días consecutivos en T0.
3. **Post-Blow-Off = señal contrarian.** Los 10-20 días post T4+ = ventana de acumulación institucional (consistente con `regime_change_exit` como detector Wyckoff).
4. **D3 raramente alcanza T3+.** El ratio `std(2)/std(10)` está físicamente acotado (~5.3σ max). Blow-offs ocurren en D1 y D2.
5. **`sigma_overflow.py` pendiente de extender** para retornar tier name además de `(sigma_depth, flag)`.

---

## 8. Inventario Histórico (34 eventos >3σ en pivotes)

| Fecha | Estación | Valor | Label D1 (clipped) |
|---|---|---|---|
| 2020-03-16 | VVIX | 207.59 | EXTREME_INSTABILITY |
| 2010-02-05 | PCR | 2.872 | EXTREME_PUT_PANIC |
| 2024-12 / 2025-02 | SKEW | 173.7–175.8 | EXTREME_PARANOIA |
| 2026-06-26 | SV5 Turb | 26.307 | EXTREME_TURBULENT |
| 2002-01-31 | DXY | 120.28 | EXTREME_STRENGTH |
| 2008-10-15 | Yield | 3.811 | EXTREME_STEEPNING |
| 2023-05-04 | Yield | −1.705 | DEEP_INVERSION |
