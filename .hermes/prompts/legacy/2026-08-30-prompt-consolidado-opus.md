# PROMPT CONSOLIDADO — Correcciones Post-Homologación + Limpieza + Políticas

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría completa del hilo
**Propósito:** Que Opus audite y ejecute las correcciones finales post-homologación canónica
**Metodología:** Clean Architecture — dominio puro desacoplado de infraestructura
**Taxonomía:** Bins numéricos canónicos para cómputo, labels para presentación humana
**Documentos relacionados:**
- `2026-08-30-complemento-walkthrough-completo.md` (11 secciones)
- `2026-08-30-correccion-rule-s7-gaussian-scale.md`
- `2026-08-30-correccion-tabla-d1-agente.md`

---

## 🚨 PRIORIDAD 1 — Corregir `gaussian_scale_policy.md` (3 cambios atómicos)

### 1.1 Rule S7 — D2/D3 extremos con bins numéricos (no labels)

**Archivo:** `.agents/references/metar/gaussian_scale_policy.md`
**Líneas:** 171-178
**Problema:** La Rule S7 usaba labels textuales para D2/D3 en vez de bins numéricos. Tras la homologación canónica, toda comparación debe usar bins. Los labels son exclusivamente para presentación humana.

**Reemplazar las líneas 171-178 por:**

```
### Rule S7: "Extreme" Means ±2σ (P2.28 / P97.72) — No Exceptions

When any code, documentation, or signal refers to a dimensional state as "extreme", it MUST correspond to the ±2σ bins:
- **D1 extremes (6 bins):** Bin 0 (< −2σ) or Bin 5 (≥ +2σ) → **2.28% of population each**
- **D2 extremes (5 bins):** Bin 0 (`FAST_CRUSH_3D`) or Bin 4 (`FAST_SPIKE_3D`) → **2.28% each**
- **D3 extremes (5 bins):** Bin 0 (`VOL_EXTREME_SQUEEZE`) or Bin 4 (`VOL_PEAK_DECELERATION`) → **2.28% each**

> **Regla:** Siempre comparar contra el bin numérico. El label taxonómico entre paréntesis es solo para referencia humana.

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

### 1.2 Tabla D1 — Eliminar columna "Ejemplos Canónicos" (incompleta e irrelevante para el agente)

**Líneas:** 41-48
**Problema:** La tabla tenía una columna "Ejemplos Canónicos" que solo mostraba 3 estaciones (VIX, FG, Credit) como referencia taxonómica. El agente no necesita los labels en esta tabla — necesita la escala numérica. Los labels se resuelven vía `resolve_label()` desde `d1_labels_canonical.md`.

**Reemplazar las líneas 41-48 por una tabla de 5 columnas + nota al pie:**

```
| Bin Index | Range | Percentile Band | Population % | Clasificación Taxónomica |
|:---:|---|:---:|:---:|---|
| 0 | val < −2σ | P0 → P2.28 | **2.28%** | Extremo inferior |
| 1 | −2σ ≤ val < −1σ | P2.28 → P15.87 | **13.59%** | Bajo |
| 2 | −1σ ≤ val < μ | P15.87 → P50 | **34.13%** | Neutro (sesgo bajo) |
| 3 | μ ≤ val < +1σ | P50 → P84.13 | **34.13%** | Neutro (sesgo alto) |
| 4 | +1σ ≤ val < +2σ | P84.13 → P97.72 | **13.59%** | Elevado |
| 5 | val ≥ +2σ | P97.72 → P100 | **2.28%** | Extremo superior |
```

### 1.3 Nota al pie — Resolución de labels + Overflow en capa paralela

**Agregar INMEDIATAMENTE DESPUÉS de la tabla D1:**

```
Los labels taxonómicos específicos de cada estación están en [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md). Para resolver un label dado un bin:

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

## 🟡 PRIORIDAD 2 — Migrar `build_continuous_metar_lake.py` a producción (Clean Architecture)

### 2.1 Acción

El lake continuo es un artefacto de infraestructura consumido por evaluadores y señales. Según Clean Architecture, debe residir en `backend/scripts/generators/`, no en `research/`.

```bash
# Copiar de research a producción
cd /root/botero-trade
cp research/01_señales_entry_exit/build_continuous_metar_lake.py \
   backend/scripts/generators/build_continuous_metar_lake.py

# Verificar que regenera correctamente desde producción
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py
```

### 2.2 Verificar que no haya imports rotos

El archivo original importa `arnes.datos` y módulos de `backend/`. Verificar que después de la migración los paths relativos sigan funcionando.

---

## 🟡 PRIORIDAD 3 — Agregar políticas de cadencia (Rule S8 + S9)

**Archivo:** `.agents/references/metar/gaussian_scale_policy.md`
**Insertar DESPUÉS de Rule S7 (línea ~178) y ANTES de Rule S6 (que debería renombrarse a Rule S10)**

### Rule S8: Update Cadence — Full Pipeline Regeneration

