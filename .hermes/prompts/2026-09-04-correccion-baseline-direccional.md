# PROMPT: CORRECCIÓN del Baseline Direccional-Condicionado en la Evaluación OOS del Comité METAR

**Fecha:** 04-Sep-2026 (v3 — consolidado y corregido tras auditoría de Opus)
**Objetivo:** Corregir el error sistemático que hace que TODAS las estaciones del comité "fallen" el OOS. Diagnóstico: el cálculo del baseline mezcla predicciones ALZA y BAJA contra un único baseline global mayoritario, forzando el accuracy de casi todas las estaciones a ≈0.536 (el % mayoritario del mercado). Esto enmascara el edge real. El fix separa la evaluación POR dirección con su baseline condicionado (principio de López de Prado: probar contra la clase mayoritaria que la señal efectivamente predice).

**Cadena de auditorías:** Auditoría OOS → Implementación Canónica → Diagnóstico S0-S3 → Auto-Auditoría Opus → **Este prompt (v3 consolidado)**.

---

## Diagnóstico confirmado (evidencia empírica)

En `comite_metar/salidas/reglas_invalidadas.json`, TODAS las 11 estaciones quedan invalidadas con accuracy agrupado muy cerca del baseline:

| Estación | accuracy | baseline | edge | Observación |
|:---------|:---------|:---------|:-----|:------------|
| vix | 0.532 | 0.536 | -0.004 | accuracy ≈ baseline → forzado |
| credit | 0.535 | 0.536 | -0.001 | idem |
| rotation | **0.554** | 0.536 | **+0.018** | **SUPERÓ baseline** (pero se invalida por umbral) |
| skew | 0.465 | 0.536 | -0.071 | predice BAJA 155/185 |

**El patrón (accuracy ≈0.47-0.55 ≈ baseline 0.536) indica que el baseline global fuerza el resultado**, no que haya ausencia real de edge en las 11.

### El error técnico (en `modelador.py` `metricas()` y `walk_forward()` tally)
1. El `tally_est` acumula `hits` y `n` **mezclando** predicciones ALZA y BAJA (`hits_est[y] = hits si hit_primary`, sin separar por dirección).
2. Luego `reglas_por_estacion` llama `MOD.metricas(hits, n, baseline)` con **UN SOLO baseline** = el mayoritario global del test (p.ej. 0.633 en test, 0.536 en todo el lake).
3. **Consecuencia:** una estación que predice BAJA en un mercado que baja el 53% obtiene accuracy ≈0.53, pero se compara contra 0.536 → edge ≈ 0 → invalidada. El baseline correcto debería ser el de la clase que la estación predice cuando la predice.

### Por qué `rotation` es la prueba del bug
rotation predice balanceado (138 ALZA / 95 BAJA) y su accuracy 0.554 supera el baseline 0.536 — pero el umbral `PASO_EDGE=0.03` y el p-value lo invalidan. Con un baseline direccional-condicionado, su edge real emergería.

---

## Corrección a implementar

### 1. Tally direccional en `walk_forward` (modelador.py)
El `tally_est` debe acumular **por dirección** para cada estación:
```python
taccum = tally_est.setdefault(est, {
    "n_alza":0, "hits_alza":0, "n_baja":0, "hits_baja":0,  # por direccion
    "dirs": {"ALZA":0,"BAJA":0}, "n":0, "hits":0
})
# al puntuar con ground_truth opcion C zz25:
if sd == "ALZA":
    taccum["n_alza"] += 1
    if hit: taccum["hits_alza"] += 1
elif sd == "BAJA":
    taccum["n_baja"] += 1
    if hit: taccum["hits_baja"] += 1
# mantener n/hits totales para compatibilidad
```

