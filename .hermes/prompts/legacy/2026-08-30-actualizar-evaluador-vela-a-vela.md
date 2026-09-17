# PROMPT DE ACTUALIZACIÓN — evaluador_vela_a_vela.py (v2 → v3)

**Archivo:** `research/01_señales_entry_exit/evaluador_vela_a_vela.py`
**Versión actual:** v2 (23-Ago-2026, 443 líneas)
**Propósito:** Calificador forense de señales — first-passage × 3 escalas + forensia F3/INDEP + perfil 3D-régimen
**Relación con medir_senal:** Son complementarios. `medir_senal` da la foto estadística, `evaluador` da la película frame por frame. Uno no reemplaza al otro.

---

## DIAGNÓSTICO — Estado actual

### ✅ Lo que funciona bien
- First-passage por 3 escalas (zz25/zz50/zz75)
- Forensia F3 (independencia informacional vs señales hermanas)
- Baseline que excluye los propios disparos de la señal
- Perfil 3D-régimen (segregado por ALZA/BAJA)
- Confidence tiers §3.3 (ANECDOTAL → ROBUST)
- Ranking por mejor celda con p-value binomial

### ❌ Lo que falta para ejecutar sobre la tabla actual

| # | Problema | Líneas | Fix |
|:-:|:---------|:-------|:----|
| **1** | Faltan blancos para 6 señales activas | 69-89 | Agregar `BLANCOS` para V2 + FG + sv5t |
| **2** | Importa de `medir_senal` (fachada) en vez de `arnes/` directamente | 29 | Cambiar import a `arnes.señales`, `arnes.datos`, `arnes.registro` |
| **3** | Output a `evaluacion_vela_a_vela_v6_final.json` — nombre legacy | 405 | Cambiar a `evaluacion_vela_a_vela_v7_final.json` |
| **4** | `RESCATADAS` hardcodeado solo con `skew_paranoia_exit` | 348 | Verificar si hay más señales rescatables |
| **5** | No hay flag --dry-run para verificar sin ejecutar | Falta | Agregar |

---

## CAMBIOS REQUERIDOS

### Cambio 1 — Agregar blancos faltantes (líneas 69-89)

Agregar al diccionario `BLANCOS`:

```python
# Señales V2 (vectoriales D1+D2) — mismas reglas que sus V1 base
"capitulacion_v2": "MIN",       # ENTRY: igual que capitulacion V1
"euforia_v2": "MAX",            # EXIT: igual que euforia V1
"vix_crisis_spike_v2": "MIN",   # ENTRY: igual que vix_crisis_spike V1 (minoria MIN)

# Señales de estaciones individuales
"fg_extreme_fear": "MIN",       # ENTRY: miedo extremo = contrarian compra (FG es contrarian)
"fg_extreme_greed": "MAX",      # EXIT: codicia extrema = techo contrarian

# Turbulencia silenciosa
"sv5t_silent_distribution": "MAX",  # EXIT: turbulencia callada en techos (solo MIN segun el clasificador original, verificar)
```

**Criterio de asignación de blanco:**
- Si la señal captura más disparos en MIN → ENTRY = `"MIN"` (favorable = subida)
- Si captura más en MAX → EXIT = `"MAX"` (favorable = caída)
- Si `pivot_type="BOTH"` y distribución equitativa, usar semántica de la señal

### Cambio 2 — Actualizar import (línea 29)

```python
# Actual:
from medir_senal import SEÑALES, _CERTEZA, cargar_datos

# Nuevo:
from arnes.registro import SEÑALES, _CERTEZA
from arnes.datos import cargar_datos
```

**Verificar:** El path `sys.path.insert(0, ...)` en línea 28 ya agrega `research/01_señales_entry_exit/` al path, por lo que `from arnes.registro import ...` funciona directamente.

### Cambio 3 — Actualizar output path (línea 405)

```python
# Actual:
out = ROOT / "data/research/signals/evaluacion_vela_a_vela_v6_final.json"

# Nuevo:
out = ROOT / "data/research/signals/evaluacion_vela_a_vela_v7_final.json"
```

### Cambio 4 — Agregar soporte --dry-run (después de línea 342)

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluador vela-a-vela v3")
    parser.add_argument("--dry-run", action="store_true", help="Verificar sin ejecutar")
    parser.add_argument("--senal", type=str, default=None, help="Evaluar solo una señal")
    args = parser.parse_args()
    
    if args.dry_run:
        print("✅ Dry-run: configuración correcta")
        print(f"  Señales registradas: {len(SEÑALES)}")
        print(f"  Blancos definidos: {len(BLANCOS)}")
        print(f"  Señales sin blanco: {[s for s in SEÑALES if s not in BLANCOS]}")
        sys.exit(0)
    
    TODAS = [args.senal] if args.senal else sorted(SEÑALES.keys())
```

---

## VERIFICACIÓN POST-ACTUALIZACIÓN

```bash
cd /root/botero-trade

# 1. Dry-run (verifica imports sin ejecutar)
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
  research/01_señales_entry_exit/evaluador_vela_a_vela.py --dry-run
# → Debe mostrar: 31 señales, todos los blancos

# 2. Ejecutar sobre la tabla actual (aprox 5-10 min)
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
  research/01_señales_entry_exit/evaluador_vela_a_vela.py

# 3. Verificar el JSON generado
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import json
ev = json.load(open('data/research/signals/evaluacion_vela_a_vela_v7_final.json'))
ok = sum(1 for v in ev.values() if isinstance(v, dict) and v.get('status') == 'OK')
pend = sum(1 for v in ev.values() if isinstance(v, dict) and v.get('status') == 'PENDIENTE')
print(f'OK: {ok}, PENDIENTE: {pend}')
"
# → OK debe cubrir todas las señales con blanco asignado
```

---

## RIESGOS

1. **Cache global:** `_CACHE` persiste en memoria. Si se ejecuta `--senal` después de una ejecución completa en el mismo proceso, no recarga datos. El `--dry-run` propuesto sale antes de cargar datos, así que no hay conflicto.
2. **BLANCOS heredados:** Las señales DEGRADADAS y RETIRADAS siguen teniendo blanco en `BLANCOS` — el evaluador las excluye por validación antes de usar el blanco, así que no hay riesgo.
3. **Señales V2 sin OOS:** Se evaluarán igual que las activas, pero sus métricas no tienen sello OOS. Esto es esperado — el evaluador mide el perfil de la señal, no su validación OOS.