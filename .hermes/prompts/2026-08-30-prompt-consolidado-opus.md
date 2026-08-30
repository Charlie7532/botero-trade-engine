# PROMPT CONSOLIDADO — Correcciones Post-Homologación + Limpieza + Políticas

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría completa del hilo
**Propósito:** Que Opus audite y ejecute las correcciones finales post-homologación canónica
**Documentos relacionados:**
- `2026-08-30-complemento-walkthrough-completo.md` (11 secciones)
- `2026-08-30-correccion-rule-s7-gaussian-scale.md`
- `2026-08-30-correccion-tabla-d1-agente.md`

---

## 🚨 PRIORIDAD 1 — Corregir `gaussian_scale_policy.md` (3 cambios atómicos)

### 1.1 Rule S7 — D2/D3 extremos en lugar de labels

**Archivo:** `.agents/references/metar/gaussian_scale_policy.md`
**Líneas:** 171-178
**Problema:** La Rule S7 usa labels textuales para D2/D3 en vez de bins numéricos.

**Reemplazar las líneas 171-178 por:**

```
### Rule S7: "Extreme" Means ±2σ (P2.28 / P97.72) — No Exceptions

When any code, documentation, or signal refers to a dimensional state as "extreme", it MUST correspond to the ±2σ bins:
- **D1 extremes (6 bins):** Bin 0 (< −2σ) or Bin 5 (≥ +2σ) → **2.28% of population each**
- **D2 extremes (5 bins):** Bin 0 (`FAST_CRUSH_3D`) or Bin 4 (`FAST_SPIKE_3D`) → **2.28% each**
- **D3 extremes (5 bins):** Bin 0 (`VOL_EXTREME_SQUEEZE`) or Bin 4 (`VOL_PEAK_DECELERATION`) → **2.28% each**

> **Regla:** Siempre comparar contra el bin numérico. El label semántico entre paréntesis es solo para referencia humana.

An indicator is NOT in an extreme state if it is in Bin 1 or Bin 4 (those are "elevated" = ±1σ to ±2σ).

For a generic function:
```python
def is_extreme(d1_bin: int, d2_bin: int, d3_bin: int) -> bool:
    d1_extreme = d1_bin in {0, 5}        # D1: 6 bins
    d2_extreme = d2_bin in {0, 4}        # D2: 5 bins (same ±2σ percentiles)
    d3_extreme = d3_bin in {0, 4}        # D3: 5 bins (same ±2σ percentiles)
    return d1_extreme or d2_extreme or d3_extreme
```
```

### 1.2 Tabla D1 — Eliminar columna "Ejemplos Canónicos" (3 estaciones incompletas)

**Líneas:** 41-48
**Problema:** La tabla tiene una columna "Ejemplos Canónicos" que solo muestra 3 estaciones (VIX, FG, Credit) — incompleta e irrelevante para el agente.

**Reemplazar las líneas 41-48 por una tabla de 5 columnas + nota al pie:**

```
| Bin Index | Range | Percentile Band | Population % | Semantic Role |
|:---:|---|:---:|:---:|---|
| 0 | val < −2σ | P0 → P2.28 | **2.28%** | Extremo inferior |
| 1 | −2σ ≤ val < −1σ | P2.28 → P15.87 | **13.59%** | Bajo |
| 2 | −1σ ≤ val < μ | P15.87 → P50 | **34.13%** | Neutro (sesgo bajo) |
| 3 | μ ≤ val < +1σ | P50 → P84.13 | **34.13%** | Neutro (sesgo alto) |
| 4 | +1σ ≤ val < +2σ | P84.13 → P97.72 | **13.59%** | Elevado |
| 5 | val ≥ +2σ | P97.72 → P100 | **2.28%** | Extremo superior |
```

### 1.3 Nota al pie — Labels + Overflow

**Agregar INMEDIATAMENTE DESPUÉS de la tabla D1** (reemplazando la línea que decía "Ejemplos Canónicos"):

```
Los labels semánticos específicos de cada estación están en [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md). Para resolver un label dado un bin:

```python
from backend.modules.entry_decision.domain.rules.metar_classifier import resolve_label

# Cargar labels del fact store de la estación
labels = json.load(open("backend/.../vix_fact_store.json"))["_documentation"]["taxonomy"]["d1"]["labels"]
label = resolve_label(4, labels)  # → "PANIC" para VIX, "EASE" para Credit
```

Los overflows (> ±3σ) y blow-offs (> ±5σ) NO modifican el bin (se clipea a [0,5]). Operan en capa paralela sobre el z-score crudo. Ver [overflow_taxonomy.md](file:///root/botero-trade/.agents/references/metar/overflow_taxonomy.md) para la escala T1-T5. En código:

```python
from backend.modules.entry_decision.domain.rules.sigma_overflow import classify_overflow_tier

# z_score crudo del indicador
tier, hazard_name, hazard_type = classify_overflow_tier(z_score=4.2)
# → (2, "OVERFLOW_EXTREMO", "CRITICAL")
```
```

---

## 🟡 PRIORIDAD 2 — Migrar `build_continuous_metar_lake.py` a producción

### 2.1 Acción

Copiar el archivo de `research/01_señales_entry_exit/build_continuous_metar_lake.py` a `backend/scripts/generators/build_continuous_metar_lake.py`. Actualizar imports de rutas relativas si es necesario.

