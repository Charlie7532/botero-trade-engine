# GUIDANCE — Reparar la cadena de regeneración (5 paths rotos) y evaluar la correspondencia del VWAP

> **Revisión fija:** primero `git rev-parse HEAD` y cítalo. Hoy: `04edfaa`.
> Este documento es un **guidance, no una corrección**: describe lo observado, propone método, y **convoca al comité** a decidir entre alternativas. **No decidas unilateralmente.**

---

## 0. CONTEXTO (qué se observó, y con qué evidencia)

Las tablas operativas `s5_triad_table.json` y `s5v_triad_table.json` (en
`backend/modules/entry_decision/domain/rules/`) **declaran su propia cadena de regeneración**
en la clave `_pipeline_prerequisites`:

```json
"step_1_vault_ingestion":        "python3 backend/scripts/populate_qqq_constituents.py",
"step_2_sector_breadth":         "python3 backend/scripts/backfill_sector_breadth.py",
"step_3_volume_breadth":         "python3 backend/scripts/fast_backfill_sv5.py",
"step_4_qqq_indicators":         "python3 backend/scripts/generate_s5_qqq_indicators.py",
"step_5_feature_lake_snapshots": "python3 backend/scripts/backfill_channel_snapshots_v2.py",
"step_6_triad_training":         "python3 backend/scripts/train_s5v_triad.py && python3 backend/scripts/train_s5_triad.py",
"master_orchestrator":           "python3 backend/scripts/master_retrain_pipeline.py",
"validation_suite":              "PYTHONPATH=. pytest"
```

**Al verificar la existencia de cada path, 5 de 8 NO existen en la ruta declarada** ✗:

| Declarado en el JSON | ¿Existe? | Ubicación real |
|---|---|---|
| `backend/scripts/backfill_sector_breadth.py` | **ROTO** ✗ | `backend/scripts/backfills/backfill_sector_breadth.py` |
| `backend/scripts/generate_s5_qqq_indicators.py` | **ROTO** ✗ | `backend/scripts/generators/generate_s5_qqq_indicators.py` |
| **`backend/scripts/backfill_channel_snapshots_v2.py`** | **ROTO** ✗ | `backend/scripts/backfills/backfill_channel_snapshots_v2.py` |
| `backend/scripts/train_s5v_triad.py` | **ROTO** ✗ | `backend/scripts/trainers/train_s5v_triad.py` |
| `backend/scripts/train_s5_triad.py` | **ROTO** ✗ | `backend/scripts/trainers/train_s5_triad.py` |
| `populate_qqq_constituents.py` · `fast_backfill_sv5.py` · `master_retrain_pipeline.py` | OK ✓ | — |

**Dato adicional:** el campo `generated_by` de ambas tablas también apunta a una ruta obsoleta
(`backend/scripts/train_s5_triad.py` en vez de `…/trainers/train_s5_triad.py`).

**Y un segundo asunto, separado pero relacionado — la correspondencia del VWAP:**
- La feature `MS_VWAP_ZScore` (familia B1 del ingeniero, `engineer_features.py`) calcula **su propio VWAP**
  con `vwap_window: int = 20`, y esa ventana **está así en el feature lake**.
- El generador del canal (`compute_channel.py`) produce **tres VWAP con ventanas 240 / 60 / auto**.
- Se observa que **no hay correspondencia automática** entre ambos. **Hacerla corresponder tiene un reto real
  y puede no ser posible** — eso es precisamente lo que el comité debe evaluar (¿se puede? ¿conviene? ¿hay fallback?).

---

## 1. POR QUÉ IMPORTA (el problema de fondo, no el síntoma)

1. **El step_5 roto es el más grave.** `backfill_channel_snapshots_v2.py` es **el generador del feature lake**,
   y el feature lake es el **hub**: lo consumen las tablas que operamos **y** el camino de features/modelos.
   **Si el hub no es reproducible por su receta, nada aguas abajo lo es.**
2. **Una receta que no corre es una trampa documental.** Quien la siga (persona, CI, cron, o un agente)
   falla en el paso 2. El fallo no avisa: se descubre tarde.
3. **El patrón huele a clase, no a caso.** Los scripts se reorganizaron en subcarpetas
   (`backfills/`, `generators/`, `trainers/`) y **la declaración no se actualizó** ✗.
   Si pasó aquí, **pudo pasar en otros manifiestos**: documentación del plan, prompts, jobs programados,
   workflows del CI, otros JSON de calibración. **Hay que censar la clase, no parchear 5 líneas.**

---

## 2. OBJETIVOS

- **O1.** Que la cadena declarada por las tablas **corra de verdad**, en el orden declarado, sin conocimiento tácito.
- **O2.** Que el **generador del feature lake** quede **reproducible y no frágil** (es el hub).
- **O3.** **No volver a romperla**: que el drift no pueda repetirse en silencio.
- **O4.** Evaluar la **correspondencia del VWAP** (ventana del ingeniero vs 240/60/auto del canal):
  **¿es posible, conviene, y qué fallback existe si no lo es?**
- **O5.** Cualquier reemplazo debe ser **un fallback o una alternativa que no deje nada roto** —
  incluso en el peor caso (que la correspondencia no se pueda hacer).

---

## 3. HIPÓTESIS A CONTRASTAR (refutar, no confirmar)

