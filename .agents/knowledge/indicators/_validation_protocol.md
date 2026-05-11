# Indicator Validation Protocol
## Scientific Methodology for Signal Validation

---

## Core Principle

**Every signal starts as HYPOTHESIS.** No signal is VALIDATED until it passes
the full walk-forward protocol below. No exceptions.

Observation ≠ Validation. Correlation ≠ Causation. In-sample ≠ Out-of-sample.

---

## Evidence Status Tags

Each signal in `signals.yaml` MUST carry one of these tags:

| Status | Meaning | Requirements |
|---|---|---|
| `CANDIDATE` | Pattern discovered by Signal Miner | Raw statistical observation |
| `HYPOTHESIS` | Observed pattern, not yet tested OOS | p < 0.10 preliminary |
| `VALIDATED` | Passed walk-forward + DSR test | All 5 steps below passed |
| `DEGRADED` | Was validated, signal decay detected | Rolling Sharpe declining >25% |
| `REPOSTULATED` | DEGRADED + conjugation restores edge | ConjugationExplorer confirms |
| `RETIRED` | Failed OOS or decayed beyond use | Remove from active gates |

---

## 5-Step Validation Pipeline

### Step 1: Define the Signal (Pre-Test)
Before any data analysis:
- State the exact condition (e.g., "S5TW < 20%")
- State the expected action (e.g., "LONG SPY")
- State the forward horizon (e.g., "60 trading days")
- State what would disprove it (falsification criteria)

### Step 2: Temporal Train/Test Split
- **Train**: First 70% of data (chronological, NEVER random)
- **Test**: Last 30% of data (never seen during threshold discovery)
- **Embargo**: 5 trading days between train/test (prevent leakage)
- Split date must be documented in `validation_log.md`

### Step 3: In-Sample Analysis (Train Only)
- Calculate thresholds on TRAIN data only
- Compute: win_rate, avg_return, Sharpe, observation count
- Minimum requirements to proceed:
  - N ≥ 30 observations
  - p-value < 0.05 (t-test vs zero return)
  - Sharpe > 0.5

### Step 4: Out-of-Sample Validation (Test Only)
- Apply EXACT thresholds from Step 3 to TEST data
- Compute same metrics on TEST data
- Pass criteria:
  - OOS win_rate ≥ 0.8 × IS win_rate (max 20% degradation)
  - OOS Sharpe > 0.0 (positive edge survives)
  - OOS p-value < 0.10

### Step 5: Deflated Sharpe Ratio (López de Prado)
- Compute DSR accounting for:
  - Number of trials/thresholds tested
  - Skewness and kurtosis of returns
  - Sample length
- DSR > 1.0 → signal has real edge after multiple testing adjustment

---

## Reliability Grading

Based on the validation results:

| Grade | Criteria | Gate Usage |
|---|---|---|
| **A** | DSR > 1.5, OOS p < 0.001, N > 100 | Hard gate (block/allow) |
| **B** | DSR > 1.0, OOS p < 0.01, N > 50 | Sizing modifier (±25%) |
| **C** | DSR > 0.5, OOS p < 0.05, N > 30 | Advisory only (alerts) |
| **D** | Suggestive: p < 0.10 or N < 30 | Monitor, do not use |
| **F** | Failed OOS or DSR < 0 | Retired |

---

## Revalidation Schedule

- **Quarterly**: Re-run full pipeline with expanded data window
- **On signal decay**: If rolling 1Y Sharpe drops >25% from validation
- **On regime change**: If market structure changes (new VIX regime, etc.)

---

## Conjugation Discovery Rules

When combining two or more indicators:
1. Each partner must independently have p < 0.10
2. Combined signal must have N ≥ 20 observations
3. Correlation between partners < 0.80 (avoid redundancy)
4. Combined must improve over best individual partner
5. Validate combined signal OOS (same 70/30 split)

---

## Anti-Patterns (What NOT to Do)

1. **Data snooping**: Testing many thresholds and keeping the best one
   → Solution: DSR adjustment for number of trials
2. **Survivorship bias**: Only using tickers that exist today
   → Solution: Use full OHLCV universe as-is in vault
3. **Look-ahead bias**: Using future data to define conditions
   → Solution: Strict temporal split with embargo
4. **Overfitting**: Complex multi-condition signals with few observations
   → Solution: Minimum N=30, prefer simple signals
5. **Cherry-picking horizons**: Testing many forward periods
   → Solution: Pre-declare horizon before testing
