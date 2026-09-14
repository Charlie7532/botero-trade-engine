# Referencia de Estación — SKEW

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes

> **Estación:** `skew` · **Polaridad Canónica:** `INVERTED` · **Rol:** `Confirmador de Largo Plazo (ACUMULACIÓN en D1=0) y Precursor de Riesgo de Cola (PARANOIA en D1=5).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `SKEW` (CBOE SKEW Index)
- **Física:** Precio de la cola izquierda (out-of-the-money puts) frente a opciones at-the-money; demanda de seguro de crash catastrófico.
- **Incepción Oficial:** `2011-02-01` | **Cobertura:** `2011-02-01 a 2026-09-03`
- **Muestra Total:** `3,921` barras diarias continuas | **Total Episodios:** `2,787`
- **Espacio de Estados:** `105` registrados | `105` poblados empíricamente
- **Distribución de Rareza:** `57` estados con $N < 10$ (54.3% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_CONFIDENCE` | 52 | 67.3% | +11.3% | +1.06% | **Fuerte Convicción Estructural (+11.3% Edge)** | `Acumulación de Largo Plazo` |
| 1 | `CONFIDENCE` | 164 | 52.4% | -3.6% | +0.16% | **Neutral Sólido** | `Construcción de Tendencia` |
| 2 | `NEUTRAL_CONFIDENT` | 463 | 48.2% | -7.9% | +0.08% | **Neutral Débil** | `Régimen Benigno Estándar` |
| 3 | `NEUTRAL_PARANOID` | 938 | 57.9% | +1.9% | +0.62% | **Cobertura Preventiva Ligera** | `Incipiente Cobertura de Cola` |
| 4 | `PARANOIA` | 853 | 50.5% | -5.5% | +0.22% | **Paranoia de Mercado Activa** | `Protección de Portafolios` |
| 5 | `EXTREME_PARANOIA` | 317 | 53.0% | -3.0% | +0.27% | **Pánico Latente de Cola Izquierda** | `Precursor de Riesgo de Cola` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `INVERTED`
  * *Regla:* Bin 0 = Estrés / Miedo / Descalabro (Suelo / Oportunidad); Bin 5 = Expansión / Facilidad.
- **Profesión de la Estación:** `Confirmador de Largo Plazo (ACUMULACIÓN en D1=0) y Precursor de Riesgo de Cola (PARANOIA en D1=5).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_CONFIDENCE`) | 11.5% | 13.5% | 17.3% | 11.5% | 9.6% | 36.5% | `ENTRE` (36.5%) | 52.6% | **0.192** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`CONFIDENCE`) | 7.3% | 12.2% | 14.0% | 9.1% | 8.5% | 48.8% | `ENTRE` (48.8%) | 40.0% | **0.195** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_CONFIDENT`) | 5.4% | 9.3% | 9.7% | 5.8% | 3.5% | 66.3% | `ENTRE` (66.3%) | 41.4% | **0.274** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_PARANOID`) | 4.4% | 7.1% | 7.6% | 5.1% | 4.1% | 71.7% | `ENTRE` (71.7%) | 56.9% | **0.408** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`PARANOIA`) | 4.1% | 3.3% | 4.1% | 3.8% | 4.3% | 80.4% | `ENTRE` (80.4%) | 48.0% | **0.386** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_PARANOIA`) | 4.1% | 4.1% | 4.1% | 3.5% | 2.2% | 82.0% | `ENTRE` (82.0%) | 48.8% | **0.401** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **72.7% de su masa en ENTRE**. Esto confirma que `SKEW` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT2` | **Lead-Time:** Medio (mide preparación anticipada para cisnes negros, no volatilidad inmediata).
- **Precursores Causalmente Previos:** CAT1 (Credit) y concentración de mercado.
- **Confirmadores Posteriores:** VIX disparándose (cuando la cola se materializa en volatilidad real).

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.

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
| 0 | `EXTREME_CONFIDENCE` | **Contrarian / Coherente** | SKEW bajo significa que a nadie le importa el mercado y está descuidado. | SKEW D1=0 (< 114.67) es la única estación cuyo EV crece monotónicamente con la escala temporal: 67% en zz25 → 87% en zz50 → 94% en zz75. Marca acumulación estructural institucional de largo plazo. | **Acumulación estructural de alta convicción acumulación estructural.** |
| 5 | `EXTREME_PARANOIA` | **Precursor / Coherente** | SKEW alto (> 145) significa que el crash ocurrirá hoy o mañana. | SKEW alto es un seguro comprado para los próximos 30-60 días. El mercado puede seguir subiendo mientras los institucionales se cubren. | **No salir en pánico, pero implementar coberturas y ceñir stops.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Septiembre 2014 (SKEW 143), Octubre 2018 (SKEW 153), Junio 2021 (SKEW 170 - récord de hedging sin crash inmediato).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `88` episodios (3.16% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** SKEW > 144.48 (+1σ).
- **Alerta Roja (CRITICAL / EMERGENCY):** SKEW > 159.40 (+2σ / Tier >= 1). Blowoff > 175.24.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** trim táctico.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → acumulación estructural.
- **Criterio de Desactivación:** SKEW normalizado por debajo de 125.0.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__1__3` | `EXTREME_CONFIDENCE` | `DECELERATING_DOWN_3D` | `VOL_ACCELERATING_EXPANSION` | +44.0% | 100.0% | 13.95 | 2 | [34.2%, 100.0%] |
| `3__0__0` | `NEUTRAL_PARANOID` | `FAST_CRUSH_3D` | `VOL_EXTREME_SQUEEZE` | +44.0% | 100.0% | 4.01 | 2 | [34.2%, 100.0%] |
| `4__1__0` | `PARANOIA` | `DECELERATING_DOWN_3D` | `VOL_EXTREME_SQUEEZE` | +44.0% | 100.0% | 5.3 | 2 | [34.2%, 100.0%] |
| `5__1__1` | `EXTREME_PARANOIA` | `DECELERATING_DOWN_3D` | `VOL_MODERATE_COMPRESSION` | +44.0% | 100.0% | 1.39 | 2 | [34.2%, 100.0%] |
| `5__3__4` | `EXTREME_PARANOIA` | `ACCELERATING_UP_3D` | `VOL_PEAK_DECELERATION` | +24.0% | 80.0% | 2.95 | 5 | [37.6%, 96.4%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `2__1__4` | `NEUTRAL_CONFIDENT` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | -56.0% | 0.0% | 2.33 | 2 | [0.0%, 65.8%] |
| `3__4__3` | `NEUTRAL_PARANOID` | `FAST_SPIKE_3D` | `VOL_ACCELERATING_EXPANSION` | -56.0% | 0.0% | 0.02 | 2 | [0.0%, 65.8%] |
| `4__4__1` | `PARANOIA` | `FAST_SPIKE_3D` | `VOL_MODERATE_COMPRESSION` | -56.0% | 0.0% | 0.21 | 2 | [0.0%, 65.8%] |
| `4__1__3` | `PARANOIA` | `DECELERATING_DOWN_3D` | `VOL_ACCELERATING_EXPANSION` | -43.5% | 12.5% | 0.34 | 16 | [3.5%, 36.0%] |
| `1__1__1` | `CONFIDENCE` | `DECELERATING_DOWN_3D` | `VOL_MODERATE_COMPRESSION` | -31.0% | 25.0% | 0.29 | 4 | [4.6%, 69.9%] |
