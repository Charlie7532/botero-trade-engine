# AUDITORÍA PROFUNDA: `prompt_tabla_unica_bar_snapshot.md`
## Marco: Arquitectura Final — 1 tabla + 37 inteligencia de señal + confluencias

---

## 🔍 Punto ciego #1 (ESTRUCTURAL): La tabla NO remplaza los evaluadores, los complementa

Gemini presenta la tabla como "elimina la dispersión de 143 archivos" y "erradica el sesgo de selección". Pero omite una distinción fundamental:

| Sistema | Mide | ¿Para qué sirve? |
|:--------|:-----|:-----------------|
| **Evaluador vela a vela** | Rendimiento **condicionado a señal** (primera barra del episodio) | Saber si UNA señal específica tiene edge |
| **`bar_snapshot.parquet`** | Rendimiento **incondicional** desde cualquier barra | Saber qué esperar desde cualquier estado, haya o no señal |

**El evaluador responde:** "¿cascade_reversal funciona cuando dispara?" → condicionado.

**La tabla responde:** "¿qué pasa en el mercado cuando VIX está en 5__4__3, independientemente de si cascade_reversal dispara?" → incondicional.

**No son intercambiables.** La tabla mide el CLIMA. Los evaluadores miden la SEÑAL. El Entry Gate necesita AMBAS: "El clima es bueno para comprar (tabla), y además mi señal favorita confirma (evaluador)."

**Corrección:** El prompt debe especificar que la tabla NO reemplaza los evaluadores. Los evaluadores siguen midiendo condicionado a señal. La tabla mide el estado incondicional. Ambos coexisten.

---

## 🔍 Punto ciego #2 (ARQUITECTÓNICO): La tabla no define cómo se genera la inteligencia de señal

Gemini produce la tabla, pero ¿de dónde sale la inteligencia de señal? El flujo completo necesita 3 capas:

```
CAPA 0 — Dato crudo:     lake.parquet (8,453 × 257) + quants_obs (1,590 pivotes)
                          ↓ un script, un barrido
CAPA 1 — Tabla atómica:  bar_snapshot.parquet (8,453 × ~95 columnas)
                          ↓ métricas condicionadas por señal (usando los booleanos)
CAPA 2 — Inteligencia:   intelligence/senales/cascade_reversal.json
                          intelligence/estaciones/vix.json
                          intelligence/confluencia.json
```

**El prompt de Gemini cubre CAPA 0→1 pero NO CAPA 1→2.** Sin la Capa 2, el Entry Gate tiene que:
1. Cargar 8,453 filas
2. Filtrar por `vix_sk = "5__4__3"`
3. Para cada señal, agrupar por `{senal}_entry = True`
4. Calcular drawdown, Kelly, sharpe
5. Repetir cada vez que pregunte

**Eso es 10ms por consulta.** No parece mucho, pero si el Entry Gate consulta 100 veces al día, son 1 segundo de cómputo innecesario. Las vistas pre-agregadas (Cap 2) reducen a <1ms y eliminan la necesidad de Pandas en producción.

**Corrección:** El prompt debe incluir la Capa 2 como paso posterior (no en el mismo script, sino como script de agregación que lee el parquet y produce los JSONs).

---

## 🔍 Punto ciego #3 (MÉTRICO): La tabla mide Long y Short, pero no cruza con el tipo de señal

Gemini incluye `zz25_long_hit` y `zz25_short_hit` para cada barra. Esto es correcto. Pero:

| Señal | Tipo | ¿Qué métrica importa? |
|:------|:----:|:----------------------|
| `cascade_reversal` | EXIT (MAX) | Short (busca techo) |
| `panico_total` | ENTRY (MIN) | Long (busca piso) |
| `neutral_crush_entry` | ENTRY (MIN) | Long |
| `defensive_rotation_divergence` | EXIT (MAX) | Short |

**La tabla tiene ambas métricas, pero no las asocia al tipo de señal.** Para saber si `cascade_reversal` funciona en `5__4__3`, hay que:
1. Leer la señal → tipo=EXIT → blanco=MAX
2. Saber que para EXIT/MAX, la métrica relevante es `zz25_short_hit`
3. Filtrar tabla por `vix_sk="5__4__3"` y `cascade_reversal_entry=True`
4. Calcular `zz25_short_hit.mean()`

**No es un error, es una omisión de documentación.** La tabla tiene los datos, pero el prompt no explica cómo usarlos según el tipo de señal.

---

## 🔍 Punto ciego #4 (COSTO): First-passage por barra es costoso

Simulemos:

```python
# 8,453 barras × 3 escalas × 2 direcciones = 50,718 evaluaciones
# Cada first_passage_bar() camina ~80 barras hacia adelante para zz25
# Total: ~4 millones de comparaciones de precio
```

**Esto no es gratis.** El evaluador general ejecuta first_passage_bar() ~2,000-5,000 veces (solo donde hay episodios). La tabla lo ejecuta 50,718 veces — **10x-25x más.**

**Tiempo estimado:**
- First-passage vectorizado: ~30-60 segundos
- Timing vs pivotes: ~5 segundos
- Evaluación de 37 señales: ~2 segundos
- **Total: ~40-70 segundos** (no 2-5 minutos, pero tampoco instantáneo)

**No es bloqueante** (se ejecuta en background, una vez al mes), pero hay que saberlo para no esperar 5 segundos pensando que son 2.

---

## 🔍 Punto ciego #5 (CONSISTENCIA): La tabla no verifica contra los evaluadores existentes

El prompt tiene tests de integridad (líneas 100-127) pero **no compara contra los evaluadores existentes**. Si el `bar_snapshot` dice que `panico_total` en `5__4__3` tiene HR=0.75, pero el evaluador vela a vela dice HR=0.92, **algo está mal**. 

