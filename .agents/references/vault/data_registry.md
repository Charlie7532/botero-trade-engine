# Vault Data Registry — Complete Reference

> **Storage:** `market.ohlcv_bars` (single table, all tickers).
> **Metadata:** `market.ticker_metadata` (sector, industry, market_cap_bucket).
> **Timestamps:** Midnight UTC, enforced by `TimescaleDataStore`.
> **Read interface:** `store.load_bars(ticker, "1d")` — universal for all types.

---

## Storage Conventions

| Type | `open` | `high` | `low` | `close` | `volume` |
|---|---|---|---|---|---|
| **Stock/ETF** | Real OHLCV | Real | Real | Real | Real trade volume |
| **Breadth** (S5/SV5) | value | value | value | value | `n_constituents` counted |
| **Single-value indicator** (FG, SV5_TURBULENCE, Yields, etc.) | value | value | value | value | `0` |
| **Multi-value indicator** (CBOE_PCR) | Real O | Real H | Real L | Real C | `0` |

---

## S5 Market Breadth (3 tickers)

% of SP500 constituents trading above their Moving Average.

| Ticker | MA Length | Timeframe | Bars | Range | Interpretation |
|---|---:|---|---:|---|---|
| `S5TH` | 200d | Structural | 11,483 | 1980→2026 | Long-term market health. <30=bear, >65=bull |
| `S5FI` | 50d | Intermediate | 11,633 | 1980→2026 | Medium-term trend. <25=oversold, >75=overbought |
| `S5TW` | 20d | Tactical | 11,663 | 1980→2026 | Short-term momentum. <20=extreme fear, >80=extreme greed |

**Provider:** `breadth_provider.py` → `calculate_breadth(all_closes, ma_length)`.

---

## SV5 Market Volume Breadth (3 tickers)

% of SP500 constituents with volume MA crossover (institutional participation).

| Ticker | Volume MAs | Timeframe | Bars | Range | Interpretation |
|---|---|---|---:|---|---|
| `SV5TH` | SMA(50,vol) > SMA(200,vol) | Structural | 6,940 | 1999→2026 | Long-term institutional commitment |
| `SV5FI` | SMA(20,vol) > SMA(50,vol) | Intermediate | 6,940 | 1999→2026 | Medium-term institutional flows |
| `SV5TW` | EMA(5,vol) > SMA(20,vol) | Tactical | 6,940 | 1999→2026 | Short-term institutional activity |

**Provider:** `volume_breadth_provider.py` → `calculate_all_volume_breadth(all_volumes)`.

---

## S5 Sector Breadth (36 tickers)

Per-sector breadth for 11 GICS sectors + QQQ. Pattern: `S5_{ETF}_{TH|FI|TW}`.

| Sectors | TH/FI/TW per sector | Total | Range |
|---|---:|---:|---|
| XLK, XLC, XLF, XLI, XLV, XLP, XLU, XLRE, XLB, XLE, XLY, QQQ | 3 each | 36 | 1972→2026 (varies) |

**Gate usage:** `sec_th`, `sec_fi`, `sec_tw` dicts for sector-level regime classification and sector selection.
**Provider:** `sector_breadth_provider.py`.

---

## SV5 Sector Volume Breadth (36 tickers)

Per-sector volume breadth. Pattern: `SV5_{ETF}_{TH|FI|TW}`.

| Sectors | TH/FI/TW per sector | Total | Range |
|---|---:|---:|---|
| XLK, XLC, XLF, XLI, XLV, XLP, XLU, XLRE, XLB, XLE, XLY, QQQ | 3 each | 36 | 1999→2026 |

**Gate usage:** `sec_v_tw`, `sec_v_fi` dicts for institutional volume filters and Weinstein Smart Veto.
**Provider:** `sector_volume_breadth_provider.py`.

---

## S5CAP Sector Cap-Weighted Breadth (33 tickers)

Cap-weighted sector breadth (large-cap influence). Pattern: `S5CAP_{ETF}_{TH|FI|TW}`.

| Sectors covered | TH/FI/TW per sector | Total | Range |
|---|---:|---:|---|
| XLK, XLC, XLF, XLI, XLV, XLP, XLU, XLRE, XLB, XLE, XLY (11 sectors) | 3 each | 33 | 1999→2026 (varies) |

**Provider:** `sector_cap_breadth_provider.py`.

---

## Sector Volume Intensity (11 tickers)

Volume Intensity per sector ETF. Pattern: `VBI_{ETF}`.

| Sectors covered | Total | Range | Interpretation |
|---|---:|---|---|
| XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY | 11 | 1999→2026 (varies) | Relative institutional volume velocity vs baseline |

**Provider:** `sector_volume_intensity_provider.py`.

---

## Volatility (4 tickers)

