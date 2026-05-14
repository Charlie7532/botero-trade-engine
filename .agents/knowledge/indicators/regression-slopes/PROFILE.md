# Regression Slope Sentiment (Ticker Fear/Greed)
## Indicator Personality Profile

### What It Measures
Per-ticker fear/greed state derived from the dual regression channels
already computed by `RegressionChannelAdapter`:
- **Tide** (200-bar long regression slope) → secular trend direction
- **Wave** (cycle-adaptive short regression slope) → micro-momentum

Together they measure: "Is this ticker in greed, confidence, anxiety, fear, or panic?"

### Data Source
- **Computed from**: OHLCV bars in the Vault (no external dependency)
- **Long channel**: 200-bar linear regression slope (normalized by mean price)
- **Short channel**: Dominant-cycle-adaptive (10-60 bars) via `_detect_dominant_cycle()`
- **Already exists in**: `signal_adapters.py → RegressionChannelAdapter`

### Empirical Results (20 tickers × 5 years = 20,580 observations)

#### Tide (Long Slope) — Contrarian
| State | % of data | P(↑ 5d) | Ret20d | Interpretation |
|---|:-:|:-:|:-:|---|
| BULL fuerte (>0.05) | 54.3% | 42.7% | +1.57% | Complacent — lower opportunity |
| BULL leve | 12.1% | 40.0% | +1.18% | Transitioning — weakest |
| FLAT | 6.6% | 41.4% | +1.73% | Neutral |
| BEAR leve | 12.0% | 42.8% | +1.28% | Starting to correct |
| BEAR fuerte (<-0.05) | 15.0% | **46.3%** | **+2.24%** | **Best opportunity** |

> Buffett/Munger validated: BEAR tide has the BEST forward returns.
> "Be greedy when others are fearful."

#### Wave (Short Slope) — Contrarian
| State | P(↑ 5d) | Ret20d |
|---|:-:|:-:|
| WAVE DOWN fuerte | **45.0%** | **+2.15%** |
| WAVE UP fuerte | 41.9% | +1.30% |

#### Wave FLIP — Most Discriminative Feature
| Event | N | P(↑ 5d) | Ret5d |
|---|:-:|:-:|:-:|
| Flip → POSITIVO | 435 | **44.8%** | +0.47% |
| Flip → NEGATIVO | 437 | **36.2%** | -0.19% |
| **Spread** | — | **8.6%** | **0.66%** |

> The wave flip is the knife-catching detector. Flip to positive =
> the knife stopped falling. Without it, you're catching a falling knife.

#### Ticker Fear/Greed Scale
| Level | Definition | P(↑ 5d) | Ret20d | Use |
|---|---|:-:|:-:|---|
| 0 GREED | Bull tide + Wave up + Accelerating | 40.4% | +1.26% | **Caution** — don't chase |
| 1 CONFIDENCE | Bull tide + Wave up | 41.9% | +1.26% | Hold, don't add |
| 2 NEUTRAL | Flat tide | 41.4% | +1.73% | No bias |
| 3 ANXIETY | Bull tide + Wave DOWN | **44.5%** | +1.94% | Pullback — opportunity starting |
| 4 FEAR | Bear tide + Wave flat/down | **45.1%** | +2.28% | Opportunity — wait for flip |
| 5 PANIC | Bear tide + Wave DOWN + Accelerating | **47.6%** | **+3.12%** | **Max opportunity — be Munger** |

### Role in the System
**TYPE: BIAS (ConfirmationPort), NOT Signal**

The regression slopes do NOT generate entry signals. They modulate the
conviction and sizing of existing signals (RC, RSI):

- `fear_level` → feature for ML lake (contrarian: high fear = high opportunity)
- `wave_flip` → feature for ML lake (the most discriminative single feature)
- `tide_slope` + `wave_slope` → continuous features for meta-model

### Conditions for Contrarian Use (Munger's Rules)
1. ✅ The knife STOPPED falling → `wave_flip == True && direction == POSITIVE`
2. ✅ The moat is INTACT → ticker is on the Quality Watchlist
3. ✅ No fundamental disruption → Piotroski/Altman/Beneish gates passed
4. ❌ If PANIC + NO wave flip → knife still falling, DO NOT buy

### Integration Points
- `PatternSignalAdapter` → Trail + fear_level as combined feature
- `KalmanSignalAdapter` → ACCUM + PANIC + wave_flip = max conviction
- `oracle_backtest.py` → persist `fear_level`, `wave_flip` in ml_labels
- `train_meta_model.py` → `fear_level` as feature in XGBoost

### Tide Acceleration — Secondary Signal
| State | P(↑ 5d) | Ret20d |
|---|:-:|:-:|
| Accelerating ↑↑ | 42.7% | +1.73% |
| Stable | 40.8% | +1.02% |
| Decelerating ↓↓ | **46.1%** | **+2.37%** |

> Deceleration of the tide = the trend is weakening = mean-reversion opportunity.
> Validates Munger: buy when the tide is slowing down, not when it's racing up.
