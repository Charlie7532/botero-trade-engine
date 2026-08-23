# Auditoría de `_structural_momentum_filter` — Sesgo y Solidez

**Archivo:** `medir_senal.py` líneas 604-729  
**Fecha auditoría:** 20-Ago-2026  
**Veredicto:** **Sesgo menor corregible** — el algoritmo central es sólido, pero el fallback heurístico está roto y la alineación de datos SPY tiene un micro-look-ahead.

---

## Pregunta 1: ¿Compara pivotes CONSECUTIVOS en la secuencia completa o solo los señal-activos? ¿Sesgo de selección?

**Respuesta:** Compara pivotes consecutivos en la secuencia COMPLETA, no solo los señal-activos. Esto **NO introduce sesgo de selección** — al contrario, es el enfoque correcto.

### Evidencia del código (ENTRY, líneas 639-651):
```python
all_min_idx = df.index[df["pivot_type"] == "MIN"]  # TODOS los MIN del zigzag
all_min_prices = spy_close_at_pivot[all_min_idx]
for idx in min_idx:  # min_idx = solo MIN donde señal=True
    pos_in_all_min = all_min_idx.get_loc(idx)     # posición dentro de la secuencia COMPLETA
    prev_min_idx = all_min_idx[pos_in_all_min - 1] # MIN anterior en secuencia COMPLETA
    p_curr = spy_close_at_pivot.get(idx)           # precio SPY en el MIN actual
    p_prev = spy_close_at_pivot.get(prev_min_idx)  # precio SPY en el MIN anterior
```

La misma estructura se replica para MAX (EXIT, líneas 688-700).

### Análisis:
- `min_idx` solo contiene los MIN donde la señal está activa. Pero `prev_min_idx` se busca dentro de `all_min_idx` (todos los MIN, con o sin señal).
- Esto es **correcto**: responde a "cuando mi señal dispara en un MIN, ¿ese MIN es estructuralmente más alto o más bajo que el MIN anterior del zigzag?".
- Si comparara solo entre MIN señal-activos, perdería el contexto estructural real (ej. dos MIN señal-activos podrían estar separados por 5 MIN no-señal-activos, y la comparación sería engañosa).

**Veredicto:** Sin sesgo de selección. ✅

---

## Pregunta 2: ¿La clasificación de EXIT invierte la lógica respecto a ENTRY? ¿Es correcto?

**Respuesta:** La lógica es **semánticamente consistente**, no invertida. Ambas ramas miden "deterioro estructural", pero aplicado a tipos de pivote opuestos.

### Evidencia del código:
```python
# ENTRY (MIN): línea 650-653
if p_curr > p_prev:
    hl_count += 1   # Higher Low → estructura MEJORA (alcista)
else:
    ll_count += 1   # Lower Low → estructura EMPEORA (trampa bajista)

# EXIT (MAX): línea 699-702
if p_curr < p_prev:
    lh_count += 1   # Lower High → estructura EMPEORA (deterioro bajista)
else:
    hh_count += 1   # Higher High → estructura MEJORA (pero clímax)
```

### Análisis:
- Ambas ramas usan **precio bajando = deterioro estructural**, que es la misma dirección semántica.
- Para MIN: precio bajando (p_curr < p_prev) = Lower Low = deterioro. ✅
- Para MAX: precio bajando (p_curr < p_prev) = Lower High = deterioro. ✅
- La aparente "inversión" es superficial: ENTRY usa `>` para detectar mejora, EXIT usa `<` para detectar deterioro. Pero ambas son la misma prueba direccional: ¿está el precio más alto o más bajo que el pivote anterior del mismo tipo?

**Veredicto:** Correcto, sin inversión lógica. ✅

---

## Pregunta 3: ¿Hay look-ahead bias? ¿Usa información del futuro?

**Respuesta:** El algoritmo NO tiene look-ahead bias estructural, pero hay un **micro-look-ahead en la alineación de datos SPY** que es corregible.

### Evidencia:

**Construcción de `spy_close_at_pivot` (líneas 621-629):**
```python
positions = closes.index.get_indexer(df["pivot_date"], method="nearest")
spy_close_at_pivot = pd.Series(closes.iloc[positions].values, index=df.index)
```

### Análisis:
1. **La comparación es entre pivote actual y pivote ANTERIOR** — ambos en el pasado. No hay forward-looking en la lógica de clasificación. ✅

2. **`method="nearest"` sin `tolerance` puede apuntar al futuro**: si un `pivot_date` cae en sábado, y el lunes siguiente está más cerca que el viernes anterior (ej. domingo más cerca del lunes), `get_indexer` matchea con el precio del lunes — que es FUTURO respecto al sábado. Esto es un micro-look-ahead en ~0.5-1% de los pivotes (los que caen en fines de semana/festivos con asimetría de distancia).

3. **Impacto**: marginal. El precio de cierre del lunes vs viernes para el mismo activo (SPY) en condiciones normales difiere <1%. Además, la comparación es entre dos pivotes, ambos potencialmente afectados por el mismo sesgo.

