# PLAN DE AGENTES — Arquitectura final + Árbol de Decisión + Próximos Pasos

> Estado: PLAN. Todo el aprendizaje del día consolidado en un plan accionable.
> Juan Andrés + Hermes, 17-Ago-2026.

---

## 1. EL ÁRBOL DE DECISIÓN (la estructura final)

```
NIVEL 1 — MACRO CLIMA (CAT 1: economía)
  ¿EXPANSIÓN o CONTRACCIÓN?
  Señales: CREDIT stress, YIELD invertida, DXY subiendo, ROTATION-A saliendo

NIVEL 2 — ¿QUIÉN LIDERA? (la secuencia de activación)
  ¿CAT 2 (sentimiento) o CAT 3 (acción) se activó primero?
  Señales: VIX↑/PCR↑/SKEW↑ para CAT2; S5↓/SV5T↑ para CAT3

NIVEL 3 — ¿CONFIRMÓ? (la categoría que sigue)
  Si CAT2 lideró, ¿CAT3 confirmó? Si CAT3 lideró, ¿CAT2 confirmó?

NIVEL 4 — RÉGIMEN EXACTO (la hoja, la secuencia completa)

LAS HOJAS (regímenes validados):
  🍃 MACRO-DRIVEN    (CAT1→CAT2→CAT3): +2.71% 40d, 83% de los pivotes
  🍃 CUCHILLO        (CAT1→CAT3→CAT2): -5.64% 20d, BEARISH
  🍃 COMPRAR MIEDO   (CAT2→CAT3→CAT1): +4.86% 40d, 85% WR (zz25)
  🍃 PROTECCIÓN LIDERA (CAT2→CAT1→CAT3): mixto
  🍃 EXPLOSIVO       (CAT3 lidera): colas gordas, vol 2×

NIVEL 5 — EVENTOS ESPECIALES (capa de transición/disrupción)
  Sobre cada régimen, se superponen eventos que califican el tipo de cambio:
  - TRANSICIÓN GRADUAL (cisne blanco): cambio de rama en el árbol
  - DISRUPCIÓN ABRUPTA (cisne negro): salta ramas, no anticipado
  - TRAMPA (bull/bear): señal falsa, requiere contexto multi-escala
```

---

## 2. ARQUITECTURA DE AGENTES

```
┌────────────────────────────────────────────────────────────┐
│               COORDINATOR (el meteorólogo)                 │
│  Lee: 3 category agents + cascade + decision tree          │
│  Produce: METAR (estado) + TAF (forecast, cono) + SIGMET   │
│  Detecta: MOMENTOS DE VERDAD (transición de régimen)       │
└──────┬──────────────────┬──────────────────┬──────────────┘
       │                  │                  │
  ┌────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
  │ CAT 1    │      │ CAT 2     │      │ CAT 3     │
  │ ECONOMÍA │      │ SENTIMIENT│      │ ACCIÓN    │
  │          │      │           │      │           │
  │ CREDIT   │      │ VIX       │      │ BSI(S5TW) │
  │ YIELD    │      │ VVIX      │      │ SV5T      │
  │ DXY      │      │ PCR       │      │ FG        │
  │ ROT-A    │      │ SKEW      │      │ ROT-B     │
  └──────────┘      └───────────┘      └───────────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                   ┌──────▼──────┐
                   │   AUDITOR   │
                   │ validación  │
                   │ CI95, N, OOS│
                   └─────────────┘
```

### 2.1 Roles de cada agente

**CATEGORY AGENT (1, 2, 3):**
```
INPUT:  sus indicadores (D1/D2/D3), knowledge del indicador
OUTPUT: estado GRADUADO de la categoría (0-100%) + SIGMETs
        (extremo alto, extremo bajo, anticipación, confirmación, flip)
HERRAMIENTAS: adapters por indicador, fact stores, secuencia
KNOWLEDGE: qué mide CADA indicador, qué es normal/extremo, pitfalls
```

