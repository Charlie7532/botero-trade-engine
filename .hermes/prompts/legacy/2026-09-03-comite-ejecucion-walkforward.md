# PROMPT DE EJECUCIÓN: Comité Walk-Forward METAR — Forensia Integral (v2)

**Motivo:** Especificación ejecutable del comité de 11 agentes LLM (estaciones) + curador, que simulan operar EN VIVO vela a vela sobre el SPY, validan/invalidan reglas, hacen forensia, analizan confluencias y señales escasas, confrontan modelos. **"La verdad habla."**

**Decisiones cerradas:**
- **Arquitectura:** B (todo-agentes LLM con personalidad). Observar (benchmark) separado de aprender (modelador).
- **Walk-forward:** por EPISODIOS/PIVOTES (no cada vela) — los agentes LLM interpretan en los puntos de decisión; el cómputo de estado/first-passage es determinista entre puntos.
- **Ancla del veredicto: OPCIÓN D** — cada estación se evalúa contra el ancla que responde a su rol (precursor→pivote, contexto→régimen/eventos, confirmador→continuación).

---

## PARTE 0 — EL MAPA DE MUNDOS (personalidad + propósito + rol por estación)

Cada agente está inmerso en SU mundo. La tabla define su rol conceptual (el que el curador usa para pesarlo y validarlo):

| Estación | Mundo | Rol | Ancla de validación (D) |
|:---------|:------|:----|:------------------------|
| **VIX** | Volatilidad implícita / miedo | **Precursor** de giro | Anticipa pivote (techo/suelo) |
| **VVIX** | Volatilidad de la volatilidad | Precursor (turbulencia) | Anticipa pivote |
| **PCR** | Posicionamiento put/call | Precursor (cobertura) | Anticipa pivote |
| **FG** | Sentimiento extremo (fear/greed) | Exageración (fat-tail) | Anticipa giro + eventos extremos |
| **SV5_Turb** | Turbulencia de mercado | **Régimen** de fondo | Cambio de régimen / quietud-estallido |
| **SKEW** | Riesgo de cola | Precursor (eventos extremos) | Anticipa eventos de cola |
| **CREDIT** | Apetito de riesgo | **Contexto** | Régimen / dirección del flujo |
| **YIELD_CURVE** | Espera de ciclo (curva) | **Régimen** de fondo | Recesión/expansión (meses) |
| **ROTATION** | Rotación sectorial | Régimen/contexto | Defensivo vs cíclico |
| **DXY** | Dólar / liquidez | **Contexto** | Dirección del flujo global |
| **BSI** | Amplitud (breadth) | **Confirmador** | Continuación de la salud del movimiento |

**Ancla D en operación:** cuando el curador evalúa el desempeño del agente VIX, lo mide por "¿anticipó el pivote?"; al agente YIELD por "¿registró el régimen de recesión?"; al BSI por "¿confirmó la salud del rally?" — cada uno contra lo que su mundo responde.

---

## PARTE 1 — WALK-FORWARD (el núcleo)

### Algoritmo (por episodio/pivote, simulación en vivo)

```
t = primera vela válida del lake (1993)
for cada episodio/pivote del recorrido (ascendente por fecha):
   1. LOS 11 AGENTES LEEN SOLO datos ≤ t (sin lookahead)
      - si su estación ya maduró (inception) → interpretan su D1×D2×D3
      - si no maduró → "datos no maduros, no opino" (se excluye, se registra)
   2. CADA AGENTE emite su interpretación semántica en el idioma de su mundo:
      { estación, D1,D2,D3, firma_estado, posicion_en_giro, huella_multiEscala,
        impact_ratio, tier §3.3, n_indep, ci95, voto_direccional {long,short},
        alerta_semantica: "<texto en su idioma>" }
   3. EL CURADOR fusiona los agentes que opinan:
      - pondera por N_indep (ROBUST pesa más, LOW aporta su evidencia)
      - detecta confluencia canaria (≥2 estaciones independientes → mismo estado/giró)
      - detecta CONFLICTO entre mundos (reporta "desacuerdo" como estado en sí)
      - emite: condicion_mercado, forecast P(giro), alertas METAR/TAF/SIGMET/NOTAM
   4. REGISTRO del desenlace real de t+k (el futuro que llegó):
      - para el ancla D del rol de cada estación
      - acierto/error por agente, por regla
   5. ACUMULACIÓN: cada regla/interpretación acumula su score de acierto/error
   t → siguiente episodio
```

### Reglas duras del walk-forward
- **Sin lookahead:** en `t` nadie usa datos post-`t`. El pivote se detecta por confirmación de pierna, no ex-post.
- **Inception respetado:** agente madura cuando su estación tiene datos (VIX 1993, VVIX/PCR 2006, CREDIT 2007, FG 2011, SV5_Turb 1999, etc.).
- **Emisión obligatoria:** cada agente opinativo emite en cada episodio (incl. "aleatoria/no-patrón con CI95"), nunca se calla.
- **Rareza ≠ exclusión:** un estado escaso (N_indep≤5, tier LOW) con patrón se conserva, se etiqueta como hipótesis con su rareza %, se estudia.

---

