# GUIDANCE — Revisión y arranque del Prompt Principal (rediseño de escalas adaptativas de Tide)

> **Sesión limpia. Este guidance es autocontenido.**
> **Revisión de referencia:** verifícala al arrancar (`git rev-parse HEAD`) y cítala en tu informe.
> **Instrucción: revisa el prompt contra el repo, MIDE lo que está desbloqueado, y RESPONDE las 4 preguntas del §9.2 con datos.**
> **Las 4 preguntas NO son opinión ni adjudicación de criterio: cada una se resuelve con una medición.** Se declara primero la regla de decisión y después se mide.

---

## 0. DÓNDE ESTÁS

**El prompt principal:**
`.hermes/prompts/2026-09-29-rediseno-ev-derived-escalas-adaptativas.md` (≈78 KB)

**Su objeto (requisito central, §2):** rediseñar la serie `ev_derived.json` con **escalas gaussianas ADAPTATIVAS per-ticker**, **conservando las dimensiones** (bins/etiquetas **inviolables**) y **recalibrando únicamente los edges**.

**Regla dura del proyecto:** **10 dimensiones intocables** — T(7) · C(7) · VWAP(6) · W(W7/v1 · 6/v2) · σVc · σc · σVw · ΔσVw (5) · vel(3) · #FATIGUE(3). `zz25/zz50/zz75` son **horizontes**, NO dimensiones. **Solo cambian los edges.**

**Estado del proyecto a la fecha:** el bug del `fatigue_type` tiene su contrato restaurado (A1) y **8 tests de contrato pasando**; el vault está cerrado en lo material (sin zigzag huérfanos, `obs_vel_svw` sin NULL); el carril `vwap`/`trade_count` está retirado y cerrado — **no lo toques**.

---

## 1. FASE 0 — REVISIÓN (antes de escribir una línea de diseño)

**1.1 Poner al día el prompt contra el repo.** El prompt fue escrito el 29-Sep; verifica cada cifra suya contra la realidad de hoy y anota las divergencias:
- **Su §2.0-ter** dice que la calibración de `vel` se hizo sobre *"un demo de ~25 barras/ticker × 17 tickers, no un censo (422 observaciones)"*.
  **MEDIDO HOY:** `engine.channel_snapshots` con `obs_vel_svw IS NOT NULL AND != 0` → **4.581.546 observaciones / 566 tickers.**
  → **Esa limitación ya no existe** (el backfill del observador se completó). **El pendiente "recalcular P33/P67 sobre el CENSO (post-backfill)" está DESBLOQUEADO.**
- Su §1 declara cifras de `channel_snapshots` (213.100 snapshots / 72 columnas). **Verifícalas** (hoy: 4.594.499 / 79).
- Verifica que sus rutas de archivos siguen existiendo: `compute_channel.py`, `icc_tide_derived.json`, `rc_tide_ev_derived.json`, `train_wave_table.py`, `backfill_channel_snapshots_v2.py`.

**1.2 Re-verificar el Registro Canónico de Dimensiones (§2.0-bis).** Está declarado *"verificado contra JSONs, 01-Oct"*. **Re-verifícalo** contra los JSONs reales y reporta cualquier divergencia. Es la base de todo lo demás: si el registro está mal, el diseño nace mal.

**1.3 Inventario de bloqueantes** (abajo) y **reporte de cuáles siguen vivos**. No los resuelvas si son del arquitecto.

---

## 2. LAS 4 PREGUNTAS DEL §9.2 — CADA UNA SE RESPONDE MIDIENDO

> **Regla:** para cada pregunta, **declara primero la regla de decisión** (qué dato, con qué corte, decide) y **después mide**. Nada se responde de palabra: cada respuesta con su comando y su salida.

| # | Pregunta | Qué se mide | Regla de decisión (declarar ANTES de medir) |
|---|---|---|---|
| **1** | **¿Qué es formalmente "Familia"?** — pooling universal (F1) / clustering sectorial (F2) / cuartiles ATR (F3) | **N/celda real sobre los 216 estados** en cada opción + **la discriminación del propio EV** (separación del forward-return entre estados) | La opción que **maximice la discriminación manteniendo el N/celda por encima del piso estadístico declarado**. Reportar las 3, no solo la ganadora |
| **2** | **¿A, B o C para la calibración per-ticker?** — cuantiles directos / PIT / shrinkage bayesiano | **IC en OOS** de cada opción + la tensión medida (IC global +0.412 vs per-ticker +0.371) | La opción cuyo **IC OOS no degrade el global declarado**. Si ninguna lo supera, se documenta y **se mantiene la global** |
| **3** | **¿Cómo se resuelve `fatigue_type`?** — matriz de rachas cinemáticas **o** propiedad unificada en el contrato | **¿La fatiga añade EV al forward-return en sus horizontes (`zz25/zz50/zz75`)?** Poblaciones con y sin la condición | Si **añade poder predictivo medible** → matriz cinemática. Si **no** → propiedad unificada declarada (contrato limpio). *(Toca la misma familia que el umbral del TRIM en `swing_gate.py:653`)* |
| **4** | **¿Estatus de las cifras de validación?** — 134/171 falsos positivos · edge 40.7 | Abrir `medicion_vix_crisis_spike.json` y `sigma_overflow.py` y **reproducir** los números | **Sustento con output propio**, no con cita del documento. Confirmado o refutado, con el comando |

