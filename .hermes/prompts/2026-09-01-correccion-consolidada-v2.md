# PROMPT DE CORRECCIÓN CONSOLIDADO — Forense Dimensional + Ejercicios + Arquitectura
# VERSIÓN CORREGIDA POST-AUDITORÍA CLAUDE OPUS

**Origen:** deepseek/deepseek-v4-flash (Hermes) + Claude Opus
**Propósito:** 20 correcciones priorizadas tras auditoría combinada de E1-E6, cobertura D1/D2/D3, tríada zigzag y estocasticidad

**Advertencias de la auditoría anterior ya incorporadas:**
- ❌ RN1 (renombrar señales.py) → Rechazado por Rule 12
- ❌ G1 (EV episodio) → Rechazado por duplicar first-passage
- ❌ G2 (EV post-episodio) → Rechazado por lookahead
- ⏸️ G4 (rendimiento slot zz50/zz75) → Diferido sin caso de uso
- ❌ C10 (renombrar perfil_3d_régimen) → Rechazado por Rule 12. Daño colateral: rompe cadena evaluador→JSON→ranking.

**Fe de erratas (correcciones de la auditoría Claude Opus):**
- C13-C16: Propuestas como "señales" por frecuencia sin señal, pero no validadas con el evaluador. Reclasificadas a "candidatos a evaluar". Dato mata relato.
- C15: D2=0 = FAST_CRUSH (velocidad más NEGATIVA), no "desacelerando".
- C16: tipo=exit, no entry. VIX D3=4 = warning de salida, no de entrada.
- Tabla de patrones: (5_2_x) aparecía duplicada con 2 interpretaciones. Unificada.
- C3/C8: Bloqueante no documentado — el lake no tiene z-scores continuos que requiere `confluencia.py`.

**Ejercicio E8 — BH/DSR ya computado con datos reales (NO teórico):**
- **Benjamini-Hochberg (FDR):** ✅ **18/194 celdas pasan BH** (q=0.05). Top 5: `capitulacion` zz50 (p=0.0001), `panico_total` zz50 (p=0.0001), `vix_crisis_spike_v2` zz50 (p=0.0001), `vix_crisis_spike` zz75 (p=0.0001), `cascade_reversal` zz50 (p=0.0002). **Ver script `/tmp/bh_real_desde_evaluadores.py`.**
- **Deflated Sharpe Ratio (DSR):** ✅ **PASA DSR** (0.473). Max z-score observado=3.719 vs esperado bajo H0=3.246. Las señales top NO son ruido.
- **Bootstrap CI95:** ✅ **E1 confirmado:** ALZA HR=87.0% CI95=[79.3%, 93.5%], BAJA HR=32.6% CI95=[25.2%, 40.7%]. Intervalos no se solapan.
- **Implementación requerida:** Agregar columna `p_BH` y `DSR` al `consolidar_ranking.py`. Los p-values ya existen en los evaluadores (`p_value_binom` en `evaluador_general.py`, `p_value` en `evaluador_vela_a_vela.py`).
- ⏸️ Combinatorial Purged Cross-Validation (purging temporal) — diferido (requiere refactor OOS)
- ⏸️ Meta-labeling (separar dirección de tamaño de posición) — diferido (requiere diseño nuevo)

---

**Taxonomía del Vector de Estado — Hallazgos Verificados:**

### Rango canónico de dimensiones
- **D1: 6 niveles (0..5)** — 0 = piso -2σ, 5 = extremo +2σ. Rango completo operativo.
- **D2: 5 niveles (0..4)** — 0 = CRUSH (cayendo rápido), 4 = SPIKE (subiendo rápido). **4 es el extremo ±2σ. No existe 5** por diseño de calibración correcto.
  - D2=0,1 = **velocidad negativa** (VIX cayendo desde pico). D2=3,4 = **velocidad positiva** (VIX acelerando al alza).
  - **D2=2 es AMBIGUO/INDETERMINADO** — abarca del percentil 15.87 al 84.13 (-1σ a +1σ, ~68%). **Incluye TANTO velocidad negativa COMO positiva.** `STABLE_CONTINUATION_3D` es engañoso → debería ser `AMBIGUOUS_VELOCITY_3D`.
  - Cuando D2 supera ±2σ (más allá de bin 4), se desborda a overflows T1-T5+ hasta BLOWOFF (>10σ).
  - Ningún evaluador cruza D2 con overflows.
