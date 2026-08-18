# AUDITORÍA CUANTITATIVA — ESTILO LÓPEZ DE PRADO
## Botero Trade · METAR/SIGMET · 11 estaciones · 1,589 pivotes zz25 SPY (1993–2026)

**Filosofía:** dato mata relato · tonos de grises (probabilístico) · nada binario.
**Datos:** 1,589 pivotes zigzag zz25 confirmados de SPY, features D1 (nivel) / D2 (velocidad Δ3d) / D3 (volatilidad std2/std10) para las 11 estaciones.
**Outcomes:** cascade_50 (binario), cascade_75 (binario), next_leg_direction (dirección del próximo leg).

---

## 1. MUTUAL INFORMATION — ¿qué features llevan info NO-lineal que ρ pierde?

**Método:** MI por bins (8 cuantiles) + χ² de independencia + test de permutación (300 shuffles) para p-value. Comparada contra Spearman |ρ|.

### Cascade_50 (continuación) — MI por bins, ordenada

| Feature | MI | p_perm | p_χ² | \|ρ\| | N |
|---|---|---|---|---|---|
| **vix_val (D1 nivel)** | **0.109** | 0.003 | 3.6e-65 | **0.426** | 1590 |
| **fg_val (D1 nivel)** | **0.071** | 0.003 | 3.4e-14 | 0.283 | 569 |
| **credit_val (D1 nivel)** | **0.062** | 0.003 | 4.8e-20 | 0.307 | 915 |
| vix_vel (D2) | 0.024 | 0.003 | 3.1e-13 | 0.067 | 1590 |
| bsi_val (D1) | 0.024 | 0.003 | 4.2e-13 | 0.176 | 1590 |
| rotation_val (D1) | 0.022 | 0.003 | 2.2e-10 | 0.153 | 1379 |
| **yield_curve_vel (D2)** | **0.018** | 0.003 | 5.2e-10 | **0.007** | 1590 |
| vvix_val (D1) | 0.018 | 0.003 | 4.5e-05 | 0.151 | 924 |
| dxy_vel (D2) | 0.012 | 0.003 | 2.8e-06 | 0.038 | 1590 |
| credit_vel (D2) | 0.012 | 0.003 | 4.1e-07 | 0.029 | 1590 |

**→ 22/33 features con MI significativa (p_perm < 0.05).**

### El hallazgo clave: la VELOCIDAD (D2) es NO-LINEAL para cascade

Features con **MI significativa pero \|ρ\| < 0.15** (relación NO-monotónica, invisible para la correlación):

| Feature | MI | \|ρ\| | Lectura |
|---|---|---|---|
| vix_vel (D2) | 0.024 | 0.067 | pánico *construyéndose* y pánico *resolviéndose* → ambos → cascade (forma de U) |
| yield_curve_vel (D2) | 0.018 | 0.007 | steepening/flattening rápido → cascade, dirección no-monotónica |
| dxy_vel (D2) | 0.012 | 0.038 | movimientos bruscos del dólar (ambas direcciones) → cascade |
| credit_vel (D2) | 0.012 | 0.029 | ídem en crédito |

**Conclusión 1:** Para **cascade** (continuación), el D2 (velocidad) aporta información **genuinamente no-lineal** que la correlación de Spearman descarta casi a cero. La señal D2 es **simétrica** (subir o bajar rápido → cascade), por eso ρ≈0 pero MI≠0. Esto VALIDA que D2 no se puede "sumar" linealmente al cascade_conviction (consistentes con los 3 intentos rechazados previos) — pero su info no es nula, es *de otra naturaleza* (timing/fase, no dirección).

### Next_leg_direction (dirección) — MI por bins

| Feature | MI | p_perm | \|ρ\| | N |
|---|---|---|---|---|
| **bsi_vel (D2)** | **0.069** | 0.003 | **0.363** | 1590 |
| **vix_vel (D2)** | **0.057** | 0.003 | **0.310** | 1590 |
| **bsi_val (D1)** | **0.056** | 0.003 | **0.309** | 1590 |
| pcr_val (D1) | 0.039 | 0.003 | 0.267 | 917 |
| fg_val (D1) | 0.036 | 0.003 | 0.233 | 569 |
| rotation_vel (D2) | 0.031 | 0.003 | 0.240 | 1590 |

**Conclusión 2:** Para **dirección**, la relación es mayormente **monotónica** (ρ captura casi toda la info). La velocidad D2 de **BSI** (ρ=+0.363) y de **VIX** (ρ=−0.310) son los predictores dominantes — confirma hallazgo previo. Aquí MI y ρ coinciden: la info es lineal.

### Contraste cascade vs dirección (el hallazgo estructural más importante)

