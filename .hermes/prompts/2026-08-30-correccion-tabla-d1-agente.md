# CORRECCIÓN — Tabla D1: simplificar a lo que el agente necesita

**Archivo:** `.agents/references/metar/gaussian_scale_policy.md`
**Problema:** La tabla D1 (líneas 41-48) tiene una columna "Ejemplos Canónicos" con 3 estaciones (VIX, FG, Credit) que son irrelevantes para el agente. El agente no necesita saber los labels de cada estación — necesita la escala numérica y la referencia para resolver labels si los requiere.

---

## QUÉ HACER: Reemplazar la tabla D1 actual por una versión sin ejemplos de labels

### Estado actual (INCORRECTO) — líneas 41-48:

```
| Bin Index | Range | Percentile Band | Population % | Semantic Role | Ejemplos Canónicos |
|:---:|---|:---:|:---:|---|---|
| 0 | val < −2σ | P0 → P2.28 | 2.28% | Extremo inferior | VIX→EXTREME_COMPLACENCY, FG→... |
| 1 | −2σ ≤ val < −1σ | P2.28 → P15.87 | 13.59% | Bajo | VIX→COMPLACENCY, FG→... |
| 2 | −1σ ≤ val < μ | P15.87 → P50 | 34.13% | Neutro (sesgo bajo) | VIX→NEUTRAL_CALM, FG→... |
| 3 | μ ≤ val < +1σ | P50 → P84.13 | 34.13% | Neutro (sesgo alto) | VIX→NEUTRAL_ALERT, FG→... |
| 4 | +1σ ≤ val < +2σ | P84.13 → P97.72 | 13.59% | Elevado | VIX→PANIC, FG→... |
| 5 | val ≥ +2σ | P97.72 → P100 | 2.28% | Extremo superior | VIX→EXTREME_PANIC, FG→... |
```

### Estado deseado (CORRECTO):

Reemplazar las líneas 41-48 con una tabla de solo 5 columnas, más una nota al pie:

```
| Bin Index | Range | Percentile Band | Population % | Semantic Role |
|:---:|---|:---:|:---:|---|
| 0 | val < −2σ | P0 → P2.28 | **2.28%** | Extremo inferior |
| 1 | −2σ ≤ val < −1σ | P2.28 → P15.87 | **13.59%** | Bajo |
| 2 | −1σ ≤ val < μ | P15.87 → P50 | **34.13%** | Neutro (sesgo bajo) |
| 3 | μ ≤ val < +1σ | P50 → P84.13 | **34.13%** | Neutro (sesgo alto) |
| 4 | +1σ ≤ val < +2σ | P84.13 → P97.72 | **13.59%** | Elevado |
| 5 | val ≥ +2σ | P97.72 → P100 | **2.28%** | Extremo superior |

Los labels semánticos específicos de cada estación están en [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md). Para resolver un label dado un bin:

```python
from backend.modules.entry_decision.domain.rules.metar_classifier import resolve_label

# Cargar labels del fact store de la estación
labels = json.load(open("backend/.../vix_fact_store.json"))["_documentation"]["taxonomy"]["d1"]["labels"]
label = resolve_label(4, labels)  # → "PANIC" para VIX, "EASE" para Credit
```

Los overflows (> ±3σ) y blow-offs (> ±5σ) NO modifican el bin (se clipea a [0,5]). Operan en capa paralela sobre el z-score crudo. Ver [overflow_taxonomy.md](file:///root/botero-trade/.agents/references/metar/overflow_taxonomy.md) para la escala T1-T5. En código:

```python
from backend.modules.entry_decision.domain.rules.sigma_overflow import classify_overflow_tier

# z_score crudo del indicador
tier, hazard_name, hazard_type = classify_overflow_tier(z_score=4.2)
# → (2, "OVERFLOW_EXTREMO", "CRITICAL")
```

---

## POR QUÉ ESTO ES MEJOR

| Aspecto | Tabla anterior | Tabla nueva |
|:--------|:--------------|:------------|
| Columnas | 7 (incluía ejemplos) | 5 (solo escala) |
| Estaciones | 3 ejemplos (incompletos) | 0 — referenciadas externamente |
| Lo que necesita un agente | Buscar su estación en la tabla | Usar `resolve_label()` universal |
| Mantenimiento | Si cambia un label, hay que actualizar 2 archivos | Solo `d1_labels_canonical.md` |
| Riesgo de error | Alto — Gemini puede inventar labels o poner incompletos | Bajo — un solo punto de verdad |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
cd /root/botero-trade
# La tabla debe tener 6 filas de datos (bins 0-5)
grep -c "Bin 0\|Bin 1\|Bin 2\|Bin 3\|Bin 4\|Bin 5" .agents/references/metar/gaussian_scale_policy.md

# No debe quedar VIX→EXTREME_COMPLACENCY en la tabla D1
grep "VIX→\|FG→\|Credit→" .agents/references/metar/gaussian_scale_policy.md
# Si devuelve algo, aún hay labels en la tabla — deben estar solo en d1_labels_canonical.md

# La referencia a d1_labels_canonical.md debe estar presente
grep "d1_labels_canonical" .agents/references/metar/gaussian_scale_policy.md
```