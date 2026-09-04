# PROMPT: Auditoría del Escalador Gaussiano METAR (edges expanding-window)

**Fecha:** 03-Sep-2026
**Propósito:** Auditar críticamente cómo el escalador gaussiano asigna los bins D1/D2/D3 (expanding-window percentile rank), y determinar si la observación de "sobrecarga" en los bins extremos es (a) esperable por diseño, (b) un artefacto de fat-tails / ventana corta, o (c) un error de calibración que invalida la "rareza = riqueza" (§3.3). **NO asumas un valor esperado teórico (2.28%) — verifica el comportamiento real del método.**

**Contexto técnico (ya verificado en código):**
```python
# build_continuous_metar_lake.py
PERCENTILES_D1 = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]  # 6 bins
PERCENTILES_D2 = [0.0228, 0.1587, 0.8413, 0.9772]          # 5 bins
PERCENTILES_D3 = [0.0228, 0.1587, 0.8413, 0.9772]          # 5 bins
MIN_EXPANDING = 252  # min 1 año

d1_rank = raw_val.expanding(min_periods=252).rank(pct=True)   # rank running del valor
d1_bin  = d1_rank.apply(lambda r: classify_bin_index(r, PERCENTILES_D1))
```
- El edge se aplica al **rank pct expanding**, NO al valor crudo ni a un quantile de la población final.
- El quants_obs (1,590 pivotes) y el lake (8,453 barras) usan este mismo `build_continuous_metar_lake.py`.

**Observaciones a auditar (reproducidas con datos reales, bins exclusivos del sentinel -1):**
| Estación | bin5 obs (≈periodo 'extremo alto') | bin0 obs |
| :-- | :-- | :-- |
| VIX | 5.28% | 3.02% |
| VVIX | 4.25% | 0.18% |
| PCR | 1.16% | 2.43% |
| FG | 2.27% | 1.26% |
| SV5_Turb | 6.78% | 0.99% |
| SKEW | 13.13% | 1.10% |
| CREDIT | 20.83% | 1.10% |
| YIELD | 2.90% | 9.44% |
| ROTATION | 2.34% | 2.92% |
| DXY | 6.27% | 5.05% |
| BSI | 4.33% | 3.84% |

---

## Preguntas de la auditoría (responder cada una con datos, no teoría)

### Q1 — Comportamiento esperado del ranking expanding
El `expanding(min_periods=252).rank(pct=True)` de una serie **no-gaussiana con fat-tails** (VIX, SKEW, CREDIT): ¿qué porcentaje REAL de observaciones en cada bin debería producir la población final? 
- **Verifica empíricamente:** recalcula el bin de una estación (ej. VIX) con una población de referencia, y compara el % real por bin vs 2.28%/13.59%/34.13% teórico. ¿Cuánto difiere por fat-tail?
- Distingue: el percentil del rank-expanding **no** garantiza 2.28% al final del total; solo lo garantiza *en cada punto* si la ventana tuviera población infinita y estacionaria. Cuantifica el desvío real.

### Q2 — El efecto "ventana corta / arranque"
Con `min_periods=252`, los primeros ~1000 puntos se clasifican sobre una ventana pequeña. ¿Cuánto distorsiona los bins extremos en los primeros años? ¿Los bin5/0 sobrecargados se concentran en los primeros años o a lo largo de toda la serie?

### Q3 — ¿Sobre la población, el reparto está dentro de lo esperado para datos fat-tailed?
Para cada estación, compara el % observado en bin5/bin0 con el que produciría un **simulacro del mismo método** aplicado a una serie con las mismas propiedades de cola. La pregunta clave: ¿la sobrecarga de CREDIT (20.8%) y SKEW (13.1%) se explica por fat-tails del indicador, o es desproporcionada (posible error de atribución de labels / dirección)?

### Q4 — Consecuencia para §3.3 / rareza
Si el % observado en bin5/bin0 dista del 2.28% teórico:
1. ¿Debe la "rareza de diamante" (§3.3) basarse en el **% teórico** (2.28%) o en el **% empírico observado** (p.ej. CREDIT 20.8%)?
2. Propón la métrica correcta de rareza: `rareza_real = p(bin) observado` vs `rareza_teorica = p(z-score)`.
3. Determina: ¿los diamantes actuales (basados en "rareza") usan una rareza mal cuantificada? Indica cuáles habría que re-clasificar.

### Q5 — Dirección física / labels por estación (spot-check)
Para CREDIT, verificar que `bin5 = EXTREME_EASE` y `bin0 = EXTREME_STRESS` correspondan a la **dirección física real** de la serie (valor alto = facilidad = bin5). Para SKEW igual. Si algún label está invertido, es un bug taxonómico que exige corrección (no solo recalibración).

---

## Verificación de aceptación

```bash
backend/.venv/bin/python << 'EOF'
# 1. Recalcular bins de VIX con expanding rank (reproducible) y reportar % real por bin
# 2. Mismo simulacro para CREDIT y SKEW (fat-tails), sobre población completa
# 3. Comparar % observado vs teórico; concluir por estación
# 4. Verificar dirección física de labels CREDIT (bin5=high value?) y SKEW
# 5. Determinar rareza correcta: empírica vs teórica
EOF
```

---

## Alcance

**Hacer:** auditar y cuantificar el comportamiento del escalador expanding-window; determinar si la sobrecarga es esperable o error; definir la métrica correcta de rareza (§3.3) basada en el % empírico; corregir cualquier label invertido.
**NO HACER:** no re-decidir la filosofía §3.3 (rareza=riqueza se mantiene); no tocar los edges sin confirmar primero la causa; no sobre-corregir sin el dato del desempeño empírico del bin.

**Reglas rectoras:** la verdad la hablan los datos. Una "sobrecarga" que es estructural (fat-tails + expanding) NO es un bug — es el verdadero comportamiento del indicador. Solo se corrige lo que es error real (labels invertidos, assignación incorrecta), y la rareza se reporta con el % empírico OA, no con el 2.28% teórico mal aplicado.