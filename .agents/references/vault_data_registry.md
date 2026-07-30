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
| **Single-value indicator** (FG, SV5_SHOCK) | value | value | value | value | `0` |
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
| `SV5TH` | SMA(50,vol) > SMA(200,vol) | Structural | 6,933 | 1999→2026 | Long-term institutional commitment |
| `SV5FI` | SMA(20,vol) > SMA(50,vol) | Intermediate | 6,933 | 1999→2026 | Medium-term institutional flows |
| `SV5TW` | EMA(5,vol) > SMA(20,vol) | Tactical | 6,933 | 1999→2026 | Short-term institutional activity |

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

## S5CAP Sector Cap-Weighted Breadth (21 tickers)

Cap-weighted sector breadth (large-cap influence). Pattern: `S5CAP_{ETF}_{TH|FI|TW}`.

| Sectors covered | TH/FI/TW per sector | Total | Range |
|---|---:|---:|---|
| XLK, XLC, XLI, XLV, XLP, XLU, XLRE (7 sectors) | 3 each | 21 | 1999→2026 |

**Provider:** `sector_cap_breadth_provider.py`.

---

## Volatility (4 tickers)

| Ticker | Formula | Bars | Range | Thresholds |
|---|---|---:|---|---|
| `VIX` | CBOE implied vol (SPX options) | 9,204 | 1990→2026 | <20=calm, 20-28=elevated, **>28=panic** |
| `VVIX` | Vol-of-vol (VIX options) | 5,071 | 2006→2026 | >120=VIX regime transition |
| `SKEW` | OTM put demand / tail risk | 9,195 | 1990→2026 | >140=institutional tail hedging |
| `SV5_SHOCK` | `std(Δ_SV5TW, 10d)` — V40 | 6,923 | 1999→2026 | P50=5.97, **>10=crisis proxy**, P90=12.66, P95=14.87 |

**SV5_SHOCK interpretation:**
- `< 6` (P50): Normal institutional activity — calm market
- `6-10`: Elevated but manageable institutional volatility
- **`> 10`**: Institutional panic — used as VIX fallback in V36 redirect (96.9% recovery)
- `> 13` (P90+): Extreme institutional shock (crashes, capitulations)

**Provider:** `sv5_shock_provider.py` (derived, runs after `volume_breadth_provider`).

---

## Sentiment (1 ticker)

| Ticker | Source | Bars | Range | Thresholds |
|---|---|---:|---|---|
| `FG` | CNN Fear & Greed Index | 3,872 | 2011→2026 | **<10=extreme fear** (76% WR buy), <20+S5TH<30=80% WR buy, >90=extreme greed |

---

## Options Flow (1 ticker)

| Ticker | Source | Bars | Range | Interpretation |
|---|---|---:|---|---|
| `CBOE_PCR` | CBOE Put/Call Ratio | 4,924 | 2006→2026 | High (>1.2)=fear, Low (<0.7)=greed. Real OHLCV with intraday range |

---

## Market Indices (3 tickers)

| Ticker | Index | Bars | Range |
|---|---|---:|---|
| `SPX` | S&P 500 | 24,703 | 1927→2026 |
| `NDQ` | Nasdaq Composite | 13,930 | 1971→2026 |
| `TNX` | 10-Year Treasury Yield | 16,075 | 1962→2026 |

---

## Sector & Market ETFs (15 tickers)

Real OHLCV with trade volume.

| Ticker | Name | Bars | Range |
|---|---|---:|---|
| `SPY` | S&P 500 | 8,431 | 1993→2026 |
| `QQQ` | Nasdaq 100 | 6,889 | 1999→2026 |
| `DIA` | Dow Jones | 7,175 | 1998→2026 |
| `IWM` | Russell 2000 | 6,581 | 2000→2026 |
| `XLK` | Technology | 6,941 | 1998→2026 |
| `XLC` | Communication Services | 2,038 | 2018→2026 |
| `XLF` | Financial | 6,941 | 1998→2026 |
| `XLI` | Industrial | 6,941 | 1998→2026 |
| `XLV` | Healthcare | 6,941 | 1998→2026 |
| `XLP` | Consumer Staples | 6,941 | 1998→2026 |
| `XLY` | Consumer Discretionary | 6,941 | 1998→2026 |
| `XLU` | Utilities | 6,941 | 1998→2026 |
| `XLE` | Energy | 6,941 | 1998→2026 |
| `XLB` | Materials | 6,941 | 1998→2026 |
| `XLRE` | Real Estate | 2,716 | 2015→2026 |

---

## SP500 Stocks (~500 tickers)

Full SP500 constituents with real OHLCV. ~1,000 to 16,000 bars each.
**Total: 5.77M bars across all tickers.**

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
    sector="Category",        # e.g. "Volatility", "Sentiment", "Options Flow"
    industry="INDICATOR",
    market_cap_bucket=None,
)
```
