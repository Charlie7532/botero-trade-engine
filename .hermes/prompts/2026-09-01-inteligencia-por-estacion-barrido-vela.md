# EJERCICIO: Inteligencia de Estación — Barrido Vela a Vela (11 archivos, data factual)

**Propósito:** Para cada una de las 11 estaciones METAR, caminar el lake vela a vela
UNA sola vez, registrar en qué estado (D1__D2__D3) está la estación en cada barra,
evaluar qué señales del catálogo disparan, y acumular la estadística por estado.

**Misma lógica que `v3_fact_table_engine.py` pero para señales en vez de física.**

---

## Algoritmo

```
1. Cargar lake (8,453 barras)
2. Cargar señales (37 del ranking v2.0)

3. Para cada barra i del lake:
   a. Leer vix_sk → estado actual "5__4__3"
   b. Evaluar las 37 señales → ¿cuáles disparan en esta barra?
   c. Para cada señal que dispara:
      - Acumular: contador[estado][senal] += 1
      - Registrar: fecha, spy_ret_1d, timing vs pivote
      - Si primer barra del episodio: ejecutar first_passage

4. Al final, para cada estado de cada estación:
   - Agregar: N episodios, hit_rate, EV, timing, drawdown
   - Output: 1 archivo por estación
```

**No hay conclusiones. Solo data factual. El consumidor interpreta.**

---

## Output

### `data/research/intelligence/estaciones/vix.json`

```json
{
  "estacion": "vix",
  "fecha_generacion": "2026-09-01",
  "_nota": "Data factual. Barrido vela a vela del lake (8,453 barras).",

  "states": {
    "5__4__3": {
      "n_barras": 45,
      "pct_del_tiempo": 0.53,
      "senales": {
        "cascade_reversal": {
          "n_episodios": 12,
          "n_barras_activas": 14,
          "fire_rate_pct": 26.67,
          "timing": {
            "n_en_rango": 11,
            "pct_en_rango": 91.67,
            "distribucion": {
              "t-2": {"n": 0, "hit_rate": null, "ev": null},
              "t-1": {"n": 2, "hit_rate": 0.5, "ev": 0.008},
              "t=0": {"n": 8, "hit_rate": 0.875, "ev": 0.025},
              "t+1": {"n": 1, "hit_rate": 0.0, "ev": -0.015},
              "t+2": {"n": 0, "hit_rate": null, "ev": null},
              "ENTRE": {"n": 1, "hit_rate": 0.0, "ev": -0.022}
            }
          },
          "first_passage": {
            "zz25": {
              "n": 12, "hit_rate": 0.75, "ev": 0.018,
              "profit_factor": 2.1, "mae_medio": -0.012,
              "mfe_medio": 0.028, "bars_medio": 6.2,
              "p_value_binom": 0.042
            },
            "zz50": {"n": 12, "hit_rate": 0.5, "ev": 0.009, ...},
            "zz75": {"n": 12, "hit_rate": 0.25, "ev": 0.004, ...}
          },
          "drawdown": {
            "max_drawdown": -0.032,
            "max_consecutive_losses": 3,
            "avg_win": 0.035,
            "avg_loss": -0.015
          }
        }
      }
    },

    "3__2__2": {
      "n_barras": 970,
      "pct_del_tiempo": 11.84,
      "senales": {
        "cascade_reversal": { ... },
        "vix_crisis_spike": { ... },
        "neutral_crush_entry": { ... }
      }
    },

    "0__0__0": {
      "n_barras": 0,
      "pct_del_tiempo": 0.0,
      "senales": {}
    }
  }
}
```

---

## Reglas

1. **Data factual pura.** Sin interpretaciones, sin conclusiones, sin recomendaciones.
2. **Un solo barrido** del lake. No re-ejecutar el evaluador por estado.
3. **Para cada barra:** leer el state_key de la estación (vix_sk, bsi_sk, etc.).
4. **Evaluar las 37 señales** del ranking v2.0. Las que disparan se acumulan en ese estado.
5. **Incluir TODOS los state_keys** con N≥1. No solo los top 10.
6. **Timing:** para cada episodio, calcular distancia al pivote más cercano y clasificar
   en los 6 slots canónicos (t-2, t-1, t=0, t+1, t+2, ENTRE).
7. **First-passage:** desde primer barra del episodio, medir zz25/50/75 con hit_rate, EV,
   MAE, MFE, profit_factor, p_value.
8. **drawdown** — calcular sobre la serie cronológica de `favorable` de la señal en ese estado:
- `max_drawdown`: peor caída desde pico de equity acumulada
- `max_consecutive_losses`: racha más larga de trades perdedores consecutivos
- `avg_win`: promedio de favorable cuando gana
- `avg_loss`: promedio de favorable cuando pierde (absoluto)
- `profit_factor`: suma wins / |suma losses|
- `kelly_fraction`: f* = p - q/b donde p=hit_rate, b=avg_win/avg_loss
- `sharpe_anualizado`: EV / std(favorable) * sqrt(252)
- `calmar_ratio`: EV_anual / |max_drawdown|

El evaluador vela a vela mide trade por trade pero NO los encadena en una secuencia.
El barrido SÍ lo hace — porque camina el lake cronológicamente y tiene el orden temporal.
9. **Output:** 11 archivos en `data/research/intelligence/estaciones/{estacion}.json`.
10. **Ejecutar en background.** El barrido completo tomará ~10-30 min.

---

## Verificación

```bash
# 11 archivos generados
ls data/research/intelligence/estaciones/*.json | wc -l  # 11

# Cada estación tiene ~50-150 state_keys
python3 -c "
import json
vix = json.load(open('data/research/intelligence/estaciones/vix.json'))
print(f'VIX: {len(vix[\"states\"])} estados medidos')
sk = list(vix['states'].keys())[0]
print(f'  {sk}: {vix[\"states\"][sk][\"n_barras\"]} barras')
print(f'  Senales en {sk}: {list(vix[\"states\"][sk][\"senales\"].keys())}')
"

# Sin interpretaciones — solo data
python3 -c "
import json
vix = json.load(open('data/research/intelligence/estaciones/vix.json'))
for sk in list(vix['states'].keys())[:3]:
    for s_name, data in vix['states'][sk]['senales'].items():
        assert 'interpretacion' not in data, f'Hay interpretacion en {sk}/{s_name}'
        assert 'recomendacion' not in data, f'Hay recomendacion en {sk}/{s_name}'
        assert 'conclusion' not in data, f'Hay conclusion en {sk}/{s_name}'
print('✅ Data factual pura — sin interpretaciones')
"
```

---

## Notas técnicas

- Usar `_get_dim(df, estacion, 0)`, `_get_dim(df, estacion, 1)`, `_get_dim(df, estacion, 2)`
  para construir el state_key desde las columnas `*_d1_bin`, `*_d2_bin`, `*_d3_bin` del lake.
- Para timing vs pivotes, usar `classify_timing_slots()` de `arnes/timing.py`.
- Para first-passage, usar `first_passage_bar()` de `evaluador_general.py`.
- El drawdown se calcula sobre la serie de `favorable` de cada señal en cada estado.
- Los state_keys que no existen en el lake (N=0) se omiten.
- Los state_keys con N<3 se incluyen pero marcar como `n_insuficiente: true`.