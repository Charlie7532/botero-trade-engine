# D2 (VELOCIDAD Δ3d) — QUÉ SIGNIFICA EN CADA ESTACIÓN

**D2(t) = diff(3) del indicador = close(t) − close(t−3).**
Reporta ρ de Spearman (ρ, p-value nominal, N). Nótese que los retornos 3d/5d se solapan
(autocorrelados) → los p-values de las ventanas solapadas son nominales (optimistas).

---

## 1. D2 vs SPY día a día — ¿ANTICIPA o CONFIRMA?

| estación | ρ(D2→SPY 1d fwd) | ρ(D2→SPY 3d fwd) | ρ(D2→SPY 5d fwd) | ρ(SPY 3d back→D2) | rol |
|---|---|---|---|---|---|
| vix | +0.020 (0.064) | +0.037 (0.0007) | +0.058 (1e-7) | **−0.752** (0) | CONFIRMA |
| vvix | −0.015 (0.28) | −0.011 (0.44) | −0.001 (0.96) | **−0.563** (0) | CONFIRMA |
| pcr | −0.010 (0.49) | −0.000 (0.99) | +0.021 (0.15) | **−0.406** (0) | CONFIRMA |
| fg | +0.029 (0.068) | +0.024 (0.14) | +0.009 (0.59) | **+0.697** (0) | CONFIRMA |
| sv5_turbulence | −0.009 (0.43) | −0.000 (1.0) | +0.006 (0.63) | −0.007 (0.54) | **NULO** |
| skew | −0.021 (0.049) | −0.020 (0.072) | −0.004 (0.74) | **+0.219** (0) | CONFIRMA (débil) |
| credit | −0.027 (0.056) | −0.060 (3e-5) | −0.051 (4e-4) | **+0.486** (0) | CONFIRMA |
| yield_curve | −0.014 (0.19) | −0.033 (0.003) | −0.041 (2e-4) | +0.100 (6e-20) | CONFIRMA (débil) |
| rotation | −0.010 (0.43) | −0.009 (0.48) | −0.014 (0.25) | **+0.547** (0) | CONFIRMA |
| bsi (S5TW) | −0.014 (0.19) | −0.030 (0.006) | −0.050 (5e-6) | **+0.828** (0) | CONFIRMA (más fuerte) |
| dxy | −0.010 (0.40) | −0.022 (0.068) | −0.028 (0.02) | −0.097 (2e-15) | CONFIRMA (débil) |

**Conclusión A: D2 es un espejo del movimiento RECIENTE de SPY (confirmador), no un anticipador.**
- El forward ρ es minúsculo (|ρ| ≤ 0.06): D2 casi NO anticipa SPY.
- El backward ρ es enorme (|ρ| 0.4–0.83): D2 = el indicador reaccionando a SPY de los últimos 1–3 días.
- Excepción leve (mean-reversion): VIX D2↑ → SPY 5d futuro +0.058 (comprar el miedo);
  BSI/CREDIT/ROTATION D2↑ → SPY 5d futuro −0.03 a −0.06 (extremo de amplitud → leve retroceso).

---

## 2. D2 vs TRÍADA ZIGZAG (en pivotes zz25, N=1589)

| estación | ρ(D2,c50) p | ρ(D2,c75) p | **ρ(D2, leg_bear)** p | veredicto |
|---|---|---|---|---|
| vix | +0.066 (0.008) | +0.048 (0.057) | **−0.310** (8e-37) | DIRECCIÓN (contrarian) |
| vvix | +0.012 (0.72) | −0.004 (0.90) | **−0.197** (2e-9) | DIRECCIÓN |
| pcr | −0.051 (0.12) | −0.085 (0.010) | **−0.215** (5e-11) | DIRECCIÓN |
| fg | +0.052 (0.21) | +0.072 (0.081) | **+0.381** (2e-21) | DIRECCIÓN (top) |
| sv5_turbulence | −0.019 (0.47) | −0.051 (0.058) | −0.028 (0.30) | **NULO** |
| skew | −0.011 (0.66) | −0.039 (0.12) | +0.115 (4e-6) | DIRECCIÓN (débil) |
| credit | −0.053 (0.11) | −0.036 (0.28) | **+0.253** (8e-15) | DIRECCIÓN |
| yield_curve | +0.009 (0.72) | +0.061 (0.015) | +0.090 (3e-4) | DIRECCIÓN (débil) |
| rotation | +0.007 (0.81) | +0.038 (0.16) | **+0.257** (3e-22) | DIRECCIÓN |
| bsi (S5TW) | −0.010 (0.69) | +0.030 (0.23) | **+0.363** (1e-50) | DIRECCIÓN (top) |
| dxy | +0.036 (0.15) | +0.006 (0.83) | −0.020 (0.43) | **NULO** |

