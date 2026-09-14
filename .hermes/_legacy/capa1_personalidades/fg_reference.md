# Referencia de Estación — FG

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes

> **Estación:** `fg` · **Polaridad Canónica:** `INVERTED` · **Rol:** `Contrarian en Suelos (EXTREME_FEAR = PISO) y Motor de Inercia en Techos (EXTREME_GREED = CONTINUACIÓN).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `FG` (CNN Fear & Greed Index (FG))
- **Física:** Sentimiento sintetizado de 7 sub-indicadores con inercia histórica de 504 días (2 años de ventana).
- **Incepción Oficial:** `2011-02-01` | **Cobertura:** `2011-02-01 a 2026-09-03`
- **Muestra Total:** `3,921` barras diarias continuas | **Total Episodios:** `2,403`
- **Espacio de Estados:** `82` registrados | `82` poblados empíricamente
- **Distribución de Rareza:** `43` estados con $N < 10$ (52.4% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_FEAR` | 29 | 69.0% | +12.9% | +0.69% | **Contrarian Alcista Extremo (+12.9% Edge)** | `Piso / Pánico de Sentimiento` |
| 1 | `FEAR` | 305 | 53.1% | -2.9% | +0.29% | **Sentimiento Defensivo en Desarrollo** | `Corrección Táctica` |
| 2 | `NEUTRAL_FEAR` | 856 | 54.4% | -1.6% | +0.36% | **Neutral** | `Equilibrio de Sentimiento` |
| 3 | `NEUTRAL_GREED` | 911 | 54.2% | -1.8% | +0.49% | **Neutral Constructivo** | `Apetito Ordinario` |
| 4 | `GREED` | 263 | 55.1% | -0.9% | +0.56% | **Apetito Expansivo por Riesgo** | `Expansión Alcista` |
| 5 | `EXTREME_GREED` | 39 | 59.0% | +2.9% | +0.89% | **Inercia Alcista Fuerte (+0.89% EV fwd)** | `Continuación por Inercia` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `INVERTED`
  * *Regla:* Bin 0 = Estrés / Miedo / Descalabro (Suelo / Oportunidad); Bin 5 = Expansión / Facilidad.
- **Profesión de la Estación:** `Contrarian en Suelos (EXTREME_FEAR = PISO) y Motor de Inercia en Techos (EXTREME_GREED = CONTINUACIÓN).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_FEAR`) | 6.9% | 13.8% | 51.7% | 6.9% | 6.9% | 13.8% | `t=0` (51.7%) | 80.0% | **0.414** | **Gatillo Síncrono** (día del pivote) |
| 1 (`FEAR`) | 7.5% | 15.7% | 23.6% | 14.4% | 7.2% | 31.5% | `ENTRE` (31.5%) | 39.6% | **0.125** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_FEAR`) | 6.9% | 7.4% | 8.1% | 7.4% | 6.1% | 64.3% | `ENTRE` (64.3%) | 49.1% | **0.316** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_GREED`) | 3.4% | 3.3% | 3.5% | 3.3% | 2.5% | 84.0% | `ENTRE` (84.0%) | 51.5% | **0.433** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`GREED`) | 1.1% | 1.1% | 1.1% | 1.1% | 0.8% | 94.7% | `ENTRE` (94.7%) | 55.8% | **0.529** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_GREED`) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | `ENTRE` (100.0%) | 59.0% | **0.59** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **70.9% de su masa en ENTRE**. Esto confirma que `FG` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT3` | **Lead-Time:** Corto a Medio (sentimiento derivado de Large Caps S&P 500, sin small caps IWM).
- **Precursores Causalmente Previos:** CAT1 (Credit) y CAT2 (VIX/PCR).
- **Confirmadores Posteriores:** BSI (amplitud de mercado).

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.
3. **Inercia de 504 días:** Fear & Greed incorpora una ventana móvil de 2 años de suavizado y mide exclusivamente S&P 500 Large Caps. Requiere confluencia de IWM para validar amplitud en small caps.

---

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)

El acoplamiento entre escalas distingue el ruido táctico del régimen duradero:

