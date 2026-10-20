# GUÍAS / PROMPT — CORRECCIÓN DEL DESFASE DE EDGES ENTRE GATE Y TABLAS (HALLAZGO N-9)

**Fecha:** 13-Oct-2026
**Alcance:** UN (1) HALLAZGO, UNA (1) CORRECCIÓN. Unificar la fuente de los edges de binning.
**Nota:** el ejecutor no conoce este documento ni los previos. Es **autocontenido**: cada cifra trae su
forma de reproducción.

---

## 0. PRINCIPIO (declarado, no negociable)

**Dos consumidores que clasifican el MISMO eje no pueden usar edges distintos.** Hoy lo hacen: el
`QualityEntryGate` y las tablas de tríada parten el mismo eje TH/FI/TW con cortes diferentes. El mismo
valor de amplitud cae en bins distintos según quién lo lea —y el bin decide la probabilidad, que decide
la asignación.

**Y un edge escrito a mano no puede converger.** Si los dos lados están congelados, el desajuste no es una
deuda que se paga sola: es **permanente**. Antes de `v3.1`, la tabla **recalculaba** sus edges en cada
corrida y podía —en principio— acercarse al gate. Después de `v3.1` ya no puede moverse.

**Corolario:** una corrección que cambia 1 de cada 8 días de clasificación **no se aprueba por inspección
de código**. Se aprueba midiendo qué cambia en el backtest.

---

## 1. ESTADO VERIFICADO (13-Oct-2026)

### 1.1 Los tres juegos de edges que conviven

```python
# GATE — quality_entry_gate.py:47-57  (hardcodeados)
S5_EDGES  = {"TH":[27.6,54.8,82.8,93.5], "FI":[20.0,46.7,76.9,90.4], "TW":[16.7,41.9,75.0,90.0]}
SV5_EDGES = {"TH":[24.6,37.2,58.0,73.8], "FI":[27.0,37.8,55.5,68.4], "TW":[23.9,34.5,50.8,65.4]}

# TABLA S5 — s5_triad_table.json v3.1 (derivados: percentiles 10/30/70/90 de 83.183 obs)
bin_edges = {"TH":[28.6,55.0,82.7,93.3], "FI":[20.7,46.7,76.6,90.0], "TW":[16.7,42.3,74.7,89.6]}

# TABLA S5V — s5v_triad_table.json v3.1
bin_edges = {"TH":[18.2,33.3,60.0,80.0], "FI":[20.0,34.3,58.8,76.9], "TW":[16.7,31.0,54.8,74.0]}
```

**Nota:** los edges de las tablas **no se movieron al regenerar** (S5 y S5V v3.1 dan los mismos valores
que v2.0). Fueron la última calibración del 07-oct, ahora congelada… no: **en la tabla S5/S5V v3.1 SÍ se
derivan dinámicamente**. Lo que está congelado es **el lado del gate**.

### 1.2 Magnitud del desajuste (3 mediciones independientes, mismo resultado)

Deltas máximos por eje:

```
S5   TH 1,0 pp · FI 0,7 pp · TW 0,4 pp
SV5  TH 6,4 pp · FI 8,5 pp · TW 8,6 pp
```

Días que cambian de bin (serie completa 1980 → 2026-10-12):

```
S5TH    11.539 días →   149 distintos (  1,29 %)
S5FI    11.689 días →   122 distintos (  1,04 %)
S5TW    11.719 días →   160 distintos (  1,37 %)
SV5TH   11.539 días → 2.362 distintos ( 20,47 %)
SV5FI   11.689 días → 2.922 distintos ( 25,00 %)
SV5TW   11.719 días → 3.033 distintos ( 25,88 %)
```

### 1.3 Magnitud de la CORRECCIÓN

Si el gate adopta los edges de la tabla:

```
días totales (6 series) : 69.894
días que cambiarían     :  8.748   = 12,5 %
```

⇒ **No es cosmético.** La corrección mueve **uno de cada ocho días** de clasificación, y el grueso está
en SV5 (**uno de cada cuatro**).

**⚠️ TRAMPA DECLARADA — leer antes de tocar nada:** `train_s5_triad.py:65-70` contiene

