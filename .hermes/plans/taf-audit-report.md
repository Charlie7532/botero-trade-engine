# TAF AUDIT — Terminal Aerodrome Forecast

**Autor**: Experto TAF (subagent)
**Fecha**: 2026-08-14
**Metodología**: Walk-Forward OOS, 26 folds temporales, 11 estaciones, D1-only state matching
**N eventos**: 1,534 legs SPY zz25 (media 8.5 estaciones/leg)
**Script principal**: `backend/scripts/taf_audit_v3.py`

---

## 1. AUDITORÍA ZIGZAG_KINEMATIC

### Campos medidos (por escala zz25/zz50/zz75, ~35 campos/estado/estación)

| Field | Target | ρ OOS | p-value | Significant? |
|-------|--------|-------|---------|--------------|
| **p_bull** | dirección (is_bull) | **+0.1611** | 0.0000 | *** SI |
| **e_days** | duración (leg_dur) | **+0.1775** | 0.0000 | *** SI |
| **ev_net** | |retorno| | **+0.0516** | 0.0432 | * marginal |
| **D2 velocity** | dirección | VIX=+0.317, PCR=+0.233, VVIX=+0.233 | — | *** SI (per estación) |
| n_pos, n_neg | — | — | — | (soporte para p_bull) |
| e_ret_max/min | — | — | — | (componentes de ev_net) |
| ftt_bull/bear | — | — | — | (no medido OOS) |
| rr_asymmetry | — | — | — | (no medido OOS) |
| ev_per_day | — | — | — | (ev_net / e_days, redundante) |

### D2 velocity por estación (Walk-Forward OOS)

| Estación | ρ(D2, dir) | Interpretación |
|----------|-----------|----------------|
| **VIX** | **+0.317** | VIX↑ = más miedo → más probable que el leg sea MIN (rebote) |
| **PCR** | **+0.233** | PCR↑ = más puts → mismo efecto que VIX |
| **VVIX** | **+0.233** | Vol-of-vol↑ confirma el miedo |
| **FG** | **-0.245** | FG↓ (menos fear) → más bullish (sentimiento contrarian) |
| **Rotation** | **-0.241** | Rotation↓ (defensivo) → ¿fin de rotación defensiva? |
| SKEW | -0.120 | Señal débil, no significativa |
| DXY | +0.041 | Sin señal |
| Yield Curve | -0.070 | Sin señal |
| BSI | +0.030 | Sin señal |
| SV5T | +0.014 | Sin señal |
| Credit | -0.198 | Señal moderada pero no significativa en agregado |

**Hallazgo clave**: Por eso el D2 agregado da ρ≈0 — las estaciones tienen signos OPUESTOS. VIX↑→bullish, FG↑→bearish. No se puede sumar D2 linealmente; hay que respetar el signo por estación.

---

## 2. DISEÑO DE LA CAPA TAF

### Campos del zigzag_kinematic que DEBEN exponerse

| Campo | Justificación | Prioridad |
|-------|--------------|-----------|
| **p_bull** | Predice dirección OOS (ρ=+0.161) | ⭐⭐⭐ CRÍTICO |
| **e_days** | Predice duración (ρ=+0.178) | ⭐⭐⭐ CRÍTICO |
| **ev_net** | Predice magnitud (ρ=+0.052, marginal) | ⭐⭐ ÚTIL |
| **D2 velocity** | Per-estación, NO se agrega — se expone como metadata | ⭐⭐⭐ CRÍTICO |
| e_ret_max/min | Asimetría up/down (útil para SL/TP) | ⭐⭐ ÚTIL |
| rr_asymmetry | Ratio |e_ret_max|/|e_ret_min| | ⭐ ÚTIL |
| n_samples | Confianza estadística | ⭐⭐ ÚTIL |

### Estructura TAFEntry (propuesta mejorada)

```python
@dataclass(frozen=True)
class TAFEntry:
    """Pronóstico probabilístico por estación (fuente: zigzag_kinematic)."""
    station: str              # "vix", "bsi", etc.
    state_key: str            # D1×D2×D3 key actual
    scale: str                # "zz25" (default)
    
    # ── Forecast ──
    direction: str            # "BULL" | "BEAR"
    p_direction: float        # probabilidad dirección dominante
    ev_net_pct: float         # EV neto esperado (%)
    e_days: float             # duración esperada (días)
    e_ret_up: float           # retorno si bullish (%)
    e_ret_down: float         # retorno si bearish (%)
    rr_asymmetry: float       # ratio up/down
    
    # ── Context ──
    n_samples: int            # observaciones en este estado
    confidence: str           # "HIGH" (≥30) | "MODERATE" (≥10) | "LOW"
    d2_velocity: float        # Δ3d del indicador (metadata, NO agregable)
    d2_direction: str         # "ACCELERATING" | "DECELERATING" | "FLAT"
```

