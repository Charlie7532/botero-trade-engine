<!-- VINTAGE_METADATA_HEADER -->
> [!WARNING]
> **VINTAGE V-B (PRE-HOMOGENEIZACIÓN) — NO COMPARABLE DIRECTAMENTE CON V-C**
> **Motivo medido:** Datos generados con series tácticas híbridas SMA5/EMA5 en las 14 series `*_TW`, barras parciales previas al rebuild de 2026-10-04, y piernas SPY desalineadas.
> **Ventana declarada:** 2000-01-03 a 2026-06-16 (6.653 días de trading en V41/V40).
> **Propósito:** Registro histórico inmutable de auditoría para preservación de evidencia empírica (F5.1).
<!-- END_VINTAGE_METADATA_HEADER -->

# 🚨 DIRECTIVA ARQUITECTÓNICA: Política de Degradación de Confianza por Datos Faltantes (V3)

**Origen**: Feedback iterativo del System Architect sobre Plan V40.  
**Fecha**: 2026-07-29  
**Estado**: POLÍTICA REFINADA V3 — Umbrales pendientes de determinación empírica via simulación.

---

## La Directiva (V3 — Corrección Crítica)

> [!IMPORTANT]
> **Corrección del System Architect**: La distinción rígida "bloquear entradas / nunca bloquear salidas" estaba equivocada. La distinción real depende de **cuánta autonomía y capacidad tiene el módulo con o sin cada señal específica**.

### Principios Rectificados

1. **El sistema NUNCA se bloquea** — siempre continúa operando con la alerta activa
2. **Cada señal faltante degrada la confiabilidad** en una cantidad medible empíricamente
3. **Las combinaciones importan**: sin FG pero con VIX ≠ sin VIX pero con FG ≠ sin ambos
4. **Los umbrales no se inventan** — se determinan por simulación del benchmark

### Pregunta correcta por señal

> *"¿Se puede operar sin la señal X? ¿Cuánto degrada la confiabilidad? ¿Es posible operar sin FG pero con VIX? ¿Sin VIX pero con FG? ¿Sin ninguno de los dos? ¿Cuánto se reduce la confiabilidad en cada caso?"*

---

## Modelo de Degradación de Confianza (Revisado)

```
CONFIDENCE = f(señales_presentes, señales_faltantes, tiempo_stale)

  El confidence NO es un umbral fijo arbitrario.
  Es una FUNCIÓN EMPÍRICA calibrada por simulación.
  
  El sistema SIEMPRE opera.
  El confidence determina:
    - Si se emite NOTAM (y a qué nivel de urgencia)
    - Si el sizing de nuevas posiciones se reduce
    - Si el log incluye tag de degradación para forensics
```

### Lo que cambia vs V2

| Aspecto | V2 (Incorrecta) | V3 (Corregida) |
| :--- | :--- | :--- |
| **Entradas** | RED → BLOQUEADAS | RED → Opera con sizing reducido + NOTAM |
| **Salidas** | Siempre operan | Siempre operan (esto sigue igual) |
| **Umbrales** | Arbitrarios (80%, 50%, 0%) | **Determinados por simulación** |
| **Bloqueo** | Sí, para entradas en RED | **NUNCA** — siempre opera con alerta |
| **Filosofía** | Regla rígida por categoría | Degradación cuantificada por señal |

---

## Simulación Requerida: Signal Dropout Experiments

Para determinar empíricamente cuánto degrada cada señal, ejecutar el benchmark V39 con dropout selectivo:

### Experimentos

| # | Experimento | Señal(es) removidas | Pregunta |
| :---: | :--- | :--- | :--- |
| 1 | **Baseline** | Ninguna (V39 completo) | Referencia: 1,034.81 acc SPY |
| 2 | **Sin FG** | FG (Fear & Greed) | ¿Cuánto pierde la antena de capitulación? |
| 3 | **Sin VIX** | VIX (usa default 18.0) | ¿Cuánto pierde la redirección V36? |
| 4 | **Sin FG + Sin VIX** | Ambos | ¿Degradación aditiva o multiplicativa? |
| 5 | **Sin SV5** | SV5_TH, SV5_FI, SV5_TW | ¿Cuánto vale la dimensión de volumen? |
| 6 | **Sin Sector Breadth** | S5_{SEC}_*, SV5_{SEC}_* | ¿Cuánto vale la resolución sectorial? |

### Métricas de Degradación

Para cada experimento, medir:
- **Δ Acciones SPY** vs baseline (impacto en retorno total)
- **Δ Max Drawdown** (impacto en protección de crisis)
- **Días de régimen misclasificados** (ej: quedarse en MERCADO_SANO cuando debería ser DISTRIBUCION)
- **Impacto por año** (¿en qué años duele más la ausencia?)

### Resultado Esperado

Una tabla de degradación empírica que responde:

```
Si falta FG:        confidence -= X%  (donde X se mide del benchmark)
Si falta VIX:       confidence -= Y%
Si faltan ambos:    confidence -= Z%  (¿Z = X+Y o Z > X+Y?)
Si falta S5 sector: confidence -= W% por sector afectado
```

