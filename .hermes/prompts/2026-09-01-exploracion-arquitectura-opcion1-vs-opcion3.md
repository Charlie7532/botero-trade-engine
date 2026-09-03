# EXPLORACIÓN ARQUITECTÓNICA: Opción 1 vs Opción 3 — El Consolidador de Señales

**Propósito:** Explorar cómo responder la pregunta clave del Entry Gate con 2 arquitecturas distintas.
No implementar — solo estudiar, prototipar, y decidir.

---

## La pregunta que el Entry Gate hará todos los días

```
Input:  "HOY el VIX está en 5__4__3, el BSI en 1__2__2, el CREDIT en 0__0__1"
Output: ¿qué señales están activas, qué tan confiables son, cuánto riesgo implican?
```

**Pregunta secundaria:** "De todas las señales que disparan en este estado, ¿cuántas lo hacen en rango vs fuera de rango? ¿Cuál es el retorno consolidado? ¿Qué señales anticipan vs confirman?"

---

## Opción 1: Tabla Única (8,453 × ~90)

### Estructura

```
┌─────────┬───────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│  fecha  │  vix_sk   │ vix_d1   │ vix_d2   │ vix_d3   │ vix_z_d1 │ v_z_d2   │ vix_z_d3 │ v_ovfl_t │
├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│2008-09-15│ 5__4__3   │    5     │    4     │    3     │   2.3    │   1.8    │   1.5    │   T0     │
│ ... (11 estaciones más: vvix, pcr, fg, sv5, skew, credit, yield, rotation, dxy, bsi)
├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ zz25_hit│ zz25_fav  │ zz25_mae │ zz25_mfe │ zz25_bar │ zz25_to  │ zz50_hit │ zz50_fav │ ...zz75  │
├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│  1      │  0.045    │ -0.008   │  0.052   │    2     │  False   │  1       │  0.032   │   ...    │
├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│tim_slot │ delta_piv │ cas_rev  │ pan_tot  │ capi     │ vix_cri  │ neu_cru  │ bsi_com  │ ...(37)  │
├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│  t=0    │    0      │   True   │   True   │  False   │  True    │  False   │  False   │   ...    │
└─────────┴───────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

### Consulta al Entry Gate

```python
# ENTRADA: VIX=5__4__3, BSI=1__2__2, CREDIT=0__0__1
import pandas as pd

# Cargar (8,453 filas, ~2ms en parquet)
df = pd.read_parquet("data/research/bar_snapshot.parquet")

# 1. Filtrar por el estado que nos interesa
mask = (df["vix_sk"] == "5__4__3")

# 2. Obtener todas las señales activas en este estado
senales_activas = [col for col in df.columns 
                   if col in CATALOGO and df.loc[mask, col].any()]

# 3. Para cada señal activa, consolidar estadística
resultado = {}
for senal in senales_activas:
    sub = df.loc[mask & df[senal]]

    resultado[senal] = {
        "n_total": len(sub),
        "n_en_rango": (sub["tim_slot"] != "ENTRE").sum(),
        "n_fuera": (sub["tim_slot"] == "ENTRE").sum(),
        "pct_en_rango": (sub["tim_slot"] != "ENTRE").mean(),
        "pct_anticipada": (sub["tim_slot"].isin(["t-2","t-1"])).mean(),
        "pct_coincidente": (sub["tim_slot"] == "t=0").mean(),
        "pct_confirmadora": (sub["tim_slot"].isin(["t+1","t+2"])).mean(),
        "zz25": {
            "hit_rate": sub["zz25_hit"].mean(),
            "ev_medio": sub["zz25_fav"].mean(),
            "ev_max": sub["zz25_fav"].max(),
            "ev_min": sub["zz25_fav"].min(),
            "ev_std": sub["zz25_fav"].std(),
            "mae_medio": sub["zz25_mae"].mean(),
            "mfe_medio": sub["zz25_mfe"].mean(),
            "bars_medio": sub["zz25_bars"].mean(),
            "profit_factor": sub.loc[sub["zz25_fav"] > 0, "zz25_fav"].sum() / 
                            abs(sub.loc[sub["zz25_fav"] <= 0, "zz25_fav"].sum())
              if (sub["zz25_fav"] <= 0).any() else float('inf')
        },
        "zz50": { ... },
        "zz75": { ... },
        "drawdown": calcular_drawdown(sub["zz25_fav"].values)
    }

# 4. Consolidado general del estado
resultado["_consolidado"] = {
    "n_senales_activas": len(senales_activas),
    "señales": senales_activas,
    "promedio_zz25_hit": df.loc[mask, senales_activas].mean(axis=1).mean()
}

