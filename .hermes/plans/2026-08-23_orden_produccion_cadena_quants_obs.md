# Plan: Orden en Producción — Cadena `quants_obs` (builder, tests, docs)

> **Para Hermes:** usar subagent-driven-development para implementar tarea por tarea.

**Goal:** dejar la cadena de observación canónica (`quants_obs`) debidamente ordenada en producción: builder versionado junto a los generadores de producción, tests de regresión que congelen los invariantes, documentación consolidada, y commits limpios.

**Arquitectura:** el builder v8 (ya auditado 3 veces, determinista, 143 columnas) se muda de `research/10_gate_oos_validation/` a `backend/scripts/generators/` siguiendo el patrón de `generate_cascade_calibration.py`. Un test de regresión congela los invariantes verificados. Los 8 documentos de auditoría se consolidan en `docs/research/10_gate_oos_validation/`.

**Tech Stack:** Python 3.12 (venv backend), pandas, pytest (backend/tests/), git.

**Contexto verificado (no re-auditar):**
- `quants_obs.pkl` oficial ya sustituido (hash 59fe36d0… = tabla nueva), backups: `quants_obs_pre_sustitucion_20260823.pkl` y `.bak`.
- 1,590 pivotes × 143 columnas · 28/28 señales disparan · determinista bit-a-bit.
- 15 fixes acumulados verificados por 3 auditorías externas (Opus ×3).

---

### Task 1: Crear `backend/tests/test_quants_obs_builder.py` (regresión)

**Objetivo:** congelar los invariantes de la cadena para que ningún cambio futuro los rompa en silencio.

**Files:**
- Create: `backend/tests/test_quants_obs_builder.py`

**Step 1: escribir el test**

```python
"""Regresión de la cadena quants_obs (sustituida 23-Ago-2026, auditada ×3)."""
import sys
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

PKL = ROOT / "data/research/pivots/quants_obs.pkl"

@pytest.fixture(scope="module")
def obs():
    return pd.read_pickle(PKL).reset_index(drop=True)

def test_esquema_143_columnas(obs):
    assert obs.shape == (1590, 143)
    for col in ("pivot_date", "pivot_type", "cascade_conviction_50",
                "n_stations_a", "duration_bars", "daily_return_pct"):
        assert col in obs.columns, f"falta columna crítica: {col}"

def test_pivotes_zigzag_oficial(obs):
    from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
    legs = sorted(ZigzagLegRepository().get_confirmed_legs("SPY", "zz25"),
                  key=lambda l: l.start_timestamp)
    assert len(legs) == len(obs)
    fechas_db = [pd.Timestamp(l.start_timestamp).tz_convert("UTC").tz_localize(None).normalize()
                 for l in legs]
    fechas_obs = pd.to_datetime(obs["pivot_date"]).dt.normalize().tolist()
    assert fechas_db == fechas_obs  # columna vertebral exacta

def test_state_keys_sin_huerfanos(obs):
    import json
    rules = ROOT / "backend/modules/entry_decision/domain/rules"
    for st in ["vix","vvix","pcr","fg","sv5_turbulence","skew","credit",
               "yield_curve","rotation","bsi","dxy"]:
        fs = json.loads((rules / f"{st}_fact_store.json").read_text())
        keys = set(fs.get("states", {}).keys())
        sks = set(obs[f"{st}_sk"].dropna().astype(str))
        assert sks <= keys, f"{st}: state_keys huérfanos"

def test_cascade_reversal_no_inerte(obs):
    sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
    from arnes import SEÑALES
    n = int(SEÑALES["cascade_reversal"](obs).sum())
    assert 100 < n < 400, f"cascade_reversal: {n} disparos (esperado ~240)"

def test_z_bear_consistente_con_produccion(obs):
    import json
    cal = json.loads((ROOT / "backend/modules/entry_decision/domain/rules"
                      / "cascade_calibration.json").read_text())
    mu, sg = cal["d1_bear_5"]["mean"], cal["d1_bear_5"]["std"]
    zb = (obs["d1_bear_5"] - mu) / sg
    assert abs(zb.mean() - obs["z_bear"].mean()) < 1e-9

def test_diamantes_no_degradados(obs):
    from arnes import SEÑALES
    for sig in ("panico_total", "skew_paranoia_exit"):
        n = int(SEÑALES[sig](obs).sum())
        assert 5 <= n <= 25, f"{sig}: N={n} fuera de rango diamante"
```

**Step 2: correr el test**
`cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python -m pytest backend/tests/test_quants_obs_builder.py -v`
Expected: 6 passed.

**Step 3: commit**
`git add backend/tests/test_quants_obs_builder.py && git commit -m "test: regresión cadena quants_obs (invariantes auditados ×3)"`

---

### Task 2: Promover el builder a generador de producción

**Objetivo:** el builder vive junto a los demás generadores, con el mismo patrón.

**Files:**
- Copy: `research/10_gate_oos_validation/builder_quants_obs.py` → `backend/scripts/generators/generate_quants_obs.py`
- Keep: original en `research/10_gate_oos_validation/` (referencia histórica con docs de auditoría)

**Step 1:** copiar el archivo y ajustar el header docstring (1 línea: "Generador oficial de la tabla de observación canónica — promovido 23-Ago-2026 tras 3 auditorías externas; reemplaza el one-off del 17-Ago y a `regenerar_quants_obs.py`").

**Step 2:** verificar que corre desde su nueva ubicación:
`PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/generators/generate_quants_obs.py`
Expected: misma salida (101/141, 28/28 señales, 1,590 pivotes) y hash idéntico al pickle oficial actual (determinismo).

