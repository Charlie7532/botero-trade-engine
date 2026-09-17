# PROMPT: CORRECCIÓN del OOS del Comité Walk-Forward — alinear a Opción C (fix `_norm_dir` + ground-truth + baseline + episodios + fuga temporal)

**Fecha:** 04-Sep-2026
**Objetivo:** Corregir la metodología de validación Out-of-Sample del Comité METAR Walk-Forward. El OOS actual **NO es válido** (verificado): usa `pivote_pred` con argmax/argmin de cierres que inventa un mercado 70% bajista (real: 52% alcista con Opción C), falsa significancia (p vs 0.5 ignorando baseline real), vacía el test (episodio monstruo), y tiene fuga temporal. El fix debe alinear el OOS a la metrología canónica del proyecto (Opción C: first-passage OHLC), al estándar OOS del proyecto (PBO/Clopper-Pearson), y a un de-clustering correcto por estación. **Esto NO es auditar (ya auditado) — es IMPLEMENTAR las correcciones y verificar con ejecución real.**

**Archivos a modificar/auditar:**
- `comite_metar/curador/modelador.py` (validar_oos, walk_forward, pivote_pred, p_binario, metricas)
- `comite_metar/curador/curador.py` (fuse, _norm_dir)
- `comite_metar/run_comite.py` (orquestador)
- `comite_metar/scripts/episodios.py` (de-clustering)
- `comite_metar/agentes/_agente_base.py` (_evidencia, fuga temporal)
- `comite_metar/salidas/*.json` (re-generar)

**Contexto — marco canónico del proyecto (documentar y confirmar que el OOS lo cumple):**
- **Metrología Opción C**: first-passage OHLC intrabar, barrera ±scale, SIN time-stop fijo. El movimiento termina por cambio de régimen/barrera, no en velas fijas.
- **Muestra válida**: ninguna estación/senal existe antes de su `fecha_inicio_valida`; muestras válidas desde inception, sin datos pre-inception ni pre-SPY (1993).
- **Estándar OOS del proyecto (del plan maestro de APIs, `.hermes/plans/2026-08-30_alcance-apis-inteligencia-metar.md`)**: el proyecto ya valida su inteligencia con **PBO (Deflated Sharpe), IC in-sample/OOS, CI95 Clopper-Pearson (Protocolo §3.3, N<21 diamante), y walk-forward OOS con edge**. Este es el BAREMO de referencia contra el que el OOS del comité debe auditarse — ¿lo cumple? Verificar las entradas I1 (Cascade: PBO 0%, IC IS/OOS), I5 (Rareza: Clopper-Pearson), I7 (Señales: walk-forward OOS con edge).
- **Evaluador GENERAL continuo** como fuente de verdad (episodios continuos, no solo-pivote).
- **De-clustering = credibilidad, no exclusión** (§3.3). Rareza = riqueza (N<21 = diamante, reportar tasa + CI95).
- **Control de falsos descubrimientos**: la lección reciente: el comité dio accuracy alta (0.857) pero **lift NEGATIVO vs baseline mayoritario (0.875)** — no añade edge sobre "siempre BAJA". El OOS debe probar contra el nulo correcto (no solo 50%).
- **Dato mata relato. La verdad habla.**

**LO QUE DEBES AUDITAR (con datos y ejecución real, no solo leer):**

### 1. ¿El OOS está VIGENTE con nuestra metrología?
Verificar y documentar si el modelador usa:
- `pivote_pred`: ¿debe ser first-passage OHLC (Opción C) o un `argmax/argmin` de cierres? **El pivote real cómo se define** — el código usa `spy_close` argmax/argmin en ventana de 80 barras. ¿Es consistente con nuestra definición de movimiento por cambio de barrera/regimen? (Si no, es una discrepancia metodológica.)
- `horizonte=80` fijo: ¿viola Opción C (sin time-stop fijo)? El horizonte del pivote debe ser el mismo criterio (primera barrera alcanzada), no una ventana de cierres fija.
- **Baseline**: el código compara vs nulo 50% y vs baseline mayoritario. Pero ¿el baseline es sobre la distribución REAL de pivotes (like 0.875 BAJA)? Verificar que la "accuracy" y su significancia se calculen contra el nulo correcto, no solo binom 50%.

### 2. El arreglo `_norm_dir`
- Verificar que `_norm_dir` (ALCISTA/BAJISTA -> ALZA/BAJA) esté correctamente aplicado en `fuse` y en `walk_forward`.
- Verificar que NO sobre-normalize ni rompa otros casos (NEUTRAL vacío mantiene).
- Correr el comité y confirmar que las lecturas/fluy_numero ahora se llenan.

