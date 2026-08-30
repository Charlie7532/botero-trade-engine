# PROMPT DE COMPLEMENTO AL WALKTHROUGH — Pipeline Completo y Atajos a Corregir

**Origen:** deepseek/deepseek-v4-flash (Hermes) + auditoría independiente
**Objetivo:** Completar el walkthrough de Fase 0→7 con el pipeline real, corrigiendo omisiones y atajos típicos de Gemini.

---

## 1. EL PIPELINE ACTIVO COMPLETO (debe reemplazar al diagrama actual)

Incluir este diagrama en el walkthrough. Es el flujo real — lo que se ejecuta y produce resultados HOY:

```
capas superiores (consumidores)
┌─────────────────────────────────────────────────┐
│  CLASIFICACIÓN FINAL                            │
│  NÚCLEO | DIAMANTES | PROPOSED | ACTIVAS | DEG │
└──────────────┬──────────────────┬───────────────┘
               │                  │
    ┌──────────▼──────┐    ┌──────▼───────────┐
    │ validador_oos   │    │ recompute_triad   │
    │ walk-forward    │    │ agregación pond   │
    │ 10 folds        │    │ ×31 señales       │
    └──────────┬──────┘    │ ×3 escalas        │
               │           └────────┬──────────┘
    ┌──────────▼────────────────────▼──────────┐
    │         evaluador_vela_a_vela             │
    │  first-passage × 3 escalas (zz25/50/75)  │
    │  + forensia F3 (INDEP) + perfil 3D-reg   │
    └──────────┬──────────────────┬────────────┘
               │                  │
    ┌──────────▼──────┐    ┌──────▼───────────┐
    │  31 señales     │    │ continuous_metar │
    │  arnes/señales  │    │ _lake.parquet    │
    │  dominio puro   │    │ 8,453×257 cols   │
    │  f(df)→bool     │    │ z-scores, tiers  │
    └──────────┬──────┘    │ panic/euphoria   │
               │           └────────┬──────────┘
    ┌──────────▼────────────────────▼──────────┐
    │         quants_obs.pkl                   │
    │  1,590 pivotes × 165 columnas            │
    │  bins numéricos en 11 estaciones         │
    │  generado por generate_quants_obs.py     │
    └──────────┬───────────────────────────────┘
               │
    ┌──────────▼───────────────────────────────┐
    │         medir_senal (paquete arnes/)     │
    │  ┌────────────────────────────────────┐  │
    │  │ datos.py     — carga quants_obs    │  │
    │  │ señales.py   — 31 definiciones     │  │
    │  │ medicion.py  — motor medir()       │  │
    │  │ estadisticas — CI95, Fisher, CP    │  │
    │  │ timing.py    — MAE, costo tarde    │  │
    │  │ estructura   — sorpresa, momentum  │  │
    │  │ registro.py  — @_registrar         │  │
    │  └────────────────────────────────────┘  │
    └──────────────────────────────────────────┘
```

---

## 2. LISTA COMPLETA DE LAS 31 SEÑALES (no solo 7 ejemplos)

### 🟢 NÚCLEO ROBUSTO (5) — OOS validado
Incluir para cada una: condición en bins numéricos, N, edge zz75, OOS edge, decay

| Señal | Condición | N | Edge zz75 | OOS | Decay |
|:------|:----------|:-:|:--------:|:---:|:----:|
| capitulacion | VIX≥3 + BSI==0 | 57 | +3.1% | +2.64% | 0.77 |
| pcr_put_panic | PCR==5 | 70 | +4.5% | +2.56% | 0.63 |
| vvix_entry | VVIX==5 | 69 | +4.5% | +2.08% | 0.67 |
| credit_stress | Credit≤1 | 101 | +3.4% | +1.43% | 0.42 |
| bsi_washed_out | BSI==0 | 117 | +5.4% | +0.99% | 0.57 |

### 💎 DIAMANTES §3.3 (2) — N<21, nunca degradar

| Señal | Condición | N | p_raw | CI95 CP | Contexto |
|:------|:----------|:-:|:-----:|:-------:|:---------|
| panico_total | VIX≥4 + SKEW≥4 | 11 | 7/7=100% | [0.59, 1.0] | 11/11 en crisis ±3σ |
| skew_paranoia_exit | SKEW==5 | 10 | 5/6=83% | [0.36, 0.99] | 8/10 en crisis |

### 🟡 PROPOSED (1)

| Señal | Condición | N | Edge | p |
|:------|:----------|:-:|:---:|:-:|
| cascade_reversal | c50 < −0.957 | 240 | +0.28% fijo / +0.44% rolling | 0.25 |

