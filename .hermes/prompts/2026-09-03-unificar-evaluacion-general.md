# PROMPT: Unificar la Evaluación de Señales al Evaluador GENERAL (disparo en todo el continuo, métrica Vela-a-Vela)

**Fecha:** 03-Sep-2026
**Ejecutor:** Gemini
**Decisión del arquitecto:** El sistema DEBE calificar las señales con el **evaluador GENERAL** (`evaluador_general.py`) que:
1. **Evalúa el disparo en TODA la data continua** (no solo cuando coincide con un pivote zigzag)
2. **Emplea la métrica del Vela-a-Vela** (first-passage OHLC intrabar, hit/loss al primer toque de barrera, drawdown MAE/MFE)
3. **Califica el disparo real de la señal** donde aparece (no solo en pivotes)

**Contexto del error verificado:**
- `evaluador_vela_a_vela.py` (VAV) solo evalúa señales que **COINCIDEN con un pivote** → ignora ~62% de la actividad real (ej. panico_total: 53 velas activas, solo 20 en pivotes).
- El ranking actual (walkthrough 22:57) reportó resultados "sospechosos" (sv5t HR 86.4%, panico_total EV +2.08%) calculados SOLO sobre pivotes → sesgo de ancla.
- Además, el criterio de descubrimiento (`medicion.py` con `next_leg`) difiere del de re-evaluación (VAV con first_passage) → resultados incomparables.

**La corrección:** el GENERAL ya implementa lo decidido (episodios continuos + first_passage OHLC + filtro inception). Debe convertirse en la fuente de verdad de calificación.

---

## TAREA

### 1. Confirmar que `evaluador_general.py` es el evaluador correcto
Verificar en el código que:
- Evalúa episodios continuos desde la primera barra activa de la señal (`build_episodes`) — NO solo pivotes
- Usa `first_passage_bar` OHLC (hit al toque de barrera ±scale, sin time-stop o con el definido)
- Calcula drawdown (mae/mfe) por episodio
- Filtra por `fecha_inicio_valida` (inception D0)
- Baselines incondicionales por escala/ blanco

### 2. Regenerar la evaluación GENERALIZADA para las 36 señales
Ejecutar `evaluar_condicion_booleana` para cada señal registrada en `_CERTEZA`, sobre el lake completo, con:
- Su `blanco` (MIN/MAX) y su `fecha_inicio_valida`
- Las 3 escalas (zz25, zz50, zz75)
- Métricas: hit_rate, lift vs baseline, EV, MAE/MFE (drawdown), bars, n_episodes, n_indep (de-clustering)

**Salida:** `data/research/signals/evaluacion_generalizada_lake.json` (esto YA se generó en el walkthrough — verificar que esté correcto y completo).

### 3. Comparar los resultados GENERALIZADOS vs VAV (el hallazgo clave)
Para las señales "sospechosas" (sv5t_silent_distribution, panico_total, vix_crisis_spike, fg_extreme_fear):
- Reportar: N episodios (general), N solo-pivote (VAV), y la diferencia
- Reportar: HR/lift/EV en ED presencial es con el GENERAL
- **Determinar si el edge (86.4% sv5t, +2.08% panico_total) se SOSTIENE cuando se evalúa en el continuo**, o era un artefacto de la selección por pivote

### 4. Re-computar el ranking maestro con los números GENERALIZADOS
`consolidar_ranking.py` debe consumir la evaluación GENERAL (continuo), no la VAV (solo pivote).
- Re-clasificar: VALIDADA/DEGRADADA/DIAMANTE/CANDIDATA con el criterio unificado
- Mantener control FDR (Benjamini-Hochberg) y DSR

### 5. Documentar la metrología única en cada celda del ranking
Cada señal del ranking debe reportar explícito:
- `criterio`: "first_passage OHLC continuo"
- `unidad`: "episodio continuo (primera barera activa)"
- `blanco`: MIN/MAX
- `inception`: fecha_inicio_valid a
- `escal a`

---

## VERIFICACIÓN DE ACEPTACIÓN

```bash
# 1. La evaluación generalizada NO depende de pivotes: n_episodes > solo-pivote
python << 'EOF'
import json
ev = json.load(open('data/research/signals/evaluacion_generalizada_lake.json'))
# para sv5t y panico_total, comparar n_episodes vs el N del VAV
print(f"sv5t_general n_episodes: {ev['sv5t_silent_distribution']['n_episodes']} vs VAV 22")
print(f"panico_total_general n_episodes: {ev['panico_total']['n_episodes']} vs VAV 29 (o 20 en pivotes)")
EOF

# 2. El ranking reporta criterio/unidad por celda
python << 'EOF'
import json
rank = json.load(open('data/research/signals/ranking_maestro.json'))
for item in rank['ranking'][:3]:
    assert 'criterio' in item and item['criterio'] == 'first_passage_ohlc_continuo'
    print(f"OK {item['senal']}: {item['criterio']}")
EOF
```

## REGLAS
- **El GENERAL es la fuente de verdad** para calificar señales (disparo en continuo, métrica vela-a-vela first-passage OHLC).
- **Unificar criterio** — descubrimiento y ranking deben usar el mismo forward/metodología.
- **No usar solo-pivote** para concluir edge — es sesgo de ancla.
- **Dato mata relato** — comparar el edge en VAV vs GENERAL y reportar la diferencia honestamente.
- **Mantener** política de inception (D0), OHLC, control FDR/DSR.
- **NO** revertir la corrección de `sigma_overflow` ni la política — esto es la fase de consolidación de criterio.