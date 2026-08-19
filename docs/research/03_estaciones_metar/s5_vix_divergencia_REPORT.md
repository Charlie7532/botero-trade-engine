# Divergencia VIX×S5 — sentir vs hacer

**Fecha:** 2026-08-16 · **Script:** `research/04_conjuncion_multi_estacion/s5_vix_divergencia.py` · **JSON:** `data/research/conjunctions/s5_vix_divergencia_results.json`

**Qué se midió:** 1,590 pivotes zz25 de SPY; 1,376 con datos VIX+S5TW+SV5TW alineados (1999-01 → 2026-07).
Todo con CI95 bootstrap (3,000 iteraciones). Wins y losses SIEMPRE separados.

- **VIX** = lo que el mercado SIENTE (volatilidad implícita).
- **S5 (S5TW)** = lo que el mercado HACE (% stocks sobre 20-MA).
- **SV5 (SV5TW)** = con qué volumen lo hace (% stocks con volumen en expansión).
- Régimen clasificado con `diff(5)` en cada pivote zz25: VIX↑ = diff>0, S5-mantiene = diff>0.

---

## 1. Baselines incondicionales (N=1,376)

| Métrica | Valor | CI95 |
|---|---|---|
| %bear (próximo leg bajista) | **50.0%** | [47.4%, 52.6%] |
| %cascade_50 (→ zz50 ±3d) | **41.4%** | [38.8%, 44.0%] |
| %cascade_75 (→ zz75 ±3d) | **20.2%** | [18.0%, 22.3%] |

SPY fwd incondicional: 5d **+0.14%** · 10d **+0.28%** · 20d **+0.66%** · 40d **+1.45%** (deriva del índice).

**Baseline de alternación explícito:** el zigzag alterna MIN→MAX→MIN por construcción → %bear ≈ 50%.
Cualquier desviación de un régimen es SOBRE ese baseline, no predicción pura. cascade_50 ≈ 40% es la tasa de continuación estructural.

---

## 2. Los 4 regímenes de divergencia

### 2.1 MIEDO SIN VENTA — VIX↑ + S5 mantiene (N=161, 11.7%)

| Target | Valor | CI95 | vs baseline |
|---|---|---|---|
| %bear (zigzag) | 54.0% | [46.6%, 61.5%] | Δ=+4.0pp, CI [-4.1, +12.0] (NS) |
| %cascade_50 | **52.8%** | [44.7%, 60.2%] | **Δ=+11.4pp, CI [+2.9, +19.4]** ✓ |
| %cascade_75 | **28.0%** | [20.5%, 35.4%] | **Δ=+7.7pp, CI [+0.6, +15.5]** ✓ |

| Horizonte | Retorno | CI95 | WR | PF | Kelly | Wipeouts>20% |
|---|---|---|---|---|---|---|
| 5d | −0.07% | [−0.68%, +0.51%] | 48.4% | 0.95 | −0.02 | 0 (0%) |
| 10d | −0.71% | [−1.63%, +0.14%] | 51.6% | 0.69 | −0.23 | 4 (2%) |
| 20d | −0.56% | [−1.87%, +0.74%] | 55.3% | 0.83 | −0.11 | 5 (3%) |
| 40d | −0.72% | [−2.27%, +0.74%] | 49.7% | 0.81 | −0.12 | 9 (6%) |

**No rebota.** Todos los horizontes negativos o planos, PF < 1, Kelly negativo, 6% de wipeouts a 40d.

### 2.2 MIEDO CON VENTA — VIX↑ + S5 colapsa (N=631, 45.9%)

| Target | Valor | CI95 | vs baseline |
|---|---|---|---|
| %bear (zigzag) | **33.3%** | [29.6%, 36.9%] | **Δ=−16.7pp, CI [−21.1, −12.1]** ✓✓ |
| %cascade_50 | 40.9% | [36.9%, 44.7%] | Δ=−0.5pp, CI [−5.2, +4.2] (NS) |
| %cascade_75 | 19.7% | [16.5%, 22.8%] | Δ=−0.6pp, CI [−4.3, +3.2] (NS) |

