# CORRECCIÓN PRODUCCIÓN — σ-Overflow (desbordamiento de escala)

> Estado: ESPECIFICACIÓN (pendiente implementar en producción).
> Flag de Juan Andrés, 17-Ago-2026.

---

## PROBLEMA

Las bandas σ calibradas (PERCENTILES_D1_GAUSS) saturan en +2σ (P97.7).
Cuando el dato desborda la escala, TODO se etiqueta con el último label:

```
VIX: edge CRISIS_SPIKE = 40.73 (+2σ)
  VIX 41 → CRISIS_SPIKE  (2.8σ)
  VIX 82 → CRISIS_SPIKE  (10.7σ)  ← 2008/2020

Ambos son "CRISIS_SPIKE", pero son eventos FUNDAMENTALMENTE distintos.
La resolución se pierde EXACTAMENTE donde viven los eventos más grandes.
```

Evidencia: VIX max = 82.7 = 10.7σ. Los 193 días de CRISIS_SPIKE van de
40.7 a 82.7 — el "over-correction" (rebote) es proporcional a la profundidad.

---

## SOLUCIÓN — sigma depth (profundidad continua)

### 1. En el fact store (v3_fact_table_engine.py)
```
Al generar los edges, GUARDAR también μ y σ de la serie:
  "sigma_baseline": {"mu": 19.44, "sigma": 7.73}

Los edges ya son los cuantiles σ:
  P2.3=-2σ, P15.9=-1σ, P50=media, P84.1=+1σ, P97.7=+2σ
```

### 2. En el lookup (cada *_lookup.py, _classify_d1)
```
Cuando el valor DESBORDA la escala (más allá de ±3σ), calcular la depth:

  if val > (mu + 3*sigma):   # > +3σ — desbordamiento REAL
      label = labels[-1]          # CRISIS_SPIKE (discreto)
      depth = (val - mu) / sigma  # cuántas σ (continuo) → ej. 10.7
      overflow_flag = "UPPER"
  elif val < (mu - 3*sigma): # < -3σ
      label = labels[0]           # DEEP_COMPLACENCY
      depth = (val - mu) / sigma  # negativo → ej. -3.5
      overflow_flag = "LOWER"
  else:
      depth = None    # dentro de ±3σ, el label discreto BASTA
      overflow_flag = None

IMPORTANTE: el threshold es ±3σ, NO ±2σ (el último edge).
  +2σ..+3σ = extremo "normal" → label discreto suficiente
  > +3σ     = desbordamiento REAL → depth continua necesaria
```

### 3. En el MarketMETAR (salida de cada servicio)
```
Agregar campo opcional:
  "sigma_depth": 10.7   # solo cuando desborda (overflow)
  "overflow_flag": "UPPER" | "LOWER" | null

El SIGMET debe capturar el overflow como EVENTO MUY ESPECIAL:
  "VIX en 10.7σ — apocalíptico" ≠ "VIX en 2.8σ — crisis moderada"
```

---

## POR QUÉ ES UN EVENTO MUY ESPECIAL

```
El overflow es RARÍSIMO (VIX > +3σ = 1.69% de los días, > +6σ = 0.26%).
Es donde viven los cisnes negros y los rebotes más violentos:

  VIX 41 (2.8σ) → rebote moderado
  VIX 82 (10.7σ) → rebote apocalíptico (+21.68% en rotación module)

La depth ES la señal: a mayor desbordamiento, mayor el "over-correction".
```

---

## IMPLEMENTACIÓN (orden)

```
1. v3_fact_table_engine.py: guardar μ y σ en _documentation
2. Cada *_lookup.py _classify_d1: calcular depth cuando desborda
3. Cada *_metar_service.py: exponer sigma_depth + overflow_flag en to_dict()
4. market_sigmet_hazard_service.py: capturar overflow como evento especial
5. Test: guard que verifica sigma_depth se calcula cuando val > edges[-1]
```

---

## REGLA DE ORO (mantener)

```
NO reemplazar el label discreto. AGREGAR la depth continua.
  label = "CRISIS_SPIKE" (para el state_key D1×D2×D3, sin cambios)
  depth = 10.7σ (para el guidance, solo cuando desborda)

El state_key NO cambia (compatibilidad con cascade_conviction).
La depth es un CAMPO ADICIONAL para el TAF/SIGMET.
```