| Escala | Time-Stop Vertical | Baseline Hit Rate (MIN) | Baseline EV (MIN) | Significado Operativo |
|:---:|:---:|:---:|:---:|:---|
| **zz25 (2.5%)** | 35 barras (P95) | 56.0% | 0.46% | Horizonte Táctico / Swing Corto (Scalp & Rebound) |
| **zz50 (5.0%)** | 110 barras (P95) | 60.8% | 1.33% | Horizonte Intermedio / Swing Estructural |
| **zz75 (7.5%)** | 190 barras (P95) | 66.7% | 2.74% | Régimen Primario de Mercado / Posicionamiento Core |

- **Convergencia Estructural (zz25 + zz50 + zz75 alineados con EV creciente):** Señal mayor de fondo. Habilita acumulación a largo plazo (acumulación estructural).
- **Divergencia Táctica (zz25 desacoplado de zz75):** Rebote contratendencial o corrección técnica. Prohibido posicionar a largo plazo; operar exclusivamente rebotes tácticos ceñidos (compra táctica en corrección).
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
| 5 | `EXTREME_GREED` | **Motor de Deriva / Trampa Narrativa** | Vender inmediatamente cuando otros son codiciosos (Warren Buffett coloquial). | FG D1=5 tiene 86.7% de su masa en ENTRE con retorno positivo fwd 20d (+0.81%). Vender en euforia temprana es sangrado de costo de oportunidad. | **Mantener posiciones en tendencia fuerte mantener posición; solo ceñir trailing stops.** |
| 0 | `EXTREME_FEAR` | **Contrarian Puro** | El miedo extremo paraliza el mercado; hay que esperar a que los problemas económicos se resuelvan. | FG D1=0 (< 8.0) produce un WR del 67.4% a 20 días vista con PF 2.30 y +3.12% a 40d (PF 3.06). | **Comprar agresivamente el pánico extremo.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Agosto 2011 (FG 5), Diciembre 2018 (FG 2), Marzo 2020 (FG 2), Octubre 2022 (FG 11).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `318` episodios (13.23% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 1`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** FG < 25.0 (Fear) o FG > 71.0 (Greed).
- **Alerta Roja (CRITICAL / EMERGENCY):** FG < 8.0 (Extreme Fear / Tier >= 1) o FG > 87.0.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica en corrección.
- **Criterio de Desactivación:** FG regresando al rango neutral 40-60.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__0__2` | `EXTREME_FEAR` | `FAST_CRUSH_3D` | `VOL_NEUTRAL_BASELINE` | +44.0% | 100.0% | 6.11 | 2 | [34.2%, 100.0%] |
| `5__2__3` | `EXTREME_GREED` | `STABLE_CONTINUATION_3D` | `VOL_ACCELERATING_EXPANSION` | +44.0% | 100.0% | 3.61 | 2 | [34.2%, 100.0%] |
| `0__1__2` | `EXTREME_FEAR` | `DECELERATING_DOWN_3D` | `VOL_NEUTRAL_BASELINE` | +27.3% | 83.3% | 1.68 | 6 | [43.6%, 97.0%] |
| `2__4__3` | `NEUTRAL_FEAR` | `FAST_SPIKE_3D` | `VOL_ACCELERATING_EXPANSION` | +24.0% | 80.0% | 2.28 | 5 | [37.6%, 96.4%] |
| `0__2__1` | `EXTREME_FEAR` | `STABLE_CONTINUATION_3D` | `VOL_MODERATE_COMPRESSION` | +19.0% | 75.0% | 1.35 | 4 | [30.1%, 95.4%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `3__0__4` | `NEUTRAL_GREED` | `FAST_CRUSH_3D` | `VOL_PEAK_DECELERATION` | -56.0% | 0.0% | 0.18 | 2 | [0.0%, 65.8%] |
| `4__1__1` | `GREED` | `DECELERATING_DOWN_3D` | `VOL_MODERATE_COMPRESSION` | -56.0% | 0.0% | 0.62 | 3 | [0.0%, 56.1%] |
| `3__3__4` | `NEUTRAL_GREED` | `ACCELERATING_UP_3D` | `VOL_PEAK_DECELERATION` | -31.0% | 25.0% | 0.96 | 4 | [4.6%, 69.9%] |
| `4__3__4` | `GREED` | `ACCELERATING_UP_3D` | `VOL_PEAK_DECELERATION` | -31.0% | 25.0% | 0.13 | 4 | [4.6%, 69.9%] |
| `1__3__1` | `FEAR` | `ACCELERATING_UP_3D` | `VOL_MODERATE_COMPRESSION` | -22.7% | 33.3% | 0.84 | 3 | [6.1%, 79.2%] |
