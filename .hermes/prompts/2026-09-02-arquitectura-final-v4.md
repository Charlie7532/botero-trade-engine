# PROMPT MAESTRO DEFINITIVO: Sistema Unificado de Inteligencia de Señales (v4.0)
## Arquitectura corregida tras auditoría de Claude Opus — Dato mata relato

**Propósito:** Consolida 114+ archivos dispersos del subsistema de señales y estados en un conjunto mínimo y canónico. Resuelve la pregunta operativa del Entry Gate: *"dado el estado actual Y la señal que disparó, ¿cuál es el rendimiento esperado con su incertidumbre muestral honesta?"*

**Archivos de salida (SOLO 3, sin duplicar el lake):**

```
data/research/
├── continuous_metar_lake.parquet    ← YA EXISTE (8,453 × 257) — NO TOCAR, NO DUPLICAR
├── bar_augment_first_passage.parquet ← NUEVO: 51 columnas que NO existen en el lake
│                                        indexado por time, join trivial
├── bar_signals.parquet              ← NUEVO: 74 columnas (37 señales × bool+entry)
│                                        indexado por time
└── _archive/                        ← Mover los 114+ archivos viejos aquí
```

**Dato factual verificado (30-Sep-2026):**
- Lake: 8,453 filas × 257 columnas, rango 1993-01-29 → 2026-08-28.
- Las **110 columnas de estación** (11 estaciones × 10: `_sk`, `_d1/2/3_bin`, `_z_d1/2/3`, `_overflow_tier_d1/2/3`) **YA EXISTEN** en el lake.
- Benchmark `first_passage_bar` (método estándar): 50,718 llamadas ≈ **0.3s**. Rápido.

---

## 1. Directivas de Rigor Cuantitativo (Anti-Complacencia)

1. **Dato Mata Relato.** Ningún estado ni señal se asume ganador por lógica de mercado. Todo se mide.
2. **Lift vs Baseline es la métrica reina.** El drift alcista incondicional de SPY hace que el HR bruto sea engañoso. Reportar obligatoriamente `Lift = HR − Baseline_incondicional`. Si `Lift ≤ 0`, sin edge estadístico.
3. **DECLUSTERING POR EMBARGO (nuevo, crítico).** Las ventanas first-passage se superponen masivamente. Declarar el **N efectivo independiente** tras purgar `⌈2/scale⌉` barras posteriores a cada medición, **NO el N crudo.** Este es el punto más grave que la auditoría corrigió.
   - Evidencia: VIX `2__2__2` tiene 1,464 barras pero N_independiente ≈ 14 (99.1% de pares comparten la misma ventana FP de 80 barras).
4. **Control de múltiples pruebas.** Todo con CI95 Clopper-Pearson y BH. Con 1,650+ celdas laxas, ~250 falsos descubrimientos solo por azar.
5. **Diamantes §3.3 — no degradar por N bajo.** Reportar siempre con su `tier_rareza` y su `n_insuficiente: true`. Los ratios continuos (Sharpe/Kelly) NO se calculan con N < 30, pero la asimetría real, MAE y MFE sí se reportan. Sin embargo, el N reportado es **siempre el purgado**, no el crudo.
6. **Cero Proliferación.** Máx 3 archivos canónicos. La síntesis estadística se genera **bajo demanda** como script de consulta, no como archivo monolítico estático (evita el God Object).

---

## 2. Archivo NUEVO 1: `bar_augment_first_passage.parquet` (51 columnas)

SOLO las columnas que NO existen en el lake. Indexado por `time` (join con lake).

### Grupo A — Timing de Ciclo ZigZag (4 columnas)
- `tim_slot`: "t-2","t-1","t=0","t+1","t+2","ENTRE" (usar `classify_timing_slots` de `arnes/timing.py`)
- `pivot_nearest_type`: "MIN"/"MAX"
- `pivot_nearest_date`: fecha del pivote SPY más cercano (de `quants_obs.pkl`, 1,590 pivotes)
- `delta_bars_pivot`: distancia con signo (negativo=anticipa, 0=coincide, positivo=retrasa)

### Grupo B — Resolución First-Passage Triple Barrier (36 columnas)
Por cada escala S ∈ {zz25=2.5%, zz50=5.0%, zz75=7.5%}, en LONG y SHORT:
- `{S}_long_hit`, `{S}_long_fav`, `{S}_long_mae`, `{S}_long_mfe`, `{S}_long_bars`, `{S}_long_timeout`
- `{S}_short_hit`, `{S}_short_fav`, `{S}_short_mae`, `{S}_short_mfe`, `{S}_short_bars`, `{S}_short_timeout`