```python
# Canonical bin edges (SSOT)
CANONICAL_BIN_EDGES = {
    "TH": [28.6, 55.0, 82.7, 93.3],
    "FI": [20.7, 46.7, 76.6, 90.0],
    ...
}
```

**Ese literal es CÓDIGO MUERTO.** Barrido del archivo: `CANONICAL_BIN_EDGES` aparece **sólo en su propia
definición (L66), en ningún uso.** El SSOT real del trainer es el cuantil dinámico
(`train_s5_triad.py:446-448` y `train_s5v_triad.py:470-473`):

```python
BIN_PERCENTILES = [0.10, 0.30, 0.70, 0.90]
"TH": [round(float(c), 2) for c in all_th.quantile(q).tolist()],
```

⇒ Un corrector que lea «Canonical bin edges (SSOT)» y una el gate con él **uniría el gate a un literal
muerto**, con riesgo de que ya no represente la población. **La unificación debe apuntar al `bin_edges`
escrito por las tablas en su última corrida, no a este literal.** Y ese comentario `(SSOT)` debe
corregirse en el mismo cambio: hoy es una etiqueta falsa.

### 1.4 El desajuste no es simétrico en importancia

`SV5_EDGES` del gate (`[24.6,37.2,58.0,73.8]`) es el conjunto **más alejado** de la tabla
(`[18.2,33.3,60.0,80.0]`). Y `SV5` es justamente el eje que alimenta la clave **7D** que decide
`spy_joint ∈ TOP_DISTRIBUTION_STATES` — el disparador de `is_pre_crash_distribution`.

⇒ El desajuste no vive en un sitio periférico: **vive en la condición que declara la distribución
pre-crash.**

---

## 2. POR QUÉ ESTA CORRECCIÓN ES LIMPIA ARQUITECTÓNICAMENTE

**El precedente ya existe en el propio gate.** `quality_entry_gate.py:71-104` carga umbrales de un fact
store de dominio:

```python
@staticmethod
def _load_turbulence_thresholds() -> tuple[float, float, float]:
    """Dynamically load empirical thresholds from sv5_turbulence_fact_store.json (Rule 21)."""
    DECLARED_FALLBACK = (11.21, 8.82, 12.06)
    fact_path = Path(__file__).resolve().parent.parent / "rules" / "sv5_turbulence_fact_store.json"
    try:
        if fact_path.exists():
            with open(fact_path, "r", encoding="utf-8") as f:
                data = json.load(f)
    ...
```

⇒ **El gate YA lee un JSON de `domain/rules/` con fallback declarado.** Leer los `bin_edges` de
`s5_triad_table.json` / `s5v_triad_table.json` es **el mismo patrón, no una arquitectura nueva.** No hay
excusa de capas.

---

## 3. EL CAMBIO

**Objetivo: una sola fuente de verdad por eje. Los edges del gate dejan de ser literales.**

1. **El gate lee los `bin_edges` de las tablas** (mismo patrón que `_load_turbulence_thresholds`):
   - `S5_EDGES` ← `s5_triad_table.json → bin_edges`
   - `SV5_EDGES` ← `s5v_triad_table.json → bin_edges`
2. **Fallback declarado y explícito** (cold-start / archivo ausente), con los valores actuales del gate
   como último recurso — **declarado en el código, no silencioso**. Si el fallback se usa, **debe dejar
   rastro en el log**.
3. **`LABELS` no se toca**: `["<<", "<", "~", ">", ">>"]` (5 etiquetas, 4 cortes) — contrato intacto.
4. **No cambiar el espacio de clave 7D** `TH|FI|TW|V_TH|V_FI|V_TW|Dir`, ni `TOP_DISTRIBUTION_STATES`
   (que es un literal aparte y **no depende de los edges**: sigue siendo la misma lista de estados).

**Alternativa admitida si se decide no acoplar** (D-1): **desacople declarado por escrito** —documentar
en el propio gate que sus edges son intencionalmente independientes, con el mismo número medido
(20,5–26,0 % de los días) y la razón. Lo que **no** se admite es dejarlo como está: **no declarado**.

---

## 4. CRITERIOS DE ACEPTACIÓN (medibles)