### 2. Baselines por dirección (en `validar_oos` y `reglas_por_estacion`)
- `baseline_alza = P(ground-truth ALZA)` = fracción de episodios resueltos cuyo ground-truth Opción C es ALZA, **calculada sobre el conjunto bajo evaluación** (lake para scoring global, test para OOS). NO es una propiedad de la estación: es una propiedad del mercado en esa escala.
- `baseline_baja = 1 - baseline_alza` (de los resueltos).
- **Referencia actual:** `run_comite.py` L58-67, función `baseline_pivote()` calcula un solo baseline global → hay que bifurcarla por dirección.

### 3. Métricas direccional-condicionadas en `reglas_por_estacion` (run_comite.py)
**Referencia actual:** `run_comite.py` L71-111, función `reglas_por_estacion()` llama `MOD.metricas(hits, n, baseline)` con UN SOLO baseline → reemplazar por edge direccional.

En vez de `metricas(hits, n, baseline_global)`, computar el edge **por dirección y combinar** con **Edge Aditivo** (puntos porcentuales, NO lift relativo):
```python
def edge_direccional(t, baseline_alza, baseline_baja):
    n_a, h_a = t["n_alza"], t["hits_alza"]
    n_b, h_b = t["n_baja"], t["hits_baja"]
    
    # Si N=0 para una dirección → None (NO 1.0, que inventaría un 100% ficticio)
    acc_a = h_a / n_a if n_a else None
    acc_b = h_b / n_b if n_b else None
    
    # Edge ADITIVO en pp (no lift relativo), coherente con PASO_EDGE = 0.03
    edge_a = (acc_a - baseline_alza) if acc_a is not None else None
    edge_b = (acc_b - baseline_baja) if acc_b is not None else None
    
    # Baseline condicionado combinado (ponderado por N de cada dirección)
    n_tot = n_a + n_b
    if n_tot > 0:
        base_cond = (n_a * baseline_alza + n_b * baseline_baja) / n_tot
        acc_tot = (h_a + h_b) / n_tot
        edge_comb = acc_tot - base_cond  # Edge aditivo combinado
    else:
        base_cond = edge_comb = None
    
    return {
        "edge_combinado": edge_comb, "baseline_condicionado": base_cond,
        "edge_alza": edge_a, "edge_baja": edge_b,
        "acc_alza": acc_a, "acc_baja": acc_b,
        "n_alza": n_a, "n_baja": n_b,
    }
```
> ⚠ **Errores corregidos vs v2:** (1) `acc = None` cuando $N=0$, NO `1.0` (un 100% ficticio distorsiona el edge combinado). (2) Edge **aditivo** ($Acc - Base$), NO lift relativo ($(Acc-Base)/Base$). El umbral `PASO_EDGE = 0.03` es en pp aditivos; mezclar con lift relativo es dimensionalmente inconsistente.

- **Clasificar VALIDADA** si el edge (direccional-condicionado) > 0 con significancia (tras FDR), es decir, si la estación supera el baseline DE LA CLASE QUE PREDICE (no el mayoritario global).
- Reportar `acc_alza/acc_baja` y `edge_alza/edge_baja` (en pp) por separado en `reglas_invalidadas.json`/`reglas_validadas.json`.

### 4. p-value por dirección (López de Prado)
- `p_greater_alza = binomtest(hits_alza, n_alza, baseline_alza, alternative="greater")`.
- `p_greater_baja = binomtest(hits_baja, n_baja, baseline_baja, alternative="greater")`.
- La estación se considera con edge direccional si al menos UNA dirección supera su baseline con p < umbral (OMEGA). (Ya que cada dirección es una apuesta distinta: predecir ALZA cuando alzas y predecir BAJA cuando bajas son dos capacidades diferentes.)

**IMPORTANTE — comparación conceptual correcta:**
Una estación que predice BAJA no debe compararse contra `baseline_alza` ni contra el promedio; debe compararse contra `baseline_baja` (lo que rendiría "siempre predecir BAJA"). Así el edge es honesto: mide si SABER CUÁNDO predecir BAJA supera a nunca parar de predecir BAJA.

