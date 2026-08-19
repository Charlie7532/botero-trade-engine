# SKEW PROFUNDO — capa de riesgo de cola

**Fecha:** 2026-08-16 · **Script:** `research/03_estaciones_metar/skew_profundo.py` (+ `skew_profundo_supp.py`)
**Datos:** SPY∩SKEW∩VIX = 8,424 barras (1993-01-29 → 2026-08-14)
**Método:** cuartiles P15/P85, forward 20/40/60d, CI95 bootstrap 2000 (seed 42), wins/losses separados.
**Percentiles:** SKEW P15=113.3, P85=137.1 · VIX P15=12.7, P85=26.1

---

## 1. CUADRANTE VIX×SKEW (forward returns, barras diarias)

| Cuadrante | N días | f20d | f40d | f60d | WR60 | PF60 | Wipeouts>20% |
|---|---|---|---|---|---|---|---|
| 🔴 **PÁNICO TOTAL** (VIX↑+SKEW↑) | 55 (0.7%) | +3.45% | +5.87% | **+6.81%** CI95[+4.99,+8.50] | 81.8% | 8.09 | 0 |
| 🟠 Crisis sin miedo (VIX↑+SKEW↓) | 1210 (14.4%) | +1.81% | +3.78% | +5.13% CI95[+4.56,+5.63] | 73.8% | 3.64 | 17 (1.4%) |
| 🟡 Miedo silencioso (VIX↓+SKEW↑) | 1209 (14.4%) | +0.72% | +1.58% | +2.15% CI95[+1.78,+2.53] | 73.9% | 2.26 | 10 (0.9%) |
| 🟢 Calma total (VIX↓+SKEW↓) | 5950 (70.6%) | +0.84% | +1.39% | +2.07% CI95[+1.86,+2.29] | 68.5% | 2.15 | 55 (0.9%) |

**✅ +6.81% 60d / 82% win VALIDADO exactamente.** Es la señal MÁS fuerte del cuadrante:
mayor return, mayor PF (8.09), WR 81.8%, CI95 entero positivo y separado del resto.
PÁNICO: **0 wipeouts >20%**, max loss −9.79%, wins 45 (mean +9.50%) vs losses 10 (mean −5.28%).

**De-clustered (≥20d):** PÁNICO N=18 → +5.75% CI95[+2.03,+8.80] WR 78% PF 4.95 — sigue significativo.

**Robustez post-2011 (N=3,919):** PÁNICO +5.51% CI95[+3.35,+7.39] WR 75% (N=36);
Crisis sin miedo +7.01% WR 82% (N=553); Miedo silencioso +1.54%; Calma +2.38%.

**Lectura:** los dos cuadrantes VIX↑ son alcistas (reversión contraria). PÁNICO (ambos miedos
juntos) es el extremo más rentable — el "ultimate contrarian buy".

---

## 2. LOW_TAIL_RISK LETAL vs SANO (2008 −40% vs 2009 +40%)

**NO es VIX el discriminador** (ΔVIX↓−VIX↑ ≈ −0.6 a −4.4pp, no significativo — ambos lados positivos).

**Discriminador #1 = FASE (SPY drawdown):**
- SPY DD ≥ −10% (complacency en máximos): f250d **+16.03%** CI95[+7.67,+25.20] WR 79% (N=28)
- SPY DD < −10% (complacency en caída): f250d +6.22% CI95[−2.66,+14.64] WR 64% (N=28)

**Discriminador #2 = D3 compresión de SKEW:**
- D3 comprimido (<0.12, SKEW vol ≈ 0): f60d **−5.06%** (N=5) — la "silencio antes de la tormenta"
- D3 expansión (≥1.05): f60d +8.74% (N=17)

