# Dossier de Personalidad V3 — VVIX

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes · **Versión:** V3 (2026-09-16)

> **Estación:** `vvix` · **Polaridad Canónica:** `NORMAL` · **Rol:** `Detector de Transición de Régimen y Estabilidad del Miedo.`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `VVIX` (CBOE VIX of VIX (VVIX))
- **Física:** Volatilidad de la volatilidad; mide la estabilidad y convicción de la demanda de opciones sobre VIX.
- **Incepción Oficial:** `2006-03-06` | **Cobertura:** `2006-03-06 a 2026-09-03`
- **Muestra Total:** `5,158` barras diarias continuas | **Total Episodios:** `3,463`
- **Espacio de Estados:** `99` registrados | `99` poblados empíricamente
- **Distribución de Rareza:** `51` estados con $N < 10$ (51.5% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_STABILITY` | 6 | 33.3% | -22.3% | -0.12% | **Compresión Anómala de Vol-de-Vol (N=6)** | `Calma Pre-Shock` |
| 1 | `STABILITY` | 159 | 52.8% | -2.8% | +0.24% | **Baja Volatilidad de Opciones** | `Régimen Benigno` |
| 2 | `NEUTRAL_STABLE` | 892 | 48.8% | -6.9% | +0.19% | **Neutral Incondicional** | `Régimen Ordinario` |
| 3 | `NEUTRAL_UNSTABLE` | 1392 | 54.0% | -1.6% | +0.42% | **Inestabilidad Incipiente** | `Transición de Volatilidad` |
| 4 | `INSTABILITY` | 848 | 54.0% | -1.6% | +0.19% | **Inestabilidad Marcada** | `Re-Hedging Activo de Opciones` |
| 5 | `EXTREME_INSTABILITY` | 166 | 63.3% | +7.6% | +0.78% | **Clímax de Inestabilidad (+7.6% Edge)** | `Capitulación de Vol-de-Vol` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `NORMAL`
  * *Regla:* Bin 0 = Complacencia / Valor bajo; Bin 5 = Pánico / Valor alto (Suelo de capitulación).
- **Profesión de la Estación:** `Detector de Transición de Régimen y Estabilidad del Miedo.`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_STABILITY`) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | `ENTRE` (100.0%) | 33.3% | **0.333** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`STABILITY`) | 1.9% | 3.8% | 4.4% | 5.7% | 6.3% | 78.0% | `ENTRE` (78.0%) | 52.4% | **0.409** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_STABLE`) | 4.4% | 5.3% | 4.8% | 5.9% | 4.5% | 75.1% | `ENTRE` (75.1%) | 45.8% | **0.344** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_UNSTABLE`) | 5.0% | 7.0% | 7.8% | 7.0% | 4.6% | 68.5% | `ENTRE` (68.5%) | 52.4% | **0.359** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`INSTABILITY`) | 9.9% | 12.7% | 14.6% | 9.6% | 5.4% | 47.8% | `ENTRE` (47.8%) | 53.8% | **0.257** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_INSTABILITY`) | 5.4% | 26.5% | 44.6% | 12.7% | 1.2% | 9.6% | `t=0` (44.6%) | 75.7% | **0.338** | **Gatillo Síncrono** (día del pivote) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **62.8% de su masa en ENTRE**. Esto confirma que `VVIX` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT2` | **Lead-Time:** Medio (precursor directo de shocks de volatilidad; se mueve antes de que el VIX termine de dispararse).
- **Precursores Causalmente Previos:** VIX D2 (aceleración cinemática) y SKEW.
- **Confirmadores Posteriores:** VIX rompiendo bandas y PCR disparándose a pánico.

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.

---

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)

El acoplamiento entre escalas distingue el ruido táctico del régimen duradero:

| Escala | Time-Stop Vertical | Baseline Hit Rate (MIN) | Baseline EV (MIN) | Significado Operativo |
|:---:|:---:|:---:|:---:|:---|
| **zz25 (2.5%)** | 35 barras (P95) | 55.6% | 0.45% | Horizonte Táctico / Swing Corto (Scalp & Rebound) |
| **zz50 (5.0%)** | 110 barras (P95) | 59.5% | 1.22% | Horizonte Intermedio / Swing Estructural |
| **zz75 (7.5%)** | 190 barras (P95) | 65.1% | 2.53% | Régimen Primario de Mercado / Posicionamiento Core |

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
| 0 | `EXTREME_STABILITY` | **Trampa Narrativa** | VVIX extremadamente bajo significa mercado aburrido sin volatilidad. | Extrema estabilidad (VVIX < 67.4) ocurre solo en 0.2% de las barras; es una compresión severa que precede a una expansión. | **Alerta de expansión inminente; no apalancar posiciones.** |
| 1 | `STABILITY` | **Coherente (neutral)** | VVIX bajo = volatilidad estable; mercado previsible. | HR=53.5% a zz25, HR=55.6% a zz75. Edge neutral. Estabilidad de vol no genera señal operativa. | **Mantener; régimen estable sin catalizador (`MKT_HOLD_STABLE`).** |
| 4 | `INSTABILITY` | **Trampa Narrativa** | VVIX alto = vol-de-vol = pánico de segundo orden; peligro extremo. | HR=54.2% a zz25, HR=56.9% a zz75. Edge neutral. La inestabilidad de vol NO predice dirección; solo indica transición de régimen. | **Mantener; evaluar contexto de VIX para discriminar. VVIX solo no es accionable (`MKT_HOLD_STABLE`).** |
| 5 | `EXTREME_INSTABILITY` | **Coherente** | VVIX > 131 indica que el mercado de opciones está roto y no se puede operar. | Indica clímax de re-hedging de los creadores de mercado. Suele coincidir con capitulación rápida de 2 a 3 días. | **Preparar compras tácticas escalonadas ante el agotamiento de la inestabilidad.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Agosto 2015 (Flash Crash VVIX 212), Febrero 2018 (Volmageddon VVIX 202), Marzo 2020 (Covid VVIX 207).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `63` episodios (1.82% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** VVIX > 108.99 (+1σ).
- **Alerta Roja (CRITICAL / EMERGENCY):** VVIX > 131.50 (+2σ / Tier >= 1 Overflow). Blowoff > 173.69.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica en corrección.
- **Criterio de Desactivación:** VVIX estabilizado < 95.0 durante 3 días hábiles.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__0__2` | `STABILITY` | `FAST_CRUSH_3D` | `VOL_NEUTRAL_BASELINE` | +44.4% | 100.0% | 4.41 | 2 | [34.2%, 100.0%] |
| `2__3__0` | `NEUTRAL_STABLE` | `ACCELERATING_UP_3D` | `VOL_EXTREME_SQUEEZE` | +44.4% | 100.0% | 2.1 | 2 | [34.2%, 100.0%] |
| `5__4__4` | `EXTREME_INSTABILITY` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | +44.4% | 100.0% | 2.27 | 5 | [56.6%, 100.0%] |
| `4__4__4` | `INSTABILITY` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | +22.2% | 77.8% | 2.59 | 9 | [45.3%, 93.7%] |
| `5__3__2` | `EXTREME_INSTABILITY` | `ACCELERATING_UP_3D` | `VOL_NEUTRAL_BASELINE` | +21.8% | 77.4% | 2.04 | 31 | [60.2%, 88.6%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `4__0__1` | `INSTABILITY` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | -55.6% | 0.0% | 0.13 | 4 | [0.0%, 49.0%] |
| `4__3__0` | `INSTABILITY` | `ACCELERATING_UP_3D` | `VOL_EXTREME_SQUEEZE` | -55.6% | 0.0% | 0.57 | 2 | [0.0%, 65.8%] |
| `4__4__1` | `INSTABILITY` | `FAST_SPIKE_3D` | `VOL_MODERATE_COMPRESSION` | -55.6% | 0.0% | 0.02 | 4 | [0.0%, 49.0%] |
| `5__2__3` | `EXTREME_INSTABILITY` | `STABLE_CONTINUATION_3D` | `VOL_ACCELERATING_EXPANSION` | -55.6% | 0.0% | 0.3 | 2 | [0.0%, 65.8%] |
| `5__4__1` | `EXTREME_INSTABILITY` | `FAST_SPIKE_3D` | `VOL_MODERATE_COMPRESSION` | -55.6% | 0.0% | 0.28 | 3 | [0.0%, 56.1%] |