### 🆕 VECTORIALES V2 (3)

| Señal | Condición | N | Edge zz75 |
|:------|:----------|:-:|:--------:|
| capitulacion_v2 | VIX≥3 + BSI==0 + BSI.D2∈{0,1} | 20 | +4.1% |
| euforia_v2 | BSI≥4 + BSI.D2≥3 | 48 | −6.1% |
| vix_crisis_spike_v2 | VIX==5 + VIX.D2≥3 | 61 | +3.4% |

### ⚪ ACTIVAS SIN OOS (8)

| Señal | Condición | N | Nota |
|:------|:----------|:-:|:-----|
| vix_crisis_spike | VIX==5 | 121 | Cerca de significancia (p=0.08) |
| euforia | VIX≤1 + BSI≠0 | 41 | Convergencia bear |
| fg_extreme_fear | FG==0 | 40 | Edge documentado |
| fg_extreme_greed | FG==5 | 29 | Edge documentado |
| sorpresa_total | surprise > P67 | 526 | Shannon surprise |
| stealth_tail_hedging | VIX≤2 + SKEW.D3≥3 | 31 | Convergencia bear |
| sub_reaccion | VIX≥3 + BSI≠0 | 667 | **NO funciona (p=1.0)** — documentar |
| dxy_bearish | DXY==5 | 35 | **NO funciona (p=0.99)** — documentar |

### 🔴 DEGRADADAS (3) — motivos estructurales, NO errores de código

| Señal | Motivo | Evidencia |
|:------|:-------|:----------|
| breadth_contraction_exit | structural break OOS | pre-2016 −1.48%, post +1.81%. Promedio engañoso |
| credit_ease_exit | reliquia pre-QE | +6.99% pre-2009 → −2.84% post (quiebre GFC) |
| bsi_recovery | edge colapsó post-2009 | No replicable tras QE |

### ⚫ RETIRADAS (9)

| Señal | Motivo |
|:------|:-------|
| credit_easing_k1 | pivot_type exclusivo (sesgo de posición) |
| credit_stress_exit | duplicado exacto de credit_stress |
| dxy_spike_exit | duplicado exacto de dxy_bearish |
| pcr_panic_exit | duplicado exacto de pcr_put_panic |
| vix_complacency_exit | duplicado exacto de euforia |
| credit_equity_divergence | LIFT≈1.0 — no discrimina |
| defensive_rotation_divergence | lift<1.0 — anti-señal |
| regime_change_exit | lift<1.0 — anti-señal |
| sv5t_silent_distribution | pivot_type MAX exclusivo |

---

## 3. DISTINGUIR PIPELINE ACTIVO vs LEGACY

El walkthrough actual incluye scripts que NO son parte del pipeline activo. Se deben marcar explícitamente:

| Script | Es | Razón |
|:-------|:---|:-------|
| `extract_overflows_vela_a_vela.py` | 🔴 Legacy | Barrido inicial. Hallazgos incorporados al lake |
| `audit_overflow_candle_anatomy.py` V1 | 🔴 Legacy | Reemplazado por V2 (mezclaba MIN/MAX) |
| `detector_regimen_crisis.py` | 🟡 Semilegacy | One-off (79 episodios). No lo consume nadie hoy |
| `audit_vector_confluence.py` | 🟡 Semilegacy | Scores ya en build_continuous_metar_lake.py |

Estos scripts se preservan por trazabilidad pero NO se ejecutan y NO forman parte del pipeline de medición. Incluirlos sin esta nota confunde a cualquier agente futuro.

---

## 4. CORREGIR PATH DEL ARTEFACTO ANATOMÍA V2

Línea 16 del resumen ejecutivo:
```
❌ data/research/overflow_candle_anatomy_v2.json
✅ data/research/anatomy/overflow_candle_anatomy_v2.json
```

---

## 5. VALIDADOR OOS — AGREGAR RESULTADOS WALK-FORWARD

El walkthrough actual no menciona el validador OOS (10 folds walk-forward anclado). Esto es esencial porque es la única validación que responde "¿se repetirá mañana?".

| Señal | IS | OOS | Decay | Folds+ | Veredicto |
|:------|:--:|:---:|:-----:|:------:|:---------:|
| capitulacion | +3.40% | **+2.64%** | 0.77 | 2/2 | 🟢 SE REPITE |
| pcr_put_panic | +4.04% | **+2.56%** | 0.63 | 3/4 | 🟢 SE REPITE |
| vvix_entry | +3.11% | **+2.08%** | 0.67 | 2/3 | 🟢 SE REPITE |
| credit_stress | +3.42% | **+1.43%** | 0.42 | 3/4 | 🟢 SE REPITE |
| bsi_washed_out | +1.73% | **+0.99%** | 0.57 | 5/6 | 🟢 SE REPITE |