**COORDINATOR:**
```
INPUT:  estados de 3 categorías + cascade_conviction + decision tree
OUTPUT: METAR (estado actual) + TAF (forecast con cono) + SIGMET
DETECTA: secuencia de activación → régimen → momento de verdad
KNOWLEDGE: árbol de decisión, regímenes validados, eventos especiales
```

**AUDITOR:**
```
Verifica: CI95 + N en toda señal, wins/losses separados, no binario,
          no promediar, no mezclar N<10 con N≥30, adapter correcto
FLAGS: etiquetas sin probabilidad, estados huérfanos sin intérprete
```

---

## 3. QUÉ SABE CADA AGENTE (contexto que cargan)

### 3.1 Conocimiento COMPARTIDO (todos los agentes)
```
- Las 3 categorías (economía/sentimiento/acción) y su lead-time
- La tríada D1×D2×D3: D1=cascade, D2=dirección, D3=confianza
- El árbol de decisión (5 niveles, regímenes validados)
- Los eventos especiales (cisnes, trampas, transiciones)
- La regla de oro: probabilidad + CI95 + N, nunca binario
- Las escalas Gaussianas (PERCENTILES_D1_GAUSS)
- Los pitfalls (1-74 del skill botero-trade-workflow)
- "Nadie es portador de la verdad absoluta" — dato mata relato
```

### 3.2 Conocimiento ESPECÍFICO (por categoría)

```
CAT 1 (ECONOMÍA):
  - CREDIT: salud del crédito corporativo (HYG/LQD), lead largo
  - YIELD: salud del ciclo macro (10Y-3M), inversión = recesión
  - DXY: salud del dólar, flujos internacionales, ES UN CICLO (no drift)
  - ROTATION-A: dinero entra/sale de USA (ligado a DXY y liquidez)
  - Señales GRADE A: CREDIT_STRESS=entry, YIELD_EXTREME_STEEPNING=exit,
    DXY_DOLLAR_SPIKE=bearish

CAT 2 (SENTIMIENTO/PROTECCIÓN):
  - VIX: miedo a volatilidad, precio del seguro, D2 flip↓=timing
  - VVIX: vol del VIX, estabilidad del miedo
  - PCR: posicionamiento en opciones, AMBOS lados (put panic=piso, call heavy=techo)
  - SKEW: miedo de cola (institucional), ORTOGONAL a VIX (ρ=-0.185),
    post-2011, contrarian, PÁNICO TOTAL=PF 8.09
  - Señales GRADE A: CAPITULACIÓN, SUB-REACCIÓN, PÁNICO TOTAL

CAT 3 (ACCIÓN/REALIDAD):
  - BSI (S5TW): amplitud de PRECIO, participación real, mean-reversion
  - SV5T: amplitud de VOLUMEN, batalla (dirless, confirmador)
  - FG: sentimiento CNN (real 2011+, suavizado 504d), EXTREME_FEAR+D3comprimido=entry
  - ROTATION-B: rota defensivo↔cíclico (protección con mandato)
  - Señales GRADE A: EUFORIA (VIX↓+S5max=techo), CAPITULACIÓN (S5 colapsó),
    EXTREME_FEAR+D3 comprimido (+4.30% 20d, PF 26.76)
```

---

## 4. PLAN DE PRÓXIMOS PASOS

### FASE 1 — Construir los 3 category agents + coordinator (AHORA)
```
Dispatch en paralelo:
  - Agente CAT 1 (economía): CREDIT, YIELD, DXY, ROTATION-A
  - Agente CAT 2 (sentimiento): VIX, VVIX, PCR, SKEW
  - Agente CAT 3 (acción): BSI, SV5T, FG, ROTATION-B
  - Agente COORDINATOR: lee los 3 + cascade + decision tree

Cada category agent produce:
  - Estado graduado de la categoría (0-100%)
  - SIGMETs (extremo, anticipación, flip)
  - Lead-lag medido (¿cuándo se activó?)

El coordinator produce:
  - METAR: estado actual de cada categoría
  - TAF: forecast con cono de dispersión
  - SIGMET: solo significancias (cortante de viento)
  - RÉGIMEN: secuencia de activación → hoja del árbol
```

