# PROMPT: Auditoría de Escala Gaussian por Estación + Cálculo σ de Muestra — Fat-Tails

**Fecha:** 03-Sep-2026
**Propósito:** Auditar, para CADA una de las 11 estaciones METAR: (1) la calibración/cálculo de su escala en desviaciones estándar sobre una muestra, y (2) cómo la forma fat-tailed de la distribución rompe el supuesto gaussiano de ese cálculo. Determinar la escala CORRECTA para definir extremos, rareza y overflow en datos reales (no gaussianos).

**Hallazgo ya confirmado (punto de partida — reproducido con datos):**
El modulo `sigma_overflow.py` usa `STATION_MU_SIGMA` con μ/σ PARAMÉTRICOS FIJOS (población completa + look-ahead), mientras el canon (`gaussian_scale_policy.md` Rule S1) dice explícitamente usar percentiles EMPÍRICOS, no μ±kσ. El resultado, con datos fat-tailed:

| Estación | Overflow paramétrico (z>3) | Overflow empírico (>P99.865) | Multiplicador |
|:---------|:--------------------------:|:----------------------------:|:-------------:|
| VIX | 1.85% | 0.142% | **13× sobre-estima** |
| PCR | 0.70% | 0.140% | 5× |
| SKEW | 0.34% | 0.142% | 2.4× |
| Todas | — | — | — |

**Las 11 estaciones son NO-gaussianas** (Shapiro p<2e-19 todas; PCR kurt=28.18, VIX 8.45).

---

## PARTE A — Auditar el cálculo σ de una muestra por estación

Para CADA estación (vix, vvix, pcr, fg, sv5_turbulence, skew, credit, yield_curve, rotation, dxy, bsi), sobre el lake (`{est}_val` en `data/research/continuous_metar_lake.parquet`):

1. **Descriptivos reales:** μ, σ (sobna total), mediana, skewness, kurtosis, y cómo dista de la gaussiana (Shapiro).
2. **σ paramétrica vs σ robusta:** el σ de la muestra (desviación estándar squeada por outliers) vs estimadores robustos (MAD, IQR/1.349). En fat-tails, el σ estándar se "infla" en la cola → cuantificar.
3. **El cálculo actual de overflow (`z=(val−μ)/σ` con μ/σ del dict):** cuántos overflows z>3σ marca vs el empírico (>P99.865) vs el robusto. **Tabla completa por estación.**
4. **Comparación:** por estación, el umbral "3σ" paramétrico vs el percentil real P99.865 vs el MAD-4σ-equivalente. ¿Cuántos falsos/verdaderos positivos produce cada método?

## PARTE B — Explicar y corregir el "fat tail" por estación

Para cada estación, caracterizar la cola:
- **Grosor de cola:** estimar el exponente de cola (Hill estimator) o index tail de la muestra. VIX, PCR, SKEW tienen colas gruesas; ¿y yield/dxy/bsi?
- **¿Cuánto del "bin5 extremo" es verdaderamente extremo?** Con fat-tails, un valor que el bin5 captura (top 2.28% nominal) ocurre más a menudo. Reportar el % real que cae en cada bin extremo vs el 2.28% que el canon asume.
- **Consecuencia para overflow y rareza:** definir la corrección.

## PARTE C — Definir la escala correcta (diseño)

Con base en A y B, definir para todas las estaciones:

1. **Redefinir el z-score de overflow:** ¿debe ser `z_empirico = percentil_P(z)` o `z_robusto = (val − mediana)/MAD`? Para fat-tails, proponer el estimador correcto y justificar con datos.
2. **Redefinir "extremo" y "rareza" (§3.3):** la rareza de diamante NO debe basarse en 2.28% gaussiano asumido sino en el **% empírico observado** del bin/estado en el lake. Proponer `rareza_real = p(estado)` y cómo afecta a los diamantes actuales.
3. **Corregir `sigma_overflow.py`:** proponer el reemplazo de `STATION_MU_SIGMA` paramétrico por un método empírico/robusto por estación, con el código y las nuevas umbrales (cuántos overflows produce cada estación con el método correcto).
4. **¿Dónde más se usa μ/σ paramétrico?** Auditar si el lake bins o los fact stores dependen de este σ (o si solo el overflow lo usa). Determinar el alcance del impacto.

## PARTE D — Tabla resumen de la auditoría (entregable)

```
| Estación | μ real | σ real | σ robusto(MAD) | skew | kurt | %bin5 real | overflow_paramet. | overflow_empirico | overflow_robusto | Veredicto |
| VIX | ... | ... | ... | 2.2 | 8.45 | 5.28% | 156 | 12 | ... | fat-tail, recблизириar |
| ... | | | | | | | | | | |
```

## Verificación de aceptación
```bash
backend/.venv/bin/python << 'EOF'
# Para las 11 estaciones: mu, sigma, MAD, skew, kurt, %bin5 real,
# overflow param/vs empirico/vs robusto; tabla final.
EOF
```

## Reglas rectoras
- **La verdad la hablan los datos** — no asumir gaussiana; medir distribución real por estación.
- **No negar el fat-tail**: si una estación es fat-tailed (la mayoría lo son), el σ paramétrico la mide mal; corregir con el estimador correcto, no forzar gaussiana.
- **§3.3 se mantiene** (rareza=riqueza), pero la rareza se cuantifica con el % EMPÍRICO real, no con el 2.28% teórico.
- **Corregir solo lo medible**: el overflow paramétrico sobre-estima (13× VIX) → corregirlo; la rareza de diamante debe usar el % real.