| Ticker | Formula / Source | Bars | Range | Thresholds |
|---|---|---:|---|---|
| `VIX` | CBOE implied vol (SPX options) | ~19,440 | 1990→2026 | <20=calm, 20-28=elevated, **>28=panic** |
| `VVIX` | Vol-of-vol (VIX options) | 5,083 | 2006→2026 | >120=VIX regime transition |
| `SKEW` | OTM put demand / tail risk | 9,208 | 1990→2026 | >140=institutional tail hedging |
| `SV5_TURBULENCE` | `std(Δ_SV5TW, 10d)` — Institutional Vol | 6,930 | 1999→2026 | P50=5.97, **>10=crisis proxy**, P90=12.66, P95=14.87 |

**SV5_TURBULENCE interpretation:**
- `< 6` (P50): Normal institutional activity — calm market
- `6-10`: Elevated but manageable institutional volatility
- **`> 10`**: Institutional panic — used as VIX fallback in V36 redirect (96.9% recovery)
- `> 13` (P90+): Extreme institutional shock (crashes, capitulations)

**Provider:** `sv5_turbulence_provider.py`.

---

## Sentiment & Fear / Greed (10 tickers)

| Ticker | Source / Meaning | Bars | Range | Thresholds |
|---|---|---:|---|---|
| `FG` | CNN Fear & Greed Composite Score | 3,880 | 2011→2026 | **<10=extreme fear** (76% WR buy), >90=extreme greed |
| `FG_SP` | S&P 500 Synthetic Sentiment Proxy | 4,358 | 2009→2026 | S&P component of sentiment |
| `FG_MOMENTUM` | Stock Price Momentum vs 125-DMA | 8,337 | 1993→2026 | S&P 500 vs 125d moving average |
| `FG_STRENGTH` | Stock Price Strength (52-week highs/lows) | 13,479 | 1973→2026 | Net new highs vs new lows |
| `FG_BREADTH` | Stock Price Breadth (McClellan ADL) | 16,006 | 1963→2026 | Volume on advancing vs declining stocks |
| `FG_PUTCALL` | Put/Call 5-day Ratio Component | 5,005 | 2006→2026 | Options trading sentiment |
| `FG_JUNKBOND` | Junk Bond Demand (Spread Yield) | 4,862 | 2007→2026 | Spread between investment grade & junk |
| `FG_SAFEHAVEN` | Safe Haven Demand (Stocks vs Treasuries) | 6,048 | 2002→2026 | Difference in 20-day returns (SPY vs TLT) |
| `FG_VIX` | Market Volatility 50-DMA Component | 9,115 | 1990→2026 | VIX vs 50-day moving average |
| `FGBI` | Fear & Greed Breadth Index | 6,946 | 1999→2026 | Breadth-derived sentiment index |

**Providers:** `fg_provider.py`, `cnn_fg_sp_provider.py`, `cnn_fg_breadth_provider.py`.

---

## Credit Stress (1 ticker)

| Ticker | Formula | Bars | Range | Interpretation |
|---|---|---:|---|---|
| `CREDIT_RATIO` | `HYG / LQD` | 4,863 | 2007→2026 | High Yield vs Investment Grade Corporate Credit. METAR station. Low=Credit stress/widening spreads |

**Provider:** `credit_provider.py` / `synthetic_indicators_provider.py`.

---

## Sector Rotation (1 ticker)

| Ticker | Formula | Bars | Range | Interpretation |
|---|---|---:|---|---|
| `ROTATION_INDEX` | `z(XLY/XLP) + z(XLK/XLU)` | 6,954 | 1998→2026 | Aggressive vs Defensive Sector Relative Strength. METAR station. Positive=Risk-On, Negative=Defensive |

**Provider:** `rotation_provider.py` / `synthetic_indicators_provider.py`.

---

## Treasury Yields & Rates (8 tickers)

| Ticker | Description | Source | Bars | Range | Interpretation |
|---|---|---|---:|---|---|
| `DTB3` | 3-Month Treasury Bill | FRED (`DTB3`) | 18,145 | 1954→2026 | Short-term cash rate benchmark |
| `DGS2` | 2-Year Treasury Constant Maturity | FRED (`DGS2`) | 12,547 | 1976→2026 | Fed policy expectations rate |
| `DGS10` | 10-Year Treasury Constant Maturity | FRED (`DGS10`) | 16,139 | 1962→2026 | Structural benchmark bond rate |
| `DFII5` | 5-Year TIPS Real Yield | FRED (`DFII5`) | 5,908 | 2003→2026 | 5-Year real interest rate |
| `DFII10` | 10-Year TIPS Real Yield | FRED (`DFII10`) | 5,908 | 2003→2026 | 10-Year structural real interest rate |
| `TNX` | CBOE 10-Year Treasury Note Yield | CBOE/Yahoo | 16,140 | 1962→2026 | Market traded 10Y index |
| `IRX` | CBOE 13-Week Treasury Bill Yield | CBOE/Yahoo | 16,637 | 1960→2026 | Market traded 3M index |
| `YIELD_SPREAD` | Synthetic 10Y-3M Spread (TNX - IRX) | Internal | 16,132 | 1962→2026 | METAR station. Inversion = Recession hazard |

