# Referencia de Estación — CREDIT

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes

> **Estación:** `credit` · **Polaridad Canónica:** `INVERTED` · **Rol:** `Canario de Salud Económica y Gatillo de Suelo de Máxima Asimetría en D2=0.`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `CREDIT` (Credit Spread Stress Ratio (HYG / LQD))
- **Física:** Salud del crédito corporativo; ratio entre bonos de alto rendimiento (junk) y bonos corporativos de grado de inversión.
- **Incepción Oficial:** `2007-04-11` | **Cobertura:** `2007-04-11 a 2026-09-03`
- **Muestra Total:** `4,882` barras diarias continuas | **Total Episodios:** `2,937`
- **Espacio de Estados:** `104` registrados | `104` poblados empíricamente
- **Distribución de Rareza:** `59` estados con $N < 10$ (56.7% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_STRESS` | 39 | 48.7% | -6.6% | +0.26% | **Congelamiento de Liquidez / Clímax de Estrés** | `Piso / Capitulación de Crédito` |
| 1 | `STRESS` | 202 | 61.4% | +6.1% | +0.58% | **Absorción de Estrés / Rebote Fuerte (+6.1% Edge)** | `Recuperación Post-Crisis` |
| 2 | `NEUTRAL_TIGHT` | 849 | 51.8% | -3.5% | +0.10% | **Neutral / Spreads Moderados** | `Régimen Ordinario de Crédito` |
| 3 | `NEUTRAL_LOOSE` | 757 | 51.9% | -3.4% | +0.38% | **Neutral Laxo** | `Expansión Ordinaria` |
| 4 | `EASE` | 507 | 58.8% | +3.5% | +0.59% | **Facilidad Crediticia Dinámica (+3.5% Edge)** | `Expansión de Balance Sostenida` |
| 5 | `EXTREME_EASE` | 583 | 51.1% | -4.2% | +0.17% | **Crédito Ultra Relajado / Madurez** | `Madurez del Ciclo de Crédito` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `INVERTED`
  * *Regla:* Bin 0 = Estrés / Miedo / Descalabro (Suelo / Oportunidad); Bin 5 = Expansión / Facilidad.
- **Profesión de la Estación:** `Canario de Salud Económica y Gatillo de Suelo de Máxima Asimetría en D2=0.`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_STRESS`) | 0.0% | 33.3% | 51.3% | 15.4% | 0.0% | 0.0% | `t=0` (51.3%) | 60.0% | **0.308** | **Gatillo Síncrono** (día del pivote) |
| 1 (`STRESS`) | 5.9% | 18.8% | 25.7% | 12.4% | 3.5% | 33.7% | `ENTRE` (33.7%) | 72.1% | **0.243** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_TIGHT`) | 7.3% | 11.7% | 11.9% | 9.7% | 6.2% | 53.2% | `ENTRE` (53.2%) | 47.6% | **0.253** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_LOOSE`) | 4.5% | 4.9% | 6.5% | 4.2% | 3.8% | 76.1% | `ENTRE` (76.1%) | 51.4% | **0.391** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`EASE`) | 4.7% | 7.3% | 8.5% | 5.9% | 2.6% | 71.0% | `ENTRE` (71.0%) | 55.3% | **0.392** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_EASE`) | 4.6% | 5.5% | 6.9% | 6.7% | 5.3% | 71.0% | `ENTRE` (71.0%) | 47.8% | **0.34** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **63.7% de su masa en ENTRE**. Esto confirma que `CREDIT` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT1` | **Lead-Time:** Largo (la economía y el crédito corporativo se deterioran ANTES de que la renta variable lo descuente).
- **Precursores Causalmente Previos:** Tasas de interés y spreads interbancarios.
- **Confirmadores Posteriores:** CAT2 (VIX/PCR) y CAT3 (BSI).

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.

---

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)

El acoplamiento entre escalas distingue el ruido táctico del régimen duradero:

| Escala | Time-Stop Vertical | Baseline Hit Rate (MIN) | Baseline EV (MIN) | Significado Operativo |
|:---:|:---:|:---:|:---:|:---|
| **zz25 (2.5%)** | 35 barras (P95) | 55.3% | 0.42% | Horizonte Táctico / Swing Corto (Scalp & Rebound) |
| **zz50 (5.0%)** | 110 barras (P95) | 58.5% | 1.11% | Horizonte Intermedio / Swing Estructural |
| **zz75 (7.5%)** | 190 barras (P95) | 63.2% | 2.26% | Régimen Primario de Mercado / Posicionamiento Core |