```
A-1  Existe UNA fuente de verdad por eje. Reportar de dónde lee el gate cada uno de los 6 conjuntos
     (S5 TH/FI/TW y SV5 TH/FI/TW) y citar el archivo y la clave.
A-2  Ejercicio de convergencia: para las 6 series, días con bin distinto entre gate y tabla = 0.
     Reportar el conteo por serie (hoy: 149/122/160/2.362/2.922/3.033).
A-3  El fallback NO se usa en operación normal. En el log de una corrida normal no debe aparecer.
A-4  `LABELS` y el formato de clave 7D intactos; `TOP_DISTRIBUTION_STATES` sin cambios de contenido.
A-5  BENCHMARK DELTA OBLIGATORIO: como la corrección mueve 8.748 días (12,5 %), se mide el backtest
     ANTES y DESPUÉS sobre la misma base y ventana. Se reportan: acciones SPY finales, Max Drawdown,
     win rate y nº de episodios por modo. NO se aprueba sin esta tabla.
A-6  Si el delta es negativo (empeora), NO se revierte a ciegas: se reporta y se decide con el número.
```

### Advertencia de método (por el caso reciente)

Una auditoría previa de este proyecto afirmó «se conserva exactamente el 100 % de las celdas y las
métricas» y **era falso**: 89 de 391 celdas cambian de clase a ±0,10. **Ninguna afirmación de
conservación se acepta sin la medición que la respalde.** Aplicar lo mismo aquí: si alguien sostiene que
«el gate no se altera», que muestre el conteo.

---

## 5. NO ANCLAR (dos caminos deben converger)

Reportar el efecto por **dos vías independientes**:

1. **Vía código:** qué edges usa el gate en runtime (imprimirlos desde el objeto cargado).
2. **Vía dato:** reclasificar las 6 series con cada juego y contar los días distintos.

Deben dar 0 diferencias tras la corrección. Si no convergen, **se reporta la discrepancia; no se ajusta
el número para que cuadre.**

---

## 6. DECISIONES A ADJUDICAR

```
D-1  ¿El gate ADOPTA los edges de las tablas, o se declara el desacople? (Recomendado: adoptar —
     el precedente ya existe y el desacople perpetúa 20-26 % de días discrepantes en SV5.)
D-2  ¿La tabla es el SSOT, o el gate? Si la tabla se recalcula cada corrida (ya lo hace), es el SSOT
     natural. Confirmarlo por escrito.
D-3  ¿Qué pasa con los edges del gate para las series que NO tienen tabla (si existe alguna)? Declararlo.
D-4  ¿El cambio se acompaña de una recalibración de `±0,10` de `net_bias`? Ese umbral **no tiene
     derivación documentada en el repo** y con los edges unificados podría necesitar revisión. Se
     declara su origen o se recalibra — pero no se toca en esta corrección.
```

---

## 7. LO QUE **NO** ENTRA AQUÍ (declarado, para no dispersar)

```
· D-5 / N-3: validación predictiva fuera de muestra de la tríada. Sigue sin existir (los tests son de
  contrato: 50 asserts, 0 referencias a backtest/return/pnl). Es la deuda mayor, pero es MEDICIÓN,
  no corrección de código.
· N-6: `ENABLE_TRIAD_AUTORETRAIN` no está definido ⇒ auto-retrainer apagado por defecto. Decisión de
  operación.
· N-8: `same_bar_pair` es columna huérfana (4.045.616 filas, 0 TRUE, 0 archivos .py la mencionan).
· N-10: tamaño de los artefactos (17.009.011 bytes los 4; parse de 271 ms sin carga lazy).
· Docstring del trainer S5V: afirma que `QualityEntryGate` consume los artefactos. **Verificado: el gate
  tiene 0 menciones de la tríada.** Corregir la línea.
```

---

## 8. CIERRE ESPERADO

```
· Un solo SSOT de edges por eje, declarado y con fallback que deja rastro.
· 0 días de discrepancia de binning entre gate y tabla en las 6 series.
· Benchmark delta medido y reportado (antes/después) — es el número que decide.
· Ninguna afirmación de «no cambia nada» sin su conteo.
```
