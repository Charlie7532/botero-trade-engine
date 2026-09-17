# PROMPT DE CORRECCIÓN — Gaps detectados en prompt_cierre_opus_v3

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría combinada Gemini + Flash
**Propósito:** Corregir 5 gaps que Gemini no detectó en su ejecución del prompt de cierre.

---

## GAP 1 — Metodología: Reportar TODAS las celdas, no solo la mejor

### El problema

El walkthrough y task.md reportan señales mostrando solo la celda con mejor edge, omitiendo celdas con edge negativo o N mayor. Esto es el mismo sesgo de celda única que ya corregimos en el validador OOS.

**Ejemplo concreto:** `neutral_crush_entry` se reporta como "N=5💎, +4.55%, PF=3.31" cuando la señal tiene N=20 total y 3/6 celdas tienen edge negativo:

| Celda | N | Hit | Neto | PF |
|:------|:-:|:---:|:----:|:--:|
| zz25\|ALZA | 6 | 16.7% | **−3.56%** | 0.12 |
| zz25\|BAJA | 14 | 57.1% | **−1.56%** | 1.14 |
| zz50\|ALZA | 5 | 80.0% | +2.49% | 2.27 |
| zz50\|BAJA | 14 | 50.0% | **−2.90%** | 0.88 |
| **zz75\|ALZA** | **5** | **80.0%** | **+4.55%** | **3.31** |
| zz75\|BAJA | 14 | 78.6% | +1.25% | 3.14 |

**Corrección:** Para cada señal reportada, presentar la tabla completa de 6 celdas (3 escalas × 2 regímenes) con N, hit, neto, PF. La celda ganadora lleva marca (★). No reportar solo el mejor caso.

---

## GAP 2 — Evaluador JSON incompleto (solo 5 señales)

### El problema

`evaluacion_vela_a_vela_v7_final.json` contiene solo 5 señales evaluadas. `neutral_crush_entry` no está en el JSON a pesar de estar registrada en el arnés y tener BLANCO en el evaluador. Señales existentes (`capitulacion_v2`, `euforia_v2`, `sv5t_silent_distribution`, etc.) no están.

### Corrección

Re-ejecutar el evaluador para regenerar el JSON completo:

```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit \
  backend/.venv/bin/python research/01_señales_entry_exit/evaluador_vela_a_vela.py
```

Verificar que el JSON resultante contenga TODAS las señales registradas:

```bash
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit \
  backend/.venv/bin/python -c "
import json, sys
sys.path.insert(0, 'research/01_señales_entry_exit')
from arnes.registro import SEÑALES
ev = json.load(open('data/research/signals/evaluacion_vela_a_vela_v7_final.json'))
ns = set(SEÑALES.keys())
ne = set(ev.keys()) - {'metadata'}
faltan = ns - ne
print(f'Señales en arnés: {len(ns)}, en JSON: {len(ne)}')
if faltan:
    print(f'FALTAN: {sorted(faltan)}')
else:
    print('✅ Completo')
"
```

---

## GAP 3 — Ejercicio E11c (FTT Collapse) no ejecutado

### El problema

E11a (Sign-Consistency) y E11b (EV Gradient) están completos. E11c (FTT Collapse) no se ejecutó. Es parte del mismo ejercicio — Triada ZZ Convergencia/Divergencia.

### Método E11c

```python
ftt25 = state.zigzag_kinematic.zz25.ftt_bull_days
ftt50 = state.zigzag_kinematic.zz50.ftt_bull_days
ftt75 = state.zigzag_kinematic.zz75.ftt_bull_days

ratio = ftt75 / max(ftt25, 1)

if ratio < 3.0:
    ftt_pattern = "COMPRESSED"      # movimiento rápido en todas las escalas
elif ratio > 10.0:
    ftt_pattern = "STRETCHED"       # movimiento lento y gradual
else:
    ftt_pattern = "NORMAL"
```

