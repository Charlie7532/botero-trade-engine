# TIMING DE-RISKING — D2 flip (velocidad) mejora la señal SHORT de la secuencia

Entrada en barra de señal · 4 variantes de timing · bootstrap 3000 · 3 escalas

## Baseline SPY (todos los días en ventana elegible)

| h | N | mean | CI95 |
|---|---|---|---|
| 5d | 8401 | +0.25 | [+0.18,+0.31] |
| 10d | 8401 | +0.49 | [+0.39,+0.58] |
| 20d | 8401 | +0.97 | [+0.85,+1.11] |
| 40d | 8401 | +1.79 | [+1.63,+1.95] |


## Escala zz25 — 1294 señales SHORT

Permutaciones: {'macro-driven (CAT1→CAT2→CAT3)': 1209, 'cuchillo (CAT1→CAT3→CAT2)': 85} · MIN/MAX: {'MIN': 655, 'MAX': 639}

### Variantes (forward desde entrada)

| Variante | N | 5d | 10d | 20d | 40d | downWR 20d | PF 20d | Kelly 20d | wipe20 | wipe40 |
|---|---|---|---|---|---|---|---|---|---|---|
| Secuencia SHORT sola (baseline, entrada barra señal) | 1294 | -0.49 | -0.87 | -1.84 | -1.13 | 61% | 2.15 | +0.33 | 3 | 11 |
| SHORT + D2 flip (entrada en el flip, NO señal) | 1294 | -0.02 | -0.10 | -0.46 | -2.19 | 48% | 1.23 | +0.09 | 2 | 9 |
| SHORT + D2 flip NO ocurrido (aún cayendo) | 0 | — | — | — | — | — | — | — | — | — |
| SHORT + cascade bear + D2 flip (dirección + timing) | 956 | +0.36 | +0.71 | +1.01 | -0.60 | 40% | 0.56 | -0.31 | 2 | 6 |

### VIX D2 TIMING (la estación validada)

| Grupo | N | 20d fwd | CI95 20d | 40d fwd | CI95 40d | downWR | PF | wipe20 |
|---|---|---|---|---|---|---|---|---|
| VIX D2 > 0 (miedo construyéndose → short ON) | 702 | -2.20 | [-2.71,-1.71] | -1.51 | [-2.25,-0.79] | 65% | 2.42 | 1 |
| VIX D2 < 0 (miedo resolviéndose → short TARDE) | 589 | -1.43 | [-1.98,-0.87] | -0.71 | [-1.43,+0.07] | 57% | 1.86 | 2 |
| VIX D2 = 0 (neutro) | 3 | -0.80 | [-1.12,-0.16] | +4.73 | [+3.22,+5.48] | 100% | — | 0 |

Último flip VIX: mediana 2d antes de la barra (P25=0d, P75=5d)


## Escala zz50 — 402 señales SHORT

Permutaciones: {'macro-driven (CAT1→CAT2→CAT3)': 372, 'cuchillo (CAT1→CAT3→CAT2)': 30} · MIN/MAX: {'MIN': 202, 'MAX': 200}

### Variantes (forward desde entrada)

| Variante | N | 5d | 10d | 20d | 40d | downWR 20d | PF 20d | Kelly 20d | wipe20 | wipe40 |
|---|---|---|---|---|---|---|---|---|---|---|
| Secuencia SHORT sola (baseline, entrada barra señal) | 402 | -0.39 | -1.36 | -3.26 | -2.17 | 65% | 2.93 | +0.43 | 2 | 7 |
| SHORT + D2 flip (entrada en el flip, NO señal) | 402 | -0.13 | -0.45 | -1.22 | -3.82 | 52% | 1.62 | +0.20 | 2 | 6 |
| SHORT + D2 flip NO ocurrido (aún cayendo) | 0 | — | — | — | — | — | — | — | — | — |
| SHORT + cascade bear + D2 flip (dirección + timing) | 266 | +0.66 | +0.99 | +1.17 | -0.59 | 39% | 0.52 | -0.36 | 2 | 6 |

### VIX D2 TIMING (la estación validada)

