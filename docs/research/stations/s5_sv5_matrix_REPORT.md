# S5×SV5 Matrix — Validación Empírica

**Fecha:** 2026-08-16 · **Script:** `scratch/s5_sv5_matrix.py` · **JSON:** `scratch/s5_sv5_matrix_results.json`

**Qué se midió:** SPY zz25 pivotes (N=1,590 total, 1,377 con datos S5TW+SV5TW, rango 1999-01 → 2026-07).
SV5TW arranca en 1999, por lo que los ~213 pivotes previos quedan fuera.

- **S5** = `diff(3)` de S5TW (% stocks sobre 20-DMA) — velocidad del breadth de PRECIO.
- **SV5** = `diff(3)` de SV5TW (% stocks con volumen en expansión) — velocidad del breadth de VOLUMEN.
- **cascade_50** = leg zz50 del MISMO tipo arranca en ±3 días (definición autoritativa de
  `v3_fact_table_engine.py`: `diffs ≤ 3d & next_types == s_type` → baseline 40.69%, reproduce exacto).
- **leg_bear** = `start_type == MAX` (el próximo leg desde el pivote es bajista).

Todo con CI95 bootstrap (3,000 iteraciones). Sin etiquetas binarias — solo probabilidades + CI95 + N.

---

## 1. Baseline incondicional (N=1,377)

| Métrica | Probabilidad | CI95 |
|---|---|---|
| %bear (próximo leg bajista) | **50.0%** | [47.5%, 52.7%] |
| %cascade_50 | **41.5%** | [39.1%, 44.1%] |

---

## 2. Los 4 cuadrantes S5×SV5

| Cuadrante | N | % de pivotes | %bear | CI95 | %cascade_50 | CI95 |
|---|---|---|---|---|---|---|
| **S5↑SV5↑** ("Rally con convicción") | 315 | 22.9% | **67.3%** | [62.2%, 72.4%] | 42.5% | [36.8%, 47.9%] |
| **S5↑SV5↓** ("Rally sin convicción") | 293 | 21.3% | **68.9%** | [63.5%, 74.1%] | 41.3% | [35.8%, 47.1%] |
| **S5↓SV5↑** ("Venta con convicción") | 477 | 34.6% | **37.7%** | [33.5%, 42.1%] | 41.9% | [37.5%, 46.5%] |
| **S5↓SV5↓** ("Deriva apática") | 292 | 21.2% | **32.5%** | [27.1%, 38.0%] | 39.7% | [33.9%, 45.2%] |

**χ² cuadrante × %bear:** 144.10, p = 5e-31 → **SIGNIFICATIVO** (los cuadrantes difieren en dirección).
**χ² cuadrante × cascade_50:** 0.56, p = 0.906 → **NO significativo** (los cuadrantes NO difieren en cascada).

---

## 3. ¿Las etiquetas documentadas tienen respaldo? → **NO. Están INVERTIDAS en dirección y SV5 es ruido.**

La documentación de `volume_breadth_calculator.py` interpreta S5↑ como *"rally en curso → continúa alcista"*
(momentum). Los datos muestran lo contrario (**reversión a la media**):

- **S5↑SV5↑ "Rally con convicción"** → 67.3% de que el PRÓXIMO leg sea BAJISTA. No es "rally que continúa", es un techo.
- **S5↓SV5↑ "Venta con convicción"** → solo 37.7% bear (62.3% alcista). No es "venta que continúa", es un suelo.

La etiqueta correcta por datos:

| Cuadrante | Etiqueta documentada | Realidad empírica |
|---|---|---|
| S5↑ (cualquier SV5) | "Rally" | **Techo probable — 68% próximo leg bajista** |
| S5↓ (cualquier SV5) | "Venta/Deriva" | **Suelo probable — 64% próximo leg alcista** |

La dimensión **SV5 (convicción) NO discrimina NADA** en dirección: dentro de S5↑, SV5↑ (67.3%) vs SV5↓ (68.9%)
= Δ1.6pp, CI95 cruza cero; dentro de S5↓, Δ5.2pp, CI95 cruza cero.

Esto es **consistente con hallazgos previos validados del proyecto**: BSI D2 (velocidad Δ3d = exactamente este S5)
predice dirección con ρ=+0.379 y NO predice cascada (ρ≈0); SV5T es "sensor de batalla DIRECTIONLESS" (pitfall #34/#41).

---

## 4. Probabilidad REAL de cada cuadrante

| Cuadrante | Probabilidad |
|---|---|
| S5↑SV5↑ | **22.9%** |
| S5↑SV5↓ | **21.3%** |
| S5↓SV5↑ | **34.6%** (el más frecuente) |
| S5↓SV5↓ | **21.2%** |

El cuadrante más común ("Venta con convicción" en la doc) es en realidad el de **mayor probabilidad alcista (62%)**.

---

## 5. ¿La matriz S5×SV5 agrega valor sobre BSI (S5TW) solo? → **NO.**

**Dirección (la única señal real):**

| Señal | N | %bear | CI95 |
|---|---|---|---|
| S5↑ (solo) | 608 | **68.1%** | [64.3%, 71.7%] |
| S5↓ (solo) | 769 | **35.8%** | [32.2%, 39.1%] |
| Gap S5↓−S5↑ | — | **−32.3pp** | [−37.5, −27.3] (no cruza cero) |

SV5 agrega dentro de S5↑: Δ≤1.6pp; dentro de S5↓: Δ≤5.2pp — ambos CI95 cruzan cero.

**Cascada:** ni S5 ni SV5 aportan. S5↑ 41.9% vs S5↓ 41.1% (gap +0.8pp, CI95 [−4.2%, +6.3%]); SV5 gaps ≤2.2pp, CI95 cruzan cero.

**Conclusión:** la matriz S5×SV5 es **equivalente a S5 solo**, y S5 solo es un predictor de **DIRECCIÓN
(reversión a la media)**, no de cascada. SV5 (breadth de volumen) no aporta información sobre ninguno de los
dos targets. Las etiquetas de "convicción" documentadas carecen de respaldo empírico y su eje de dirección está invertido.

---

## Recomendación operativa (probabilidades, no etiquetas)

Si se usa S5 (BSI velocity) como señal de dirección en pivotes zz25:

- **S5↑** (breadth acelerando): P(próximo leg bajista) = **68%** [64%, 72%], N=608.
- **S5↓** (breadth frenando): P(próximo leg bajista) = **36%** [32%, 39%], N=769 (⇒ 64% alcista).

No exponer jamás "Rally con convicción" / "Venta con convicción" como reglas binarias — viola el principio
"todo señal con p + CI95 + N" (pitfall #51) y, peor, el eje está invertido respecto a la realidad medida.
