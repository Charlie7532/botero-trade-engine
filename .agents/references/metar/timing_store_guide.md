# Timing Store Guide — Continuous Temporal State Distribution

> **Purpose:** How to read and use the 11 timing stores (`*_timing_fact_store.json`).
> **Audience:** AI agents and developers consuming METAR intelligence.

---

## 1. Theory: Fact Store vs Timing Store

These are **TWO DIFFERENT THEORIES** applied to the same D1__D2__D3 state space:

| | Fact Store | Timing Store |
|---|---|---|
| **Training method** | ZigZag pivot-to-pivot legs | Every bar (continuous) |
| **Question it answers** | "What return do I expect until next pivot?" | "Am I near a turning point RIGHT NOW?" |
| **Population** | N = # ZigZag legs that traversed this state | N = # bar-episodes in this state |
| **Key metrics** | `p_bull`, `ev_net`, `e_ret_max/min` at zz25/50/75 | `slots_zz25`, `first_passage`, `fire_rate_pct` |
| **State sets** | ≥80% overlap with timing stores, but NOT identical (different populations) | Same |

## 2. Structure per State

```json
{
  "4__3__2": {
    "poblacion": {
      "barras": 240,              // Total bars in this state
      "fire_rate_pct": 2.84,       // % of all time this state is active
      "n_episodios": 178,          // # independent episodes
      "duracion_media": 1.35,      // Average episode duration (days)
      "duracion_max": 4            // Longest episode
    },
    "overflows": {
      "n_episodios_tier_gte_1": 0,  // Episodes with ≥1 overflow tier
      "pct_episodios_overflow": 0.0,
      "max_tier_d1": 0, "max_tier_d2": 0, "max_tier_d3": 0
    },
    "medicion_min": { ... },       // FLOOR intelligence (toward minima)
    "medicion_max": { ... }        // CEILING intelligence (toward maxima)
  }
}
```

## 3. Floor/Ceiling Measurement: `medicion_min` / `medicion_max`

Each direction contains:

### `resumen_rango` — Proximity summary
```json
{
  "n_en_rango": 140,       // Bars within ±2 bars of a ZZ turning point
  "pct_en_rango": 78.65,   // % of episodes near a turn
  "delta_medio": 1.7,      // Average distance to nearest turn (bars)
  "delta_mediana": 1.0
}
```

### `slots_zz25` — Temporal slot distribution
```
t-2: 2 bars before the zigzag turn     → "Anticipation"
t-1: 1 bar before the turn             → "Imminent"
t=0: Day of the turn                   → "Confirmation"
t+1: 1 bar after the turn              → "Validation"
t+2: 2 bars after the turn             → "Post-validation"
ENTRE: Not near any turn               → "Away from turn"
```

Each slot has `{n, pct, hit_rate, ev, bars}`.

**The temporal alpha is the spread between t=0 and ENTRE:**
- High HR at t=0, low HR at ENTRE → strong timing signal
- Similar HR everywhere → this state is not a timing indicator

### `first_passage` — Path quality at each scale
```json
{
  "zz25": { "mae_medio": -0.02, "mfe_medio": 0.021, "mae_p90": -0.04, "mfe_p90": 0.037 },
  "zz50": { "mae_medio": -0.034, "mfe_medio": 0.041 },
  "zz75": { "mae_medio": -0.047, "mfe_medio": 0.066 }
}
```
- **MAE** = Maximum Adverse Excursion (worst drawdown before resolution)
- **MFE** = Maximum Favorable Excursion (best gain before resolution)
- **MFE > |MAE|** → the path toward the turn is favorable (more gain than pain)

## 4. How the Lookup Integrates Timing

After Etapa 1 integration, each `StateGuidance` object has a `timing: Optional[TimingContext]` field that provides:

```python
guidance = vix_lookup.lookup_vix_guidance(val=25.0, d3_speed=1.5)
tc = guidance.timing
if tc:
    print(tc.floor_pct_en_rango)     # 46.15% → how often this state is near a floor
    print(tc.ceiling_pct_en_rango)   # 39.16% → how often this state is near a ceiling
    print(tc.fire_rate_pct)          # 1.80% → how rare is this state
    print(tc.n_episodios)            # 143 → how many times this state has occurred
    print(tc.first_passage_zz75_floor)  # FirstPassage object with MAE/MFE metrics
```

## 5. Consumption in Compositor and TAF

- **Compositor:** `station_summaries[code]["timing_context"]` contains the serialized TimingContext
- **TAF:** The cone metrics from the fact store + timing proximity from timing store combine to answer: "Which direction is the cone pointing, and how close am I to a turn?"
