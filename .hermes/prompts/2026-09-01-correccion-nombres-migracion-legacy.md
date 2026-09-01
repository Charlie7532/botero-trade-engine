# PROMPT DE CORRECCIÓN — Renombrar e_ret_max_5d + guard post_2011 + NOTAM FOMC + Migrar joyas legacy

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría de cambios de Opus
**Propósito:** 5 correcciones pendientes de la auditoría forense consolidada

---

## CORRECCIÓN 1 — Renombrar `e_ret_max_5d`/`e_ret_min_5d` → `e_ret_max_zz75`/`e_ret_min_zz75`

### Problema
Opus agregó los campos con sufijo `_5d` que es **incorrecto**. `guidance.zz75.e_ret_max` es el retorno esperado a la escala zz75 (~30-44 barras, no 5 días). El nombre `_5d` es engañoso: sugiere un horizonte de 5 días que no corresponde.

**Nota:** No hay otras variables con este problema. `velocity_3d`, `roc_5d`, `composite_ev_5d`, `vol_10d` son correctos porque miden horizontes reales de 3, 5 y 10 días respectivamente.

### Archivos afectados (12)

**11 servicios `*_metar_service.py`** — Cambiar en el dataclass `MarketMETAR`:
```python
# Antes:
- e_ret_max_5d: Optional[float] = None
- e_ret_min_5d: Optional[float] = None
# Después:
+ e_ret_max_zz75: Optional[float] = None
+ e_ret_min_zz75: Optional[float] = None
```

Cambiar en la construcción del dataclass:
```python
# Antes:
- e_ret_max_5d=guidance.zz75.e_ret_max,
- e_ret_min_5d=guidance.zz75.e_ret_min,
# Después:
+ e_ret_max_zz75=guidance.zz75.e_ret_max,
+ e_ret_min_zz75=guidance.zz75.e_ret_min,
```

**Atención: `dxy_metar_service.py`** tiene además `to_dict()` inline que expone estos campos (L92-93). Corregir también:
```python
# Antes:
- "e_ret_max_5d": self.e_ret_max_5d,
- "e_ret_min_5d": self.e_ret_min_5d,
# Después:
+ "e_ret_max_zz75": self.e_ret_max_zz75,
+ "e_ret_min_zz75": self.e_ret_min_zz75,
```

**1 compositor `convergence_compositor.py`:**
```python
# Antes L388-389:
- e_ret_max_5d = data.get("e_ret_max_5d", None)
- e_ret_min_5d = data.get("e_ret_min_5d", None)
# Después:
+ e_ret_max_zz75 = data.get("e_ret_max_zz75", None)
+ e_ret_min_zz75 = data.get("e_ret_min_zz75", None)

# Antes L426-427:
- "e_ret_max_5d": round(e_ret_max_5d, 6) if e_ret_max_5d is not None else None,
- "e_ret_min_5d": round(e_ret_min_5d, 6) if e_ret_min_5d is not None else None,
# Después:
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
El docstring de `notam_incident_service.py` promete 3 checks (L62-65) pero solo implementa 2 (stale data + VIX circuit breaker).

### Corrección
```python
from backend.modules.flow_intelligence.domain.rules.macro_calendar import FOMC_BLACKOUT_WINDOWS

def _check_fomc_blackout(as_of_date: datetime) -> Optional[OperationalNOTAM]:
    for window in FOMC_BLACKOUT_WINDOWS:
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        if start <= as_of_date <= end:
            return OperationalNOTAM(
                notam_id=f"NOTAM-FOMC-{as_of_date.strftime('%Y%m%d')}-001",
                ...)
    return None
```

---

## CORRECCIÓN 4 — Migrar Panic/Euphoria Score a `arnes/confluencia.py`

### Origen
`research/_legacy/audit_vector_confluence.py` — función de conteo multi-estación de overflows simultáneos (±2σ) con forward return condicionado.

### Destino
`research/01_señales_entry_exit/arnes/confluencia.py`

### Funcionalidad a extraer
```python
def calcular_score_confluencia(z_mat, st_cols, panic_stations, euphoria_stations):
    \"\"\"Calcula Panic Score y Euphoria Score: conteo de estaciones en overflow simultáneo.
    
    Args:
        z_mat: DataFrame con columnas {station}.{dim} y valores z-score
        st_cols: lista de columnas z-score
        panic_stations: estaciones donde z≥2 = pánico
        euphoria_stations: estaciones donde z≥2 = euforia
    
    Returns:
        panic_score, euphoria_score arrays
    \"\"\"
    panic_scores = np.zeros(len(z_mat), dtype=int)
    euphoria_scores = np.zeros(len(z_mat), dtype=int)
    for col in st_cols:
        st, dim = col.split('.')
        vals = z_mat[col].values
        pos = (vals >= 2.0)
        neg = (vals <= -2.0)
        if st in panic_stations:
            panic_scores += np.where(pos, 1, 0)
        if st in euphoria_stations:
            euphoria_scores += np.where(pos, 1, 0)
        if st in ['fg', 'bsi', 'credit', 'rotation']:
            panic_scores += np.where(neg, 1, 0)
        elif st in ['vix', 'pcr']:
            euphoria_scores += np.where(neg, 1, 0)
    return panic_scores, euphoria_scores
```

### Esta función alimenta el Ejercicio E2 (Gaussian Confluence Multi-Estación) del prompt de cierre.

---

## CORRECCIÓN 5 — Migrar Contención de Crisis a `arnes/contencion.py`

### Origen
`research/_legacy/detector_regimen_crisis.py` — funciones `_clasificar_contencion()`, `analizar_contencion()`, `regimen_crisis()`.

### Destino
`research/01_señales_entry_exit/arnes/contencion.py`

### Funcionalidad a extraer
```python
def clasificar_contencion(estacion_overflow, dim_overflow, señal):
    \"\"\"Clasifica si la confluencia de overflows es reforzante o canceladora.\"\"\"

def analizar_contencion(ev, df, activas, c_dias=5):
    \"\"\"Analiza ventana de 5 días post-crisis para ver si el mercado se recupera.\"\"\"

def regimen_crisis(ev, fechas, ventana=None):
    \"\"\"Detecta régimen de crisis con fecha de inicio/fin basado en overflows.\"\"\"
```

---

## ORDEN DE EJECUCIÓN

| # | Corrección | Archivos | Esfuerzo |
|:-:|:-----------|:---------|:---------|
| **1** | Renombrar `e_ret_max_5d` → `e_ret_max_zz75` | 11 services + 1 compositor | 10 min |
| **2** | Guard `post_2011` redundante | `evaluador_general.py` | 3 min |
| **3** | NOTAM FOMC Blackout | `notam_incident_service.py` + `macro_calendar.py` | 15 min |
| **4** | Migrar Panic/Euphoria Score | `arnes/confluencia.py` (nuevo) | 15 min |
| **5** | Migrar Contención de Crisis | `arnes/contencion.py` (nuevo) | 15 min |

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
"

# 4. Nuevos módulos arnes/ importan
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit python3 -c "
from arnes.confluencia import calcular_score_confluencia
from arnes.contencion import clasificar_contencion, analizar_contencion, regimen_crisis
print('✅ arnes/confluencia.py y arnes/contencion.py importan correctamente')
"
```