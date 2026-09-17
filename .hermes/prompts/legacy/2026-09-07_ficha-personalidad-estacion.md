# PROMPT — Fichas de Personalidad por Estación (Capa 1 de 3) · v3

> **Fecha:** 2026-09-07 · **Paso del pipeline:** CAPA 1 — 11 fichas individuales (una por estación).
> **Precede a:** CAPA 2 (fichas de agrupación por rol/fase) → CAPA 3 (criterio general = régimen de mercado).
> **Naturaleza:** Es la personalidad de UN indicador/estación. NO hay personalidad global; hay 11,
> y las capas superiores COMPONEN estas 11 (no las reemplazan ni las promedian).
>
> ## CONTRATO DE USO DEL AGENTE (A-Read: qué lee el agente y de dónde)
> **El agente NO lee SOLO esta ficha.** En su contexto también tiene los fact stores
> (`{station}_timing_fact_store.json` y `{station}_fact_store.json`). Por lo tanto, la ficha
> **NO duplica datos crudos que ya están en los fact stores** — los fact stores son la fuente de
> datos granular (per-episodio, per-escala, slots); el agente puede consultarlos puntualmente.
> La ficha existe para aportar lo que los fact stores **no tienen**:
>   (a) la TRADUCCIÓN/COHERENCIA de los números; (b) el significado direccional y de fase;
>   (c) el juicio de gobernanza (qué reportar, qué NO); (d) la lectura multiescala ya sintetizada;
>   (e) el perfil dimensional cinemático y la física de squeeze; (f) el contraste prosa vs verbo;
>   (g) el protocolo diamante, los overflows y el contrato de escalación a SIGMET.
> **Regla anti-redundancia:** Si el dato vive en el fact store, la ficha NO lo pega entero — la
> ficha apunta `→ ver {station}_timing_fact_store.json` y ofrece el VALOR YA INTERPRETADO (la
> decisión), no la tabla cruda completa.
>
> ## PRINCIPIO RECTOR (crítico — define el contenido entero de la ficha)
> **La ficha aporta el DECIDIDO; los fact stores aportan el DETALLE.**
> El agente NO deriva interpretación en runtime: cuando necesita un número exacto consulta el fact
> store; cuando necesita saber QUÉ significa y QUÉ hacer, lo lee YA RESUELTO en la ficha. Toda
> interpretación que hoy exige mirar el state_key crudo y aplicar la polaridad → se carga RESUELTA
> en la ficha. Si el agente tuviera que derivar (inferir "este state_key + esta polaridad = estrés"),
> repetiría en runtime el trabajo de construcción — con riesgo de error o alucinación.

---

## Objetivo

Generar **una Ficha de Personalidad por cada una de las 11 estaciones METAR**:
`vix, vvix, pcr, fg, sv5_turbulence, skew, credit, yield_curve, rotation, bsi, dxy`.
Ruta de destino: `.hermes/dossiers/capa1_personalidades/{station}_personalidad.md`.

---

## Entradas (fuentes de verdad — la ficha se DERIVA de estas, no se copia a ciegas)

1. `backend/modules/entry_decision/domain/rules/{station}_timing_fact_store.json` ×11
   (calibrados con barreras P95: zz25=35, zz50=110, zz75=190 barras) — D1/D2/D3, first-passage dual (`MIN` y `MAX`), slots_zz25, baselines, overflows.
2. `backend/modules/entry_decision/domain/rules/{station}_fact_store.json` ×11 — taxonomía V1, bordes empíricos, labels, estados registrados.
3. `.agents/references/metar/d1_labels_canonical.md` — labels D1 CANÓNICOS (copiar literal, PROHIBIDO inventar labels).
4. `.agents/references/metar/gaussian_scale_policy.md` — política gaussiana (edges σ, 6 bins simétricos).
5. `.hermes/plans/clasificacion_naturaleza.md` — clasificación causal CAT1 (Economía) → CAT2 (Protección) → CAT3 (Acción), lead-times relativos, reglas de compra/espera/venta, doble salida funcional de ROTATION e inercia de 504d de FG.
6. `.hermes/plans/2026-09-07_puente-fase-regimen-personalidad.md` — constructo maestro: fases del ciclo (`PISO → ACUMULACIÓN → CONTINUACIÓN → TECHO → DISTRIBUCIÓN → CRASH`), regímenes estables, multiescala y ROTATION como rotación sectorial.
7. `.hermes/prompts/2026-09-03-documento-diseno-valor-significado.md` — principio rector §3.3 (rareza = riqueza y significado), tratamiento honesto de lo fuera de rango (`ENTRE`), de-clustering como credibilidad y no exclusión.
8. `backend/modules/entry_decision/domain/rules/sigma_overflow.py` y `market_sigmet_hazard_service.py` — escala de 5 Tiers de desbordamiento (T1 a T5), clasificación de severidad y protocolo de despacho SIGMET.
9. `data/research/pivots/quants_obs.pkl` — pivotes ZigZag de referencia histórica.