- **D3: 5 niveles (0..4)** — 0 = MUY_ESTABLE (convicción), 4 = MUY_INESTABLE (duda). 4 es el extremo.
- **Combinaciones doble extremo (5_4_x), (5_x_4), (x_4_4) existen pero son raras.** (5_4_4) es casi inexistente (0-2 ocurrencias).

### Cascada dimensional real
- **D3=4 precursora en 11.7% de casos** (20/171 eventos D1=5). 88.3% saltan directo.
- **Sesgo del indicador:** Lo que es alcista para VIX puede ser bajista para BSI.

### Patrones de rango medio (definen ~68% del mercado)
| Patrón | VIX | BSI | SKEW | Interpretación |
|:-------|:---:|:---:|:----:|:---------------|
| `(2_2_2)` | +0.14% WR 57.7% | +0.11% WR 53.2% | -0.10% WR 50.5% | **Mild bullish** para VIX/BSI |
| `(3_2_2)` | +0.13% WR 51.6% | +0.09% WR 52.1% | +0.02% WR 50.0% | **Neutral** — estado más común |
| `(1_2_2)` | +0.32% WR 75.0% | -0.40% WR 38.4% | +0.06% WR 47.2% | **Divergencia crítica** VIX vs BSI |
| `(0_2_2)` | — | -1.66% WR 30.8% | -0.18% WR 45.4% | **Piso NO es compra** |

### Extremos que definen edge operativo (VIX D1=5)
| Patrón | D2 | SPY ret | WR | N | Taxonomía |
|:-------|:---|:-------:|:--:|:-:|:----------|
| `(5_4_x)` | D2=4 — VIX acelerando AL ALZA | **-3.50%** | 15.8% | 57 | **PÁNICO CLÍMAX** |
| `(5_3_x)` | D2=3 — VIX subiendo lento | **-0.89%** | 32.3% | 31 | **ABDICACIÓN** |
| `(5_2_x)` | D2=2 — VIX plano (ambigüo) | **+1.20%** | 62.1% | 29 | **AMBIGUO** — giro o pausa |
| `(5_<2_x)` | D2<2 — VIX cayendo (vel negativa) | **+0.80%** | 61.1% | 54 | **CONTRARIAN BUY** |

---

## 🔴 P0 — NUEVO EJERCICIO E7: Taxonomía de Estados del Vector (D1×D2×D3)

**Propósito:** Analizar sistemáticamente el significado y frecuencia de cada combinación del vector de estado para las 11 estaciones METAR. No solo extremos — también patrones de rango medio.

### Datos de entrada
| Dataset | Barras | Columnas |
|:--------|:------:|:---------|
| Lake continuo | 8,453 | `*_d1_bin`, `*_d2_bin`, `*_d3_bin` para 11 estaciones |
| quants_obs | 1,354 | `*_sk`, `daily_return_pct` |

### Preguntas por estación
1. **Top 10 state keys** — frecuencia y SPY retorno
2. **Patrón (2_2_2)** — ¿continuación, complacencia o ruido? varía por estación
3. **Patrón (3_2_2)** — ¿continuación alcista o agotamiento?
4. **D2=2 cuando D1 extremo** — ¿complacencia o señal contrarian?
5. **D3=4 cuando D1 neutral (2,3)** — ¿precursora de crisis? (11.7% de casos)
6. **D2=0 cuando D1=0** — ¿capitulación o continuación?
7. **D2=4 cuando D1=5** — ¿explosión o agotamiento?

