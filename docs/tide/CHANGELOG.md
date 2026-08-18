# Tide System — Design Dialogue & Changelog

> **Purpose:** Chronological record of every design discussion, experiment, and decision
> made on the Tide/Quality Swing subsystem. Each entry is timestamped, attributed,
> and linked to the relevant section of the [Design Memory](./README.md).
>
> **Format:** Most recent entries first. Each entry has: date, topic, discussion, resolution, and references.

---

## How to Use This Document

1. **Before proposing a change:** Search this log to see if the topic was already discussed.
2. **After a decision:** Add a new entry at the top with the full rationale.
3. **Cross-reference:** Link to the Decision Log table in [README.md §5](./README.md#5-decision-log-change-control).

---

## Entries

### [2026-07-28] Architecture Approval: P-007 Vault Classified Columns Persistence

**Topic:** Persisting discrete quantile classification columns (`tide_level`, `current_level`, `wave_level`, `vwap_bin`, `state_key_3d`) directly in `engine.channel_snapshots`.

**Discussion & Decision:**
- Approved proposal **P-007**.
- Consolidates `engine.channel_snapshots` as an autonomous, self-contained ML Feature Store (Single Source of Truth).
- Eliminates divergence between production runtime and offline research scripts.
- Enables direct SQL `GROUP BY state_key_3d` aggregations for model training at 100× speedup.

**Decision ID:** D-014

---

### [2026-07-28] General Architecture Directive: Vault-Backed Fallback Policy & JSON DB Backup

**Topic:** Complete prohibition of hardcoded fallbacks or default assumptions when data is missing; fallbacks ALLOWED ONLY over verified backup data.

**Directive & Policy Standard:**
- **Complete Prohibition of Hardcoded Fallbacks:** Hardcoded fallbacks, dummy values, or default assumptions in code when data is missing are COMPLETELY PROHIBITED.
- **Verified Backup Data Only:** Fallbacks are **ONLY** allowed over verified backup data (e.g. secondary DB backup in Neon Vault).
- **Absence of Data:** If neither primary data nor verified DB backup data is available, modules MUST raise explicit errors (`FileNotFoundError`, `KeyError`, `ValueError`) and halt execution without assuming data.
- **Pending Task (P-006):** Evaluate and execute the backup/persistence of research JSON tables (`rc_tide_derived.json`, `rc_tide_probability_table.json`, `rc_tide_ev_derived.json`, `rc_vol_normalized_thresholds.json`) into Neon PostgreSQL to serve as verified backup data.

**Resolution:** Documented and enforced across domain rules.

---

### [2026-07-28] Rejection & Disconnection of `generate_per_ticker_fact_tables.py`

**Topic:** Disconnecting the legacy 3-bin absolute slope generator and ensuring research JSON operational path.

**Discussion:**
- `generate_per_ticker_fact_tables.py` used 3-bin absolute slope classification (`T+`/`T0`/`T-` at `±0.05`) without volatility normalization.
- This approach is rejected as inadequate. Slopes cannot be evaluated using fixed absolute thresholds across heterogeneous assets.
- Pending task created: Elaborate a new approach/framework for fact generation (e.g., multi-scale T, W, VWAP coincidence maps or asset-class specific quantile classifiers).

**Resolution:**
- `generate_per_ticker_fact_tables.py` is explicitly disconnected (`RuntimeError` on execution).
- The production lookup path continues to rely on `rc_tide_derived.json` and `rc_tide_probability_table.json` as the operational standard.

---

### [2026-07-28] Handoff: 3 Pending Tasks Defined

**Topic:** Session continuity — defining immediate work items.

**Context:**
After completing the VIX A/B experiment, Trend Protection Gate, and Markov calibration in the previous session (conversation `68bcd487-aebf-4bc0-8e5a-c2301a19c8ba`), three tasks remain:

**Pending Work:**

1. **TASK 1 — Taxonomy Unification:**
   - `rc_tide_ev_lookup.py` reads JSON with 6-level keys (`T+++|C---|>`).
   - `rc_swing_ev_decision_engine.py` reads DB with 3-bin keys (`T+|C-|>`).
   - Need to connect `rc_tide_ev_lookup.py` to Neon PostgreSQL with key normalization.
   - Ref: [README.md §6.1](./README.md#61-task-1-taxonomy-unification-rc_tide_ev_lookuppy--vault)

2. **TASK 2 — Dynamic Duration & Capital Velocity:**
   - Add `e_days` and `ev_per_day` to `engine.ticker_fact_states`.
   - Update decision engine Kelly sizing to weight by capital velocity.
   - Dynamic Time Stop: `1.5 × e_days(S_t)`.
   - Ref: [README.md §6.2](./README.md#62-task-2-dynamic-duration-e_days--capital-velocity)

3. **TASK 3 — Scaled Forensic Benchmark:**
   - Run `eval_swing_forensic_benchmark.py` on 10 tickers, then full universe.
   - Ref: [README.md §6.3](./README.md#63-task-3-scaled-forensic-benchmark)

**Resolution:** Documented. Awaiting execution approval.

**Decision IDs:** D-007, D-008, D-009, D-010

---

### [2026-07-27] Dynamic Duration (e_days) Discovery

**Topic:** The fixed 20-day forward horizon is an irrational parameter.

**Discussion:**
- The `generate_per_ticker_fact_tables.py` script uses `lookforward_days = 20` as a hardcoded constant.
- Audit (`audit_dynamic_duration_practicability.py`) revealed that actual ZigZag 5% pivot horizons vary dramatically:
  - AAPL bullish state: ~7 days to pivot → EV/day = +0.358%/day
  - XOM same state: ~12 days to pivot → EV/day = +0.187%/day
  - Defensive stocks (JNJ, PG): ~15-20 days → slower capital
  - High-beta tech: ~5-8 days → faster capital
- Using a fixed horizon treats all states equally, destroying the information contained in the natural pivot duration.

**Resolution:**
- `e_days` per state will be computed from ZigZag pivot distances.
- `ev_per_day = E[R] / max(e_days, 1.0)` becomes the primary sizing input.
- The Time Stop becomes `1.5 × e_days(S_t)` (dynamic, not 20 fixed).
- **Decision ID: D-007, D-008, D-009**

---

### [2026-07-27] Trend Protection Gate — Buyback Slippage Fix

**Topic:** HARVEST signals in secular bull tides destroy value.

**Discussion:**
- JNJ, WMT, COST: strong secular uptrends (T+ or T++) with consistent positive E[R].
- The engine was issuing HARVEST signals when E[R] went slightly negative (absolute),
  even though the ticker's L0 baseline was also positive (secular bull).
- After harvesting, the price continued upward, forcing re-accumulation at higher prices.
- Net effect: negative Δ shares vs Buy & Hold.

**Root Cause Analysis:**
1. **Absolute E[R] is insufficient.** E[R] = −0.3% means nothing if L0 = −0.5% (the state is actually BETTER than average).
2. **Secular trends need protection.** When `t_slope ≥ 0.05`, the structural trend is intact. Harvesting during a healthy tide is fighting the current.

**Solution Implemented:**
- **Relative Expectation:** HARVEST requires `(E[R] − L0) < threshold`, not just `E[R] < 0`.
- **Trend Protection Gate:** Block HARVEST when `t_slope ≥ 0.05` UNLESS `σVw ≥ 1.50` (extreme overbought exception).

**Result:**
- JNJ: from −0.78 to **+0.28** Δ shares net (a swing of +1.06 shares).
- WMT: from −0.41 to **+0.15** Δ shares net.
- COST: minimal change (was already near-neutral due to high volatility absorbing the gate).

**Decision ID: D-003, D-004**

---

### [2026-07-27] VIX A/B Experiment — 3D vs 4D State Space

**Topic:** Should VIX be a 4th dimension in the state classification?

**Hypothesis:** Adding VIX regime (V_LOW / V_NORM / V_ELEV / V_CRISIS) as a 4th dimension would improve decision quality by conditioning returns on the volatility environment.

**Experiment Design:**
- **3D (Control):** State = T|C|VWAP (45 states)
- **4D (Treatment):** State = T|C|VWAP|VIX (180+ states)
- **OOS window:** 2020-01-01 → 2026-07-25
- **In-sample:** Pre-2020
- **Metric:** Mean Δ shares per ticker vs Buy & Hold

**Results:**

| Metric | 3D | 4D |
|---|:---:|:---:|
| Mean Δ shares | **+0.50%** | +0.08% |
| t-statistic | **1.64** | 0.18 |
| Regime crossings (OOS) | ~50 | **238** |
| States with n ≥ 15 | ~35 | ~18 |

**Root Cause of 4D Failure:**
- VIX crosses its classification thresholds 238 times in 5.5 years of OOS data.
- Each crossing changes the state key, fragmenting samples across more bins.
- The result: most 4D states have too few samples (n < 15), falling back to L0 (no edge).
- The 3D system concentrates its samples, yielding higher certainty (Ω) per state.

**Resolution:**
- VIX **removed** as state dimension.
- VIX **kept** as Circuit Breaker gate: `VIX ≥ 28.0 AND t_slope < −0.05 → EXIT_CRISIS`.
- **Decision ID: D-001, D-002**

---

### [2026-07-27] Markov Transition Calibration (16,470 OOS Transitions)

**Topic:** Are the Markov transition probabilities reliable out-of-sample?

**Method:**
- Built in-sample transition matrix from pre-2020 data per ticker.
- Predicted most-likely-next-state with probability P for each bar in OOS.
- Bucketed by predicted confidence: P ≥ 90%, P ≥ 80%, P ≥ 70%, P ≥ 60%, P ≥ 50%.
- Measured observed hit rate per bucket.

**Results:**

| Predicted Confidence | Observed Hit Rate | N Transitions |
|:---:|:---:|:---:|
| P ≥ 90% | **90.8%** | 2,104 |
| P ≥ 80% | **82.1%** | 4,892 |
| P ≥ 70% | **75.2%** | 8,403 |
| P ≥ 60% | **64.5%** | 12,841 |
| P ≥ 50% | **55.3%** | 16,470 |

**Conclusion:** Near-perfect linear calibration. The transition matrix is not overfit — it captures genuine temporal structure in state evolution. This justifies using Markov projections for preventive HARVEST decisions (Step 5c in the decision chain).

**Decision:** Markov anticipation integrated into production decision engine.

---

### [2026-07-27] Per-Ticker Kelly Scaling (Eliminates Global Constant)

**Topic:** The global `_KELLY_SCALE = 0.0736` constant is a design flaw.

**Problem:**
- The 0.0736 constant was derived from the P85 of Half-Kelly across ALL tickers and ALL history (1981-2026).
- This creates two issues:
  1. **Data leakage:** The constant uses future data (post-OOS).
  2. **Cross-ticker distortion:** AMZN (σ ≈ 2.5%) and PG (σ ≈ 0.8%) get the same scaling factor, which doesn't make physical sense.

**Solution:**
- Each ticker gets its own Kelly scale, derived from its L0 baseline:
  ```python
  l0_half_kelly = |E[R]_L0 / σ²_L0| / 2
  ticker_scale = 0.10 / l0_half_kelly  # maps L0 to operational midpoint
  ```
- States with stronger signal than L0 get f* > 0.10; weaker get f* < 0.10.
- Scale clamped to [0.01, 0.50] for stability.

**Decision ID: D-005**

---

### [2026-07-27] VWAP Drift Modifier: tanh vs copysign

**Topic:** Discontinuity at E[R] = 0 in the drift modifier.

**Problem:**
- Original implementation used `copysign(1.0, ev_net)` to determine if VWAP drift agrees with E[R].
- At `ev_net = 0.0`, `copysign` jumps from −1 to +1 — a discontinuity.
- States near E[R] ≈ 0 could flip the drift modifier sign on tiny floating-point noise.

**Solution:**
- Replace with `tanh(ev_net × 200)`:
  - When |E[R]| > 0.005: saturates to ±1 (identical to copysign behavior).
  - When E[R] ≈ 0: smoothly approaches 0 (no modification — correct behavior).
  - No discontinuity. No sensitivity to noise.

**Decision ID: D-006**

---

### [~2026-05-24] Stateful-First Architecture Policy (Rules 15-17)

**Topic:** Classifiers are amnesiac — they don't know how they got to the current state.

**Full discussion:** See [Legible_Establishing_Stateful_Design_Philosophy.md](file:///root/botero-trade/Legible_Establishing_Stateful_Design_Philosophy.md).

**Summary:**
- VIX = 25 arriving from VIX = 12 (shock) vs VIX = 40 (recovery) produces the same `ELEVATED` label.
- Gates can't differentiate because classifiers don't persist transitions.
- **Rules 15, 16, 17 added to AGENTS.md** to mandate `StateSnapshot` with `duration_bars`, `previous_state`, and `trigger_event`.
- `RegimeStatePort` + `PostgresRegimeStateAdapter` created.
- `market.regime_states` table in Neon PostgreSQL.

**Status:** Infrastructure implemented. Consumption in gates is incremental.

---

*Last updated: 2026-07-28T10:11Z*
*Version: 1.0.0*