| Horizonte | Retorno | CI95 | WR | PF | Kelly | Wipeouts>20% |
|---|---|---|---|---|---|---|
| 5d | **+0.92%** | [+0.63%, +1.23%] | 64.5% | 1.89 | +0.30 | 0 (0%) |
| 10d | **+1.04%** | [+0.65%, +1.43%] | 62.9% | 1.70 | +0.26 | 0 (0%) |
| 20d | **+1.51%** | [+0.99%, +1.99%] | 64.2% | 1.84 | +0.29 | 5 (1%) |
| 40d | **+2.40%** | [+1.79%, +2.99%] | 65.0% | 2.19 | +0.35 | 11 (2%) |

**No sigue cayendo — rebota.** 64–65% WR, PF 1.7–2.2, Kelly +0.26→+0.35, todos los CI95 excluyen cero.
Dirección zigzag claramente alcista (33.3% bear = 66.7% bull).

### 2.3 CALMA CON AMPLITUD — VIX↓ + S5 se recupera (N=440, 32.0%)

| Target | Valor | CI95 | vs baseline |
|---|---|---|---|
| %bear (zigzag) | **71.4%** | [67.0%, 75.5%] | **Δ=+21.4pp, CI [+16.4, +26.3]** ✓✓ |
| %cascade_50 | 37.7% | [33.0%, 42.3%] | Δ=−3.7pp, CI [−9.0, +1.5] (NS) |
| %cascade_75 | 19.1% | [15.2%, 23.0%] | Δ=−1.1pp, CI [−5.5, +3.1] (NS) |

| Horizonte | Retorno | CI95 | WR | PF | Kelly | Wipeouts>20% |
|---|---|---|---|---|---|---|
| 5d | **−0.87%** | [−1.20%, −0.52%] | 37.3% | 0.52 | −0.35 | 0 (0%) |
| 10d | **−0.46%** | [−0.88%, −0.07%] | 46.1% | 0.76 | −0.15 | 0 (0%) |
| 20d | −0.10% | [−0.64%, +0.47%] | 53.6% | 0.96 | −0.02 | 4 (1%) |
| 40d | +0.71% | [−0.04%, +1.46%] | 55.1% | 1.27 | +0.12 | 5 (1%) |

**No es tendencia sana — es un techo.** 71.4% próximo leg bajista, 5d claramente negativo (−0.87%),
WR 5d = 37%. El "calma con amplitud" es breadth en pico = techo (reversión a la media).

### 2.4 CALMA SIN CONVICCIÓN — VIX↓ + S5 no reacciona (N=144, 10.5%)

| Target | Valor | CI95 | vs baseline |
|---|---|---|---|
| %bear (zigzag) | 53.5% | [45.1%, 61.1%] | Δ=+3.5pp, CI [−5.0, +12.0] (NS) |
| %cascade_50 | 42.4% | [34.0%, 50.7%] | Δ=+0.9pp, CI [−7.4, +9.6] (NS) |
| %cascade_75 | 17.4% | [11.8%, 23.6%] | Δ=−2.8pp, CI [−9.2, +3.9] (NS) |

| Horizonte | Retorno | CI95 | WR | PF | Kelly | Wipeouts>20% |
|---|---|---|---|---|---|---|
| 5d | +0.05% | [−0.56%, +0.69%] | 43.1% | 1.04 | +0.02 | 0 (0%) |
| 10d | +0.27% | [−0.54%, +1.03%] | 53.8% | 1.18 | +0.08 | 1 (1%) |
| 20d | +0.62% | [−0.50%, +1.66%] | 56.6% | 1.27 | +0.12 | 1 (1%) |
| 40d | +1.94% | [+0.58%, +3.28%] | 64.1% | 1.92 | +0.31 | 2 (1%) |

**Deriva alcista**, sin dirección zigzag clara. A 40d supera al baseline (+1.94% vs +1.45%).
Único régimen donde zigzag y fijos NO concuerdan (pero el %bear es NS → "sin señal", no contradicción real).