- **Convergencia Estructural (zz25 + zz50 + zz75 alineados con EV creciente):** Señal mayor de fondo. Habilita acumulación a largo plazo (acumulación estructural).
- **Divergencia Táctica (zz25 desacoplado de zz75):** Rebote contratendencial o corrección técnica. Prohibido posicionar a largo plazo; operar exclusivamente rebotes tácticos ceñidos (compra táctica en corrección).
- **Filtro de Operabilidad:** Razón Riesgo/Beneficio $RR = MFE / |MAE| \ge 1.0$. Si $RR < 1.0$, la combinación se considera matemáticamente no operable.

---

## 6. PERFIL DIMENSIONAL INTEGRADO (D1 Magnitud × D2 Velocidad Cinemática × D3 Volatilidad Interna)

- **Papel de D1 (Magnitud Estática):** Determina la ubicación de la estación dentro de la población gaussiana histórica de 33 años.
- **Papel de D2 (Velocidad Cinemática 72h, $\Delta 3d$):** Modula la inercia inmediata. Destacan las siguientes singularidades:
  * `D2=0 (FAST_CRUSH_3D)`: $HR = 80.0\%$, $Edge = +22.5\%$, $PF = 51.33$, $RR = 2.40$. **El gatillo de suelo más potente del sistema METAR**.
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
| 0 | `EXTREME_STRESS` | **Contrarian Supremo** | Cuando el crédito se congela, las acciones caerán indefinidamente; no tocar nada. | CREDIT D1=0 concentra 51.3% de masa en t=0. Cuando se combina con D2=0 (FAST_CRUSH_3D), alcanza HR=80.0%, Edge=+22.5%, EV=+2.18% y Profit Factor de 51.33. Es el mejor suelo del sistema. | **Comprar agresivamente el suelo de crédito.** |
| 5 | `EXTREME_EASE` | **Trampa Narrativa** | Crédito ultra relajado es garantía eterna de mercado alcista sin fin. | El crédito ultra laxo suele preceder el inicio de ciclos de subida de tasas y ajuste de liquidez. | **Mantener posiciones pero auditar solvencia fundamental.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Octubre 2008 (Lehman Credit Freeze), Agosto 2011 (Crisis deuda soberana), Marzo 2020 (Covid Credit Crunch, intervención Fed).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `165` episodios (5.62% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 1`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** Credit Ratio < 0.5799 (-1σ).
- **Alerta Roja (CRITICAL / EMERGENCY):** Credit Ratio < 0.5256 (-2σ / Tier >= 1 Stress). Blowoff < 0.4639.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica en corrección.
- **Criterio de Desactivación:** Credit Ratio recuperando > 0.60 de forma sostenida.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__0__1` | `EXTREME_STRESS` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | +44.7% | 100.0% | 1.43 | 2 | [34.2%, 100.0%] |
| `0__4__2` | `EXTREME_STRESS` | `FAST_SPIKE_3D` | `VOL_NEUTRAL_BASELINE` | +44.7% | 100.0% | 1.42 | 3 | [43.9%, 100.0%] |
| `1__0__3` | `STRESS` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | +44.7% | 100.0% | 12.31 | 3 | [43.9%, 100.0%] |
| `1__1__3` | `STRESS` | `DECELERATING_DOWN_3D` | `VOL_ACCELERATING_EXPANSION` | +44.7% | 100.0% | 4.68 | 11 | [74.1%, 100.0%] |
| `1__3__1` | `STRESS` | `ACCELERATING_UP_3D` | `VOL_MODERATE_COMPRESSION` | +44.7% | 100.0% | 23.86 | 3 | [43.9%, 100.0%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__3__2` | `EXTREME_STRESS` | `ACCELERATING_UP_3D` | `VOL_NEUTRAL_BASELINE` | -55.3% | 0.0% | 0.13 | 2 | [0.0%, 65.8%] |
| `2__3__4` | `NEUTRAL_TIGHT` | `ACCELERATING_UP_3D` | `VOL_PEAK_DECELERATION` | -55.3% | 0.0% | 0.26 | 4 | [0.0%, 49.0%] |
| `3__4__2` | `NEUTRAL_LOOSE` | `FAST_SPIKE_3D` | `VOL_NEUTRAL_BASELINE` | -55.3% | 0.0% | 0.31 | 2 | [0.0%, 65.8%] |
| `3__1__4` | `NEUTRAL_LOOSE` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | -35.3% | 20.0% | 0.45 | 5 | [3.6%, 62.4%] |
| `2__4__2` | `NEUTRAL_TIGHT` | `FAST_SPIKE_3D` | `VOL_NEUTRAL_BASELINE` | -30.3% | 25.0% | 0.11 | 8 | [7.1%, 59.1%] |
