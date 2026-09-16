# Dossier de Personalidad V3 — ROTATION

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes · **Versión:** V3 (2026-09-16)

> **Estación:** `rotation` · **Polaridad Canónica:** `INVERTED` · **Rol:** `Canario de Rotación de Riesgo (D1=0 Defensivo = PISO; D2=4 Aceleración Ofensiva = CONTINUACIÓN).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `ROTATION` (Sector Rotation Ratio: Cyclical vs Defensive)
- **Física:** Rotación de sectores en el S&P 500: z(XLY/XLP) + z(XLK/XLU); liderazgo de consumo discrecional y tecnología vs consumo básico y utilities.
- **Incepción Oficial:** `1999-01-04` | **Cobertura:** `1999-01-04 a 2026-09-03`
- **Muestra Total:** `6,960` barras diarias continuas | **Total Episodios:** `4,577`
- **Espacio de Estados:** `124` registrados | `124` poblados empíricamente
- **Distribución de Rareza:** `63` estados con $N < 10$ (50.8% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_DEFENSIVE` | 142 | 55.6% | +2.2% | +0.39% | **Agotamiento de Vuelo a Refugio (Rng% 72%)** | `Piso de Rotación / Suelo Cíclico` |
| 1 | `DEFENSIVE` | 701 | 53.5% | +0.1% | +0.18% | **Sesgo Defensivo Moderado** | `Corrección de Sectores Cíclicos` |
| 2 | `NEUTRAL_DEFENSIVE` | 1315 | 50.6% | -2.7% | +0.21% | **Neutral Incondicional** | `Equilibrio Sectorial` |
| 3 | `NEUTRAL_OFFENSIVE` | 1530 | 53.9% | +0.5% | +0.38% | **Incipiente Apetito Cíclico** | `Rotación Constructiva` |
| 4 | `OFFENSIVE` | 778 | 52.6% | -0.8% | +0.36% | **Liderazgo Cíclico Marcado** | `Expansión de Beta` |
| 5 | `EXTREME_OFFENSIVE` | 111 | 55.9% | +2.5% | +0.40% | **Euforia Cíclica / Momentum Fuerte** | `Clímax de Liderazgo Tecnológico` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `INVERTED`
  * *Regla:* Bin 0 = Estrés / Miedo / Descalabro (Suelo / Oportunidad); Bin 5 = Expansión / Facilidad.
