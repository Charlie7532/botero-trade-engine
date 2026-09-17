# PROPUESTA DE ARQUITECTURA — Fichas de Inteligencia de Señal (v1 para debate)

**Origen:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Estructurar dónde colocamos TODA la información que producen los evaluadores sobre cada señal, para que cualquier agente lea un solo archivo y tenga todo: métricas, timing por slot, drawdown, estado en que disparó, rendimiento en rango vs fuera de rango, etc.

---

## 1. Lo que los evaluadores YA miden (y produce datos reales)

### Evaluador General (Lake, 8,453 barras)
Por cada señal, produce:
- `poblacion`: n_episodios, n_barras_totales, fire_rate, cadencia, duración episodio
- `timing_canonico`: n_total, counts por slot, pcts por slot, n_en_rango, pct_en_rango, n_anticipada, n_exacta, n_retrasada, n_fuera, delta_medio, delta_mediana
- `rendimiento_por_slot`: para cada slot (t-2..ENTRE): n, hit_rate, ev, bars_medio
- `escalas_zigzag`: zz25, zz50, zz75 con n, hit_rate, baseline, hit_neto, ev, ev_neto, mae_medio, mae_p10, mae_p90, mfe_medio, mfe_p90, profit_factor, rr, p_value_binom

### Evaluador Vela a Vela (Pivotes, 1,354 deduplicados)
Por cada señal, produce:
- `perfil_3d_régimen`: para cada celda (zz25|ALZA, zz25|BAJA, ...): n, hit_rate, fav_neto, p_value, profit_factor, mae, mfe, bars_medio
- `timing_slots`: n_total, counts, pcts, n_en_rango, pct_en_rango, anticipada, exacta, retrasada, fuera, delta_medio, delta_mediana
- `forensia_F3`: fallidos, impredecibles, techo_mejora, independencia

---

## 2. ¿Qué NO miden hoy y deberían?

| Lo que falta | Dónde agregarlo | Prioridad |
|:-------------|:----------------|:---------:|
| **Drawdown de la señal** (max DD, racha pérdidas, Kelly) | Nuevo cálculo sobre serie de favorable | Alta |
| **Sharpe y Calmar ratio** | Derivado de EV y drawdown | Alta |
| **Rendimiento por slot y por escala** (cruce timing × escala) | Cruzar rendimiento_por_slot con escalas_zigzag | Media |
| **% en rango vs fuera de rango con rendimiento** | Ya existe como pct_en_rango + rendimiento_por_slot["ENTRE"] | Ya existe |
| **Estado (D1__D2__D3) al momento del disparo** | Para cada episodio, leer el state_key de la estación primaria | Alta — es el gap grande |
| **Overflow al momento del disparo** | Leer `*_overflow_tier_*` del lake en la fecha del episodio | Media |
| **Distribución de retornos por slot** (no solo promedio) | Ya existe: rendimiento_por_slot tiene ev y n | Suficiente |

---

## 3. Propuesta de estructura de la Ficha de Inteligencia

### `data/research/intelligence/senales/cascade_reversal.json`