return resultado
```

### Lo que responde inmediatamente

| Pregunta | Cómo |
|:---------|:-----|
| "¿Qué señales están activas en VIX 5__4__3?" | `filter by vix_sk` + `col.any()` |
| "¿Cuántas en rango vs fuera?" | `tim_slot != "ENTRE"` por señal |
| "¿Cuál es el retorno consolidado?" | `zz25_fav.mean()`, `.max()`, `.min()` |
| "¿Correlación entre señales?" | `df[senales_activas].corr()` |
| "¿Qué señales anticipan?" | `tim_slot in ["t-2","t-1"]` |
| "¿Qué señales confirman?" | `tim_slot == "t=0"` |

### Costo

| Operación | Tiempo |
|:----------|:-------|
| Cargar parquet (8,453 × 90) | ~2 ms |
| Filtrar por vix_sk | ~0.5 ms |
| Consolidar 10 señales activas | ~5 ms |
| **Total por consulta** | **< 10 ms** |

### ⚠️ Riesgos de Opción 1

1. **Todas las barras tienen first-passage, no solo las de episodio.** Las ~8,000 barras sin señal activa también tienen zz25_hit/fav calculados. Son mediciones "incondicionales" — miden qué pasa si entras en cualquier barra, no solo cuando hay señal. **Esto es correcto para el Entry Gate** (quiere saber qué esperar desde cualquier punto), pero **diferente a lo que miden los evaluadores hoy** (solo miden condicionado a señal).

2. **Señales posicionales** (4 que usan pivot_type): mapear al lake con ±2 barras hace que ~80% del lake tenga pivot_type=None. En esas barras, las señales posicionales siempre dan False. **Es correcto** — solo disparan cerca de pivotes — pero la muestra es pequeña.

3. **Drawdown por estado** requiere orden cronológico. Si un estado tiene solo 5 eventos en 20 años, el drawdown sobre esos 5 puntos no es representativo. **Se reporta igual** (dato mata relato), pero con flag `n_insuficiente`.

---

## Opción 3: Híbrido — Parquet + Vistas Pre-Agregadas

### Estructura

```
CAPA 1 — Dato primario:    bar_snapshot.parquet (8,453 × 90)
                            ↓ se agrega una vez (~2 min)
CAPA 2 — Vistas:            intelligence/estaciones/vix.json (pre-agregado por state_key)
                            intelligence/senales/panico_total.json (pre-agregado por señal)
                            intelligence/confluencia.json (pre-agregado por pares)
```

### Consulta al Entry Gate

```python
# ENTRADA: VIX=5__4__3, BSI=1__2__2, CREDIT=0__0__1

# 1. Cargar la vista PRE-CALCULADA del estado VIX 5__4__3
#    (no filtra, no agrega — ya está hecho)
vix_543 = json.load("intelligence/estaciones/vix.json")["states"]["5__4__3"]

# 2. Todas las señales y sus métricas ya están allí
resultado = vix_543["senales"]
# → cascade_reversal: pct_en_rango=91.67, zz25_hit=0.875, ev=0.025
# → panico_total: pct_en_rango=85.0, zz25_hit=0.917, ev=0.032