---

## 👉 EL CONTENIDO: Estructura Homologada de las Fichas (9 Secciones Obligatorias)

Cada sección responde a la pregunta: *"¿Qué necesita saber el agente para operar SIN derivar lógica en runtime?"*.

```markdown
# Ficha de Personalidad — {STATION}

## 1. IDENTIDAD Y ARQUITECTURA FÍSICA
- station, familia física, qué mide (física del indicador en 1 línea clara y concisa).
- inception_date oficial (para evitar contaminación sintética pre-incepción), coverage, sample_size_bars.
- universo de estados: total_episodes, states_registered, states_populated, % estados N<10.

## 2. TABLA DE DIRECCIÓN Y DECISIÓN OPERATIVA (Mapa de Consumo del Agente)
La arquitectura de decisión se estructura en DOS NIVELES para garantizar 100% de cobertura sin ambigüedad:

### 2.1 Baseline Incondicional por D1 (Cobertura 100% de Estados Base)
Tabla exhaustiva de 6 filas obligatorias (Bins 0 a 5):
| D1 Bin | Label Canónico | Dirección | Fase del Ciclo | Directiva Canónica MKT (Regla 20) | Restricción Operativa |
*Directivas Canónicas de Mercado válidas (Ámbito MKT_):* MKT_ACCUMULATE_STRUCTURAL, MKT_BUY_DIP_TACTICAL, MKT_HOLD_STABLE, MKT_TRIM_TACTICAL, MKT_DISTRIBUTE_DECAY, MKT_BLOCK_CRISIS, MKT_MACRO_CIRCUIT_BREAKER.

> ⚠️ **CRÍTICO — ÁMBITO DE ACCIÓN (MKT_ vs STK_):** En Capa 1 las directivas pertenecen ESTRICTAMENTE al ámbito de Mercado (`MKT_`). Las estaciones METAR monitorean el mercado global y emiten directivas macro/clima; **PROHIBIDO usar el prefijo `STK_`** (las acciones a nivel de ticker individual pertenecen exclusivamente a los Entry Gates de cartera al evaluar acciones específicas).

### 2.2 Tríadas Singulares de Excepción (Moduladas por D2/D3 o |Edge| >= 10%)
Tabla con las combinaciones específicas donde la velocidad cinemática (D2) o la volatilidad interna (D3) alteran la directiva base de D1:
| State Key | Label D1 | D2 Kinematic | D3 Vol | Edge % | HR | RR | N | Tier Cred (Opus σ×N) | Directiva Específica (MKT_) |

> ⚠️ **TIERS DE CREDIBILIDAD (Matriz σ×N de Opus):** Usar exclusivamente las categorías cuantitativas de Opus:
> - `DIAMOND` ($N < 10$): Rareza con significado §3.3 (colas gaussianas extremas, auditoría de caso histórico real).
> - `UNUSUAL_COMBO` ($N \in [10..29]$): Muestra intermedia / combinación cinemática infrecuente.
> - `CONFIRMED_ALERT` ($N \ge 30$ en bines de alerta/extremos $D1 \in \{0, 1, 4, 5\}$ o estados de tensión): Señal estadísticamente robusta y confirmada.
> - `WEATHER` ($N \ge 30$ en bines centrales $D1 \in [2, 3]$): Clima modal ordinario del mercado.
> **PROHIBIDO usar las etiquetas obsoletas/degradantes `ANECDOTAL`, `LOW`, `MODERATE`, `HIGH`, `ROBUST`.**

> 📌 **Regla de Lookup para el Agente:**
> Al recibir el `state_key` actual:
> 1. Buscar si el `state_key` está registrado en la **Sub-tabla 2.2**. Si existe → ejecutar la directiva específica de excepción (`MKT_`).
> 2. Si no está en 2.2 → aplicar el baseline correspondiente a su bin D1 en la **Sub-tabla 2.1** (`MKT_`).
> Cero deducción, cero cálculo en runtime.

## 3. PROFESIÓN, POLARIDAD & SESGO MODAL DE TIMING
- Polaridad Funcional: NORMAL | INVERTED | TRANSITIONAL_MACRO.
  * Escribir explícitamente la regla de interpretación (ej. para BSI/CREDIT: Bin 0 = estrés/suelo/compra; para VIX: Bin 5 = pánico/suelo, Bin 0 = complacencia/deriva).
- Profesión de la Estación: Piso | Techo | Continuación | Acumulación | Distribución.
- Desglose de Geometría Temporal (Slots ZZ25):
  * Distribución de masa en porcentaje (%): t-2, t-1, t=0, t+1, t+2, ENTRE.
  * Slot Modal y Rol: Identificar en cuál slot se concentra la mayor masa de episodios:
    - Canario Anticipatorio (t-2 / t-1) [Lead-time 24h-48h]
    - Gatillo Síncrono (t=0) [Coincidencia temporal exacta]
    - Confirmador Rezagado (t+1 / t+2) [Reacción post-giro con bajo drawdown]
    - Proceso Lento / Runway (ENTRE) [Masa > 50%]
  * **Poder de Confirmación en Slot Modal:**
    $$P_{\text{confirmación}} = \% \text{ masa}_{\text{slot modal}} \times HR_{\text{en slot modal}}$$
  * **Diagnóstico Físico de Masa en ENTRE (§3 Documento de Diseño):**
    Evaluar qué significa la presencia fuera de rango:
    - Si HR en ENTRE es alto y con EV > 0 sostenido → CONTINUACIÓN CON FUERZA.
    - Si HR en ENTRE ≈ 50% y EV ≈ 0 → DESACUERDO / DESIDIA (estancamiento lateral).
    - Si HR en ENTRE tiene baja dispersión y avance gradual a > 15 barras → CANARIO DE PROCESO LENTO (acumulación/distribución sostenida).

## 4. ROL EN EL ÁRBOL (CAT1 / CAT2 / CAT3) Y CADENA CAUSAL
- Categoría y Lead-Time:
  * CAT1 (Economía, lead largo): CREDIT, YIELD_CURVE, DXY, ROTATION (Salida A).
  * CAT2 (Protección, lead medio): VIX, VVIX, PCR, SKEW.
  * CAT3 (Acción, lead corto): BSI, SV5_TURBULENCE, FG, ROTATION (Salida B).
- Cadena Causal:
  * ¿Qué indicador precursor previo debe vigilarse antes de confiar en esta estación?
  * ¿A qué indicador posterior valida o confirma la señal de esta estación?
- Casos Especiales de Arquitectura:
  * Si es ROTATION: Explicitar sus DOS salidas funcionales independientes (Salida A: macro/liquidez de capital vs Salida B: rotación sectorial cíclica/defensiva).
  * Si es FG: Declarar su inercia de 504 días (suavizado de 2 años) y su limitación a Large Caps (sin IWM).
- Reglas de Confluencia Causal:
  * Explicitar la conducta ante "Miedo sin Venta" (CAT2 en pánico pero CAT3 mantiene → SUB-REACCIÓN → ESPERAR).
  * Explicitar la conducta ante "Miedo con Venta" (CAT2 en pánico + CAT3 colapsado → CAPITULACIÓN → COMPRAR).

## 5. FIRMA MULTIESCALA ZZ25 / ZZ50 / ZZ75 (Puente al Régimen)
- Comportamiento Cross-Escala:
  * Convergencia Estructural (zz25, zz50, zz75 alineados con EV creciente a mayor plazo) → Sostiene Régimen de Mercado Duradero.
  * Divergencia Táctica (zz25 desacoplado de zz75, ej. rebote rápido en tendencia mayor bajista) → Oportunidad de Scalp / Pullback; PROHIBIDO posicionar a largo plazo.
- Filtro de Operabilidad y Estructura:
  * Ratio de Asimetría RR = MFE / |MAE| ≥ 1.0 (si RR < 1.0, celda clasificada como NO OPERABLE).
  * Break-of-Structure: Umbral MAE P95 que invalida la tesis operativa.

## 6. PERFIL DIMENSIONAL INTEGRADO (D1 Magnitud × D2 Velocidad Cinemática × D3 Volatilidad Interna)
- **Papel de D1 (Magnitud Estática):** Posicionamiento en percentiles gaussianos y colas σ.
- **Papel de D2 (Velocidad Cinemática 72h, Δ3d):** Inercia a corto plazo.
  * Catálogo de Singularidades Cinemáticas de la estación (ej. CREDIT D2=0 con HR=80% y PF=51.33; ROTATION D2=4 con HR=66.9%; VIX D1=5 con D2=4 falling knife vs D2=0 absorción).
- **Papel de D3 (Volatilidad Interna):** Amplificador no lineal en "U" (modula convicción y riesgo, NO dirección monótona).
  * **D3 = 0 (VOL_EXTREME_SQUEEZE):** Compresión extrema de volatilidad. Mecánica de resorte comprimido (*coiled spring*). Acumula energía elástica masiva; cuando una perturbación en D2 impacta, detona un **U-Turn violento** (giro en V o reversión instantánea con asimetría masiva; ej. BSI D3=0 con t=0 alcanza HR = 100%).
  * **D3 ∈ [1, 2]:** Régimen ordinario / inercial. Menor asimetría.
  * **D3 = 3 (VOL_EXPANSION):** Expansión de volatilidad en pleno desarrollo.
  * **D3 = 4 (VOL_PEAK_DECEL):** Clímax y agotamiento de la volatilidad. Absorción institucional que frena el movimiento y constituye el segundo punto focal de **U-Turns** por agotamiento.

## 7. CONTRASTE DE LA PROSA Y EL VERBO (Mitos Narrativos vs Comportamiento Cuantitativo)
Evaluación formal y obligatoria de cada bin notable bajo 4 arquetipos:
1. **Coherente:** La narrativa financiera común y la evidencia empírica coinciden (ej. pánico extremo en VIX D1=5 que genera rebotes alcistas; capitulación en BSI D1=0).
2. **Contrarian:** La señal opera exactamente al revés del titular del periódico (ej. FG D1=0 pánico extremo compra con 67.4% WR).
3. **Trampa Narrativa:** La creencia popular destruye valor al invitar a operar en la dirección contraria a la física del mercado (ej. Shortear VIX en D1=0 por "complacencia" o vender euforia en FG D1=5).
4. **Motor de Deriva:** Estados que no marcan techos ni pisos, sino que alimentan una tendencia sostenida dentro de ENTRE (ej. VIX D1=0 con HR=82.8% y EV=+3.76%).
*Desmontar explícitamente los mitos más comunes de la estación.*

## 8. GOBIERNO DE N, PROTOCOLO DIAMANTE (§3.3) Y GESTIÓN DE OVERFLOWS / BLOWOFFS

### 8.1 Protocolo Diamante (§3.3) — Rareza con Significado y Disrupciones Históricas
- Muestras con N < 10 o N < 21 con asimetría o edge comprobado: Reportar fechas históricas reales (1998, 2000, 2008, 2011, 2018, 2020, 2022).
- Reporte honesto: aciertos empíricos k/n, intervalo de Wilson 95%, rango MFE/MAE.
- **Prohibición de Censura:** Prohibido descartar o silenciar muestras raras como "ruido". En escalas gaussianas sobre 33 años, las colas de ±2σ ocurren exactamente con la frecuencia teórica esperada (~2.28%).

### 8.2 Caracterización Forense de Overflows (±3σ) y Blowoffs (>5σ)
- Frecuencia histórica y dimensiones afectadas (D1, D2, D3) según el bloque `overflows` del timing fact store (`n_episodios_tier_gte_1`, `pct_episodios_overflow`, `max_tier_d1/d2/d3`).
- Clasificación bajo la escala estandarizada de 5 Tiers (`sigma_overflow.py`):
  * Tier 1 (3σ - 4σ): OVERFLOW_MODERADO (WARNING)
  * Tier 2 (4σ - 5σ): OVERFLOW_EXTREMO (CRITICAL)
  * Tier 3 (5σ - 7σ): BLOW_OFF_SEVERE (EMERGENCY)
  * Tier 4 (7σ - 10σ): BLOW_OFF_EXTREME (CATASTROPHIC)
  * Tier 5 (≥ 10σ): BLOW_OFF_SYSTEMIC (SYSTEMIC)
- Física del desbordamiento en los activos subyacentes cuando esta estación entra en overflow.

### 8.3 Protocolo de Escalación y Contrato con SIGMET (El Puente Operativo Bidireccional)
- **Umbrales Cuantitativos de Escalación:**
  * Alerta Amarilla (WARNING): Tier 1 (3σ - 4σ).
  * Alerta Roja (CRITICAL / EMERGENCY): Tier ≥ 2 (≥ 4σ) o detección de estado Diamante disruptivo.
- **Doble Naturaleza Operativa (Riesgo vs Oportunidad Generacional):**
  * **Fase de Impacto Cinético / Shock Inicial (D2 expansivo / falling knife):** La estación ordena a SIGMET emitir boletín con directiva de preservación de capital: `MKT_BLOCK_CRISIS` o `MKT_MACRO_CIRCUIT_BREAKER`.
  * **Fase de Clímax, Capitulación Extrema o Absorción Institucional:** Un overflow extremo post-clímax o una señal Diamante en suelo de pánico NO es un bloqueo permanente, sino **LA GRAN OPORTUNIDAD DE COMPRA GENERACIONAL** → La estación ordena a SIGMET emitir directiva de acumulación agresiva: `MKT_BUY_DIP_TACTICAL` o `MKT_ACCUMULATE_STRUCTURAL`.
- **Criterio de Desactivación:** Descompresión sostenida a < 3σ durante N barras consecutivas.

## 9. TOP TRÍADAS OPERATIVAS Y SINGULARIDADES
- Ranking de las 5 mejores tríadas alcistas (piso/rebote) y las 5 mejores bajistas (techo/defensiva):
  * `state_key`, HR %, Edge neto %, RR, N, p-value, Wilson 95% CI.
  * Fase del ciclo y acción canónica de mercado (`MKT_`) ya precalculada.
```

