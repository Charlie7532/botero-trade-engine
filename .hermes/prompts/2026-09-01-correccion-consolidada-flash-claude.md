# PROMPT DE CORRECCIÓN — Auditoría Consolidada (Flash + Claude) + Cobertura de Métricas

**Origen:** deepseek/deepseek-v4-flash (Hermes) + Claude Opus
**Propósito:** 12 correcciones identificadas por auditoría combinada de los cambios de Gemini

---

## 🔴 ESTÁNDAR DE NOMENCLATURA — Regla del proyecto

### RN1 — Renombrar `señales.py` → `signals.py` (eliminar caracteres especiales del español)

**Regla del proyecto (recordatorio):** Todos los nombres de archivos, módulos, clases, funciones, variables y documentación deben estar en **inglés**. Los caracteres especiales del español (`ñ`, `í`, `é`, `á`, `ó`, `ú`) no deben usarse en nombres de archivos ni en código.

**Archivo a renombrar:**
```
research/01_señales_entry_exit/arnes/señales.py  →  research/01_señales_entry_exit/arnes/signals.py
```

**Archivos que importan `arnes.señales` (actualizar import):**

| Archivo | Línea | Import actual | Import corregido |
|:--------|:-----:|:--------------|:-----------------|
| `arnes/__init__.py` | 7 | `from . import señales as _señales` | `from . import signals as _señales` |
| `recompute_signals_fact_store_triad_v2.py` | 23 | `import arnes.señales` | `import arnes.signals` |

**Nota:** El alias `as _señales` en `__init__.py` se mantiene para compatibilidad interna. Lo que cambia es el nombre del archivo físico.

**Comando de verificación:**
```bash
cd /root/botero-trade
# Verificar que no queda ninguna referencia a arnes.señales
grep -rn "arnes\.señales\|from arnes.señales\|import arnes.señales" --include="*.py" | grep -v __pycache__
# Debe retornar 0 resultados
# Verificar que el archivo existe con el nuevo nombre
ls -la research/01_señales_entry_exit/arnes/signals.py
```

---

## 🔴 ERRORES DE GEMINI VERIFICADOS (3)

### E1 — `vvix_entry.fecha_inicio_valida` incorrecta
**Archivo:** `arnes/signals.py`
**Gemini puso:** `"2006-01-03"`
**Debería ser:** `"2006-03-06"` (lanzamiento oficial VVIX CBOE)
**Acción:** Verificar si CBOE publicó data retroactiva. Si no, corregir a 2006-03-06.

### E2 — `neutral_crush_entry` y `neutral_spike_exit` mal mapeadas en `contencion.py`
**Archivo:** `arnes/contencion.py` — `SEÑAL_ESTACIONES`
**Gemini mapeó:** `"neutral_crush_entry": {"vix"}`
**Correcto:** `"neutral_crush_entry": {"vix", "bsi", "credit", "yield_curve", "vvix", "sv5_turbulence", "fg", "skew", "pcr", "rotation", "dxy"}` (las 11 estaciones de `_STATIONS_E7`)
**Igual:** `"neutral_spike_exit"`

### E3 — `euforia_v2` mal mapeada en `contencion.py`
**Gemini mapeó:** `"euforia_v2": {"vix", "bsi"}`
**Correcto:** `"euforia_v2": {"bsi"}` (V2 eliminó el filtro VIX de V1)

---

## 🟡 PUNTOS CIEGOS RESIDUALES (2)

### PC-A — `sorpresa_total` sin inception constraints
**Archivo:** `arnes/signals.py` — función `_sorpresa_total`
**Problema:** Lee `_surprise_vector(df)` que internamente usa TODAS las estaciones. Pre-2007, 3-5 estaciones no existen (SKEW, FG, VVIX, PCR, Credit). `skipna=True` las ignora silenciosamente, pero la sorpresa se computa con 6-8 estaciones en vez de 11.
**Fix:** Agregar `fecha_inicio_valida="2007-04-11"` (inicio de Credit, la más tardía de las estaciones que lee) a `_sorpresa_total`, o documentar que la sorpresa pre-2007 es incompleta.

### PC-B — Baseline del evaluador_general usa muestreo uniforme, no pondera por régimen
**Archivo:** `evaluador_general.py` L181-186
**Problema:** `np.arange(0, n_total - 20, 5)` muestrea cada 5ta barra uniformemente. Esto sobrepondera regímenes laterales (donde SPY pasa más tiempo) y subpondera crisis.
**Nota:** El evaluador vela-a-vela SÍ tiene desglose por régimen ALZA/BAJA. El evaluador general no. Es una asimetría de diseño, no un error.

---

## 🔴 GAPS DE MÉTRICAS (de mi auditoría de cobertura)

### G1 — EV del episodio (retorno acumulado first_bar → last_bar)
**Archivo:** `evaluador_general.py`
**Problema:** No existe métrica de retorno acumulado del episodio completo.
**Fix:** Agregar `ev_episodio` a `poblacion`: retorno acumulado `spy_ret_1d` desde `first_bar` hasta `last_bar`.