Método: 10 folds cronológicos, train anclado ≥5 años, test ~3 años por fold, mejor celda elegida solo con datos train.

---

## 6. POLÍTICAS DE MEDICIÓN — VERIFICACIÓN DE NO-ARBITRARIEDAD

Incluir sección que responda explícitamente: ¿por qué NO son arbitrarias estas mediciones?

| Método | Respuesta |
|:-------|:----------|
| Bins D1/D2/D3 | Percentiles empíricos expanding — no asume normalidad, zero look-ahead |
| CI95 | Bootstrap 3,000 iteraciones (seed=42) o Clopper-Pearson exacto |
| Walk-forward | 10 folds temporales anclados, mejor celda elegida sin test |
| Overflow tiers | T1(3σ-4σ)..T5(≥10σ) — escala estándar, no inventada |
| First-passage | Primer cruce de umbral — sin horizonte fijo arbitrario |
| Baseline | Excluye pivotes donde la señal disparó — evita contaminación |

**Prohibiciones explícitas (se cumplen):**
- ❌ No degradar por N bajo (§3.3 — rareza=riqueza)
- ❌ No aplicar Bonferroni a señales o diamantes
- ❌ No mezclar MIN y MAX en mediciones de anatomía
- ❌ No usar horizonte fijo 20d como métrica causal
- ❌ No ocultar señales que no funcionan (sub_reaccion p=1.0, dxy_bearish p=0.99)

---

## 7. NOTA SOBRE `_regime_change_exit` — EL BIN CORREGIDO

Incluir como ejemplo de revisión post-auditoría:
> En la primera migración, `_regime_change_exit` usaba `credit_d1 <= 1` (faltaba Bin 2 = NEUTRAL_TIGHT). Fue corregido a `credit_d1 <= 2` en la iteración final tras la auditoría del plan.

Esto muestra que hubo revisión y que los atajos fueron identificados y corregidos.

---

## FORMATO DE ENTREGA ESPERADO

1. Walkthrough actualizado con los 7 puntos anteriores incorporados
2. Mantener la estructura de Fase 0→7 pero con el diagrama de pipeline activo
3. Las 31 señales con clasificación completa (NÚCLEO/DIAMANTE/PROPOSED/etc.)
4. No atajar con ejemplos — el lector necesita el mapa completo del ecosistema
5. Firma del modelo auditor y fecha de actualización

---

## 8. CORREGIR ARCHIVOS DE REFERENCIA PARA AGENTES (hallazgo de Claude Opus)

Además del walkthrough, hay **4 archivos en `.agents/references/metar/`** que contienen formatos pre-homologación. Si un agente futuro los lee sin contexto, operará con state keys incorrectos:

### 8.1 🔴 CRÍTICO — `fact_store_guide.md` — ACTUALIZAR al formato canónico numérico

**Líneas 27-30:** state_key con formato label (pre-homologación):
```
state_key = "{D1_label}__{D2_label}__{D3_label}"
Ejemplo: NEUTRAL_ALERT__ACCELERATING_UP_3D__VOL_ACCELERATING_EXPANSION
```
**Debe ser (formato canónico actual):**
```
state_key = "{D1_bin}__{D2_bin}__{D3_bin}"
Ejemplo: "3__3__3"
```
Los labels semánticos viven en `_documentation.taxonomy` del fact store JSON y son **exclusivamente para presentación al usuario humano**, nunca para comparación en código.

**Línea 96:** mismo problema — el ejemplo usa labels de texto como keys del fact store. Actualizar a: `fs["5__4__3"]`.

### 8.2 🟡 ALTA — `signal_rules.md`
**Línea 45:** Usa labels sin bin equivalente. Añadir el bin numérico como referencia junto a cada label. Ejemplo correcto:
```
VIX con state_key "5__4__3" (EXTREME_PANIC + FAST_SPIKE + VOL_ACCEL) → modo crisis
```

### 8.3 🟡 ALTA — `gaussian_scale_policy.md`
**Líneas 43-48:** Labels genéricos de ejemplo (`DEEP_COMPLACENCY`, `LOW_VOL`, etc.) que no corresponden a la taxonomía canónica de ninguna estación. Reemplazar o referenciar la tabla real en `d1_labels_canonical.md`.

### 8.4 ⚪ BAJA — `overflow_taxonomy.md`
**Línea 102:** Nota de pendiente que ya fue resuelto en Fase 0 (T1-T5 implementados en `sigma_overflow.py`). Eliminar o marcar como resuelto.

