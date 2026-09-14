# Referencia de Estación — DXY

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes

> **Estación:** `dxy` · **Polaridad Canónica:** `NORMAL` · **Rol:** `Barómetro de Drenaje de Liquidez (D1=5 Fortaleza Extrema = Venta/Crash; D1=0 Debilidad = Expansión).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `DXY` (US Dollar Index (DXY))
- **Física:** Fortaleza del dólar estadounidense frente a una canasta de divisas; barómetro de liquidez global y flujos de refugio.
- **Incepción Oficial:** `1993-01-29` | **Cobertura:** `1993-01-29 a 2026-09-03`
- **Muestra Total:** `8,457` barras diarias continuas | **Total Episodios:** `5,810`
- **Espacio de Estados:** `112` registrados | `112` poblados empíricamente
- **Distribución de Rareza:** `46` estados con $N < 10$ (41.1% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_WEAKNESS` | 295 | 50.5% | -3.4% | -0.02% | **Dólar Deprimido / Expansión de Liquidez** | `Estímulo de Liquidez Global` |
| 1 | `WEAKNESS` | 1041 | 57.9% | +4.0% | +0.47% | **Sesgo Alcista Neto (+4.0% Edge)** | `Régimen Expansivo de Divisas` |
| 2 | `NEUTRAL_WEAK` | 1214 | 52.6% | -1.4% | +0.33% | **Neutral Incondicional** | `Equilibrio Cambiario` |
| 3 | `NEUTRAL_STRONG` | 1817 | 52.0% | -2.0% | +0.34% | **Neutral Débil** | `Fortaleza Cambiaria Ordinaria` |
| 4 | `STRENGTH` | 1044 | 52.1% | -1.8% | +0.17% | **Presión Moderada de Liquidez** | `Apretamiento Financiero` |
| 5 | `EXTREME_STRENGTH` | 399 | 42.4% | -11.6% | -0.35% | **Fuerte Sesgo Bajista (-11.6% Edge, Drenaje)** | `Drenaje de Liquidez / Vuelo a Refugio` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `NORMAL`
  * *Regla:* Bin 0 = Complacencia / Valor bajo; Bin 5 = Pánico / Valor alto (Suelo de capitulación).
- **Profesión de la Estación:** `Barómetro de Drenaje de Liquidez (D1=5 Fortaleza Extrema = Venta/Crash; D1=0 Debilidad = Expansión).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_WEAKNESS`) | 7.1% | 11.9% | 11.5% | 9.2% | 4.1% | 56.3% | `ENTRE` (56.3%) | 50.0% | **0.281** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`WEAKNESS`) | 4.7% | 6.5% | 8.7% | 6.6% | 4.6% | 68.8% | `ENTRE` (68.8%) | 57.4% | **0.395** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_WEAK`) | 4.7% | 6.8% | 7.2% | 5.4% | 4.4% | 71.5% | `ENTRE` (71.5%) | 48.3% | **0.345** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_STRONG`) | 4.9% | 8.5% | 10.3% | 7.2% | 5.3% | 63.7% | `ENTRE` (63.7%) | 50.0% | **0.319** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`STRENGTH`) | 7.1% | 11.1% | 12.2% | 9.5% | 6.7% | 53.4% | `ENTRE` (53.4%) | 45.7% | **0.244** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_STRENGTH`) | 9.5% | 14.3% | 14.8% | 10.8% | 7.8% | 42.9% | `ENTRE` (42.9%) | 36.3% | **0.156** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **62.6% de su masa en ENTRE**. Esto confirma que `DXY` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT1` | **Lead-Time:** Largo a Medio (afecta directamente la liquidez internacional y las ganancias corporativas multinacionales).
- **Precursores Causalmente Previos:** Tasas relativas Fed vs BCE/BoJ y balanza comercial.
- **Confirmadores Posteriores:** Commodities y mercados emergentes.

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
| 5 | `EXTREME_STRENGTH` | **Trampa Narrativa Clásica** | Un dólar fuerte es señal de economía estadounidense todopoderosa y por tanto las acciones deben subir. | DXY D1=5 (> 116.07) tiene un edge negativo masivo de -15.8% para la renta variable. Un dólar disparado drena liquidez global, aprieta las condiciones financieras y comprime beneficios de empresas multinacionales. | **Modo defensivo riguroso; prohibido acumular activos de riesgo con DXY en blowoff alcista.** |
| 0 | `EXTREME_WEAKNESS` | **Contrarian** | Un dólar colapsando destruye el poder adquisitivo y hundirá a Wall Street. | DXY débil expande la liquidez global, impulsa los commodities y estimula las valoraciones bursátiles. | **Entorno favorable para activos de riesgo.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Octubre 2008 (Flight to dollar), Marzo 2020 (Dólar squeeze global), Septiembre 2022 (DXY 114.78 - pico de drenaje de liquidez y suelo de bolsas).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `1781` episodios (30.65% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** DXY > 102.82 (+1σ) con D2 acelerando.
- **Alerta Roja (CRITICAL / EMERGENCY):** DXY > 116.07 (+2σ / Tier >= 1 Liquidity Squeeze). Blowoff > 119.50.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → acumulación estructural.
- **Criterio de Desactivación:** DXY descendiendo por debajo de 100.0.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__0__1` | `EXTREME_WEAKNESS` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | +46.1% | 100.0% | 3.44 | 2 | [34.2%, 100.0%] |
| `0__0__3` | `EXTREME_WEAKNESS` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 5.18 | 3 | [43.9%, 100.0%] |
| `1__1__4` | `WEAKNESS` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 2.36 | 4 | [51.0%, 100.0%] |
| `2__0__3` | `NEUTRAL_WEAK` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 2.44 | 3 | [43.9%, 100.0%] |
| `5__4__3` | `EXTREME_STRENGTH` | `FAST_SPIKE_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 3.08 | 3 | [43.9%, 100.0%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__0__3` | `WEAKNESS` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | -53.9% | 0.0% | 0.22 | 3 | [0.0%, 56.1%] |
| `2__4__4` | `NEUTRAL_WEAK` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.14 | 2 | [0.0%, 65.8%] |
| `3__4__4` | `NEUTRAL_STRONG` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.18 | 4 | [0.0%, 49.0%] |
| `4__4__1` | `STRENGTH` | `FAST_SPIKE_3D` | `VOL_MODERATE_COMPRESSION` | -53.9% | 0.0% | 0.31 | 4 | [0.0%, 49.0%] |
| `4__4__4` | `STRENGTH` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.01 | 2 | [0.0%, 65.8%] |