### 3. Otras fallas / robustez
- Sin lookahead: ¿hay alguna fuga en `pivote_pred` (usa post-t solo para scoring, OK) pero... el `flujo_numero` o el tune de `T` en train usa¿? episodios test en train? Verificar superposición temporal (¿corte train<2020/test>=2023 correcto?).
- ¿`validar_oos` tunea `T` sobre test implícitamente? (deflated correcto?)
- ¿Coverage mínimo 25% correcto? ¿`baseline` se computa sobre test (correcto) pero el lift se reporta bien?
- De-clustering: se procesan los 730 episodios, pero ¿hay doble conteo (episodios del mismo régimen correlacionados)? §3.3 exige no excluir, pero el test deberia considerar independencia temporal.

### 4. Reproducibilidad
- Ejecutar `backend/.venv/bin/python3 comite_metar/run_comite.py` y documentar el output real (pub cargar los artefactos si procede).

**ENTREGABLES:**
1. Dictamen: ¿el OOS está vigente con la metodología canónica? (differences)
2. Lista de acuerdos (fixes) necesarios con severidad: bloqueante / importante / menor.
3. Propuesta concreta de fix para que el OOS sea robust y conforme (pivote first-passage OHLC, baseline vs distribución real, independencia).
4. Verificación del `_norm_dir`.

**REFERENCIA: AUDITORÍA PREVIA (ya realizada por Gemini, en `audit_oos_comite.md` del brain Antigravity) — complementar esta auditoría, no repetirla desde cero:**
Hallazgos previos confirmados (H1-H7), con severidad:
- **H1 BLOQUEANTE** `pivote_pred` usa argmax/argmin en 80 barras de close (Δ=0) → inventa 70% BAJA en S&P secular alcista. Con Opción C (±2.5% OHLC) la distribución real es 52.3% ALZA / 47.5% BAJA. **Invalida el ground-truth.**
- **H2 BLOQUEANTE** p-value binomial contra 0.5 ignora baseline real (0.875) → p=0.00647 FALSO con lift negativo (-2%).
- **H3 BLOQUEANTE** `episodios.py` gap≤2 global → Episodio #714 de 745 barras (2022-2025) fusiona crédito+curva → **vació el test OOS de 2023-2025** (0 episodios 2023-2025, solo 16 tardíos).
- **H4 IMPORTANTE** autocorrelación test >90% (solapamiento), muestra no independiente.
- **H5 IMPORTANTE** fuga temporal: `Agente._evidencia()` usa `ranking_maestro.json` consolidado con TODO el lake (incl. datos futuros) → convicción contaminada OOS upstream.
- **H6 IMPORTANTE** estaciones invalidadas vs baseline falso 0.6986 (de pivote_pred sesgado).
- **H7 MENOR** vocabulario direcciones inconsistente (ALCISTA vs ALZA) — resuelto provisional por `_norm_dir`.

**EVIDENCIA EMPÍRICA VERIFICADA (4 artefactos de investigación, ejecutados — estos son los números REALES que ratifican la auditoría):**
Los 4 scripts están en el brain Antigravity `76affbfe-.../scratch/`: `investigar_pivotes.py`, `comparar_metrologias.py`, `evaluar_vs_opcion_c.py`, `evaluar_test_opc.py`. Output ejecutado:
1. **`comparar_metrologias.py`** (730 episodios):
   - `pivote_pred` actual: ALZA 220 (30.1%) / BAJA 510 (69.9%) → infla BAJA
   - Opción C ±2.5% (first-passage OHLC): ALZA 382 (52.3%) / BAJA 347 (47.5%), 1 sin resolver
   - Opción C ±5.0%: ALZA 443 (60.7%) / BAJA 286 (39.2%), 1 sin resolver
   → **`pivote_pred` invierte el sesgo del mercado** (dice 70% BAJA cuando el real es 52% ALZA).
2. **`evaluar_vs_opcion_c.py`**: debe arrojar baseline Opción C 2.5% ~0.524 y el accuracy del comité vs OpC, contrastado con el baseline sesgado 0.875.
3. **`evaluar_test_opc.py`**: en test 2023-2026, el accuracy del comité vs el `pivote_pred` sesgado ~73% cae a **~33% real vs Opción C** — el comité NO predice el mercado, solo el sesgo.

