# PROMPT DE CORRECCIÓN — Puntos Ciegos de Integración API + NOTAM

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras meta-auditoría `alcance_apis_metar` + verificación de código
**Propósito:** Corregir 4 puntos ciegos de producción que ninguna auditoría de señales/OOS cubrió

---

## IMPORTANCIA

Mientras todo el hilo de los últimos 2 días iteró sobre señales, OOS, evaluador y compositor, **4 bugs de producción quedaron sin corregir**. El router REST y NOTAM no se tocaron desde el 30-Ago.

---

## PC-1 — DXY No Tiene Endpoint REST (🔴 Crítico)

### Diagnóstico

La estación DXY (11ª, más ortogonal del cluster Macro) está operativa en:

| Capa | Estado |
|:-----|:-------|
| `dxy_lookup.py` | ✅ Existente, 30-Ago |
| `dxy_metar_service.py` | ✅ Existente, 18-Ago |
| `convergence_compositor.py` | ✅ Importa, rutea, scale factors, STATIONS_HIGH_BEARISH |
| `test_compositor.py` | ✅ `total_stations == 11` |

**Sin embargo, el router `metar.py` NO la incluye:**

```python
# backend/api/routers/metar.py L203-213 — FALTA DXY
indicators = {
    "vix": ..., "vvix": ..., "pcr": ..., "fg": ..., "sv5_turbulence": ...,
    "skew": ..., "credit": ..., "yield_curve": ..., "rotation": ..., "bsi": ...,
    # ❌ "dxy" NO ESTÁ
}
```

### Corrección

**1. Importar DXY en el router:**
```python
from backend.modules.entry_decision.domain.services.dxy_metar_service import (
    get_dxy_market_metar,
    StrictDataPolicyError as DXYError,
)
```

**2. Agregar al diccionario `indicators`:**
```python
indicators = {
    ...  # los 10 existentes
    "dxy": (get_dxy_market_metar, DXYError),
}
```

**3. Crear endpoint individual `/api/metar/dxy`:**
```python
@router.get("/dxy")
async def get_dxy_metar(as_of_date: Optional[str] = Query(None)):
    return _get_single_metar("dxy", get_dxy_market_metar, DXYError, as_of_date)
```

**4. Verificar:**
```bash
curl http://localhost:8000/api/metar/dxy  # debe devolver METAR, no 404
```

---

## PC-1b — Tests del Router Desactualizados

### Diagnóstico

`test_metar_router.py` aserta `registered_count == 10` — consolidando el bug como "correcto".

### Corrección

**Actualizar test en `tests/test_metar_router.py`:**

```python
# L74: cambiar
assert data["registered_count"] == 10
# a:
assert data["registered_count"] == 11
```

**Agregar tests individuales para estaciones sin cobertura:**
```python
def test_get_dxy_metar(client):
    response = client.get("/api/metar/dxy")
    assert response.status_code in [200, 503]  # 503 si DXY no tiene datos ese día

def test_get_skew_metar(client):
    response = client.get("/api/metar/skew")
    assert response.status_code in [200, 503]

def test_get_credit_metar(client):
    response = client.get("/api/metar/credit")
    assert response.status_code in [200, 503]

def test_get_yield_curve_metar(client):
    response = client.get("/api/metar/yield-curve")
    assert response.status_code in [200, 503]

def test_get_rotation_metar(client):
    response = client.get("/api/metar/rotation")
    assert response.status_code in [200, 503]
```

**Verificar:**
```bash
pytest tests/test_metar_router.py -v | grep "registered_count\|DXY\|skew\|credit\|yield\|rotation"
```

---

## PC-2 — NOTAM Service Incompleto (FOMC + Staleness)

### Diagnóstico

`notam_incident_service.py` implementa solo 2 de 3 checks documentados:

| Check | ¿Implementado? |
|:------|:--------------:|
| 1. Stale Data (pipeline freshness) | ⚠️ Parcial — solo detecta NULL, no datos de hace >24h en día de trading |
| 2. Macro Circuit Breaker (VIX ≥ 40) | ✅ |
| 3. **FOMC Blackout Window** | ❌ **No implementado** — calendario existe en `macro_calendar.py` pero NOTAM no lo consume |
| 4. Broker API connectivity | ❌ No implementado |
| 5. Vault staleness (vacío vs stale) | ❌ No implementado |

### Corrección

**1. FOMC Blackout Window — Conectar NOTAM con `macro_calendar.py`:**

```python
# En notam_incident_service.py, agregar:
from backend.modules.flow_intelligence.domain.rules.macro_calendar import FOMC_BLACKOUT_WINDOWS

def _check_fomc_blackout(as_of_date: datetime) -> Optional[IncidentRecord]:
    """Check if today falls within an FOMC blackout window."""
    for window in FOMC_BLACKOUT_WINDOWS:
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        if start <= as_of_date <= end:
            return IncidentRecord(
                incident_id="NOTAM-FOMC-BLACKOUT",
                severity="MODERATE",
                message=f"FOMC Blackout window: {window['label']} ({start.date()} - {end.date()})",
            )
    return None
```

