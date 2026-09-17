# PROMPT: GENERAR 37 FICHAS DE INTELIGENCIA DE SEÑAL + 1 DE CONFLUENCIA

**Propósito:** Un solo script en background que produce:
- 37 archivos `data/research/intelligence/senales/[senal].json` — inteligencia completa por señal
- 1 archivo `data/research/intelligence/confluencia.json` — inteligencia de confluencia

**No más interpretación.** Un agente lee el JSON y sabe todo: timing, drawdown, D1×D2×D3 usado, overflow, confiabilidad, recomendación.

---

## Output: 37 archivos de señal

### `data/research/intelligence/senales/cascade_reversal.json`

```json
{
  "senal": "cascade_reversal",
  "tipo": "exit",
  "blanco": "MAX",
  "version": "2.0-homologada",

  "poblacion": {
    "n_episodios": 219,
    "n_barras_totales": 238,
    "fire_rate_pct": 2.82,
    "cadencia_1_en_n_barras": 38.6,
    "duracion_episodio": {"mean": 1.09, "median": 1.0, "p90": 1.0},
    "es_diamante": false,
    "tier_rareza": "ROBUST"
  },

  "timing": {
    "precision": "COINCIDENTE",
    "t_2_pct": 0.9,
    "t_1_pct": 3.7,
    "t_0_pct": 52.4,
    "t_1_ret_pct": 11.9,
    "t_2_ret_pct": 10.1,
    "entre_pct": 21.0,
    "delta_medio_barras": 1.9,
    "rendimiento_por_slot": {
      "t=0": {"n": 118, "hit_rate": 0.856, "ev": 0.0198},
      "ENTRE": {"n": 61, "hit_rate": 0.131, "ev": -0.0204}
    }
  },

  "first_passage": {
    "zz25": {"n": 219, "hit_rate": 0.539, "hit_neto": 0.106, "ev_neto": 0.0062,
             "profit_factor": 1.17, "mae_medio": -0.0186, "mae_p10": -0.007,
             "mfe_medio": 0.0225, "bars_medio": 6.4, "p_value_binom": 0.001},
    "zz50": {...},
    "zz75": {...}
  },

  "perfil_regimen": {
    "zz25_alza": {"n": 92, "hit_rate": 0.87, "fav_neto": 0.0124, "p_value": 0.0, "pf": 7.42},
    "zz25_baja": {"n": 135, "hit_rate": 0.326, "fav_neto": -0.0136, "p_value": 1.0}
  },

  "drawdown_y_riesgo": {
    "max_drawdown": -0.087,
    "max_consecutive_losses": 12,
    "avg_loss": -0.018,
    "avg_win": 0.035,
    "profit_factor": 1.17,
    "kelly_fraction": 0.08,
    "sharpe_anualizado": 0.85
  },

  "confiabilidad": {
    "p_value_binom": 0.001,
    "p_bonferroni": 0.033,
    "p_BH": 0.008,
    "significativo_BH": true,
    "significativo_bonferroni": true,
    "dsr_contribucion": 0.47,
    "independencia_F3": 0.48,
    "techo_mejora_F3": 0.52
  },

  "recomendacion_operativa": {
    "rol": "ESTRUCTURAL",
    "escala_optima": "zz75",
    "mejor_celda": "zz25|ALZA",
    "precision_temporal": "COINCIDENTE — confirma techos",
    "condiciones": "Solo en regimen ALZA. En BAJA pierde edge.",
    "kelly_sugerido": 0.08
  }
}
```

---

## Output: 1 archivo de confluencia

### `data/research/intelligence/confluencia.json`

```json
{
  "confluencias": {
    "cascade_reversal + credit_stress": {
      "n_coincidencias": 12,
      "tipo": "REFORZANTE",
      "hit_rate_combinado": 0.83,
      "ev_neto_combinado": 0.021,
      "independencia": "BAJA — 60% de overlap en estaciones VIX/CREDIT"
    },
    "pcr_put_panic + vix_crisis_spike": {
      "n_coincidencias": 8,
      "tipo": "REDUNDANTE",
      "hit_rate_combinado": 0.75,
      "ev_neto_combinado": 0.015,
      "independencia": "MUY BAJA — mismas estaciones, mismo D1=5"
    }
  },
  "overflow_multiestacion": {
    "T2+_simultaneo": {"n_episodios": 15, "spy_ret_promedio": -0.035, "peor_caso": -0.12},
    "T3+_simultaneo": {"n_episodios": 3, "spy_ret_promedio": -0.068, "peor_caso": -0.12}
  }
}
```

---

## Reglas

1. **No hay interpretación.** El JSON es la inteligencia. Un agente lo lee y sabe.
2. **No tocar fact stores.** Son física atómica. La inteligencia de señales es aparte.
3. **37 archivos de señal** (uno por cada señal del ranking v2.0).
4. **1 archivo de confluencia** que cruza pares de señales + overflows multi-estación.
5. **Background.** `terminal(background=true, notify_on_complete=true)`.

---

## Verificación

```bash
ls data/research/intelligence/senales/*.json | wc -l  # 37
python3 -c "
import json
c = json.load(open('data/research/intelligence/senales/cascade_reversal.json'))
print(c['senal'], c['timing']['precision'], c['confiabilidad']['p_BH'])
"
python3 -c "
import json
c = json.load(open('data/research/intelligence/confluencia.json'))
print(len(c['confluencias']), 'pares analizados')
"
```