### G2 — EV post-episodio (retorno last_bar → siguiente cambio de estado)
**Archivo:** `evaluador_general.py`
**Problema:** No existe métrica de qué pasa después del episodio.
**Fix:** Agregar `ev_post_episodio`: retorno desde `last_bar` hasta `last_bar + duracion_episodio` (o siguiente cambio de estado).

### G3 — MAE_p10 en first-passage
**Archivo:** `evaluador_general.py` + `evaluador_vela_a_vela.py`
**Problema:** Existe MAE_medio y MAE_p90, pero no MAE_p10 (dolor extremo).
**Fix:** Agregar `mae_p10` a las escalas zigzag.

### G4 — Rendimiento por slot para zz50 y zz75 (no solo zz25)
**Archivo:** `evaluador_general.py` L360-383
**Problema:** `rendimiento_por_slot` solo se calcula para zz25.
**Fix:** Calcular para las 3 escalas.

### G5 — `delta_medio` (distancia media al pivote más cercano)
**Archivo:** `arnes/timing.py` o evaluadores
**Problema:** No existe métrica de distancia media al pivote más cercano.
**Fix:** Agregar `delta_medio` al `timing_canonico`.

### G6 — Clasificación "señal de fondo" (cadencia < 10)
**Archivo:** `evaluador_general.py`
**Problema:** Existe `es_diamante` (n_episodios < 21) pero no `es_fondo` (cadencia < 10).
**Fix:** Agregar `es_fondo: cadencia_1_en_n_barras < 10` a la población.

---

## 🟡 CORRECCIÓN DE DISEÑO

### D1 — `VENTANA_DIAS` → `VENTANA_BARRAS` en forensia F3
**Archivo:** `evaluador_vela_a_vela.py` L357
**Problema:** `pd.Timedelta(days=VENTANA_DIAS)` usa días calendario, no barras de trading. Un viernes→lunes cuenta como 3 días calendario pero 1 barra.
**Fix:** Cambiar a `trading_index` con barras de trading en lugar de días calendario.

---

## ORDEN DE EJECUCIÓN

| # | Prioridad | Corrección | Archivos | Esfuerzo |
|:-:|:---------:|:-----------|:---------|:---------|
| **RN1** | 🔴 P0 | Renombrar `señales.py` → `signals.py` + actualizar imports | 2 archivos | 5 min |
| **1** | 🔴 P0 | E2: Mapear neutral_crush/spike a 11 estaciones en `contencion.py` | 1 | 2 min |
| **2** | 🔴 P0 | E3: Corregir euforia_v2 a `{"bsi"}` en `contencion.py` | 1 | 1 min |
| **3** | 🔴 P0 | G1: EV del episodio (retorno acumulado) | `evaluador_general.py` | 10 min |
| **4** | 🔴 P0 | G2: EV post-episodio | `evaluador_general.py` | 10 min |
| **5** | 🟡 P1 | E1: Verificar/corregir fecha_inicio_valida de vvix_entry | `signals.py` | 2 min |
| **6** | 🟡 P1 | PC-A: fecha_inicio_valida para sorpresa_total | `signals.py` | 5 min |
| **7** | 🟡 P1 | G3: MAE_p10 en ambas escalas | 2 evaluadores | 5 min |
| **8** | 🟡 P1 | G4: rendimiento_por_slot para zz50 y zz75 | `evaluador_general.py` | 15 min |
| **9** | 🟡 P1 | G5: delta_medio en timing_canonico | `arnes/timing.py` | 5 min |
| **10** | 🟡 P1 | G6: señal de fondo (cadencia < 10) | `evaluador_general.py` | 3 min |
| **11** | 🟡 P1 | D1: VENTANA_DIAS → VENTANA_BARRAS | `evaluador_vela_a_vela.py` | 5 min |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 0. No mas arnes.señales
grep -rn "arnes\.señales\|from arnes.señales\|import arnes.señales" --include="*.py" | grep -v __pycache__
# → 0 resultados

# 1. Contencion correcto
grep -n "neutral_crush_entry\|neutral_spike_exit\|euforia_v2" research/01_señales_entry_exit/arnes/contencion.py

# 2. Tests pasan
cd /root/botero-trade && python3 -m pytest tests/ backend/modules/entry_decision/tests/ -v

# 3. Evaluador general produce nuevas metricas
PYTHONPATH=/root/botero-trade/research/01_señales_entry_exit:/root/botero-trade backend/.venv/bin/python -c "
from evaluador_general import evaluar_senal, cargar_entorno_evaluacion
cargar_entorno_evaluacion()
r = evaluar_senal('cascade_reversal')
pob = r['poblacion']
print('ev_episodio:', pob.get('ev_episodio'))
print('ev_post_episodio:', pob.get('ev_post_episodio'))
print('es_fondo:', pob.get('es_fondo'))
"
```