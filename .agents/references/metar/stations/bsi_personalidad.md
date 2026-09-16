# Dossier de Personalidad V3 — BSI

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes

> **Estación:** `bsi` · **Polaridad Canónica:** `INVERTED` · **Rol:** `Localizador Temporal de Máxima Precisión de Suelos (93.3% en rango).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `BSI` (Breadth S5TW (Stocks Above 20-DMA))
- **Física:** Porcentaje de componentes del S&P 500 cotizando por encima de su media móvil de 20 sesiones.
- **Incepción Oficial:** `1993-01-29` | **Cobertura:** `1993-01-29 a 2026-09-03`
- **Muestra Total:** `8,457` barras diarias continuas | **Total Episodios:** `6,321`
- **Espacio de Estados:** `112` registrados | `112` poblados empíricamente
- **Distribución de Rareza:** `44` estados con $N < 10$ (39.3% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo | Acción Canónica (Regla 20) | Juicio Contextual de Convicción |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|:---|:---|
| 0 | `BREADTH_WASHED_OUT` | 239 | 54.0% | +0.1% | +0.28% | **Amplitud Destruida / 93.3% Rango de Suelo** | `Piso / Capitulación de Amplitud` | `MKT_BUY_DIP_TACTICAL` | < 10% de acciones sobre su 20-DMA. Máxima precisión de localización de giros del sistema; preparar compras escalonadas. |
| 1 | `OVERSOLD_BREADTH` | 990 | 56.8% | +2.9% | +0.46% | **Rebote de Amplitud en Expansión (+2.9% Edge)** | `Acumulación / Ensanchamiento` | `MKT_ACCUMULATE_STRUCTURAL` | Operacionalmente superior a D1=0 por mayor N y edge confirmado. En zz75 el Hit Rate se expande al 65.2%. |
| 2 | `NEUTRAL_LOW_BREADTH` | 1897 | 52.0% | -1.9% | +0.22% | **Amplitud Media-Baja** | `Participación Selectiva` | `MKT_HOLD_STABLE` | 35-50% de componentes participando; selectividad en nombres individuales. |
| 3 | `NEUTRAL_HIGH_BREADTH` | 1880 | 53.0% | -0.9% | +0.32% | **Amplitud Saludable** | `Mercado Amplio` | `MKT_HOLD_STABLE` | 50-78% de componentes sobre media de 20 sesiones. Tendencia sana y diversificada. |
| 4 | `EXPANSIVE_BREADTH` | 1051 | 53.3% | -0.6% | +0.30% | **Amplitud Fuerte** | `Impulso de Participación` | `MKT_HOLD_STABLE` | Participación generalizada en la subida; continuar con asignación core. |
| 5 | `HYPER_EXPANSIVE_BREADTH` | 264 | 54.2% | +0.3% | +0.33% | **Breadth Thrust / Impulso Masivo** | `Empuje Extremo de Amplitud` | `MKT_HOLD_STABLE` | > 90% de stocks sobre media. Típicamente señala el arranque de un nuevo ciclo alcista, no un techo inmediato. |

### 2.2 Tríadas Singulares de Excepción (Moduladas por D2/D3 o |Edge| >= 10%)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Tier Cred (§3.3) | Directiva Específica |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|

| `0__0__3` | `BREADTH_WASHED_OUT` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 1.7 | 5 | `LOW` | **GATILLO DE REBOTE VIOLENTO (U-TURN):** Ejecutar compra inmediata `MKT_BUY_DIP_TACTICAL`. |
| `3__4__4` | `NEUTRAL_HIGH_BREADTH` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 4.12 | 2 | `ANECDOTAL` | **SINGULARIDAD ALCISTA ALTA CONVICCIÓN (+46.1%):** Compra agresiva `MKT_BUY_DIP_TACTICAL`. |
| `5__4__3` | `HYPER_EXPANSIVE_BREADTH` | `FAST_SPIKE_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 2.95 | 2 | `ANECDOTAL` | **SINGULARIDAD ALCISTA ALTA CONVICCIÓN (+46.1%):** Compra agresiva `MKT_BUY_DIP_TACTICAL`. |
| `5__3__3` | `HYPER_EXPANSIVE_BREADTH` | `ACCELERATING_UP_3D` | `VOL_ACCELERATING_EXPANSION` | -33.9% | 20.0% | 0.62 | 5 | `LOW` | **DRENAJE DE LIQUIDEZ / TRAMPA (-33.9%):** Veto de entrada `MKT_BLOCK_CRISIS`. |
| `3__1__4` | `NEUTRAL_HIGH_BREADTH` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | +30.7% | 84.6% | 3.06 | 13 | `HIGH` | **SINGULARIDAD ALCISTA ALTA CONVICCIÓN (+30.7%):** Compra agresiva `MKT_BUY_DIP_TACTICAL`. |
| `2__4__4` | `NEUTRAL_LOW_BREADTH` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -28.9% | 25.0% | 0.55 | 4 | `LOW` | **DRENAJE DE LIQUIDEZ / TRAMPA (-28.9%):** Veto de entrada `MKT_BLOCK_CRISIS`. |
| `3__1__1` | `NEUTRAL_HIGH_BREADTH` | `DECELERATING_DOWN_3D` | `VOL_MODERATE_COMPRESSION` | -22.3% | 31.6% | 0.67 | 19 | `HIGH` | **DRENAJE DE LIQUIDEZ / TRAMPA (-22.3%):** Veto de entrada `MKT_BLOCK_CRISIS`. |

