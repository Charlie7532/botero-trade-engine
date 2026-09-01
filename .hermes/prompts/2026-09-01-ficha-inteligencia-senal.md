# PROMPT: FICHA DE INTELIGENCIA DE SEÑAL — Consolidación Definitiva (E7 + E8 + Timing + Drawdown)

**Origen:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Un solo script en background que produce un JSON completo por señal con TODA la información disponible — métricas, timing, precisión, D1×D2×D3, drawdown, confiabilidad. El "dossier de inteligencia" que cualquier agente puede leer sin necesidad de cruzar 3 archivos.
**Framework:** López de Prado — Triple Barrier, DSR, Stochastic Dominance, Probability of Backtest Overfitting (PBO).

---

## Lo que ya existe (NO reinventar)

| Archivo | Contenido | Problema |
|:--------|:----------|:---------|
| `evaluacion_generalizada_lake.json` | 37 señales × poblacion + timing + escalas_zigzag | ❌ No tiene D1×D2×D3, no tiene perfil de precisión, no tiene drawdown |
| `evaluacion_vela_a_vela_v7_final.json` | ~20 señales × perfil_3d_régimen + timing_slots + F3 | ❌ No cubre todas las señales, no tiene cobertura dimensional |
| `ranking_maestro.json` | BH + Bonferroni + DSR | ❌ No tiene drawdown, no tiene perfil temporal |
| `ejercicios_regimen_e1_e6.json` | E1-E6 | ❌ Ejercicios independientes, no por señal |
| `e7_taxonomia_estados.json` | D1×D2×D3 para 11 estaciones | ❌ No cruza con señales |

---

## El Output: `ficha_inteligencia_[señal].json`

