# ESPECIFICACIÓN DEL SISTEMA — Régimen + Bitácora + Evaluador + Aprendiz

> Estado: ESPECIFICACIÓN CONSOLIDADA. Juan Andrés + Hermes, 17-Ago-2026.
> Propósito: artefacto ÚNICO, completo y autocontenido. Todo agente futuro recibe
> ESTE documento, no un fragmento. Lección: el error de diseño grave fue despachar
> agentes sin una spec congelada — cada uno recibió (o inventó) un fragmento.

---

## 0. LECCIÓN APRENDIDA (no repetir)

```
ERROR: despachar agentes con definiciones ad-hoc (retornos crudos, cascade bear
invertido, sin D2 flip, sin tríada) en vez de las definiciones YA concluidas.
CAUSA: el diseño no estaba congelado en UN artefacto. Cada agente recibió un fragmento.
REGLA: NINGÚN agente se despacha antes de que esta spec esté cerrada y referenciada.
       El outcome de TODO agente es la TRÍADA ZIGZAG, nunca retornos crudos.
```

---

## 1. ARQUITECTURA CONCEPTUAL (metáfora meteorológica)

```
El piloto primero determina la ESTACIÓN (régimen), luego consulta el CLIMA.

ESTACIÓN = RÉGIMEN (contexto)     → el árbol de decisión (sección 3)
CLIMA    = condiciones actuales    → METAR + SIGMET + TAF

RÉGIMEN  = el ESTADO (¿dónde estoy?)
EVENTO   = la TRANSICIÓN (¿qué pasa de repente?)  → cisne negro/blanco/trampa

Dos capas distintas que se cruzan. El régimen es el estado, el evento es la disrupción.
```

---

## 2. CLASIFICACIÓN POR NATURALEZA (las 3 categorías, por lead-time)

```
CAT 1 — ECONOMÍA (lead MÁS LARGO, generan tendencias):
  CREDIT (HYG/LQD), YIELD_CURVE (10Y-3M), DXY, ROTATION-A (flujos USA)
  → ¿expansión o contracción? (salud económica 0-100%)

CAT 2 — SENTIMIENTO/PROTECCIÓN (lead MEDIO, se cubren primero):
  VIX, VVIX, PCR, SKEW
  → ¿bochorno o seco? (protección 0-100%)

CAT 3 — ACCIÓN (lead MÁS CORTO, la confirmación real):
  BSI (S5TW), SV5T, FG, ROTATION-B (liderazgo sectorial)
  → ¿llueve o aún no? (amplitud 0-100%)

ROTATION es DUAL: salida A (CAT1, flujos) + salida B (CAT3, liderazgo).

CADENA CAUSAL: ECONOMÍA(1) → PROTECCIÓN(2) → ACCIÓN(3)
  economía se deteriora → institucionales compran puts (protección) →
  el mercado AÚN no vendió (S5 mantiene) → recién después S5 COLAPSA (venta).
```

---

## 3. ÁRBOL DE DECISIÓN DE REGÍMENES (5 niveles)

```
NIVEL 1 — MACRO CLIMA (CAT 1): ¿EXPANSIÓN o CONTRACCIÓN? = "¿verano o invierno?"
  → CREDIT spreads, YIELD curve, DXY, ROTATION-A

NIVEL 2 — LIQUIDEZ (CAT 1 granular): ¿FLUYE o se CONTRAE? = "¿húmeda o seca?"
  → CREDIT tightening/widening, YIELD steepening/inverting

NIVEL 3 — SENTIMIENTO/PROTECCIÓN (CAT 2): ¿hay bochorno? = "¿sube la humedad?"
  → VIX, VVIX, PCR, SKEW

NIVEL 4 — ACCIÓN (CAT 3): ¿YA actuó? = "¿llueve ya, o aún no?"
  → BSI/S5TW, SV5T, FG

NIVEL 5 — RÉGIMEN EXACTO (la hoja): combinación + señales + probabilidad
```

---

## 4. LAS HOJAS (regímenes ya poblados — GRADE A)

```
INVIERNO → liquidez tight → bochorno → AÚN NO llueve = SUB-REACCIÓN → ESPERAR
INVIERNO → liquidez tight → bochorno → YA llovió      = CAPITULACIÓN → COMPRAR
INVIERNO → liquidez tight → bochorno EXTREMO (VIX↑+SKEW↑) = PÁNICO TOTAL → COMPRAR (PF 8.09)
VERANO   → liquidez fluye → seco → máximos             = EUFORIA → TECHO (vender)
VERANO   → liquidez fluye → seco → normal              = TENDENCIA SANA → CONTINUAR (cascade)
CUALQUIER clima → CAT 3 lidera (acción antes que sentimiento) = RÉGIMEN EXPLOSIVO → colas gordas
```