| | Cascade (continuación) | Dirección (próximo leg) |
|---|---|---|
| Dimensión dominante | **D1 nivel** (VIX, FG, Credit) | **D2 velocidad** (BSI, VIX, PCR) |
| Naturaleza de la info | **NO-lineal** (D2 en U) | **Lineal/monotónica** |
| Top feature | vix_val (MI 0.109) | bsi_vel (MI 0.069) |

Los dos objetivos responden a **mecanismos distintos**: cascade = nivel de estrés (D1), dirección = momentum/fase (D2). Son ortogonales por construcción.

---

## 2. ORTOGONALIDAD REAL — clustering vs familias propuestas

**Método:** matriz de correlación Pearson + matriz de MI + clustering jerárquico (Ward sobre distancia 1−\|ρ\|) + PCA.

### Matriz de correlación (D1 niveles) — pares fuertes

| Par | ρ | MI | |
|---|---|---|---|
| **credit ↔ yield_curve** | **−0.588** | **0.974** | máxima MI del dataset |
| **fg ↔ bsi** | **+0.686** | **0.690** | máxima ρ |
| vix ↔ credit | −0.612 | 0.739 | |
| credit ↔ dxy | +0.446 | 0.941 | |
| yield_curve ↔ dxy | −0.352 | 0.886 | |
| vix ↔ vvix | +0.368 | 0.470 | **¡más débil de lo esperado!** |
| pcr ↔ skew | −0.153 | 0.232 | **casi nula** |

### Clustering jerárquico real (k=4)

```
Cluster 1: {pcr, fg, bsi}          ← sentimiento/posicionamiento/breadth
Cluster 2: {vvix, dxy}             ← régimen de vol + dólar
Cluster 3: {vix, skew, credit, yield_curve}  ← estrés + macro
Cluster 4: {sv5_turbulence}        ← ÚNICO y ORTOGONAL
```
(k=6 separa `rotation`, `skew` y `yield_curve`; `sv5_turbulence` permanece solo siempre.)

### Validación de FAMILIAS propuestas

| Familia propuesta | ρ̄ intra | MĪ intra | ρ̄ inter | Veredicto |
|---|---|---|---|---|
| **Miedo (VIX+VVIX)** | 0.368 | 0.470 | 0.257 | **⚠ REFUTADA** — VIX correlaciona MÁS con credit (−0.61) que con VVIX (+0.37) |
| **Posicionamiento (PCR+SKEW)** | 0.153 | 0.232 | 0.210 | **⚠ REFUTADA** — casi independientes |
| Sentimiento (FG solo) | — | — | — | N/A (single) |
| Batalla (SV5T solo) | — | — | — | N/A (single) |
| **Participación (BSI+Rotation)** | 0.256 | 0.559 | 0.208 | **⚠ REFUTADA** — BSI va con FG/BSI/PCR, no con Rotation |
| **Macro (Credit+Yield+DXY)** | **0.462** | **0.934** | 0.143 | **✅ VÁLIDA** — única familia coherente |

**Conclusión 3:** Las familias propuestas por intuición **no sobreviven el clustering**. La realidad empírica:
1. **Macro/estrés** (credit, yield_curve, dxy, vix, skew) = familia real y densa.
2. **Breadth/sentimiento** (fg, bsi, pcr) = segundo núcleo.
3. **SV5_TURBULENCE es la estación MÁS ORTOGONAL del sistema** — MI≤0.48 con todo, ρ≤0.22 con todo. Es la única que aporta información genuinamente independiente (consistente con su rol de "timing/battle sensor", no de dirección).
4. VVIX es híbrida (vol-regime + dólar), NO "miedo" junto a VIX.

### PCA — dimensionalidad efectiva

PC1 30.5% · PC2 20.4% · PC3 12.4% (cum 63.4%) → **~6 componentes efectivos** para 11 estaciones. Hay redundancia sustancial (~45% de la varianza se comprime), pero **no colapsa a 1-2 factores** — el sistema NO es redundante en bloque.

---

## 3. TRIPLE BARRIER — labeling alternativo

**Método:** para cada pivote, camino forward de precio con 3 barreras: profit (+X%), stop (−Y%), tiempo (horizonte). Label = {+1 profit primero, −1 stop primero, 0 tiempo}.

| Parámetros | Distribución (+1/−1/0) | IC cascade_conviction → barrera | IC cascade_conviction → cascade_50 | Δ\|IC\| |
|---|---|---|---|---|
| 5d, +3%/−2% | 409/611/570 | **+0.112** | +0.414 | **−0.302** |
| 20d, +5%/−3% | 466/741/383 | **+0.116** | +0.414 | **−0.298** |
| 20d, +8%/−4% | 187/618/785 | **+0.006** | +0.414 | **−0.408** |

