# PROMPT: Implementación Canónica del OOS Walk-Forward del Comité METAR (Opción C + Desacoplo Episodios + Baseline Real + Temporalidad por Estación + Embargo)

**Fecha:** 04-Sep-2026
**Objetivo:** Implementar las correcciones metodológicas al pipeline Out-of-Sample del Comité METAR Walk-Forward. La auditoría demostró empíricamente que el OOS está distorsionado por `pivote_pred` (argmax de cierres sin barrera → inventa 70% bajista), falso test binomial contra 0.50, un mega-episodio de 745 barras que vació test 2023-2025, fuga temporal en la convicción de los agentes, y falta de respeto de la temporalidad/inception por estación. Este prompt es de **IMPLEMENTACIÓN Y VERIFICACIÓN EN CÓDIGO**, no de re-auditoría.

**Archivos a Modificar:**
1. `comite_metar/scripts/episodios.py` — De-clustering desacoplado + **respeto de inception por estación**.
2. `comite_metar/curador/modelador.py` — Ground-truth Opción C (Triada canónica zz25/zz50/zz75), test binomial vs baseline real, resolución de frontera, **embargo temporal**.
3. `comite_metar/agentes/_agente_base.py` — Nomenclatura nativa ALZA/BAJA y **aislamiento temporal de evidencia (sin lookahead, física D1xD2xD3)**.
4. `comite_metar/curador/curador.py` — Limpieza de adaptadores.
5. `comite_metar/run_comite.py` — Orquestación, clasificación de estaciones vs baseline real, y propagación de `fecha_inicio_valida`.
6. `comite_metar/scripts/first_passage.py` — Uso del first-passage OHLC canónico como ground-truth (si se reutiliza).
7. `comite_metar/salidas/*.json` — Regeneración de artefactos.

**Contexto — marco canónico del proyecto:**
- **Metrología Opción C**: first-passage OHLC intrabar (highs/lows del lake), barrera ±scale, SIN time-stop fijo de velas. El movimiento termina por cambio de régimen/barrera.
- **Política de Inception / temporalidad (OJO — CRÍTICO y OBLIGATORIO)**: Una estación/senal **NO existe antes de su `fecha_inicio_valida`**. Cada estación SOLO activa o contribuye a episodios DESDE su fecha de nacimiento. **8 estaciones tienen inicio posterior en los datos reales (verificado en el lake):**
  - **SV5_TURBULENCE** nace **1999-01-19** (86% NaN pre-2000)
  - **ROTATION** nace **1999-01-04** (86% NaN pre-2000)
  - **VVIX** nace **2006-03-06** (100% NaN pre-2000)
  - **PCR** nace **2006-11-01** (100% NaN pre-2000)
  - **CREDIT** nace **2007-04-11** (100% NaN pre-2000)
  - **FG** nace **2011-02-01** (100% NaN pre-2000)
  - **SKEW** nace **2011-02-01** (100% NaN pre-2000)
  - (VIX, YIELD, DXY, BSI desde inicio lake 1993)
  - **La regla se aplica a TODAS las de inicio tardío, no solo SKEW.** La activación de cualquier estación debe exigir `fecha_episodio >= fecha_inicio_valida(estación)`, leyendo el `inception` del perfil. Verificar que NADIE contribuya a episodios antes de su nacimiento (especialmente SV5/ROTATION ≥1999, VVIX/PCR ≥2006, CREDIT ≥2007, FG/SKEW ≥2011).
- **Estándar OOS del proyecto**: PBO (Deflated), IC in/out, Clopper-Pearson §3.3 (N<21 = diamante). Dato mata relato. La verdad habla.

---

### ESPECIFICACIONES TÉCNICAS OBLIGATORIAS:

#### 1. Ground-Truth Opción C (Triada Canónica)
- Eliminar la lógica `argmax/argmin` sobre `spy_close` en `pivote_pred`.
- Sustituir por first-passage intrabar sobre `spy_high`/`spy_low` para la Triada Canónica: zz25=±2.5%, zz50=±5.0%, zz75=±7.5%.
- Sin time-stop fijo de 80 velas. **Definir explícitamente el evento del tail (fin de serie)**: si un evento del lake NO alcanza ninguna barrera antes del final de la serie, marcar `resuelto: False` y **excluirlo de la accuracy**, reportando `resolution_rate` separada. No forzar resolución artificial.
- En `walk_forward`, cada episodio registra su ground-truth para las 3 escalas (zz25/zz50/zz75).

