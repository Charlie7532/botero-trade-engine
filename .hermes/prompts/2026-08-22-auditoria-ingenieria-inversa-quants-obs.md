# AUDITORÍA EXTERNA — `quants_obs.pkl`: arquitectura de regeneración guiada por propósito

**Solicitante:** Juan Andrés (Arquitecto) vía Hermes (qwen/qwen3.8-max)
**Fecha:** 22-Ago-2026
**Ambiente:** `/root/botero-trade` — ejecutar con `cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python <script>`

---

## 0. EL PROPÓSITO (guía de arquitectura — leer primero)

`quants_obs.pkl` es la **tabla de observación canónica** del sistema de investigación de señales de Botero Trade. Para cada pivote confirmado del zigzag SPY escala zz25 (un punto donde el mercado giró), captura el **estado dimensional instantáneo de las 11 estaciones** (nivel `_val`, velocidad `_vel`, inestabilidad `_vol`, estado dimensional `_sk`, voto D1, probabilidades del fact store, EV neto) más la convicción del cascade.

**Mide:** la condición del mercado en el instante de un posible giro — "qué leía cada instrumento cuando el mercado cambió de dirección". Es la matriz de features sobre la que se mide el edge real de cada señal de entry/exit.

**La consecuencia arquitectónica que rige esta auditoría:** el fin es una tabla **correcta según la lógica de producción actual y reproducible**, NO una réplica byte-a-byte del artefacto one-off del 17-Ago. La fidelidad al original es un *detector de divergencias*, no la meta. Cada divergencia debe clasificarse en una de tres categorías:

- **CAT-A — Bug del one-off original:** el original estaba equivocado; la tabla correcta usa la lógica de producción. (Ej. candidato: clasificación skew no reproducida por ningún clasificador conocido.)
- **CAT-B — Artefacto histórico aceptable:** el original usó una versión de datos/calibración que ya no existe (deriva); se acepta documentar la divergencia. (Ej. confirmado: bloque plano `zz25` de fact stores regenerado; μ/σ de `z_bear` invertidos = 0.3299/0.2856 que no existen en ningún archivo actual.)
- **CAT-C — Fórmula aún no identificada:** falta encontrar la especificación real. (Ej. candidato: el clasificador D1 de skew.)

**Tu trabajo es dictaminar la categoría de cada divergencia y proponer la arquitectura correcta columna por columna, guiada por el propósito.** No se trata de alcanzar 100% de réplica a cualquier costo.

## 1. CONTEXTO: QUÉ ES EL PICKLE Y POR QUÉ SE REGENERA

- 1,590 pivotes SPY zz25 (1993-01-29 a 2026-07-29) × 141 columnas.
- Motivos de regeneración: (a) el generador fue un one-off **nunca versionado**; (b) el zigzag crece (+1 pivote nuevo en la DB posterior al 17-Ago) y se necesita pipeline reproducible; (c) la auditoría previa reveló deriva y look-ahead que obligan a regenerar la cadena bajo control.
- Consumidores aguas abajo: `evaluador_vela_a_vela.py`, `arnes/` (las señales leen **solo D1** del state_key), `audit_regimes.py`, forensia de wins/losses, análisis de duración.

## 2. LO YA VERIFICADO (no repetir este trabajo)

1. **Pivotes reproducibles al 100%** vía `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")`. Fórmula del zigzag consistente en zz25/zz50/zz75.
2. **`cascade_50/75` = proximidad temporal** (±3 días a un pivote zz50/zz75), NO pertenencia. Recalculado coincide 99.9%.
3. **State_keys 100% consistentes** con los fact stores de producción (cero huérfanos, 11 estaciones).
4. **Builder v2** en `research/10_gate_oos_validation/builder_quants_obs.py` con **compuerta de fidelidad** integrada. Estado actual: **101/141 columnas al ≥99.9%**. Salida en `quants_obs_new.pkl` (NO sustituye al original).
5. **Reporte de la compuerta:** `research/10_gate_oos_validation/COMPUERTA_FIDELIDAD_BUILDER_v2_22AGO.md`.
6. **Patrones de construcción de referencia:** `audit_regimes.py` (FASE 1), `d2_direction_step1.py` (`build_obs_df()`), `regenerar_quants_obs.py`, `recalibrar_cascade_trailing.py`.

## 3. INCÓGNITAS YA RESUELTAS (verificadas con datos, match indicado)

| Columna | Resolución | Match |
|---------|-----------|:---:|
| `duration_bars` | Duración CALENDARIO de la pierna que ARRANCA en el pivote, piso 1 día | 100% |
| `daily_return_pct` | Retorno de esa pierna (%) ÷ duración | 100% |
| `next_bear` / `next_leg_direction` | Idénticos a `leg_bear` (el original los nombró mal) | 100% |
| `z_dom` | μ/σ del calibration file (0.0532/0.035) | 100% |
| `cascade_conviction` | 0.66·z_bear + 0.34·z_dom plano | 100% |
| `{st}_zk_pbull/pbear` | Bloque `zigzag_kinematic.zz25` del fact store | 100% |
| Alineación `_val/_vel/_vol` | Fecha EXACTA; fuera de rango val=NaN, vel=0, vol=1 | 100% (PCR) |
| `z_bear` | μ=0.3299 σ=0.2856 por ingeniería inversa (no existen en ningún archivo) | 99.94% |

## 4. LAS 40 COLUMNAS DIVERGENTES — causas raíz ya identificadas (dictaminar categoría)