| Métrica | Evaluador VAV (condicionado) | Tabla (condicionado a `vix_sk`) | Diferencia esperada |
|:--------|:---------------------------:|:-------------------------------:|:--------------------|
| `panico_total` HR | HR condicionado a la señal | HR condicionado a VIX 5__4__3 | **Son métricas diferentes.** El VAV mide solo cuando panico_total dispara. La tabla mide todas las barras en 5__4__3, hayan o no disparado. |

**No se pueden comparar directamente.** Pero el prompt no lo aclara, y quien lea los tests pensará que ambos HR deben coincidir. 

**Corrección:** Agregar un test que compare manzanas con manzanas:

```python
# Test de consistencia: condicionado a señal Y estado
# Esto SÍ debe coincidir con el evaluador VAV
cond = df[(df["vix_sk"] == "5__4__3") & (df["panico_total_entry"])]
# → HR aquí DEBE ser similar al VAV para panico_total en estado 5__4__3
```

---

## 🔍 Punto ciego #6 (FUTURO): Una nueva señal NO requiere re-barrido completo

Gemini propone que las señales están en la tabla como columnas booleanas. Si agregamos una señal nueva (señal #38), necesitamos:
1. Agregar `senal_38` y `senal_38_entry` como nuevas columnas
2. Eso requiere **re-ejecutar el barrido completo** (40-70 segundos)

**Esto es aceptable** si agregamos señales una vez al mes. Pero si el research está explorando 20 variantes por semana, no lo es.

**Alternativa que Gemini no considera:** Las columnas de estado (`vix_sk`, `zz25_long_hit`, etc.) son estables y raramente cambian. Las columnas de señales son volátiles. Separar en 2 archivos:

```
bar_snapshot_base.parquet     ← Columnas de estado + first-passage (estable, ~55 cols)
bar_snapshot_signals.parquet  ← Solo las 37 señales booleanas (volátil, ~74 cols)
```

**Agregar señal #38:** Solo regenerar `bar_snapshot_signals.parquet` (2 segundos, no 70). La base no se toca.

---

## 🔍 Punto ciego #7 (CONFLUENCIA): No se deriva de la tabla

El prompt no menciona cómo identificar confluencias. Con la tabla, la confluencia se obtiene así:

```python
# Co-ocurrencia de señales en el mismo estado
confluencia = df[df["vix_sk"] == "5__4__3"].groupby("fecha").agg(
    {s: "max" for s in SENALES_37}
)
# Matriz de correlación binaria
corr = confluencia.corr()
# Pares que co-ocurren >20% del tiempo
pares = [(c, r) for (c, r) in np.argwhere(corr > 0.2) if c != r]
```

**Pero esto no es una métrica de edge.** Dos señales pueden co-ocurrir 80% y ser redundantes. El edge combinado puede ser peor que cada una por separado. **La confluencia de verdad requiere medir el rendimiento combinado**:

```python
# Rendimiento cuando cascade_reversal Y panico_total disparan juntos
ambas = df[df["cascade_reversal_entry"] & df["panico_total_entry"]]
hr_combinado = ambas["zz25_long_hit"].mean()
hr_cascade_solo = df[df["cascade_reversal_entry"] & ~df["panico_total_entry"]]["zz25_long_hit"].mean()
hr_panico_solo = df[~df["cascade_reversal_entry"] & df["panico_total_entry"]]["zz25_long_hit"].mean()

# ¿Combinar mejora el HR individual?
print(f"Ambas: {hr_combinado:.3f} | Cascade solo: {hr_cascade_solo:.3f} | Panico solo: {hr_panico_solo:.3f}")
```

Gemini no lo menciona. La confluencia es una **vista derivada** de la tabla, no viene incluida.

---

## ✅ Lo que Gemini hizo bien (y no debemos perder)

| Acierto | Por qué es importante |
|:--------|:----------------------|
| **Long + Short** | Permite evaluar cualquier señal en cualquier estado, independientemente de su dirección natural |
| **Entry flags** | `{senal}_entry` elimina autocorrelación por ráfaga |
| **Time-stop canónico** | C9 implementado correctamente |
| **Zero sesgo de selección** | Todos los state_keys son señales atómicas |
| **MAE/MFE explícitos** | Permite dimensionar stops y objetivos mecánicamente |
| **6 slots de timing** | Alineación canónica con ciclos ZZ |
| **Archivo único** | Una sola fuente de verdad, 143 → 1 |

---

## 📋 Lo que la arquitectura FINAL necesita (y Gemini no cubre)

| Componente | ¿Gemini lo cubre? | Prioridad |
|:-----------|:-----------------:|:---------:|
| 1 tabla (`bar_snapshot.parquet`) | ✅ Sí | 🔴 Esencial |
| 37 inteligencia de señal | ❌ No — no produce vistas por señal | 🔴 Esencial |
| 11 inteligencia por estación | ❌ No — no produce vistas por estación | 🟡 Importante |
| Confluencia | ❌ No — no calcula co-ocurrencia ni edge combinado | 🟡 Importante |
| Drawdown inter-trade | ❌ No — solo MAE intra-trade | 🔴 Esencial |
| Overflow detallado (T1-T5+) | ❌ No — solo booleano | 🟡 Importante |
| Ventanas históricas | ❌ No — todos los datos como iguales | 🟡 Importante |
| Verificación vs evaluadores | ❌ No — tests solo de integridad | 🟡 Importante |
| Separación base vs señales | ❌ No — todo en una tabla | 🟢 Opcional |
| Archive 77+ archivos | ✅ Sí — menciona limpieza | 🟢 Opcional |