## PARTE 2 — OUTPUTS DEL COMITÉ (los 5 objetivos)

| Salida | Objetivo que cumple |
|:-------|:--------------------|
| `registro_forense.json` | Forensia completa: cada disparo + desenlace real + acierto/error |
| `reglas_validadas.json` | Reglas que SOBREVIVIERON al walk-forward (desempeño OOS + N_indep + CI95) |
| `reglas_invalidadas.json` | Reglas que el tiempo DESCARTÓ (y por qué, con el score) |
| `señales_disculiertas.json` | Estados/señales NUEVAS que el comité descubrió y que las reglas previas no capturaban |
| `confluencias_canarias.json` | Pares/tríadas de estaciones que anticipan giros (lift sobre base-rate, CI95 excluye nulo) |
| `señales_escasas_significado.json` | Cada señal rara estudiada: significado, rareza %, team §3.3, desenlaces en vivo |
| `modelo_confluencia.json` | **El modelo que opera**: pesos calibrados OOS + validación por episodio (2000/2008/2011/2020/2022) |

### Registro forense (estructura por vela)
```
{ vela: t, fecha,
  agente_vix: {...interpretación...}, agente_yield: {...}, ...,  (los que maduraron)
  curador: { condicion: <miedo|euforia|acumulación|distribución|continuación|desacuerdo|neutral>,
             p_giro: [lo, hi], n_confluentes: N,
             alertas: [ {tipo:METAR|TAF|SIGMET|NOTAM, msg, atribuciones} ] },
  desenlace: { pivote_real?: MAX/MIN, next_leg_direc: ±, evento?: "", rr: x },
  acierto: { vix: bool, yield: bool, ... }   # contra el ancla D de cada rol
}
```

---

## PARTE 3 — CÓMO SE CONFRONTAN LOS MODELOS ("la verdad habla")

1. **Confrontación entre estaciones:** comparar los scores de acierto de cada agente por su ancla → ranking de ¿cuál mundo es verdaderamente canario? (≥5 hits OOS con lift contra el nulo).
2. **Confrontación entre combinaciones:** el curador prueba distintas tríadas de mundos (e.g. VIX+YIELD+BSI) y verifica cuál predice mejor OOS. La que gana → `modelo_confluencia.json`.
3. **Confrontación contra el mercado:** ningún modelo se acepta por narrativa — solo si su forecast OOS supera el baseline de pivotes (con CI95 excluyendo el nulo).
4. **La verdad habla:** toda regla que no supere el walk-forward se invalida, sin importar cuánto "significó" in-sample.

---

## PARTE 4 — IMPLEMENTACIÓN PRÁCTICA (para Hermes)

**Por qué no 93,000 llamadas LLM:** los agentes LLM solo invocan en los **episodios/pivotes de decisión** (los ~1,590 pivotes del lake + transiciones de estado), no en las 8,453 velas. Entre puntos, el cómputo de estado/first-passage es determinista (script). Esto reduce a un número manejable de interpretaciones por agente.

**Estructura de carpetas:**
```
comite_metar/
├── perfiles/          # perfil de cada estación (mundo, rol, ancla, idioma, inception)
├── scripts/           # cómputo determinista de estado/first-passage/episodios
├── agentes/           # los 11 agentes LLM (cada uno invoca con su perfil)
├── curador/           # fusión + confluencia + confrontation
├── salidas/           # los 8 JSON de salida
└── README.md          # cómo se corre
```

**Flujo de ejecución:**
1. Generar episodios/pivotes (determinista)
2. Para cada episodio: invocar los 11 agentes LLM (solo los maduros) → interpretación
3. Curador fusiona + registra desenlace + puntúa
4. Modelador aprende OOS + confronta modelos
5. Verificación: N honesto, contra el nulo, OOS, ex-ante

---

## PARTE 5 — VERIFICACIÓN DE LA VERDAD (blindaje del comité anterior)

1. **N honesto:** toda métrica usa N_indep (nunca N≤13 como verdad sin CI95).
2. **Contra el nulo:** un "canario" solo es tal si el CI95 de lift excluye la base-rate de pivotes (bootstrap de permutación).
3. **OOS por episodio:** validar en 2000, 2008, 2011, 2020, 2022 (separados). Si el patrón solo se repite en los mismos pánicos, es memoria de muestra.
4. **Ex-ante:** la métrica posicional nunca usa el pivote futuro.
5. **Dato mata relato:** toda alerta es reproducible desde los parquets, con atribución a N_indep + CI95 + estaciones + escalas.
6. **No redes profundas sobre 37 señales:** la fusión es evidencial/bayesiana (Dempster-Shafer / soft-vote ponderado), no MLP sobre pocas filas.

---

## ENTREGABLE FINAL
Un sistema de **forecast y alertas operativo en vivo**, calibrado y validado OOS, que:
- usa cada estación según su rol (precursor/contexto/confirmador/régimen),
- fusiona confluencias con pesos aprendidos del walk-forward,
- emite condición de mercado + P(giro) + alertas METAR/TAF/SIGMET/NOTAM con atribución,
- conserva y estudia las señales escasas (§3.3),
- y cuyas reglas fueron VALIDADAS O INVALIDADAS por la verdad del mercado.