### 2.2 Verificar que el lake se regenera desde producción

```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py
```

---

## 🟡 PRIORIDAD 3 — Actualizar mapa de cadencia en documentación

### 3.1 Agregar sección de periodicidad a `gaussian_scale_policy.md` (o a un nuevo archivo de políticas)

Después de Rule S6 (línea ~160), agregar:

```
### Rule S8: Update Cadence — Full Pipeline Regeneration

| Cadencia | Acción | Comando | Tiempo |
|:---------|:-------|:--------|:------:|
| **Diaria** | Ingesta al Vault (TimescaleDB) | EOD batch externo | — |
| **Semanal** | Verificar drift taxonómico | `pytest tests/test_taxonomy_integrity.py -q` | ~5s |
| **Mensual** | Regeneración completa | Ver Rule S9 | ~15 min |
| **Por evento** | Bug / nueva señal / taxonomía | Variable según evento | 5-60 min |

### Rule S9: Monthly Regeneration Procedure

Ejecutar en orden estricto:

```bash
# 1. Fact stores (desde Vault)
cd /root/botero-trade
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_all_150_state_fact_stores.py

# 2. Lake continuo
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py

# 3. Tabla pivotal
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_quants_obs.py

# 4. Tests de regresión
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/ -q
```

**Artefactos generados:**
- 11 fact stores JSON: `backend/modules/entry_decision/domain/rules/*_fact_store.json`
- Lake continuo: `data/research/continuous_metar_lake.parquet`
- Tabla pivotal: `data/research/pivots/quants_obs.pkl`

**NOTA:** Los archivos de evaluación (evaluador, tríada, anatomía) se ejecutan a pedido de investigación, no forman parte de la regeneración mensual.
```

---

## 🟢 PRIORIDAD 4 — Verificar limpieza de legacy

### 4.1 Confirmar que `research/_legacy/` tiene todos los scripts

```
research/_legacy/ debe contener:
☐ extract_overflows_vela_a_vela.py
☐ audit_overflow_candle_anatomy.py (V1)
☐ detector_regimen_crisis.py
☐ audit_vector_confluence.py
☐ recompute_signals_fact_store_triad.py (V1)
☐ wins_losses_entry47_v2.py
☐ wins_losses_top3.py
☐ wins_losses_top3_v2.py
☐ wins_losses_exit_neutral_v2.py
☐ wins_losses_summary.py
☐ wins_losses_sv5t_vix_bsi_credit.py
☐ wins_losses_yield_rotation.py
☐ audit_entry_exit.py
☐ generate_full_population_census.py
☐ README_LEGACY.md (ya existe)
```

### 4.2 Verificar que ningún script activo importa legacy

```bash
cd /root/botero-trade
for f in research/_legacy/*.py; do
  name=$(basename $f .py)
  refs=$(grep -rn "$name" research/ --include="*.py" | grep -v "_legacy" | grep -v "__pycache__" | wc -l)
  if [ $refs -gt 0 ]; then echo "⚠️ $name tiene $refs referencias activas"; fi
done
# Debe devolver 0 advertencias
```

---

## 🟢 PRIORIDAD 5 — Verificación end-to-end post-correcciones

```bash
# 5.1 Tests
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -m pytest tests/ -q
# → 303 passed

# 5.2 Compuerta de propósito: 31/31 señales activas
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import sys; sys.path.insert(0, 'research/01_señales_entry_exit')
import arnes.datos as dm; df,_ = dm.cargar_datos()
from arnes import SEÑALES
activas = sum(1 for n,f in SEÑALES.items() if f(df).astype(bool).sum() > 0)
assert activas == 31, f'Solo {activas}/31'
print(f'✓ {activas}/31 señales activas')
"

# 5.3 gaussian_scale_policy.md sin labels en Rule S7
grep -n "D2 extremes.*\`[A-Z]" .agents/references/metar/gaussian_scale_policy.md
# Debe mostrar: Bin 0 (FAST_CRUSH_3D) — NO solo FAST_CRUSH_3D
```

---

## 📋 FORMATO DE ENTREGA ESPERADO

1. **Archivos corregidos:**
   - `.agents/references/metar/gaussian_scale_policy.md` — 3 cambios (Rule S7, tabla D1, nota al pie)
   - `backend/scripts/generators/build_continuous_metar_lake.py` — migrado de research

2. **Archivos verificados (no modificados):**
   - `research/_legacy/` — 14 scripts + README
   - `research/01_señales_entry_exit/` — 5 scripts activos confirmados
   - `backend/scripts/generators/` — generadores existentes intactos

3. **Políticas agregadas:**
   - Rule S8 (cadencia de actualización) + Rule S9 (regeneración mensual) en `gaussian_scale_policy.md`

4. **Verificación ejecutada:**
   - Tests (303 passed)
   - Compuerta 31/31 señales
   - Sin referencias activas a legacy
   - Lake regenerable desde producción

5. **Firma del modelo auditor** y fecha

---

## ⚠️ PROBLEMA CONOCIDO (no resuelto en este prompt)

Los edges del `agent_quick_reference.md` creado por Gemini fueron fabricados (4 de 5 no coinciden con el triadic V2, y referencian un archivo `catalogo_31_senales_medidas.json` que no existe). Esto necesita corrección por separado — no se incluye aquí porque requiere reconciliación manual de valores.