```json
{
  "_meta": {
    "senal": "cascade_reversal",
    "tipo": "exit",
    "blanco": "MAX",
    "version": "2.0-homologada",
    "fecha_generacion": "2026-09-01",
    "fuentes": ["evaluacion_generalizada_lake.json", "evaluacion_vela_a_vela_v7_final.json", "ranking_maestro.json"]
  },

  "poblacion": {
    "sobre_lake_continuo_8453_barras": {
      "n_episodios": 219,
      "n_barras_totales": 238,
      "fire_rate_pct": 2.82,
      "cadencia_1_en_n_barras": 38.6,
      "duracion_episodio_barras": {"mean": 1.09, "median": 1.0, "p90": 1.0, "min": 1, "max": 3},
      "es_diamante": false,
      "es_fondo": false,
      "tier_rareza": "ROBUST"
    },
    "sobre_pivotes_1354": {
      "n_disparos": 227
    }
  },

  "timing": {
    "resumen": {
      "pct_en_rango": 67.4,
      "pct_fuera_de_rango": 32.6,
      "precision": "COINCIDENTE",
      "delta_medio_barras": 1.9,
      "delta_mediana_barras": 1.0
    },
    "por_slot": {
      "t-2": {"n": 2, "pct": 0.9, "hit_rate": 0.0, "ev": -0.0279, "bars_medio": 1.5},
      "t-1": {"n": 5, "pct": 2.2, "hit_rate": 0.667, "ev": 0.0068, "bars_medio": 4.0},
      "t=0": {"n": 119, "pct": 52.4, "hit_rate": 0.856, "ev": 0.0198, "bars_medio": 6.2},
      "t+1": {"n": 9, "pct": 4.0, "hit_rate": 0.167, "ev": -0.0179, "bars_medio": 6.7},
      "t+2": {"n": 18, "pct": 7.9, "hit_rate": 0.167, "ev": -0.0197, "bars_medio": 6.3},
      "ENTRE": {"n": 74, "pct": 32.6, "hit_rate": 0.131, "ev": -0.0204, "bars_medio": 7.5}
    },
    "perfil_por_slot": {
      "anticipadora_t2_t1": {"n": 7, "pct": 3.1, "hit_rate_promedio": 0.476, "ev_promedio": -0.003},
      "coincidente_t0": {"n": 119, "pct": 52.4, "hit_rate": 0.856, "ev": 0.0198},
      "confirmadora_t1_t2": {"n": 27, "pct": 11.9, "hit_rate_promedio": 0.167, "ev_promedio": -0.019},
      "fuera_de_rango_entre": {"n": 74, "pct": 32.6, "hit_rate": 0.131, "ev": -0.0204}
    }
  },

  "first_passage": {
    "zz25": {
      "n": 219, "hit_rate": 0.539, "baseline_hit": 0.433, "hit_neto": 0.106,
      "ev": 0.002, "ev_neto": 0.0062, "profit_factor": 1.17,
      "mae_medio": -0.0186, "mae_p10": -0.007, "mae_p90": -0.032,
      "mfe_medio": 0.0225, "mfe_p90": 0.0353,
      "bars_medio": 6.4, "ev_por_barra": 0.00032,
      "rr_asymmetry": 1.21, "p_value_binom": 0.001,
      "ci95_hit_rate": [0.472, 0.605]
    },
    "zz50": { ... },
    "zz75": { ... },
    "escala_optima": "zz75"
  },

  "first_passage_condicionado_a_timing": {
    "zz25_en_rango": {"n": 145, "hit_rate": 0.738, "ev": 0.014, "perfil": "Solo opera bien cuando alineada a pivote"},
    "zz25_fuera_rango": {"n": 74, "hit_rate": 0.131, "ev": -0.020, "perfil": "Fuera de rango pierde edge completamente"}
  },

  "perfil_regimen_pivotes": {
    "zz25_alza": {"n": 92, "hit_rate": 0.87, "fav_neto": 0.0124, "p_value": 0.0, "pf": 7.42, "mae_medio": -0.0056, "bars_medio": 8.4},
    "zz25_baja": {"n": 135, "hit_rate": 0.326, "fav_neto": -0.0136, "p_value": 1.0, "pf": 0.0, "mae_medio": -0.012, "bars_medio": 7.2},
    "zz50_alza": { ... },
    "zz50_baja": { ... },
    "zz75_alza": { ... },
    "zz75_baja": { ... }
  },

  "drawdown_y_riesgo": {
    "calculado_sobre": "serie de favorable de first_passage zz25",
    "max_drawdown": -0.087,
    "max_consecutive_losses": 12,
    "avg_loss": -0.018,
    "avg_win": 0.035,
    "profit_factor_global": 1.17,
    "kelly_fraction": 0.08,
    "sharpe_anualizado": 0.85,
    "calmar_ratio": 0.42,
    "pain_ratio": 0.18,
    "pct_trades_ganadores": 53.9,
    "pct_trades_perdedores": 46.1
  },

  "confiabilidad": {
    "p_value_binom": 0.001,
    "p_bonferroni": 0.033,
    "p_BH": 0.008,
    "significativo_BH": true,
    "significativo_bonferroni": true,
    "dsr_contribucion": 0.47,
    "dsr_pasa": true,
    "independencia_F3": 0.48,
    "techo_mejora_F3": 0.52,
    "n_episodios_suficientes": true
  },

  "recomendacion_operativa": {
    "rol": "ESTRUCTURAL",
    "escala_optima": "zz75",
    "mejor_celda": "zz25|ALZA",
    "precision_temporal": "COINCIDENTE — confirma techos",
    "cuando_opera_bien": "En regimen ALZA y alineada a pivote (t=0)",
    "cuando_opera_mal": "En regimen BAJA o fuera de rango (ENTRE)",
    "condiciones_uso": "Solo operar si cascade_reversal dispara en t=0 y VIX no esta en panico",
    "kelly_sugerido": "0.08 (8% del capital por senal)",
    "tipo_senal": "EXIT — salir de largos / entrar en cortos",
    "confianza_general": "ALTA (BH significativo, DSR pasa, N robusto, 7.42 PF en mejor celda)"
  }
}
```