**Criterio:** ¿Los estados COMPRESSED coinciden con crashes/rallies documentados?

**Output:** Agregar resultados al JSON existente `data/research/metar_triada_convergencia_divergencia.json`

---

## GAP 4 — Ejercicio E10: integración de p_bull cinemático al compositor

### El problema

E10 fue pre-validado y confirmado (Kinematic gana 8/11 estaciones), pero la integración al compositor no se implementó. El prompt de cierre dice "Implementar consumo directo en compositor (no servicio nuevo)".

### Método

1. Identificar qué lookups ya emiten `zigzag_kinematic` (dxy_lookup.py L210 como referencia)
2. Extender los 10 lookups restantes para emitir `zigzag_kinematic` en `to_dict()`
3. En el compositor (`_compose()`), leer `zigzag_kinematic.zz75.p_bull` del estado JSON de cada estación
4. Agregar `kinematic_p_bull` a `station_summaries`
5. Agregar `n_kinematic_bull_convergent` y `n_kinematic_bear_convergent` al `ConvergenceReport`
6. Integrar en la lógica de `unified_guidance`: si cinemático concuerda con estándar, ponderar más

**No crear servicio nuevo.** Es ~30 líneas en el compositor + 1-2 líneas por lookup.

---

## GAP 5 — Tests del compositor (627 líneas, 0 tests)

### El problema

El compositor tiene 627 líneas de lógica de decisión sin un solo test unitario. Esto es anti-patrón #15 del prompt de cierre.

### Método

Crear tests para `d1_directional_vote()`:

```python
# test_compositor.py
def test_d1_directional_vote_vix_high():
    """VIX bin 4 → bearish (-1)"""
    assert d1_directional_vote("4__3__2", "vix") == -1

def test_d1_directional_vote_vix_low():
    """VIX bin 0 → bullish (+1)"""
    assert d1_directional_vote("0__1__2", "vix") == +1

def test_d1_directional_vote_fg_low():
    """F&G bin 0 → bearish (polaridad invertida)"""
    assert d1_directional_vote("0__1__2", "fg") == -1

def test_d1_directional_vote_neutral():
    """VIX bin 2 → neutral (0)"""
    assert d1_directional_vote("2__1__2", "vix") == 0

def test_d1_directional_vote_no_station():
    """Sin station → 0"""
    assert d1_directional_vote("4__3__2", None) == 0
```

Ubicar en `backend/modules/entry_decision/tests/test_compositor.py` y verificar que pasen:

```bash
cd /root/botero-trade && source backend/.venv/bin/activate
python3 -m pytest backend/modules/entry_decision/tests/ -v
```

---

## ORDEN DE EJECUCIÓN

| # | Gap | Prioridad | Esfuerzo |
|:-:|:----|:---------:|:---------|
| **1** | Reportar todas las celdas (task.md + walkthrough) | 🟡 Alta | 5 min |
| **2** | Re-ejecutar evaluador JSON completo | 🔴 P0 | 5 min |
| **3** | E11c FTT Collapse | 🟡 Alta | 15 min |
| **4** | E10 — Integrar p_bull cinemático al compositor | 🟡 Alta | 30 min |
| **5** | Tests para compositor | 🟡 Alta | 20 min |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. JSON completo
PYTHONPATH=research/01_señales_entry_exit backend/.venv/bin/python \
  -c "import json; ev=json.load(open('data/research/signals/evaluacion_vela_a_vela_v7_final.json')); print(f'{len(ev)} senales en JSON')"

# 2. E11c output
ls -la data/research/metar_triada_convergencia_divergencia.json

# 3. Tests pasan
cd /root/botero-trade && python3 -m pytest backend/modules/entry_decision/tests/ -v

# 4. Reporte E7 multi-celda
PYTHONPATH=research/01_señales_entry_exit backend/.venv/bin/python \
  research/01_señales_entry_exit/evaluador_vela_a_vela.py --senal neutral_crush_entry