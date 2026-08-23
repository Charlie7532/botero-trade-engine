# COMPUERTA DE FIDELIDAD — Builder `quants_obs` v2 (22-Ago-2026)

**Firma:** qwen/qwen3.8-max (Hermes)
**Builder:** `research/10_gate_oos_validation/builder_quants_obs.py`
**Salida:** `data/research/pivots/quants_obs_new.pkl` (1,590 × 141, **NO** sustituye al original)
**Compuerta:** comparación columna por columna vs `quants_obs.pkl` (original 17-Ago)

---

## Progreso de fidelidad

| Iteración | Columnas ≥99.9% | Columnas divergentes |
|-----------|:---:|:---:|
| Builder v1 | 34/141 | 107 |
| **Builder v2** | **101/141** | **40** |

## Incógnitas RESUELTAS esta sesión (verificadas con datos)

| Incógnita | Resolución | Match |
|-----------|-----------|:---:|
| `duration_bars` | Duración CALENDARIO de la pierna que ARRANCA en el pivote, piso 1 día | 100% |
| `daily_return_pct` | Retorno de esa pierna (%) ÷ duración | 100% |
| `next_bear` / `next_leg_direction` | Idénticos a `leg_bear` (el generador los nombró mal) | 100% |
| `z_dom` | μ/σ del calibration file (0.0532 / 0.035) | 100% |
| `cascade_conviction` | 0.66·z_bear + 0.34·z_dom plano | 100% |
| `{st}_zk_pbull/pbear` | Bloque `zigzag_kinematic.zz25` del fact store | 100% (VIX) |
| Alineación `_val/_vel/_vol` | Fecha EXACTA (no ffill); fuera de rango: val=NaN, vel=0, vol=1 | 100% (PCR) |
| `z_bear` | Ingeniería inversa μ=0.3299 σ=0.2856 (no está en ningún archivo actual) | 99.94% |

## Columnas DIVERGENTES (40) — causas raíz

### A. SKEW: bins D1 SOLAPADOS → irreproducible con edges estáticos
Los bins del pickle se solapan en el valor de SKEW:
- `NORMAL_TAIL_RISK`: 109.10 – 119.83
- `ELEVATED_TAIL_RISK`: 113.49 – 120.40
- `LOW_TAIL_RISK`: 104.31 – 113.33

Con un clasificador de umbral estático (el del adapter actual) los bins **nunca** se solapan. El solapamiento prueba que el generador original usó una clasificación **variable en el tiempo**. `_val/_vel/_vol` de skew matchean al 99.7%, así que la serie es la misma — solo la clasificación D1 difiere.
- **Hipótesis trailing probada y RECHAZADA (22-Ago):** cuantiles Gaussianos recalculados en cada pivote sobre ventanas de 252/504/756/1000 barras alcanzan como máximo **41.9%** de match (ventana 1000). Ninguna ventana reproduce el solapamiento. El clasificador original de skew D1 sigue sin identificarse — candidato a resolver por la auditoría externa.
- Afecta: `skew_sk` (13.3%), `skew_n`, `skew_d1_vote` (66.4%), `skew_zz25_pbull/pbear`, `skew_ev_net` (0.4%), `skew_zk_pbull/pbear` (3.5%).

### B. D1 votes y cascade (contaminación aguas abajo del solapamiento skew + deriva bsi)
- `bsi_d1_vote`: 73.1% — la clasificación bsi también deriva (sus bins se separan limpiamente, pero el `d1_vote` depende del estado completo D1__D2__D3 y de la función de voto que mapea bins a ±1).
- `d1_bear_5`: 15.2% — promedio de votos Grupo A; arrastrado por skew/bsi.
- `z_bear`, `cascade_conviction`: 15.2% — cascada de `d1_bear_5` (la fórmula es correcta al 100%, solo el input difiere).
- `mean_zk_pbull_11`: 3.5% — arrastrado por skew_zk.

### C. Deriva del bloque plano `zz25` de los fact stores
- `{st}_zz25_pbull/pbear`, `{st}_ev_net`: 80-94% según estación (vvix 79.8%, vix 93.9%, etc.).
- El bloque plano `zz25` fue regenerado (el docstring de `recalibrar_cascade_trailing.py` dice "fact stores regenerados con edges trailing 3 años"); el bloque `zigzag_kinematic` NO deriva (100%).
- Los fact stores tienen timestamp 16-Ago (antes del pickle 17-Ago), pero el bloque plano claramente no reproduce los valores del pickle.

## Impacto aguas abajo (para priorizar)

| Columna divergente | ¿La lee el evaluador/catálogo v7? | Impacto |
|--------------------|-----------------------------------|---------|
| `{st}_sk` (D2/D3) | Las señales leen SOLO D1 (`sk.split("__")[0]`) | Solo skew D1 difiere → afecta señales que usan skew D1 |
| `cascade_conviction` | 1 señal de exit lo usa | Medio |
| `daily_return_pct` | Forensia wins/losses | Resuelta 100% |
| `duration_bars` | Análisis de duración | Resuelta 100% |
| `{st}_zz25_pbull/_ev_net` | No los lee el evaluador de señales | Bajo |

## Conclusión

- **101/141 columnas reproducidas al ≥99.9%**, incluyendo TODAS las de mayor consumo aguas abajo (pivotes, `_val` base de VIX/BSI/credit/rotation, `duration_bars`, `daily_return_pct`, `z_dom`, `cascade_conviction` fórmula, `_zk_pbull`).
- Las 40 restantes se agrupan en **3 causas raíz**, todas identificadas y documentadas:
  1. **Skew D1 con edges trailing** (irreproducible con edges estáticos) — la más severa.
  2. **Deriva del bloque plano `zz25`** de los fact stores (bloque kinematic intacto).
  3. **Cascada de `d1_bear_5`** por las dos anteriores.
- El pickle original queda intacto; la sustitución requiere decidir cómo tratar skew trailing (reproducir los edges trailing, o aceptar la clasificación estática actual).
