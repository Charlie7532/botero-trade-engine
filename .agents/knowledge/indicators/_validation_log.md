# Hypothesis Validation Report — 2026-05-11 22:30 UTC

## Methodology
- **Engine**: OracleBacktester with Triple Barrier labeling
- **Data Source**: Vault (Neon PostgreSQL) — `market.ohlcv_bars`
- **Test Universe**: AAPL, MSFT, GOOGL, AMZN, NVDA, JPM, XOM, UNH, JNJ, PG, SPY, QQQ
- **Geometry**: SPECULATIVE_SPRING (TP=2.0×ATR, SL=1.0×ATR, max_bars=15)

## Results by Signal

### `bos_choch`
- **Status**: INSUFFICIENT_DATA across all tickers
- **Limitation**: ⚠️ LIMITED: Requires SMC structure context (smc_structure dict). Tested with empty context — 0 entries expected. Full validation requires SMC adapter pre-computation.

### `kalman_wyckoff`
- **Avg Oracle Sharpe**: 0.8826 → Grade **C**
- **Avg Win Rate**: 37.4%
- **Avg Profit Factor**: 1.34
- **Total Entries**: 867 across 11 tickers
- **Verdict**: MARGINAL (Grade C ceiling)

| Ticker | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| GOOGL | 1.9714 | 47.0 | 1.80 | 83 | A |
| UNH | 1.8228 | 39.5 | 1.74 | 86 | A |
| SPY | 1.7725 | 40.2 | 1.80 | 82 | A |
| JPM | 0.9740 | 37.1 | 1.37 | 70 | C |
| MSFT | 0.9251 | 38.0 | 1.31 | 71 | C |
| NVDA | 0.8081 | 38.2 | 1.25 | 68 | C |
| AAPL | 0.7989 | 37.0 | 1.28 | 81 | C |
| PG | 0.4687 | 35.2 | 1.17 | 88 | D |
| AMZN | 0.2141 | 34.2 | 1.07 | 73 | D |
| XOM | 0.2016 | 35.3 | 1.06 | 68 | D |
| QQQ | — | — | — | 0 | N/A |
| JNJ | -0.2481 | 28.9 | 0.93 | 97 | D |

### `mean_reversion`
- **Avg Oracle Sharpe**: 1.2264 → Grade **B**
- **Avg Win Rate**: 38.9%
- **Avg Profit Factor**: 1.70
- **Total Entries**: 418 across 10 tickers
- **Verdict**: VIABLE (Grade B ceiling)

| Ticker | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| XOM | 5.3643 | 63.6 | 4.32 | 33 | A |
| PG | 3.4892 | 50.0 | 2.92 | 12 | A |
| AAPL | 1.4999 | 40.5 | 1.60 | 37 | B |
| GOOGL | 1.4511 | 38.3 | 1.51 | 60 | B |
| MSFT | 1.4189 | 40.5 | 1.54 | 37 | B |
| AMZN | 1.0613 | 41.1 | 1.36 | 56 | B |
| JPM | 0.3436 | 28.6 | 1.11 | 49 | D |
| NVDA | 0.1631 | 34.4 | 1.05 | 61 | D |
| UNH | 0.1305 | 33.3 | 1.04 | 57 | D |
| JNJ | — | — | — | 7 | N/A |
| QQQ | — | — | — | 0 | N/A |
| SPY | -2.6580 | 18.8 | 0.53 | 16 | D |

### `pattern_recognition`
- **Avg Oracle Sharpe**: 0.5835 → Grade **C**
- **Avg Win Rate**: 36.8%
- **Avg Profit Factor**: 1.24
- **Total Entries**: 456 across 11 tickers
- **Verdict**: VIABLE (Grade B ceiling)

| Ticker | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| XOM | 1.8897 | 47.4 | 1.78 | 38 | A |
| GOOGL | 1.4778 | 41.7 | 1.49 | 48 | B |
| UNH | 1.1103 | 34.1 | 1.51 | 41 | B |
| AAPL | 1.0807 | 45.5 | 1.39 | 44 | B |
| PG | 0.8124 | 31.9 | 1.30 | 47 | C |
| NVDA | 0.6645 | 41.7 | 1.24 | 36 | C |
| JPM | 0.5430 | 33.3 | 1.19 | 42 | C |
| SPY | 0.4933 | 34.9 | 1.19 | 43 | D |
| QQQ | — | — | — | 0 | N/A |
| MSFT | -0.2985 | 39.4 | 0.92 | 33 | D |
| AMZN | -0.5061 | 29.4 | 0.86 | 34 | D |
| JNJ | -0.8488 | 26.0 | 0.76 | 50 | D |

### `rsi_intelligence`
- **Avg Oracle Sharpe**: 1.1691 → Grade **B**
- **Avg Win Rate**: 39.0%
- **Avg Profit Factor**: 1.51
- **Total Entries**: 1272 across 11 tickers
- **Verdict**: VIABLE (Grade B ceiling)