### A. SKEW D1 — bins SOLAPADOS, clasificador no identificado [candidato CAT-A o CAT-C]
Los bins del pickle se solapan en el valor de SKEW:
- `NORMAL_TAIL_RISK`: 109.10 – 119.83
- `ELEVATED_TAIL_RISK`: 113.49 – 120.40
- `LOW_TAIL_RISK`: 104.31 – 113.33

Con umbral estático los bins nunca se solapan. `_val/_vel/_vol` de skew matchean al 99.7% (la serie es la misma); solo difiere la clasificación D1.
- **Hipótesis trailing probada y RECHAZADA:** cuantiles Gaussianos recalculados en cada pivote sobre ventanas 252/504/756/1000 barras alcanzan máximo 41.9% de match. Ninguna reproduce el solapamiento.
- **PREGUNTA CLAVE:** ¿qué clasificador produce bins solapados? ¿Es un bug del one-off (CAT-A → usar edges estáticos de producción y documentar) o una fórmula aún no identificada (CAT-C)?
- Afecta: `skew_sk` (13.3%), `skew_n`, `skew_d1_vote` (66.4%), `skew_zz25_pbull/pbear`, `skew_ev_net` (0.4%), `skew_zk_pbull/pbear` (3.5%).

### B. D1 votes y cascade (contaminación aguas abajo de A + deriva bsi)
- `bsi_d1_vote`: 73.1% — los bins bsi se separan limpiamente, pero el voto depende del estado completo D1__D2__D3.
- `d1_bear_5`: 15.2% — promedio de votos Grupo A, arrastrado por skew/bsi.
- `z_bear`, `cascade_conviction`: 15.2% — cascada de `d1_bear_5` (la fórmula es correcta al 100%, solo el input difiere).
- `mean_zk_pbull_11`: 3.5%.

### C. Deriva del bloque plano `zz25` de los fact stores [candidato CAT-B]
- `{st}_zz25_pbull/pbear`, `{st}_ev_net`: 80-94% según estación.
- El bloque plano `zz25` fue regenerado (post-17-Ago, "edges trailing 3 años" según docstring); el bloque `zigzag_kinematic` NO deriva (100%).
- Fact stores con timestamp 16-Ago (antes del pickle), pero el bloque plano no reproduce los valores del pickle.

## 5. PREGUNTAS CONCRETAS PARA EL AUDITOR

1. **Dictaminar la categoría (A/B/C) de cada divergencia** de la sección 4, con evidencia reproducible.
2. **Para cada CAT-A:** proponer el patch al builder usando la lógica de producción correcta (no la del one-off).
3. **Para cada CAT-B:** cuantificar el impacto aguas abajo y proponer cómo documentar la divergencia de forma versionada.
4. **Para cada CAT-C:** entregar la especificación (fuente, fórmula, alineación, parámetros) con script de forensia que la reproduzca.
5. **Resolver el clasificador de skew** (sección 4A): identificar qué lo produce, o dictaminar definitivamente que es un bug del one-off y que la tabla correcta usa edges estáticos.
6. **Verificar la hipótesis de deriva** de los fact stores (bloque plano `zz25`) y proponer cómo congelar versiones para regresión segura futura.
7. **Especificar la arquitectura final de regeneración:** un builder versionado que, guiado por el propósito, produzca una tabla correcta y reproducible — con la especificación por columna que faltó el 17-Ago.

## 6. LÍMITES DEL SCOPE

- ✅ **Preservar** `quants_obs.pkl` intacto (backup byte-a-byte en `quants_obs.pkl.bak`); el builder escribe en `quants_obs_new.pkl`; la sustitución solo ocurre con dictamen de arquitectura aprobado.
- ✅ **Respetar** los edges estáticos de los LookupAdapters de producción como la clasificación correcta por defecto (el propósito es una tabla correcta según producción, no una réplica histórica).
- ✅ **Mantener** el universo de 1,590 pivotes SPY zz25 (el pivote nuevo de 2026-07-29 queda fuera de esta regeneración).
- ✅ **Aislar** los cambios a `builder_quants_obs.py`, scripts de forensia en `scratch/` y salida `_new.pkl`.
- ✅ **Conservar** la comparabilidad con los consumidores actuales (`evaluador_vela_a_vela.py`, `arnes/`, `audit_regimes.py`); documentar cualquier columna cuyo valor cambie y qué consumidor la lee.
- ✅ **Registrar** la especificación final por columna como documentación versionada (el entregable que faltó el 17-Ago).

## 7. FORMATO DE ENTREGA ESPERADO

1. Tabla de dictamen: 40 columnas divergentes × (columna, categoría A/B/C, evidencia, resolución propuesta).
2. Tabla de especificación: 141 filas × (columna, fuente, fórmula, alineación, match alcanzado).
3. Patch al builder para cada CAT-A, con la compuerta de fidelidad antes/después.
4. Especificación de la arquitectura final de regeneración.
5. Firma del modelo auditor y fecha.

## 8. NOTA SOBRE CONSUMO AGUAS ABAJO (para priorizar)

Las 8 señales del catálogo v7 (`pcr_put_panic`, `credit_stress`, `capitulacion`, `panico_total`, `vvix_entry`, `bsi_washed_out`, `breadth_contraction_exit`, `skew_paranoia_exit`) leen **solo la componente D1** del state_key (`sk.split("__")[0]`). Columnas de mayor consumo: `_sk` (todas las señales), `_val` (algunas), `cascade_conviction` (1 señal), `daily_return_pct` (forensia), `duration_bars` (análisis de duración). Priorizar la corrección de esas columnas sobre las de consumo nulo. **La pregunta decisiva: ¿la divergencia D1 de skew afecta a alguna señal del catálogo?**