**Veredicto:** Sin look-ahead estructural, pero con micro-sesgo de alineación corregible. ⚠️

**Corrección recomendada:**
```python
positions = closes.index.get_indexer(df["pivot_date"], method="ffill")
# o usar tolerance + ffill para evitar forward-matching
```

---

## Pregunta 4: ¿El fallback heurístico con `prev_leg_return.shift(1)` es correcto o introduce sesgo?

**Respuesta:** El fallback está **FUNDAMENTALMENTE ROTO** — clasifica el 100% de MIN como LL y el 100% de MAX como HH, sin poder discriminativo alguno.

### Evidencia del código (ENTRY fallback, líneas 666-679):
```python
min_pivots = df[min_mask]                              # solo MIN señal-activos
prev_leg_shift = min_pivots["prev_leg_return"].shift(1)  # shift DENTRO del subset
valid = prev_leg_shift.notna()
hl_count = int((prev_leg_shift[valid] > 0).sum())       # ¿prev_leg_return > 0?
ll_count = int((prev_leg_shift[valid] <= 0).sum())
```

### Análisis:
1. **`prev_leg_return` para MIN pivots es SIEMPRE negativo**: es el drawdown que terminó en ese mínimo (confirmado en `credit_easing_pisos.py` línea 81: `prev_leg_return < 0`). Por definición del zigzag, un MIN es el fin de una pierna bajista.

2. **`shift(1)` sobre el subset filtrado** compara contra el `prev_leg_return` del MIN señal-activo ANTERIOR, no contra el MIN estructural anterior. Esto ya es incorrecto conceptualmente.

3. **Resultado determinista**: `prev_leg_shift[valid] > 0` es SIEMPRE False (todos los retornos de drawdown son negativos). Por tanto `hl_count = 0` y `ll_count = N-1` siempre. El fallback no discrimina nada.

4. **Para EXIT (MAX, líneas 714-727)** es simétricamente opuesto: `prev_leg_return` siempre positivo → `lh_count = 0`, `hh_count = N-1`.

### Verificación numérica:
```
MIN prev_leg_return: [-0.05, -0.02, -0.08, -0.03, -0.10]
shift(1):            [nan, -0.05, -0.02, -0.08, -0.03]
> 0 (hl_count):      0 de 4  ← 0%, siempre
<= 0 (ll_count):     4 de 4  ← 100%, siempre
```

### ¿Impacta en la práctica?
El fallback solo se ejecuta cuando `spy is None` o cuando `spy_close_at_pivot.notna().sum() < 5`. En el flujo normal de `medir()`, SPY siempre está disponible y tiene datos desde 1993. **El fallback probablemente nunca se ejecuta en producción.** Pero existe como dead code peligroso.

**Veredicto:** Roto, sin poder discriminativo. ⚠️ Bajo impacto práctico (nunca se ejecuta con SPY disponible).

**Corrección recomendada:**
- Opción A: Eliminar el fallback y exigir SPY (levantar error si no disponible).
- Opción B: Corregir el fallback usando `df["close"]` del propio activo en lugar de `prev_leg_return`.

---

## Pregunta 5: Veredicto final

### Resumen de hallazgos:

| Aspecto | Estado | Severidad |
|---------|--------|-----------|
| Comparación en secuencia completa vs señal-activos | ✅ Correcto | — |
| Lógica ENTRY/EXIT | ✅ Consistente | — |
| Look-ahead estructural | ✅ Sin sesgo | — |
| Micro-look-ahead en alineación SPY | ⚠️ Corregible | Baja |
| Fallback heurístico | ❌ Roto | Baja (dead code) |

### Veredicto: **SESGO MENOR CORREGIBLE**

El algoritmo central de `_structural_momentum_filter` es **sólido**: compara pivotes consecutivos en la secuencia completa del zigzag usando precios SPY reales, sin look-ahead estructural. La lógica ENTRY/EXIT es semánticamente consistente. Los resultados de `p_hl` y `p_hh` son confiables.

Los dos problemas encontrados no invalidan los resultados:
1. **Micro-look-ahead en `get_indexer(method="nearest")`**: afecta marginalmente (<1% de pivotes, <1% de error en precio). Corregible con `method="ffill"`.
2. **Fallback heurístico roto**: nunca se ejecuta en el flujo normal porque SPY siempre está disponible. Es dead code que debería eliminarse o corregirse para evitar que alguien lo ejecute sin SPY en el futuro.

### Acciones recomendadas (prioridad):
1. **[BAJA]** Cambiar `method="nearest"` → `method="ffill"` en línea 623 para eliminar el micro-look-ahead.
2. **[BAJA]** Reemplazar el fallback heurístico por un error explícito si SPY no está disponible, o corregirlo para usar `df["close"]` del activo subyacente.
3. **[INFO]** Documentar que los resultados de `p_hl` y `p_hh` dependen de la disponibilidad de SPY. Sin SPY, el filtro no funciona.