| Ticker | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| XOM | 2.6206 | 46.0 | 2.57 | 76 | A |
| JPM | 2.5967 | 48.3 | 2.21 | 116 | A |
| SPY | 1.9008 | 43.4 | 1.70 | 76 | A |
| AAPL | 1.2891 | 38.9 | 1.46 | 131 | B |
| UNH | 1.2374 | 41.2 | 1.51 | 160 | B |
| PG | 1.1817 | 39.4 | 1.45 | 137 | B |
| AMZN | 0.8121 | 35.8 | 1.31 | 134 | C |
| MSFT | 0.7460 | 35.2 | 1.24 | 122 | C |
| NVDA | 0.6940 | 41.8 | 1.22 | 67 | C |
| GOOGL | 0.6245 | 30.9 | 1.23 | 97 | C |
| QQQ | — | — | — | 0 | N/A |
| JNJ | -0.8429 | 27.6 | 0.77 | 156 | D |

### `volume_quality`
- **Avg Oracle Sharpe**: 0.5757 → Grade **C**
- **Avg Win Rate**: 35.7%
- **Avg Profit Factor**: 1.21
- **Total Entries**: 6512 across 11 tickers
- **Verdict**: WEAK (Grade D ceiling)

| Ticker | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| JPM | 1.1516 | 39.4 | 1.45 | 597 | B |
| SPY | 1.0669 | 39.1 | 1.44 | 644 | B |
| XOM | 1.0642 | 38.2 | 1.40 | 571 | B |
| UNH | 0.7462 | 32.8 | 1.29 | 573 | C |
| NVDA | 0.6157 | 38.1 | 1.21 | 583 | C |
| PG | 0.5031 | 34.3 | 1.18 | 577 | C |
| GOOGL | 0.4712 | 35.6 | 1.15 | 601 | D |
| AAPL | 0.4693 | 36.3 | 1.16 | 601 | D |
| AMZN | 0.3088 | 34.0 | 1.10 | 574 | D |
| MSFT | 0.2078 | 34.3 | 1.07 | 595 | D |
| QQQ | — | — | — | 0 | N/A |
| JNJ | -0.2724 | 30.4 | 0.92 | 596 | D |

## Summary

| Signal | Avg Sharpe | Grade | Verdict |
|---|---|---|---|
| bos_choch | -29.75 | **F** | **RETIRED** — 0% WR across 12 tickers |
| kalman_wyckoff | 0.8826 | C | MARGINAL (Grade C ceiling) |
| mean_reversion | 1.2264 | B | VIABLE (Grade B ceiling) |
| pattern_recognition | 0.5835 | C | VIABLE (Grade B ceiling) |
| rsi_intelligence | 1.1691 | B | VIABLE (Grade B ceiling) |
| volume_quality | 0.5757 | C | WEAK (Grade D ceiling) |

## BOS/CHoCH Full Validation (Run 2 — Self-Contained Adapter)

**Status: RETIRED (Grade F)**

After refactoring `BOSSignalAdapter` to be self-contained (single-pass `smartmoneyconcepts`
pre-computation on full OHLCV), the signal was re-evaluated across 12 tickers:

| Ticker | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| NVDA | -7.29 | 6.2% | 0.16 | 16 | F |
| AAPL | -9.57 | 0.0% | 0.06 | 17 | F |
| JPM | -12.27 | 5.3% | 0.10 | 19 | F |
| SPY | -22.20 | 0.0% | 0.00 | 14 | F |
| QQQ | -23.12 | 0.0% | 0.00 | 16 | F |
| AMZN | -26.15 | 0.0% | 0.00 | 21 | F |
| GOOGL | -30.63 | 0.0% | 0.00 | 21 | F |
| UNH | -31.36 | 0.0% | 0.00 | 19 | F |
| MSFT | -33.21 | 0.0% | 0.00 | 18 | F |
| XOM | -43.83 | 0.0% | 0.00 | 20 | F |
| PG | -62.05 | 0.0% | 0.00 | 12 | F |
| JNJ | -63.36 | 0.0% | 0.00 | 16 | F |

**Conclusion**: BOS/CHoCH as a standalone entry signal on daily timeframe has **no edge**.
Average Sharpe = -29.75. Per governance protocol, status → `RETIRED` as standalone signal.
Remains as `CANDIDATE` for conjugation exploration (may function as filter, not trigger).

## QQQ Supplemental Validation

QQQ was initially missing from the Vault due to a `load_bars` param format bug (fixed).
After fix, 1,255 daily bars were confirmed present. Results:

| Signal | Sharpe | WR% | PF | Entries | Grade |
|---|---|---|---|---|---|
| rsi_intelligence | **2.0065** | 45.1% | 1.71 | 82 | **A** ⭐ |
| kalman_wyckoff | 1.1047 | 34.9% | 1.42 | 63 | **B** |
| volume_quality | 0.5392 | 35.7% | 1.19 | 647 | C |
| pattern_recognition | 0.2770 | 38.1% | 1.10 | 42 | F |
| mean_reversion | -0.0839 | 32.1% | 0.98 | 28 | F |

## Data Source Annotations

- ✅ All validation data sourced from **Vault (Neon PostgreSQL)**
- ✅ No simulated or synthetic data used
- ✅ BOS/CHoCH fully validated with self-contained adapter (smartmoneyconcepts v0.0.27)
- ✅ QQQ confirmed: 1,255 daily bars in Vault
- ⚠️ This is **Step 1 only** (Oracle Alpha Ceiling). Full validation requires Steps 2-5.