**Criterio de sustento (el que ya usa el proyecto):** un valor está sustentado cuando existe **imposibilidad física**, **separación de poblaciones medida**, o **decisión declarada**. Lo demás es provisional.

### 🟡 Deuda de contrato (el diseño debe absorberla o declararla)
El rediseño **va a emitir** `signal` y `action_code`, hoy `str` sin tipo: el spec declara 6 valores de `signal`, el comentario del código declara 4, el código emite 5; y coexisten **dos namespaces** de `action_code` (`STK_*` en el módulo vs `ACTION_STK_T_*` en scripts). **Si el diseño no nace con el contrato tipado, heredará el drift.**

---

## 3. FASE 1 — ARRANQUE (lo que YA está desbloqueado: hazlo)

Esto **no depende** de las 4 decisiones del §9.2. Es trabajo real y es el cimiento del diseño (D):

1. **Recalibrar `vel`/`traj` sobre el CENSO.** Con las 4,58M observaciones / 566 tickers ahora disponibles, recalcular **P33/P67 de `obs_vel_svw`** (excluyendo ceros) y compararlos con los valores hoy vigentes:
   ```
   P33 = -0.130758   P50 = -0.004765   P67 = +0.120383   (N = 405, excl. ceros) ← calibración ACTUAL
   ```
   Reporta: los P33/P67 del censo, y **cuántos estados cambian de clasificación** (STABLE vs ▲/▼).
2. **Cerrar el fallback stale de Wave.** `rc_wave_lookup.py:174` tiene `_VEL_SVW_TH = (-0.091, 0.091)` (el valor EMA original); el trainer sobrescribe a `(-0.058, +0.123)` vía P33/P67 Kalman, **pero `rc_wave_ev_derived.json` no contiene `vel_thresholds`** (solo `rc_wave_derived.json` y `rc_wave_probability_table.json` lo tienen). **Verifica si `rc_wave_ev_lookup.py` cae al fallback stale y repórtalo con la línea exacta.**
3. **Medir la discrepancia de calibración/aplicación.** `train_wave_table.py` L286-289 cae a `EMA(5).diff()` cuando `obs_vel_svw IS NULL`, mientras los umbrales vienen del Kalman → **calibración ≠ aplicación**. Cuantifica cuántas barras caen por cada camino.
4. **PC-02 · Overflow:** definir las anclas **P0.135 / P99.865 (±3σ)** para `ticker_gaussian_profiles.json` (que **hoy no existe**) junto a los 5 edges D1. Sin ellas no hay z-score de overflow.
5. **PC-03 · Inception:** adaptar a Tide la política ya existente para METAR (`inception_policy.md`: `min_periods=252`, expanding window, exclusión por `fecha_inicio_valida`). Sin ella, un ticker de 100 barras tendría percentiles sobre ~2 observaciones.
6. **Construir el Documento de Diseño (D)** con la estructura completa, y cada sección del §9.2 alimentada por **el resultado de su medición** — no por una decisión de palabra.

---

## 4. REGLAS

1. **Ejecutar ≠ leer.** Cada afirmación con comando + salida real. Sin output, no hay hallazgo.
2. **No decidas lo del arquitecto.** Las 4 del §9.2 y todo trade-off de diseño: **se presentan con su trade-off y se marcan "a adjudicar"**.
3. **Las DIMENSIONES son inviolables.** Solo se recalibran los **edges**. No cambies bins, etiquetas ni llave.
4. **El spec es la autoridad.** Si código y spec divergen, se alinea o se declara — no se improvisa.
5. **Una sola fuente de verdad por indicador.** Antes de afirmar que algo es "la única fuente", verifica que no existan stores coexistentes.
6. **ADDITIVE-ONLY** si tocas algún prompt o artefacto.
7. **No amplíes el alcance:** el carril `vwap`/`trade_count` está cerrado; el bug `fatigue_type` ya tiene su contrato restaurado (no lo re-abras).
8. **Reporta lo que NO pudiste verificar**, explícitamente.

---

## 5. ENTREGABLE

1. **Tabla de revisión (Fase 0):** `PUNTO DEL PROMPT | LO QUE DICE | REALIDAD MEDIDA HOY | ¿VIGENTE? | ACCIÓN` — incluyendo las cifras, las rutas y el Registro Canónico re-verificado.
2. **Tabla de las 4 preguntas del §9.2:** `PREGUNTA | REGLA DE DECISIÓN DECLARADA | MEDICIÓN (comando + output) | RESULTADO | VALOR ADOPTADO`.
3. **Los 6 puntos de la Fase 1 ejecutados**, cada uno con comando + salida real:
   - los P33/P67 del censo + cuántos estados cambian,
   - el fallback stale de Wave (verificado con la línea exacta),
   - la discrepancia calibración/aplicación cuantificada,
   - el 134/171 y el 40.7 confirmados o refutados,
   - el Documento D con sus 4 respuestas medidas.
4. **El Documento de Diseño (D)** con las 4 respuestas **medidas**, cada una trazable al comando que la produjo.
5. **Dos listas obligatorias:** *"afirmaciones que no debí hacer sin medir"* y *"no verificable en esta sesión"*.
6. **Respuesta corta:** ¿el prompt principal está vigente contra el repo? Sí/No, con la lista exacta de lo que quedó desactualizado.