**DEBES EJECUTAR estos 4 scripts (y corregir las rutas si el módulo `comite_metar` importa) para confirmar los números antes de implementar el fix**, y reportarlos en el entregable.

**PROPUESTAS de la auditoría previa a implementar:**
1. `pivote_pred` → usar la verdad Opción C canónica (`first_passage` OHLC ±2.5/5/7.5% intrabar, sin time-stop; la que ya existe en el proyecto); multiescala (zz25/zz50/zz75).
2. `metricas()` → test binomial contra baseline real (no 0.5): p_null = baseline mayoritario.
3. `episodios.py` → de-clustering por estación/confluencia (no fusionar las 11 globalmente si una estación está en régimen continuo); límite longitud + re-disparo por cambio de state D1xD2xD3; o mapeo al Evaluador GENERAL continuo.
4. OOS estricto → `_evidencia()` solo con datos < corte (ranking/fichas pre-corte) o reglas físicas D1xD2xD3 sin condicionar al ranking global.

**OBJETIVO DE ESTE PROMPT:** ejecutar estas correcciones (pivote canónico, baseline correcto, de-clustering episodios, OOS sin fuga temporal), NO solo auditar. Verificar con ejecución real que el OOS sobre el criterio Opción C dé resultados honestos.

---

**⚠️ CORRECCIONES AL PROMPT (de la auditoría de Gemini `audit_prompt_oos_comite.md`) — INCORPORAR OBLIGATORIAMENTE:**

1. **ESCALA DEL GROUND-TRUTH (DECISIÓN DEL ARQUITECTO): TRIADA CANÓNICA.** El pivote real debe homologarse a **first-passage OHLC intrabar multiescala: zz25=±2.5%, zz50=±5.0%, zz75=±7.5%** (los highs/lows del lake `spy_high`/`spy_low`), sin time-stop fijo. Reportar el edge/accuracy POR cada escala (como el Evaluador General). No usar escala ATR aquí.

2. **PREISA CORREGIDA — el `baseline 0.875 BAJA` NO es la realidad del mercado.** Es un artefacto de `pivote_pred` (argmax de cierres sin barrera intrabar). El baseline REAL bajo Opción C canónica es: lake histórico **52.3% ALZA / 47.5% BAJA** (zz25), y en test ~60/40. El test binomial DEBE usar como nula la distribución real bajo Opción C (`p_null = baseline mayoritario real`), NO 0.875 ni 0.5.

3. **SIN FUGA EN EL TUNE DE `T`:** el barrido de `T∈[0,4]` en `validar_oos` itera solo sobre `train_rows (<2020)`, se congela y se aplica a test. NO hay fuga en T. La fuga real está en OTRA parte: **`_agente_base._evidencia()` consume `ranking_maestro.json` calculado sobre TODO el lake (1993-2026)** — cuando el agente evalúa un episodio de 2008 usa significancia BH calculada con datos de 2026 (FUTURO). Corregir: `_evidencia()` debe usar solo ranking/fichas pre-corte, o reglas físicas D1xD2xD3 sin condicionar al ranking global.

4. **AUTOCORRELACIÓN DE OUTCOMES:** en test los episodios contiguos se producen a 5-7 días de distancia con ventana forward de 80 barras → solapamiento >90%. NO son observaciones binomiales independientes. Aplicar purga/embargo temporal (López de Prado) o reportar n-efectivo ajustado por solapamiento.

5. **EPISODIO MONSTRUO en `episodios.py`:** el de-clustering global con `gap≤2` fusionó 3 años (2022-2025) en el Ep #714 (745 barras) porque yield_curve/credit estuvieron activas de forma persistente. Esto vació el test 2023-2025. Corregir: de-clustering **por estación/confluencia** (no fusionar las 11 globalmente si UNA estación de régimen lento está activa), con límite de longitud y re-disparo por cambio de state D1xD2xD3.

**VERIFICACIÓN DE ACEPTACIÓN (obligatoria):**
- `pivote_pred` reemplazado por first-passage OHLC de la triada; la distribución del ground-truth debe volver a ~52/48 ALZA/BAJA (no 30/70).
- `metricas()` usa `p_null = baseline real` bajo Opción C.
- `episodios.py` ya NO produce el Ep #714 de 745 barras; test 2023-2025 vuelve a tener episodios.
- `_evidencia()` no usa datos futuros → convicción calculada sin lookahead.
- Re-ejecutar y reportar el OOS honesto: accuracy vs Opción C por escala, con p-value vs baseline real, tras embargo.