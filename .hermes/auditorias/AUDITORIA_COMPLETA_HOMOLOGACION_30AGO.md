# AUDITORÍA COMPLETA — Homologación Canónica + Fase 0→7 (30-Ago-2026)

**Auditor:** deepseek/deepseek-v4-flash (Hermes)
**Verificación:** Independiente — cada punto contrastado con código, datos y ejecución.
**Estado general:** ✅ **APTO PARA PRODUCCIÓN, con 2 observaciones menores**

---

## 1. VERIFICACIONES END-TO-END

| # | Check | Resultado | Detalle |
|:-:|:------|:---------:|:--------|
| 1 | Suite completa (303 tests) | ✅ **303/303 passed (51s)** | Sin regresiones |
| 2 | `d1_directional_vote()` numérico | ✅ **6/6 tests OK** | VIX, Credit, labels nuevos, vacío |
| 3 | `quants_obs.pkl` regenerado | ✅ **1,590×165, 100% numérico** | 22 cols nuevas (overflow_tiers, d1_bin, etc.) |
| 4 | 31 señales activas | ✅ **31/31 disparan** | 28 originales + 3 V2 (capitulacion_v2, euforia_v2, vix_crisis_spike_v2) |
| 5 | `_get_dim()` con NaN | ✅ NaN → NaN (no label fantasma) | Columna faltante → todo NaN |
| 6 | Lake continuo | ✅ **8,453×257, 100% numérico** | 33 overflow_tier cols (3×11 estaciones) |
| 7 | Overflow tiers T1-T5 | ✅ **7/7 correctos** | map(z=3.5→T1, 4.5→T2, 6.0→T3, 8.0→T4, 12.0→T5) |
| 8 | `sigma_overflow.py` 11 estaciones | ✅ d1/d2/d3 completas | DXY incluida |
| 9 | `audit_overflow_candle_anatomy_v2` | ✅ **610 combinaciones** | Segregadas MIN/MAX/ENTRE, Tiers A/B/C |
| 10 | Panic/Euphoria scores en lake | ✅ Presentes | panic_score_pct normalizado por n_active |
| 11 | Pantallas de señales V2 | ✅ Funcionan | capitulacion_v2, euforia_v2, vix_crisis_spike_v2 |

---

## 2. OBSERVACIONES

### 🔶 OBSERVACIÓN 1 — `_regime_change_exit`: Gemini perdió 1 bin (menor)

**Archivo:** `research/01_señales_entry_exit/arnes/señales.py` — señal ya RETIRADA

| Condición | Original (labels) | Gemini (bins) | Correcto |
|:----------|:-----------------:|:-------------:|:--------:|
| Credit bins | `{CREDIT_CRISIS, CREDIT_STRESS, ELEVATED_CREDIT_STRESS}` | **<= 1** | **<= 2** |
| VIX bins | `{HIGH_VOL, ELEVATED_PANIC, CRISIS_SPIKE}` | >= 3 ✅ | >= 3 |
| BSI bins | `{BREADTH_WASHED_OUT, OVERSOLD_BREADTH, NEUTRAL_LOW_BREADTH}` | <= 2 ✅ | <= 2 |

**Impacto:** La señal está retirada (lift<1.0 desde el 20-Ago). Si se re-evalúa algún día, perdería observaciones donde Credit está en `NEUTRAL_TIGHT` (bin 2).

**Fix:** `credit_d1 <= 1` → `credit_d1 <= 2` (1 línea).

---

### 🔶 OBSERVACIÓN 2 — Fallback semántico de `d1_directional_vote()` no cubre labels viejos (documentado)

**Archivo:** `backend/modules/entry_decision/domain/services/convergence_compositor.py`

La función tiene 2 rutas:
1. **Labels semánticos NUEVOS**: `D1_BEARISH_BINS = {"EXTREME_PANIC", "PANIC", ...}` — ✅ funciona
2. **Bins numéricos**: `int("4") >= 4` — ✅ funciona

**Lo que NO cubre:** labels semánticos **VIEJOS** (`CRISIS_SPIKE`, `DEEP_COMPLACENCY`, etc.). Si algún script legacy pasa state_keys viejos, el fallback numérico falla → retorna 0.

**Impacto:** Bajo — toda la cadena fue regenerada con keys numéricos. Pero es un punto ciego en la retrocompatibilidad. Documentar como limitación conocida.

---

## 3. ESTADO DEL ARTE — MÉTRICAS POST-HOMOLOGACIÓN

### 3.1 Las 5 señales núcleo (confirmadas)

| Señal | Condición canónica | N | Edge zz75 | Patrón |
|:------|:------------------|:-:|:--------:|:------:|
| **capitulacion** | VIX≥3 + BSI==0 | 57 | +3.1% | CONV BULL |
| **pcr_put_panic** | PCR==5 | 70 | +4.5% | CONV BULL |
| **vvix_entry** | VVIX==5 | 69 | +4.5% | CONV BULL |
| **credit_stress** | Credit≤1 | 101 | +3.4% | CONV BULL |
| **bsi_washed_out** | BSI==0 | 117 | +5.4% | CONV BULL |

### 3.2 Los 2 diamantes §3.3

| Señal | Condición | N | Contexto |
|:------|:----------|:-:|:---------|
| **panico_total** | VIX≥4 + SKEW≥4 | 11 | 11/11 en crisis ±3σ |
| **skew_paranoia_exit** | SKEW==5 | 10 | 8/10 en crisis ±3σ |

### 3.3 Las 3 señales V2 (nuevas)

| Señal | Condición | N | Edge zz75 | Patrón |
|:------|:----------|:-:|:--------:|:------:|
| **capitulacion_v2** | VIX≥3 + BSI==0 + BSI.D2∈{0,1} | 20 | +4.1% | CONV BULL |
| **euforia_v2** | BSI≥4 + BSI.D2≥3 | 48 | −6.1% | CONV BEAR |
| **vix_crisis_spike_v2** | VIX==5 + VIX.D2≥3 | 61 | +3.4% | CONV BULL |

---

## 4. LIMITACIONES CONOCIDAS (heredadas, no introducidas)

1. **236 fechas de pivote duplicadas** (F4) — benigno, señales leen D1, no pivot_date
2. **Denominador variable de d1_bear_5** (BS3) — 64% de pivotes con <5 estaciones Grupo A
3. **Drift Expanding Rank vs Static Edges** — inherente al diseño dual research/producción
4. **62% de FG ausente pre-2011** — señal `capitulacion` opera sobre población reducida

---

## 5. FIRMA Y VEREDICTO

| Dimensión | Calificación |
|:----------|:-----------:|
| Rigor de la migración | **9.5/10** |
| Cobertura de tests | **10/10** (303 tests, +46 taxonomy) |
| Calidad del código | **9/10** (limpio, helpers reutilizables) |
| Atajos de Gemini | **1 encontrado** — menor, señal retirada |
| Documentación actualizada | **8/10** (docstrings recortados en cascade_reversal) |

**Veredicto global: ✅ APTO PARA PRODUCCIÓN** con 2 observaciones documentadas y 1 fix menor pendiente (1 línea en `_regime_change_exit` que no afecta operación).

La cadena completa está sincronizada: fact stores numéricos → lookup adapters → quants_obs → señales → evaluador → lake continuo. Cualquier agente futuro puede leer `d1_bin >= 4` sin ambigüedad.