# PROMPT DE CORRECCIÓN — Gaps detectados en prompt_cierre_opus_v3 (v2 corregida)

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría combinada de Gemini + Flash
**Versión:** v2 (incorpora las 4 correcciones de Gemini verificadas contra datos reales)
**Propósito:** Corregir 5 gaps + 2 fallas técnicas + 2 puntos ciegos que ni Gemini ni Flash detectaron individualmente.

---

## ⚠️ ACLARACIÓN IMPORTANTE — FTT NO está 100% vacío

Verificación empírica en los 11 fact stores:

| Estación | Estados con FTT real | % |
|:---------|:--------------------:|:-:|
| VIX | 65/113 | 57.5% |
| BSI | 79/112 | 70.5% |
| Credit | 73/104 | 70.2% |
| DXY | 92/128 | 71.9% |
| F&G | 44/82 | 53.7% |
| PCR | 59/95 | 62.1% |
| Rotation | 77/124 | 62.1% |
| SKEW | 91/118 | 77.1% |
| SV5 | 77/110 | 70.0% |
| VVIX | 57/98 | 58.2% |
| Yield Curve | 95/131 | 72.5% |

**El FTT SÍ existe en los fact stores, en `zigzag_kinematic.zz25.ftt_bull_days`.** No está en `kinematic_layer` (esa clave no existe). El fallback 10.0 se usa solo cuando n_pos=0 o n_neg=0 (no hay piernas en esa dirección para ese estado). **E11c es ejecutable contra los fact stores.** El lake continuo NO tiene FTT — no hay atajo.

---

## CORRECCIÓN 1 — E11c: FTT Collapse (versión corregida)

### Fallas técnicas que corrige Gemini

**Falla 1 — TypeError por None:** Cuando n_pos=0, `ftt_bull_days` usa fallback `e_days` (10.0). Pero `n_pos` puede ser 0 y el código debe proteger contra división por cero. Implementar:

```python
ftt25 = state.get("zigzag_kinematic", {}).get("zz25", {}).get("ftt_bull_days")
ftt75 = state.get("zigzag_kinematic", {}).get("zz75", {}).get("ftt_bull_days")

# Protección contra None/0
if not isinstance(ftt25, (int, float)) or not isinstance(ftt75, (int, float)) or ftt25 <= 0:
    ftt_pattern = "NO_DATA"
else:
    ratio = ftt75 / ftt25
    if ratio < 3.0:
        ftt_pattern = "COMPRESSED"
    elif ratio > 10.0:
        ftt_pattern = "STRETCHED"
    else:
        ftt_pattern = "NORMAL"
```

**Falla 2 — Asimetría unidireccional (ignora crashes):** Solo se evaluaba `ftt_bull_days`. Agregar `ftt_bear_days`:

```python
# Dual classification
for direction, field in [("BULL", "ftt_bull_days"), ("BEAR", "ftt_bear_days")]:
    ftt25 = state.get("zigzag_kinematic", {}).get("zz25", {}).get(field)
    ftt75 = state.get("zigzag_kinematic", {}).get("zz75", {}).get(field)
    if isinstance(ftt25, (int, float)) and isinstance(ftt75, (int, float)) and ftt25 > 0:
        ratio = ftt75 / ftt25
        if ratio < 3.0:
            print(f"  COMPRESSED_{direction}: ftt75/ftt25={ratio:.1f}")
        elif ratio > 10.0:
            print(f"  STRETCHED_{direction}: ftt75/ftt25={ratio:.1f}")
```

**Criterio de corte:** ¿Los estados COMPRESSED_BEAR coinciden con crashes documentados (2015, 2018, 2020, COVID)?

**Output:** Agregar al JSON existente: `data/research/metar_triada_convergencia_divergencia.json`

---

## CORRECCIÓN 2 — Gap 1: Reporte multi-celda con nota de pivotes vs continuo

### Problema
El walkthrough y task.md reportan señales mostrando solo la mejor celda, omitiendo celdas con edge negativo.

### Corrección
Para cada señal reportada, presentar la tabla completa de 6 celdas (3 escalas × 2 regímenes). **Agregar nota explícita:**

> *"⚠️ El evaluador vela a vela opera sobre fechas de pivotes de precio (N=20 para esta señal). La señal de Zona Neutral está diseñada para operar en días continuos (N>4,000). El desempeño condicionado a pivote NO representa el desempeño potencial en régimen continuo intra-tramo."*

**Ejemplo concreto para neutral_crush_entry:**

| Celda | N | Hit | Neto | PF | Nota |
|:------|:-:|:---:|:----:|:--:|:-----|
| zz25\|ALZA | 6 | 16.7% | −3.56% | 0.12 | ⚠️ Negativo |
| zz25\|BAJA | 14 | 57.1% | −1.56% | 1.14 | ⚠️ Negativo |
| zz50\|ALZA | 5 | 80.0% | +2.49% | 2.27 | |
| zz50\|BAJA | 14 | 50.0% | −2.90% | 0.88 | ⚠️ Negativo |
| **zz75\|ALZA** | **5** | **80.0%** | **+4.55%** | **3.31** | ★ Mejor |
| zz75\|BAJA | 14 | 78.6% | +1.25% | 3.14 | |

