# Dossier de Personalidad V3 — YIELD_CURVE

> **Módulo:** Capa 1 de 3 (Personalidades Individuales) · **Sistema:** METAR Hermes · **Versión:** V3 (2026-09-16)

> **Estación:** `yield_curve` · **Polaridad Canónica:** `TRANSITIONAL_MACRO` · **Rol:** `Régimen Macroeconómico de Fondo (D1=0 Inversión = Alza; D1=4/5 Empinamiento = Peligro).`

> **Regla Anti-Derivación:** El agente NO calcula polaridades ni deduce direcciones en runtime; lee la decisión precomputada en esta ficha.

---

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA

- **Estación:** `YIELD_CURVE` (US Treasury Yield Curve Spread (10Y - 3M))
- **Física:** Pendiente de la curva de tipos de interés soberana de EE.UU.; ciclo macroeconómico de liquidez y política monetaria.
- **Incepción Oficial:** `1993-01-29` | **Cobertura:** `1993-01-29 a 2026-09-03`
- **Muestra Total:** `8,457` barras diarias continuas | **Total Episodios:** `5,414`
- **Espacio de Estados:** `132` registrados | `132` poblados empíricamente
- **Distribución de Rareza:** `62` estados con $N < 10$ (47.0% del universo poblado) — *conforme a la distribución normal gaussiana calibrada a 33 años*.

---

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)

Tabla empírica y probabilística de 6 filas obligatorias (Bins 0 a 5) con métricas consolidadas del Fact Store:

| D1 Bin | Label Canónico | N Episodios | HR zz25 (%) | Edge Neto (%) | EV zz25 (%) | Sesgo Probabilístico | Fase del Ciclo |
|:---:|:---|:---:|:---:|:---:|:---:|:---|:---|
| 0 | `DEEP_INVERSION` | 534 | 64.2% | +10.3% | +0.75% | **Fuerte Sesgo Alcista en Equities (+10.3% Edge)** | `Inversión Macroeconómica de Ciclo` |
| 1 | `MODERATE_INVERSION` | 1005 | 58.5% | +4.6% | +0.51% | **Sesgo Favorable (+4.6% Edge)** | `Madurez de Inversión` |
| 2 | `FLAT_CURVE` | 1816 | 53.5% | -0.4% | +0.47% | **Neutral Incondicional** | `Transición Plana` |
| 3 | `NORMAL_CURVE` | 1423 | 48.4% | -5.5% | +0.00% | **Neutral Débil** | `Pendiente Positiva Estándar` |
| 4 | `STEEPNING_CURVE` | 470 | 50.6% | -3.3% | +0.05% | **Alerta Macro por Desinversión** | `Normalización Rápida / Pre-Recesión` |
| 5 | `EXTREME_STEEPNING` | 166 | 39.8% | -14.2% | -0.49% | **Fuerte Sesgo Bajista (-14.2% Edge, EV Negativo)** | `Empinamiento de Crisis / Choque Recesivo` |

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING

- **Polaridad Canónica:** `TRANSITIONAL_MACRO`
  * *Regla:* Bin 0 = Inversión Profunda (Expansión de equities); Bins 4-5 = Empinamiento / Desinversión (Crash macro).
- **Profesión de la Estación:** `Régimen Macroeconómico de Fondo (D1=0 Inversión = Alza; D1=4/5 Empinamiento = Peligro).`

### 3.1 Geometría de Slots (zz25) y Poder de Confirmación en Slot Modal