---

## 3. Respuesta a las preguntas clave

### Q1: ¿VIX↑ + S5 NO colapsa → rebote (sobre-reacción)? → **NO. Es una ADVERTENCIA.**

MIEDO SIN VENTA no rebota. Retornos negativos (−0.56% 20d, −0.72% 40d), PF<1, Kelly negativo,
y —lo más importante— **cascade_50 = 52.8% vs 41.4% baseline** (Δ=+11.4pp, CI95 significativo).

**Interpretación económica:** cuando el miedo sube pero la amplitud AÚN no ha caído, el mercado
todavía NO ha pagado el miedo. La venta real está por venir → el movimiento estructural CONTINÚA
(más cascada). No es sobre-reacción; es **sub-reacción** — el precio aún no refleja el miedo.

### Q2: ¿VIX↑ + S5 colapsa → sigue cayendo (venta real)? → **NO. Es CAPITULACIÓN (rebote).**

MIEDO CON VENTA rebota con fuerza: +1.51% 20d, +2.40% 40d, 64–65% WR, PF 2.2, Kelly +0.35,
dirección zigzag 66.7% alcista. Todos los CI95 excluyen cero.

**Interpretación:** cuando el miedo YA se expresó en la amplitud (S5 colapsó), la venta está
agotada → capitulación → rebote. Es exactamente el principio "comprar miedo" del proyecto,
pero con un filtro crucial: **solo se compra el miedo cuando la amplitud confirma que la venta
ya ocurrió.** Si la amplitud no ha caído, el miedo aún no se ha descargado → no comprar.

### Q3: ¿SV5 (volumen) distingue los casos ambiguos? → **NO (ruido, consistente con hallazgos previos).**

| Caso ambiguo | ΔSV5↑−SV5↓ | CI95 |
|---|---|---|
| MIEDO SIN VENTA · fwd 20d | −0.02% | [−2.75%, +2.80%] |
| MIEDO SIN VENTA · %cascade_50 | −7.1pp | [−22.3%, +8.4%] |
| CALMA SIN CONVICCIÓN · fwd 20d | +0.25% | [−1.98%, +2.61%] |
| CALMA SIN CONVICCIÓN · %cascade_50 | +9.4pp | [−6.6%, +25.9%] |

