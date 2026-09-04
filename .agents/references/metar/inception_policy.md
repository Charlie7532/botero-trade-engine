# POLÍTICA GENERAL DE INCEPTION — METAR (Canónica)

**Fecha:** 03-Sep-2026
**Status:** CANONICAL SOURCE OF TRUTH — política obligatoria de todas las evaluaciones.
**Regla rectora:** **Una estación/senal NO existe antes de su `fecha_inicio_valida`** (su nacimiento). Ningún dato pre-inception es válido; ninguna evaluación puede usarlo.

---

## 1. La Regla

Una estación de telemetría METAR representa una serie cuyo valor **solo es válido desde su fecha de inicio** (`fecha_inicio_valida`). Antes de esa fecha la señal **no existe** (o es dato sintético/inválido). Por lo tanto:

1. **Cualquier disparo/observación/estado con fecha < `fecha_inicio_valida`** de su estación se **EXCLUYE** de la evaluación (no es falla, es pre-nacimiento).
2. **Toda calibración** (cuantiles empíricos, bins, z-scores, medias, estadísticos, overflows) se computa SOLO sobre la muestra ≥ inception de la estación.
3. **Todo generador/evaluador** que procese señales DEBE filtrar por inception. No hacerlo = BUG de política.

**Motivación:** evita contaminar la calibración con datos sintéticos/inválidos (ej. SKEW o F&G pretendidos desde 1990 cuando solo existen desde 2011, o CREDIT antes de 2007). El 29-Ago y 03-Sep-2026 se detectaron múltiples señales contaminadas por pre-inception (panico_total 61%, stealth 42%, skew_paranoia 19%).

### 1.1 Regla Adicional — No incluir periodos pre-SPY (pre-1993) 🔴

**La ventana de evaluación es el SPY (lake desde 1993-01-29).** La calibración de una estación **NUNCA incluye historia anterior al inicio de la ventana de evaluación SPY**, incluso si el Vault tiene series más antiguas.

- **Por qué:** el sistema evalúa señales contra el SPY; datos anteriores a 1993 no pertenecen a la ventana de evaluación. Incluirlos (ej. DXY desde 1970, YIELD desde 1962) **descalibra** contra la población que realmente se evalúa.
- **Regla efectiva:** la muestra válida de calibración de cada estación = **`max(fecha_inicio_valida, 1993-01-29)`** (es decir, el nacimiento de la estación NO antes del inicio del SPY).
- **Ejemplos:**
  - **DXY:** Vault tiene DXY desde ~1970, pero la muestra válida para evaluación SPY es **≥ 1993-01-29**. **No incluir los 1970s-80s.**
  - **YIELD_CURVE:** Vault desde 1962, pero **≥ 1993-01-29** para SPY. No incluir pre-1993.
  - **SKEW / F&G:** nacen en 2011 (posterior a 1993) → fecha efectiva es 2011-02-01 (su inception prevalece por ser más reciente).
- **Excepción:** estaciones que nacen después de 1993 (SKEW, F&G, CREDIT, etc.) usan su propio inception (>1993) como límite; la regla 1993 solo "recorta" la historia que la estación pudiera tener ANTES del SPY (DXY, Yield, VIX, BSI, Rotation).

**Fórmula unificada:**

```
fecha_valida_calibracion(estacion) = max(fecha_inicio_valida(estacion), 1993-01-29)  # inicio SPY
```

Esto garantiza: **no datos pre-inception + no datos pre-SPY** = calibración solo sobre la población que la evaluación realmente usa.

---

## 2. Inception Dates Canónicas (fuente: `_CERTEZA` / registro METAR)

| Estación | fecha_inicio_valida | Nota |
|:---------|:-------------------|:-----|
| VIX | 1990-01-02 | desde inicio dato real |
| VVIX | 2006-03-06 | |
| PCR | 2006-11-01 | |
| F&G | 2011-02-01 | NO es válido antes (serie comercial inicia 2011) |
| SV5_TURBULENCE | 1999-01-04 | |
| SKEW | 2011-02-01 | **NO es válido desde 1990 — solo 2011** |
| CREDIT | 2007-04-11 | NO es válido antes |
| YIELD_CURVE | 1993-01-29 | (dato real SPY-era) |
| ROTATION | 1999-01-04 | |
| DXY | 1993-01-29 | (dato real SPY-era; Vault tiene 1970+, pero para SPY solo 1993+) |
| BSI | 1993-01-29 | |

> **DXY matiz:** el Vault contiene DXY desde ~1970, pero para evaluación SPY (lake desde 1993), la muestra válida de calibración es **≥ 1993-01-29** (nacimiento en la ventana de evaluación). No incluir los 1970s pre-SPY.

---

## 3. ¿Dónde se aplica? (estado de cumplimiento)

| Módulo | Filtro inception | Estado |
|:-------|:-----------------|:-------:|
| `evaluador_vela_a_vela.py` | ✅ Sí (L211-218, L271) | Cumple |
| `evaluador_general.py` | ✅ Sí (L273-274, L492-519) | Cumple |
| `consultar_inteligencia.py` | ✅ Sí (era_start) | Cumple |
| `construir_bar_snapshot.py` | ❌ **No** (genera bar_signals) | 🔴 **BUG — corregir** |
| `arnes/medicion.py` | ❌ **No** (núcleo medición señales) | 🔴 **BUG — corregir** |
| `ejercicios_regimen.py` | ❌ **No** | 🔴 **BUG — corregir** |
| `consolidar_ranking.py` | ⚠️ Por verificar | 🟡 |

---

## 4. Implementación de referencia

Filtro estándar (patrón ya usado en VAV y GENERAL):
```python
fecha_inicio = certeza.get("fecha_inicio_valida")
if fecha_inicio:
    mask_inicio = (df.index >= pd.Timestamp(fecha_inicio))
    disparos = disparos[mask_inicio]
    # NOTA: no es falla, es exclusion por pre-nacimiento
```

Para calibración de cuantiles/edges (expanding, sin look-ahead):
```python
# Sobre la serie ALINEADA al SPY (lake), filtrar por inception, luego expanding
serie_valida = serie[serie.index >= pd.Timestamp(fecha_inicio)]
z_edges = serie_valida.expanding(min_periods=252).quantile([0.135, 2.275, 15.866, 50, 84.134, 97.725, 99.865]/100.0)
```

---

## 5. Reglas operativas

1. **El inception se lee de `_CERTEZA`/registro**, nunca hardcodeado suelto (fuente única de verdad).
2. Un estado que caiga antes del inception = **`pre_inception`**, excluido de HR, conteos, lift y baselines — jamás contado como falla.
3. La calibración de escala (z, overflow) usa SOLO la muestra ≥ inception + filosofía expanding (sin look-ahead) — ver `2026-09-03-correccion-sigma-overflow-v2.md` D1-D8.
4. Cualquier script nuevo que procese señales debe incluir este filtro desde su diseño.

## 6. Historial de incidentes (por qué existe)

- **29-Ago-2026:** agente inventó/escorró labels en 9/11 estaciones; se añadió `test_taxonomy_integrity.py`.
- **03-Sep-2026:** `bar_augment` y señales contaminadas por pre-inception (panico_total 61%, stealth 42%, skew_paranoia 19%); BUG #2 reincidió en `construir_bar_snapshot.py`. → Esta política general se crea para impedir recurrencia.