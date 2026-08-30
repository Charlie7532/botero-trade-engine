# SCANNER SISTEMÁTICO DE ESTACIONES — DISEÑO COMPLETO v2

> Estado: DISEÑO. Incorpora feedback de Juan Andrés, 17-Ago-2026.
> Objetivo: scanner probabilístico que determine regímenes de mercado,
> eventos especiales, retardos de señales, interpretación de data huérfana,
> y complemente cascade con señales aún no integradas.

---

## 1. PROPÓSITO AMPLIADO

El scanner NO es un "correlacionador de números". ES un sistema de diagnóstico
que entiende QUÉ mide cada indicador (su significado económico) y responde:

### 1.1 Preguntas fundamentales
- ¿En qué RÉGIMEN está el mercado? (crisis / calma / tendencia / transición)
- ¿Qué indicadores CONFIRMAN este régimen y cuáles lo CONTRADICEN?
- ¿Hay un EVENTO ESPECIAL en formación? (pánico, euforia, capitulación)
- ¿Las señales ANTICIPAN (pre-zigzag) o CONFIRMAN (post-zigzag)?
- ¿Qué señales COMPLEMENTAN lo que cascade no captura?
- Para data huérfana (N<10): ¿qué dice el vector D1×D2×D3 completo?

### 1.2 Cada hallazgo con grado de certeza
```
GRADE A: CI95 tight, N≥30, OOS validado → operar con confianza
GRADE B: CI95 amplio pero excluye 0, N≥10 → operar con sizing reducido
GRADE C: CI95 cruza 0, N<10 → investigar, no operar
```

---

## 2. QUÉ ENTIENDE EL SCANNER (contexto que debe CARGAR antes de medir)

### 2.1 El significado de cada indicador (NO solo el número)
```
VIX   = miedo a volatilidad — precio del seguro, NO direccional
SKEW  = miedo de cola — costo de puts OTM, institucional, ortogonal a VIX
PCR   = posicionamiento en opciones — AMBOS lados (put panic = piso, call heavy = techo)
FG    = sentimiento suavizado 504d — EXTREME_FEAR + D3 comprimido = entry seguro
BSI   = amplitud de PRECIO (% stocks sobre MA20) — participación real
SV5T  = amplitud de VOLUMEN — batalla, dirless, confirmador
CREDIT= salud del crédito corporativo — HYG/LQD spread
YIELD = salud del ciclo macro — 10Y-3M
DXY   = salud del dólar — flujos internacionales
ROTATION = DUAL: dinero entra/sale USA (economía) + defensivo↔cíclico (protección)
VVIX  = estabilidad del miedo — vol del VIX
```

### 2.2 Las 3 escalas zigzag y su significado
```
zz25 (2.5%) = REVERSIÓN TÁCTICA — "el mercado giró 2.5%"
zz50 (5%)   = SWING OPERACIONAL — "el mercado giró 5%"
zz75 (7.5%) = TENDENCIA ESTRATÉGICA — "el mercado giró 7.5%"

Cascade: zz25→zz50 (40.7%), zz25→zz75 (19.1%), zz50→zz75 (47.7%)
```