Time-stop canónico: zz25→80v, zz50→40v, zz75→27v. Timeout = falla.
Método: `first_passage_bar`. Cómputo total ≈ 0.3s.

### Grupo C — Entry Flags de Estación (11 columnas, opcional)
- `{E}_entry`: True en la primera barra donde `{E}_sk` cambia vs el día anterior.

**NOTA:** Las columnas `{E}_sk`, `{E}_z_*`, `{E}_overflow_tier_*` YA están en el lake. No duplicar.

---

## 3. Archivo NUEVO 2: `bar_signals.parquet` (74 columnas)

- Por cada una de las 37 señales de `arnes/señales.py`: `{S}` (bool) + `{S}_entry` (bool, primera barra de transición 0→1 calculada con `build_episodes`).
- **Señales posicionales (usan `pivot_type`):** mapear el pivote SPY más cercano (≤2 barras). Si la barra dista >2 barras, `pivot_type=None` → señal False.
- Se regenera en ~0.3s cuando cambia el catálogo.

---

## 4. Síntesis bajo demanda `consultar_inteligencia.py` (NO un archivo estático)

Un script de consulta que responde la pregunta del Entry Gate. NO produce un JSON monolítico. `lake.join(bar_augment).join(bar_signals)` en memoria, luego filtra/agrega según la consulta.

### Las 3 consultas canónicas que debe soportar

**CONSULTA 1 — Ficha de estado (clima de hoy):**
```
Input:  estación + state_key (ej: vix, "5__4__3")
Output: - N_barras, %_tiempo, N_episodios de entrada ({E}_entry)
        - Duración media y máxima de permanencia en el estado
        - First-passage Long & Short a 3 escalas con Lift vs baseline
        - Clasificación funcional (abajo)
```
**Régimen del mercado:** derivado del **consenso de estaciones** — contar cuántas de las 11 están en estado extremo inferido desde D1 y D2:
- ≥3 estaciones con `D1≥3` y `D2≥3` → `CRISIS_ACELERACION`
- ≥4 estaciones con `D1≤1` y `D2≤2` → `COMPLACENCIA_GLOBAL`
- VIX `D1≥4` dominante (peso D3: si D3≥3 sin convicción, rebaja el régimen) → consideraciones de convicción
- Fallback → `RUIDO_MODAL`

**CONSULTA 2 — Ficha de señal (edge en contexto):**
```
Input:  señal + estación + state_key
Output: - N_episodios (de {S}_entry)
        - N_INDEPENDIENTE purgado por embargo (reportar SIEMPRE este)
        - HR, Lift, CI95 (sobre N_independiente), p_raw, p_BH
        - MAE, MFE, bars_medio, drawdown (max_dd, avg_loss, kelly si N≥30)
        - Timing distribution (quantos en rango vs ENTRE) — SOLO descriptivo, NO clasifica el estado
        - Grado: GRADE_A_VALIDADA / GRADE_B_MODERADA / GRADE_C_DIAMANTE / ESPECULATIVA
        - Acción: PRODUCCION_PLENA / EXCEPCION_COLA / MONITOREO
        - Micro-estados donde dispara y cómo varía su edge entre ellos
        - Ventana de incepción respetada (ESTACION_INCEPTION_DATES)
```

**CONSULTA 3 — Confluencia (bajo demanda, no pre-materializada):**
```
Input:  par de señales (opcional escala y dirección)
Output: - Co-ocurrencia (n días ambos activos)
        - Independencia (correlación de Pearson + solapamiento de estaciones)
        - Edge combinado vs individual (¿mejora el HR o es redundancia?)
NOTA: 666 pares × 6 = 3,996 tests potenciales → aplicar BH siempre. ~200 falsos esperados por azar.
```

---

## 5. Clasificación funcional de estados (SIN circularidad de timing)

**Advertencia de la auditoría:** el timing mide proximidad al pivote de **SPY** (no del indicador). Clasificar un estado como "INFLEXION" por su timing es **circular** — el extremo de VIX coincide con el giro de SPY por construcción. La clasificación funcional debe derivarse de **métricas intrínsecas del estado, no del timing:**

| Clasificación | Métrica (intrínseca) | Regla |
|:--------------|:---------------------|:------|
| `CONTINUACION_IMPULSO` | MAE y MFE ambos > 0 (el movimiento sigue su sesgo) | `sign(MFE)=sign(MAE)` y `|Lift|≥5%` |
| `REVERSION_ESTRUCTURAL` | MAE y MFE opuestos (reversión tras excursión adversa) | `sign(MFE)=-sign(MAE)` y asimetría RR alta |
| `INESTABILIDAD_PRECURSORA` | D3≥3 con D1∈[2,3] (volatilidad oculta) | `D3≥3 & D1∈{2,3}` |
| `RUIDO_ESTACIONARIO` | Lift cerca de cero y MAE ≈ baseline | `|Lift|<2%` y MAE≈baseline |