### FASE 2 — Poblar las hojas faltantes
```
- COMPLACENCIA (extremo bajo de CAT 2): VIX↓+SKEW↓+PCR↓ = ¿piso o calma sana?
- RÉGIMEN NORMAL (todo en límites): "tendencia continúa sin alteración"
- Transiciones entre regímenes: ¿qué dispara el cambio de hoja?
```

### FASE 3 — Validación OOS
```
- Walk-forward OOS para cada régimen (26 folds)
- Bootstrap CI95 para todas las señales
- Benchmark anticipación vs falsa alarma
- Comparar contra baseline SPY por régimen
```

### FASE 4 — Eventos especiales (traducción de puntos ciegos)
```
- RALLY ESTRECHO (concentración mega-cap)
- ACUMULACIÓN vs DISTRIBUCIÓN (dirección del flujo)
- PÁNICO DE AMPLITUD (8+ sectores distribuyendo)
- CAPITULACIÓN ESTRUCTURAL (120d)
```

---

## 5. HERRAMIENTAS QUE YA TENEMOS (para los agentes)

```
✅ secuencias_classifier.py — clasifica regímenes por secuencia de activación
✅ metar_skeleton.py — prototipo con SIGMET bus + lead-lag
✅ especificacion_operativa.md — 9 señales GRADE A validadas
✅ clasificacion_naturaleza.md — 3 categorías con lead-time
✅ inventario_eventos_especiales.md — 4 capas de eventos
✅ sistema_metar_regimenes_v4.md — arquitectura + decisiones
✅ skill botero-trade-workflow — 76 pitfalls documentados
```

---

## 6. MÉTRICAS DE ÉXITO (para validar cada fase)

```
FASE 1: cada category agent reproduce hallazgos GRADE A conocidos
FASE 2: las hojas nuevas tienen CI95 que excluye 0
FASE 3: OOS IC > 0 para al menos 80% de los regímenes
FASE 4: cada nuevo evento especial es medible (no solo conceptual)
```

## 7. DOS CORRECCIONES CRÍTICAS (auditadas antes del lanzamiento)

### 7.1 DESBORDAMIENTO DE ESCALA (σ-overflow) — flag de Juan Andrés
```
Las bandas σ saturan en +2σ (P97.7). El dato desborda la escala:
  VIX max = 82.7 = 10.7σ, pero todo ≥40.7 se etiqueta "CRISIS_SPIKE".

FIX: añadir "sigma depth" (profundidad continua):
  depth = (val - μ) / σ  — cuántas σ más allá de la media
  label discreto (bandas σ) + depth continuo = resolución completa en el extremo.

El extremo profundo (depth > 4σ) es DONDE viven los eventos más grandes:
  VIX 41 (2.8σ) ≠ VIX 82 (10.7σ). El "over-correction" es proporcional a la depth.
```

### 7.2 VECTOR DE ESTADO COMPLETO (D1×D2×D3 calibrado)
```
El calibrador usa D1 calibrado pero D2/D3 CRUDOS (diff3, std2/std10).
Los agents DEBEN usar el state_key COMPLETO del fact store:
  D1×D2×D3 con los 3 labels calibrados (ej. CRISIS_SPIKE__FAST_CRUSH_3D__VOL_COMPRESSED).

NO usar D2/D3 crudos — usar los bins D2/D3 del fact store
(FAST_SPIKE_3D, ACCELERATING_UP_3D, VOL_EXTREME_SQUEEZE, etc.).
Esto alinea con la tríada D1×D2×D3 que ya está calibrada.
```