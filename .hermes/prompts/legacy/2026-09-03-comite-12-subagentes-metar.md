# PROMPT: Comité METAR de 12 Subagentes — Walk-Forward Forense Integral

**Fecha:** 03-Sep-2026
**Propósito amplio (la verdad habla):** Un comité de 11 agentes LLM (una por estación METAR, cada uno con su comportamiento/personalidad de experto en su "mundo") + 1 curador, que **simulan operar EN VIVO vela a vela** sobre el SPY desde la primera vela (1993) hasta hoy. Durante el recorrido:
1. **VALIDAN / INVALIDAN** las reglas e interpretaciones construidas en las auditorías (taxonomía, canarios, niveles).
2. **DESCUBREN** nuevas señales, estados y significados que las reglas previas no capturaron.
3. **CALIFICAN** cada señal/vigilancia por su credibilidad (N_indep, CI95) y por su desempeño OOS en el recorrido en vivo.
4. **CONFRONTAN** modelos/interpretaciones entre sí y contra el mercado (confrontar = comparar predictores y dejar que el desempeño real decida).
5. **Analizan confluencias** y **señales escasas** (rareza=Riqueza, §3.3) para entender su significado — no silenciarlas.

**El principio rector: "la verdad habla."** Cada conclusión se gana o se pierde por lo que el mercado hizo DESPUÉS, en el walk-forward. Nada vale por su narrativa.

**Marco normativo (no negociable):**
- **Metrología:** first-passage OHLC intrabar, sin time-stop (Opción C). El movimiento termina cuando cambia de régimen del zz.
- **Simulación en vivo:** cada agente lee SOLO datos hasta la vela `t` (sin lookahead). Espera a que su estación madure (inception: VIX 1993, VVIX/PCR 2006, CREDIT 2007, FG 2011, etc.) antes de opinar.
- **De-clustering = credibilidad, nunca exclusión.** N_indep + CI95 honestos; señales escasas se conservan y estudian (§3.3).
- **La rareza se prueba contra el nulo** (CI95 excluya base-rate), no se declara.
- **Taxonomía desacoplada en ejes:** (estado × posición-en-giro × confianza).
- **Fusion probabilística, no determinista.** Miedo/euforia se exageran (fat-tail).

---

## ARQUITECTURA (Opción B — separar observar de operar, con curador que APRENDE)

```
┌─────────────────────────────────────────────────────────────┐
│      AGENTE OBSERVADOR-CURADOR (1, escribe registros)        │
│  "Observa la verdad": recibe 11 reportes, fusiona por vela,  │
│   escribe curador_registro.json (diagnóstico + forecast)     │
└──────────────────────────┬──────────────────────────────────┘
                           │ 11 series benchmark_{est}​.json
     ┌──────────┬──────────┼──────────┬──────────┬─────────┐
     │          │          │          │          │         │
   VIX        VVIX       PCR        FG        SV5_T    ... BSI
   Agent      Agent      Agent      Agent      Agent    Agent
     └──────────┴──────────┴──────────┴──────────┴─────────┘
      (11 escriben benchmark_{estación}.json, en paralelo)

        ↓ (después, sobre el histórico)
┌─────────────────────────────────────────────────────────────┐
│         MODELADOR-APRENDIZ (lee registros, aprena)           │
│  Lee benchmark_*.json + curador_registro.json, calibra       │
│   modelo_confluencia.json + confluencias_canarias.json       │
│   con OOS por episodio. El MODELO QUE OPERA.                 │
└─────────────────────────────────────────────────────────────┘
```

**Separación de responsabilidades:**
- **11 agentes** → OBSERVAN su mundo → `benchmark_{estación}.json`
- **Curador observador** → INTEGRA los 11 → `curador_registro.json` (diagnóstico vela a vela, en vivo)
- **Modelador-aprendiz** → APRENDE del histórico → `modelo_confluencia.json` + `confluencias_canarias.json` (el modelo que opera, calibrado OOS)

**El curador APRENDE (no solo registra):** el modelador-aprendiz lee los registros históricos completos y calibra los pesos de confluencia — qué combinación de mundos anticipó giros reales vs falsos, con N_indep y validación OOS. Ese aprendizaje se persiste en `modelo_confluencia.json` para operar en vivo.

---

## PARTE 1 — SUBAGENTES DE ESTACIÓN (11, corren en paralelo)

### Rol de cada uno
Cada subagente es el **interprete semántico de UNA estación** sobre su vector de estado D1×D2×D3, en cada vela del SPY. NO predice dirección a ciegas — evalúa **qué significa el estado de esa estación** en cada punto y su **proximidad/impacto al giro**.

