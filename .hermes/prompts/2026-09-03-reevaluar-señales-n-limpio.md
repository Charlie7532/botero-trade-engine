# PROMPT: Re-Evaluación Integral de Señales con N Limpio (Política de Inception) — Ranking y Confluencias

**Fecha:** 03-Sep-2026
**Ejecutor:** Gemini
**Contexto:** La política de inception (D0) fue aplicada y `bar_signals.parquet` regenerado (22:37). Muchas señales vieron su N real reducirse dramáticamente al excluir disparos pre-inception (que usaban SKE/ágs sintéticos pre-2011). **El ranking maestro actual fue computado con N CONTAMINADO** y debe re-evaluarse.

## 🔴 Hallazgo verificado (datos en disco, bar_signals 22:37)

| Señal | N fire episodios (regenerado) | Ranking viejo citaba (contaminado) | Diferencia |
|:------|:------------------------------|:-----------------------------------|:-----------|
| `panico_total` | **29** | N=55 (zz75) | **-47%** (mitad era pre-inception) |
| `stealth_tail_hedging` | **276** | N=219 | +26% (¿definición difiere?) |
| `vix_crisis_spike` | 83 | N=83 | igual (inception 1990) |
| `capitulacion` | 98 | N=98 | igual |
| `skew_paranoia_exit` | **114** | (pre-2011 contaminado) | **ahora limpio** |

**Importante:** estos son conteos de FIRE (episodios). El ranking usaba N de episodios por escala (zz25/50/75) tras embargo — debe recomputarse.

---

## TAREA

### 1. Re-evaluar TODAS las señales con la metrología actual (VAV/GENERAL, OHLC, política de inception)
Ejecutar el evaluador (`evaluador_vela_a_vela.py` / `evaluador_general.py`) sobre los parquet regenerados, de modo que:
- Cada señal usa SOLO datos ≥ su `fecha_inicio_valida`
- N honesto (N_indep tras embargo) sobre la muestra limpia
- HR, Lift, EV, Profit Factor, CI95, p-values recomputados

### 2. Regenerar el ranking maestro (`consolidar_ranking.py`)
Con los N/hit rates limpios:
- Re-computar `score_compuesto`, `rol_operacional`, `escala_optima`
- **Re-clasificar diamantes §3.3** (N<21): las señales que antes "parecían" tener N alto por contaminación ahora pueden ser diamantes reales o dejar de serlo
- Verificar las 3 señales retiradas/en disputa (`defensive_rotation_divergence`, `credit_equity_divergence`) con su N limpio

### 3. Re-evaluar confluencias canarias
Las confluencias que usaban `bar_signals` pre-inception cambian su overlap/N. Recalcular pares/tríadas de señales que coinciden, con el N limpio.

### 4. Comparar antes/después (tabla)
Para cada señal, reportar: N viejo (contaminado) → N nuevo (limpio), y si cambió su clasificación (VALIDADA/DEGRADADA/DIAMANTE/CANDIDATA).

### 5. Señal `skew_paranoia_exit`
Asignar `fecha_inicio_valida = 2011-02-01` en `_CERTEZA` (depende de SKEW) — aunque el NaN del lake ya la limpia, hacerlo explícito por robustez (política: fuente única de verdad).

---

## VERIFICACIÓN DE ACEPTACIÓN

```bash
# 1. Ranking regenerado: cada señal con N honesto post-inception
python << 'EOF'
import json
rank = json.load(open('data/research/signals/ranking_maestro.json'))
# panico_total debe reportar N real (~29 o el N_indep post-embargo), ya no 55
EOF

# 2. Ninguna señal valida con disparos pre-inception
python << 'EOF'
import pandas as pd, sys
sys.path.insert(0, 'research/01_señales_entry_exit')
from arnes.registro import _CERTEZA
sig = pd.read_parquet('data/research/bar_signals.parquet')
violaciones = []
for col in sig.columns:
    base = col.replace('_fire','')
    if base in _CERTEZA:
        incept = _CERTEZA[base].get('fecha_inicio_valida')
        if incept:
            trues = sig.index[sig[col].astype(bool)]
            if len(trues) and pd.Timestamp(trues[0]) < pd.Timestamp(incept):
                violaciones.append((col, str(pd.Timestamp(trues[0]).date()), incept))
print(f"Violaciones pre-inception: {len(violaciones)}")
assert not violaciones
EOF

# 3. skew_paranoia_exit tiene fecha_inicio_valida asignada
# 4. Tabla antes/despues documentada
```

---

## ENMIENDA 1 — Derivar `fecha_inicio_valida` para las señales que NO la tienen (BLOQUEANTE) 🔴

**Hallazgo de la auditoría de inception:** hay **12+ señales sin `fecha_inicio_valida`** en `_CERTEZA` que usan estaciones cuya inception es posterior al inicio del lake (1990/1993). Sin la fecha declarada, el filtro en `medicion.py` (`if fecha_inicio:`) NO las protege explícitamente.

### Señales sin inception declarado (derivarlas de las estaciones que usan)

| Señal | Estación usada | Inception a derivar (`max_req`) |
|:------|:---------------|:-------------------------------|
| `vix_crisis_spike`, `vix_crisis_spike_v2`, `vix_instability_warning`, `vix_complacency_exit` | VIX | 1990-01-02 |
| `capitulacion`, `sub_reaccion`, `euforia` | VIX+BSI | 1993-01-29 |
| `euforia_v2`, `bsi_washed_out`, `bsi_recovery`, `bsi_compression_entry`, `breadth_contraction_exit` | BSI | 1993-01-29 |
| `dxy_bearish`, `dxy_spike_exit` | DXY | 1993-01-29 |
| `sv5t_silent_distribution` | SV5 | 1999-01-04 |
| `defensive_rotation_divergence` | ROTATION | 1999-01-04 |

> **Regla de derivación:** `fecha_inicio_valida(señal) = max(inception de las estaciones que usa)` — la señal no puede existir antes de su insumo más reciente. Si usa VIX+BSI, el inception es 1993 (el mayor), no 1990.

### Acción requerida
1. **Asignar `fecha_inicio_valida`** a estas señales en `_CERTEZA` (derivada = max_req de sus estaciones).
2. Cuando usa MÚLTIPLES estaciones, el inception = **máximo** de sus tempos (la más tardía).
3. Re-evaluar estas señales con la política ahora EXPLÍCITA (filtro aplica en medicion.py y construir_bar_snapshot).

### Verificación
```python
# Tras asignar: no debe quedar señal con estaciones sin fecha_inicio_valida
from arnes.registro import _CERTEZA, SEÑALES
faltan = [s for s in SEÑALES
          if _CERTEZA.get(s, {}).get('fecha_inicio_valida') is None
          and _CERTEZA.get(s, {}).get('fuente')]
print(f"Señales aún sin inception: {len(faltan)}")
assert not faltan, f"Faltan: {faltan}"
```

---

## REGLAS
- **Política de inception obligatoria** — N limpio, sin datos pre-inception.
- **Dato mata relato** — el ranking regenerado se apoya en los parquet limpios verificados.
- **Re-clasificar honestamente:** una señal cuyo edge se sostenía en N contaminado puede degradarse o volverse diamante real (N<21). No forzar el resultado.
- **NO revertir** la corrección de overflow ni la política — esto es una re-evaluación consecuente.