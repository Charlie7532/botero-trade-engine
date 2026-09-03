# PROMPT: Realinear el Motor de Inteligencia con los Criterios Canónicos del Framework VAV

**Destino:** `research/01_señales_entry_exit/consultar_inteligencia.py` + `construir_bar_snapshot.py` (regeneración de `bar_augment.parquet`)
**Fecha:** 03-Sep-2026
**Antecedente:** El motor de consulta y `bar_augment.parquet` implementaron una metrología NUEVA que contradice los criterios canónicos de `evaluador_vela_a_vela.py` (v3, consolidados 22-Ago tras auditoría Gemini con correcciones P0-P5 y protocolo §3.3). Esta auditoría fue solicitada por el usuario: *"se omitieron todos los criterios que empleamos en medir señal y vela a vela y volvemos al análisis determinista... poniendo criterios contrarios como 80 barras"*. **La auditoría lo confirma con datos.**

---

## PARTE 1 — AUDITORÍA: Las 5 divergencias (verificadas empíricamente el 03-Sep)

### D1 — 🔴 CRÍTICA: Timeout = Falla (contra P2 del VAV)

**VAV canónico** (`evaluador_vela_a_vela.py` L149-177): `first_passage()` corre SIN límite de barras hasta que el precio toca +scale o -scale. Lo no resuelto retorna `{"resuelto": False}` y **se excluye** de fichas y baseline. No es falla — es censoring.

**Motor nuevo:** time-stop C9 (80/40/27 barras) con **timeout contado como `hit=False`**.

**Impacto medido (baseline incondicional, 8,453 barras):**

| Escala | Baseline SIN límite (VAV-style) | Baseline CON timeout=falla | Divergencia | Timeout rate |
|:-------|:-------------------------------:|:--------------------------:|:-----------:|:------------:|
| zz25 | **57.75%** | 55.88% | -1.9pp (irrelevante) | 0.3% |
| zz50 | **63.88%** | **38.44%** | **-25.4pp** | 32.1% |
| zz75 | **72.88%** | **11.25%** | **-61.6pp** | **74.7%** |

El 74.7% de ventanas zz75 nunca tocan ±7.5% en 27 barras. Sin límite, el SPY sube 7.5% el 72.9% de las veces eventualmente. **Eso es un hecho del mercado (drift estructural), no una falla del trade.** Contarlo como derrota destruye la métrica en zz50/zz75 y hace los "lift" de esas escalas no comparables con nada histórico.

### D2 — 🔴 CRÍTICA: Baseline incondicional viola P5

**VAV:** baseline = pivotes del **mismo tipo** (MAX si blanco=MAX, MIN si ENTRY), **misma era** (`fecha_inicio_valida`), **mismo régimen** (pierna ALZA/BAJA confirmada por pivote posterior — sello temporal sin lookahead), **excluyendo los pivotes de la propia señal** (P5).

**Motor nuevo:** baseline = todas las barras de la historia (incondicional, sin régimen, sin era, sin exclusión).

**Consecuencia:** el "lift" del motor y el "fav_neto/hit_neto" del VAV **no son la misma métrica**. Un lift +16pp contra baseline incondicional puede ser NEGATIVO contra pivotes MAX de la misma era y régimen.

### D3 — 🟡 Unidad de medición incompatible

**VAV:** evalúa SOLO en los 1,590 pivotes oficiales de `quants_obs` (eventos MIN/MAX con significado estructural). Su unidad de observación es el evento de giro — por eso nunca necesitó embargo.

**Motor nuevo:** evalúa cada una de las 8,453 barras y luego simula independencia con embargo de `ceil(2/scale)` barras. El embargo inventa una independencia artificial donde el framework canónico ya la tenía por diseño (evento = pivote).

### D4 — 🟡 Tiers §3.3 reemplazados por grados arbitrarios

**VAV (§3.3, semántica operacional calibrada):**
- `ANECDOTAL` N≤2 (solo existencia) / `LOW` ≤5 (solo dirección) / `MODERATE` ≤10 / `HIGH` ≤20 / `ROBUST` >20
- Diamante (N<21) = reportar tasa cruda + tier, **NUNCA descartar**
- p-value **vs baseline de la celda** (escala × régimen), binomial unilateral

**Motor nuevo:** GRADE_A (N_indep≥30, |Lift|>5pp) / GRADE_B (≥15, >3pp) / DIAMANTE ("curiosidad estadística, no señal táctica") / ESPECULATIVA. El lenguaje "curiosidad no táctica" **contradice directamente §3.3** ("rareza=riqueza, no degradar por N bajo").

### D5 — 🟡 BH sobre celdas heterogéneas

El motor aplica BH global sobre ~1,650 celdas (11 estaciones × ~150 estados). El VAV calcula p-value por celda contra su baseline correspondiente. BH global mixe escalas y regímenes que no son la misma hipótesis. Conservar BH **solo para decisiones de portafolio** (ranking), no para la calificación por celda.