---

## 6. Regímenes: Transiciones del vector de estado (NO décadas)

La estabilidad temporal se mide por **transiciones D1×D2×D3 y overflows**, no por décadas:
- `COMPLACENCIA`: VIX D1=0,1
- `NEUTRAL`: VIX D1=2,3 (~68% del tiempo)
- `CRISIS`: VIX D1=4,5
- `CRISIS_EXTREMA`: VIX D1=5 + overflow D1≥T1
- `RECUPERACION`: VIX D1 pasando 5→3→2

**Detección de cambio de régimen:** ventana rolling 12 meses (~250 barras). Si el CI95 del HR rolling no solapa el CI95 histórico, emitir NOTAM: `SEÑAL_PERDIO_EFECTIVIDAD` o `REGIMEN_CAMBIO`.

---

## 7. Calificación de señales (preserva tu intención)

| Grado | Regla (N = N_independiente purgado) |
|:------|:------------------------------------|
| `GRADE_A_VALIDADA` | N_indep≥30, p_BH<0.05, |Lift|>5% |
| `GRADE_B_MODERADA` | N_indep≥15, p_BH<0.10, |Lift|>3% |
| `GRADE_C_DIAMANTE` | N_indep<15, asimetría confirmada (§3.3) |
| `ESPECULATIVA` | Sin evidencia suficiente |

**Nota sobre N:** El N_independiente purgado (no el crudo) es la base de todo. Una señal puede tener N_crudo=200 pero N_indep=18 → GRADE_B, no GRADE_A. **Esto NO descarta la señal — solo hace honesto su CI95.**

---

## 8. Verificación y Control de Calidad

```bash
backend/.venv/bin/python -c "
import pandas as pd, numpy as np, json
lake = pd.read_parquet('data/research/continuous_metar_lake.parquet')
aug = pd.read_parquet('data/research/bar_augment_first_passage.parquet')
sig = pd.read_parquet('data/research/bar_signals.parquet')

# 1. Alineación de índices
assert len(aug) == 8453 and len(sig) == 8453
assert (aug.index == lake.index).all() and (sig.index == lake.index).all()

# 2. No duplicamos el lake
assert not any(c in aug.columns for c in ['vix_sk','spy_close','vix_z_d1']), 'DUPLICA EL LAKE!'

# 3. Columnas críticas presentes
assert 'zz25_long_hit' in aug.columns and 'tim_slot' in aug.columns
assert 'panico_total_entry' in sig.columns

# 4. Declustering: N_independiente por embargo
#    El script de consulta DEBE reportar n_independiente, no n_crudo

print('✅ ARQUITECTURA JOAIN NIVEL: lake sin duplicar + 2 parquets nuevos (125 cols totales nuevas)')
"
```

---

## 9. Política de Archivo

Mover a `data/research/_archive/` (NO borrar) los 114+ archivos obsoletos tras validar que las consultas reproducen sus resultados:
- `medicion_*.json` (35 raíz + 31 signals)
- `evaluacion_vela_a_vela_v1..v7_final.json`
- `evaluacion_generalizada_lake.json`
- `ranking_maestro.json`
- `e7_taxonomia_estados.json`
- Fichas de inteligencia unitarias generadas por deber de tracción

---

## 10. Cadencia de regeneración

| Artefacto | Frecuencia | Trigger |
|:----------|:----------:|:--------|
| `bar_augment_first_passage.parquet` | Trimestral | Cambia calibración de bins σ |
| `bar_signals.parquet` | Semanal | Cambia catálogo de señales |
| `consultar_inteligencia.py` | Bajo demanda | Sin almacenamiento estático |
| `_archive/` | Manual | Tras validar reproducción |

---

## 11. Las 3 preguntas que este sistema responde HOY

| Necesidad | Respuesta |
|:----------|:----------|
| **METAR** (¿qué clima hay?) | Ficha del estado actual (Consulta 1) — descriptivo |
| **TAF** (¿qué esperar?) | Rendimiento condicional con CI95 honesto + N purgado (Consulta 2) — inferencial |
| **SIGMET/NOTAM** (¿advertencias?) | Cambio de régimen (rolling vs histórico) + confluencias (Consulta 3) — alertas |