**2. Stale Data Detection — comparar `MAX(time)` vs fecha actual:**

```python
def _check_stale_data(as_of_date: datetime) -> Optional[IncidentRecord]:
    """Check if SPY data is older than 24h during a trading day."""
    # query vault for MAX(spy.time)
    # if max_time + 24h < now and today is weekday → stale
    max_time = _get_latest_spy_timestamp()
    if max_time is None:
        return IncidentRecord(...)  # NULL case (existing)
    if (as_of_date - max_time).total_seconds() > 86400 and as_of_date.weekday() < 5:
        return IncidentRecord(
            incident_id="NOTAM-STALE-DATA",
            severity="MODERATE",
            message=f"SPY data stale: last bar {max_time.date()}, {int((as_of_date - max_time).total_seconds() / 3600)}h ago",
        )
    return None
```

**3. Verificar:**
```bash
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from backend.modules.entry_decision.domain.services.notam_incident_service import get_notam_incidents
incidents = get_notam_incidents()
for i in incidents:
    print(f'{i.incident_id}: {i.message}')
"
```

---

## PC-3 — Conflicto Arquitectónico Frontend (Vault-First vs FastAPI)

### Diagnóstico

El frontend (`market.ts`) NO llama a FastAPI — lee del Vault directo vía `pg` Pool. Proponer `fetch()` a FastAPI rompe la resiliencia actual.

### Decisión Arquitectónica

**Adoptar Opción C (Híbrida) del meta_audit:**

| Tipo de dato | Fuente | Motivo |
|:-------------|:-------|:-------|
| METAR individual (estaciones) | **Vault-First** (clasificar en TS) | Datos crudos ya están. Clasificación D1/D2/D3 es aritmética pura |
| Convergence / SIGMET / NOTAM | **FastAPI** | Lógica compleja que no vale la pena duplicar en TS |
| Banners de alerta | FastAPI con degradación graceful | Si backend cae, el frontend muestra "sin datos" no se rompe |

**No cambiar nada en el frontend ahora.** Esta corrección es documentación de la decisión — el frontend no requiere cambios inmediatos.

---

## PC-4 — Servicios Referenciados que No Existen (Documentación)

### Diagnóstico

4 servicios que el plan asume existentes son greenfield puro:

| Servicio | Realidad | Acción |
|:---------|:---------|:-------|
| `confluence_service.py` | ❌ No existe | Quitar del plan o crear después de E2 |
| `rarity_service.py` | ❌ Solo `rarity_amplifier()` inline en compositor | Migrar Clopper-Pearson de research a `backend/modules/entry_decision/domain/rules/` |
| `lead_lag_service.py` | ❌ Solo script de benchmark | Quitar del plan — no prioritario |
| `cascade_conviction_service.py` | ⚠️ Integrado en compositor | Documentar que vive dentro de convergence_compositor.py, no como servicio separado |

### Corrección

**Actualizar el plan de APIs para reflejar la realidad.** Marcar estos como greenfield o eliminarlos del roadmap inmediato.

---

## ORDEN DE EJECUCIÓN

| # | Corrección | Prioridad | Esfuerzo | Archivos |
|:-:|:-----------|:---------:|:---------|:---------|
| **1** | DXY en router REST (import + dict + endpoint) | 🔴 P0 | 10 min | `metar.py` |
| **2** | Tests del router (registered_count 10→11 + 5 endpoints) | 🔴 P0 | 15 min | `test_metar_router.py` |
| **3** | FOMC Blackout en NOTAM | 🟡 Alta | 20 min | `notam_incident_service.py` |
| **4** | Stale Data Detection en NOTAM | 🟡 Alta | 15 min | `notam_incident_service.py` |
| **5** | Documentar decisión arquitectónica Frontend (Opción C) | 🟢 Media | 5 min | `docs/` |
| **6** | Actualizar plan de APIs (servicios greenfield) | 🟢 Media | 5 min | Plan de implementación |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. DXY endpoint existe
curl -s http://localhost:8000/api/metar/dxy | python3 -c "import json,sys; d=json.load(sys.stdin); print('DXY METAR:' if 'metar_id' in d else 'FALLA')"

# 2. registered_count == 11
curl -s http://localhost:8000/api/metar/all | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'registradas: {d[\"registered_count\"]}')"

# 3. Tests pasan
pytest tests/test_metar_router.py -v | tail -10

# 4. NOTAM incluye FOMC
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from backend.modules.entry_decision.domain.services.notam_incident_service import get_notam_incidents
incidents = get_notam_incidents()
fomc = [i for i in incidents if 'FOMC' in i.incident_id]
print(f'NOTAM FOMC: {len(fomc)} incidentes (esperado: 1 en periodo blackout, 0 fuera)')
"