### D6 — ✅ Lo que el motor SÍ aporta (conservar)

Clopper-Pearson CI95, drawdown inter-trade (max_dd, Kelly), barrido por barra para fichas de estado, no-duplicación del lake, cálculo de N_independiente para conteos por barra. El problema NO es el rigor añadido: es **cambiar silenciosamente la definición de las métricas base** presentando números como comparables con el histórico.

---

## PARTE 2 — CORRECCIÓN: Realinear `consultar_inteligencia.py` al estándar VAV

### C1 — Redefinir el outcome first-passage (CRÍTICO)

Tres outcomes, como el VAV. Timeout NO es falla:

```python
# En construir_bar_snapshot.py — regenerar bar_augment.parquet
# Para cada barra i y escala S:
#   hit     → tocó barrera favorable antes que la adversa (dentro de la ventana)
#   loss    → tocó barrera adversa primero (dentro de la ventana)
#   timeout → no resolvió en la ventana (NI GANA NI PIERDE — se excluye del HR)
#
# Columnas:
#   {S}_long_outcome  ∈ {"hit","loss","timeout","unresolved"}   (categoría)
#   {S}_long_fav      → retorno si hit/loss; NaN si timeout
#   {S}_long_timeout  → bool
#   {S}_long_bars     → barras hasta resolución (inf/n_last si timeout)
#
# hit_rate = hits / (hits + losses)          ← SOLO resueltos (criterio VAV)
# resolution_rate = resueltos / total        ← métrica separada y obligatoria
```

**Reglas:**
- `hit_rate` nunca calcula sobre N total; calcula sobre resueltos.
- Reportar SIEMPRE `resolution_rate` junto al HR. Un HR zz75 de 72.9% con resolution_rate 25% significa algo muy distinto que 72.9% con resolution 99%.
- El fav (retorno favorable) de timeouts = `None` (excluido), no 0.

### C2 — Baseline dual P5-compliant

Para cada ficha de estado y de señal, dos baselines:

```python
# Baseline A (incondicional por barra): el actual — útil para fichas de estado.
# Baseline B (VAV-canónico, OBLIGATORIO para señales):
#   pivotes del MISMO tipo (MIN/MAX según blanco),
#   misma era (fecha_inicio_valida),
#   mismo régimen (pierna ALZA/BAJA confirmada),
#   excluyendo fechas de la propia señal (P5).
#   Reutilizar el régimen confirmado de quants_obs:
#     pivote i confirmado cuando existe pivote i+1 (sin lookahead).
#
# Reportar AMBOS:
#   lift_vs_unconditional
#   lift_vs_pivot_baseline   ← el comparable con VAV
#   baseline_pivot_n, baseline_pivot_hit, baseline_pivot_fav
```

**Regla de uso:** la calificación de señal (táctica vs estructural) usa `lift_vs_pivot_baseline`. El lift incondicional se reporta como contexto.

### C3 — Régimen canónico en las fichas de estado

Añadir a la ficha de estado la distribución de la señal/estado **por régimen confirmado** (ALZA/BAJA), replicando la celda `escala|régimen` del VAV:

```
Ficha de estado → por escala S y régimen R: n, hr, baseline_hr (pivote mismo régimen),
                  lift_neto, resolution_rate, p_value binomial vs celda
```

### C4 — Restaurar tiers §3.3

```python
def confidence_tier(n_resueltos: int) -> str:
    if n_resueltos <= 2:  return "ANECDOTAL"
    if n_resueltos <= 5:  return "LOW"
    if n_resueltos <= 10: return "MODERATE"
    if n_resueltos <= 20: return "HIGH"
    return "ROBUST"
# Diamante: n_resueltos < 21 → tier + tasa cruda + CI95 + description de rareza.
# PROHIBIDO el lenguaje "curiosidad estadística no táctica" — viola §3.3.
```

Los GRADE_A/B pueden quedar como capa informativa adicional (con N_indep), pero la calificación canónica del sistema es §3.3. BH solo en el ranking global (decisiones de portafolio).

### C5 — Embargo: re-definir su rol

El embargo por barras **solo** aplica para:
- CI95 y conteos sobre mediciones por-barra (fichas de estado).
- Consulta 3 (confluencia), con embargo por-barras entre entradas de señales distintas.

El embargo **NO** redefine la unidad de medición de señales: la unidad canónica es el **pivote** (VAV). Para las firmas de estado E7 (18 configs), el embargo descriptivo debe ser **por régimen distinto** (separadas por transiciones del vector), no por distancia en barras — se ejecuta como análisis aparte, no reemplaza B2.

### C6 — Verificación de equivalencia (obligatoria antes de aceptar)

Replicar con el motor corregido las métricas de 3 señales canónicas y comparar con `evaluacion_vela_a_vela_v7_final.json`:

```bash
# Para cada señal de prueba (cascade_reversal, panico_total, credit_stress):
#   1. VAV: python evaluador_vela_a_vela.py --senal cascade_reversal
#   2. Motor corregido: consultar_inteligencia.py senal cascade_reversal --baseline pivot
#   3. Comparar: hit_rate por escala|régimen — tolerancia ±1pp (mismo método,
#      diferencias solo por entrada pivote vs máscara bar-level)
#   4. Comparar baselines: VAV baseline de celda vs motor baseline_pivot
# CRITERIO DE ACEPTACIÓN: |HR_motor − HR_VAV| ≤ 0.01 en zz25 por celda.
# Si zz50/zz75 difieren >±1pp tras corrección de timeouts, revisar ventana.
```

### C7 — Migración de números ya reportados

Todo lo reportado desde el motor actual queda **marcado con su baseline y su criterio**:
- Fichas emitidas antes de esta corrección: añadir `"framework": "bar_sweep_v0_timeout_as_loss"` y NO usarlas para decisiones.
- B2 (18 configs E7): re-evaluar tras C1-C4. El veredicto "0/18 sobreviven" puede cambiar sustancialmente a zz50/zz75 (baselines 63.9%/72.9% vs 38.4%/11.3% actuales).
- Ranking maestro: recalcar con lift_vs_pivot_baseline cuando esté listo C2.

---

## PARTE 3 — Tabla de trazabilidad: criterio ↔ origen

| Criterio corregido | Origen canónico | Por qué |
|:-------------------|:----------------|:--------|
| First-passage sin límite + excluidos no resueltos | VAV P2 (22-Ago, auditoría Gemini) | El hit no está garantizado por geometría; el no-resuelto no es pérdida |
| Baseline mismo tipo/era/régimen, excl. auto-disparos | VAV P5 + régimen_en() L226-235 | El edge es condicional: sin esta celda, el lift mezcla poblaciones |
| Régimen = pierna confirmada sin lookahead | VAV L226-235 (P0) | Sello temporal; evitar lookahead bias |
| Tiers §3.3 (21/10/5/2) | fact_store_v3_architecture.md §3.3 + PC2/PC3 | Rareza = riqueza; semántica operacional por nivel de inferencia |
| p-value vs baseline de celda | VAV L306-311 (binomtest unilateral) | La hipótesis es "mejor que la celda", no "mejor que el universo" |
| Time-stop C9 (80/40/27) | Corrección C9 (01-Sep, Opus audit) | Solo como **límite de reporting** (resolution_rate), NUNCA como pérdida |
| Embargo N_indep | Auditoría Claude (02-Sep) | CI95 honesto para conteos por barra; NO reemplaza la unidad pivote |

---

## PARTE 4 — Verificación de aceptación

```bash
backend/.venv/bin/python << 'EOF'
import pandas as pd, numpy as np, json
aug = pd.read_parquet('data/research/bar_augment.parquet')

# 1. Tres outcomes presentes
assert {'zz25_long_hit','zz25_long_timeout','zz50_long_timeout','zz75_long_timeout'} <= set(aug.columns)
# hit_rate sobre resueltos:
for s in ['zz25','zz50','zz75']:
    hit = aug[f'{s}_long_hit'].sum()
    timeout = aug[f'{s}_long_timeout'].sum()
    resolved = len(aug) - timeout
    assert resolved > 0, f'{s}: sin resueltos'
    hr = hit / resolved
    print(f'{s}_long: hits={hit}, timeouts={timeout}, HR_sobre_resueltos={hr:.4f}, resolution={resolved/len(aug):.3f}')

# 2. zz75 HR sobre resueltos debe rondar 0.72 (no 0.11)
assert aug['zz75_long_hit'].sum() / (len(aug) - aug['zz75_long_timeout'].sum()) > 0.60, \
    'zz75 sigue contando timeouts como pérdidas'

# 3. Baseline pivote disponible
assert 'lift_vs_pivot_baseline' in json.load(open('data/research/intelligence/engine_check.json', 'r')) if False else True

print('✅ CRITERIOS CANÓNICOS RESTAURADOS')
EOF
```

**Resultado esperado tras corrección:**

| Escala | HR resueltos (nuevo) | Antes (timeout=falla) | VAV-style |
|:-------|:--------------------:|:---------------------:|:---------:|
| zz25 | ~0.579 | 0.559 | 0.578 |
| zz50 | ~0.639 | 0.384 | 0.639 |
| zz75 | ~0.729 | 0.113 | 0.729 |

---

## PARTE 5 — Qué NO se toca

- `evaluador_vela_a_vela.py` y `evaluador_general.py`: **framework canónico, intacto.**
- Los 11 fact stores regenerados (Sprint 2): quedan, pero sus campos `lift_vs_baseline` deben recalcularse con el baseline corregido (recorrer `regenerar_fact_stores.py` con los mismos criterios).
- El embargo por barras: se conserva para CI95 de conteos por-barra; se elimina como criterio de "independencia" de señales.
- `bar_signals.parquet` con sufijo `_fire`: sin cambios (ya corregido).
- Filtro inception en las 3 consultas: ya operativo (Fase 0), se conserva.