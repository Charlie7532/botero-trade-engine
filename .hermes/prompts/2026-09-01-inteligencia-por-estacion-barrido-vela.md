# EJERCICIO: Inteligencia de Estación — Barrido Vela a Vela (11 archivos, data factual)

**Propósito:** Para cada una de las 11 estaciones METAR, caminar el lake vela a vela
UNA sola vez, registrar en qué estado (D1__D2__D3) está la estación en cada barra,
evaluar qué señales del catálogo disparan, y acumular la estadística por estado.

**Misma lógica que `v3_fact_table_engine.py` pero para señales en vez de física.**

---

## Algoritmo

```
1. CARGAR (una vez):
   lake ← continuous_metar_lake.parquet (8,453 × 257)
   pivots ← quants_obs.pkl (1,590 pivotes SPY con pivot_date, pivot_type)
   señales[37] ← SEÑALES registry (arnes/registro.py)
   spy_close, spy_high, spy_low ← lake[spy_*].values

2. PRE-COMPUTAR MASCARAS DE SEÑALES (una vez por señal):
   Para señales DIMENSIONALES PURAS (solo _get_dim):
     → evaluar directo sobre lake (8,453 barras)
   Para señales POSICIONALES (usan pivot_type):
     → evaluar sobre quants_obs (1,590 pivotes)
     → mapear fechas al lake index

3. BARRIDO UNICO (sobre 8,453 barras):
   Para cada barra i:
     Para cada estación (11):
       sk = lake["{est}_sk"].iloc[i]
       Si sk es NaN → skip (estación no disponible en esa fecha)
       sk_key = construir desde _d1_bin, _d2_bin, _d3_bin
       Leer z_scores: {est}_z_d1, {est}_z_d2, {est}_z_d3
       Leer overflow_tiers: {est}_overflow_tier_d1, etc.
       
       Para cada señal (37):
         Si masks[señal][i] == True:
           Si es inicio de episodio (transición 0→1):
             → first_passage_bar(spy, i, zz25/50/75)
             → classify_timing_slot(date_i, pivots, lake.index)
           acumular[est][sk_key][señal] += 1
           acumular favorable, timing, etc.

4. AGREGACION (por estado × señal):
   → n_episodios, fire_rate, timing distribution (6 slots)
   → first_passage (zz25/50/75 con hit/ev/pf/mae/mfe/bars/p_value)
   → drawdown (equity curve sintética desde favorable cronológico)
   → z_scores promedio, overflow_tiers, overflow flag

5. OUTPUT: 11 archivos
   data/research/intelligence/estaciones/{estacion}.json
```

**No hay conclusiones. Solo data factual. El consumidor interpreta.**

---

## Output

### `data/research/intelligence/estaciones/vix.json`

```json
{
  "estacion": "vix",
  "fecha_generacion": "2026-09-01",
  "fecha_inicio_datos": "1993-01-01",
  "n_barras_evaluadas": 8194,
  "pct_lake_cubierto": 96.9,
  "documentation": {
    "model_purpose": "Inteligencia de estacion por state_key — barrido vela a vela",
    "state_key_format": "D1_bin__D2_bin__D3_bin",
    "d1_range": "0..5 (6 bins, Gaussian sigma)",
    "d2_range": "0..4 (5 bins, Gaussian sigma)",
    "d3_range": "0..4 (5 bins, Gaussian sigma)",
    "overflow_tiers": "T0=normal, T1=3-4σ, T2=4-5σ, T3=5-7σ, T4=7-10σ, T5=10σ+",
    "inception_dates": {
      "vix": "1993-01-01",
      "fg": "2011-02-01",
      "pcr": "2006-11-01",
      "credit": "2007-04-11",
      "vvix": "2006-03-06",
      "sv5_turbulence": "1999-01-04"
    },
    "fuentes": ["continuous_metar_lake.parquet", "quants_obs.pkl", "arnes/registro.py"]
  },

  "states": {
    "5__4__3": {
      "n_barras": 45,
      "pct_del_tiempo": 0.53,
      "z_scores": {"d1": 2.3, "d2": 1.8, "d3": 1.5},
      "overflow_tiers": {"d1": "T0", "d2": "T0", "d3": "T0"},
      "overflow": false,
      "senales": {
        "cascade_reversal": {
          "n_episodios": 12,
          "n_barras_activas": 14,
          "fire_rate_pct": 26.67,
          "evaluado_sobre": "lake_continuo",
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
            "avg_loss": -0.015,
            "profit_factor_global": 2.1,
            "kelly_fraction": 0.12
          }
        }
      }
    },

    "3__2__2": {
      "n_barras": 970,
      "pct_del_tiempo": 11.84,
      "z_scores": {"d1": 0.3, "d2": 0.1, "d3": 0.0},
      "overflow_tiers": {"d1": "T0", "d2": "T0", "d3": "T0"},
      "overflow": false,
      "senales": {
        "cascade_reversal": { ... },
        "vix_crisis_spike": { ... },
        "neutral_crush_entry": { ... }
      }
    }
  }
}
```

