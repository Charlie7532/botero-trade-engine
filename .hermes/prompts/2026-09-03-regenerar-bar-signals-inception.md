# PROMPT: Regenerar bar_augment y bar_signals con Política de Inception + Verificar Contaminación

**Fecha:** 03-Sep-2026
**Ejecutor:** Gemini
**Contexto:** La política general de inception (D0, ver `inception_policy.md`) quedó implementada en `construir_bar_snapshot.py` (filtro L230-234). El `continuous_metar_lake.parquet` fue regenerado correctamente (22:26, SKEW empieza 2011, DXY 1993). **PERO `bar_augment.parquet` y `bar_signals.parquet` son del 10:06 — ANTERIORES a la política.** Resultado: señales que dependen de SKEW/FG (inception 2011) siguen con disparos pre-2011.

## 🔴 Hallazgo verificado (punto de partida)

| Señal | fecha_inicio_valida | En bar_signals (10:06) | Estado |
|:------|:-------------------|:----------------------|:-------|
| `panico_total` | 2011-02-01 | primer disparo **1994-02-04** | ❌ Contaminada |
| `stealth_tail_hedging` | 2011-02-01 | primer disparo **1994-05-19** | ❌ Contaminada |

**Causa:** `bar_signals.parquet` fue generado ANTES de aplicar la política D0. El filtro en `construir_bar_snapshot.py` L230-234 existe pero el artefacto no se regeneró.

---

## TAREA

### 1. Regenerar bar_augment.parquet y bar_signals.parquet
Ejecutar `construir_bar_snapshot.py` (que ya contiene el filtro de inception) para regenerar ambos artefactos.

### 2. Verificar que la contaminación pre-inception desapareció

```python
import pandas as pd
sig = pd.read_parquet('data/research/bar_signals.parquet')
# Cada señal debe tener SU primer disparo >= su fecha_inicio_valida
# Particularmente:
# - panico_total (2011): primer disparo debe ser >= 2011-02-01
# - stealth_tail_hedging (2011): primer disparo >= 2011-02-01
# - skew_paranoia (2011): primer disparo >= 2011-02-01
# Nombre de señales que dependen de SKEW/FG (inception 2011) NO deben disparar antes.
```

### 3. Verificar cada señal contra su inception
Para TODA señal en `bar_signals`, confirmar que `primer_disparo >= fecha_inicio_valida` de `_CERTEZA[señal]`. Reportar CUALQUIER señal que aún dispare pre-inception (sería un bug del filtro, no solo del artefacto).

### 4. Verificar N honesto
Tras regenerar, recomputar el N de episodios de señales clave (panico_total, stealth, vix_crisis_spike) — con el filtro pre-inception, el N debe bajar (se excluyen disparos inválidos).

### 5. Confirmar consistencia con el lake regenerado
`bar_augment`/`bar_signals` deben tener las mismas fechas/métricas que el `continuous_metar_lake.parquet` nuevo, y ser generados del lake regenerado (22:26), NO del viejo.

---

## VERIFICACIÓN DE ACEPTACIÓN

```bash
# 1. Fechas de modificación: los 3 parquet deben ser POST-política (>= 22:26)
ls -la data/research/*.parquet

# 2. Ninguna señal dispara antes de su inception
python << 'EOF'
import pandas as pd, sys
sys.path.insert(0, 'research/01_señales_entry_exit')
from arnes.registro import _CERTEZA
sig = pd.read_parquet('data/research/bar_signals.parquet')
violaciones = []
for col in sig.columns:
    # extraer nombre de señal (quitar _fire/_entry/_exit)
    base = col.replace('_fire','')
    if base in _CERTEZA:
        incept = _CERTEZA[base].get('fecha_inicio_valida')
        if incept:
            trues = sig.index[sig[col].astype(bool)]
            if len(trues) and pd.Timestamp(trues[0]) < pd.Timestamp(incept):
                violaciones.append((col, str(pd.Timestamp(trues[0]).date()), incept))
print(f"Señales con disparo pre-inception: {len(violaciones)}")
for v in violaciones: print(f"  VIOLACION: {v[0]} primera={v[1]} incept={v[2]}")
assert not violaciones, "Hay señales pre-inception que deben regenerarse"
# 3. panico_total y stealth: primer disparo >= 2011-02-01
EOF
```

## REGLAS
- **La política de inception es obligatoria** (inception_policy.md). Un disparo pre-inception no existe, se excluye.
- **Artefactos desactualizados deben regenerarse** — no hay excusa para parquet viejos con contaminación.
- **Dato mata relato:** verificar en disco que la regeneración funcionó, no asumir.
- **NO tocar** el lake (ya regenerado correcto) ni `sigma_overflow.py` (ya corregido). Solo regenerar bar_augment/bar_signals con la política.