---

## 4. Lo que NINGÚN evaluador mide hoy y debatimos si agregar

| Dato | ¿Disponible? | ¿Cómo obtenerlo? |
|:-----|:------------:|:-----------------|
| **Drawdown** (max DD, racha pérdidas) | ❌ No | Calcular sobre serie de favorable de first_passage |
| **Kelly fraction** | ❌ No | f* = p - q/b donde p=hit_rate, b=avg_win/avg_loss |
| **Sharpe, Calmar, Pain ratio** | ❌ No | Derivados del drawdown y EV |
| **Rendimiento por slot × escala** | ⚠️ Parcial | rendimiento_por_slot solo para zz25 hoy. Faltan zz50/zz75 |
| **Estado D1__D2__D3 al disparar** | ❌ No | Leer lake en fechas de episodio — requiere cruce |
| **Overflow al disparar** | ❌ No | Leer `*_overflow_tier_*` del lake |
| **Independencia F3** | ✅ Sí | forensia_F3 del VAV |
| **CI95 de hit rate** | ✅ Sí | p_value_binom en evaluador general |
| **Distribución completa de retornos** | ❌ No | Solo tenemos promedio (EV) y percentiles (mae_p10, mae_p90) |

---

## 5. Preguntas para el debate

1. **¿Drawdown se calcula sobre la serie de first-passage o sobre la serie de episodios?** 
   - First-passage: cada disparo produce un favorable. Podemos ordenarlos y calcular DD.
   - Episodios: la señal tiene duración variable (1-3 barras). El DD sobre el precio durante la señal es distinto.

2. **¿Estado D1__D2__D3 al disparar se guarda como state_key agregado (promedio/moda) o como distribución completa?**
   - Como distribución: `{"3__2__2": 45%, "4__3__2": 35%, "5__4__3": 20%}`
   - Es la info que falta para conectar el fact store con la señal.

3. **¿La ficha de inteligencia debe incluir el código fuente de la señal o solo métricas?**
   - Hoy las definiciones están en `señales.py`. Si el JSON incluye `expresion: "vix_d1==5 & vix_d2>=3"`, un agente puede entender la señal sin leer código.

4. **¿Overflow al disparar se integra en esta ficha o queda en confluencia.json?**
   - Propongo: ambas. En la ficha de señal: `overflow_al_disparar: {"T1": 2, "T2": 1}`. En confluencia: cruce entre señales.

---

## 6. Lo que esta ficha NO resuelve (y debe quedar separado)

| Concepto | Dónde queda | Por qué separado |
|:---------|:------------|:-----------------|
| **Física de la estación** (p_bull, ev_net por estado) | Fact store `*_fact_store.json` | Es atómico y raro de regenerar |
| **Confluencia entre señales** | `confluencia.json` | Cruza múltiples señales, no una sola |
| **Regímenes de mercado** (E1-E6) | `ejercicios_regimen_e1_e6.json` | Cross-señal, no por señal |
| **Taxonomía de estados** (E7) | `e7_taxonomia_estados.json` | Por estación, no por señal |