---

## CORRECCIÓN 3 — Gap 2: Re-ejecutar evaluador JSON completo

### Problema
`evaluacion_vela_a_vela_v7_final.json` contiene solo 5 señales. `neutral_crush_entry` no está.

### Corrección
```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit \
  backend/.venv/bin/python research/01_señales_entry_exit/evaluador_vela_a_vela.py
```

Verificar:
```bash
PYTHONPATH=research/01_señales_entry_exit backend/.venv/bin/python -c "
import json, sys; sys.path.insert(0, 'research/01_señales_entry_exit')
from arnes.registro import SEÑALES
ev = json.load(open('data/research/signals/evaluacion_vela_a_vela_v7_final.json'))
ns = set(SEÑALES.keys()); ne = set(ev.keys()) - {'metadata'}
faltan = ns - ne
print(f'Señales en arnés: {len(ns)}, en JSON: {len(ne)}')
if faltan: print(f'FALTAN: {sorted(faltan)}')
else: print('✅ Completo')
"
```

---

## CORRECCIÓN 4 — Gap 4: E10 — Integrar p_bull cinemático al compositor

### Problema
E10 pre-validado (Kinematic gana 8/11), pero no implementado.

### Método
1. El dato ya existe en `zigzag_kinematic.zz75.p_bull` de cada fact store (verificado)
2. En el compositor, leer `p_bull` cinemático del estado JSON de cada estación
3. Agregar `kinematic_p_bull` a `station_summaries`
4. Agregar `n_kinematic_bull_convergent` y `n_kinematic_bear_convergent` al `ConvergenceReport`
5. Integrar en `unified_guidance`: si cinemático concuerda con estándar, ponderar más

**No crear servicio nuevo.** ~30 líneas en compositor.

---

## CORRECCIÓN 5 — Gap 5: Suite de tests integral del compositor

### Problema
Mi propuesta original solo cubría `d1_directional_vote` (5 tests triviales). Gemini exige 4 áreas más.

### Tests requeridos

**1. d1_directional_vote** (5 tests — mantener)
**2. Cálculo ponderado de composite_ev_1d y composite_ev_5d** con `reliability_factor(n)`:
```python
def test_composite_ev_reliability():
    """EV con N alto debe ponderar más que EV con N bajo."""
    ...
```
**3. Detección de rarity_score** con N<10:
```python
def test_rarity_score_extreme():
    """Estación con N<10 debe activar rarity_amplifier."""
    ...
```
**4. Manejo de quórum con blind_stations:**
```python
def test_blind_stations_quorum():
    """Si 5/11 estaciones están ciegas, el quórum debe ajustarse."""
    ...
```
**5. n_convex_stations y consistencia de ConvergenceReport.to_dict():**
```python
def test_n_convex_stations():
    """Si 3 estaciones tienen rr_asymmetry > 1.0, n_convex_stations debe ser 3."""
    ...
```

Ubicar: `backend/modules/entry_decision/tests/test_compositor.py`

---

## ORDEN DE EJECUCIÓN (6 pasos, plan de Gemini)

| # | Corrección | Prioridad | Esfuerzo | Depende de |
|:-:|:-----------|:---------:|:---------|:-----------|
| **1** | Re-ejecutar evaluador JSON completo (Gap 2) | 🔴 P0 | 5 min | — |
| **2** | Homologación capas cinemática (Gap 4.1) | 🟡 Alta | 20 min | — |
| **3** | Consumo cinemático en compositor (Gap 4.2) | 🟡 Alta | 30 min | #2 |
| **4** | E11c FTT Collapse robusto (Corrección 1) | 🟡 Alta | 15 min | — |
| **5** | Tests integrales del compositor (Corrección 5) | 🟡 Alta | 20 min | — |
| **6** | Documentación multi-celda (Corrección 2) | 🟢 Media | 5 min | — |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. JSON completo
PYTHONPATH=research/01_señales_entry_exit backend/.venv/bin/python \
  -c "import json; ev=json.load(open('data/research/signals/evaluacion_vela_a_vela_v7_final.json')); print(f'{len(ev)} señales')"

# 2. Tests pasan
python3 -m pytest backend/modules/entry_decision/tests/ -v -k "compositor"

# 3. E11c output con dual bull/bear
ls -la data/research/metar_triada_convergencia_divergencia.json

# 4. Reporte E7 multi-celda con nota de pivotes vs continuo
PYTHONPATH=research/01_señales_entry_exit backend/.venv/bin/python \
  research/01_señales_entry_exit/evaluador_vela_a_vela.py --senal neutral_crush_entry