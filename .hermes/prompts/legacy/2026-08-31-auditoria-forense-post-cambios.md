# AUDITORÍA FORENSE — Cambios Post-Homologación (66 archivos)

**Auditor:** deepseek/deepseek-v4-flash
**Archivos auditados:** 66
**Calificación general:** 8/10 — Aprobado con 5 hallazgos críticos que corregir

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

## 🟡 BUG #2 — MEDIO: NOTAM promete FOMC Blackout pero no lo implementa

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

## 🟡 BUG #3 — MEDIO: `pcr_completo.py` reporte timing siempre 0 (display)

### Ubicación
`pcr_completo.py` L972 y L1043-1045

### Causa
Las claves `anticipada`, `en_pivote`, `retrasada` no existen en el nuevo `F_timing`. Las claves correctas son `n_anticipada`, `n_exacta`, `n_retrasada`, `n_fuera_de_rango`.

### Corrección
✅ **YA CORREGIDA** en mi intervención anterior — parchado L972 y L1043-1045.

---

## 🟡 BUG #4 — BAJO: `e_ret_max`/`e_ret_min` no existen en MarketMETAR

### Ubicación
11 archivos `*_metar_service.py` — dataclass `MarketMETAR`

### Detalle
El dataclass `MarketMETAR` no tiene campos `e_ret_max_5d` ni `e_ret_min_5d`. Solo existen en el lookup `ScaleGuidance` por escala. El prompt de cierre pedía exponerlos, pero no se agregaron al dataclass.

### Dependencia
Bloquea la corrección del BUG #1. Sin estos campos en el dataclass, el compositor nunca puede leerlos.

---

## ⚠️ BUG #5 — INFORMATIVO: `n_convex` funciona pero por la ruta equivocada

### Ubicación
`convergence_compositor.py` L386-390

### Detalle
El código intenta primero leer `rr_asymmetry_ratio` del nivel superior (funciona, porque el dataclass sí tiene ese campo), y como fallback `zz75_data.get("rr_asymmetry")` (siempre falla). El `n_convex` count funciona, pero la lógica de fallback es código muerto.

### Fix
Eliminar el fallback de `zz75_data` — el campo `rr_asymmetry_ratio` ya está en el nivel superior. Simplificar a:
```python
rr_ratio = data.get("rr_asymmetry_ratio")
```

---

## ✅ LO QUE ESTÁ CORRECTO

| Componente | Veredicto |
|:-----------|:---------:|
| DXY en router REST + endpoint `/api/metar/dxy` | ✅ Correcto — 11 estaciones, `registered_count: 11` |
| Tests del router (11 tests) | ✅ Correcto — DXY, skew, credit, yield-curve, rotation |
| NOTAM stale data detection | ✅ Correcto — gap > 24h en día de trading |
| Kinematic en 10 lookups (`zigzag_kinematic` en `to_vector()`) | ✅ Correcto |
| Kinematic en 10 servicios METAR | ✅ Correcto |
| `n_kinematic_bull_convergent` / `n_kinematic_bear_convergent` | ✅ Correcto — lógica en compositor |
| `n_convex_stations` | ✅ Correcto (funciona, aunque con fallback muerto) |
| Timing module `arnes/timing.py` (6 slots) | ✅ Correcto — 3 tests, 100% PASS |
| Evaluador vela-a-vela con timing integrado | ✅ Correcto — `timing_slots` en JSON |
| Señales E7 (`neutral_crush_entry`, `neutral_spike_exit`) | ✅ Correctas — registradas con `@_registrar` |
| `fecha_inicio_valida` en señales Post-2011 | ✅ Correcto — SKEW, FG, panico_total, stealth_tail_hedging |
| Imports migrados a `arnes/timing.py` | ✅ YA CORREGIDO |

---

## PLAN DE CORRECCIÓN

| # | Prioridad | Corrección | Archivos | Esfuerzo |
|:-:|:---------:|:-----------|:---------|:---------|
| **1** | 🔴 P0 | Agregar `e_ret_max_5d`/`e_ret_min_5d` al dataclass MarketMETAR (11 servicios) | 11 `*_metar_service.py` | 20 min |
| **2** | 🔴 P0 | Leer `e_ret_max_5d`/`e_ret_min_5d` desde nivel superior en compositor (no desde `zz75`) | `convergence_compositor.py` | 5 min |
| **3** | 🟡 P1 | Implementar FOMC Blackout en NOTAM | `notam_incident_service.py` + `macro_calendar.py` | 15 min |
| **4** | ⚪ P2 | Eliminar fallback muerto de `zz75_data` para `rr_asymmetry` | `convergence_compositor.py` | 2 min |