---

## Reglas de Validación (Obligatorias para el Generador)

1. **Dato mata relato:** Cada número debe derivarse exclusivamente de las fuentes oficiales (1-9). Citar la fuente y escala correspondiente.
2. **Cero derivación en el agente:** Toda directiva, fase y acción canónica debe estar resuelta en las tablas. Un agente no calcula polaridades en runtime.
3. **Cero inventos de labels:** Copiar los labels D1 textualmente de `d1_labels_canonical.md`.
4. **Ámbito de Mercado Obligatorio (MKT_):** En Capa 1 las directivas pertenecen exclusivamente al ámbito `MKT_`. **PROHIBIDO usar prefijo `STK_`**.
5. **Tiers de Credibilidad de Opus (σ×N):** Clasificar obligatoriamente en `DIAMOND` ($N < 10$), `UNUSUAL_COMBO` ($N \in [10..29]$), `CONFIRMED_ALERT` ($N \ge 30$ alerta/extremo) o `WEATHER` ($N \ge 30$ central). **PROHIBIDO usar `ANECDOTAL`, `LOW`, `MODERATE`, `HIGH`, `ROBUST`**.
6. **Poder de confirmación acoplado:** No reportar Rng% aislado sin calcular el slot modal y su $P_{\text{confirmación}} = \% \text{ masa}_{\text{modal}} \times HR_{\text{modal}}$.
7. **D3 como amplificador en U:** Explicar el Squeeze en D3=0 como acumulador elástico para U-Turns y D3=4 como agotamiento.
8. **Mitos vs Cuantitativo:** Completar la Sección 7 desmontando falsas narrativas bajo los 4 arquetipos.
9. **Bidireccionalidad de Overflows y SIGMET:** El protocolo de escalación en la Sección 8.3 debe contemplar tanto el veto de riesgo inicial (`MKT_BLOCK_CRISIS`) como la oportunidad de compra generacional (`MKT_BUY_DIP_TACTICAL` / `MKT_ACCUMULATE_STRUCTURAL`).
10. **Gobierno de N honesto (§3.3):** Reportar ocurrencias reales $k/n$, fechas y Wilson CI para $N < 10$. Nunca descartar colas como ruido.

---

## Verificación de Aceptación (Checklist para Hermes)

- [ ] Existen 11 fichas (una por estación) en `.hermes/dossiers/capa1_personalidades/{station}_personalidad.md`.
- [ ] Cada ficha contiene las 9 secciones canónicas completas.
- [ ] La Sección 2 implementa la arquitectura de 2 niveles (2.1 Baseline D1, 2.2 Tríadas de Excepción).
- [ ] La Sección 3 reporta el Poder de Confirmación en Slot y diagnostica la masa en `ENTRE`.
- [ ] La Sección 6 detalla la física del Squeeze en D3 y su relación con los U-Turns.
- [ ] La Sección 7 clasifica formalmente los mitos bajo los 4 arquetipos (Coherente, Contrarian, Trampa Narrativa, Motor de Deriva).
- [ ] La Sección 8 implementa las 3 subsecciones: 8.1 Protocolo Diamante, 8.2 Caracterización Forense de Overflows/Blowoffs, 8.3 Contrato SIGMET Bidireccional (Bloqueo vs Compra Generacional).
- [ ] Todas las polaridades y labels cruzan 100% contra los Fact Stores y referencias canónicas.