---

## Auditoría: Señales del Gate y su Redundancia

| Señal | Qué detecta | ¿Tiene redundancia? | Sin ella, ¿qué pierde el gate? |
| :--- | :--- | :--- | :--- |
| **S5TH/FI/TW** | Breadth estructural/intermedio/táctico | No — es el input primario | Pierde clasificación de régimen completa |
| **SV5TH/FI/TW** | Volumen institucional | Parcial (S5 sigue funcional) | Pierde antena pre-crash (#1), reabsorción (#3), capitulación vol (#4) |
| **VIX** | Nivel de volatilidad/pánico | Parcial (FG cubre sentimiento) | Pierde redirect V36 (CRASH→PISO si VIX≤28) |
| **FG** | Fear & Greed / sentimiento extremo | Parcial (VIX cubre vol/pánico) | Pierde antena FGBI reversal (CRASH→PISO) |
| **tw_prev** | Dirección del momentum táctico | No — se necesita el día anterior | Pierde spy_joint state → TOP_DISTRIBUTION_STATES inutilizables |
| **S5_{SEC}_*** | Breadth por sector | No para ese sector | Sector se excluye del universo → reduce diversificación |

### Observación Clave: Redundancia VIX ↔ FG

VIX y FG cubren **dimensiones complementarias pero parcialmente superpuestas**:
- **VIX alto + FG bajo** = Crash clásico (ambos señalan lo mismo)
- **VIX normal + FG bajo** = Miedo por sentimiento sin vol (divergencia útil)
- **VIX alto + FG normal** = Vol técnica sin pánico retail (divergencia útil)

La redundancia no es completa → la degradación al perder uno NO es catastrófica, pero al perder ambos se pierde la capacidad de detectar transiciones de crash.

---

## Niveles de Severidad: De Señal Faltante a Infraestructura Caída

La degradación no se limita a señales individuales. Hay niveles de fallo progresivamente más severos:

| Nivel | Fallo | Ejemplo | Impacto | Contingencia |
| :---: | :--- | :--- | :--- | :--- |
| **L1** | Señal individual faltante | FG no se actualizó hoy | Antena específica degradada | Último valor conocido + NOTAM + evaluar si el cálculo se puede omitir |
| **L2** | Proveedor MCP caído | Finviz, Finnhub, UW offline | Múltiples señales afectadas simultáneamente | Intelligence procura dato alternativo. ¿Se puede sintetizar desde otra fuente? |
| **L3** | Base de datos inaccesible | Neon PostgreSQL caído | **Todo el Vault inaccesible** — sin datos históricos ni estados de régimen | ⚠️ Plan de contingencia agéntica (NO implementado aún) |
| **L4** | Sistema de respaldo caído | DB + MCP + fallback todos caídos | Ceguera total | ⚠️ Circuit breaker: mantener última posición conocida, no operar |

> [!WARNING]
> **L3 y L4 requieren un plan de contingencia agéntica** que actualmente NO existe en la arquitectura. Diseñarlo es una fase posterior que involucra múltiples módulos (Intelligence, Execution, Risk). Se documenta aquí como deuda técnica reconocida.

---

## Principios de Reemplazo de Datos (Caso por Caso)

> [!IMPORTANT]
> **Directiva del System Architect**: "Prefiero no tener que suponer. Pero también tratar de obtener el reemplazo del dato sintetizando sobre la data del mercado o sobre observaciones reales del tiempo real, puede ser alternativa."

Cada dato faltante tiene un tratamiento distinto que debe evaluarse individualmente:

| Estrategia | Cuándo aplica | Ejemplo |
| :--- | :--- | :--- |
| **Omitir el cálculo** | Cuando el cálculo sin el dato se puede omitir y la degradación es medible | Sin FG → la antena FGBI se omite, las otras antenas siguen. Degradación = lo que mida la simulación |
| **Último valor conocido** | Cuando el dato tiene inercia temporal (cambia poco día a día) | VIX ayer = 15.2. Si hoy no llega, usar 15.2 es razonable por 1 día. Alertar |
| **Sintetizar desde observables** | Cuando se puede derivar un proxy desde datos de mercado en tiempo real | Si FG no llega pero tenemos VIX + PCR + Put/Call ratio → se puede estimar un proxy. Requiere validación |
| **No operar ese cálculo** | Cuando suponer es peor que no tener el dato | Si tw_prev es incorrecto → spy_joint state es falso → mejor no evaluar TOP_DISTRIBUTION_STATES que evaluarlas con basura |

> La decisión entre estas estrategias **depende del caso** y **debe evaluarse por impacto y pérdida de confiabilidad**. No hay una regla universal.

---

## Próximos Pasos

1. **Ejecutar los 6 Signal Dropout Experiments** contra el benchmark V39
2. **Medir las métricas de degradación** para calibrar los umbrales empíricamente
3. **Codificar la tabla de degradación** como un JSON fact store (con `_documentation` metadata)
4. **Integrar al Data Manifest** de cada gate: `{señal: degradation_weight}`
5. **Conectar al NOTAM/METAR** de Intelligence con urgencia proporcional a la degradación acumulada