### 5. Confluencia del comité
Aplicar el mismo principio al `modelo_confluencia` test: desglosar el accuracy del comité por dirección (ALZA vs BAJA) con sus baselines propios (`baseline_alza`, `baseline_baja`), y reportar `edge_alza`/`edge_baja` y `p_greater_alza`/`p_greater_baja`. Mantener los reportes tri-escala (zz25/zz50/zz75) y el embargo (N_indep).

### 6. MÉTRICAS POR CADA ESCALA DE LA TRIADA (zz25/zz50/zz75) — OBLIGATORIO
**El desglose direccional-condicionado NO se aplica solo a zz25.** Debe computarse para **CADA escala de la triada** por separado, porque cada escala es una apuesta distinta (táctica 2.5% vs intermedia 5% vs estructural 7.5%) y una estación puede tener edge en una y no en otra (como el ranking maestro con su escala_optima).

Para cada `zz ∈ {zz25, zz50, zz75}`:
- `baseline_alza_zz` y `baseline_baja_zz` = fracción de ground-truth Opción C ALZA/BAJA en ESA escala (del test o del conjunto relevante).
- `tally` direccional por estación en esa escala: `n_alza_zz`, `hits_alza_zz`, `n_baja_zz`, `hits_baja_zz`.
- Por estación y escala, reportar: `acc_alza_zz`, `acc_baja_zz`, `edge_alza_zz`, `edge_baja_zz` (aditivos en pp, NO lift relativo — coherente con §3), `p_greater_alza_zz`, `p_greater_baja_zz` (binomtest de cada dirección contra SU baseline en ESA escala).
- **Clasificación por estación por escala** (opcional pero recomendado, tipo ranking maestro): la estación se valida en la escala donde tenga edge direccional significativo. Ej. "rotation tiene edge en zz50 (no en zz25)".

**Estructura de salida en `reglas_validadas.json`/`reglas_invalidadas.json`:** un dict por estación con la métrica direccional-condicionada de CADA escala:
```json
{
  "estacion": "rotation",
  "por_escala": {
    "zz25": {"acc_alza":0.52,"acc_baja":0.55,"edge_alza":...,"edge_baja":...,"p_alza":...,"p_baja":...,"n_alza":138,"n_baja":95},
    "zz50": {...},
    "zz75": {...}
  },
  "escala_optima": "zz50",
  "status": "VALIDADA" | "INVALIDADA"
}
```

Y en `modelo_confluencia.json`, el desglose por dirección y por escala (zz25/zz50/zz75) con sus baselines propios.

---

**Entregables (§1-6):** (a) archivos modificados, (b) tabla por estación con accuracy/edge/p direccional-condicionado, (c) qué estaciones SÍ tienen edge direccional real y cuáles no (ahora sí con conclusión válida), (d) modelo confluencia desglosado por dirección.

**Principios:** Dato mata relato. Probar contra la clase mayoritaria que la señal predice, no contra un baseline global (López de Prado). El baseline global mezclado enmascara el edge — corrígelo.

> **Criterios de aceptación completos:** ver §final "Verificación de aceptación (INDEPENDIENTE del número pre-fijado)" al final de este documento — incluye FDR, CI95, N mínimo y smoke test.

---

### 6.5 RESIDUO H5: `_evidencia()` SIGUE LEYENDO `ranking_maestro.json` (LOOKAHEAD PARCIAL)
**Referencia actual:** `_agente_base.py` L126-154, función `_evidencia()` lee `ranking_maestro.json` para extraer `score_compuesto`, `p_BH`, `ev_lake`, `hit_lake`, etc. Estos valores fueron calculados sobre el **lake completo (1993-2026)** y se usan para ordenar la evidencia (`evi_ord`, L182).