> 📌 **Regla de Lookup para el Agente (`A-Read`):**

> 1. Al recibir el `state_key` actual, verificar si está registrado en la **Sub-tabla 2.2**.

> 2. Si existe en 2.2 → ejecutar directamente la **Directiva Específica**.

> 3. Si NO existe en 2.2 → aplicar la decisión del bin correspondiente en la **Sub-tabla 2.1 Baseline**.

> *Cero deducción, cero cálculo de polaridad en runtime.*

---

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `INVERTED`
  * *Regla:* Bin 0 = Estrés / Miedo / Descalabro (Suelo / Oportunidad); Bin 5 = Expansión / Facilidad.
- **Profesión de la Estación:** `Localizador Temporal de Máxima Precisión de Suelos (93.3% en rango).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| 0 (`BREADTH_WASHED_OUT`) | 7.9% | 29.7% | 43.9% | 10.0% | 1.7% | 6.7% | `t=0` (43.9%) | 61.0% | **0.268** | **Gatillo Síncrono** (día del pivote) |
| 1 (`OVERSOLD_BREADTH`) | 9.5% | 18.4% | 24.6% | 11.6% | 5.6% | 30.3% | `ENTRE` (30.3%) | 43.3% | **0.131** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_LOW_BREADTH`) | 7.4% | 9.1% | 9.0% | 10.0% | 7.5% | 57.0% | `ENTRE` (57.0%) | 47.6% | **0.272** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_HIGH_BREADTH`) | 4.1% | 3.9% | 3.9% | 4.9% | 5.0% | 78.1% | `ENTRE` (78.1%) | 52.0% | **0.406** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`EXPANSIVE_BREADTH`) | 3.7% | 3.8% | 3.1% | 4.6% | 3.4% | 81.4% | `ENTRE` (81.4%) | 53.5% | **0.435** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`HYPER_EXPANSIVE_BREADTH`) | 3.8% | 3.8% | 8.0% | 6.8% | 3.8% | 73.9% | `ENTRE` (73.9%) | 54.4% | **0.402** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **61.9% de su masa en ENTRE**. Esto confirma que `BSI` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT3` | **Lead-Time:** Corto (acción pura y dura del mercado; la confirmación final de la participación).
- **Precursores Causalmente Previos:** CAT1 (Credit) y CAT2 (VIX/PCR).
- **Confirmadores Posteriores:** S5FI (50-DMA) y S5TH (200-DMA).

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.

---

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)

El acoplamiento entre escalas distingue el ruido táctico del régimen duradero:

| Escala | Time-Stop Vertical | Baseline Hit Rate (MIN) | Baseline EV (MIN) | Significado Operativo |
|:---:|:---:|:---:|:---:|:---|
| **zz25 (2.5%)** | 35 barras (P95) | 53.9% | 0.41% | Horizonte Táctico / Swing Corto (Scalp & Rebound) |
| **zz50 (5.0%)** | 110 barras (P95) | 58.0% | 1.45% | Horizonte Intermedio / Swing Estructural |
| **zz75 (7.5%)** | 190 barras (P95) | 61.6% | 2.66% | Régimen Primario de Mercado / Posicionamiento Core |

- **Convergencia Estructural (zz25 + zz50 + zz75 alineados con EV creciente):** Señal mayor de fondo. Habilita acumulación a largo plazo (`MKT_ACCUMULATE_STRUCTURAL`).
- **Divergencia Táctica (zz25 desacoplado de zz75):** Rebote contratendencial o corrección técnica. Prohibido posicionar a largo plazo; operar exclusivamente rebotes tácticos ceñidos (`MKT_BUY_DIP_TACTICAL`).
- **Filtro de Operabilidad:** Razón Riesgo/Beneficio $RR = MFE / |MAE| \ge 1.0$. Si $RR < 1.0$, la combinación se considera matemáticamente no operable.

---

## 6. PERFIL DIMENSIONAL INTEGRADO (D1 Magnitud × D2 Velocidad Cinemática × D3 Volatilidad Interna)

- **Papel de D1 (Magnitud Estática):** Determina la ubicación de la estación dentro de la población gaussiana histórica de 33 años.
- **Papel de D2 (Velocidad Cinemática 72h, $\Delta 3d$):** Modula la inercia inmediata. Destacan las siguientes singularidades:
  * Modula el impacto de D1: $D2=0$ desacelera pánicos o acelera colapsos; $D2=4$ confirma impulsos o clímax de compras.
- **Papel de D3 (Volatilidad Interna) — Amplificador No Lineal en 'U':**
  * **$D3=0$ (`VOL_EXTREME_SQUEEZE`):** Compresión extrema de volatilidad interna. El indicador actúa como un resorte comprimido (*coiled spring*). Acumula energía elástica masiva; cuando una perturbación en D2 impacta este estado, detona un **U-Turn violento** (giro en V o reversión instantánea de alta asimetría; ej. en BSI con $t=0$, $HR = 100\%$).
  * **$D3 \in [1, 2]$ (`VOL_COMPRESSION` a `VOL_NEUTRAL`):** Régimen ordinario e inercial. Baja asimetría.
  * **$D3=3$ (`VOL_EXPANSION`):** Expansión de volatilidad en pleno desarrollo.
  * **$D3=4$ (`VOL_PEAK_DECEL`):** Clímax y agotamiento de la volatilidad. Absorción institucional que frena el movimiento y constituye el segundo punto focal de **U-Turns** por agotamiento.

---

## 7. CONTRASTE DE LA PROSA Y EL VERBO (Mitos Narrativos vs Comportamiento Cuantitativo)

Evaluación formal bajo los 4 arquetipos institucionales:

| Bin | Label | Arquetipo | El Mito Narrativo (La Prosa) | La Realidad Cuantitativa (El Verbo) | Directiva para el Agente |
|:---:|:---|:---:|:---|:---|:---|
| 0 | `BREADTH_WASHED_OUT` | **Contrarian / Coherente** | Si el 95% de las acciones están cayendo bajo su media, hay que salirse porque nadie sostiene el mercado. | BSI < 10.3% tiene una precisión de localización de suelos de 93.3% (casi nunca falla en caer dentro de +/- 2 barras del suelo). El rebote inicial es violento. | **Preparar órdenes de compra escalonadas; el suelo físico está presente (MKT_BUY_DIP_TACTICAL).** |
| 1 | `OVERSOLD_BREADTH` | **Motor de Deriva (alcista)** | Amplitud sobrevendida sigue siendo peligrosa; el mercado va a seguir cayendo. | HR=55.8% a zz25, HR=58.3% a zz75 con Edge +2.9%. Operacionalmente superior a D1=0 por mayor N y edge confirmado. | **Acumulación gradual; la amplitud se está recuperando (`MKT_ACCUMULATE_STRUCTURAL`).** |
| 4 | `EXPANSIVE_BREADTH` | **Coherente (neutral)** | Amplitud fuerte confirma tendencia; mantener posiciones. | HR=51.5% a zz25, HR=57.0% a zz75. Participación generalizada en la subida sin edge direccional fuerte. | **Mantener posiciones core sin cambios (`MKT_HOLD_STABLE`).** |
| 5 | `HYPER_EXPANSIVE_BREADTH` | **Trampa Narrativa** | Amplitud > 90% es sobrecompra y el mercado va a colapsar. | Amplitud > 90% suele ser un 'Breadth Thrust' al inicio de un nuevo mercado alcista. | **No shortear un Breadth Thrust; comprar pullbacks.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Octubre 2008 (BSI 1.2%), Agosto 2011 (BSI 2.5%), Diciembre 2018 (BSI 1.8%), Marzo 2020 (BSI 1.2%).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `260` episodios (4.11% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** BSI < 15.0% o BSI > 85.0%.
- **Alerta Roja (CRITICAL / EMERGENCY):** BSI < 10.3% (-2σ / Washed Out / Tier >= 1). Blowoff < 0.9%.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** `MKT_BLOCK_CRISIS (si D2 es FAST_CRUSH_3D con liquidación masiva).`
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → `MKT_BUY_DIP_TACTICAL (en cuanto BSI comience a cruzar al alza desde < 10%).`
- **Criterio de Desactivación:** BSI recuperando > 35.0% de forma sostenida.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI | Acción Recomendada |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `0__0__3` | `BREADTH_WASHED_OUT` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 1.7 | 5 | [56.6%, 100.0%] | `MKT_BUY_DIP_TACTICAL` |
| `3__4__4` | `NEUTRAL_HIGH_BREADTH` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 4.12 | 2 | [34.2%, 100.0%] | `MKT_ACCUMULATE_STRUCTURAL` |
| `5__4__3` | `HYPER_EXPANSIVE_BREADTH` | `FAST_SPIKE_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 2.95 | 2 | [34.2%, 100.0%] | `MKT_BUY_DIP_TACTICAL` |
| `3__1__4` | `NEUTRAL_HIGH_BREADTH` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | +30.7% | 84.6% | 3.06 | 13 | [57.8%, 95.7%] | `MKT_ACCUMULATE_STRUCTURAL` |
| `0__2__4` | `BREADTH_WASHED_OUT` | `STABLE_CONTINUATION_3D` | `VOL_PEAK_DECELERATION` | +21.1% | 75.0% | 1.57 | 4 | [30.1%, 95.4%] | `MKT_ACCUMULATE_STRUCTURAL` |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI | Acción Recomendada |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `1__4__2` | `OVERSOLD_BREADTH` | `FAST_SPIKE_3D` | `VOL_NEUTRAL_BASELINE` | -53.9% | 0.0% | 0.67 | 2 | [0.0%, 65.8%] | `MKT_BLOCK_CRISIS` |
| `5__4__0` | `HYPER_EXPANSIVE_BREADTH` | `FAST_SPIKE_3D` | `VOL_EXTREME_SQUEEZE` | -53.9% | 0.0% | 0.47 | 2 | [0.0%, 65.8%] | `MKT_BLOCK_CRISIS` |
| `5__4__1` | `HYPER_EXPANSIVE_BREADTH` | `FAST_SPIKE_3D` | `VOL_MODERATE_COMPRESSION` | -53.9% | 0.0% | 0.49 | 5 | [0.0%, 43.4%] | `MKT_BLOCK_CRISIS` |
| `5__3__3` | `HYPER_EXPANSIVE_BREADTH` | `ACCELERATING_UP_3D` | `VOL_ACCELERATING_EXPANSION` | -33.9% | 20.0% | 0.62 | 5 | [3.6%, 62.4%] | `MKT_BLOCK_CRISIS` |
| `2__4__4` | `NEUTRAL_LOW_BREADTH` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -28.9% | 25.0% | 0.55 | 4 | [4.6%, 69.9%] | `MKT_BLOCK_CRISIS` |
