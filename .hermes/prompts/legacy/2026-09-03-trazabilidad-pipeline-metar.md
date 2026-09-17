# PROMPT: Auditoría de Trazabilidad del Pipeline de Datos METAR — Diseño Verificado de punta a punta

**Fecha:** 03-Sep-2026
**Ejecutor:** Gemini (agente de trabajo en el repo `/root/botero-trade`)
**Propósito:** Verificar con datos el DISEÑO INTEGRAL del pipeline de datos METAR — desde cómo se calculan los edges de los bins, hasta las mediciones de señales — para establecer una línea base de credibilidad. Antes de auditar cualquier métrica por estación o "fat-tail", hay que trazar CADA eslabón a su fuente canónica y confirmar que el diseño es correcto.

**Contexto:** El usuario señala que las afirmaciones sobre las escalas y los fat-tails son "delicadas" sin verificar el diseño de las tablas y la data desde el origen. Este es el paso 0: el MAPA DE TRAZABILIDAD.

**Regla rectora:** No asumir. Cada eslabón se verifica leyendo el código real y, cuando es posible, reproduciendo el cálculo. El entregable es un mapa que conecta cada columna del artifact final con su generador y su diseño.

---

## PARTE A — MAPA DE TRAZABILIDAD (el árbol genealógico de cada dato)

Construir un mapa que documente, para **cada artifact**, su fuente y el diseño de cada eslabón:

| Artifact | Archivo(s) | Generador(fuente) | Diseño del eslabón clave | ¿Look-ahead? | ¿Empírico o paramétrico? |
|:---------|:-----------|:------------------|:-------------------------|:---:|:---:|
| `continuous_metar_lake.parquet` | `backend/scripts/generators/build_continuous_metar_lake.py` | Neon Vault | Edges D1/D2/D3: ¿expanding-rank empírico (L134) o quantile? | ? | ? |
| Fact stores (`*.fact_store.json`) | `generate_all_150_state_fact_stores.py` | Vault | Edges de bins: ¿los mismos del lake o recalculados? | ? | ? |
| `quants_obs.pkl` | `generate_quants_obs.py` | Lake + SS | Pivotes, d1_vote | ? | ? |
| `bar_augment.parquet` | `construir_bar_snapshot.py` | Lake | First-passage OHLC | ? | — |
| `sigma_overflow.py` `STATION_MU_SIGMA` | `sigma_overflow.py` | ¿Vault? ¿fijo? | μ/σ paramétrico fijo | ? | **paramétrico** |

**Tarea A.1:** Para cada artifact, ejecutar o leer el generador y VERIFICAR:
1. ¿Los edges de D1/D2/D3 se calculan como **expanding-window percentile rank** (empírico, sin look-ahead), o es **quantile de población final** (look-ahead)?
2. ¿Las columnas `*_d1_bin` del lake coinciden con lo que los fact stores usan como celdas? ¿O recalculan?
3. ¿De dónde sale `STATION_MU_SIGMA` (los μ/σ del overflow)? ¿Es fijo? ¿De qué población? ¿Tiene look-ahead?
4. ¿Hay alguna columna donde el diseño contradiga el canon (`gaussian_scale_policy.md` Rule S1-S5, `d1_labels_canonical.md`)?

**Tarea A.2 — el diseño real, no el documento:** El canon dice "expanding-rank empírico, sin μ±kσ". **VERIFICAR si el código real lo cumple** o si hay discrepancias (p.ej. overflow paramétrico vs edges empíricos). Documentar las discrepancias encontradas.

---

## PARTE B — REPRODUCCIÓN DE LA LÍNEA BASE (solo tras A)

Una vez trazado el diseño real, reproducir los valores que el sistema usa, para confirmar que se pueden recomputar desde la fuente:

1. **Edges D1 de VIX:** recalcular los edges reales que produce `build_continuous_metar_lake.py` y comparar con lo esperado.
2. **Bins de VIX:** reproducir el % por bin (0-5) y confirmar si el diseño expanding-window produce el reparto documentado.
3. **Z-score del lake vs overflow:** verificar si la columna `vix_z_d1` usa el mismo método que `sigma_overflow` (z paramétrico) o edges empíricos — **son métodos distintos, documentar cuál alimenta qué.**
4. **Overflow:** reproducir cuántos overflows z>3σ produce cada estación con el MÉTODO QUE EL SISTEMA REAL USA (paramétrico de `STATION_MU_SIGMA`), y reportar el conteo real.

**NO concluir fat-tails todavía** — en esta fase solo se reproduce la línea base que el sistema usa, sin juzgarla.

---

## PARTE C — DIFERENCIAS ENTRE ARTIFACTS (detección de inconsistencias de diseño)

- Comparar los edges/bins del lake vs los de los fact stores vs los de `quants_obs`. ¿Son consistentes entre sí? ¿O cada uno calcula distinto?
- Si hay 2 métodos distintos (ej: lake expand-ing-empírico vs overflow paramétrico), **documentar la divergencia** de diseño — es una candidata a fuente de error.

---

## PARTE D — ENTREGABLES

1. `mapa_trazabilidad.md` — el árbol genealógico de cada artifact (fuente + diseño + look-ahead + empírico/param).
2. `reproduccion_linea_base.md` — los valores reales recomputados (edges VIX, % bins, z-scores, overflows) que el sistema usa.
3. `discrepancias_diseno.md` — TODAS las divergencias encontradas (incluso las menores), con su severidad y la posible fuente de error.

---

## PARTE E — PREGUNTAS QUE RESPONDER

1. ¿El diseño del pipeline cumple el canon (expanding-rank empírico, sin look-ahead)? Verificar cada artifact.
2. ¿El overflow usa un método DISTINTO (paramétrico) al de los edges del lake (empírico)? Si sí, ¿es eso una inconsistencia de diseño?
3. ¿Dónde está la fuente de verdad canónica de los edges — en el lake, en los fact stores, o en `STATION_MU_SIGMA`?
4. ¿Cuáles artifacts comparten diseño y cuáles divergen?

---

## Verificación de aceptación
```bash
# Recomputar y reportar:
backend/.venv/bin/python << 'EOF'
# 1. Edges D1 de VIX del generador real (leer codigo, no asumir)
# 2. % bins de VIX en el lake (distribucion real)
# 3. z-scores del lake vs sigma_overflow (mismo metodo?)
# 4. overflows param de cada estacion (conteo real)
# Entregable: mapa de trazabilidad completo
EOF
```

**Reglas:** no concluir sobre fat-tails o calibración hasta que el mapa de trazabilidad esté verificado. Dato mata relato — cada afirmación del mapa se apoya en el código leído o el resultado reproducido.