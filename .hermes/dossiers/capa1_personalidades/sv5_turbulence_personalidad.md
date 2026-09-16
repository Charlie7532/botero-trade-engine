# Dossier de Personalidad V3 — SV5_TURBULENCE

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes · **Versión:** V3 (2026-09-16)

> **Estación:** `sv5_turbulence` · **Polaridad Canónica:** `NORMAL` · **Rol:** `Detector de Desorden Institucional (D1=5 = PISO por agotamiento; D1=0 = DISTRIBUCIÓN silenciosa).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `SV5_TURBULENCE` (Institutional Volume Turbulence (SV5_TURB))
- **Física:** Desviación estándar de los cambios en la participación de volumen institucional del SP500.
- **Incepción Oficial:** `1999-01-04` | **Cobertura:** `1999-01-04 a 2026-09-03`
- **Muestra Total:** `6,960` barras diarias continuas | **Total Episodios:** `4,517`
- **Espacio de Estados:** `110` registrados | `110` poblados empíricamente
- **Distribución de Rareza:** `45` estados con $N < 10$ (40.9% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `EXTREME_CALM` | 51 | 41.2% | -12.2% | -0.58% | **Sesgo Bajista Oculto (-12.2% Edge)** | `Distribución Silenciosa Institucional` |
| 1 | `CALM` | 334 | 47.3% | -6.1% | +0.04% | **Participación Apática / Débil** | `Desidia Institucional` |
| 2 | `NEUTRAL_CALM` | 1170 | 52.5% | -0.9% | +0.29% | **Neutral Incondicional** | `Flujo Ordinario de Bloques` |
| 3 | `NEUTRAL_TURBULENT` | 1691 | 50.7% | -2.7% | +0.14% | **Actividad Institucional Creciente** | `Rebalanceo de Posiciones` |
| 4 | `TURBULENT` | 920 | 54.7% | +1.3% | +0.37% | **Fuerte Rotación de Volumen (+1.3% Edge)** | `Aceleración de Transferencia` |
| 5 | `EXTREME_TURBULENT` | 351 | 60.1% | +6.7% | +0.54% | **Agotamiento Vendedor Institucional (+6.7% Edge)** | `Piso / Clímax de Transferencia` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `NORMAL`
  * *Regla:* Bin 0 = Complacencia / Valor bajo; Bin 5 = Pánico / Valor alto (Suelo de capitulación).
- **Profesión de la Estación:** `Detector de Desorden Institucional (D1=5 = PISO por agotamiento; D1=0 = DISTRIBUCIÓN silenciosa).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`EXTREME_CALM`) | 11.8% | 5.9% | 2.0% | 13.7% | 3.9% | 62.7% | `ENTRE` (62.7%) | 34.4% | **0.216** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`CALM`) | 7.5% | 9.3% | 10.5% | 5.1% | 6.0% | 61.7% | `ENTRE` (61.7%) | 44.2% | **0.273** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`NEUTRAL_CALM`) | 5.0% | 7.9% | 9.4% | 6.6% | 4.4% | 66.7% | `ENTRE` (66.7%) | 46.2% | **0.308** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NEUTRAL_TURBULENT`) | 6.3% | 8.9% | 10.3% | 8.2% | 5.0% | 61.3% | `ENTRE` (61.3%) | 47.0% | **0.288** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`TURBULENT`) | 4.7% | 7.7% | 9.9% | 6.6% | 3.6% | 67.5% | `ENTRE` (67.5%) | 54.9% | **0.371** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_TURBULENT`) | 6.3% | 11.4% | 10.5% | 7.7% | 4.8% | 59.3% | `ENTRE` (59.3%) | 56.7% | **0.336** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **63.8% de su masa en ENTRE**. Esto confirma que `SV5_TURBULENCE` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT3` | **Lead-Time:** Corto (acción real de volumen de los participantes institucionales).
- **Precursores Causalmente Previos:** Flujo de grandes bloques y dark pools.
- **Confirmadores Posteriores:** BSI (confirmación de precio del volumen).

### 4.1 Reglas de Confluencia Operativa

1. **Miedo sin Venta (`ESPERAR`):** Si esta estación emite alarma o pánico en CAT2 pero CAT3 (BSI/SV5) mantiene soporte sin colapsar, el mercado aún no ha terminado de absorber la venta. Directiva: `ESPERAR / SUB-REACCIÓN`.
2. **Miedo con Venta (`COMPRAR`):** Si esta estación emite pánico/estrés extremo y CAT3 colapsa en capitulación completa, el ciclo de venta se ha completado. Directiva: `COMPRAR / PISO GENERACIONAL`.

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
| 0 | `EXTREME_CALM` | **Trampa Narrativa** | Baja turbulencia de volumen es señal de mercado plácido, seguro y sin riesgo. | D1=0 (< 2.30) coincide con distribución silenciosa institucional: las manos fuertes descargan posiciones sin levantar volumen agregado. Retorno neto inferior al benchmark. | **Régimen de fondo desfavorable; reducir tamaño de posición.** |
| 5 | `EXTREME_TURBULENT` | **Coherente** | La turbulencia masiva de volumen es caos descontrolado donde nadie debe operar. | D1=5 (> 17.44) señala clímax de transferencia institucional: las manos débiles capitulan y las manos fuertes absorben. Edge alcista neto de +6.7% en suelos. | **Acompañar la absorción institucional compra táctica en corrección.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Octubre 2008 (Turbulence 24.5), Mayo 2010 (Flash Crash 21.0), Marzo 2020 (Covid 23.8).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `181` episodios (4.01% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** SV5_TURB > 10.77 (+1σ).
- **Alerta Roja (CRITICAL / EMERGENCY):** SV5_TURB > 17.44 (+2σ / Tier >= 1). Blowoff > 23.75.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** bloqueo por crisis.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → compra táctica en corrección.
- **Criterio de Desactivación:** SV5_TURB estabilizado por debajo de 8.0.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `2__0__0` | `NEUTRAL_CALM` | `FAST_CRUSH_3D` | `VOL_EXTREME_SQUEEZE` | +46.6% | 100.0% | 3.2 | 3 | [43.9%, 100.0%] |
| `4__4__0` | `TURBULENT` | `FAST_SPIKE_3D` | `VOL_EXTREME_SQUEEZE` | +46.6% | 100.0% | 2.26 | 5 | [56.6%, 100.0%] |
| `4__3__0` | `TURBULENT` | `ACCELERATING_UP_3D` | `VOL_EXTREME_SQUEEZE` | +34.1% | 87.5% | 2.19 | 8 | [52.9%, 97.8%] |
| `3__4__2` | `NEUTRAL_TURBULENT` | `FAST_SPIKE_3D` | `VOL_NEUTRAL_BASELINE` | +32.3% | 85.7% | 1.42 | 7 | [48.7%, 97.4%] |
| `3__2__4` | `NEUTRAL_TURBULENT` | `STABLE_CONTINUATION_3D` | `VOL_PEAK_DECELERATION` | +29.9% | 83.3% | 2.13 | 6 | [43.6%, 97.0%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__0__2` | `EXTREME_CALM` | `FAST_CRUSH_3D` | `VOL_NEUTRAL_BASELINE` | -53.4% | 0.0% | 0.09 | 2 | [0.0%, 65.8%] |
| `5__3__0` | `EXTREME_TURBULENT` | `ACCELERATING_UP_3D` | `VOL_EXTREME_SQUEEZE` | -53.4% | 0.0% | 0.4 | 4 | [0.0%, 49.0%] |
| `2__3__1` | `NEUTRAL_CALM` | `ACCELERATING_UP_3D` | `VOL_MODERATE_COMPRESSION` | -39.1% | 14.3% | 0.39 | 7 | [2.6%, 51.3%] |
| `3__4__4` | `NEUTRAL_TURBULENT` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -28.4% | 25.0% | 0.69 | 4 | [4.6%, 69.9%] |
| `4__0__3` | `TURBULENT` | `FAST_CRUSH_3D` | `VOL_ACCELERATING_EXPANSION` | -28.4% | 25.0% | 0.57 | 8 | [7.1%, 59.1%] |