---

## Reglas

1. **Data factual pura.** Sin interpretaciones, sin conclusiones, sin recomendaciones.
2. **Un solo barrido** del lake. No re-ejecutar el evaluador por estado.
3. **Para cada barra:** leer el state_key de la estación (vix_sk, bsi_sk, etc.) y los
   z-scores (`*_z_d1`, `*_z_d2`, `*_z_d3`) y overflow tiers (`*_overflow_tier_*`).
4. **Señales dimensionales puras** (solo usan `_get_dim`): evaluar directo sobre lake.
   **Señales posicionales** (usan `pivot_type`): evaluar sobre quants_obs, luego mapear
   fechas al lake index. Marcar en output: `"evaluado_sobre": "lake_continuo"` o
   `"evaluado_sobre": "pivotes_quants_obs"`.
5. **Incluir TODOS los state_keys** con N≥1. No solo los top 10. **No filtrar por N.**
   Los diamantes (N<21) se identifican naturalmente al digerir la data.
6. **Timing:** para cada episodio, calcular distancia al pivote SPY más cercano
   (desde quants_obs) y clasificar en los 6 slots canónicos (t-2, t-1, t=0, t+1, t+2, ENTRE).
   Usar `classify_timing_slots()` de `arnes/timing.py` que ya maneja el merge lake+pivotes.
7. **First-passage:** desde primer barra del episodio, medir zz25/50/75 con hit_rate, EV,
   MAE, MFE, profit_factor, p_value. Usar `first_passage_bar()` de `evaluador_general.py`.
8. **Drawdown** — calcular sobre la serie cronológica de `favorable` de la señal en ese estado:
   - `max_drawdown`: peor caída desde pico de equity acumulada
   - `max_consecutive_losses`: racha más larga de trades perdedores consecutivos
   - `avg_win`: promedio de favorable cuando gana
   - `avg_loss`: promedio de favorable cuando pierde (absoluto)
   - `profit_factor_global`: suma wins / |suma losses|
   - `kelly_fraction`: f* = p - q/b donde p=hit_rate, b=avg_win/avg_loss
9. **Overflow:** registrar dentro de cada state_key, no en archivos separados:
   - `z_scores`: valores z actuales de D1, D2, D3
   - `overflow_tiers`: tier de overflow de D1, D2, D3 (T0-T5+)
   - `overflow`: true si alguna dimensión está en T1 o superior
10. **Cada estación debe declarar** `fecha_inicio_datos` y `n_barras_evaluadas` en el
    metadata del output, para que las métricas no sean comparadas ciegamente entre
    estaciones con ventanas históricas diferentes.
11. **Output:** 11 archivos en `data/research/intelligence/estaciones/{estacion}.json`.
12. **Ejecutar en background.** El barrido completo tomará ~2-5 min.

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
print(f'Inicio: {vix[\"fecha_inicio_datos\"]}, Barras: {vix[\"n_barras_evaluadas\"]}')
# Verificar overflow integrado en state_key
for sk in list(vix['states'].keys())[:3]:
    data = vix['states'][sk]
    assert 'overflow' in data, f'Falta overflow en {sk}'
    assert 'z_scores' in data, f'Falta z_scores en {sk}'
    assert 'overflow_tiers' in data, f'Falta overflow_tiers en {sk}'
print('✅ Overflow integrado en state_key')
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

# Señales posicionales marcadas correctamente
python3 -c "
import json
vix = json.load(open('data/research/intelligence/estaciones/vix.json'))
for sk, data in vix['states'].items():
    for s_name, s_data in data['senales'].items():
        assert 'evaluado_sobre' in s_data, f'Falta evaluado_sobre en {sk}/{s_name}'
print('✅ Tipo de evaluacion registrado para cada senal')
"
```