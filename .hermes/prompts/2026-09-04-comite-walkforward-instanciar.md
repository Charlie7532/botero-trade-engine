# PROMPT: Comité METAR Walk-Forward — Instanciar los 11 Agentes sobre el Catálogo Homogenizado

**Fecha:** 04-Sep-2026
**Ejecutor:** Gemini
**Contexto:** El catálogo de señales fue homogenizado y es ahora la fuente de verdad:
- Criterio unificado: evaluador GENERAL continuo (first-passage OHLC, episodios continuos, no solo pivotes)
- N limpios (política de inception, sin datos pre-fecha_inicio_valida ni pre-SPY)
- `cascade_reversal` corregido a semántica de confirmación de pierna (modo `pierna_confirmada`, inception=2011, **N=80 limpio** — no 219)
- Confluencias canarias regeneradas (51 pares sobre datos limpios)
- Ranking maestro consumiendo `rendimiento_lake` (continuo)

La infraestructura del comité ya existe como esqueleto en `comite_metar/`:
- `perfiles/perfil_estaciones.json` (11 estaciones con mundo/rol/ancla/inception) — COMPLETO
- `agentes/`, `curador/`, `scripts/`, `salidas/` — VACÍOS (a implementar)

**Objetivo de esta etapa:** instanciar la **Fase 1 (episodios) + Fase 2 (agentes LLM)** del comité walk-forward forense sobre el catálogo homogenizado.

---

## TAREA

### Fase 1: Scripts deterministas (`comite_metar/scripts/`)
Crear los cómputos deterministas que simulan el estado vela a vela:
- `episodios.py`: desde el lake continuo limpio, generar los **episodios** y **pivotes de decisión** donde los agentes interpretan (no cada vela — puntos de decisión).
- `estado_en.py`: dado un punto temporal t, reconstruye el **state_key completo** (D1×D2×D3, overflow, bins) de las 11 estaciones que un agente vería EN t (sin lookahead).
- `first_passage.py`: dado el disparo de una señal en t, computa el first-passage OHLC hacia adelante (triple barrera), respetando el `blanco` de la señal y Opción C (sin time-stop fijo / o el definido).
- De-clustering dinámico por episodios continuos (no excluye — agrupa, §3.3).

Usar solo columnas observables en t (no usar pivotes futuros). Respetar `fecha_inicio_valida` por estación.

### Fase 2: Agentes LLM (`comite_metar/agentes/`)
Crear 11 agentes, cada uno con su perfil de `perfil_estaciones.json`. Cada agente en cada punto de decisión:
1. Lee el `state_key` de SU estación en t (decodificado con sus labels D1×D2×D3 + dirección física).
2. Emite SU lectura: ¿es precursor/canario/confirmador? ¿qué predice sobre el pivote próximo?
3. Actúa con **validación de ancla D**: ¿su lectura responde a lo que su rol predice? (VIX anticipa pivote, BSI confirma movimiento, etc.)
4. NO usa datos post-t (lookahead prohibido).

**Cuestionario canónico para cada agente en cada episodio:**
- ¿Qué D1×D2×D3 observas y qué significa en tu mundo?
- ¿Estás **pre-cursor** (anticipas), **canario** (a ~1-2 velas), **confirmador** (en/tras el pivote) o **ruido**?
- ¿Probarías una entrada/exit? ¿Con qué convicción (alta/media/baja) y riesgo?
- ¿Qué tel evidencia del catálogo respalda tu lectura (posición en el ranking, EV del continuo, timing)?

### Fase 3 (diseño): Interfaz de curador
Definir la interfaz de `curador/` (fusión de lecturas, confluencia probabilística, confrontación de modelos) — NO implementar aún, solo el contrato de entrada/salida.

---

## ENTRADA (usar los datos homogenizados)
- `data/research/continuous_metar_lake.parquet` (8,456 barras, limpio)
- `data/research/signals/evaluacion_generalizada_lake.json` (36 señales, continuo)
- `data/research/signals/ranking_maestro.json` (posición/score por señal)
- `data/research/signals/confluencias_canarias.json` (51 pares)
- `comite_metar/perfiles/perfil_estaciones.json` (11 perfiles)

## SALIDA (JSON por agente y consolidado)
Por cada agente en cada episodio → lectura (estación, D1D2D3, rol precognitivo, convicción, decisión). Consolidado en `comite_metar/salidas/`.

---

## PRINCIPIOS OBLIGATORIOS (no negociables)
- **Sin lookahead:** en t ningún agente ve post-t.
- **Inception:** respetar fecha_inicio_valida por estación (agente "madura" cuando su estación tiene datos).
- **Continuo, no solo-pivote:** los agentes interpretan en el continuo, no solo en pivotes (el catálogo ya es continuo).
- **De-clustering = credibilidad, no exclusión.**
- **Rareza se prueba contra el nulo**, no se declara.
- **Confluencia probabilística**, no determinista.
- **Dato mata relato.** **La verdad habla.**

## VERIFICACIÓN DE ACEPTACIÓN
```python
# Los perfiles cargan
import json
perf = json.load(open('comite_metar/perfiles/perfil_estaciones.json'))
assert len(perf) == 11  # o la estructura del registro

# Los scripts existen y corren determinista sin lookahead
# episodios.py genera >0 episodios
# estado_en(t) reconstruye state_key solo con datos <= t
```

No implementar aún la Fase 4 (modelador OOS) ni la 5 (entrega). Esta etapa = Fases 1-3.