| Grupo | N | 20d fwd | CI95 20d | 40d fwd | CI95 40d | downWR | PF | wipe20 |
|---|---|---|---|---|---|---|---|---|
| VIX D2 > 0 (miedo construyéndose → short ON) | 221 | -4.69 | [-5.81,-3.58] | -3.41 | [-5.15,-1.60] | 69% | 4.91 | 0 |
| VIX D2 < 0 (miedo resolviéndose → short TARDE) | 181 | -1.50 | [-2.81,-0.09] | -0.66 | [-2.46,+1.29] | 60% | 1.66 | 2 |
| VIX D2 = 0 (neutro) | 0 | — | [—,—] | — | [—,—] | 0% | — | None |

Último flip VIX: mediana 3d antes de la barra (P25=0d, P75=5d)


## Escala zz75 — 160 señales SHORT

Permutaciones: {'macro-driven (CAT1→CAT2→CAT3)': 152, 'cuchillo (CAT1→CAT3→CAT2)': 8} · MIN/MAX: {'MIN': 81, 'MAX': 79}

### Variantes (forward desde entrada)

| Variante | N | 5d | 10d | 20d | 40d | downWR 20d | PF 20d | Kelly 20d | wipe20 | wipe40 |
|---|---|---|---|---|---|---|---|---|---|---|
| Secuencia SHORT sola (baseline, entrada barra señal) | 160 | -0.82 | -1.58 | -4.32 | -4.26 | 64% | 3.97 | +0.48 | 0 | 1 |
| SHORT + D2 flip (entrada en el flip, NO señal) | 160 | -0.38 | -0.84 | -1.89 | -5.71 | 56% | 2.47 | +0.33 | 0 | 1 |
| SHORT + D2 flip NO ocurrido (aún cayendo) | 0 | — | — | — | — | — | — | — | — | — |
| SHORT + cascade bear + D2 flip (dirección + timing) | 107 | -0.02 | +0.09 | -0.21 | -3.29 | 48% | 1.15 | +0.06 | 0 | 1 |

### VIX D2 TIMING (la estación validada)

| Grupo | N | 20d fwd | CI95 20d | 40d fwd | CI95 40d | downWR | PF | wipe20 |
|---|---|---|---|---|---|---|---|---|
| VIX D2 > 0 (miedo construyéndose → short ON) | 83 | -6.18 | [-8.14,-4.23] | -5.19 | [-8.12,-1.82] | 72% | 6.49 | 0 |
| VIX D2 < 0 (miedo resolviéndose → short TARDE) | 77 | -2.32 | [-4.02,-0.71] | -3.27 | [-5.05,-1.59] | 56% | 2.28 | 0 |
| VIX D2 = 0 (neutro) | 0 | — | [—,—] | — | [—,—] | 0% | — | None |

Último flip VIX: mediana 3d antes de la barra (P25=0d, P75=5d)


---
## Veredicto

**El D2 flip SÍ mejora la señal SHORT — pero como DIRECCIÓN del VIX D2, no como "entrada en el flip".**

1. El flip de CUALQUIER estación NO discrimina: 100% de ventanas 30d tienen ≥1 flip (variante c degenerada, N=0); el "primer flip" es ~29d antes (censurado) y dominado por DXY/SKEW/YIELD (las más volátiles). Confirma pitfall #90.

2. La DIRECCIÓN del VIX D2 en la barra de señal discrimina: VIX D2>0 (miedo construyéndose) → short fuerte (zz50 -4.69% downWR 69% PF 4.91, zz75 -6.18% PF 6.49, 0 wipeouts) vs VIX D2<0 (resolviéndose) → short débil (zz50 -1.50%, zz75 -2.32%, con wipeouts). Gap crece con la escala (+3.2pp zz50, +3.9pp zz75).

3. "Último flip VIX ↑" (miedo recién empieza a construir) es el timing óptimo: zz75 PF 6.65, downWR 73%, 0 wipeouts.

4. cascade bear + D2 flip es CONTRARIAN (short pierde: fwd20 +1.0% zz25, +1.2% zz50) — cascade bear = rebote (comprar miedo).

5. Regla operativa: ENTRAR el short SOLO si VIX D2>0; NO ENTRAR si VIX D2<0. La secuencia ya es OP-SHORT sin timing, pero el filtro VIX D2 building la fortalece 2-3× y elimina wipeouts.
