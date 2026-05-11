# S5TW — S&P 500 % Above 20-DMA
## Indicator Personality Profile

### What It Measures
Percentage of S&P 500 constituent stocks trading above their 20-day
moving average. Measures short-term market participation and tactical breadth.

### Data Source
- **Historical**: TradingView `INDEX_S5TW` (4,892 bars from 2006-12-29)
- **Live**: Calculated daily by daemon from SP500-member OHLCV bars
  (`asset_type='STOCK' AND 'SP500' = ANY(index_membership)` — 506 tickers)
- **Previous proxy**: Was incorrectly calculated from ALL 542 tickers (including ETFs, indices). Corrected 2026-05-11.

### Mechanical Behavior
- Moves faster than S5TH (20-DMA vs 200-DMA)
- Range: 0% (total washout) to 100% (universal rally)
- Typical oscillation: 25%-75% in normal markets
- Mean-reverts from extremes within 5-15 trading days

### Observed Correlations (HYPOTHESIS — not validated OOS)
- SPY: moderate positive (r ≈ 0.45)
- RSI-14: strong positive (r ≈ 0.76)
- VIX: moderate negative (r ≈ -0.50)

### Known Limitations
- Sensitive to S&P 500 rebalancing events
- Does NOT measure magnitude of moves, only direction vs MA
- Lagging during V-shaped reversals (20-DMA takes days to turn)

### Live Feed
✅ Calculated daily from SP500 stocks in vault
