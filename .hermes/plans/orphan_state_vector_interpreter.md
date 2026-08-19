# ORPHAN STATE VECTOR INTERPRETER — Diseño

> **Filosofía:** Una señal huérfana (N<10) NO es "no sé". Es una señal RARA que
> requiere MAYOR procesamiento. Es una señal IMPORTANTE.
> **Regla de oro:** Toda probabilidad con CI95 + N. Nada binario.

---

## 1. Concepto

```
Antes:  N<10 → reliability_factor=0 → "apago el canal, no sé"
Ahora:  N<10 → ES UNA SEÑAL HUÉRFANA → interpreto con el vector completo
```

Un estado raro en 33 años es precisamente cuando el mercado "grita". No le tenemos miedo — lo interpretamos con estadística.

---

## 2. Detección

```
state_key (D1__D2__D3) → fact store → N_raw < 10 → "huérfano"
```

---

## 3. Interpretación por vector completo (D1 × D2 × D3)

Cada dimensión aporta una pregunta distinta:

```
D1 (nivel)      → ¿en qué condición?      → extremo alto / bajo / medio
D2 (velocidad)  → ¿hacia dónde y rápido?  → acelerando / desacelerando / estable
D3 (volatilidad)→ ¿estabilidad?           → expandiendo / picó_y_cede / contrayendo
```

**El vector completo cuenta UNA historia, no tres señales sueltas.**

---

## 4. Escenarios validados (VIX, N=47 huérfanos en crisis)

| Escenario (D1×D2×D3) | %bull | Lectura | Decisión |
|---|---|---|---|
| CRISIS + ACELERANDO + VOL_CONTRACCIÓN | **76%** | Pánico acelerando pero vol COMPRIMIDA → explosión alcista | ENTRAR |
| CRISIS + ACELERANDO + VOL_PICÓ_Y_CEDE | 57% | Pánico acelerando, vol ya picó → movimiento maduro | ESPERAR |
| CRISIS + DESACELERANDO + VOL_EXPANSIÓN | 60% | Pánico cediendo en caos → reversión volátil | ENTRAR (con cautela) |
| CRISIS + DESACELERANDO + VOL_CONTRACCIÓN | 38% | Pánico cediendo con calma → bear sigue | SALIR / ESPERAR |

---

## 5. Árbol de decisión (la variable que discrimina)

**No es el promedio de escenarios (~58%, moneda al aire). Es un árbol condicional.**

```
ESTADO HUÉRFANO (N<10) — VIX
   │
   ├─ D3 = CONTRACCIÓN (vol calma)            ← LA VARIABLE CLAVE
   │    ├─ D2 = ACELERANDO     → 76% bull → ENTRAR (gap 38pp)
   │    └─ D2 = DESACELERANDO  → 38% bull → SALIR
   │
   └─ D3 ≠ CONTRACCIÓN (caos)
        └─ ~58% en ambos → NO OPERAR (moneda al aire)
```

**D3 es el discriminador: cuando la volatilidad está contraída, la velocidad abre un abismo de 38pp. Cuando no, es ruido.**

| D3 | D2 | %bull | Decisión |
|---|---|---|---|
| CONTRACCIÓN | ACELERANDO | 76% | ENTRAR |
| CONTRACCIÓN | DESACELERANDO | 38% | SALIR |
| NO CONTRACCIÓN | cualquiera | ~58% | NO OPERAR |

⏳ **Confirmadores pendientes:** breath, SV5T, VIX×SV5T — añadirán capa adicional de filtro.

---

## 6. Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  ORPHAN STATE VECTOR INTERPRETER                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  INPUT: state_key (D1__D2__D3) + N + estación               │
│                                                             │
│  1. DETECCIÓN:  N < 10 → huérfano                           │
│  2. VECTOR:     descomponer D1, D2, D3 con su significado   │
│  3. ESCENARIO:  match contra tabla de escenarios validados  │
│  4. PROBABILIDAD: P(dirección) + P(cascade) + CI95 + N      │
│  5. DECISIÓN:   {ENTRAR | ESPERAR | SALIR} + confianza      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Plan de extensión (11 estaciones)

| Fase | Qué | Estado |
|---|---|---|
| 1. VIX | 4 escenarios validados | ✅ Medido |
| 2. Confirmar D2/D3 (agentes en curso) | qué significa velocidad y volatilidad | 🔄 Corriendo |
| 3. VVIX, BSI, PCR, FG | estaciones donde D3 discrimina | ⏳ |
| 4. Macro (credit, yield, rotation) | D3 neutro — usar solo D1+D2 | ⏳ |
| 5. SKEW | D3 invertido — caso especial | ⏳ |
| 6. SV5T | sensor de batalla, lógica propia | ⏳ |

---

## 7. Orquestación final (próxima etapa)

Cuando los intérpretes por estación estén validados:
- Conjunción de 11 estaciones (¿cuántas coinciden?)
- Multi-escala (zz25/zz50/zz75)
- Confirmadores (VIX×SV5T, S5×SV5)
- Cascade conviction (D1-only, ya validado)

→ Discriminar, interpretar y operar con probabilidad sustentada en escenarios.

---

## 8. Próximo paso

Esperar los 2 agentes (D2, D3) → refinar los escenarios → prompt a Gemini
para implementar el intérprete.