**d1_bear_5 → barrera:** +0.141 · **mean_zk_pbull_A (estado completo) → barrera:** +0.258

**Conclusión 4:** El etiquetado Triple Barrier **destruye** el poder predictivo del cascade_conviction (IC +0.41 → +0.11, degradación ~73%). El cascade_conviction está **calibrado específicamente para predecir cascade** (continuación de la estructura zigzag), NO para predecir magnitud/dirección de retorno. Notablemente, el **vector de estado completo (zk_p_bull)** predice *mejor* la barrera que el cascade_conviction (+0.258 vs +0.112) — coherente con que dirección ≠ cascade.

**Implicación operativa:** si el objetivo es un retorno barrier-based (no cascade), el modelo debe re-entrenarse sobre ese target; el cascade_conviction NO se transfiere.

---

## 4. PBO — Probability of Backtest Overfitting

**Método:** Combinatorial Purged Cross-Validation (López de Prado). S=8 grupos cronológicos, C(8,2)=28 combinaciones test. Familia de 40 modelos (4 conjuntos de estaciones × 10 pesos w_bear ∈ [0.30, 0.75]).

| Métrica | Valor |
|---|---|
| Modelos en familia | 40 |
| Combinaciones CPCV | 28 |
| **PBO** | **28.6%** |
| Ranking relativo OOS del modelo elegido IS (0=peor, 1=mejor) | **0.683** |
| Mejor-IS queda en Top 50% OOS | 71.4% |
| Mejor-IS queda en Bottom 50% OOS | 28.6% |

**Walk-forward OOS (ventanas rodantes 5 años):**
- Folds positivos: **26/28 (92.9%)**
- IC medio OOS: **+0.302** · mediana +0.335 · min/max −0.256 / +0.571

**Bootstrap (2000 resamples, full-sample):**
- IC full-sample: **+0.414**
- CI 95%: **[+0.371, +0.455]**
- % bootstrap positivo: **100.0%**

**Conclusión 5:** PBO = **28.6%** (riesgo moderado, no nulo). El IC +0.41 NO es un artefacto de selección — sobrevive walk-forward (92.9% folds positivos, OOS +0.30) y bootstrap (100% positivo). **PERO** hay un matiz honesto: el modelo ganador in-sample varía según el split — frecuentemente **VixBsFg (3 estaciones) con w_bear≈0.70** gana sobre Grupo A (5 estaciones). La región de pesos es relativamente plana y la *elección del conjunto de estaciones* introduce riesgo de selección. El 28.6% es la probabilidad de que el modelo elegido IS quede en la mitad inferior OOS.

---

## 5. STRUCTURAL BREAKS — CUSUM sobre IC por década

**IC cascade_conviction → cascade_50 por década:**

| Década | IC | N | p-value |
|---|---|---|---|
| 1990s | +0.410 | 280 | 8.5e-13 |
| 2000s | +0.367 | 690 | 2.0e-23 |
| 2010s | +0.376 | 308 | 9.4e-12 |
| **2020s** | **+0.559** | 311 | **5.7e-27** |

**CUSUM (rolling W=150):**
- IC medio rolling: +0.361
- CUSUM max: 40.46
- **p-value (bootstrap 1000): 0.0000 → Structural break SIGNIFICATIVO**

**Tasa de cascade baseline por década:**
1990s 45.2% · 2000s 55.1% · 2010s 47.1% · 2020s 48.9%

**IC d1_vote → cascade_50 por estación y década (Δ max):**

| Station | 1990s | 2000s | 2010s | 2020s | Δ max |
|---|---|---|---|---|---|
| vix | −0.355 | −0.360 | −0.400 | −0.499 | +0.144 |
| bsi | −0.218 | −0.155 | −0.083 | −0.349 | +0.265 |
| fg | ~0 | ~0 | −0.153 | −0.398 | +0.398 |
| credit | ~0 | −0.214 | −0.087 | −0.258 | +0.258 |
| rotation | −0.096 | −0.115 | −0.126 | −0.148 | +0.052 |

**Conclusión 6:** La relación señal→outcome **cambió en el tiempo** (CUSUM p=0.0000). Patrón:
1. El IC del cascade_conviction **se fortalece en la década 2020** (+0.559 vs +0.37–0.41 previas) — el régimen post-2020 (QE masivo, crisis 2020, 2022 bear) amplifica la señal de estrés.
2. **FG y Credit son estaciones "nuevas"** — su señal direccional solo existe desde ~2010 (datos con cobertura limitada antes; FG cobertura 35.8%). Su IC salta de ~0 a −0.40/−0.26 en la década 2020. **Riesgo de survivorship:** la validez de FG/Credit está concentrada en el régimen reciente.
3. **VIX y Rotation son las más estables** (Δ max pequeños) — señal persistente a través de 3 décadas.
4. La tasa baseline de cascade también varía (χ² p=0.020 previamente confirmado): 2000s 55% vs 1990s 45%.

