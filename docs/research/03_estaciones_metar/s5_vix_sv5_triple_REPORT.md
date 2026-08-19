# VIX×S5×SV5 — Matriz Triple: ¿SV5 agrega una tercera dimensión?

**Auditado 2026-08-16 · Script `research/04_conjuncion_multi_estacion/s5_vix_sv5_triple.py` (+ `research/04_conjuncion_multi_estacion/s5_vix_sv5_horizons.py`)**
**Resultados: `data/research/conjunctions/s5_vix_sv5_triple_results.json`**

## Pregunta

¿SV5 (= SV5TW, breadth de volumen, "convicción") agrega una TERCERA dimensión que
discrimina los casos ambiguos de los 4 regímenes VIX×S5 (sentir × hacer)?

Ejes (velocidad diff(3), cada uno su ticker correcto — pitfall #56):
- **VIX** = diff(3) de VIX ("sentir": miedo acelerando vs resolviendo)
- **S5** = diff(3) de S5TW ("hacer": breadth de precio)
- **SV5** = diff(3) de SV5TW ("convicción": breadth de volumen)

## Respuesta corta: **NO.**

SV5 es ruido en DIRECCIÓN (todos los horizontes fijos, CI95 cruza 0), ruido en CASCADA
(χ² p=0.31/0.82), y NO resuelve ninguno de los 4 casos ambiguos. La única dimensión que
discrimina es **S5** (breadth de precio, mean-reversion), modulada por **VIX**. SV5 no suma.

## 1. Matriz 8 celdas — %bear (dirección del próximo leg)

El %bear está dominado por S5 (mean-reversion en el pivote: breadth pica en techos,
se lava en pisos), NO por VIX ni SV5. El χ² de 8 celdas es significativo SOLO por S5.

### zz25 (N=1,377 pivotes)

| Celda | N | %bear [CI95] |
|---|---|---|
| VIX↑ S5↑ SV5↑ | 64 | 54.7% [42,66] |
| VIX↑ S5↑ SV5↓ | 63 | 60.3% [48,73] |
| **VIX↑ S5↓ SV5↑** | 406 | **34.7%** [30,39] ← 65% ALCISTA |
| **VIX↑ S5↓ SV5↓** | 230 | **30.0%** [24,36] ← 70% ALCISTA |
| **VIX↓ S5↑ SV5↑** | 251 | **70.5%** [65,76] ← 70% BAJISTA |
| **VIX↓ S5↑ SV5↓** | 230 | **71.3%** [65,77] ← BAJISTA |
| VIX↓ S5↓ SV5↑ | 71 | 54.9% [44,66] |
| VIX↓ S5↓ SV5↓ | 62 | 41.9% [31,55] |

χ² 8 celdas × %bear = 164.2, p=0.0000 (SIG). χ² 8 celdas × %cascade = 8.3, p=0.306 (NO sig).

### Los 2 regímenes "limpios" (señal direccional real, 2D VIX×S5):

| Régimen | %bear | Lectura |
|---|---|---|
| **MIEDO CON VENTA** (VIX↑ S5↓) | ~30-35% | **65-70% ALCISTA** — pánico+lavado = "comprar miedo" (tesis contraria del proyecto, confirmada) |
| **CALMA CON AMPLITUD** (VIX↓ S5↑) | ~70% | **~70% BAJISTA** — pico de breadth = techo |

### Los 2 regímenes "ambiguos" (que SV5 debía resolver — NO lo hace):

| Régimen | %bear | SV5↑ | SV5↓ | Δbear (CI95) | ¿Discrimina SV5? |
|---|---|---|---|---|---|
| **MIEDO SIN VENTA** (VIX↑ S5↑) | 55-60% | 54.7% | 60.3% | −5.6pp [−22.9,+11.7] | NO |
| **CALMA SIN CONVICCIÓN** (VIX↓ S5↓) | 42-55% | 54.9% | 41.9% | +13.0pp [−4.5,+29.9] | NO (CI cruza 0) |

## 2. Los 4 casos clave — hipótesis vs dato

| Hipótesis (conviction) | Dato (zz25, %bear) | Veredicto |
|---|---|---|
| MIEDO SIN VENTA + SV5↑ = rebote confirmado | 54.7% (vs 60.3% SV5↓) | NO — Δ no significativo, dirección marginal |
| MIEDO SIN VENTA + SV5↓ = rebote falso | 60.3% | NO — CI [48,73] cruza 50% |
| MIEDO CON VENTA + SV5↑ = capitulación | 34.7% (vs 30.0% SV5↓) | NO — SV5↑ es MÁS bear, opuesto a capitulación; Δ CI cruza 0 |
| MIEDO CON VENTA + SV5↓ = deriva bajista | 30.0% | NO — es 70% ALCISTA (mean-reversion), no deriva |

**Ninguna hipótesis de "convicción de volumen" se sostiene.** SV5TW es DIRECTIONLESS (pitfall #34/#41 confirmado).

## 3. Horizontes fijos 5/10/20/40d — 16/16 celdas CI cruzan 0

Δret(SV5↑ − SV5↓) dentro de cada régimen, TODOS los horizontes:

| Régimen | 5d | 10d | 20d | 40d |
|---|---|---|---|---|
| MIEDO SIN VENTA | −0.02% | +0.04% | −0.35% | −0.60% |
| MIEDO CON VENTA | +0.01% | +0.17% | +0.06% | +0.31% |
| CALMA CON AMPLITUD | +0.11% | +0.15% | −0.06% | +0.02% |
| CALMA SIN CONVICCIÓN | −0.38% | −0.23% | −0.26% | +0.43% |

**Cero significancia.** El win rate 20d de todas las celdas está en 57-66% (= deriva SPY ~63%).
Retornos forward todos positivos (~+0.2 a +0.9% 20d) — es la deriva alcista del SPY, no el SV5.

## 4. Cascada — SV5 (y S5, y VIX-vel) NO predicen cascade

χ² 8 celdas × cascade: **p=0.306 (zz25), p=0.821 (zz50)**. Todas las celdas ≈40-50%
(= baseline 40.7%/47.7%). Confirma el hallazgo previo (S5/SV5 no predicen cascada;
la cascada la predice d1_bear_5 + domino, no estas velocidades).

## 5. Único atisbo — frágil, NO validado (escala-dependiente)

En **CALMA CON AMPLITUD (VIX↓ S5↑)** a escalas GRANDES (zz50/zz75), SV5↓ tiene MÁS
%bear que SV5↑:
- zz50: SV5↓ 85.7% vs SV5↑ 70.8% (Δ−14.9pp CI[−28.4,−1.4])
- zz75: SV5↓ 91.7% vs SV5↑ 66.7% (Δ−25.0pp CI[−44.2,−5.0])
- zz25: SV5↓ 71.3% vs SV5↑ 70.5% (Δ−0.8pp — NO replica)

Lectura económica tentativa: "rally hueco sin volumen mean-revierte más duro". PERO:
(a) no replica en zz25 (N mayor), (b) no aparece en horizontes fijos, (c) CI95 borderline,
(d) N pequeño (63/72 y 24/30), (e) inconsistente con la hipótesis "volumen confirma
continuación" (aquí modula la magnitud de la REVERSIÓN, no el momentum). **NO operativo.**

## Conclusión

1. **SV5 NO agrega tercera dimensión.** Es ruido en dirección (16/16 horizontes fijos CI
   cruzan 0), ruido en cascada (χ² p>0.3), y no resuelve los casos ambiguos (Δbear CI cruzan 0).
2. **La matriz se colapsa a VIX×S5 (2D), y esa interacción SÍ es real para DIRECCIÓN:**
   - MIEDO CON VENTA (VIX↑ S5↓) → 65-70% alcista ("comprar miedo", mean-reversion)
   - CALMA CON AMPLITUD (VIX↓ S5↑) → 70% bajista (pico de breadth = techo)
   - VIX modula a S5: ~16-20pp de gap entre los regímenes con el mismo S5.
3. **No exponer etiquetas "con convicción" / "sin convicción" para SV5** — viola la regla
   p+CI95+N (pitfall #51). SV5TW es directionless; su valor (si alguno) es como sensor de
   batalla/timing, no como confirmador de dirección (pitfall #41).
4. Recomendación: mantener SV5TW fuera de cualquier voto direccional. Si se quiere
   investigar el atisbo de zz50/zz75 (rally hueco), hacerlo con OOS walk-forward y N mayor
   antes de considerarlo — hoy no pasa la barrera.