### Reglas de ejecución
1. No limitarse a extremos. Rango medio es 68% del mercado.
2. Reportar por estación separadamente.
3. D3=4 precursora: documentar si cayó en 30d vs casos sin crisis.
4. Output: `data/research/signals/e7_taxonomia_estados.json`.
5. **Fase 1: VIX + BSI + CREDIT** (3 estaciones más operacionales). Fase 2: resto.

---

## 🔴 P0 — Errores Factuales en Ejercicios E1-E6

Estos 4 errores se resuelven automáticamente implementando **C11 (framework conclusiones dinámicas)** primero. Ver orden de ejecución.

### C1 — E1: Conclusión hardcoded 76% vs dato real 32.6%
**Archivo:** `ejercicios_regimen.py`
**Datos:** JSON dice "76% en BAJA" cuando `hit_rate_baja = 0.326`.

### C2 — E4: Conclusión "≤5 barras" vs mediana real 10.0
**Archivo:** `ejercicios_regimen.py`
**Datos:** `mediana_barras_resolucion = 10.0`.

### C3 — E5: Lift negativo invalida hipótesis
**Archivo:** `ejercicios_regimen.py`
**Datos:** `lift_vs_unconditional = -0.0244`. Confluencia ≥2 estaciones NO produce edge.
**⚠️ Bloqueante:** El lake NO tiene `*_d1_z` ni `*_d2_z` (z-scores continuos). `calcular_score_confluencia()` espera z-scores, no bins discretos. Sin generar esas columnas, C8 caerá al fallback de bins que ya produce lift negativo.

### C4 — E6: N=0 en bear invalida comparación
**Archivo:** `ejercicios_regimen.py`
**Datos:** N=18 bull / N=0 bear. FG Extreme Greed solo ocurre en bull markets.

---

## 🔴 P0 — Rankings y CI95 (3 correcciones)

### C5 — Sin CI95 Clopper-Pearson en E1-E6
**Archivo:** `ejercicios_regimen.py`
**Fix:** Agregar a cada hit rate:
```python
from scipy.stats import binom
ci_low, ci_high = binom.interval(0.95, n, p_hat) / n  # canónico
```

### C6 — Bonferroni + BH en ranking maestro
**Archivo:** `consolidar_ranking.py`
**Datos ya verificados:** 18/194 celdas pasan BH (q=0.05). DSR=0.473 (pasa). Los p-values existen en `p_value_binom` (lake) y `p_value` (VAV).
**Fix:** Agregar columnas `p_bonferroni = min(p * 33, 1.0)` y `p_BH` al ranking. Reportar ambos. Implementar en `consolidar_ranking.py` usando los p-values ya producidos por los evaluadores.

### C7 — Sin p-values ni Bonferroni en E1-E6
**Archivo:** `ejercicios_regimen.py`
**Fix:** Fisher/Mann-Whitney U con α' = 0.05/6 = 0.0083.

---

## 🟡 P1 — Cobertura Dimensional (2 correcciones)

### C8 — E5 rediseño: Confluencia multi-dimensional
**Archivo:** `ejercicios_regimen.py`
**⚠️ Bloqueante no resuelto:** El lake tiene `*_d1_bin` (enteros 0-5) pero NO tiene `*_d1_z` (z-scores continuos). `calcular_score_confluencia()` espera z-scores.
**Acción previa requerida:** Verificar si z-scores existen en el lake o reconstruirlos desde raw values. Sin esto, C8 no es ejecutable.

### C9 — Time-stop como tercera barrera en first-passage
**Archivo:** `evaluador_general.py`
**Fix:** `max_barras = ceil(1/scale)`. zz25→40b, zz50→20b, zz75→14b. Retornar `timeout=True` como fracaso (contar en métricas, no excluir).

---

## ⚪ P2 — Arquitectura (1 corrección)