---

## 6. SÍNTESIS — LOS 5 HECHOS MÁS ROBUSTOS Y PROBABLES

### HECHO 1 — El vector de estado completo (D1×D2×D3) es 3.2× superior a D1-only para predecir dirección
D1-only → dirección: IC = **−0.155** · Estado completo (11 estaciones, zk_p_bull) → dirección: IC = **−0.489**.
*Ratio 3.2×. Confianza: MUY ALTA (N=1,589, 33 años, consistente con IC=−0.425 del hallazgo previo).*

### HECHO 2 — Cascade y dirección son dos objetivos ORTOGONALES con mecanismos distintos
Cascade (continuación) lo domina **D1 nivel de estrés** (VIX MI=0.109, ρ=+0.426); dirección lo domina **D2 velocidad** (BSI ρ=+0.363, VIX ρ=−0.310). IC del cascade_conviction → dirección = −0.086 (≈0).
*Confianza: MUY ALTA — dos señales independientes, confirmadas por MI y ρ.*

### HECHO 3 — La velocidad (D2) lleva información NO-lineal sobre cascade que ρ pierde
vix_vel MI=0.024 con \|ρ\|=0.067 (p_perm=0.003); yield_curve_vel MI=0.018 con \|ρ\|=0.007. La señal D2 es **simétrica** (subir o bajar rápido → cascade), por eso es invisible a la correlación lineal pero real.
*Confianza: ALTA — p_perm < 0.005 con test de permutación, 22/33 features significativas.*

### HECHO 4 — Las "familias" propuestas no sobreviven el clustering; SV5_TURBULENCE es la única estación verdaderamente ortogonal
Solo **Macro (credit+yield_curve+dxy)** se confirma (ρ̄=0.46, MĪ=0.93). Miedo (VIX+VVIX) y Posicionamiento (PCR+SKEW) quedan **refutadas**. SV5T tiene MI≤0.48 con todo → aporta info independiente (consistente con su rol de timing, no dirección).
*Confianza: ALTA — clustering jerárquico + PCA (6 PCs efectivas).*

### HECHO 5 — El cascade_conviction IC=+0.414 NO es overfit, pero tiene riesgo de selección moderado
PBO=28.6%, walk-forward OOS +0.302 (26/28 folds positivos, 92.9%), bootstrap CI [+0.371, +0.455] (100% positivo). El IC es real, **pero** la relación señal→outcome cambió en el tiempo (CUSUM p=0.0000, IC 2020s +0.559 vs 1990s +0.410) y FG/Credit concentran su validez en el régimen reciente.
*Confianza: ALTA para la robustez del IC; MODERADA para la estabilidad temporal (structural break confirmado).*

---

## Tabla resumen de confianza

| Hecho | Confianza | p-value / evidencia |
|---|---|---|
| Estado completo 3.2× > D1-only (dirección) | Muy alta | N=1,589, 33 años |
| Cascade ⟂ Dirección (D1 vs D2) | Muy alta | MI y ρ divergentes |
| D2 no-lineal para cascade | Alta | p_perm=0.003 |
| Familias refutadas, SV5T ortogonal | Alta | clustering + PCA |
| IC +0.414 no-overfit pero PBO 28.6% | Alta/Moderada | walk-forward 92.9% +, CI [+0.37,+0.46] |

## Artefactos generados (scratch/)

- `quantitative_audit_lopez_de_prado.py` — pipeline completo (6 análisis)
- `quants_obs.pkl` — dataset extraído (1,590 × 141 features)
- `quants_audit_output.txt` — salida completa
- `pbo_cpcv.py` + `pbo_results.json` — PBO CPCV (28.6%)
- `mi_permutation_test.py` + `mi_permutation_results.csv` — MI con p-values
- `mi_results.csv` — MI kNN (ranking alternativo)

## Limitaciones honestas

1. **FG cobertura 35.8%** (N=569) y **Credit N=915**, **PCR N=917**, **VVIX N=924** — indicadores con historia incompleta. Su validez está sesgada al régimen reciente (survivorship parcial).
2. **MI kNN vs MI bins divergen** — el estimador kNN (n_neighbors=3) subestima MI para targets binarios; el método bins+χ² es más robusto. Ambos incluidos.
3. **PBO usa z-score global** (no estrictamente expanding-window), lo que puede subestimar ligeramente el overfitting real.
4. **Triple Barrier** usó cierre diario (no intradía) — las barreras intra-día no son observables en este dataset.
