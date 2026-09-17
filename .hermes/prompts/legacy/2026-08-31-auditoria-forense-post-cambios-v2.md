# AUDITORÍA FORENSE — Cambios Post-Homologación (66 archivos) — v2

**Auditor:** deepseek/deepseek-v4-flash
**Archivos auditados:** 66
**Calificación general:** 8/10 — Aprobado con 8 hallazgos críticos que corregir

---

## 🔴 BUG #1 — CRÍTICO: `e_ret_max`/`e_ret_min` siempre None en compositor

### Ubicación
`convergence_compositor.py` L388-392

### Código problemático
```python
zz75_data = data.get("zz75", {})   # ← SIEMPRE retorna {} 
e_ret_max_5d = zz75_data.get("e_ret_max")   # ← siempre None
e_ret_min_5d = zz75_data.get("e_ret_min")   # ← siempre None
```

### Causa
El `MarketMETAR.to_dict()` NO tiene una clave `"zz75"`. Las escalas individuales no se serializan — solo existen vectores agregados (`p_bull_vector`, `ev_net_vector`, etc.). `e_ret_max` y `e_ret_min` existen en `ScaleGuidance` dentro del lookup, pero **nunca se propagaron** al `MarketMETAR` dataclass.

### Impacto
`station_summaries["e_ret_max_5d"]` y `station_summaries["e_ret_min_5d"]` son **siempre None para las 11 estaciones**. El canal "Cono de Dispersión" (para sizing de stops/targets) no funciona.

### Fix
Agregar `e_ret_max_5d` y `e_ret_min_5d` al dataclass `MarketMETAR` en los 11 `*_metar_service.py`, poblarlos desde `guidance.zz75.e_ret_max`, y luego leerlos en el compositor como `data.get("e_ret_max_5d")`.

---

## 🔴 BUG #2 — CRÍTICO: SKEW — Datos pre-2011 (sintéticos) sin filtrar en cadena de evaluación

### Alcance del problema
El CBOE SKEW es oficial desde 2011-02-01. Datos pre-2011 son sintéticos (backtest) y estadísticamente inválidos para cualquier análisis de señales, fact stores, o evaluadores.

### Estado actual de filtros

| Componente | ¿Filtra pre-2011? | Detalle |
|:-----------|:-----------------:|:--------|
| `v3_fact_table_engine.py` L478 | ✅ **PARCIAL** | Thresholds D1/D2/D3 calibrados solo post-2011. Pero el expanding rank se computa sobre toda la serie (correcto: no look-ahead). |
| `arnes/señales.py` — señales con SKEW | ✅ Metadata | `fecha_inicio_valida="2011-02-01"` existe en `panico_total`, `skew_paranoia_exit`, `stealth_tail_hedging`, `fg_extreme_fear`, `fg_extreme_greed` |
| `evaluador_general.py` L464 | ✅ **CORRECTO** | Lee `fecha_inicio_valida` y filtra `lake_idx` con `mask_valida`. |
| **`evaluador_vela_a_vela.py`** | ❌ **NO FILTRA** | No lee `fecha_inicio_valida` del metadata. Evalúa todas las señales con datos completos. |
| **`stealth_tail_hedging`** | ❌ **BUG CONFIRMADO** | **13/29 disparos (45%) son pre-2011 con SKEW sintético.** Contamina el ranking. |
| **`build_continuous_metar_lake.py`** | ❌ **NO FILTRA** | No hay filtro por inception date para SKEW en el lake builder. |
| **`skew_lookup.py`** (backend) | ❌ **NO FILTRA** | No hay filtro de fecha. El fact store contiene datos pre-2011. |
| **40+ scripts research** | ❌ **NO FILTRAN** | Scripts en `03_estaciones_metar/`, `04_conjuncion_*` que leen SKEW no filtran. |

### Impacto cuantificado
```python
# stealth_tail_hedging:
# Pre-2011 (sintetico): 13 disparos — INVÁLIDO
# Post-2011 (CBOE real): 16 disparos — VÁLIDO
#  45% de la muestra es basura.
```
# D3=3,4 de SKEW:
D#3=3: pre=147 estados, post=63 —  70% son sintéticos
D3=4: pre=17 estados, post=14 —  55% son sintéticos

