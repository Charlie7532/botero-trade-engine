# RC Tide Lookup & Real EV Engine — Technical Specification

> **Purpose:** Detailed engineering and scientific specification of the two primary Tide domain lookup adapters:
> 1. **Signal & Alignment Lookup:** `rc_tide_lookup.py` (reads `rc_tide_derived.json`)
> 2. **Point-in-Time Real EV Engine:** `rc_tide_ev_lookup.py` (reads `rc_tide_ev_derived.json`)
>
> **Cross-references:**
> - Master Index: [README.md](./README.md)
> - Slope Classifier Spec: [SLOPE_CLASSIFIER_SPEC.md](./SLOPE_CLASSIFIER_SPEC.md)
> - I/O Specification: [IO_SPEC.md](./IO_SPEC.md)
> - Open Proposals (P-006): [PROPOSALS.md](./PROPOSALS.md)

---

## Table of Contents

1. [Executive Summary & Architectural Scope](#1-executive-summary--architectural-scope)
2. [Module 1: Signal & Alignment Lookup (`rc_tide_lookup.py`)](#2-module-1-signal--alignment-lookup-rc_tide_lookuppy)
3. [Module 2: Point-in-Time Real EV Engine (`rc_tide_ev_lookup.py`)](#3-module-2-point-in-time-real-ev-engine-rc_tide_ev_lookuppy)
4. [Cascading Fallback Hierarchy ($L3 \to L2 \to L1 \to L0$)](#4-cascading-fallback-hierarchy-l3-%E2%86%92-l2-%E2%86%92-l1-%E2%86%92-l0)
5. [Universal Taxonomy Mapping Standard](#5-universal-taxonomy-mapping-standard)
6. [Coupling & Interoperability](#6-coupling--interoperability)
7. [Strict No-Fallback & Data Governance](#7-strict-no-fallback--data-governance)

---

## 1. Executive Summary & Architectural Scope

The Quality Swing Tide subsystem relies on two specialized pure-domain lookup modules located in `backend/modules/quality_swing/domain/rules/`:

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                      INPUT: (t_slope, c_slope, svw)                    │
 └─────────────────────────────────────────────────────────────────────────┘
                                     │
               ┌─────────────────────┴─────────────────────┐
               ▼                                           ▼
  ┌─────────────────────────┐                 ┌─────────────────────────┐
  │   rc_tide_lookup.py     │                 │   rc_tide_ev_lookup.py   │
  │  (Reads rc_tide_derived)│                 │ (Reads rc_tide_ev_deriv)│
  └─────────────────────────┘                 └─────────────────────────┘
               │                                           │
               ▼                                           ▼
  ┌─────────────────────────┐                 ┌─────────────────────────┐
  │ Dataclass: TideSignal   │                 │ Dataclass: RealEVSignal │
  │ - Identity & Regime     │                 │ - Point-in-Time EV      │
  │ - P(bull) & Z-Score     │                 │ - Sharpe & Asymmetry RR │
  │ - Turn Risk (Bottom/Top)│                 │ - e_days & EV/day       │
  │ - Purity & Confidence   │                 │ - 4-Level Fallback (L3) │
  └─────────────────────────┘                 └─────────────────────────┘
```

Both modules conform to **Clean Architecture**: they are pure domain rules that load pre-computed empirical research tables once into memory upon first call and perform zero I/O operations during decision queries.

---

## 2. Module 1: Signal & Alignment Lookup (`rc_tide_lookup.py`)

### 2.1. Purpose & Data Source
`rc_tide_lookup.py` provides committee-approved qualitative and quantitative alignment signals across **180 discrete states** of the Regression Channel model:

$$\text{State Space} = \text{Tide (6 levels)} \times \text{Current (6 levels)} \times \sigma_{Vw} \text{ (5 bins)} = 180 \text{ states}$$

- **Data File:** `rc_tide_derived.json` (475 KB)
- **Census Volume:** 763,118 daily observations across 561 tickers.
- **Global Baseline:** $P(bull) = 60.78\%$ across all market bars.

---

### 2.2. Value Object: `TideSignal` Dataclass

`TideSignal` is an immutable value object encapsulating 25+ empirical metrics:

```python
@dataclass(frozen=True)
class TideSignal:
    # Identity
    state_key: str          # e.g. "T+++|C---|<<"
    signal: str             # ACCUMULATE / BUY_DIP / TAKE_PROFIT / REDUCE / MOMENTUM / BULL_TREND / WATCH / NO_EDGE
    action_code: str        # Universal Taxonomy code (e.g. STK_ACCUMULATE_STRUCTURAL)
    urgency_level: str      # LOW / HIGH / PASSIVE / NORMAL / IMMEDIATE
    scope_level: str        # STK / SEC / MKT
    zone: str               # FLOOR / BELOW / NEUTRAL / ABOVE / CEILING
    regime: str             # ALIGN_BULL / ALIGN_BEAR / DIV_UP / DIV_DOWN / TRANSITION
    conviction: str         # HIGH / MEDIUM / LOW
    conviction_score: int   # 0-100 (log(N) x z-score)
    signal_confidence: int  # 0-100 (sample size x edge x stability)

    # Directional Statistics
    p_bull: float           # P(bull) percentage (0 - 100)
    odds: float             # Bull/Bear ratio
    lift_vs_band: float     # Lift relative to σVw band baseline
    z_score: float          # Z-score vs global P_bull (60.78%)

    # Turn Risk (ZigZag Pivots)
    bottom_25_pct: float    # % of bars that are 2.5% ZigZag bottoms (support)
    top_25_pct: float       # % of bars that are 2.5% ZigZag tops (resistance)
    asymmetry_pp: float     # bottom_25 - top_25 in percentage points

    # Composition & Quality
    momentum_purity: float  # HH / (HH + HL) — cleanliness of uptrend
    capitulation_purity: float # LL / (LH + LL) — purity of selling panic

    # Frequency & Rarity
    n_samples: int          # Sample size in census (N)
    rank: int               # Frequency rank (1 to 180)

    # Optional Context Flags
    predictive_edge: Optional[str]  # LEADING_BOTTOM / LEADING_TOP / None
    rotation_flag: Optional[str]    # EARLY_ROTATION / LATE_CYCLE_WARNING / None

    # Human Reading & Real EV Confluence
    reading: str
    ev: float = 0.0
    sharpe: float = 0.0
    rr_asymmetry: float = 1.0
    fatigue_type: str = "STABLE"
```

---

### 2.3. Operational Helper Properties

| Property | Return Type | Condition | Purpose |
|---|:---:|---|---|
| `is_accumulate` | `bool` | `signal in ("ACCUMULATE", "BUY_DIP")` or action code match | Triggers entry gate checks |
| `is_trim` | `bool` | `signal in ("TAKE_PROFIT", "REDUCE")` or action code match | Triggers exit/harvest checks |
| `is_hold` | `bool` | `signal in ("MOMENTUM", "BULL_TREND", "WATCH", "NO_EDGE")` | Maintains current allocation |
| `is_bullish_zone` | `bool` | `zone in ("ABOVE", "CEILING")` | High pricing zone |
| `is_bearish_zone` | `bool` | `zone in ("FLOOR", "BELOW")` | Discount pricing zone |
| `conviction_factor`| `float` | `conviction_score / 100.0` | Sizing multiplier $[0.0, 1.0]$ |
| `confidence_factor`| `float` | `signal_confidence / 100.0` | Certainty filter $[0.0, 1.0]$ |

---

### 2.4. $\sigma_{Vw}$ Bin Discretization Table

Before querying `rc_tide_derived.json`, continuous float $\sigma_{Vw}$ values are binned as follows:

$$\sigma_{Vw} = \frac{\text{Price} - \text{VWAP}_{wave}}{\text{std}(\text{VWAP}_{wave})}$$

| $\sigma_{Vw}$ Range | Bin Label | Zone Name | Meaning |
|:---:|:---:|:---:|---|
| $\sigma_{Vw} < -1.0$ | `<<` | **FLOOR** | Deep discount vs VWAP Wave |
| $-1.0 \le \sigma_{Vw} < -0.3$ | `<` | **BELOW** | Moderately below VWAP Wave |
| $-0.3 \le \sigma_{Vw} \le 0.3$ | `~` | **NEUTRAL** | Equilibrium / At fair value |
| $0.3 < \sigma_{Vw} \le 1.0$ | `>` | **ABOVE** | Moderately above VWAP Wave |
| $\sigma_{Vw} > 1.0$ | `>>` | **CEILING** | Overextended / Euphoria zone |

---

## 3. Module 2: Point-in-Time Real EV Engine (`rc_tide_ev_lookup.py`)

### 3.1. Purpose & Data Source
`rc_tide_ev_lookup.py` computes point-in-time **Expected Value ($E[R]$)**, Risk/Reward Asymmetry, Sharpe ratios, and capital velocity across three ZigZag resolution scales (`zz25`, `zz50`, `zz75`).

- **Data File:** `rc_tide_ev_derived.json` (276 KB)
- **Mathematical Target:** Real return $R_{real}$ measured from bar entry to next ZigZag pivot.

---

### 3.2. Value Object: `RealEVSignal` Dataclass

```python
@dataclass(frozen=True)
class RealEVSignal:
    state_key: str          # e.g. "T+++|C---|<<" or "GLOBAL"
    level: str              # "zz25", "zz50", "zz75"
    fallback_level: str     # "L3", "L2", "L1", "L0"
    signal: str             # "ACCUMULATE", "BUY_DIP", "NEUTRAL", "TRIM", "BLOCK", "EXIT_THESIS"
    action_code: str        # Universal Taxonomy code (e.g. STK_T_ACCUMULATE_STRUCTURAL)

    p_bull: float           # Probability of reaching next MIN (floor) first
    p_bear: float           # Probability of reaching next MAX (ceiling) first
    ev: float               # Expected Return E[R|S_t] (net percentage)
    sharpe: float           # EV / std(real_return)
    e_ret_min: float        # Expected real drawdown to next MIN pivot (negative)
    e_ret_max: float        # Expected real gain to next MAX pivot (positive)
    e_days: float           # Expected days to next pivot (holding horizon)
    rr_asymmetry: float     # E[ret_max] / |E[ret_min]| (Risk/Reward ratio)
    ev_per_day: float       # EV / e_days (Capital Velocity)
    n_samples: int          # Sample size in training database
    is_rare_state: bool     # Low-N tail state flag

    is_unobserved_state: bool = False
    fallback_reason: str = "EXACT_L3_MATCH"
```

---

### 3.3. Key Derived Formulas

#### 1. Risk/Reward Asymmetry Ratio ($RR_{asym}$)
Measures structural reward asymmetry relative to downside risk:

$$RR_{asym} = \frac{E[ret_{max}]}{|E[ret_{min}]|}$$

#### 2. Capital Velocity ($EV_{per\_day}$)
Measures return generated per calendar day held, penalizing slow-accruing states:

$$EV_{per\_day} = \frac{EV}{\max(e\_days, 1.0)}$$

#### 3. High Asymmetry Flag (`is_high_asymmetry`)
$$RR_{asym} \ge 2.5 \quad \text{AND} \quad P(bull) \ge 0.50$$

---

## 4. Cascading Fallback Hierarchy ($L3 \to L2 \to L1 \to L0$)

When querying `lookup_real_ev(t_slope, c_slope, svw, level="zz25", min_l3_samples=1)`, the engine executes a **4-level hierarchical cascade** to handle rare or unobserved states without guessing numbers:

```
               ┌──────────────────────────────────────────────┐
               │ Level 3: Exact Match (T x C x σVw)           │
               │ Key: "T+++|C---|<<"                           │
               └──────────────────────────────────────────────┘
                                      │
                         (If N < min_l3_samples or unobserved)
                                      ▼
               ┌──────────────────────────────────────────────┐
               │ Level 2: Mid-Macro Fallback (T x C)          │
               │ Key: "T+++|C---" (assumes σVw = ~)           │
               └──────────────────────────────────────────────┘
                                      │
                               (If unobserved)
                                      ▼
               ┌──────────────────────────────────────────────┐
               │ Level 1: Macro Trend Fallback (T alone)      │
               │ Key: "T+++" (assumes C = C~, σVw = ~)         │
               └──────────────────────────────────────────────┘
                                      │
                               (If unobserved)
                                      ▼
               ┌──────────────────────────────────────────────┐
               │ Level 0: Global Market Baseline              │
               │ Key: "GLOBAL" (Unconditional 763k census)    │
               └──────────────────────────────────────────────┘
```

### Cascade Execution Logic:

1. **Level 3 (Exact 3D Match):** Looks up `l3_full_state[l3_key]`. If $N \ge N_{min}$, returns $L3$ match with `fallback_reason = "EXACT_L3_MATCH"`.
2. **Level 2 (Mid-Macro Fallback):** If $L3$ is missing or $N < N_{min}$, queries `l2_mid_macro[t_slope | c_slope]`. Sets `fallback_level = "L2"` and `is_unobserved_state = True`.
3. **Level 1 (Macro Trend Fallback):** If $L2$ is missing, queries `l1_macro[t_slope]`. Sets `fallback_level = "L1"`.
4. **Level 0 (Global Baseline Fallback):** If state is completely unobserved across all macro levels, queries `l0_global["zz25"]`. Sets `fallback_level = "L0"` and `matched_key = "GLOBAL"`.

---

## 5. Universal Taxonomy Mapping Standard

`rc_tide_ev_lookup.py` maps statistical outputs directly into the **Universal Institutional Action Taxonomy** (prefixed with `STK_T_` for the Tide layer):

```python
if resolved_t in ("T---", "T--") and ev_net < -0.010:
    signal = "EXIT_THESIS"
    action_code = "STK_T_EXIT_THESIS_DEATH"

elif resolved_t in ("T---", "T--"):
    signal = "BLOCK"
    action_code = "STK_T_BLOCK_CRISIS"

elif ev_net <= -0.015:
    signal = "DISTRIBUTE"
    action_code = "STK_T_DISTRIBUTE_DECAY"

elif ev_net < -0.008:
    signal = "EXIT_TIME"
    action_code = "STK_T_EXIT_TIME_STOP"

elif resolved_t in ("T+", "T++", "T+++") and ev_net >= 0.005 and rr_asymmetry >= 1.5:
    signal = "ACCUMULATE"
    action_code = "STK_T_ACCUMULATE_STRUCTURAL"

elif ev_net >= 0.002 or (resolved_svw in ("<<", "<") and ev_net > 0.0):
    signal = "BUY_DIP"
    action_code = "STK_T_BUY_DIP_TACTICAL"

elif ev_net <= -0.003 or (resolved_svw in (">>", ">") and resolved_t in ("T+++", "T+")):
    signal = "TRIM"
    action_code = "STK_T_TRIM_TACTICAL"

else:
    signal = "NEUTRAL"
    action_code = "STK_T_HOLD_STABLE"
```

---

## 6. Coupling & Interoperability

`rc_tide_lookup.py` and `rc_tide_ev_lookup.py` are cross-coupled to ensure full signal confluence:

- When `lookup_tide_signal()` is called, it queries `rc_tide_derived.json` for identity, direction, and turn risk metrics.
- Internally, `classify_tide_signal_from_features()` invokes `lookup_real_ev(level="zz50")` to fetch point-in-time $EV$, Sharpe, and $RR_{asym}$.
- These EV metrics are embedded directly into the returned `TideSignal` object (`signal.ev`, `signal.sharpe`, `signal.rr_asymmetry`).

This guarantees that qualitative alignment and quantitative expected return are unified in every signal query.

---

## 7. Fast-Path & Deprecation Policy (P-007 / D-014 Standard)

In strict compliance with architectural directives and the P-007 / D-014 specification:

1. **Fast-Path Priority:** When `lookup_tide_signal()` or `lookup_real_ev()` is called with `snapshot=ChannelSnapshot` or `state_key_3d="..."`, the adapter executes a zero-cost $O(1)$ dictionary lookup against the pre-classified state key generated by `compute_channel_snapshot()`.
2. **Vault Feature Store Persisted Labels:** The `engine.channel_snapshots` table in Neon PostgreSQL stores 7 pre-classified columns (`atr_pct`, `tide_level`, `current_level`, `wave_level`, `vwap_bin`, `state_key_3d`, `quantile_version`), ensuring $100\%$ determinism between Vault persistence and domain logic.
3. **Deprecation of Un-normalized Float Calls:** Passing raw `float` numeric slopes directly to `lookup_tide_signal()` without `atr_pct` is **DEPRECATED** and emits a `DeprecationWarning` (lines 313-321 in `rc_tide_lookup.py`). Consumers must pass pre-classified levels, `state_key_3d`, or `ChannelSnapshot`.
4. **No Dummy Fallbacks:** Both `_load_tide()` and `_ensure_table_loaded()` raise explicit `FileNotFoundError` exceptions if research tables are missing or unreadable. Fallbacks across states ($L3 \to L2 \to L1 \to L0$) draw strictly from empirical census distributions.

---

*Specification Version: 1.1.0 (P-007 / D-014 Standard)*  
*Last Updated: 2026-07-28T20:05Z*  
*Author: Botero Trade Engine Architecture Team*