### 2.3 Hallazgos confirmados (conocimiento previo)
```
GRADE A (alta certeza):
  - PÁNICO TOTAL (VIX↑+SKEW↑): PF 8.09, 0 wipeouts, 82% win 60d — señal más fuerte
  - Cascade_conviction: IC +0.41, PBO 0%, w_bear=0.66 — NO se toca
  - "Vender euforia es mito": FG EXTREME_GREED es positivo → refutado
  - D2 predice DIRECCIÓN, NO cascade (ρ≈0 cascade, ρ≈0.40 dirección)
  - D3 discrimina CASCADE, NO dirección (FG -17pp, VVIX -9pp, BSI -7pp)
  - MIEDO SIN VENTA = sub-reacción (VIX↑ + S5 mantiene → NO comprar)
  - EXTREME_FEAR + D3 comprimido: FG entry más seguro (CI95 tight, 0 wipeouts)

GRADE B (confirmado, necesita más N):
  - SKEW como confirmador de naturaleza del miedo (cola vs volatilidad)
  - PCR como ENTRY (put panic +2.26%, gate N≥10)
  - DXY EXTREME_STRENGTH = bearish (-1.94%)
  - YIELD EXTREME_STEEPNING = EXIT
  - Conjunciones rara vez suman (VVIX solo basta al cluster MIEDO)

GRADE C (preliminar, investigar):
  - Orphan Interpreter (árbol D3 discrimina, D2 gatilla)
  - PCR lado alcista (call heavy = techo)
  - Regímenes de mercado (clasificación automática)
```

### 2.4 Data huérfana (N<10) — el Orphan Interpreter
```
NO ignorar. Interpretar con vector D1×D2×D3 completo.
Regla (pitfall #55):
  D3 CONTRACCIÓN + D2 ACELERANDO → 76% bull → ENTRAR
  D3 CONTRACCIÓN + D2 DESACELERANDO → 38% bull → SALIR
  D3 NO CONTRACCIÓN → ~58% → NO OPERAR (moneda al aire)
```

---

## 3. METODOLOGÍA — PRE/POST ZIGZAG (retardos)

### 3.1 Marco temporal alrededor del pivote
```
Para CADA pivote zz25 (MIN=compra, MAX=venta):
  T-20 T-10 T-5 T-3 T-2 T-1 [PIVOTE] T+1 T+2 T+3 T+5 T+10 T+20

Medir CADA estación en cada punto T:
  - D1 (nivel), D2 (velocidad), D3 (volatilidad)
  - ¿El indicador ANTICIPA el pivote (señal antes)? → LEAD
  - ¿El indicador CONFIRMA el pivote (señal después)? → LAG
  - ¿Cuál es el retardo típico? (mediana de T_señal − T_pivote)
```

### 3.2 Clasificación de timing por estación
```
LEAD (anticipa):   señal antes del pivote → early warning
COINCIDENTE:       señal en o cerca del pivote → confirmación inmediata
LAG (confirma):    señal después del pivote → confirmación tardía
```

---

## 4. REGÍMENES DE MERCADO Y EVENTOS ESPECIALES

### 4.1 Clasificación de regímenes (automática)
```
CRISIS:      VIX>P80, cascade>60%, 3+ estaciones en D1 extremo
TENDENCIA:   cascade 40-60%, amplitud confirmando (BSI direccional)
CALMA:       VIX<P20, cascade<35%, sin estaciones en extremo
TRANSICIÓN:  D2 acelerando en 3+ estaciones, D3 contrayéndose
```

### 4.2 Eventos especiales
```
PÁNICO TOTAL:         VIX↑ + SKEW↑ simultáneo (0.8% días) → +6.81% 60d
CAPITULACIÓN:         VIX↑ + S5 colapsó → comprar (MIEDO CON VENTA)
SUB-REACCIÓN:         VIX↑ + S5 mantiene → esperar (MIEDO SIN VENTA)
EUFORIA REAL:         VIX↓ + S5 en máximos → techo
PRE-TORMENTA:         D2 acelerando + D3<0.5 → peligro (pitfall #65)
```

---

## 5. COMPLEMENTAR CASCADE

El cascade (D1 vote + domino) tiene IC +0.41 pero es INCOMPLETO:
- NO usa D2 (dirección)
- NO usa D3 (confianza)
- NO usa las relaciones cross-station
- NO captura eventos raros (PÁNICO TOTAL, N<10)