Cada señal produce un JSON con esta estructura:

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
    "es_fondo": false,
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
      "t=0": {"n": 118, "hit_rate": 0.856, "ev": 0.0198, "rr": 5.26},
      "ENTRE": {"n": 61, "hit_rate": 0.131, "ev": -0.0204, "rr": 0.88}
    }
  },

  "first_passage": {
    "zz25": {"n": 219, "hit_rate": 0.539, "baseline_hit": 0.433, "hit_neto": 0.106,
             "ev": 0.002, "ev_neto": 0.0062, "profit_factor": 1.17,
             "mae_medio": -0.0186, "mae_p10": -0.007, "mae_p90": -0.032,
             "mfe_medio": 0.0225, "mfe_p90": 0.0353,
             "bars_medio": 6.4, "ev_por_barra": 0.00032,
             "rr_asymmetry": 1.21, "p_value_binom": 0.001},
    "zz50": {...},
    "zz75": {...}
  },

  "perfil_regimen": {
    "zz25_alza": {"n": 92, "hit_rate": 0.87, "fav_neto": 0.0124, "p_value": 0.0, "pf": 7.42},
    "zz25_baja": {"n": 135, "hit_rate": 0.326, "fav_neto": -0.0136, "p_value": 1.0, "pf": 0.0}
  },

  "cobertura_dimensional": {
    "d1_usado": true,
    "d2_usado": false,
    "d3_usado": false,
    "estaciones_que_lee": [],
    "vector_estado_tipico": "3__2__2",
    "d1_5_con_d2_menor_2": {"n": 54, "wr": 0.611, "spy_ret": 0.0080, "interpretacion": "CONTRARIAN_BUY"},
    "d1_5_con_d2_mayor_2": {"n": 88, "wr": 0.216, "spy_ret": -0.0258, "interpretacion": "ABDICACION"}
  },

  "drawdown_y_riesgo": {
    "max_drawdown": -0.087,
    "max_consecutive_losses": 12,
    "avg_loss": -0.018,
    "avg_win": 0.035,
    "profit_factor": 1.17,
    "kelly_fraction": 0.08,
    "sharpe_anualizado": 0.85,
    "calmar_ratio": 0.42,
    "pain_ratio": 0.18
  },

  "confiabilidad": {
    "p_value_binom": 0.001,
    "p_bonferroni": 0.033,
    "p_BH": 0.008,
    "significativo_BH": true,
    "significativo_bonferroni": true,
    "dsr_contribucion": 0.47,
    "pasa_DSR": true,
    "n_episodios_oot": 0,
    "estabilidad_temporal": "ROBUSTA",
    "independencia_F3": 0.48,
    "techo_mejora_F3": 0.52
  },

  "recomendacion_operativa": {
    "rol": "ESTRUCTURAL",
    "escala_optima": "zz75",
    "mejor_celda": "zz25|ALZA",
    "horizonte": "30-44 barras (~1-2 meses)",
    "timing": "COINCIDENTE — confirma techos",
    "condiciones": "Solo en regimen ALZA. En BAJA pierde edge.",
    "limite": "No operar si D1 de VIX > 3 (mercado en panico absorbe la senal)"
  }
}
```

---

## El Script: `generar_fichas_inteligencia.py`

### Qué debe hacer

1. **Cargar** todos los JSONs existentes (lake, VAV, ranking, E7)
2. **Para cada señal** (37 del ranking):
   - Leer `poblacion`, `timing_canonico`, `rendimiento_por_slot`, `escalas_zigzag` del lake
   - Leer `perfil_3d_régimen`, `timing_slots`, `forensia_F3` del VAV
   - Leer `p_BH`, `p_bonferroni`, `significativo_BH`, `score_compuesto` del ranking
   - Calcular **drawdown y riesgo**:
     - `max_drawdown`: usando la serie de `favorable` de first-passage
     - `max_consecutive_losses`: racha de pérdidas consecutivas
     - `avg_loss / avg_win`: promedio de ganancias y pérdidas
     - `kelly_fraction`: Kelly óptimo = `(p * b - q) / b` donde p=hit_rate, b=avg_win/|avg_loss|
     - `sharpe_anualizado`: `EV / std(favorable) * sqrt(252)`
     - `calmar_ratio`: `EV_anual / |max_drawdown|`
   - Calcular **cobertura dimensional**:
     - Leer el código fuente de la señal (inspeccionar `_get_dim` calls)
     - Identificar D1, D2, D3 usados
     - Identificar estaciones que lee
     - Del E7, extraer qué combinaciones D1×D2×D3 son relevantes
   - **Clasificar precisión temporal**:
     - `pct_anticipada = pct_t_2 + pct_t_1`
     - `pct_coincidente = pct_t_0`
     - `pct_confirmadora = pct_t_1_ret + pct_t_2_ret`
     - Si `pct_anticipada > pct_coincidente` → ANTICIPADORA
     - Si `pct_coincidente > pct_anticipada + pct_confirmadora` → COINCIDENTE
     - Si `pct_confirmadora > pct_anticipada` → CONFIRMADORA
     - Si `pct_fuera > 50%` → SIN_ALINEACION (opera en continuo)
   - **Generar recomendación operativa** basada en todas las métricas

### Output

```
data/research/signals/fichas_inteligencia/
├── cascade_reversal.json
├── credit_stress.json
├── ...
└── resumen_ejecutivo.json   # Tabla consolidada top-10 + BH + DSR
```

---

## Qué diría López de Prado

| Principio | Lo que pregunta | Lo que responde el JSON |
|:----------|:---------------|:------------------------|
| **Deflated Sharpe Ratio** | ¿El edge es real o ruido de selección múltiple? | `pasa_DSR`, `p_BH` |
| **Triple Barrier** | ¿Tiene time-stop o horizonte infinito? | `bars_medio`, `bars_p90`, `max_barras` |
| **Probability of Backtest Overfitting** | ¿Cuántos de los N trials son falsos positivos? | `p_BH` (proxy), `dsr_contribucion` |
| **Stochastic Dominance** | ¿La distribución de retornos domina al baseline? | `ev_neto`, `hit_neto`, `profit_factor` |
| **Meta-labeling** | ¿Debemos separar dirección de tamaño? | `kelly_fraction`, `calmar_ratio` |
| **Concentration Risk** | ¿Las señales están correlacionadas? | `estaciones_que_lee`, `cobertura_dimensional` |
| **First Order vs Second Order** | ¿El edge está en la media o en la varianza? | `hit_rate` (1er orden) vs `profit_factor` (2do orden) |

---

## Reglas de Ejecución

1. **Background.** `terminal(background=true, notify_on_complete=true)`
2. **No modificar** los evaluadores existentes. Solo leer sus outputs.
3. **Si la señal no tiene datos en algún evaluador**, reportar `null` con causa.
4. **Incluir CI95** (Clopper-Pearson) para cada hit rate.
5. **Incluir drawdown** calculado sobre la serie de `favorable` del first-passage.
6. **Output único por señal** + `resumen_ejecutivo.json` con tabla consolidada.

---

## Verificación

```bash
# 1. Fichas generadas para las 37 senales
ls data/research/signals/fichas_inteligencia/*.json | wc -l

# 2. Resumen ejecutivo existe
python3 -c "import json; r = json.load(open('data/research/signals/fichas_inteligencia/resumen_ejecutivo.json')); print(f'{r[\"metadata\"][\"total_senales\"]} senales, {r[\"metadata\"][\"n_BH_significativas\"]} BH significativas')"

# 3. Drawdown calculado
python3 -c "
import json
c = json.load(open('data/research/signals/fichas_inteligencia/cascade_reversal.json'))
dd = c['drawdown_y_riesgo']
print(f'Max DD: {dd[\"max_drawdown\"]}, Kelly: {dd[\"kelly_fraction\"]}, Sharpe: {dd[\"sharpe_anualizado\"]}')
"

# 4. Perfil de precision para todas las senales
python3 -c "
import json, glob
perfiles = {}
for f in glob.glob('data/research/signals/fichas_inteligencia/*.json'):
    if 'resumen' in f: continue
    d = json.load(open(f))
    perfiles[d['senal']] = d['timing']['precision']
for s, p in sorted(perfiles.items(), key=lambda x: x[1]):
    print(f'{p:<20s} {s}')
"
```