**Step 3:** documentar en `research/11_experimental_engines/regenerar_quants_obs.py` (1 línea en docstring): "DEPRECADO 23-Ago-2026 — sustituido por `backend/scripts/generators/generate_quants_obs.py`".

**Step 4: commit**
`git add backend/scripts/generators/generate_quants_obs.py research/11_experimental_engines/regenerar_quants_obs.py && git commit -m "feat: promover builder quants_obs a generador de producción"`

---

### Task 3: Consolidar documentación en `docs/research/10_gate_oos_validation/`

**Objetivo:** los 8 documentos de auditoría/autoauditoría salen de `research/10_gate_oos_validation/` (zona de trabajo) hacia la documentación versionada, dejando solo código en research.

**Files:**
- Create dir: `docs/research/10_gate_oos_validation/`
- Move (8 docs): `AUTOAUDITORIA_GENERADOR_v5_22AGO.md`, `AUTOAUDITORIA_OOS_22AGO.md`, `AUTOAUDITORIA_PROPOSITO_QUANTS_OBS.md`, `COMPUERTA_FIDELIDAD_BUILDER_v2_22AGO.md`, `INFORME_AUDITORIA_PROFUNDA_CALIBRACION_23AGO.md`, `RESPUESTA_AUDITORIA_DOBLE_22AGO.md`, `RESPUESTA_AUDITORIA_OPUS_GENERADOR_23AGO.md`, `RESPUESTA_AUDITORIA_PROFUNDA_OPUS_23AGO.md`

**Step 1:** `mkdir -p docs/research/10_gate_oos_validation && git mv research/10_gate_oos_validation/*.md docs/research/10_gate_oos_validation/`

**Step 2:** crear `docs/research/10_gate_oos_validation/README.md` — índice de la cadena: propósito, los 15 fixes, manifiesto CAT-A/B/C, ubicación del builder/test/JSONs, protocolo diamante aplicado, y los 3 JSONs de evidencia en `data/research/signals/` (manifiesto_divergencias, calibracion_cascade_reversal, walkforward_cascade_reversal, diamantes_analisis_individual).

**Step 3: commit**
`git add docs/research/10_gate_oos_validation/ && git commit -m "docs: consolidar auditoría cadena quants_obs"`

---

### Task 4: Actualizar `GUIA_EMPLEO.md` del arnés

**Objetivo:** la guía de empleo del sistema de señales refleja la tabla nueva (143 columnas, `cascade_conviction_50`, `n_stations_a`, umbral calibrado de cascade_reversal, tratamiento diamante).

**Files:**
- Modify: `research/01_señales_entry_exit/GUIA_EMPLEO.md`

**Step 1:** añadir sección "Tabla de observación (23-Ago-2026)": esquema 143 columnas, builder oficial, nuevas columnas, umbral −0.957 de cascade_reversal (PROPOSED), diamantes panico_total/skew_paranoia_exit con CI95 CP, limitación conocida de 236 fechas duplicadas y n_stations_a (64% de pivotes con <5 estaciones).

**Step 2: commit**
`git add research/01_señales_entry_exit/GUIA_EMPLEO.md && git commit -m "docs: guía de empleo actualizada a tabla 143 columnas"`

---

### Task 5: Commit del data-artifact y limpieza final

**Objetivo:** el pickle oficial sustituido queda versionado con trazabilidad; scratch queda limpio de scripts ya promovidos.

**Files:**
- Add: `data/research/pivots/quants_obs.pkl` (nuevo), `quants_obs_pre_sustitucion_20260823.pkl` (backup)
- Check: `.gitignore` para `quants_obs_new.pkl` (artefacto intermedio) o eliminarlo si ya no se usa

**Step 1:** decidir si `quants_obs_new.pkl` se elimina (ya es idéntico al oficial) — verificar hash antes:
`md5sum data/research/pivots/quants_obs.pkl data/research/pivots/quants_obs_new.pkl` → si iguales, eliminar el `_new`.

**Step 2: commit**
`git add data/research/pivots/ && git commit -m "data: quants_obs oficial sustituido por tabla auditada (backup 20260823)"`

**Step 3:** mover scripts de forensia de `scratch/` que tengan valor permanente a `research/10_gate_oos_validation/forensia/` (calibrar_cascade_reversal.py, walkforward_cascade_reversal.py, diamantes_analisis_individual.py, comparar_evaluador_tablas.py) + commit.

---

## Validación final del plan

Al terminar las 5 tareas, correr la suite completa:
1. `pytest backend/tests/test_quants_obs_builder.py -v` → 6 passed
2. `PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/generators/generate_quants_obs.py` → salida esperada + hash determinista
3. `git log --oneline -5` → 5 commits limpios y atómicos
4. `git status` → sin archivos huérfanos de la cadena

## Riesgos y trade-offs

- **Tests lentos:** el test de pivotes consulta Timescale (~5s). Aceptable para regresión de cadena crítica.
- **El repo tiene muchos otros cambios pendientes** (AGENTS.md, routers, etc.): los commits de este plan aíslan solo los archivos de la cadena quants_obs para no mezclar scopes.
- **`quants_obs_new.pkl` duplicado:** eliminar solo tras verificar hash idéntico al oficial (paso 5.1).
- **Trade-off documentado:** z_bear/cascade no replican el one-off original (consistencia con producción > fidelidad al artefacto) — queda en el README como decisión de arquitectura.

## Preguntas abiertas

1. ¿Los 5 commits van a `main` directamente o vía branch + PR? (el repo trabaja directo en main según historial — propongo directo, son cambios ya auditados ×3).
2. ¿El backup `quants_obs_pre_sustitucion_20260823.pkl` se versiona en git (2.5 MB) o se guarda fuera del repo? Propongo versionarlo una vez: es el único ejemplar del artefacto original del 17-Ago.