| Bin D1 | Masa t-2 (%) | Masa t-1 (%) | Masa t=0 (%) | Masa t+1 (%) | Masa t+2 (%) | Masa ENTRE (%) | Slot Modal | HR Modal | $P_{\text{confirmación}}$ | Rol Temporal |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 (`DEEP_INVERSION`) | 4.5% | 7.5% | 9.4% | 7.1% | 5.2% | 66.3% | `ENTRE` (66.3%) | 65.5% | **0.435** | **Proceso Lento / Runway** (entre pivotes) |
| 1 (`MODERATE_INVERSION`) | 4.6% | 7.6% | 8.8% | 6.1% | 4.1% | 69.0% | `ENTRE` (69.0%) | 58.3% | **0.402** | **Proceso Lento / Runway** (entre pivotes) |
| 2 (`FLAT_CURVE`) | 6.2% | 8.0% | 9.5% | 7.1% | 5.7% | 63.5% | `ENTRE` (63.5%) | 48.1% | **0.306** | **Proceso Lento / Runway** (entre pivotes) |
| 3 (`NORMAL_CURVE`) | 7.0% | 11.6% | 13.1% | 9.1% | 4.8% | 54.3% | `ENTRE` (54.3%) | 41.9% | **0.228** | **Proceso Lento / Runway** (entre pivotes) |
| 4 (`STEEPNING_CURVE`) | 7.4% | 8.9% | 12.8% | 10.4% | 5.7% | 54.7% | `ENTRE` (54.7%) | 46.7% | **0.255** | **Proceso Lento / Runway** (entre pivotes) |
| 5 (`EXTREME_STEEPNING`) | 6.0% | 7.2% | 8.4% | 7.8% | 5.4% | 65.1% | `ENTRE` (65.1%) | 33.3% | **0.217** | **Proceso Lento / Runway** (entre pivotes) |

### 3.2 Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño)

La estación presenta **61.7% de su masa en ENTRE**. Esto confirma que `YIELD_CURVE` NO es un oscilador de pivote puro, sino un **generador de régimen y pista continua**. Su presencia fuera de rango representa **CONTINUACIÓN CON FUERZA** cuando acompaña tendencias, o **CANARIO DE PROCESO LENTO** cuando acumula energía antes de un giro.

---

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL

- **Clasificación por Naturaleza:** `CAT1` | **Lead-Time:** Largo (anticipa recesiones con 12 a 18 meses de adelanto).
- **Precursores Causalmente Previos:** Política de la Reserva Federal e inflación.
- **Confirmadores Posteriores:** Credit Spreads y desempleo macro.

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
| 0 | `DEEP_INVERSION` | **Trampa Narrativa Masiva** | La curva de rendimientos se invirtió, la recesión viene mañana, hay que vender todas las acciones ya. | YIELD D1=0 tiene HR=64.2%, Edge=+10.2% y EV=+0.67% a favor de los activos de riesgo. Históricamente, las bolsas suben con fuerza durante la inversión profunda; el colapso ocurre cuando la curva se desinvierte rápidamente hacia el empinamiento. | **Permanecer invertido durante la inversión mantener posición; el crash NO ocurre durante la inversión, sino en el empinamiento.** |
| 1 | `INVERSION` | **Contrarian (fuerte)** | Curva invertida = recesión inminente; vender todo. | HR=54.2% a zz25, HR=59.2% a zz75 con Edge +4.2%. La inversión de curva tiene un lead de 12-18 meses; el mercado SUBE durante la inversión. | **Mantener posiciones; la inversión es un canario a largo plazo, no un gatillo de venta inmediata (`MKT_HOLD_STABLE`).** |
| 4 | `STEEPENING` | **Coherente (cautela)** | Curva empinada = economía saludable; comprar. | HR=52.1% a zz25, HR=52.7% a zz75. Edge NEGATIVO a zz75. El empinamiento rápido post-inversión indica el impacto REAL de la política monetaria. | **Cautela; empinamiento no es señal de compra. Puede indicar estrés post-inversión (`MKT_HOLD_STABLE`).** |
| 5 | `EXTREME_STEEPNING` | **Contrarian / Coherente** | La curva se está normalizando y empinando, lo peor ya pasó y la economía se recupera. | La desinversión acelerada y empinamiento extremo (D1=4 y D1=5) ocurre cuando la Fed baja tasas de emergencia porque la recesión ya llegó. Es el periodo de mayor caída en bolsas. | **Máxima cautela defensiva.** |

---

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas

- Las muestras con $N < 10$ en colas de $\pm 2\sigma$ representan el $2.28\%$ teórico de la población y capturan las fracturas estructurales más importantes de la historia.
- **Casos Históricos Relevantes en esta Estación:** Agosto 2000 (Inversión dotcom), Febrero 2007 (Inversión GFC), Noviembre 2022 - 2024 (Inversión récord histórica 10Y-3M a -1.55%).
- **Regla de No-Censura:** Prohibido degradar o filtrar muestras raras como 'ruido'. Se reportan con su frecuencia observada $k/n$, intervalo de Wilson al 95% y dispersión empírica MFE/MAE.

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)

- **Episodios con Desbordamiento (Tier $\ge 1$):** `307` episodios (5.67% de la muestra total).
- **Máximo Tier Histórico Registrado:** `Tier 2`.
- **Escala de Tiers (`sigma_overflow.py`):**
  * Tier 1 (3σ - 4σ): `OVERFLOW_MODERADO` (WARNING)
  * Tier 2 (4σ - 5σ): `OVERFLOW_EXTREMO` (CRITICAL)
  * Tier 3 (5σ - 7σ): `BLOW_OFF_SEVERE` (EMERGENCY)
  * Tier 4 (7σ - 10σ): `BLOW_OFF_EXTREME` (CATASTROPHIC)
  * Tier 5 (≥ 10σ): `BLOW_OFF_SYSTEMIC` (SYSTEMIC)

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)

- **Alerta Amarilla (WARNING):** Spread < -1.05% (Inversión profunda) o empinamiento rápido > +0.22% en 3d.
- **Alerta Roja (CRITICAL / EMERGENCY):** Desinversión de pánico con empinamiento acelerado > +2σ (Tier >= 1).
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético Inicial (Caída libre / D2 expansivo):** circuit breaker macroeconómico — si la desinversión coincide con credit stress.
  * **Fase de Clímax, Capitulación o Absorción:** **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → acumulación estructural.
- **Criterio de Desactivación:** Curva con pendiente positiva normalizada entre +1.0% y +2.0%.

---

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES

### 9.1 Top 5 Tríadas Alcistas (Suelo / Rebote / Compra)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `0__0__4` | `DEEP_INVERSION` | `FAST_CRUSH_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 2.11 | 2 | [34.2%, 100.0%] |
| `1__0__0` | `MODERATE_INVERSION` | `FAST_CRUSH_3D` | `VOL_EXTREME_SQUEEZE` | +46.1% | 100.0% | 2.01 | 3 | [43.9%, 100.0%] |
| `1__0__1` | `MODERATE_INVERSION` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | +46.1% | 100.0% | 2.82 | 4 | [51.0%, 100.0%] |
| `1__0__4` | `MODERATE_INVERSION` | `FAST_CRUSH_3D` | `VOL_PEAK_DECELERATION` | +46.1% | 100.0% | 3.22 | 2 | [34.2%, 100.0%] |
| `1__1__0` | `MODERATE_INVERSION` | `DECELERATING_DOWN_3D` | `VOL_EXTREME_SQUEEZE` | +46.1% | 100.0% | 3.93 | 2 | [34.2%, 100.0%] |

### 9.2 Top 5 Tríadas Bajistas / Defensivas (Techo / Preservación)

| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % (MIN) | HR zz25 | RR | N | Wilson 95% CI |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|
| `1__1__4` | `MODERATE_INVERSION` | `DECELERATING_DOWN_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.17 | 4 | [0.0%, 49.0%] |
| `2__0__1` | `FLAT_CURVE` | `FAST_CRUSH_3D` | `VOL_MODERATE_COMPRESSION` | -53.9% | 0.0% | 0.15 | 4 | [0.0%, 49.0%] |
| `3__4__4` | `NORMAL_CURVE` | `FAST_SPIKE_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.16 | 3 | [0.0%, 56.1%] |
| `5__2__4` | `EXTREME_STEEPNING` | `STABLE_CONTINUATION_3D` | `VOL_PEAK_DECELERATION` | -53.9% | 0.0% | 0.27 | 7 | [0.0%, 35.4%] |
| `0__3__3` | `DEEP_INVERSION` | `ACCELERATING_UP_3D` | `VOL_ACCELERATING_EXPANSION` | -42.8% | 11.1% | 0.46 | 9 | [2.0%, 43.5%] |
