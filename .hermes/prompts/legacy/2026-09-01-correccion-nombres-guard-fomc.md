# PROMPT DE CORRECCIÓN — Renombrar e_ret_max_5d/e_ret_min_5d + guard post_2011 + NOTAM FOMC

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría de cambios de Opus
**Propósito:** Corregir 3 issues pendientes de la auditoría forense consolidada

---

## CORRECCIÓN 1 — Renombrar `e_ret_max_5d`/`e_ret_min_5d` → `e_ret_max_zz75`/`e_ret_min_zz75`

### Problema
Opus agregó los campos con sufijo `_5d` que es **incorrecto**. `guidance.zz75.e_ret_max` es el retorno esperado a la escala zz75 (~30-44 barras, no 5 días). El nombre `_5d` es engañoso: sugiere un horizonte de 5 días que no corresponde.

### Archivos afectados (12)

**11 servicios `*_metar_service.py`:**
```python
# Cambiar en el dataclass MarketMETAR:
- e_ret_max_5d: Optional[float] = None
- e_ret_min_5d: Optional[float] = None
+ e_ret_max_zz75: Optional[float] = None
+ e_ret_min_zz75: Optional[float] = None

# Cambiar en la construcción del dataclass:
- e_ret_max_5d=guidance.zz75.e_ret_max,
- e_ret_min_5d=guidance.zz75.e_ret_min,
+ e_ret_max_zz75=guidance.zz75.e_ret_max,
+ e_ret_min_zz75=guidance.zz75.e_ret_min,
```

**1 compositor `convergence_compositor.py`:**
```python
# Cambiar en la lectura:
- e_ret_max_5d = data.get("e_ret_max_5d", None)
- e_ret_min_5d = data.get("e_ret_min_5d", None)
+ e_ret_max_zz75 = data.get("e_ret_max_zz75", None)
+ e_ret_min_zz75 = data.get("e_ret_min_zz75", None)

# Cambiar en station_summaries:
- "e_ret_max_5d": round(e_ret_max_5d, 6) if e_ret_max_5d is not None else None,
- "e_ret_min_5d": round(e_ret_min_5d, 6) if e_ret_min_5d is not None else None,
+ "e_ret_max_zz75": round(e_ret_max_zz75, 6) if e_ret_max_zz75 is not None else None,
+ "e_ret_min_zz75": round(e_ret_min_zz75, 6) if e_ret_min_zz75 is not None else None,
```

### Comando de verificación
```bash
cd /root/botero-trade
grep -rn "e_ret_max_5d\|e_ret_min_5d" backend/ --include="*.py" | grep -v __pycache__
# Debe retornar 0 resultados después de la corrección
```

---

## CORRECCIÓN 2 — Guard `post_2011` redundante en `evaluador_general.py`

### Problema
Para señales con `fecha_inicio_valida='2011-02-01'`, la sub-población `post_2011` produce resultados **100% idénticos** al resultado principal. Es waste computacional (~3s por señal).

### Ubicación
`evaluador_general.py` L386-400

### Corrección
```python
# Antes del bloque que computa post_2011 (aproximadamente L386):
if not (fecha_inicio and pd.Timestamp(fecha_inicio) >= pd.Timestamp("2011-02-01")):
    # Compute post_2011 sub-population...
```

---

## CORRECCIÓN 3 — NOTAM FOMC Blackout

### Problema
El docstring de `notam_incident_service.py` promete 3 checks (L62-65) pero solo implementa 2 (stale data + VIX circuit breaker). El FOMC Blackout no existe.

### Ubicación
`notam_incident_service.py` + `backend/modules/flow_intelligence/domain/rules/macro_calendar.py`

### Corrección
```python
from backend.modules.flow_intelligence.domain.rules.macro_calendar import FOMC_BLACKOUT_WINDOWS

def _check_fomc_blackout(as_of_date: datetime) -> Optional[OperationalNOTAM]:
    """Check if today falls within an FOMC blackout window."""
    for window in FOMC_BLACKOUT_WINDOWS:
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        if start <= as_of_date <= end:
            return OperationalNOTAM(
                notam_id=f"NOTAM-FOMC-{as_of_date.strftime('%Y%m%d')}-001",
                timestamp_utc=as_of_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                incident_type="NOTAM_FOMC_BLACKOUT",
                severity="MODERATE",
                component="FlowIntelligence",
                title=f"FOMC Blackout: {window['label']}",
                description=f"FOMC blackout window active ({start.date()} - {end.date()}). Trading around FOMC decisions restricted.",
                operational_action="MKT_MACRO_CIRCUIT_BREAKER",
                is_active=True,
                details={"window_label": window["label"], "window_start": str(start.date()), "window_end": str(end.date())}
            )
    return None
```

Llamar `_check_fomc_blackout(now_utc)` dentro de `evaluate_operational_notams()` y agregar el resultado a la lista `notams` si no es None.

---

## ORDEN DE EJECUCIÓN

| # | Corrección | Archivos | Esfuerzo |
|:-:|:-----------|:---------|:---------|
| **1** | Renombrar `e_ret_max_5d` → `e_ret_max_zz75` | 11 services + 1 compositor | 10 min |
| **2** | Guard `post_2011` redundante | `evaluador_general.py` | 3 min |
| **3** | NOTAM FOMC Blackout | `notam_incident_service.py` + `macro_calendar.py` | 15 min |

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. No mas e_ret_max_5d
grep -rn "e_ret_max_5d\|e_ret_min_5d" backend/ --include="*.py"

# 2. Tests pasan
cd /root/botero-trade && python3 -m pytest tests/ backend/modules/entry_decision/tests/ -v

# 3. NOTAM incluye FOMC
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from backend.modules.entry_decision.domain.services.notam_incident_service import get_notam_incidents
incidents = get_notam_incidents()
fomc = [i for i in incidents if 'FOMC' in i.incident_id]
print(f'NOTAM FOMC: {len(fomc)} incidentes')
for i in fomc:
    print(f'  {i.title}: {i.description}')
"
```