### 5.1 Lo que el scanner debe encontrar para complementar cascade
```
1. Señales de DIRECCIÓN (D2): ¿el movimiento es alcista o bajista?
   → cascade dice "va a continuar", dirección dice "hacia dónde"

2. Señales de CONFIANZA (D3): ¿la señal es confiable?
   → D3 comprimido = alta confianza, D3 caos = baja confianza

3. Señales de RÉGIMEN: ¿estamos en crisis o calma?
   → el cascade tiene distinto significado según régimen (IC 0.56 en 2020s vs 0.41 en 1990s)

4. Señales HUÉRFANAS: N<10 → interpretar, no ignorar
   → los eventos más raros son los más peligrosos (SKEW LOW_TAIL en 2008)
```

---

## 6. ARQUITECTURA DEL SCANNER

### 6.1 Knowledge Store (en vez de RAG completo)
```
Formato: JSON estructurado por estación, categoría, hallazgo, grado de certeza.
Archivo: scratch/knowledge_store.json → consultable, actualizable incrementalmente.

Estructura:
{
  "findings": [
    {
      "id": "FG-001",
      "station": "FG",
      "category": 3,
      "description": "EXTREME_FEAR + D3 comprimido = entry seguro",
      "metric": { "ev_20d": 4.30, "wr": 0.87, "pf": 26.76, "n": 15 },
      "ci95": { "ev": [2.48, 6.45], "wr": [0.71, 0.97] },
      "grade": "A",
      "regime": "CRISIS",
      "timing": "coincidente",
      "cross_refs": ["VIX-003", "SKEW-001"]
    }
  ]
}
```

### 6.2 Pipeline del scanner
```
FASE 1 — CARGA: 11 fact stores, cascade_calibration, ohlcv_bars, zigzag_legs,
                 intelligence docs, clasificación, knowledge_store previo

FASE 2 — POR ESTACIÓN (11 sub-agentes en paralelo):
  - D1×D2×D3 completo (poblado N≥10 y huérfano N<10)
  - Pre/post zigzag timing (lead/lag)
  - Matriz D2×D3 dentro de cada D1

FASE 3 — CROSS-STATION (1 agente consolidor):
  - Correlaciones (raw, D2, D3)
  - Divergencias (contradicciones)
  - Conjunciones (coincidencias)
  - Lead-lag entre estaciones (valida la cadena causal)

FASE 4 — REGÍMENES Y EVENTOS (1 agente):
  - Clasifica cada pivote en un régimen
  - Identifica eventos especiales (PÁNICO TOTAL, CAPITULACIÓN, etc.)
  - Mide comportamiento de indicadores POR RÉGIMEN

FASE 5 — COMPLEMENTO CASCADE (1 agente):
  - Identifica señales que cascade no captura
  - Evalúa si mejoran la predicción (OOS gate)
  - Sugiere integración (confirmador / filtro / nueva capa)

FASE 6 — REPORTE + KNOWLEDGE STORE:
  - Reporte unificado con hallazgos GRADE A/B/C
  - Actualiza knowledge_store.json incrementalmente
  - FLAGS automáticos de violaciones metodológicas
```

---

## 7. QUÉ NO DEBE HACER

```
- NO proponer cambios al cascade sin OOS gate
- NO usar Kronos/ML para predicción (solo stress-test)
- NO reportar sin CI95 + N
- NO promediar wins con losses
- NO mezclar N<10 con N≥30
- NO etiquetas binarias sin probabilidad
```

---

## 8. PREGUNTAS ABIERTAS (para decidir antes de construir)

1. ¿11 sub-agentes en paralelo o secuencial? (paralelo = 2-3 min, secuencial = 20-30 min)
2. ¿El knowledge store va a un solo JSON o a SQLite? (JSON = simple, SQLite = consultable)
3. ¿Los regímenes se definen con reglas fijas (VIX>P80...) o con clustering no supervisado?
4. ¿El scanner corre una vez (snapshot) o es incremental (cada nuevo dato)?
5. ¿Pre/post zigzag usa TODOS los pivotes o solo los de eventos especiales?