### C11 — Framework de conclusiones dinámicas
**Archivo:** `ejercicios_regimen.py`
**Prioridad:** **HACER PRIMERO**. Absorbe C1-C4 automáticamente.
**Fix:** Función `_generar_conclusion(ej, res)`:
- Lift significativo → "CONFIRMADO"
- N < 21 → "DIAMANTE §3.3"
- p > α' → "NO SIGNIFICATIVO tras Bonferroni"
- Contradice hipótesis → "RECHAZADO"

### C12 — Documentar eras en E3 (trivial)

---

## 🟡 P1 — Candidatos Dimensionales a Evaluar (antes llamados "señales")

**Nota:** Estos NO son señales validadas. Son candidatos identificados por frecuencia sin señal en el catálogo actual. Requieren evaluación con `medir()` o `evaluar_condicion_booleana()` antes de crear en `señales.py`. Dato mata relato.

### C13 — SKEW D1=0 → candidato `skew_complacencia`
**Datos:** 516 pivotes (32.5%). WR 44.0%, SPY -0.28%. **WR baja — no es EXIT claro.**
**Estado:** CANDIDATO. Evaluar antes de crear. Si el evaluador confirma edge, nombrar `skew_complacencia_exit` (tipo=exit).

### C14 — BSI D1≤1 → candidato `bsi_compression`
**Datos:** 589 pivotes (37%). WR 31.9%, SPY -0.91%. **Bearish, no ENTRY.** D1=0 da WR 21.7%, D1=1 da WR 35.7%. El mercado cae cuando BSI está comprimido.
**Estado:** CANDIDATO. Evaluar edge como señal de SHORT (no entry long). Si se crea, tipo=exit.

### C15 — CREDIT (0_0_x) → candidato `credit_capitulation`
**Datos:** 24 pivotes. WR 41.7%, SPY -0.22%. **Diamante §3.3 (N<21).**
**Corrección:** D2=0 = **FAST_CRUSH**, velocidad más NEGATIVA (acelerando a la baja), NO "desacelerando". CREDIT en piso + cayendo rápido = máximo pánico crediticio.
**Estado:** CANDIDATO diamante. N insuficiente para inferencia robusta.

### C16 — VIX D3=4 + D1≤3 → candidato `vix_instability_warning`
**Datos:** 27 eventos. WR 25.9%, SPY -0.91%. **Buena señal de EXIT.**
**Corrección:** tipo=exit (warning), no entry. VIX inestable sin pánico confirmado = protegerse, no comprar.
**Estado:** CANDIDATO más sólido del grupo. Evaluar con `evaluar_condicion_booleana()`.

---

## 🟠 P1 — Puente Dimensional y Fact Store

### C17 — Variantes D2 para top-10 señales D1-only
**Archivo:** `arnes/señales.py`
**Datos:** Las V2 demostraron edge (capitulacion_v2, euforia_v2, vix_crisis_spike_v2). Escalar a `credit_stress`+D2, `pcr_put_panic`+D2, etc.
**Nota:** D2=2 es AMBIGUO — NO usar como filtro. Usar solo D2 extremos (0,1,3,4).

### C18 — Cruzar evaluadores con Fact Store (alignment score)
**Archivo:** `evaluador_general.py` o nuevo módulo
**Propuesta:** Para cada state_key activo al disparar, comparar `p_bull` del Fact Store con hit rate observado.

---

## ⚪ P2 — Refinamientos

### C19 — Score separado por categoría en ranking
**Archivo:** `consolidar_ranking.py`
**Fix:** No comparar filtros de fondo (sorpresa_total, fire rate 32%) con señales tácticas (cadencia 400v).

### C20 — Persistencia temporal del régimen favorable
**Archivo:** `evaluador_general.py`
**Fix:** Agregar métrica de vida media del régimen favorable post-señal.

---

## ORDEN DE EJECUCIÓN CORREGIDO