**Providers:** `yield_curve_provider.py`, `synthetic_indicators_provider.py`, `vault_fred_macro`.

---

## Inflation & Macro Economics (2 tickers)

| Ticker | Description | Source | Bars | Range | Interpretation |
|---|---|---|---:|---|---|
| `CPI` | Consumer Price Index (All Urban Consumers) | FRED (`CPIAUCSL`) | 954 | 1947→2026 | Baseline price index level (Monthly) |
| `CPIAUCSL` | Consumer Price Index (FRED Series Key) | FRED (`CPIAUCSL`) | 954 | 1947→2026 | Direct alias for FRED series ticker |

**Provider:** `vault_fred_macro`.

---

## Options Flow & Gamma (Multi-ticker)

| Ticker | Source | Bars | Range | Interpretation |
|---|---|---:|---|---|
| `CBOE_PCR` | CBOE Total Put/Call Ratio | 4,924 | 2006→2026 | High (>1.2)=fear, Low (<0.7)=greed. Daily OHLCV |
| `CBOE_PCR_5M` | CBOE Put/Call 5-minute Intraday | Varies | Recent | Intraday micro options sentiment |
| `PCCE` | CBOE Equity Put/Call Ratio | 4,854 | 2007→2026 | Equity-only options sentiment |
| `UW_GEX_*` | Unusual Whales Dealer Net Gamma | Varies | 2021→2026 | SPY, QQQ, Megacaps dealer gamma regimes |

---

## Market & Macro Indices (4 tickers)

| Ticker | Index | Bars | Range |
|---|---|---:|---|
| `SPX` | S&P 500 Index | 24,703 | 1927→2026 |
| `NDQ` | Nasdaq Composite Index | 13,930 | 1971→2026 |
| `DXY` | US Dollar Index | 13,878 | 1971→2026 |
| `TRIN` | NYSE ARMS Index | 5,728 | 2003→2026 |

---

## Sector & Market ETFs (~20 tickers)

Real OHLCV with trade volume.

| Ticker | Name | Bars | Range |
|---|---|---:|---|
| `SPY` | S&P 500 ETF | 8,431 | 1993→2026 |
| `QQQ` | Nasdaq 100 ETF | 6,889 | 1999→2026 |
| `DIA` | Dow Jones Industrial ETF | 7,175 | 1998→2026 |
| `IWM` | Russell 2000 ETF | 6,581 | 2000→2026 |
| `XLK` | Technology Select Sector | 6,941 | 1998→2026 |
| `XLC` | Communication Services Select Sector | 2,038 | 2018→2026 |
| `XLF` | Financial Select Sector | 6,941 | 1998→2026 |
| `XLI` | Industrial Select Sector | 6,941 | 1998→2026 |
| `XLV` | Healthcare Select Sector | 6,941 | 1998→2026 |
| `XLP` | Consumer Staples Select Sector | 6,941 | 1998→2026 |
| `XLY` | Consumer Discretionary Select Sector | 6,941 | 1998→2026 |
| `XLU` | Utilities Select Sector | 6,941 | 1998→2026 |
| `XLE` | Energy Select Sector | 6,941 | 1998→2026 |
| `XLB` | Materials Select Sector | 6,941 | 1998→2026 |
| `XLRE` | Real Estate Select Sector | 2,716 | 2015→2026 |
| `TLT` | 20+ Year Treasury Bond ETF | 5,800+ | 2002→2026 |
| `HYG` | iShares iBoxx $ High Yield Corporate Bond ETF | 4,800+ | 2007→2026 |
| `LQD` | iShares iBoxx $ Investment Grade Corporate Bond ETF | 5,800+ | 2002→2026 |

---

## SP500 Stocks (~500 tickers)

Full SP500 constituents with real OHLCV. ~1,000 to 16,000 bars each.
**Total: ~5.85M bars across all tickers.**

---

## Adding New Indicators

```python
# 1. Compute value
value = your_computation()

# 2. Persist as pseudo-OHLCV
store.upsert_ohlcv_bar(
    ticker="MY_INDICATOR", timeframe="1d", time=now,
    open=value, high=value, low=value, close=value, volume=0,
)

# 3. Register metadata (once)
store.upsert_ticker_metadata(
    ticker="MY_INDICATOR",
    sector="Category",        # e.g. "Yields", "Volatility", "Sentiment", "Credit", "Rotation"
    industry="INDICATOR",
    market_cap_bucket=None,
)
```