# to das las metricas de D3 de SKEW pre-2011 son inválidas por construcción.mat
```

### Correccin requerida (6 puntos)

**1. Evaluador vela-a-vela** — Leer `fecha_inicio_valida` del metadata (`_CERTEZA`) y filtrar disparos pre-inception:

```python
# En evaluar() de evaluador_vela_a_vela.py:
fecha_inicio = _CERTEZA.get(señal_nombre, {}).get("fecha_inicio_valida")
if fecha_inicio:
    disp = disparos[disparos["pivot_date"] >= pd.Timestamp(fecha_inicio)]
else:
    disp = disparos
```

**2. Lake builder** — Agregar filtro post-2011 para SKEW en `build_continuous_metar_lake.py`

**3. Research scripts (priorizar):** `e11_triada_convergencia.py`, `pcr_completo.py`, `conjuncion_posicionamiento.py`, `sigmet.py` — verificar que usan datos SKEW válidos

**4. `skew_fact_store.json`** — Si se regenera, asegurar que el generador filtre datos pre-2011

**5. Documentar** que `D3=3,4` de SKEW no es "N bajo" — es evento de cola por construcción. Protocolo §3.3.

---

## 🟡 BUG #3 — MEDIO: NOTAM promete FOMC Blackout pero no lo implementa

### Ubicación
`notam_incident_service.py` L6, L64 (docstring promete) vs código (no existe)

### Evidencia
```python
# Docstring L62-65:
# Checks:
# 1. Pipeline freshness...
# 2. Macro Circuit Breaker...
# 3. FOMC Blackout Window status    ← PROMETIDO
```
`grep "FOMC\|fomc\|blackout" notam_incident_service.py` → 0 resultados en el código ejecutable.

### Impacto
El servicio NOTAM dice chequear 3 condiciones pero solo implementa 2. El calendario FOMC existe en `macro_calendar.py` pero nunca se conectó.

---

## 🟡 BUG #4 — MEDIO: `pcr_completo.py` reporte timing siempre 0 (display)
✅ **YA CORREGIDA** en intervención anterior.

---

## 🟡 BUG #5 — MEDIO: `skew_paranoia_exit` — Contradicción tipo vs BLANCOS

### Ubicación
`arnes/señales.py` L253-258

### Detalle (hallazgo de Claude)
| Campo | Valor actual | Valor correcto |
|:------|:------------:|:--------------:|
| `_registrar tipo=` | `"entry"` | `"exit"` |
| `BLANCOS[]` | `"MAX"` | `"MAX"` (consistente con EXIT) |
| Nombre | `skew_paranoia_exit` | `skew_paranoia_exit` |

El nombre dice "exit", el BLANCO dice "MAX" (exit), pero el `tipo` dice "entry". Es una contradicción de metadata que contamina la interpretación.

### Corrección
Revertir `tipo` a `"exit"` en `_registrar` o cambiar `BLANCOS` a `"MIN"` si realmente es entry. La evidencia empírica del Lake continuo post-2011 muestra **edge ≈ 0 en ambas direcciones** — la señal es un diamante §3.3 cuyo edge original era condicionado a régimen ALZA.

---

## 🟡 BUG #6 — BAJO: `e_ret_max`/`e_ret_min` no existen en MarketMETAR

11 archivos `*_metar_service.py` — dataclass `MarketMETAR`. Sin estos campos en el dataclass, el compositor nunca puede leerlos. Bloquea BUG #1.

---

## ⚠️ BUG #7 — INFORMATIVO: Ranking del evaluador no pondera por N

### Ubicación
`evaluador_vela_a_vela.py` — lógica interna de ranking.

### Problema
El ranking elige `max(fav_neto)` sin considerar N. Señales con N=3 (diamante) aparecen como #1 cuando la celda robusta (N=48) tiene edge mucho menor.

### Ejemplo concreto
```
pcr_put_panic:
  zz75|ALZA (N=3💎): +7.67% ← aparece en ranking como "mejor"
  zz75|BAJA (N=48): +0.57% ← la celda real