### 8.5 ➕ Crear `agent_quick_reference.md`
Crear un archivo compacto en `.agents/references/metar/agent_quick_reference.md` con:
1. **Regla #1:** Usa `d1_vote` para polaridad (−1/0/+1). NO interpretes `d1_bin` direccionalmente.
2. Regla de oro: "Bins para comparar, Labels para presentar"
3. Snippets de acceso a fact stores y clasificador centralizado
4. Las 5 señales del NÚCLEO ROBUSTO con condiciones canónicas
5. Referencia rápida de bins: 0=extremo_inferior, 2=neutro, 4=extremo_superior, 5=overlfow

Esto elimina la necesidad de que cada agente lea 1,264+ líneas de documentación para operar correctamente.

---

## 9. CONFIRMAR: "Extremo" = +-2sigma (homologado en D1/D2/D3)

**La regla ya es consistente en las tres dimensiones PERO debe explicitarse en toda documentacion y codigo para evitar ambiguedad.**

### 9.1 Regla Universal

> When any code, documentation, or signal refers to a dimensional state as "extreme", it MUST correspond to the +/-2sigma bins:
> - **D1** extremes: Bin 0 (< -2sigma) or Bin 5 (>= +2sigma) -> **2.28% of population each**
> - **D2** extremes: Bin 0 (`FAST_CRUSH_3D`) or Bin 4 (`FAST_SPIKE_3D`) -> **2.28% each**
> - **D3** extremes: Bin 0 (`VOL_EXTREME_SQUEEZE`) or Bin 4 (`VOL_PEAK_DECELERATION`) -> **2.28% each**

Los percentiles Gaussianos son identicos: `[0.0228, 0.1587, 0.5, 0.8413, 0.9772]` para D1 (6 bins) y `[0.0228, 0.1587, 0.8413, 0.9772]` para D2/D3 (5 bins). La unica diferencia es que D1 subdivide la zona media en dos bins (+/- 1sigma), D2/D3 tienen un bin central unico.

### 9.2 Implicaciones para codigo

```python
# CORRECTO — funcion generica para detectar extremo en cualquier dimension
def es_extremo(d1_bin, d2_bin, d3_bin):
    d1_extremo = d1_bin in {0, 5}        # 6 bins
    d2_extremo = d2_bin in {0, 4}        # 5 bins (mismos percentiles +/-2sigma)
    d3_extremo = d3_bin in {0, 4}        # 5 bins (mismos percentiles +/-2sigma)
    return d1_extremo or d2_extremo or d3_extremo

# INCORRECTO — asumir que extremo siempre es Bin 5
if d1_bin == 5:   # Funciona en D1, FALLA en D2/D3 donde extremo es Bin 4
```

### 9.3 Archivos a verificar/corregir

| Archivo | Debe explicitar la regla |
|:--------|:------------------------|
| `gaussian_scale_policy.md` | YA corregido por Opus — verificar que incluya la nota de D2/D3 |
| `agent_quick_reference.md` | Debe incluir la tabla de comparacion con bins exactos |
| Cada lookup adapter | No necesita cambio — los percentiles ya estan en el JSON |
| Cada senal en senales.py | No necesita cambio — `_get_dim()` extrae el bin y la condicion usa operadores de comparacion |

---

## 10. LIMPIEZA DE LEGACY — Separar en carpeta dedicada

**Problema:** Scripts de exploracion historica (`extract_overflows_vela_a_vela.py`, `audit_overflow_candle_anatomy.py` V1, `detector_regimen_crisis.py`, `audit_vector_confluence.py`, `wins_losses_*.py`) conviven con el pipeline activo en `research/01_senales_entry_exit/`. Un agente futuro no distingue que es produccion vs exploracion.

### 10.1 Accion: Mover legacy a `research/_legacy/`

```
research/01_senales_entry_exit/        <- solo pipeline activo
  arnes/                              <- medicion
  evaluador_vela_a_vela.py            <- activo
  recompute_signals_fact_store_triad_v2.py  <- activo
  audit_overflow_candle_anatomy_v2.py <- activo (V2, segregado)
  build_continuous_metar_lake.py      <- activo

research/_legacy/                       <- scripts legacy preservados
  extract_overflows_vela_a_vela.py    <- barrido inicial
  audit_overflow_candle_anatomy.py    <- V1 (mezclaba MIN/MAX)
  detector_regimen_crisis.py          <- one-off 79 episodios
  audit_vector_confluence.py          <- scores ya en lake
  wins_losses_entry47_v2.py           <- medicion antigua
  wins_losses_top3_v2.py              <- medicion antigua
  wins_losses_exit_neutral_v2.py      <- medicion antigua
  wins_losses_summary.py              <- medicion antigua
  wins_losses_sv5t_vix_bsi_credit.py  <- medicion antigua
  wins_losses_yield_rotation.py       <- medicion antigua
  README_LEGACY.md                    <- nota de trazabilidad
```