# 3. Si necesito cruzar con otras estaciones:
#    → consultar bsi.json["states"]["1__2__2"], credit.json["states"]["0__0__1"]
```

### Lo que responde inmediatamente

| Pregunta | Tiempo |
|:---------|:-------|
| "¿Qué señales activas en VIX 5__4__3?" | **< 1 ms** (JSON precargado, 0 operaciones) |
| "¿Cuántas en rango vs fuera?" | ✅ Ya está en `pct_en_rango` |
| "¿Retorno consolidado?" | ✅ Ya está en `zz25.ev` |
| "¿Correlación entre señales?" | ❌ **No está pre-calculada** — requiere cargar el parquet |
| "Drawdown de una señal en este estado?" | ✅ Ya está en `drawdown.max_drawdown` |
| "¿Qué pasa si cruzo VIX 5__4__3 + CREDIT 0__0__1?" | ⚠️ **No está pre-calculado** — requiere cargar 2 JSONs + cruzar señales comunes |

### ⚠️ Riesgos de Opción 3

1. **No responde preguntas nuevas.** Si alguien pregunta "¿qué señales funcionan en VIX 5__4__3 PERO SOLO en años recientes (2020+)?" — no está pre-calculado. Hay que re-agregar desde el parquet o re-barrer.

2. **Overflow dinámico.** Si el Entry Gate pregunta "VIX 5__4__3 con overflow T2 en D1" — ¿es un state_key separado o un filtro adicional? Claude propuso archivos separados; acordamos integrarlo en el state_key. Pero si el state_key no tiene el overflow codificado, la vista pre-agregada no lo captura.

3. **Multi-estación es costoso.** Para cruzar VIX+BSI+CREDIT, hay que cargar 3 JSONs y hacer el join en memoria. No es instantáneo.

---

## Comparación para la pregunta del Entry Gate

| Criterio | Opción 1 (Tabla única) | Opción 3 (Híbrido) |
|:---------|:----------------------:|:------------------:|
| **Speed: 1 estación, 1 estado** | 10 ms (filter + groupby) | **< 1 ms** (JSON lookup) |
| **Speed: 3 estaciones, 3 estados** | **10 ms** (mismos filtros) | **5 ms** (3 JSON lookups + merge) |
| **Speed: correlación entre señales** | **10 ms** (`.corr()`) | ❌ > 100 ms (cargar parquet + calcular) |
| **Speed: drawdown por estado** | 10 ms (ordenar + calcular) | **1 ms** (pre-calculado) |
| **Preguntas nuevas (no pre-vistas)** | ✅ **Cualquier consulta SQL** | ❌ **Solo lo pre-agregado** |
| **Flexibilidad de esquema** | ⚠️ Nueva señal = nueva columna | ⚠️ Nueva señal = nuevo JSON |
| **Complejidad de implementación** | **Una tabla, un script** | Dos scripts (barrido + agregación) |
| **Dato mata relato** | ✅ Datos crudos, sin interpretar | ✅ Igual |
| **Tamaño en disco** | ~500 KB | ~1 MB (parquet + ~20 JSONs) |

---

## Prototipo para decidir

Propongo construir **un solo script pequeño** que:

1. Cargue el lake + quants_obs
2. Evalúe las 37 señales
3. Para CADA barra, compute first_passage desde ese punto (zz25/50/75)
4. Clasifique timing vs pivote más cercano
5. **Guarde 2 archivos:**
   - `bar_snapshot.parquet` (Opción 1 — tabla única)
   - `intelligence/estaciones/vix.json` (Opción 3 — vista pre-agregada para VIX)

Luego compare:

```python
# Opción 1
df = pd.read_parquet("bar_snapshot.parquet")
sub = df[df["vix_sk"] == "5__4__3"]
print("OPCION 1:", sub["panico_total"].mean(), sub["zz25_fav"].mean())

# Opción 3
vix = json.load("intelligence/estaciones/vix.json")
print("OPCION 3:", vix["states"]["5__4__3"]["senales"]["panico_total"]["zz25"]["hit_rate"])
```

**Si los números coinciden** → ambas opciones son equivalentes en precisión. La decisión es solo de velocidad vs flexibilidad.

**Si no coinciden** → hay un error en la agregación de Opción 3 que hay que corregir.

---

## Preguntas para responder en la exploración

1. **¿Opción 1 responde todas las preguntas del Entry Gate sin pre-agregar?** El prototipo lo mostrará.
2. **¿El first-passage incondicional (desde TODA barra) es útil o confunde?** Los evaluadores miden condicionado a señal. El Entry Gate necesita incondicional (desde cualquier punto). Ambos son válidos, pero distintos.
3. **¿Cuánto tiempo toma la agregación de Opción 3?** Si es < 2 min, vale la pena tener las vistas pre-calculadas. Si es > 10 min, mejor consulta directa sobre parquet.
4. **¿Necesitamos multi-estación frecuentemente?** Si el Entry Gate siempre cruza VIX + BSI + CREDIT, la Opción 1 (una tabla, todos los sk juntos) puede ser más rápida que cargar 3 JSONs y mergearlos.
5. **¿El JSON pre-agregado puede incluir el drawdown por estado?** Sí, si se calcula durante la agregación. Si no, la Opción 1 lo calcula sobre la marcha en ~5 ms extra.
6. **¿Qué pasa cuando agregamos una señal nueva?** Opción 1: agregar columna al parquet (requiere re-barrido completo). Opción 3: agregar vista + re-agregar desde el parquet existente (sin re-barrido). **Opción 3 gana en mantenibilidad.**
7. **¿Qué pasa cuando cambia un state_key?** Si la calibración de bins cambia, el parquet de Opción 1 tiene los bins viejos — hay que re-barrer. Opción 3 igual (las vistas derivadas también se invalidan). **Ninguna gana.**

---

## Decisión esperada

| Si el Entry Gate necesita... | Elegir |
|:----------------------------|:-------|
| Respuesta instantánea (< 1 ms) y preguntas fijas | **Opción 3** (JSON pre-agregados) |
| Flexibilidad total para preguntas nuevas | **Opción 1** (parquet consultable) |
| Ambos → barrido produce parquet + script de agregación produce JSONs | **Híbrido (Opción 3)** |
| Menos archivos que mantener | **Opción 1** (1 parquet vs 11 JSONs + parquet) |
| Drawdown siempre disponible y exacto | **Opción 1** (orden cronológico preservado) |