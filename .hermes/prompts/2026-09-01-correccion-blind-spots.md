# PROMPT DE CORRECCIÓN — Renombrar e_ret_max_5d + Ranking N+ guard post_2011 + NOTAM FOMC + Migrar joyas legacy

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría de walkthrough de Opus
**Propósito:** 6 correcciones pendientes + 3 blind spots detectados en la ejecución de Opus

---

## 🔴 BLIND SPOT 1 — Ranking N≥10 incompleto (solo se aplicó al ranking principal)

### Problema
Opus aplicó Fix #5 (N≥10) solo al ranking principal (v7). El ranking secundario de reevaluadas/retiradas (L480) quedó con N≥5.

### Ubicación
`evaluador_vela_a_vela.py` L478-480

### Corrección
```python
# Antes (L480):
if p["n"] < 5:
# Después:
if p["n"] < 10:
```

---

## 🔴 BLIND SPOT 2 — `e_ret_max_5d`/`e_ret_min_5d` no fueron renombrados a `e_ret_max_zz75`/`e_ret_min_zz75`

### Problema
Opus agregó los campos con sufijo `_5d` que es **incorrecto**. `guidance.zz75.e_ret_max` es el retorno esperado a la escala zz75 (~30-44 barras, no 5 días). El nombre `_5d` engaña a cualquier consumidor.

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

## 🟡 BLIND SPOT 3 — FOMC Blackout: semana anterior frágil

### Problema
El cálculo de `blackout_start` es frágil (depende de `weekday()`). Funcionalmente correcto pero podría quebrar con días festivos.

### Ubicación
`notam_incident_service.py` L148-150

### Corrección opcional
```python
# Más robusto:
blackout_start = meeting_day1 - timedelta(days=meeting_day1.weekday() + 2)  # sábado anterior siempre
blackout_end = decision_day
```

---

## CORRECCIÓN 4 — Guard `post_2011` redundante en `evaluador_general.py`

### Problema
Para señales con `fecha_inicio_valida='2011-02-01'`, la sub-población `post_2011` produce resultados **100% idénticos** al resultado principal.

### Ubicación
`evaluador_general.py` L386-400 — ✅ **YA CORREGIDO por Opus**. Verificar que funciona.

---

## CORRECCIÓN 5 — NOTAM FOMC Blackout (completar)

### Ubicación
`notam_incident_service.py` L145-165 — ✅ **YA CORREGIDO por Opus**. Incluir blind spot 3 si aplica.

---

## CORRECCIÓN 6 — Migrar Panic/Euphoria Score a `arnes/confluencia.py`

### Origen
`research/_legacy/audit_vector_confluence.py`

### Destino
`research/01_señales_entry_exit/arnes/confluencia.py`

### Funcionalidad a extraer
```python
def calcular_score_confluencia(z_mat, st_cols, panic_stations, euphoria_stations):
    """Calcula Panic Score y Euphoria Score: conteo de estaciones en overflow simultáneo."""
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

---

## CORRECCIÓN 7 — Migrar Contención de Crisis a `arnes/contencion.py`

### Origen
`research/_legacy/detector_regimen_crisis.py`

### Destino
`research/01_señales_entry_exit/arnes/contencion.py`

### Funcionalidad a extraer
```python
def clasificar_contencion(estacion_overflow, dim_overflow, señal):
    """Clasifica si la confluencia de overflows es reforzante o canceladora."""

def analizar_contencion(ev, df, activas, c_dias=5):
    """Analiza ventana de 5 días post-crisis."""

def regimen_crisis(ev, fechas, ventana=None):
    """Detecta régimen de crisis con fecha de inicio/fin."""
```

---

## ORDEN DE EJECUCIÓN

| # | Prioridad | Corrección | Archivos | Esfuerzo |
|:-:|:---------:|:-----------|:---------|:---------|
| **1** | 🔴 P0 | Renombrar `e_ret_max_5d` → `e_ret_max_zz75` | 11 services + 1 compositor | 10 min |
| **2** | 🔴 P0 | Ranking N≥10 en tabla reevaluadas (L480) | `evaluador_vela_a_vela.py` | 1 min |
| **3** | 🟡 P1 | FOMC blackout_start robusto (opcional) | `notam_incident_service.py` | 2 min |
| **4** | 🟡 P1 | Migrar Panic/Euphoria Score | `arnes/confluencia.py` (nuevo) | 15 min |
| **5** | 🟡 P1 | Migrar Contención de Crisis | `arnes/contencion.py` (nuevo) | 15 min |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. No mas e_ret_max_5d
grep -rn "e_ret_max_5d\|e_ret_min_5d" backend/ --include="*.py"

# 2. Tests pasan
cd /root/botero-trade && python3 -m pytest tests/ backend/modules/entry_decision/tests/ -v

# 3. Nuevos módulos arnes/ importan
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit python3 -c "
from arnes.confluencia import calcular_score_confluencia
from arnes.contencion import clasificar_contencion
print('✅ arnes/confluencia.py y arnes/contencion.py importan correctamente')
"
```