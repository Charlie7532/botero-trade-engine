# EJERCICIO: Generar Inteligencia de Estación (11 archivos, data factual pura)

**Propósito:** Para cada una de las 11 estaciones METAR, barrer TODOS los state_keys
(D1__D2__D3) reales que existen en su fact store, y para cada uno medir con el
evaluador vela-a-vela qué señales disparan en ese estado y cómo performan.

**Sin conclusiones. Sin interpretaciones. Data factual pura.**

---

## Estructura de output

### `data/research/intelligence/estaciones/vix.json`

```json
{
  "estacion": "vix",
  "fecha_generacion": "2026-09-01",
  "_nota": "Data factual de medicion. Sin interpretaciones ni conclusiones.",

  "states": {
    "5__4__3": {
      "n_barras_observadas": 45,
      "pct_del_tiempo": 0.53,
      "medicion_signals": {
        "cascade_reversal": {
          "n_episodios": 12,
          "n_barras_activas": 12,
          "fire_rate_pct": 26.67,
          "timing_distribucion": {
            "t-2": {"n": 0, "hit_rate": null, "ev": null, "bars_medio": null},
            "t-1": {"n": 2, "hit_rate": 0.5, "ev": 0.008, "bars_medio": 4.0},
            "t=0": {"n": 8, "hit_rate": 0.875, "ev": 0.025, "bars_medio": 5.8},
            "t+1": {"n": 1, "hit_rate": 0.0, "ev": -0.015, "bars_medio": 6.0},
            "t+2": {"n": 0, "hit_rate": null, "ev": null, "bars_medio": null},
            "ENTRE": {"n": 1, "hit_rate": 0.0, "ev": -0.022, "bars_medio": 7.0}
          },
          "pct_en_rango": 91.67,
          "first_passage": {
            "zz25": {"n": 12, "hit_rate": 0.75, "ev": 0.018, "profit_factor": 2.1,
                     "mae_medio": -0.012, "mfe_medio": 0.028, "bars_medio": 6.2,
                     "p_value_binom": 0.042},
            "zz50": {"n": 12, "hit_rate": 0.5, "ev": 0.009, "profit_factor": 1.2, ...},
            "zz75": {"n": 12, "hit_rate": 0.25, "ev": 0.004, ...}
          },
          "drawdown": {
            "max_drawdown": -0.032,
            "max_consecutive_losses": 3,
            "avg_win": 0.035,
            "avg_loss": -0.015
          },
          "n_episodios_suficientes": true
        },
        "vix_crisis_spike": {
          "n_episodios": 8,
          "n_barras_activas": 10,
          "fire_rate_pct": 22.22,
          "timing_distribucion": { ... },
          "first_passage": { ... },
          "drawdown": { ... }
        }
      }
    },

    "3__2__2": {
      "n_barras_observadas": 970,
      "pct_del_tiempo": 11.84,
      "medicion_signals": {
        "cascade_reversal": { ... },
        "vix_crisis_spike": { ... },
        "neutral_crush_entry": { ... },
        ...y otras senales que disparen aqui
      }
    },

    ...todos los state_keys reales...
  }
}
```

---

## Reglas de ejecución

1. **Sin conclusiones.** El archivo contiene SOLO los datos de medición. Nada de
   interpretaciones como "esto es contrarian" o "esto es de tendencia". Data pura.

2. **Barrer todos los state_keys** reales de la estación (los que existen en el
   lake con N≥3). No solo los top 10. Todos los que tengan datos suficientes.

3. **Para cada state_key**, ejecutar el evaluador vela-a-vela (`evaluador_general.py`
   o `arnes/medicion.py`) sobre todos los días donde la estación está en ese estado,
   y medir qué señales del catálogo disparan ahí.

4. **Para cada señal que dispara** en ese estado, registrar:
   - N episodios, fire rate
   - Distribución de timing (t-2..ENTRE con hit_rate y EV)
   - First-passage (zz25, zz50, zz75 con hit_rate, ev, pf, mae, mfe, bars, p_value)
   - Drawdown calculado (max_dd, racha pérdidas, avg_win, avg_loss)

5. **No filtrar por BH o Bonferroni.** Incluir todas las señales que disparen,
   incluso con N bajo. El consumidor del dato decide qué filtrar.

6. **Output:** `data/research/intelligence/estaciones/{estacion}.json`

7. **Tiempo estimado:** El barrido completo de 11 estaciones × ~150 state_keys
   cada una puede tomar varias horas. Ejecutar en background con
   `terminal(background=true, notify_on_complete=true)`.

---

## Verificación

```bash
# 11 archivos generados
ls data/research/intelligence/estaciones/*.json | wc -l  # 11

# VIX debe tener ~150 state_keys
python3 -c "
import json
vix = json.load(open('data/research/intelligence/estaciones/vix.json'))
print(f'VIX: {len(vix[\"states\"])} state_keys medidos')
for sk, data in list(vix['states'].items())[:3]:
    n_senales = len(data['medicion_signals'])
    n_barras = data['n_barras_observadas']
    print(f'  {sk}: {n_barras} barras, {n_senales} senales que disparan')
"

# Data factual pura — sin interpretaciones
python3 -c "
import json
vix = json.load(open('data/research/intelligence/estaciones/vix.json'))
sk = list(vix['states'].keys())[0]
senal = list(vix['states'][sk]['medicion_signals'].keys())[0]
print(f'Data factual: {senal} en {sk}')
print(f'  Keys: {list(vix[\"states\"][sk][\"medicion_signals\"][senal].keys())}')
# NO debe contener 'interpretacion', 'recomendacion', 'significado', etc.
llaves_texto = [k for k in vix['states'][sk]['medicion_signals'][senal] if k in ['interpretacion','recomendacion','significado','conclusion']]
assert len(llaves_texto) == 0, f'HAY INTERPRETACIONES: {llaves_texto}'
print('  ✅ Sin interpretaciones — data factual pura')
"
```