### TAF compuesto (agregado multi-estación)

```python
@dataclass(frozen=True)
class TAFComposite:
    """Pronóstico agregado de todas las estaciones."""
    consensus_direction: str          # "BULL" | "BEAR" | "NEUTRAL"
    p_bull_consensus: float           # p_bull promedio (≥3 estaciones)
    p_bull_weighted: float            # p_bull ponderado por n_samples
    ev_net_consensus: float           # EV neto promedio
    e_days_consensus: float           # duración esperada promedio
    stations_contributing: int        # N estaciones con datos
    stations_bull: int                # cuántas votan BULL
    stations_bear: int                # cuántas votan BEAR
    dispersion: float                 # std de p_bull entre estaciones
    most_predictive_station: str      # estación con mayor n_samples
    d2_divergence: bool               # True si D2 signs divergen entre estaciones
```

### ¿Por estación, por escala, o agregado?

**RESPUESTA: LOS TRES.** La capa TAF debe exponer:
1. **Per-station TAFEntry** (granularidad máxima — lo que ya existe en ConvergenceReport.taf)
2. **TAFComposite** (agregado — útil para decisiones rápidas)
3. **zz50 + zz75** (para ver si la señal se mantiene a escalas superiores — consistencia multi-escala)

---

## 3. VALOR PREDICTIVO DEL TAF

### 3.1 ¿TAF predice DIRECCIÓN mejor que cascade_conviction?

**NO — son PREGUNTAS DIFERENTES.** El cascade_conviction predice CASCADE (¿el próximo leg será del mismo tipo a escala superior?). El TAF predice DIRECCIÓN (¿el próximo leg será MIN o MAX?).

| Predictor | Target | ρ OOS | Accuracy |
|-----------|--------|-------|----------|
| **TAF (p_bull consensus)** | dirección (is_bull) | **+0.1611** *** | 56.65% |
| **cascade_proxy (bear vote)** | dirección (is_bull) | **-0.0980** *** | — |
| **TAF + cascade** | dirección (is_bull) | **+0.1209** *** | — |
| **Baseline (always bull)** | dirección | 0.0000 | 50.00% |

**TAF SOLO es MEJOR que TAF+cascade combinados.** El cascade_proxy DILUYE la señal direccional. Esto confirma que son señales ortogonales y no deben mezclarse para predecir dirección.

**Bootstrap CI95 para TAF accuracy**: [54.24%, 59.19%] — significativamente >50%.

### 3.2 ¿TAF predice MAGNITUD?

| Predictor | Target | ρ OOS | p-value |
|-----------|--------|-------|---------|
| ev_net consensus | |retorno| | **+0.0516** | 0.0432 * |

Marginalmente significativo. La magnitud es más difícil de predecir que la dirección.

### 3.3 ¿TAF predice DURACIÓN?

| Predictor | Target | ρ OOS | p-value |
|-----------|--------|-------|---------|
| e_days consensus | leg_duration | **+0.1775** | 0.0000 *** |

**SORPRENDENTEMENTE FUERTE.** La duración esperada del estado predice la duración real del próximo leg mejor que p_bull predice dirección. Este era el campo más ignorado y resultó ser el más predictivo.

### 3.4 ¿TAF + cascade_conviction combinados superan?

**NO para dirección** (TAF solo ρ=+0.1611 > TAF+cascade ρ=+0.1209).
**SÍ para tareas diferentes**: TAF predice dirección, cascade_conviction predice cascada. Son complementos, no competidores.

### 3.5 Terciles TAF

| Tercile | Bull Rate | N |
|---------|-----------|---|
| TAF bear (p_bull < 0.496) | 40.82% | 512 |
| TAF neutral | 51.08% | 511 |
| TAF bull (p_bull > 0.506) | 58.12% | 511 |

**Spread bear→bull**: 17.3pp — el TAF discrimina direccionalmente.

---

## 4. HALLAZGOS ADICIONALES

### 4.1 Agotamiento real (prev_leg_duration)

| Predictor | Target | ρ | p-value | N |
|-----------|--------|---|---------|---|
| **prev_leg_duration** | cascade_50 | **-0.2591** | 0.0000 | 1,589 |
| **prev_leg_duration** | cascade_75 | **-0.2402** | 0.0000 | 1,589 |

**CONFIRMA pitfall #27**: prev_leg_duration es un predictor OMITIDO del cascade. Piernas previas más largas → MENOS cascada. El agotamiento es REAL. Este campo NO está en la cascade_conviction actual.

### 4.2 Structural momentum (continuación)

