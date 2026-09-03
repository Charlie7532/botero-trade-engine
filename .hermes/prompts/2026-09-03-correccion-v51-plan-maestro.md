# PROMPT: Corrección v5.1 — Higiene de Señales + Preguntas al Plan Maestro v5.0

**Contexto:** El Plan Maestro v5.0 (03-Sep, "Culminar el Sistema METAR") es sólido pero tiene 3 errores factuales detectados en auditoría y omite 2 etapas que ya fueron contempladas y ejecutadas en iteraciones anteriores. Este prompt: (1) corrige el bug `_entry_entry` con regla general, (2) emite las correcciones factuales, (3) deja las preguntas al plan para que el implementador las responda ANTES de ejecutar.

---

## PARTE 1 — CORRECCIÓN TÉCNICA: Bug `_entry_entry` (A3 del plan)

### Regla general (NO renombrar señales, fixear el generador)

**REGLA:** El sufijo de episodio debe ser `_fire` o computarse en el generador, NUNCA concatenarse ciegamente como `f"{senal}_entry"`.

```python
# ANTES (bug): en construir_bar_snapshot.py
entries[f"{nombre}_entry"] = entry_mask   # vvix_entry → vvix_entry_entry ❌

# DESPUÉS (fix): sufijo fijo de episodio
ENTRY_SUFFIX = "_fire"
entries[f"{nombre}{ENTRY_SUFFIX}"] = entry_mask   # vvix_entry → vvix_entry_fire ✅
```

**Alternativa (si se quiere mantener `_entry` como sufijo):**
```python
# Detectar si el nombre ya termina en _entry y no duplicar
if nombre.endswith("_entry"):
    col_bool = nombre            # vvix_entry (bool activa)
    col_fire = nombre + "_fire"  # vvix_entry_fire (episodio)
else:
    col_bool = nombre
    col_fire = nombre + "_entry"
```

**Acción:** Regenerar `bar_signals.parquet` con sufijo `_fire` (o `entry` sin duplicar). Actualizar `consultar_inteligencia.py` para leer el nuevo sufijo. Los 4 archivos columnas basura desaparecen.

**PROHIBIDO renombrar las señales en `arnes/señales.py`** (corrección RN1 ya aceptada en iteraciones previas — rompe cadena evaluador→JSON→ranking y el directorio tiene ñ).

---

## PARTE 2 — CORRECCIONES FACTUALES AL PLAN MAESTRO v5.0

### 2.1 — Frente A2: NO falta la señal #37. La cuenta "37" era un conteo con duplicados

**El plan dice:** "37 señales planeadas → 36 en registro (1 señal faltante)".

**Dato real (verificado hoy):** El registro tiene **36 señales**. El "37" venía de contar `neutral_crush_entry` y `neutral_spike_exit` como familia + la numeración histórica C1-C20 que no son señales. **No hay señal faltante que rescatar.** El catálogo canónico es 36. Cerrar A2 como "verificado, no hay gap".

### 2.2 — Frente A1: NO son 7 señales RETIRADAS/DEGRADADAS. Son 10

**El plan dice:** "7 señales RETIRADAS/DEGRADADAS siguen activas en bar_signals".

**Dato real (verificado hoy):** Son **10 señales** que siguen disparando en `bar_signals.parquet`:

```
bsi_recovery, credit_stress_exit, dxy_spike_exit, pcr_panic_exit,
vix_complacency_exit, credit_ease_exit, breadth_contraction_exit,
regime_change_exit, credit_equity_divergence, defensive_rotation_divergence
```

**ATENCIÓN con 2 de ellas (posible error del plan):**
- `defensive_rotation_divergence` y `credit_equity_divergence` están marcadas como "DEGRADADA GRADO C" en su docstring **pero el ranking maestro v2.0 las clasifica como TACTICA_RAPIDA con BH significativo**. Si están en el ranking activo, NO deben excluirse de `bar_signals`. Verificar contra `ranking_maestro.json` ANTES de excluir. La fuente de verdad del estado de una señal es el ranking + `_CERTEZA` de `arnes/registro.py`, no el docstring.

### 2.3 — Etapas omitidas del plan (ya contempladas al inicio del proyecto)

El plan v5.0 omite 2 etapas que ya se ejecutaron o acordaron en iteraciones previas:

**OMISIÓN 1 — Filtro `fecha_inicio_valida` (BUG #2 histórico, CONFIRMADO AÚN VIVO):**
El plan no menciona el filtro de inception por señal. **Verificado hoy: `stealth_tail_hedging` dispara 222 veces PRE-2011 con SKEW sintético inválido.** El lake tiene 4,274 barras con `skew_sk` no-nulo antes de 2011-02-01 (CBOE real solo desde 2011).

**Acción que falta en el plan:** El generador `construir_bar_snapshot.py` y el motor `consultar_inteligencia.py` deben aplicar `fecha_inicio_valida` de `_CERTEZA` por señal ANTES de evaluar. Es el mismo BUG #2 que se corrigió en los evaluadores v7 y que el pipeline nuevo reincidió. Añadir como **A4** en Frente A.

**OMISIÓN 2 — Panic/Euphoria Score como módulo `arnes/`:**
El plan C1 propone "confluencia vectorial VIX⊗BSI⊗CREDIT reemplazando la lineal", pero olvida que la confluencia por overflows (Panic/Euphoria Score) vive en `arnes/confluencia.py` y **el E2 P0 del prompt de cierre v3 la tenía como rescate obligatorio desde `_legacy/`**. Ya está rescatada — pero el plan no la conecta: el Convergence Compositor debería consumir `calcular_score_confluencia()` como canal adicional (Channel 4). Añadir como **C1b**.

**OMISIÓN 3 — El problema de promedios entre estaciones con ventanas distintas:**
El plan E1 regenera fact stores "usando los Parquets canónicos actualizados", pero no recuerda que **5 de las 11 estaciones arrancan mucho después** (FG 2011, PCR/Credit/VVIX 2006-07, SV5T 1999). Cualquier agregación cross-estación (como el régimen global o la confluencia) debe usar solo el periodo común o normalizar por estación. Ya fue corrección obligatoria en la auditoría del barrido (2.4). Añadir al criterio de "METAR Culminado".

### 2.4 — Nota sobre C1: la cifra "lift negativo −7.2%"

El plan afirma que la confluencia lineal aditiva actual del Compositor tiene "lift negativo −7.2%" empíricamente refutado. **No aparece evidencia de esa cifra en los artefactos auditados** (no está en walkthrough, ni en ranking, ni en E7). Antes de refactorizar el Compositor con base en ella, ejecutar la Consulta 3 del motor (`confluencia`) sobre los pares que el Compositor combina y reportar el lift combinado real. Si el −7.2% sale de una medición previa, citar el artefacto. Si no, es un número sin fuente (viola Dato Mata Relato).

---

## PARTE 3 — PREGUNTAS AL PLAN (responder antes de ejecutar Frente B y C)

**P1 (Frente B1):** Las 18 configs de E7 tienen N por configuración entre 17 y 77 episodios (ej: `0__3__3` con HR=1.0 en 25 episodios). Al aplicar de-clustering por embargo, ¿cuántas sobreviven con N_indep ≥ 15? La validación B2 debe reportar **N_indep, no N_raw** — si se formalizan con N_raw la gobernanza es mentira.

**P2 (Frente B3):** Si una config pasa Grade A/B, ¿se registra como señal compuesta independiente en `arnes/señales.py` (nuevo registry) o como capa aparte (`arnes/confluencia.py`)? Impacta el de-clustering: señales compuestas del mismo vector comparten barras → auto-correlación entre las nuevas señales. Proponer esquema de purga entre señales compuestas.

**P3 (Frente C1):** ¿El "reemplazo" de la confluencia lineal es aditivo (agregar Channel 4 vectorial y dejar la lineal con peso menor) o sustitutivo (eliminar el voto D1 lineal)? El Compositor tiene 3 canales con pesos calibrados (Grinold-Kahn); eliminar el D1 vote sin medir el impacto en el score compuesto puede degradar señales validadas (sv5t=33.6, defensive_rotation=30.6).

**P4 (Frente C3):** TAF nativo en API: ¿se expone `lift_vs_baseline`/`ci95`/`grade` del Fact Store enriquecido (ya regenerado, Sprint 2) o se recalcula en vivo? Lo correcto es exponer los campos ya persistidos — confirmar que los 11 lookups leerán los nuevos campos sin romper schema (backward compat ya verificado).

**P5 (Frente A1):** Confirmar la fuente de verdad del estado de señal: ¿docstring de `_CERTEZA` o `ranking_maestro.json`? Hoy discrepan para 2 señales (`defensive_rotation_divergence`, `credit_equity_divergence`). El plan debe definir UNA fuente canónica antes de excluir cualquier señal.

**P6 (Gantt):** El plan estima el frente completo en ~12 días con C1 después de E3. Si C1 (confluencia vectorial) es el cambio de mayor impacto, ¿por qué va al final? Proponer: ejecutar B2 (validación de las 18 configs con el motor, es barato) ANTES de A+D, porque su resultado puede cambiar qué señales se archivan/excluyen.

---

## PARTE 4 — Resumen de cambios al plan v5.0

| Item | Plan dice | Corrección |
|:-----|:----------|:-----------|
| A1 | 7 señales retiradas | **10** — y verificar 2 contra ranking antes de excluir |
| A2 | Falta señal #37 | **No falta** — 36 es el catálogo canónico |
| A3 | Renombrar señales | **Prohibido** — fix en generador con sufijo `_fire` |
| A4 (nuevo) | — | Aplicar `fecha_inicio_valida` en generador + motor (BUG #2 reincidió) |
| C1b (nuevo) | — | Conectar Panic/Euphoria Score (`arnes/confluencia.py`) como Channel 4 del Compositor |
| Criterio (nuevo) | — | Agregaciones cross-estación: solo periodo común (inception dates) |
| C1 | lift lineal −7.2% | Sin fuente — medir con Consulta 3 antes de refactorizar |
| B2 | Validar con N | Validar con **N_indep** |
| Gantt | C1 al final | B2 primero (barato, cambia decisiones de A+D) |

**Verificación de aceptación del fix A3:**
```bash
backend/.venv/bin/python -c "
import pandas as pd
sig = pd.read_parquet('data/research/bar_signals.parquet')
bad = [c for c in sig.columns if c.endswith('_entry_entry')]
assert len(bad) == 0, f'Sigue el bug: {bad}'
fire = [c for c in sig.columns if c.endswith('_fire')]
assert len(fire) >= 36, f'Faltan episodios: {len(fire)}'
print('✅ bar_signals limpio:', len(sig.columns), 'columnas')
"
```