# Dossier de Personalidad V3 — PCR

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes · **Versión:** V3 (2026-09-16)

> **Estación:** `pcr` · **Polaridad Canónica:** `NORMAL` · **Rol:** `Detector Dual de Suelo (Put Panic = PISO) y Techo (Call Euphoria = TECHO).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `PCR` (CBOE Equity Put/Call Ratio (PCR))
- **Física:** Posicionamiento institucional y retail en opciones: volumen relativo de puts versus calls.
- **Incepción Oficial:** `2006-11-01` | **Cobertura:** `2006-11-01 a 2026-09-03`
- **Muestra Total:** `4,990` barras diarias continuas | **Total Episodios:** `3,974`
- **Espacio de Estados:** `96` registrados | `96` poblados empíricamente
- **Distribución de Rareza:** `50` estados con $N < 10$ (52.1% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_CALL_EUPHORIA` | 107 | 54.2% | -1.2% | +0.26% | **Euforia en Calls / Complacencia** | `Complacencia de Opciones` |
| 1 | `CALL_EUPHORIA` | 589 | 53.5% | -1.9% | +0.36% | **Sesgo Alcista Ordinario** | `Apetito Especulativo` |
| 2 | `NEUTRAL_CALL_BIAS` | 1381 | 54.2% | -1.2% | +0.42% | **Neutral Incondicional** | `Equilibrio de Cobertura` |
| 3 | `NEUTRAL_PUT_BIAS` | 1374 | 52.5% | -2.9% | +0.27% | **Leve Sesgo Defensivo** | `Cobertura Preventiva` |
| 4 | `PUT_PANIC` | 470 | 55.1% | -0.3% | +0.34% | **Pánico Creciente en Opciones** | `Fase Avanzada de Corrección` |
| 5 | `EXTREME_PUT_PANIC` | 53 | 54.7% | -0.7% | +0.41% | **Pánico Masivo en Puts / Capitulación** | `Piso de Opciones` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `NORMAL`
  * *Regla:* Bin 0 = Complacencia / Valor bajo; Bin 5 = Pánico / Valor alto (Suelo de capitulación).
- **Profesión de la Estación:** `Detector Dual de Suelo (Put Panic = PISO) y Techo (Call Euphoria = TECHO).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_CALL_EUPHORIA`) | 2.8% | 1.9% | 3.7% | 9.3% | 1.9% | 80.4% | `ENTRE` (80.4%) | 55.8% | **0.449** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`CALL_EUPHORIA`) | 3.7% | 3.9% | 3.1% | 4.8% | 4.1% | 80.5% | `ENTRE` (80.5%) | 53.0% | **0.426** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_CALL_BIAS`) | 4.6% | 4.9% | 5.4% | 7.2% | 5.4% | 72.5% | `ENTRE` (72.5%) | 53.9% | **0.391** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_PUT_BIAS`) | 6.3% | 10.1% | 11.6% | 6.5% | 5.0% | 60.5% | `ENTRE` (60.5%) | 48.0% | **0.29** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`PUT_PANIC`) | 9.6% | 20.4% | 22.6% | 6.6% | 2.3% | 38.5% | `ENTRE` (38.5%) | 44.2% | **0.17** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_PUT_PANIC`) | 9.4% | 28.3% | 32.1% | 7.5% | 5.7% | 17.0% | `t=0` (32.1%) | 58.8% | **0.189** | **Gatillo Síncrono** (día del pivote) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **65.0% de su masa en ENTRE**. Esto confirma que `PCR` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT2` | **Lead-Time:** Medio (el pánico en puts o la euforia en calls precede el agotamiento del movimiento).
- **Precursores Causalmente Previos:** Flujo de dinero y sentimiento minorista.
- **Confirmadores Posteriores:** BSI y VIX.

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.

---

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)

El acoplamiento entre escalas distingue el ruido táctico del régimen duradero:

| Escala | Time-Stop Vertical | Baseline Hit Rate (MIN) | Baseline EV (MIN) | Significado Operativo |
|:---:|:---:|:---:|:---:|:---|
| **zz25 (2.5%)** | 35 barras (P95) | 55.4% | 0.44% | Horizonte Táctico / Swing Corto (Scalp & Rebound) |
| **zz50 (5.0%)** | 110 barras (P95) | 59.2% | 1.17% | Horizonte Intermedio / Swing Estructural |
| **zz75 (7.5%)** | 190 barras (P95) | 64.0% | 2.37% | Régimen Primario de Mercado / Posicionamiento Core |

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
| 0 | `EXTREME_CALL_EUPHORIA` | **Trampa Narrativa** | Mucha compra de calls garantiza que el mercado seguirá subiendo con fuerza. | PCR < 0.69 (Call Euphoria) marca techos de complacencia donde los creadores de mercado están short gamma y vulnerables a caídas. | **Cosechar beneficios parciales; prohibido comprar en euforia extrema.** |
| 1 | `CALL_EUPHORIA` | **Trampa Narrativa** | Euforia de calls = sobrecompra; el mercado va a caer. | HR=55.3% a zz25, HR=56.9% a zz75. Edge neutral. La euforia de calls NO predice corrección inmediata. | **Mantener; la euforia de calls es ruido sin edge direccional (`MKT_HOLD_STABLE`).** |
| 4 | `PUT_PANIC` | **Contrarian (acumulación)** | Put panic = hay que comprar puts y protegerse; vender equities. | HR=52.9% a zz25, HR=59.1% a zz75. A mayor escala, edge MEJORA. El pánico de puts es el mercado comprando seguro. | **Evaluar para acumulación en zz75; no vender por pánico de opciones (`MKT_BUY_DIP_TACTICAL`).** |
| 5 | `EXTREME_PUT_PANIC` | **Contrarian** | Mucha compra de puts significa que las instituciones saben que el mercado se va a cero. | PCR > 1.31 es cobertura tardía/pánico minorista que marca suelos de corto plazo con altísimo Hit Rate de rebote. | **Activar gatillo de compra contra el consenso compra táctica en corrección.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Noviembre 2008 (PCR 1.45), Diciembre 2018 (PCR 1.82), Diciembre 2022 (PCR 2.45 - récord histórico de puts).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `31` episodios (0.78% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 4`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** PCR > 1.08 (sesgo defensivo elevado).
- **Alerta Roja (CRITICAL / EMERGENCY):** PCR > 1.31 (+2σ / Put Panic / Tier >= 1). Blowoff > 2.63.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica en corrección.
- **Criterio de Desactivación:** PCR normalizado por debajo de 0.95.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__0__1` | `CALL_EUPHORIA` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | +44.6% | 100.0% | 2.4 | 2 | [34.2%, 100.0%] |
| `4__1__1` | `PUT_PANIC` | `DECELERATING_DOWN_3D` | `VOL_MODERATE_COMPRESSION` | +44.6% | 100.0% | 8.18 | 2 | [34.2%, 100.0%] |
| `4__2__0` | `PUT_PANIC` | `STABLE_CONTINUATION_3D` | `VOL_EXTREME_SQUEEZE` | +44.6% | 100.0% | 7.07 | 4 | [51.0%, 100.0%] |
| `0__2__4` | `EXTREME_CALL_EUPHORIA` | `STABLE_CONTINUATION_3D` | `VOL_PEAK_DECELERATION` | +27.9% | 83.3% | 2.86 | 6 | [43.6%, 97.0%] |
| `2__0__3` | `NEUTRAL_CALL_BIAS` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | +24.6% | 80.0% | 1.74 | 5 | [37.6%, 96.4%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__3__2` | `CALL_EUPHORIA` | `ACCELERATING_UP_3D` | `VOL_NEUTRAL_BASELINE` | -55.4% | 0.0% | 0.38 | 3 | [0.0%, 56.1%] |
| `2__3__1` | `NEUTRAL_CALL_BIAS` | `ACCELERATING_UP_3D` | `VOL_MODERATE_COMPRESSION` | -38.7% | 16.7% | 0.31 | 12 | [4.7%, 44.8%] |
| `3__2__0` | `NEUTRAL_PUT_BIAS` | `STABLE_CONTINUATION_3D` | `VOL_EXTREME_SQUEEZE` | -36.6% | 18.8% | 0.39 | 16 | [6.6%, 43.0%] |
| `2__1__0` | `NEUTRAL_CALL_BIAS` | `DECELERATING_DOWN_3D` | `VOL_EXTREME_SQUEEZE` | -30.4% | 25.0% | 0.57 | 4 | [4.6%, 69.9%] |
| `3__1__0` | `NEUTRAL_PUT_BIAS` | `DECELERATING_DOWN_3D` | `VOL_EXTREME_SQUEEZE` | -30.4% | 25.0% | 0.53 | 4 | [4.6%, 69.9%] |