**Estado actual post-corrección canónica:** la convicción ya NO depende de `_evidencia()` (se basa puramente en D1xD2xD3 + overflow, L185-199). Sin embargo, `_evidencia()` se sigue invocando y sus valores se incluyen en el campo `evidencia` del JSON de salida (L226). Esto tiene **2 implicaciones**:
1. **No afecta la señal direccional ni la convicción** (la implementación canónica ya desacopló esto correctamente).
2. **Sí contamina la descripción narrativa** (`_resumen()`, L229-) y el campo `evidencia` del registro forense con datos del futuro.

**Decisión recomendada:** NO es bloqueante para la ejecución de Fases 1-2 (el edge operacional no depende de `_evidencia()`). Pero en una fase posterior (limpieza), `_evidencia()` debe o bien recibir un corte temporal, o bien ser eliminada del JSON de salida del walk-forward OOS.

---

### 7. CONEXIÓN AL FACT STORE — CON ADVERTENCIA DE LOOKAHEAD (BLOQUEANTE, revisado tras auditoría de Opus)
**El análisis S0-S3 de Gemini (verificado) demostró que el edge real del motor está donde el agente NO lo está leyendo** (heurística `_direccion_spy` ≈ baseline; Fact Store/`P_bull` → edge real). **PERO la auditoría de Opus detectó un fallo crítico que DEBEMOS respetar:**

🔴 **LOS FACT STORES ACTUALES CONTIENEN LOOKAHEAD (datos futuros).** Fueron generados (`generate_all_150_state_fact_stores.py`) sobre TODAS las piernas del Vault **1993 → ago 2026**, sin corte temporal. Si el comité evalúa un episodio de 2008 y consulta el fact store, el `P_bull` de ese estado "sabe" qué pasó de 2009 a 2026 → **18 años de futuro en la señal del agente.** Esto es exactamente la fuga H5 que ya corregimos en `ranking_maestro.json`. Conectar al fact store tal cual REINTRODUCE la fuga y el OOS queda invalidado.

**Enmienda obligatoria (elegir UNA):**
- **Alternativa A — Fact Stores temporalmente particionados (expanding window):** re-ejecutar el generador con un corte `end_date` (ej. `*_fact_store_pre2020.json` con datos `< 2020`), usar ese archivo en el arnés OOS del comité, y mantener los completos solo para producción. **Ojo:** el particionado puede reducir N de estados raros (diamantes §3.3 de cola) → más estados ANECDOTAL en test.
- **Alternativa B — Heurística causal corregida (SIN fact store en el OOS):** mantener `_direccion_spy` como regla determinista causal en `t` (D1/D2/D3 + overflow), pero **corrigiendo sus reglas** para alinearlas con la física real de los indicadores. Las correcciones del evaluador (baseline direccional, OBSERVAR peso 0) se aplican igualmente y revelan el edge real sin riesgo de lookahead ni pérdida de N por particionado.

> **Ordenación recomendada (DECIDIDA):** implementar primero las **Fases 1-2 (evaluador + curador)** con la heurística causal corregida = **Alternativa B**. Esto revela el edge direccional real OOS SIN fuga y SIN perder states por particionado. **Solo si tras Fases 1-2 el edge es insuficiente**, explorar la **Alternativa A** (fact store particionado) como fase opcional, sabiendo que reducirá N. **NO conectar al fact store completo (con lookahead) jamás en el OOS.**

**Esquema del fact store (válido solo si se particiona):** `states` keyed por `d1__d2__d3` con `zz25/zz50/zz75` → `p_bull`, `p_bear`, `ev_net`, `n_raw`, `n_independent`, `ci95`, `p_bh`, `grade`. **Baselines POR ESCALA** (rotation: `{zz25:0.558, zz50:0.609, zz75:0.670}`), NO umbral global único — el agente compara `p_bull_zz` contra el baseline de SU escala. **N mínimo por state:** si `n_independent < 5` → `ANECDOTAL` → `NEUTRAL`/`OBSERVAR`.