**Conclusión B:**
- D2 NO predice cascade (todos |ρ| < 0.09 sobre cascade_50/75). El nivel D1/domino es lo que gobierna el cascade.
- D2 SÍ predice la DIRECCIÓN del próximo leg (leg_bear), mucho más fuerte que D1 nivel (ρ=0.12).
  Confirmado: FG +0.38, BSI +0.36, VIX −0.31.

---

## 3. SIGNIFICADO de D2 por estación (qué nos dice)

**D2 positivo significa…**

| estación | D2↑ = | correlación con SPY pasado | señal direccional |
|---|---|---|---|
| **VIX** | miedo subiendo (VIX > hace 3d) | −0.75 (SPY cayó) | **contrarian: D2↑ → leg BULL** (ρ bear −0.31; %bear 33% vs 69%) |
| **VVIX** | vol del VIX subiendo | −0.56 | contrarian: D2↑ → leg BULL (%bear 39% vs 59%) |
| **PCR** | put/call subiendo (miedo) | −0.41 | contrarian: D2↑ → leg BULL (%bear 37% vs 61%) |
| **FG** | greed subiendo | +0.70 | **contrarian: D2↑ → leg BEAR** (%bear 74% vs 31%) |
| **SV5_TURB** | caos subiendo | ~0 | NINGUNA (ni dirección ni cascade) |
| **SKEW** | miedo de cola subiendo | +0.22 | débil: D2↑ → leg BEAR (%bear 58% vs 45%) |
| **CREDIT** | risk-on subiendo (HYG/LQD) | +0.49 | contrarian: D2↑ → leg BEAR (%bear 65% vs 37%) |
| **YIELD_CURVE** | steepening | +0.10 | débil: D2↑ → leg BEAR (%bear 54% vs 43%) |
| **ROTATION** | rotación risk-on | +0.55 | contrarian: D2↑ → leg BEAR (%bear 66% vs 35%) |
| **BSI (S5TW)** | amplitud mejorando | +0.83 | **contrarian: D2↑ → leg BEAR** (%bear 71% vs 30%) |
| **DXY** | dólar fuerte | −0.10 | NINGUNA (%bear 50/50) |

**Lectura económica:** los indicadores de "miedo" (VIX/VVIX/PCR) tienen D2 **contrario**:
el miedo subiendo → pierna alcista próxima (comprar el pánico). Los indicadores de "euforia/amplitud"
(FG/BSI/CREDIT/ROTATION) también son **contrarios**: euforia subiendo → pierna bajista próxima
(techo). DXY y SV5_TURBULENCE no aportan dirección.

---

## 4. SÍNTESIS — ¿qué estaciones tienen D2 informativo?

**D2 INFORMATIVO (dirección del próximo leg, |ρ| ≥ 0.20):**
1. **FG** ρ=+0.381 — greed acelerando → techo (leg bear). MEJOR.
2. **BSI** ρ=+0.363 (S5TW) / +0.379 (S5FI) — amplitud acelerando → techo.
3. **VIX** ρ=−0.310 — miedo acelerando → suelo (leg bull).
4. **ROTATION** ρ=+0.257 — rotación risk-on acelerando → techo.
5. **CREDIT** ρ=+0.253 — crédito acelerando → techo.
6. **PCR** ρ=−0.215, **VVIX** ρ=−0.197 — miedo acelerando → suelo.

**D2 MARGINAL (|ρ| 0.09–0.12):** SKEW (+0.115), YIELD_CURVE (+0.090).

**D2 NO INFORMATIVO:** **SV5_TURBULENCE** (−0.028), **DXY** (−0.020).
  — SV5_TURBULENCE mide caos/volumen, no dirección; su D2 no correlaciona con SPY ni con leg.
  — DXY es un asset externo (dólar); su velocidad no mapea a piernas de SPY.

**Regla de oro:** D2 NO sirve para cascade_conviction (eso es dominio de D1 + domino).
D2 es una señal de **dirección contrariana** para el forecast del próximo leg: úsalo en TAF
(direction forecast), no en cascade. La velocidad confirma el movimiento reciente de SPY
(NO lo anticipa), y su utilidad es como voto de "extremo/agotamiento" (mean-reversion en el siguiente leg).

---

## Nota técnica BSI
`decay_check_cascade_conviction.py` usa ticker **S5FI** para "bsi", pero el prompt define
BSI = "amplitud S5TW". Ambos dan casi idéntico resultado (ρ bear: S5TW +0.363, S5FI +0.379).
Recomendación: unificar en uno (S5FI es el que está en producción).