Regla de oro por hoja: señales + probabilidad + CI95 + N (nunca binario).

---

## 5. EVENTOS ESPECIALES (2ª capa — la transición, no el estado)

```
CISNE NEGRO: impredecible (2008 Lehman, 2020 COVID)
  → detección solo POST-hoc, SIGMET inmediato (no anticipado)
  → régimen: típicamente EXPLOSIVO o en transición

CISNE BLANCO: previsible (flaggeado antes)
  → detección ANTICIPADA (bochorno extremo que SÍ terminó en tormenta)
  → régimen: SUB_REACCION → CAPITULACION (transición gradual)

TRAMPA: falsa señal (rebote táctico en tendencia mayor)
  → BULL_TRAP (zz25 rebote dentro de zz75 bajista)
  → BEAR_TRAP (zz25 caída dentro de zz75 alcista)
  → detección: CONTEXTO multi-escala (¿este zz25 está en qué zz75?)
```

INVENTARIO COMPLETO en `.hermes/plans/inventario_eventos_especiales.md`:
- Estructurales (5 permutaciones CAT), Empíricos METAR (7), Rotación (7), uso común (mapeo).

---

## 6. DISTINCIÓN CRÍTICA: FASE ≠ DIRECCIÓN

```
El clasificador de regímenes (el árbol) detecta FASE (pre-pivote), NO dirección.
Secuencia CAT1→CAT2→CAT3 = detector de FASE, MIN/MAX ~50/50.

DIRECCIÓN la da cascade_conviction (independiente): w_bear=0.66/w_dom=0.34,
Grupo A vota (VIX, BSI, FG, Credit, Rotation), IC +0.41, PBO=0%.

DECISIÓN DE TRADING = RÉGIMEN (fase) + DIRECCIÓN (cascade) + PRONÓSTICO (tríada).
Nunca confundir: el árbol dice DÓNDE estás, el cascade dice HACIA DÓNDE.
```

---

## 7. LA TRÍADA ZIGZAG (el outcome de TODO)

```
El cascade es binario (¿llega al 5%?) = la COLA de la distribución.
La tríada zigzag del fact store es la DISTRIBUCIÓN COMPLETA, por escala zz25/50/75:
  p_bull/p_bear, ev_per_day/ev_net, ftt_bull_days/ftt_bear_days/e_days,
  e_ret_max/e_ret_min, rr_asymmetry

→ medir SIEMPRE contra la tríada, NUNCA contra retornos crudos ni cascade solo.
→ la tríada YA ES el triple barrier de López de Prado (profit/target=escala,
  tiempo=ftt/e_days, stop=drawdown del evaluador).
```

---

## 8. BITÁCORA — esquema de campos

Dos capas:
- CAPA 1 — SERIE DE ESTADO: cada CAMBIO significativo del vector (D2 flip, D1
  transición, σ-overflow, cascade cruza umbral). Registra timestamp + qué cambió.
- CAPA 2 — REGISTRO DE DECISIONES: ENTRADA/SALIDA/TAMAÑO, referenciando la capa 1.

Campos por barra de decisión:

```
IDENTIDAD: bar_id, timestamp, pivot_date, episode_id, era, pivot_type

RÉGIMEN (vectorial por escala): regimen_zz25/50/75 (TREND/MEAN_REVERSION/INDEF),
  secuencia_CAT, discriminador (qué disonancia gobierna)

VECTOR DE ESTADO (11 estaciones × D1×D2×D3):
  {st}_state_key, {st}_d1, {st}_d2_sign, {st}_d3,
  {st}_zk_pbull, {st}_ev_per_day, {st}_ftt_bull, {st}_ftt_bear,
  {st}_rr_asymmetry, {st}_n (credibilidad), {st}_sigma_depth (rareza)

DISPERSIÓN: dispersion_global, dispersion_grupoA/B, discriminador, pares_disonantes

DIRECCIÓN: cascade_conviction_25/50/75, d1_bear_5

RIESGO/BENEFICIO: rr_esperado, ev_esperado, sigma_overflow_flags

DECISIÓN: decision_zz25/50/75 (ENTRY_LONG/SHORT/NO_ENTRY), size_pct, rationale

RESULTADO (post-hoc, evaluador): por escala — anticip_barras, dd_punteria,
  dd_mercado, retorno_real, llego_a_target, salio_temprano, rr_realizado, gap_rr,
  capture_ratio

OMISIÓN: tramo_no_operado, acierto_omision (evitó pérdida), oportunidad_perdida

EVENTO (transición): cisne_negro/blanco/trampa detectado, tipo, impacto

META: regime_label (ground truth), dsr_grade, decay_check
```