- **Profesión de la Estación:** `Canario de Rotación de Riesgo (D1=0 Defensivo = PISO; D2=4 Aceleración Ofensiva = CONTINUACIÓN).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_DEFENSIVE`) | 7.7% | 21.8% | 27.5% | 10.6% | 4.2% | 28.2% | `ENTRE` (28.2%) | 62.5% | **0.176** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`DEFENSIVE`) | 8.4% | 15.8% | 18.1% | 10.8% | 6.3% | 40.5% | `ENTRE` (40.5%) | 48.6% | **0.197** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_DEFENSIVE`) | 6.1% | 10.6% | 11.3% | 7.6% | 4.9% | 59.5% | `ENTRE` (59.5%) | 48.8% | **0.29** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_OFFENSIVE`) | 4.6% | 6.4% | 7.8% | 5.9% | 4.4% | 70.8% | `ENTRE` (70.8%) | 49.1% | **0.348** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`OFFENSIVE`) | 5.7% | 5.9% | 4.9% | 6.3% | 4.0% | 73.3% | `ENTRE` (73.3%) | 50.9% | **0.373** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_OFFENSIVE`) | 1.8% | 4.5% | 4.5% | 3.6% | 2.7% | 82.9% | `ENTRE` (82.9%) | 57.6% | **0.478** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **62.3% de su masa en ENTRE**. Esto confirma que `ROTATION` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `DUAL: CAT1 (Salida A Macro) y CAT3 (Salida B Acción Sectorial)` | **Lead-Time:** Dual: Largo en asignación de riesgo macro; Corto en momentum sectorial.
- **Precursores Causalmente Previos:** Curva de tipos y DXY.
- **Confirmadores Posteriores:** BSI sectorial.

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.
3. **Dualidad Funcional PLA:** `ROTATION` alimenta simultáneamente la Salida A (Macro/Liquidez global) y la Salida B (Liderazgo sectorial cíclico vs defensivo). No confundir con volumen agregado.

---

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)

El acoplamiento entre escalas distingue el ruido táctico del régimen duradero:

| Escala | Time-Stop Vertical | Baseline Hit Rate (MIN) | Baseline EV (MIN) | Significado Operativo |
|:---:|:---:|:---:|:---:|:---|
| **zz25 (2.5%)** | 35 barras (P95) | 53.4% | 0.31% | Horizonte Táctico / Swing Corto (Scalp & Rebound) |
| **zz50 (5.0%)** | 110 barras (P95) | 56.1% | 0.97% | Horizonte Intermedio / Swing Estructural |
| **zz75 (7.5%)** | 190 barras (P95) | 60.5% | 2.13% | Régimen Primario de Mercado / Posicionamiento Core |

- **Convergencia Estructural (zz25 + zz50 + zz75 alineados con EV creciente):** Señal mayor de fondo. Habilita acumulación a largo plazo (acumulación estructural).
- **Divergencia Táctica (zz25 desacoplado de zz75):** Rebote contratendencial o corrección técnica. Prohibido posicionar a largo plazo; operar exclusivamente rebotes tácticos ceñidos (compra táctica en corrección).
- **Filtro de Operabilidad:** Razón Riesgo/Beneficio $RR = MFE / |MAE| \ge 1.0$. Si $RR < 1.0$, la combinación se considera matemáticamente no operable.

---

## 6. PERFIL DIMENSIONAL INTEGRADO (D1 Magnitud × D2 Velocidad Cinemática × D3 Volatilidad Interna)

- **Papel de D1 (Magnitud Estática):** Determina la ubicación de la estación dentro de la población gaussiana histórica de 33 años.
- **Papel de D2 (Velocidad Cinemática 72h, $\Delta 3d$):** Modula la inercia inmediata. Destacan las siguientes singularidades:
  * `D2=4 (FAST_SPIKE_3D)`: $HR = 66.9\%$, $Edge = +13.5\%$, $PF = 1.56$. Rotación ofensiva explosiva que confirma continuidad alcista institucional.
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
| 0 | `EXTREME_DEFENSIVE` | **Contrarian** | Cuando el dinero corre a Utilities y Staples, el mercado está herido de muerte. | ROTATION D1=0 tiene 72% de coincidencia con suelos de mercado (Rng% 72%). Marca la fase final de pánico donde todo lo cíclico se ha vendido y los defensivos hacen techo relativo. | **Preparar rotación hacia sectores cíclicos y beta alto compra táctica en corrección.** |
| 1 | `DEFENSIVE` | **Motor de Deriva (flujo defensivo)** | Rotación defensiva = el mercado se está deteriorando. | HR=52.0% a zz25, HR=55.3% a zz75. Edge leve positivo. El flujo defensivo NO implica caída, sino reacomodación sectorial. | **Mantener con sesgo selectivo a sectores defensivos (`MKT_HOLD_STABLE`).** |
| 4 | `OFFENSIVE` | **Motor de Deriva (expansión)** | Rotación ofensiva confirma tendencia alcista; comprar agresivamente. | HR=54.5% a zz25, HR=57.1% a zz75 con Edge +3.0%. Tendencia sostenida pero no explosiva. | **Mantener con sesgo a sectores cíclicos (`MKT_HOLD_STABLE`).** |
| 4 | `OFFENSIVE (D2=4)` | **Coherente** | Tecnología subiendo demasiado rápido en 3 días es sobrecompra que debe corregir inmediatamente. | ROTATION D2=4 (FAST_SPIKE_3D) tiene HR=66.9%, Edge=+13.5% y PF=1.56. Confirma continuación alcista con fuerza institucional. | **Montarse a la tendencia en sectores líderes acumulación estructural.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Noviembre 2008 (Defensivo extremo), Marzo 2009 (Giro violento a cíclicos), Noviembre 2020 (Rotación masiva por vacunas).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `96` episodios (2.1% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 3`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** Rotation < -1.97 (-1σ).
- **Alerta Roja (CRITICAL / EMERGENCY):** Rotation < -4.31 (-2σ / Tier >= 1 Defensivo). Blowoff < -6.68.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica en corrección.
- **Criterio de Desactivación:** Rotation ratio cruzando por encima de 0.0 (sesgo ofensivo restablecido).

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__0__1` | `EXTREME_DEFENSIVE` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | +46.6% | 100.0% | 1.87 | 3 | [43.9%, 100.0%] |
| `0__1__0` | `EXTREME_DEFENSIVE` | `DECELERATING_DOWN_3D` | `VOL_EXTREME_SQUEEZE` | +46.6% | 100.0% | 3.78 | 2 | [34.2%, 100.0%] |
| `0__1__4` | `EXTREME_DEFENSIVE` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | +46.6% | 100.0% | 8.1 | 2 | [34.2%, 100.0%] |
| `0__2__0` | `EXTREME_DEFENSIVE` | `STABLE_CONTINUATION_3D` | `VOL_EXTREME_SQUEEZE` | +46.6% | 100.0% | 2.46 | 2 | [34.2%, 100.0%] |
| `1__1__0` | `DEFENSIVE` | `DECELERATING_DOWN_3D` | `VOL_EXTREME_SQUEEZE` | +46.6% | 100.0% | 5.8 | 2 | [34.2%, 100.0%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__0__0` | `DEFENSIVE` | `FAST_CRUSH_3D` | `VOL_EXTREME_SQUEEZE` | -53.4% | 0.0% | 0.1 | 2 | [0.0%, 65.8%] |
| `2__3__0` | `NEUTRAL_DEFENSIVE` | `ACCELERATING_UP_3D` | `VOL_EXTREME_SQUEEZE` | -53.4% | 0.0% | 0.34 | 4 | [0.0%, 49.0%] |
| `3__0__1` | `NEUTRAL_OFFENSIVE` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | -53.4% | 0.0% | 0.2 | 3 | [0.0%, 56.1%] |
| `0__1__3` | `EXTREME_DEFENSIVE` | `DECELERATING_DOWN_3D` | `VOL_ACCELERATING_EXPANSION` | -36.7% | 16.7% | 0.31 | 6 | [3.0%, 56.4%] |
| `2__1__4` | `NEUTRAL_DEFENSIVE` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | -36.7% | 16.7% | 0.36 | 12 | [4.7%, 44.8%] |