### 10.2 README_LEGACY.md

Incluir nota estandar en cada lote de legacy:
> *"Este script fue parte del trabajo de descubrimiento historico. Su funcionalidad fue incorporada al pipeline activo. Se preserva exclusivamente para trazabilidad y re-evaluacion futura. NO ejecutar como parte del pipeline de medicion."*

### 10.3 No mover (permanecen en su lugar)

| Archivo | Razon |
|:--------|:-------|
| `build_continuous_metar_lake.py` | Pipeline activo — regenera el lake |
| `audit_overflow_candle_anatomy_v2.py` | Pipeline activo — anatomia segregada V2 |
| `recompute_signals_fact_store_triad_v2.py` | Pipeline activo — triada ponderada |
| `evaluador_vela_a_vela.py` | Pipeline activo — first-passage |
| `arnes/` | Pipeline activo — 8 modulos de medicion |

---

## 11. VERIFICACION END-TO-END COMPLETA — Desde Vault hasta Senales

Despues de la limpieza, ejecutar verificacion completa para confirmar que nada se rompio:

### 11.1 Pipeline de regeneracion (orden correcto)

```bash
# 1. Fact stores (JSON) — se regeneran desde el Vault si es necesario
#    Politica: los fact stores son la fuente de verdad. NO se regeneran a menos
#    que cambien los datos del Vault o se modifique la taxonomia.

# 2. Lake continuo — regenerar despues de fact stores
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \\
  research/01_senales_entry_exit/build_continuous_metar_lake.py

# 3. Tabla pivotal — regenerar despues del lake
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \\
  backend/scripts/generators/generate_quants_obs.py

# 4. Suite de tests — verificar que nada se rompio
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -m pytest tests/ -q

# 5. Compuerta de proposito — 31/31 senales activas
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c \\
  "import sys; sys.path.insert(0, 'research/01_senales_entry_exit'); import arnes.datos as dm; df,_ = dm.cargar_datos(); from arnes import SENALES; activas = sum(1 for n,f in SENALES.items() if f(df).astype(bool).sum() > 0); assert activas == 31; print(f'{activas}/31 senales activas')"

# 6. Evaluador (opcional, pesado)
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \\
  -c "from evaluador_vela_a_vela import evaluar; evaluar('todas')"
```

### 11.2 Politicas de actualizacion de JSON fact stores

| Evento | Accion | Responsable |
|:-------|:-------|:-----------|
| Nuevos datos en Vault | Regenerar fact stores + lake + quants_obs + tests | Humano |
| Cambio de taxonomia | Regenerar fact stores + lake + quants_obs + tests + walkthrough | Humano decide |
| Correccion de bug en lookup adapter | Solo el adapter + tests | Automatico |
| Nueva senal en arnes/senales.py | Tests + compuerta 31/31 -> si todo verde, ok | Automatico |

**Regla:** Los fact stores JSON se regeneran DESDE el Vault, no se editan a mano. Cualquier modificacion manual debe documentarse con timestamp y razon en el commit.

### 11.3 Verificacion post-limpieza

| Check | Comando | Resultado esperado |
|:------|:--------|:------------------|
| Tests | `pytest tests/ -q` | 303 passed |
| Senales activas | `medir_senal --list` | 31/31 |
| Lake existe | `build_continuous_metar_lake.py --dry-run` | Sin errores |
| quants_obs schema | `generate_quants_obs.py --dry-run` | 1590x165, sin errores |
| No queda legacy en activo | No hay scripts de wins_losses en research/01_senales_entry_exit/ | 0 scripts |
| No hay imports rotos | `from arnes import SENALES; len(SENALES)` | 31 |

---

## FORMATO DE ENTREGA FINAL

1. **Walkthrough actualizado** con los 11 puntos anteriores incorporados
2. **Archivos de referencia corregidos** (fact_store_guide, signal_rules, gaussian_scale_policy, overflow_taxonomy)
3. **agent_quick_reference.md creado** con la Regla #1: usar d1_vote, no interpretar d1_bin direccionalmente
4. **Legacy movido a research/_legacy/** con README_LEGACY.md
5. **Pipeline completo ejecutado** y verificado (tests + compuerta 31/31)
6. **Firma del modelo auditor y fecha**