| Cadencia | Acción | Comando | Tiempo | Responsable |
|:---------|:-------|:--------|:------:|:-----------:|
| **Diaria** | Ingesta al Vault (TimescaleDB) | EOD batch externo | — | Datos externos |
| **Semanal** | Verificar drift taxonómico | `pytest tests/test_taxonomy_integrity.py -q` | ~5s | Automático (CI) |
| **Mensual** | Regeneración completa de artefactos | Ver Rule S9 | ~15 min | Humano o cron |
| **Por evento** | Bug / nueva señal / cambio taxonómico | Variable según evento | 5-60 min | Humano |

### Rule S9: Monthly Regeneration Procedure

Ejecutar en orden estricto — cada paso depende del anterior:

```bash
# 1. Fact stores (desde Vault) — regenera 11 JSON
cd /root/botero-trade
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_all_150_state_fact_stores.py

# 2. Lake continuo — regenera continuous_metar_lake.parquet
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py

# 3. Tabla pivotal — regenera quants_obs.pkl
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_quants_obs.py

# 4. Tests de regresión — verifica integridad
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/ -q
```

**Artefactos generados:**
- `backend/modules/entry_decision/domain/rules/*_fact_store.json` (11 archivos)
- `data/research/continuous_metar_lake.parquet` (8,453×257)
- `data/research/pivots/quants_obs.pkl` (1,590×165)

**NOTA:** Los scripts de investigación (evaluador, tríada, anatomía) se ejecutan a pedido. No forman parte de la regeneración mensual.

---

## 🟢 PRIORIDAD 4 — Verificar limpieza de legacy (ya ejecutada, confirmar)

### 4.1 Confirmar que `research/_legacy/` contiene los 14 scripts

```bash
cd /root/botero-trade
ls research/_legacy/*.py | wc -l
# Debe devolver 14
```

### 4.2 Verificar que ningún script activo importa legacy

```bash
for f in research/_legacy/*.py; do
  name=$(basename $f .py)
  refs=$(grep -rn "$name" research/ --include="*.py" | grep -v "_legacy" | grep -v "__pycache__" | wc -l)
  if [ $refs -gt 0 ]; then echo "⚠️ $name tiene $refs referencias activas"; fi
done
# Debe devolver 0 advertencias
```

### 4.3 README_LEGACY.md

Ya existe en `research/_legacy/README_LEGACY.md` con la nota de trazabilidad. Verificar que mencione explícitamente los 14 scripts.

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

# 5.3 gaussian_scale_policy.md verificado sin labels en Rule S7
grep -n "D2 extremes.*\`[A-Z]" .agents/references/metar/gaussian_scale_policy.md
# Debe mostrar: Bin 0 (FAST_CRUSH_3D) — NO solo FAST_CRUSH_3D

# 5.4 Tabla D1 sin ejemplos de labels
sed -n '41,48p' .agents/references/metar/gaussian_scale_policy.md
# Debe mostrar 5 columnas, sin columna "Ejemplos Canónicos"

# 5.5 Lake regenerable desde producción
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py --dry-run
# → Sin errores
```

---

## 📋 FORMATO DE ENTREGA ESPERADO

1. **Archivos corregidos:**
   - `.agents/references/metar/gaussian_scale_policy.md` — 3 cambios (Rule S7 con bins, tabla D1 sin labels, nota al pie con resolve_label + overflow)
   - `backend/scripts/generators/build_continuous_metar_lake.py` — migrado de research a producción

2. **Archivos verificados (no modificados):**
   - `research/_legacy/` — 14 scripts + README_LEGACY.md
   - `research/01_señales_entry_exit/` — 5 scripts activos confirmados
   - `backend/scripts/generators/` — generadores existentes intactos

3. **Políticas agregadas:**
   - Rule S8 (cadencia de actualización: diaria/semanal/mensual/evento)
   - Rule S9 (procedimiento mensual de regeneración en 4 pasos)

4. **Verificación ejecutada:**
   - Tests (303 passed)
   - Compuerta 31/31 señales activas
   - Sin referencias activas a legacy
   - Lake regenerable desde producción
   - Rule S7 verificada sin labels

5. **Firma del modelo auditor** y fecha

---

## ⚠️ PROBLEMA CONOCIDO (corregido en walkthrough §12, pendiente en archivo)

El `agent_quick_reference.md` creado por Gemini tenía edges fabricados (4 de 5 no coincidían con la evaluación) y referenciaba un archivo `catalogo_31_senales_medidas.json` que yo erróneamente afirmé que no existía (está en `data/research/` no en `data/research/signals/`).

**El walkthrough §12 corrige esto satisfactoriamente:**
- Tabla reemplazada por valores de `validacion_oos_catalogo_v7.json`
- N sobre población deduplicada (1,354 pivotes)
- Fuente documentada explícitamente

**Pendiente:** Verificar que los cambios del walkthrough §12 se reflejen realmente en el archivo `.agents/references/metar/agent_quick_reference.md`.