### Benchmark vela a vela que cada uno realiza (dato a dato)
Para **cada vela `t`** del SPY (8,453 barras, 1993→2026):

1. **Leer el estado:** `{estación}_sk` → D1×D2×D3 actual.
2. **Clasificar la firma por ejes (taxonomía desacoplada):**
   - **ESTADO** (proceso): ¿continua con fuerza? ¿desacuerdo/desidia? ¿acumulación? ¿distribución? ¿punto de interés?
   - **POSICIÓN-EN-GIRO** (coordenada temporal): canario de proceso (>15d del pivote), canario de giro (t-1/t-2), confirmación (t=0), rezagada (t+1/t+2), FUERA/ENTRE.
   - **CONFIANZA**: tier §3.3 (ANECDOTAL→ROBUST), N_indep, CI95 Clopper-Pearson.
3. **Medir la huella multi-escala:** gradiente del estado en zz25 (corto), zz50 (medio), zz75 (largo). Escalado por volatilidad realizada. No comparar crudos.
4. **Impact ratio** (§2.D): de las N veces que la estación alcanzó este estado, ¿cuántas cayeron DENTRO del rango del giro (t±2) vs fuera? Corregido por densidad de pivotes. **Ex-ante** (el giro futuro no se usa para medir — el pivote se detecta en tiempo real por confirmación de pierna).
5. **Emitir veredicto por vela:**
   ```
   { fecha, estación, D1, D2, D3,
     firma_estado: <proceso>,
     posicion: <canario_proceso|canario_giro|confirmación|rezagada|fuera>,
     huella: {zz25: señ, zz50: señ, zz75: señ},   # alineada↑/↓ o divergente
     impact_ratio: x/y,
     tier: <§3.3>, n_indep: N, ci95: [lo,hi],
     voto_direccional: {long: p, short: q},      # probabilidad, no punto
     alerta_preliminar: "<texto>"                # si aplica
   }
   ```

### Regla de emisión obligatoria
Cada subagente **emite veredicto para TODA vela** incluida la "aleatoria" — nunca se queda callado. Si "no hay patrón", dice "aleatoria/no-patrón con confianza X" (la ausencia de patrón también es un dato — pero solo con su CI95, no como verdad).

### Regla: no tratar la rareza como ruido
Si un estado es escaso (N_indep≤5, tier LOW) pero muestra patrón consistente, el subagente lo **conserva y etiqueta como hipótesis** con su rareza %, NO lo elimina. La rareza se reporta como contexto (feature), nunca como criterio de borrado.

---

## PARTE 2 — AGENTE CURADOR (1, recibe las 11 salidas)

### Rol
Recibe los 11 reportes por vela y **saca la verdad**: determina la condición de mercado, el forecast probabilístico y las alertas. Es quien **construye el modelo que opera**.

### Proceso por vela
1. **Fusionar los 11 veredictos** de la vela.
2. **Confluencia:** detectar cuándo ≥2 estaciones independientes apuntan al mismo estado/giró el mismo día. La confluencia de señales → condición de mercado, no 1 resultado.
3. **Pesos por credibilidad:** cada voto se pondera por su tier/N_indep (no uniforme). Un voto ROBUST pesa más que uno LOW — pero el LOW no se descarta, aporta su evidencia.
4. **Detectar divergencia cross-escala global:** "corto apunta abajo, largo nivelado/arriba → probable rebote" — como señal débil alineada con el prior, escalada por vol, con su incertidumbre.
5. **Determinar condición de mercado:**
   ```
   { fecha,
     estado_mercado: <miedo|euforia|acumulación|distribución|continuación|desacuerdo|neutral>,
     exageracion: "miedo/euforia — sesgo fat-tail",
     p_giro_floor: <probabilidad de giro en H>,
     p_giro_ceiling: <...>,
     n_estaciones_confluentes: N,
     alertas: [ {tipo: METAR|TAF|SIGMET|NOTAM, mensaje, atribuciones} ],  # cada alerta cita N_indep+CI95+estaciones
     voto_democratizado: {long, short, neutral}   # agregado probabilístico
   }
   ```
6. **Emitir alertas con atribución** (dato mata relato): cada SIGMET/NOTAM cita qué estaciones, con qué N_indep y CI95 lo sustentan.

### El modelo que opera = el curador calibrado sobre el benchmark
El curador **aprende la verdad** del benchmark vela a vela histórico: ajusta sus pesos de confluencia a lo que la data muestra que funciona (con N honesto, no sobre 37 filas). No es una red profunda sobre pocas muestras — es **fusión evidencial calibrada** (Dempster-Shafer / soft-vote ponderado por N_indep) verificada OOS por episodios (2000, 2008, 2011, 2020, 2022).