### 8. NO PENALIZAR OBSERVAR COMO PÉRDIDA
Cuando el agente recomendó `accion == "OBSERVAR"` (convicción BAJA, ruido, o sin señal clara), el evaluador NO debe contarlo como una apuesta cuya falla resta accuracy. **Separar:**
- **edge operacional** = accuracy sobre las apuestas donde el agente recomendó `ENTRADA`/`COBERTURA` (señal accionable).
- Las lecturas `OBSERVAR` se excluyen del numerador y denominador del edge operacional (o se reportan aparte como "cobertura de señal"), de forma que el accuracy refleje solo las decisiones que el agente realmente recomienda operar.

**Dos puntos de implementación — uno en el tally, otro en el curador:**

**8a. En el tally (`modelador.py`, L204-249):** Actualmente, el tally acumula TODA lectura con dirección ALZA o BAJA (L213: `if sd not in ("ALZA", "BAJA"): continue`). Para separar operacional de bruto, el tally debe consultar `lec.get("accion")` y `lec.get("conviccion")` y acumular en contadores separados: `n_operacional/hits_operacional` (solo ENTRADA/COBERTURA) y `n_bruto/hits_bruto` (todas las direccionales).

**8b. En el curador `fuse()` (`curador.py`, L98-198):** Actualmente, toda lectura con dirección ALZA o BAJA aporta su peso al `flujo_neto` (L153-156: `anti[dir_] += w`), incluyendo las de `accion == "OBSERVAR"` con peso `BAJA=1`. **Enmienda:** los agentes con `accion == "OBSERVAR"` aportan **peso 0** al flujo neto (se excluyen del voto). Además, `flujo_neto` debe normalizarse por el número de agentes que votaron (no por 11 fijos). Implementar en la sección L133-156 de `curador.py`:
```python
# En el bucle de fuse(), después de L141:
w = conviccion_peso(conv)
accion = lec.get("accion", "OBSERVAR")
if accion == "OBSERVAR" or dir_ == "NEUTRAL":
    w_voto = 0  # no vota
else:
    w_voto = w
# usar w_voto (no w) para anti[dir_] += w_voto
```

**Estructura de salida:** por estación y escala, reportar `edge_operacional` (solo ENTRADA/COBERTURA) SEPARADO de `edge_bruto` (todas las direccionales, incl. OBSERVAR), y `n_operacional` vs `n_bruto`. El análisis S1-S3 de Gemini ya mostró que filtrar por convicción (S1→S3) sube el edge — esto codifica ese hallazgo.

**Entregables adicionales:** (e) tabla S0/S2/S3 replicada tras el fix (heurística vs Fact Store, por estación y escala) para confirmar que conectar al Fact Store revela el edge, (f) edges con CI95 y N_indep.

---

### 9. BLINDAJES DE RIGOR (OBLIGATORIOS — no reintroducir falsos edges)
**Los edges del análisis S2/S3 (especialmente los de n~30) son PROMETEDORES PERO NO PROBADOS. El plan/prompt debe protegerse contra la reintroducción de falsos descubrimientos con estos 3 blindajes:**

**9.1 Umbral de significancia ESTÁNDAR (p < 0.05), no laxo.**
- NO usar p < 0.15 como umbral de validación (es débil y calibrado para que "todo pase"). Usar **p < 0.05** (convención estándar) para `p_greater` de la dirección validada.
- **NO pre-anunciar el número de estaciones que deben validarse.** El resultado debe emerger del dato, no ser un objetivo pre-fijado ("que salgan 8/11" condiciona el análisis). Reportar cuántas resultan validadas después de aplicar el umbral honesto.