| Métrica | Valor | N |
|---------|-------|---|
| p_continuation (global) | 0.0691 | 1,533 |
| p_continuation (MIN) | 0.0683 | 776 |
| p_continuation (MAX) | 0.0700 | 757 |
| ρ(|prev_return|, continuation) | +0.0447 (p=0.08) | — |

La continuación pura (mismo tipo → mismo tipo) es rara (6.9%). El |prev_return| NO predice continuación significativamente.

---

## 5. PROPUESTA DE INTEGRACIÓN EN ConvergenceReport

### Lo que YA existe (correcto)
```python
# En ConvergenceReport:
taf: Dict[str, Any]  # station_code → TAFEntry.to_dict()
```

### Lo que FALTA agregar

```python
# NUEVO campo en ConvergenceReport:
taf_composite: Optional[Dict[str, Any]]  # TAFComposite.to_dict()
```

### Código de integración (en convergence_compositor.py, ~línea 695)

```python
# ── TAF Composite (agregado multi-estación) ──
taf_composite = None
if len(taf_entries) >= 3:
    p_bulls = [e['p_direction'] if e['direction'] == 'BULL' else 1-e['p_direction'] 
               for e in taf_entries.values()]
    ev_nets = [e['ev_pct'] for e in taf_entries.values()]
    e_days = [e['e_days'] for e in taf_entries.values()]
    n_bull = sum(1 for e in taf_entries.values() if e['direction'] == 'BULL')
    n_bear = len(taf_entries) - n_bull
    
    taf_composite = {
        'consensus_direction': 'BULL' if np.mean(p_bulls) > 0.5 else 'BEAR',
        'p_bull_consensus': round(float(np.mean(p_bulls)), 4),
        'ev_net_consensus': round(float(np.mean(ev_nets)), 4),
        'e_days_consensus': round(float(np.mean(e_days)), 1),
        'stations_contributing': len(taf_entries),
        'stations_bull': n_bull,
        'stations_bear': n_bear,
        'dispersion': round(float(np.std(p_bulls)), 4),
    }
```

### Pasar a ConvergenceReport

```python
return ConvergenceReport(
    # ... campos existentes ...
    taf=taf_entries,
    taf_composite=taf_composite,  # ← NUEVO
    # ...
)
```

### REGLAS DE NO TOCAR

- ❌ NO modificar cascade_conviction_50/75/50to75
- ❌ NO cambiar pesos (0.66/0.34) validados
- ❌ NO usar TAF como input del cascade (son redundantes)
- ✅ TAF es OUTPUT adicional, no input modificador
- ✅ TAF + cascade coexisten en el report, no se combinan

---

## 6. RESUMEN EJECUTIVO

```
┌─────────────────────────────────────────────────────────────┐
│                    BOTERO TRADE — TAF LAYER                 │
│                 Terminado por 11 estaciones                  │
│                 Walk-Forward OOS, 26 folds                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  DIRECCIÓN PRÓXIMO LEG:                                     │
│    TAF accuracy:  56.65% (baseline 50%, edge +6.65pp)      │
│    CI95: [54.24%, 59.19%]                                   │
│    ρ(p_bull, dir) = +0.1611 ***                             │
│                                                             │
│  DURACIÓN PRÓXIMO LEG:                                      │
│    ρ(e_days, duration) = +0.1775 ***                        │
│                                                             │
│  MAGNITUD PRÓXIMO LEG:                                      │
│    ρ(ev_net, |ret|) = +0.0516 *                             │
│                                                             │
│  D2 VELOCITY (per-station):                                  │
│    VIX: ρ=+0.317  PCR: ρ=+0.233  VVIX: ρ=+0.233           │
│    FG:  ρ=-0.245  Rotation: ρ=-0.241                        │
│    ⚠ Signos OPUESTOS — no agregar D2 linealmente           │
│                                                             │
│  TAF vs CASCADE:                                             │
│    TAF predice DIRECCIÓN (ρ=+0.161)                         │
│    Cascade predice CASCADA (IC=+0.348)                      │
│    Son COMPLEMENTOS — no competidores                       │
│    TAF solo > TAF+cascade para dirección                    │
│                                                             │
│  AGOTAMIENTO (OMITIDO en cascade_conviction):                │
│    ρ(prev_leg_duration, cascade_50) = -0.259 ***           │
│    → Piernas más largas → MENOS cascada                     │
│                                                             │
│  PRÓXIMOS PASOS:                                             │
│    1. Agregar taf_composite a ConvergenceReport             │
│    2. Agregar D2 velocity como metadata (NO al composite)   │
│    3. Evaluar prev_leg_duration como 3er término cascade    │
│    4. No tocar cascade_conviction                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```