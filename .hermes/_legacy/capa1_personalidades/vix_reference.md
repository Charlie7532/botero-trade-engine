# Referencia de Estación — VIX

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes

> **Estación:** `vix` · **Polaridad Canónica:** `NORMAL` · **Rol:** `Detector de Giro de Suelo (PISO) en pánico, y Motor de Deriva (CONTINUACIÓN) en complacencia.`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `VIX` (CBOE Volatility Index (VIX))
- **Física:** Precio del seguro de volatilidad implícita del S&P 500 a 30 días vista.
- **Incepción Oficial:** `1990-01-02` | **Cobertura:** `1993-01-29 a 2026-09-03`
- **Muestra Total:** `8,457` barras diarias continuas | **Total Episodios:** `5,916`
- **Espacio de Estados:** `113` registrados | `113` poblados empíricamente
- **Distribución de Rareza:** `50` estados con $N < 10$ (44.2% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_COMPLACENCY` | 145 | 41.4% | -12.5% | +0.93% | **Fuerte Deriva Alcista (Trend Drift)** | `Continuación de Baja Volatilidad` |
| 1 | `COMPLACENCY` | 487 | 49.9% | -4.0% | +0.40% | **Alcista Moderado Inercial** | `Tendencia Saludable` |
| 2 | `NEUTRAL_CALM` | 1960 | 54.6% | +0.7% | +0.34% | **Neutral Incondicional** | `Régimen Ordinario` |
| 3 | `NEUTRAL_ALERT` | 1754 | 52.6% | -1.3% | +0.19% | **Alerta Temprana / Compresión** | `Transición a Turbulencia` |
| 4 | `PANIC` | 1217 | 53.2% | -0.7% | +0.24% | **Estrés Elevado / Corrección Activa** | `Distribución / Corrección en Marcha` |
| 5 | `EXTREME_PANIC` | 353 | 49.9% | -4.1% | +0.15% | **Pánico Clímax / Suelo en Potencia** | `Piso / Capitulación` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `NORMAL`
  * *Regla:* Bin 0 = Complacencia / Valor bajo; Bin 5 = Pánico / Valor alto (Suelo de capitulación).
- **Profesión de la Estación:** `Detector de Giro de Suelo (PISO) en pánico, y Motor de Deriva (CONTINUACIÓN) en complacencia.`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_COMPLACENCY`) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | `ENTRE` (100.0%) | 41.4% | **0.414** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`COMPLACENCY`) | 0.6% | 0.2% | 0.4% | 1.0% | 1.6% | 96.1% | `ENTRE` (96.1%) | 50.2% | **0.483** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_CALM`) | 3.3% | 3.2% | 2.9% | 3.5% | 4.4% | 82.8% | `ENTRE` (82.8%) | 52.4% | **0.434** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_ALERT`) | 8.3% | 10.4% | 10.9% | 10.0% | 7.0% | 53.3% | `ENTRE` (53.3%) | 50.6% | **0.27** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`PANIC`) | 9.9% | 17.6% | 22.2% | 13.4% | 7.8% | 29.1% | `ENTRE` (29.1%) | 41.8% | **0.122** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_PANIC`) | 6.8% | 26.9% | 33.1% | 13.0% | 3.4% | 16.7% | `t=0` (33.1%) | 64.1% | **0.212** | **Gatillo Síncrono** (día del pivote) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **60.6% de su masa en ENTRE**. Esto confirma que `VIX` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT2` | **Lead-Time:** Medio (los institucionales compran puts/cobertura antes de que el precio caiga).
- **Precursores Causalmente Previos:** CREDIT (HYG/LQD) y YIELD_CURVE (el estrés de crédito o curva presiona primero).
- **Confirmadores Posteriores:** BSI (S5TW) colapsando (la acción real confirma la capitulación) y VVIX acelerando.

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
  * `D1=5 + D2=4`: Pánico en aceleración (falling knife); esperar.
  * `D1=5 + D2=0`: Pánico en desaceleración y absorción; detonante inmediato de rebote alcista en V.
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
| 0 | `EXTREME_COMPLACENCY` | **Motor de Deriva** | VIX bajo es peligroso / complacencia previa a un crash inminente; se debe vender o shortear. | VIX D1=0 tiene HR=82.8% a favor de la tendencia alcista con EV=+3.76% en zz25. El mercado pasa semanas en deriva alcista constante. | **PROHIBIDO shortear o salir de posiciones core por VIX bajo; mantener posiciones alcistas mantener posición.** |
| 5 | `EXTREME_PANIC` | **Contrarian / Coherente** | VIX disparado a 40+ significa que el mundo se acaba; vender todo por pánico. | VIX D1=5 concentra 33.1% de masa en t=0 con Hit Rate de rebote del 64.1% a favor de compras. Es el suelo del mercado. | **Tras la absorción inicial (D2 frenando), es la gran oportunidad de compra compra táctica en corrección.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Octubre 2008 (VIX 89.53), Agosto 2011 (VIX 48.00), Febrero 2018 (Volmageddon, VIX 50.30), Marzo 2020 (Covid, VIX 85.47).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `157` episodios (2.65% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** VIX entre 25.71 y 40.73 (+1σ a +2σ) con D2 acelerando.
- **Alerta Roja (CRITICAL / EMERGENCY):** VIX > 40.73 (> +2σ / Tier >= 1 Overflow). Blowoff > 5σ si VIX > 69.95.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis — congelar nuevas compras mientras D2 esté en FAST_SPIKE_3D.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica o acumulación estructural — en cuanto D2 desacelere a DECEL o D3 marque PEAK_DECEL.
- **Criterio de Desactivación:** VIX descendiendo por debajo de 25.71 de forma sostenida por 3 barras.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__0__2` | `COMPLACENCY` | `FAST_CRUSH_3D` | `VOL_NEUTRAL_BASELINE` | +46.1% | 100.0% | 4.04 | 3 | [43.9%, 100.0%] |
| `1__3__3` | `COMPLACENCY` | `ACCELERATING_UP_3D` | `VOL_ACCELERATING_EXPANSION` | +46.1% | 100.0% | 24.27 | 2 | [34.2%, 100.0%] |
| `3__1__4` | `NEUTRAL_ALERT` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 2.07 | 4 | [51.0%, 100.0%] |
| `5__3__0` | `EXTREME_PANIC` | `ACCELERATING_UP_3D` | `VOL_EXTREME_SQUEEZE` | +46.1% | 100.0% | 18.19 | 2 | [34.2%, 100.0%] |
| `5__4__4` | `EXTREME_PANIC` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 4.59 | 2 | [34.2%, 100.0%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `2__4__2` | `NEUTRAL_CALM` | `FAST_SPIKE_3D` | `VOL_NEUTRAL_BASELINE` | -53.9% | 0.0% | 0.53 | 2 | [0.0%, 65.8%] |
| `3__0__0` | `NEUTRAL_ALERT` | `FAST_CRUSH_3D` | `VOL_EXTREME_SQUEEZE` | -53.9% | 0.0% | 0.21 | 4 | [0.0%, 49.0%] |
| `5__3__4` | `EXTREME_PANIC` | `ACCELERATING_UP_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.25 | 5 | [0.0%, 43.4%] |
| `0__2__0` | `EXTREME_COMPLACENCY` | `STABLE_CONTINUATION_3D` | `VOL_EXTREME_SQUEEZE` | -28.9% | 25.0% | 2.08 | 4 | [4.6%, 69.9%] |
| `0__2__4` | `EXTREME_COMPLACENCY` | `STABLE_CONTINUATION_3D` | `VOL_PEAK_DECELERATION` | -28.9% | 25.0% | 1.25 | 4 | [4.6%, 69.9%] |
