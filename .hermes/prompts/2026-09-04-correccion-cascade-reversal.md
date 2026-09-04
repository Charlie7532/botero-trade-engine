# PROMPT: Corrección de Metrología para `cascade_reversal` — Señal de Confirmación de Pierna (no NO_OPERABLE)

**Fecha:** 04-Sep-2026
**Ejecutor:** Gemini
**Contexto:** Se descubrió la "puerta trasera `quants_mapped`" en `evaluador_general.py`. Tras auditoría técnica y discusión con el arquitecto, se estableció que **`cascade_reversal` NO es una trampa retrospectiva ni una señal que deba marcarse `NO_OPERABLE`** — es una **señal de CONFIRMACIÓN de pierna cerrada** legítima.

---

## Semántica canónica acordada

**`cascade_reversal` opera cuando una pierna del zigzag se CONFIRMA** (el `pivot_type` MIN/MAX queda sellado temporalmente). Su insumo `cascade_conviction_50` se deriva de:
- `cascade_conviction = w_bear * z_bear + w_dom * z_dom` (por pierna, `generate_quants_obs.py` L407-413)
- Es observable SOLO cuando la pierna se ha cerrado (no vela a vela vivo)

Esto la define como **señal de confirmación de giro ya ocurrido**, no retro-predicción del futuro:
> "el pivote ya pasó, pero las entradas institucionales confirman — todo depende de la convicción del pivote."

Por tanto su evaluación SOBRE pivotes confirmados es la UNIDAD CORRECTA, y su edge se mide **hacia adelante desde el cierre** — operable como un trader que entra tras la confirmación.

---

## TAREA

### 1. Re-etiquetar el modo en `evaluador_general.py`
- En `evaluar_senal` (L505-516), cuando una señal cae al fallback, **no** dejar el tag oscuro `quants_mapped`.
- Renombrario a **`pierna_confirmada`** cuando la causa sea que la señal requiere una métrica por-pierna (como cascade_conviction). Documentar en el valor `modo_ejecucion`.
- **NO** marcar `NO_OPERABLE` para las señales de confirmación de pierna. (Guard reservado SOLO para casos donde la señal no pueda evaluarse honestamente NI en continuo NI en piernas confirmadas.)

2. **Confirmar metrología del forward:** Verificar que el `first_passage_bar` en `cascade_reversal` se mide **desde la fecha del pivot confirmado hacia ADELANTE** (con barreras favorable/adversa por `blanco`). Documentar t_pos = índex del pivote corroborado.

3. **Documentar en `_CERTEZA`:** Añadir a `cascade_reversal` la nota:
   - `temporidad: "CONFIRMACION_PIERNA"` (no tiempo real vela a vela)
   - `unidad_medicion: "pierna confirmada -> forward"`

4. **Re-evaluar `cascade_reversal`** y confirmar que su edge (N, hit, EV) se presenta transparente, indicando que es sobre pivotes confirmados, y que el forward es hacia adelante.

---

## VERIFICACIÓN DE ACEPTACIÓN

```python
# 1. El modo ya no es oscuro
ev = json.load(open('data/research/signals/evaluacion_generalizada_lake.json'))
cr = ev['cascade_reversal']
assert cr['modo_ejecucion'] in ('pierna_confirmada', 'lake'), cr['modo_ejecucion']

# 2. La métrica documenta la semántica
assert 'pierna_confirmada' in cr.get('modo_ejecucion', '') or cr['modo_ejecucion']=='lake'

# 3. NO es NO_OPERABLE
assert cr['status'] == 'OK'

# 4. Forward medido desde pivote cerrado hacia adelante (revisión en código)
```

## REGLAS
- **NO marcar `cascade_reversal` como NO_OPERABLE** — es una señal de confirmación legítima. Cualquier solución que la bloquee es ERRÓNEA.
- **NO clasificar `quants_mapped` como fraude** — para señales por-pierna es la unidad natural, siempre que el forward se mida hacia adelante desde la pierna cerrada.
- Mantener la política de inception, OHLC first-passage, y el resto del pipeline intacto.
- Si existe OTRA señal cuyo fallback fuera por `pivot_type` (sesgo de posición si), distinguir: las de CONFIRMACIÓN (este caso) vs las de FILTRO DE POSICION (que sí son sesgo). Documentar ambas.