#### 2. Optimización de T y Baseline Real en `validar_oos`
- La optimización de `T ∈ [0.0..4.0]` en train (< 2020) se calibra usando como objetivo la escala táctica `zz25` (cobertura mínima 25%).
- El baseline del test se computa como la tasa de la clase mayoritaria bajo Opción C en test: `baseline = max(P_alza, P_baja)`.
- El test binomial unilateral (`p_greater`) en `metricas()` se evalúa OBLIGATORIAMENTE contra el baseline: `binomtest(hits, total, baseline, alternative="greater")`.
- Con `T` congelado, reportar el rendimiento en test por las 3 escalas: `zz25`, `zz50`, `zz75`.

#### 3. Desacoplo de Episodios en `episodios.py` (con temporalidad)
- Las estaciones estructurales (`yield_curve`, `credit`, `dxy`) se reclasifican como **régimen/contexto**: NO abren episodios continuos por sí solas.
- Un episodio se abre por activación extrema de ≥1 estación táctica (`vix`, `vvix`, `pcr`, `fg`, `sv5_turbulence`, `skew`, `bsi`, `rotation`) O por confluencia de ≥2 estaciones cualesquiera.
- **TEMPORALIDAD (obligatorio)**: la activación de cualquier estación SOLO cuenta si `fecha_episodio >= fecha_inicio_valida(estación)`. SKEW NO activa episodios antes de 2011; CREDIT antes de 2007; VVIX/PCR antes de 2006; SV5 antes de 1999; etc. Leer `inception` del perfil de cada estación.
- Límite de longitud de episodio: si un evento supera 20 barras sin nueva activación, se cierra.
- Restaura episodios del período 2023-2025 (objetivo: ≥40 episodios en test).

#### 4. Nomenclatura y Aislamiento Temporal de Agentes
- En `_agente_base.py`, cambiar `_TIPOS_DIR` a `{1: "ALZA", -1: "BAJA", 0: "NEUTRAL"}` (nomenclatura nativa; luego `_norm_dir` en curador se simplifica o se elimina para que todo use ALZA/BAJA).
- **Sin lookahead en convicción (física D1xD2xD3, NO ranking futuro)**: `_evidencia()` NO debe usar `ranking_maestro.json` calculado sobre TODO el lake (contiene datos futuros → fuga). La convicción del agente debe derivarse de la **congruencia física D1×D2×D3 + overflow** de la estación en t (reglas del perfil), sin condicionar a significancia BH del ranking global. NO depender de un ranking <<2020 (que no existe — no inventarlo ni asumirlo).

#### 5. Embargo Temporal (Punto ciego H4 — OBLIGATORIO)
- La autocorrelación de outcomes entre episodios contiguos en test es >90% (se generan a 5-7 días con forward de ~80 barras). NO son observaciones binomiales independientes.
- Implementar **embargo temporal (purga)**: al puntuar, descartar (o separar) evaluaciones cuyo viaje forward se solape con el episodio previo. Reportar **AMBAS**: muestra nominal `N` y muestra purgada/independiente `N_indep` (episodios separados por al menos la mediana de barras de resolución de zz25).
- Las métricas de significancia se calculan idealmente sobre `N_indep` (o se reporta el n-efectivo). No tratar muestras solapadas como binomios independientes.

---

### CRITERIOS DE ACEPTACIÓN (Dato Mata Relato):
1. La distribución global de ground-truth en el lake bajo `zz25` debe ubicarse en ~52% ALZA / ~48% BAJA (no 30/70).
2. El período de test OOS (2023-2026) debe contener ≥40 episodios evaluados (superando el vacío del Ep #714).
3. `modelo_confluencia.json` debe reportar métricas tri-escala (zz25/zz50/zz75) con p-values contra el baseline real, y N_nominal vs N_indep (embargo).
4. **Temporalidad**: verificar que NINGUNA estación contribuye a episodios antes de su `fecha_inicio_valida`. Test explícito: SV5/ROTATION no activan pre-1999, VVIX/PCR no pre-2006, CREDIT no pre-2007, FG/SKEW no pre-2011 (SKEW incluido).
5. `run_comite.py` ejecuta de principio a fin **sin errores**, regenerando los 5 archivos de `comite_metar/salidas/` sin warnings.
6. `_evidencia()` sin fugas: la convicción usa reglas físicas D1/D2/D3 del perfil (no ranking con datos futuros).
7. Sin-lookahead: `estado_en` sigue usando solo datos ≤ t (assert ya existente pasa).

**Entregables:** (a) archivos modificados, (b) distribución del ground-truth por escala, (c) N_nominal vs N_indep y p-values, (d) episodios restaurados en test (2023-2025), (e) verificación de temporalidad SKEW, (f) OOS honesto final.