**9.2 Control de selección múltiple en `escala_optima` (FDR / Bonferroni).**
- Elegir para cada estación la `escala_optima` con el mejor p entre 3 escalas equivale a **11 estaciones × 3 escalas = 33 comparaciones** → selección múltiple que infla el edge si no se controla.
- **Aplicar control de hipótesis múltiples** sobre el mejor-p por estación (p.ej. **Benjamini-Hochberg FDR q=0.05** sobre las 33 pruebas, o **Bonferroni**), y reportar el p-value **ajustado** (p_BH) de la escala_optima, no el p crudo.
- Solo una estación se VALIDA si su `p_BH(escala_optima) < 0.05` (o el p ajustado por selección), no el p crudo sin corregir.

**9.3 N mínimo defensivo (anti-ruido de n~30) — valores concretos fijados.**
- **Para emitir señal (no ANECDOTAL):** `n_independent ≥ 5` en el state del fact store. Si `n_independent < 5` → `ANECDOTAL` → `NEUTRAL`/`OBSERVAR` (nunca operar un state sin respaldo muestral).
- **Para convicción ALTA/operación:** `n_independent ≥ 10` (y `N_operacional ≥ 50` o `N_indep ≥ 30` tras embargo en la agregación OOS).
- **Para VALIDAR una estación en OOS:** `N_operacional ≥ 50` (o `N_indep ≥ 30` tras embargo). Un edge sobre n=30-31 (rotation 71%, vvix 70%) tiene **CI95 ancho** y NO se confirma como edge sin ese N mínimo.
- Reportar el **CI95 Clopper-Pearson** de cada accuracy; si el límite inferior del CI ≤ baseline, no declarar edge aunque el p crudo sea <0.05.

**Nota de interpretación (López de Prado):** el edge direccional se valida si la estación supera el baseline DE LA CLASE QUE PREDICE, con significancia estándar (p<0.05), tras control de selección (FDR) y con N mínimo. Un edge "grande" sobre n pequeños es —aún— evidencia débil; se reporta como prometedor, NO como validado.

---

### 10. OMISIONES ESTRUCTURALES DE OPUS (incorporadas)

**10.1 El curador `fuse()` debe adaptarse (omisión estructural 1 de Opus).**
El plan modifica `_agente_base.py` (dirección), `modelador.py` (evaluación) y `run_comite.py` (clasificación), pero `curador.py` `fuse()` queda desacoplado. Si los agentes ahora emiten más `NEUTRAL`/`OBSERVAR` (donde antes BAJA), el `flujo_neto` y el umbral `T` de `validar_oos` se desestabilizan. **Enmienda:**
- Los agentes con `accion == "OBSERVAR"` y `conviccion == "BAJA"` aportan **peso 0** al `flujo_neto` (se excluyen del voto, no votan NEUTRAL).
- El `flujo_neto` se **normaliza por el número de agentes que efectivamente votaron** (no por 11 fijos).

**10.2 Separar tabla in-sample vs tabla OOS (omisión estructural 2 de Opus).**
Los edges S2/S3 reportados en el análisis de Gemini se computaron sobre **los 752 episodios del lake completo (1993-2026)**, NO sobre el test OOS (≥ 2023). Son "potencial del motor", NO resultado OOS. **Enmienda:**
- **Tabla in-sample:** los edges S2/S3 actuales, presentados como "potencial del motor en producción" y "upper bound".
- **Tabla OOS (test ≥ 2023):** re-ejecutar la simulación sobre los 91 episodios de test, con fact stores cortados a `< 2020` (si se elige Alternativa A), reportando N_indep, CI95 y p ajustado.

---

## ORDEN DE EJECUCIÓN (de la auditoría de Opus, incorporado)
- **Fase 0 (si se elige A):** re-ejecutar `regenerar_fact_stores.py` con `--end_date 2020-01-01` → `*_fact_store_pre2020.json` (solo para OOS; producción usa los completos).
- **Fase 1:** corregir `modelador.py` (tally direccional tri-escala, `metricas_direccionales` con Baseline_condicionado) y `run_comite.py` (reglas por escala_optima).
- **Fase 2:** corregir `curador.py` `fuse()` (OBSERVAR peso 0, normalizar por votantes).
- **Fase 3 (opcional, solo si A):** conectar `_agente_base.py` al fact store particionado. Si NO hay fact store particionado, mantener `_direccion_spy` corregida (Alternativa B).
- **Fase 4:** re-ejecutar `run_comite.py` end-to-end; reportar tabla OOS separada de in-sample, con edges direccionales, N_indep, CI95, p ajustado.