| # | Prioridad | Corrección | Archivo | Esfuerzo | Depende de |
|:-:|:---------:|:-----------|:--------|:--------:|:-----------|
| **1** | 🔴 P0 | **C11: Framework conclusiones dinámicas** | `ejercicios_regimen.py` | 20 min | — |
| **2** | 🔴 P0 | C5: CI95 Clopper-Pearson en 6 ejercicios | `ejercicios_regimen.py` | 15 min | C11 |
| **3** | 🔴 P0 | **E8: BH/DSR/Bootstrap en ranking y E1-E6** | `consolidar_ranking.py` | 15 min | — |
| **4** | 🔴 P0 | C7: p-values + Bonferroni en E1-E6 | `ejercicios_regimen.py` | 15 min | C5 |
| **5** | 🔴 P0 | C6: BH + Bonferroni en ranking maestro | `consolidar_ranking.py` | 10 min | E8 |
| **6** | 🟡 P1 | C9: Time-stop en first-passage | `evaluador_general.py` | 20 min | — |
| **7** | 🟡 P1 | E7 Fase 1: Taxonomía VIX+BSI+CREDIT | Nuevo script | 45 min | — |
| **8** | 🟡 P1 | **C16: Evaluar VIX D3=4 como warning exit** | `evaluador_general.py` | 15 min | — |
| **9** | 🟠 P1 | C17: Variantes D2 para top-10 señales | `arnes/señales.py` | 30 min | — |
| **10** | 🟠 P1 | C18: Fact Store alignment score | `evaluador_general.py` | 30 min | — |
| **11** | ⚪ P2 | C12: Documentar eras en E3 | `ejercicios_regimen.py` | 5 min | C11 |
| **12** | ⚪ P2 | C19-C20: Refinamientos ranking y persistencia | 2 archivos | 30 min | C6 |
| **13** | 🔴 P0 | **Resolver bloqueante C8:** z-scores en lake | `backend/scripts/_lib/` | 30 min | — |
| — | ❌ | C10: Renombrar perfil_3d → **RECHAZADO** | — | — | — |

**Nota:** C1-C4 quedan **absorbidos por C11**. No requieren implementación separada.

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. Conclusiones dinámicas (C11) verificadas
cd /root/botero-trade
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
import json
ej = json.load(open('data/research/signals/ejercicios_regimen_e1_e6.json'))
for e in ['E1','E2','E3','E4','E5','E6']:
    r = ej[e]
    # Verificar que NO contenga texto hardcoded
    assert '76%' not in r.get('conclusion',''), f'{e} hardcoded'
    assert '5 barras' not in r.get('conclusion',''), f'{e} hardcoded'
    assert 'INVarianza' not in r.get('conclusion',''), f'{e} conclusion incorrecta'
"

# 2. CI95 presentes
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
ej = json.load(open('data/research/signals/ejercicios_regimen_e1_e6.json'))
for e_name, e_data in ej.items():
    has_ci = any('ci95' in str(k).lower() or 'ci_lower' in str(k) for k in e_data if isinstance(e_data[k], dict))
    print(f'{e_name}: CI95 {\"✅\" if has_ci else \"❌\"}')
"

# 3. Bonferroni + BH en ranking
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
import json
rank = json.load(open('data/research/signals/ranking_maestro.json'))['ranking']
print(f'Bonferroni: {\"✅\" if \"p_bonferroni\" in rank[0] else \"❌\"}')
print(f'BH: {\"✅\" if \"p_BH\" in rank[0] else \"❌\"}')
"

# 4. Time-stop implementado
grep -n "max_barras\|timeout" research/01_señales_entry_exit/evaluador_general.py | head -5

# 5. Tests pasan
backend/.venv/bin/python3 -m pytest tests/test_arnes_timing.py backend/modules/entry_decision/tests/test_compositor.py -v

# 6. Candidatos evaluados (C13-C16)
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
from evaluador_general import evaluar_condicion_booleana, cargar_entorno_evaluacion
cargar_entorno_evaluacion()
for cand in ['skew_complacencia', 'bsi_compression', 'credit_capitulation', 'vix_instability_warning']:
    print(f'Candidato {cand}: pendiente de evaluacion con medir()')
"
```