```

### Corrección
Requerir N≥10 para que una celda sea elegible como "mejor", o mostrar N junto al neto en el ranking.

---

## ⚠️ BUG #8 — INFORMATIVO: Fallback muerto de `zz75_data` para `rr_asymmetry`

### Ubicación
`convergence_compositor.py` L386-390

### Detalle
El código intenta leer `rr_asymmetry_ratio` del nivel superior (funciona), y como fallback `zz75_data.get("rr_asymmetry")` (siempre falla). Eliminar fallback.

---

## ✅ LO QUE ESTÁ CORRECTO

| Componente | Veredicto |
|:-----------|:---------:|
| DXY en router REST + endpoint `/api/metar/dxy` | ✅ Correcto — 11 estaciones, `registered_count: 11` |
| Tests del router (11 tests) | ✅ Correcto |
| NOTAM stale data detection | ✅ Correcto |
| Kinematic en 10 lookups + 10 servicios METAR | ✅ Correcto |
| `n_kinematic_bull/bear_convergent` | ✅ Correcto |
| `n_convex_stations` | ✅ Correcto |
| Timing module `arnes/timing.py` (6 slots) | ✅ Correcto — 3 tests, 100% PASS |
| `evaluador_general.py` filtro post-2011 | ✅ Correcto |
| `v3_fact_table_engine.py` thresholds SKEW post-2011 | ✅ Correcto |
| `fecha_inicio_valida` en señales.py metadata | ✅ Correcto (5 señales) |

---

## PLAN DE CORRECCIÓN

| # | Prioridad | Corrección | Archivos | Esfuerzo |
|:-:|:---------:|:-----------|:---------|:---------|
| 
|**1**| 🔴 P0| Filtar `echa_inicio_valida` en `evaludor_vela_a_vela.py` |`valuador_vla_a_vela.p] | 5 min |
|**2**| 🔴 P0|regar e_rt_mx5d/`e_t_min_d` a dcass`MarerMETR` (1 servicios) | 11 `*tmar_erc.pr` | 20 min |
|**3** |🔴 P0 | Leer `e_ret_max_5d`/`e_ret_min_5d` desde nivel superior en compositor | `convergence_compositor.py` | 5 min |
|**4** |🔴 P0 | Filtrar SKEW pre-2011 en `build_continuous_metar_lake.py` | `build_continuous_metar_lake.py` | 5 min |
|**5** |🟡 P1 | Revisar 40+ scripts research que leen SKEW sin filtrar | `03_estaciones_metar/`, `04_conjuncion_*`, etc. | 30 min |
|**6** |🟡 P1| Coerir `kew_panaia_ext` ipo` enry`o"exit" | `arnes/señales.py` | 2 min|
|**7** |�0 P1| mlemetar MOBlackout en NOTAM | notam_icdent_ere.py +`maco_alndar.py| 15 min |
|**8** |🟡 P1 | Ranking del evaluador: requerir N≥10 para celda "mejor" | `evaluador_vela_a_vela.py` | 5 min |
|**9** |⚪ P2 | Eliminar fallback muerto `zz75_data` para `rr_asymmetry` | `convergence_compositor.py` | 2 min |
|**10**|⚪ P2 | Documentar D3 de SKEW como evento de cola por construcción (no descartar por N bajo) | Documentación §3.3 | 5 min |

---

## NOTA IMPORTANTE — SKEW D3 y sentido común

La D3 de SKEW mide la **expansión de cobertura de cola** (vol of vol de tail hedging). D3=3,4 son eventos unidireccionales raros por construcción:

| D3 | Significado | Frecuencia |
|:-:|:------------|:----------:|
| 0-1 | Normal | 15% |
| 2 | Neutral | **67%** |
| 3 | **Expansión de cobertura de cola** | 15% |
| 4 | **Pánico de cola** | 2% |

D3=4 solo ocurre 31 veces en 1,354 pivotes (2%). **Cada uno de esos eventos debe analizarse individualmente**, no descartarse por "N bajo". Es exactamente el Protocolo §3.3: rareza = riqueza. La rareza NO es un defecto de muestra — es la naturaleza del indicador. No descartar por "datos insuficientes" cuando la baja frecuencia es inherente a la métrica.