| # | Hipótesis | Se refuta si… |
|---|---|---|
| **H1** | El drift se limita a esos 5 paths. | Existen más manifiestos/paths obsoletos en el repo (docs, prompts, CI, cron, otros JSON). |
| **H2** | El `master_retrain_pipeline.py` (el orquestador) tiene el mismo drift o lo compensa. | Sus rutas están sanas y/o ya resuelve las reales por otra vía. |
| **H3** | Hoy **nadie puede regenerar las tablas** siguiendo su propia declaración. | Existe otra vía documentada, o el path histórico se conserva por symlink/alias. |
| **H4** | El generador del feature lake es **punto único de fallo** del sistema. | Hay más de un camino para regenerar el lake, o el lake se considera descartable. |
| **H5** | La ventana 20 del `MS_VWAP_ZScore` fue **decisión**, no accidente. | No hay rastro de la decisión (ni comentario, ni commit, ni doc) → es accidente. |
| **H6** | La correspondencia VWAP ingeniero↔canal **es posible sin costo material**. | Requiere cambiar el lake, o romper semántica, o duplicar cálculo. |

---

## 4. MÉTODO Y TAREAS (cada una con su evidencia)

**T1 · Censo COMPLETO del drift (por familia, no por lista corta).**
Barre **todos** los sitios donde se declaren rutas: los `_pipeline_prerequisites` de los 31 JSON de
`entry_decision/domain/rules/`, los `.md` del plan/planes, los prompts, los workflows del CI, los jobs de cron,
los `docstring` de los propios scripts. Para cada ruta declarada que sea un script: **verifica existencia**.
Salida: tabla `Archivo que declara | Ruta declarada | ¿Existe? | Ruta real`.

**T2 · El orquestador y la automatización.**
Audita `master_retrain_pipeline.py`: ¿usa rutas reales? ¿las resuelve por nombres? ¿tiene su propio mapa?
Y revisa si hay **cron/jobs/CI** que invoquen las rutas rotas (serían fallos silenciosos en producción).

**T3 · Los consumidores del feature lake.**
Traza **quién** lee el lake (tablas, modelos, research, daemons) y **qué pasa hoy** si se regenera el lake:
¿se invalidan las tablas? ¿los `sentinel_*.pkl`? ¿las caches?
(Esto es el probe de *"salidas derivadas ya consumidas"*.)

**T4 · Evaluar el VWAP del ingeniero (ventana 20) contra el canal (240/60/auto).**
Mide: ¿la ventana 20 tiene sustento (¿percentil? ¿ciclo? ¿decisión escrita?)? ¿Qué cambiaría si el ingeniero
consumiera las columnas del canal en vez de recalcular? ¿Es viable pasar el dataframe del lake al ingeniero?
**Prohibido concluir sin medir**: si no hay rastro de la decisión de 20, se declara **sin sustento**.

**T5 · Construir las alternativas con su costo.**
Para cada objetivo (O1–O5), enumera **al menos 3 caminos posibles**, incluido **explícitamente el fallback**
(el "si no se puede, entonces…"). Con: el costo, el riesgo, lo que rompe, lo que no, y si es reversible.

---

## 5. ENTREGABLE — **opciones para el COMITÉ**, no una decisión

### 5.1 Tabla de hallazgos
```
HALLAZGO | EVIDENCIA (comando + salida) | POBLACIÓN MEDIDA | SUSTENTO | CONSUMIDOR FINAL | ESTADO
```

### 5.2 Tabla de opciones (esto es lo que se le lleva al comité)
| # | Opción | Qué resuelve | Costo | Riesgo | ¿Reversible? | Recomendada por el analista |
|---|---|---|---|---|---|---|
| 1 | … | … | … | … | … | sí/no |

Debe incluir **al menos**:
- **(a) Reparación mínima** (actualizar los paths declarados a las rutas reales).
- **(b) Robustez estructural** (que la declaración no dependa de rutas: resolver por nombre/registro/entrypoints,
  o un test que falle si un path declarado no existe).
- **(c) Fallback obligatorio**: **¿qué se hace si el generador del lake no puede correr?** Debe existir un plan
  explícito — no puede quedar "roto y sin plan".
- **(d) Para el VWAP**: la tabla de opciones debe incluir la **correspondencia** (ingeniero ← canal),
  la **no-correspondencia declarada** (mantener las dos, documentando por qué), y el **reemplazo** (una tercera
  vía que no duplique: p.ej. que el lake materialice la columna y todos la lean).

### 5.3 Dos listas obligatorias
- **«Afirmaciones que NO debí hacer sin medir»**.
- **«No verificable aquí»** (con lo que haría falta).

### 5.4 Las tres respuestas cortas
1. ¿Cuántos paths rotos hay **en total** (no solo los 5) y en cuántos archivos?
2. ¿Puede hoy un tercero regenerar las tablas **siguiendo solo lo declarado**? (sí/no + por qué)
3. De las opciones, **¿cuál no deja nada roto en el peor caso?** (el fallback)

---

## 6. REGLAS

1. **NO modifiques nada.** Este ejercicio es de diagnóstico y propuesta. La corrección se decide en comité.
2. **Evidencia literal** por afirmación (comando + salida). Sin salida, no hay afirmación.
3. **Ley 1:** «esto NO es un problema» exige la misma evidencia que «esto SÍ lo es».
4. **Ley 2:** ningún criterio es correcto hasta que se **EJECUTA** (verifica los paths uno por uno, no de memoria).
5. **No ancles**: dos caminos independientes (lectura de manifiestos + ejecución/verificación real) que converjan.
6. **Por familia, no por lista corta**: censa la clase de drift, no los 5 que ya conocemos.
7. **El feature lake es el hub**: trátalo como el componente crítico del sistema, no como un script más.

---

*Contexto de por qué se pide: el sistema **opera** con las tablas `s5/s5v`, y esas tablas **no pueden regenerarse
siguiendo su propia declaración**. El generador del feature lake está entre las rutas rotas. Un sistema que no
puede reconstruirse desde su propia documentación no es reproducible — y eso ya estaba declarado como deuda.*