---

## 9. EVALUADOR — medidas post-hoc

```
ENTRADA: anticip_barras, dentro_banda (±3 barras), dd_punteria, dd_mercado
SALIDA:  holding_period_real, salio_temprano (vs regla), retorno_dejado,
         dd_por_no_salir, capture_ratio por escala
OMISIÓN: tramo no operado (falso negativo)

La salida perfecta de cada escala = el fin de la pierna (post-hoc, inalcanzable en vivo).
El aprendiz optimiza capture DENTRO de banda (≥0.7), no persigue la perfección.
```

---

## 10. APRENDIZ (compositor de tríadas)

```
Función objetivo: MAXIMIZAR el spread — ganar lo MÁS (p_win×avg_win) y perder lo
MENOS (p_loss×|avg_loss|). Ambos lados de la ecuación, no uno solo.

El aprendiz ES el compositor: agrega 11 tríadas en 1 señal, ponderadas por
credibilidad (N, CI95, DSR). No existe aún — es el gap central a construir.

Herramientas López de Prado:
  Triple Barrier (ya en la tríada), Meta-labeling (afinar puntería),
  PBO + Deflated Sharpe (gates), Structural breaks/CUSUM ("olvidar"),
  Walk-forward con purging+embargo (overlap temporal de pivotes),
  EVT + shrinkage (rareza = riqueza, tratar como evento no media).
```

---

## 11. REGLAS OPERATIVAS

```
1. No usar stops de PRECIO — stop de SEÑAL (el vector de estado dice "peligro").
   Las señales raras de peligro (σ-overflow, D3<0.5 pre-extreme, cuchillo) son la
   ÚNICA defensa contra la cola izquierda. Validar contra wipeouts >20%.
2. R:R mínimo 2:1; mandato del sistema 5:1 (asimetría del cascade).
   EV = |loss| × (p_bull × R:R − p_bear). R:R sin probabilidad no decide.
3. Timing perfecto es imposible; timing ADECUADO es la banda. Riesgo es lo que se
   administra, retorno lo da el mercado.
4. Dato mata relato: toda conclusión con N + CI95 + wins/losses separados.
5. Rareza (N bajo) = riqueza, no ruido. Tratar como EVENTO (shrinkage+EVT), no media.
6. Las validaciones de agentes despachados SIN esta spec NO se consideran.
   Solo lo verificado fácticamente contra datos.
```

---

## 12. PENDIENTES

```
1. Construir el clasificador de regímenes (árbol → hoja) — fase, no dirección.
2. Definir operativamente cisne blanco y trampa (SIGMET, tienen capa pero no umbral).
3. Medir la confluencia de zigzags (3 escalas alineadas = evento de máxima significancia).
4. Componer el catálogo de eventos con credibilidad (N, CI95, PF) por evento.
5. Construir la bitácora (Parquet, capa estado + capa decisiones).
6. Regenerar quants_obs.pkl (SKEW mismatch: 6 state_keys obsoletos → 17 NaN).
7. Regenerar fact stores con SKEW post-2011 (verificado: datos CBOE directos).
8. Componer el compositor de tríadas (aprendiz) — el gap central.
```

---

## 13. HALLAZGOS VALIDADOS OOS (ancla, no reinventar)

```
- Dispersión entre estaciones (std zk_pbull): SOBREVIVE OOS, 10/10 folds.
  CONSENSO → cascade_50 61.7% vs FRAGMENTACIÓN 36.1% (Δ -0.256, CI95 no overlap).
  Spearman ρ=-0.175 (p<1e-8). Escala dominante zz25.
- GAP DE COHERENCIA: el fact store sobre-estima ev_per_day bajo fragmentación
  (+0.148 esperado) pero la realización NO lo confirma → sesgo a corregir.
- Fragmentación → piernas más LARGAS (6.2→10.8 bars) y movimientos choppy.
```