---

## MAPA DE CÓDIGO: REFERENCIAS EXACTAS AL CODEBASE ACTUAL

Para que el agente ejecutor sepa exactamente QUÉ líneas tocar sin exploración:

| Componente | Archivo | Líneas | Qué hay actualmente | Qué debe cambiar |
|:---|:---|:---:|:---|:---|
| **Tally por estación** | `modelador.py` | L236-249 | `{hits, n, contra, dirs, hits_zz50, hits_zz75}` | Añadir `n_alza, hits_alza, n_baja, hits_baja` por escala; añadir `n_operacional, hits_operacional` |
| **Métricas globales** | `modelador.py` | L145-165 | `metricas(hits, total, baseline)` usa lift relativo | Crear `metricas_direccionales()` con edge aditivo |
| **Baselines** | `run_comite.py` | L58-67 | `baseline_pivote()` retorna UN baseline | Bifurcar en `baseline_alza` + `baseline_baja` por escala |
| **Reglas por estación** | `run_comite.py` | L71-111 | `reglas_por_estacion(tally, baseline)` compara vs baseline global | Reescribir con `edge_direccional()` + FDR + CI95 |
| **Curador fuse()** | `curador.py` | L133-156 | OBSERVAR vota con peso `BAJA=1` | OBSERVAR → peso 0; normalizar flujo por votantes |
| **Convicción agente** | `_agente_base.py` | L185-199 | Puramente causal (D1xD2xD3 + overflow) | **NO TOCAR** (correcto desde walkthrough canónico) |
| **_evidencia()** | `_agente_base.py` | L126-154 | Lee `ranking_maestro.json` (lookahead) | **NO TOCAR** en Fases 1-2 (no afecta señal/convicción; limpieza posterior) |
| **Salidas JSON** | `run_comite.py` | L164-198 | 5 archivos en `comite_metar/salidas/` | Enriquecer con desglose direccional/tri-escala/CI95/FDR |

---

## Verificación de aceptación (INDEPENDIENTE del número pre-fijado)
1. Reportar para cada estación y CADA escala (zz25/zz50/zz75): `acc_alza_zz/acc_baja_zz`, `edge_alza/edge_baja` (aditivos en pp), `CI95 Clopper-Pearson`, `p_greater_alza_zz/p_greater_baja_zz`, `n_alza_zz/n_baja_zz`, `n_operacional` vs `n_bruto`.

2. **Validación solo con p<0.05 ajustado por FDR (BH) sobre la escala_optima + N_operacional ≥ 50 (o N_indep ≥ 30).** Una estación con p crudo <0.05 pero p_BH ≥0.05 NO se valida.

3. **La estación se invalida** si NINGUNA dirección supera su baseline condicionado con significancia estándar tras corrección múltiple y N mínimo. El NÚMERO de validadas NO está pre-fijado — es el dato el que lo decide.

4. `OBSERVAR` NO penaliza: `edge_operacional` (solo ENTRADA/COBERTURA) separado de `edge_bruto`, con `n_operacional`/`n_bruto`.

5. El modelo confluencia desglosa edge y p por dirección Y por escala (zz25/zz50/zz75), con N_nominal vs N_indep (embargo) y p ajustado.

6. Re-ejecutar `run_comite.py` completo sin errores.

7. **Smoke test de regresión:** `pytest tests/ -x` debe pasar (11 tests). Verificar que `sin_lookahead` en `resumen.json` sigue True.