---

## PARTE 3 — SALIDAS DEL COMITÉ

1. **Benchmark por estación** (`benchmark_{estación}.json`): para cada vela, el veredicto de la estación. Permite auditar qué estación anticipa mejor cada tipo de giro, con N_indep y CI95.
2. **Registro del curador** (`curador_registro.json`): por vela, estado de mercado + forecast + alertas + atribuciones.
3. **Modelo calibrado** (`modelo_confluencia.json`): pesos aprendidos, con N_indep, validez OOS por episodio, CI95.
4. **Ranking de confluencias canarias** (`confluencias_canarias.json`): pares/tripleas de estaciones que cuando coinciden anticipan giros (con lift sobre base-rate y CI95 excluyendo nulo).

---

## PARTE 4 — VERIFICACIÓN DE LA "VERDAD"

Antes de aceptar cualquier conclusión del comité:

1. **N honesto:** toda métrica usa N_indep (de-clustered), reportar N_crudo aparte. Nunca N ≤13 como "verdad" sin CI95.
2. **Contra el nulo:** un "canario" solo es tal si CI95 de lift excluye 1.0 (base-rate de pivotes). Verificar con bootstrap de permutación.
3. **OOS:** el modelo se valida en episodios separados (2000, 2008, 2011, 2020, 2022). Si el patrón solo se repite en los 2 pánicos que lo generaron, es memoria de muestra, no learnable.
4. **Dato mata relato:** toda alerta del curador es reproducible desde los parquets; nada se inventa.
5. **Ex-ante:** la métrica posicional nunca usa el pivote futuro — se detecta por confirmación de pierna, no por lookahead.

---

## PARTE 5 — RECURSO / LÍMITES

- **No redes profundas sobre la tabla de señales** (N≈37, N_indep≈3-14 → sobreajuste garantizado). La fusión es evidencial/bayesiana calibrada, no un MLP.
- **No tratar lo raro como ruido:** re-pesar por 1/N_indep, elegir modelo por macro-F1/rare-class recall, emisión obligatoria, score de anomalía como feature.
- **Auditabilidad:** toda salida atribuible a N_indep/CI95/estaciones/escalas. Un intérprete black-box es inaceptable.

---

## PARTE 6 — ORDEN DE EJECUCIÓN (Opción B — observar, registrar, aprender)

```
FASE 1: Benchmark en paralelo (OBSERVAR)
  Lanzar 11 subagentes (uno por estación) — cada uno recorre las 8,453 velas
  sobre el SPY, emite su serie de veredictos. Paralelos (máx. 3 concurrentes).
  → Escriben 11 × benchmark_{estación}.json

FASE 2: Curador observador (REGISTRAR)
  El curador recibe las 11 series, fusiona por vela, determina estado de mercado,
  emite forecast + alertas con atribución.
  → Escribe curador_registro.json (diagnóstico en vivo, dato a dato)

FASE 3: Modelador-aprendiz (APRENDER)
  Lee benchmark_*.json + curador_registro.json sobre todo el histórico.
  Calibra pesos de confluencia — qué combinación de mundos anticipa giros reales
  vs falsos — con N honesto, contra el nulo, OOS por episodio (2000, 2008, 2011,
  2020, 2022), ex-ante.
  → Escribe modelo_confluencia.json + confluencias_canarias.json

FASE 4: Entrega
  El modelo que opera (modelo_confluencia.json calibrado OOS) + ranking de
  confluencias canarias + resumen ejecutivo.
```

---

## Entregables finales (por actor)

| Actor | Archivo(s) | Función |
|:------|:-----------|:--------|
| **11 agentes** | `benchmark_{estación}.json` × 11 | Observación vela a vela de cada mundo |
| **Curador observador** | `curador_registro.json` | Diagnóstico + forecast fusionado, en vivo |
| **Modelador-aprendiz** | `modelo_confluencia.json` | **El modelo que opera** — pesos calibrados OOS |
| **Modelador-aprendiz** | `confluencias_canarias.json` | Pares/tríadas de mundos que anticipan con lift |
| **Curador/Modelador** | `alertas_historico.json` + resumen ejecutivo | SIGMET/NOTAM atribuidas + qué estaciones son canarias reales |

**Gana la verdad**: si tras validar OOS una estación o confluencia no muestra edge contra el nulo, se baja — sin importar cuánto "significó" in-sample.