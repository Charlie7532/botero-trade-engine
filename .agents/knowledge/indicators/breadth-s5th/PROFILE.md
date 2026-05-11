# S5TH — S&P 500 % Above 200-DMA
## Indicator Personality Profile

### What It Measures
Percentage of S&P 500 constituent stocks trading above their 200-day
moving average. Measures long-term structural market health and cycle position.

### Data Source
- **Historical**: TradingView `INDEX_S5TH` (4,994 bars from 1990-10-15)
- **Live**: Calculated daily by daemon from SP500-member OHLCV bars
  (`asset_type='STOCK' AND 'SP500' = ANY(index_membership)` — 506 tickers)
- **Previous proxy**: Was incorrectly calculated from ALL 542 tickers (including ETFs, indices). Corrected 2026-05-11.

### Mechanical Behavior
- Slower than S5TW — captures major trend shifts, not noise
- Range: 0% (secular bear/crash) to 100% (broad secular bull)
- Typical oscillation: 40%-80% in normal bull markets
- Extremes (<20% or >90%) are rare and historically significant

### Observed Correlations (HYPOTHESIS — not validated OOS)
- SPY: strong positive (structural trend alignment)
- S5TW: moderate positive (both breadth, different timeframes)
- S5FI: moderate positive (intermediate breadth)
- VIX: moderate negative

### Key Difference vs S5TW / S5FI
- S5TH captures STRUCTURAL health (monthly/quarterly cycles, MA=200)
- S5FI captures INTERMEDIATE health (weekly/monthly cycles, MA=50)
- S5TW captures TACTICAL breadth (daily/weekly swings, MA=20)
- Divergence between them (S5TH high, S5TW low) may signal
  narrow market concentration — HYPOTHESIS, not validated

### Known Limitations
- Requires 200+ trading days per ticker to calculate
- Very slow to react — will miss V-bottoms entirely
- Does NOT tell you WHY breadth is narrow (could be rotation, not crash)

### Live Feed
✅ Calculated daily from SP500 stocks in vault