**Timeline GFC (episodios de-clustered ≥60d):**
| Fecha | SKEW | VIX | DD | D3 | f250d | Fase |
|---|---|---|---|---|---|---|
| 2008-05-23 | 113.1 | 19.5 | −12% | 0.37 | −35.2% | DENIAL (letal) |
| 2008-08-19 | 111.4 | 21.3 | −19% | 0.76 | −22.6% | DENIAL (letal) |
| 2008-11-28 | 113.1 | 55.3 | −42% | 0.06 | +23.6% | capitulación (giro) |
| **2009-03-09** | 113.1 | 49.7 | **−56%** | 1.16 | **+67.7%** | CAPITULACIÓN (oro) |
| 2009-07-10 | 113.2 | 29.0 | −44% | 0.92 | +21.8% | recuperación |

**Conclusión:** el mismo bin D1 (SKEW~113) significa cosas opuestas según la fase.
LETAL = complacencia en **fase de negación** (drawdown moderado −12/−19% + VIX elevado pero
aún sin espiga 19-24). SANO = complacencia en **capitulación** (drawdown profundo −56% + VIX
extremo 50). D3 comprimido es la firma de la letal.

---

## 3. SKEW como EARLY WARNING

- **SKEW NO precede crashes — SIGUE.** En el pico/inicio de los 12 drawdowns >10%, SKEW está
  BAJO/normal (complacency): 2007→109, 2020→129, 2022→128, 2025→129. SKEW≥P85 antes del DD:
  17% (2/12); después: 8% (1/12). SKEW alto es CONTRARIAN (comprar), no predictivo de crash.
- **LOW_TAIL_RISK NO precede drawdowns >10% — es tasa base.**
  - LOW_TAIL_RISK → DD>10% en 60d: **25%** (14/56) vs **base rate 21.3%**
  - LOW_TAIL_RISK → DD>10% en 120d: **37.5%** (21/56) vs **base rate 35.5%**
  - (Base rate: 141 días de-clustered 60td; 30/141 y 50/141.) → sin edge predictivo.

---

## 4. SKEW D2 (velocidad) y D3 (volatilidad)

**D2 señal propia:** FAST_CRUSH (SKEW cayendo rápido) = **+4.08% 60d** WR 81% PF 5.16 (N=99)
— la más fuerte; FAST_SPIKE = +2.92% (más débil). SKEW desplomándose = venta de protección
pánico → reversión alcista.

**D3:** VOL_PEAK_DECELERATION = **+3.72% 60d** WR 73% (más fuerte); VOL_ACCELERATING_EXPANSION
= +2.16% (más débil).

### ⭐ HALLAZGO CLAVE — SKEW es NO-MONOTÓNICO
Curva forward 60d por bin D1:

| Bin D1 | N | f60d | WR |
|---|---|---|---|
| LOW_TAIL_RISK | 1814 | +1.38% | 66% |
| NORMAL | 2239 | **+3.46%** (peak) | 70% |
| ELEVATED | 2381 | +2.55% | 70% |
| HIGH | 1332 | +3.04% | 77% |
| TAIL_PARANOIA | 509 | +2.35% | 74% |
| **BLACK_SWAN (≥159)** | 89 | **−1.99%** CI95[−3.19,−0.80] | **40%** |

El "comprar miedo" de SKEW se **INVIERTE en el extremo ≥159**: el seguro de crash tan caro ya
no es contrarian, es un crash en curso. ⚠️ La nota previa "BLACK_SWAN ≥136 → +2.36%" usaba el
corte P85 (=137 ≈ HIGH/TAIL_PARANOIA), NO el bin D1 ≥159 — son cosas distintas. El punto de
inflexión real está en ~159.

**PÁNICO TOTAL refinado D2×D3:** todos los sub-grupos positivos (+5.70% a +9.98%), sin celda
negativa → la señal más robusta del estudio.

---

## Veredicto operativo
1. **PÁNICO TOTAL es la señal más fuerte** (VIX↑ + SKEW↑ simultáneo): +6.81% 60d, PF 8.09, 82% WR, 0 wipeouts. Validado.
2. **SKEW extremo (≥159) es BAJISTA**, no compra — refina el "comprar miedo" que solo vale hasta ~159.
3. **LOW_TAIL_RISK letal vs sano lo discrimina la FASE** (drawdown + D3 comprimido), no VIX ni D2.
4. **LOW_TAIL_RISK no es early-warning** (tasa base); **SKEW alto sigue, no precede, crashes.**