Todos los CI95 cruzan cero. El único matiz (no significativo) en el cuadrante S5×SV5 dentro de
MIEDO CON VENTA: la capitulación "apática" (S5↓SV5↓, fwd20d +2.04%, N=182) rebota más que la
"con convicción" (S5↓SV5↑, +1.39%, N=360) — el agotamiento sin volumen es más suelo que la
venta con volumen. Coherente con SV5 = sensor DIRECTIONLESS (pitfall #34/#41), no con la matriz
de "convicción" (refutada en `s5_sv5_matrix.py`).

### Q4 (reconciliación): ¿zigzag y fijos se contradicen? → **Solo en 1 de 4, y es "sin señal".**

| Régimen | %bear zigzag | fwd 20d | ¿Concuerdan? |
|---|---|---|---|
| MIEDO SIN VENTA | 54% (NS) | −0.56% | ✓ (ambos suaves/bajistas) |
| MIEDO CON VENTA | 33% (alcista) | +1.51% | ✓ (ambos alcistas) |
| CALMA CON AMPLITUD | 71% (bajista) | −0.10% (5d −0.87%) | ✓ (techo, reversión rápida) |
| CALMA SIN CONVICCIÓN | 53% (NS) | +0.62% | ✗ — pero %bear NS = sin señal |

La reversión de CALMA CON AMPLITUD se materializa en 5–10 días (fwd 5d −0.87%), por eso el
zigzag (que espera el cruce del umbral) y el horizonte corto coinciden. El único "desacuerdo"
es CALMA SIN CONVICCIÓN, donde el zigzag no tiene señal direccional (CI cruza 50%) y el fijo
es deriva alcista débil — no hay contradicción real, solo ausencia de señal + deriva del índice.

---

## 4. La clave: S5 (amplitud) es el gauge de "cuánto falta del movimiento"

Los 4 regímenes revelan que **la amplitud S5 marca la FASE del movimiento, no su dirección:**

- **VIX↑ + S5 AÚN en pie** = miedo sin descargar → el movimiento **continúa** (cascade_50 52.8%,
  significativo). NO es momento de comprar: la venta real no ha ocurrido todavía.
- **VIX↑ + S5 ya colapsó** = miedo descargado en venta → **capitulación** → rebote (fwd 40d +2.40%).
  ES el momento de comprar.
- **VIX↓ + S5 en pico** = amplitud agotada al alza → **techo** (71% próximo leg bajista).
- **VIX↓ + S5 plana** = sin convicción → deriva alcista débil.

**Refinamiento operativo del principio "comprar miedo":** el VIX solo dice CUÁNTO miedo hay;
la amplitud S5 dice SI ese miedo ya se convirtió en venta. Divergencia VIX↑/S5-mantiene =
miedo que aún no ha vendido = esperar. Convergencia VIX↑/S5-colapsa = miedo que ya vendió = entrar.

Esto es consistente con el hallazgo del proyecto "CRISIS_SPIKE + pivot zz25 = ENTRY" (pitfall #60):
la entrada en miedo requiere confirmación de que la caída ya ocurrió, no comprar en el primer
repunte del VIX.

---

## 5. Sensibilidad de la ventana de clasificación (diff(3) vs diff(5))

| Régimen | diff(5) N (%) | diff(3) N (%) | Δ |
|---|---|---|---|
| MIEDO SIN VENTA | 161 (11.7%) | 127 (9.2%) | −2.5pp |
| MIEDO CON VENTA | 631 (45.9%) | 635 (46.1%) | +0.3pp |
| CALMA CON AMPLITUD | 440 (32.0%) | 481 (34.9%) | +3.0pp |
| CALMA SIN CONVICCIÓN | 144 (10.5%) | 134 (9.7%) | −0.7pp |

La clasificación es estable (el régimen dominante MIEDO CON VENTA apenas cambia +0.3pp).
Los hallazgos NO dependen del ancho de ventana.

---

## 6. Tests de independencia (χ²)

| Test | χ² | p | Conclusión |
|---|---|---|---|
| régimen × leg_bear (dirección) | 152.63 | 0.0000 | **SIGNIFICATIVO** |
| régimen × cascade_50 | 11.18 | 0.0108 | **SIGNIFICATIVO** |
| régimen × cascade_75 | 7.17 | 0.0666 | no significativo |

La divergencia VIX×S5 discrimina dirección de forma MUY fuerte (χ²=152) y cascada a zz50 de forma
moderada. La cascada a zz75 no la discrimina (los efectos se diluyen a escala mayor).

---

## Resumen ejecutivo

**Las dos hipótesis naïve están INVERTIDAS por los datos:**

1. "VIX↑ + S5 no colapsa = sobre-reacción → rebote" → **FALSO. Es sub-reacción: la venta aún no
   ocurrió y el movimiento continúa (cascade_50 +11.4pp, retornos negativos).**
2. "VIX↑ + S5 colapsa = venta real → sigue cayendo" → **FALSO. Es capitulación: la venta ya
   ocurrió y rebota (+2.40% 40d, 65% WR, Kelly +0.35).**
3. "VIX↓ + S5 se recupera = tendencia sana" → **FALSO. Es techo (71% próximo leg bajista, −0.87% 5d).**
4. "VIX↓ + S5 no reacciona = deriva" → **CONFIRMADO (deriva alcista débil).**

**SV5 no distingue los casos ambiguos** (todos los CI95 cruzan cero) — consistente con SV5 =
sensor de volumen DIRECTIONLESS. La señal está 100% en la divergencia VIX×S5, no en el volumen.

**La amplitud S5 es el gauge de fase:** miedo sin amplitud caída = esperar; miedo con amplitud
ya caída = comprar. El "sentir" (VIX) sin el "hacer" (S5) es incompleto — solo juntos ubican al
mercado en el ciclo.
