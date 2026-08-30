# Botero Trade — Agent Context

This file is auto-loaded by OpenAI Codex CLI at the start of every session. Read it fully before writing any code.


---

## CRITICAL DIRECTIVE: ZERO-BIAS TRADING
**Full behavioral rules in `.agents/skills/operational-purpose/SKILL.md`.**
Summary: This is a sandbox calibration environment. Zero disclaimers. The user is the System Architect. Mechanical truth over theory. No Discovery Sabotage. No academic hedging. Deterministic language for deterministic mechanics.

---

## What this project is

Algorithmic trading monorepo combining:
- **Next.js 16 + PayloadCMS 3** (TypeScript) — trading dashboard UI + CMS admin at `src/`
- **Python Trading Engine** — institutional-grade engine with MCP data pipelines at `backend/`
- **8 MCP Servers** (~200+ tools) — Alpaca, GuruFocus, Finviz, Finnhub, FRED, Yahoo Finance, News, Unusual Whales
- **Docker Compose** — orchestrates `web` (3000) and `api` (8000). PostgreSQL is **external**.

Git remote: `https://github.com/Charlie7532/botero-trade-engine`

---

## Clean Architecture — mandatory for all code
**Full structural rules in `.agents/skills/clean-architecture/SKILL.md`.**
Summary: Dependencies point inward. Domain knows nothing about infrastructure. Use Cases depend on Ports (ABCs), never concrete adapters. Module structure follows Screaming Architecture under `backend/modules/`.

---

## Project structure

```
botero-trade/
├── src/                          # Next.js + PayloadCMS (TypeScript)
│   ├── app/(frontend)/          # Trading dashboard pages
│   ├── app/(payload)/           # CMS admin panel
│   ├── shared/                  # Cross-cutting Clean Architecture (TS)
│   ├── modules/                 # Feature modules
│   ├── collections/             # PayloadCMS collections (infrastructure)
│   ├── plugins/                 # PayloadCMS plugins
│   │   └── payload-mcp-gateway/ # MCP protocol adapter — exposes CMS to AI agents
│   └── components/              # Shared React components (UI layer)
│
├── backend/                     # Python trading engine
│   ├── modules/                 # Feature-oriented Hexagonal Architecture Modules
│   │   ├── price_analysis/      # RSI & Phase Timing (Pure Domain)
│   │   ├── volume_intelligence/ # Volume Profile & Kalman Filter (Pure Domain)
│   │   ├── pattern_recognition/ # Candlestick patterns via pandas-ta (Pure Domain)
│   │   ├── flow_intelligence/   # Whale flow (Domain) + Finnhub/UW/FRED (Infra)
│   │   ├── options_gamma/       # Gamma Regime (Domain) + yfinance chain (Infra)
│   │   ├── entry_decision/      # Entry Hub (Domain) + Price/VIX fetcher (Infra)
│   │   ├── portfolio_management/# Universe Filter, Alpha Scanner (Domain) + Finviz (Infra)
│   │   ├── execution/           # Paper Trading, Journal (Domain) + Broker adapters (Infra)
│   │   ├── simulation/          # Backtester, Autopsy (Domain) + Backtrader (Infra)
│   │   ├── volatility_regime/   # Vol Regime Classification (Pure Domain)
│   │   └── shared/              # Cache Utils, Global Ports, Market Data entities
│   ├── _legacy/                 # Deprecated / Experimental code (LSTM, Sequence modeling)
│   ├── daemons/                 # Background runners (Quality, Speculative — delivery mechanism)
│   └── api/
│       ├── main.py              # FastAPI app + CORS
│       └── routers/
│
├── mcp-servers/                  # Local MCP server installs (consolidated)
│   ├── finviz/                  # Finviz Elite (cloned fork, local venv)
│   ├── gurufocus/               # GuruFocus Premium (custom wrapper)
│   └── .cache/                  # Storage dirs for FRED & Finnhub MCP servers
│
├── tests/                       # Pytest suite (20 tests)
│   ├── conftest.py              # Shared fixtures (MongoDB test DB)
│   ├── test_risk_guardian.py     # 7 tests: DD, VIX, anti-martingale
│   ├── test_trailing_stop.py     # 5 tests: regime adaptation, floor/ceiling
│   └── test_trade_journal.py     # 6 tests: MongoDB persistence, patterns
│
├── .mcp.json                    # 10 MCP server configs (secrets via env vars)
├── pytest.ini
└── package.json
```

---

## MCP Servers (8 active)

All configured in `.mcp.json` with secrets via environment variables.

| Server | Tools | Plan | Primary Use |
|---|:-:|---|---|
| **Finviz** | 35 | Elite | Screening, sector performance, SEC filings |
| **GuruFocus** | 55 | Premium (USA) | QGARP scoring, insider tracking, guru analysis |
| **Alpaca** | 61 | Free (paper) | Execution + basic OHLCV data |
| **Finnhub** | 45 | Free | Earnings calendar, insider transactions, news |
| **FRED** | 12 | Free | Macro indicators (GDP, CPI, FFR, yield curve) |
| **Yahoo Finance** | 9 | Free | VIX, options chains, fallback data |
| **News Sentiment** | 4 | Free | FinBERT sentiment scoring |
| **Unusual Whales** | 20+ | Premium | Institutional flow, market tide, SPY delta, options alerts |

### Data Provider Hierarchy

1. **Finviz Elite** → PRIMARY for screening, sectors, market overview
2. **GuruFocus Premium** → PRIMARY for fundamentals, insiders, gurus (USA only)
3. **FRED** → PRIMARY for macro indicators
4. **Finnhub** → Earnings calendar + insider redundancy
5. **Alpaca** → Execution only (future: migrate to Interactive Brokers)
6. **Unusual Whales** → Institutional flow, macro gates, market sentiment
7. **Yahoo Finance** → Last resort fallback

---

## Key domain entities (Python)

```python
Bar(symbol, timestamp, open, high, low, close, volume)
Order(symbol, side, quantity, order_type, broker, status, ...)
Position(symbol, quantity, avg_cost, market_price, broker)
Trade(order_id, symbol, side, quantity, price, broker, executed_at)
Signal(symbol, side, strength 0–1, strategy_name)
Portfolio(broker, cash, positions[], trades[])
Broker(enum): interactive_brokers | alpaca
```

---

## API endpoints (port 8000)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/market-data/{symbol}` | Historical OHLCV bars |
| GET | `/api/market-data/{symbol}/price` | Current price |
| GET | `/api/portfolio/{broker}` | Portfolio from one broker |
| GET | `/api/portfolio/` | All connected broker portfolios |
| GET | `/api/strategy/list` | Registered strategies |
| POST | `/api/strategy/backtest` | Run Backtrader backtest |
| — | `/api/docs` | Swagger UI |

---

## Dev commands

```bash
pnpm dev:all          # start everything (Next.js + Python API) — use this first
pnpm dev              # frontend only
pnpm dev:api          # Python API only (uses backend/.venv)
pnpm docker:up        # Docker Compose (web + api)
pnpm generate         # regenerate PayloadCMS types + importmap
```

---

## Available slash commands

Full documentation for each command is in `.claude/SKILLS.md`.

| Command | Purpose |
|---|---|
| `/start` | Full startup checklist — prerequisites, env, install, launch |
| `/context` | Detailed architecture reference (entities, endpoints, env vars) |
| `/dev` | Dev environment reference and common task cheatsheet |
| `/add-strategy` | Guided workflow: add a new Backtrader strategy |
| `/add-broker` | Guided workflow: add a new broker adapter |
| `/find-finance-skills` | Descubrir e integrar nuevas herramientas financieras (librerías, APIs, MCP servers) |
| `/proposito-practico` | Activa directivas anti-sesgo y enfoca a la AI en el pragmatismo institucional |

---

## Security — credential files are OFF LIMITS

**This is a hard rule. No exceptions.**

The following files contain secrets and must NEVER be read, written, viewed, cat'd, printed, or output by any AI agent:

- `.env`
- `.env.local`
- `.env.development`
- `.env.production`
- `.mcp.json`
- Any file matching `.env*` (except `.env.example`)

**What you CAN do:**
- Edit `.env.example` (it contains only placeholders, never real values)
- Tell the user what variables to add/change and let them edit manually
- Use `grep -c VARIABLE_NAME .env` to check if a variable exists (returns count, not content)
- Reference env var names in code via `process.env.X` or `os.getenv("X")`

**What you MUST NEVER do:**
- `cat .env`, `view_file .env`, or any command that outputs credential file contents
- Write or overwrite `.env`, `.env.local`, or `.mcp.json`
- Include credential values in your responses, code comments, or logs
- Copy credential values between files

Credentials leaking into LLM context = credentials leaking to the world. Treat these files like they don't exist.

---

## Coding rules every agent must follow

1. **Never bypass the layer boundary.** If `api/routers/strategy.py` needs market data, it calls a use case, which calls the broker adapter — not the broker SDK directly.

2. **Never put business logic in routers or components.** HTTP handlers validate input and delegate. React components render and delegate. Logic lives in use cases or domain rules.

3. **New broker = new adapter only.** Adding Coinbase, Kraken, or any other broker means one new file in `infrastructure/brokers/`. Nothing else changes.

4. **New strategy = new file + one registry line.** Create the strategy in `infrastructure/backtrader/strategies/`, register it in `api/routers/strategy.py`. Nothing else changes.

5. **Pydantic schemas are not domain entities.** Request/response models in `api/routers/` are API contracts. Domain entities in `modules/*/domain/entities/` are business concepts. Keep them separate.

6. **No direct `fetch` in React components.** Data fetching belongs in `src/modules/*/infrastructure/` or `src/shared/infrastructure/`. Components receive data as props or via hooks that call infrastructure.

7. **Do not add error handling for impossible cases.** Trust the layer above to validate. Trust the broker adapter interface. Only handle errors at system boundaries (incoming HTTP, external API responses).

8. **Never read or modify `.env` files.** Only `.env.example` may be edited. See the Security section above.

9. **All MCP adapters receive pre-fetched data.** Infrastructure adapters (`gurufocus_intelligence.py`, `finviz_intelligence.py`, `fred_macro_intelligence.py`) never call MCP tools directly. The orchestrator fetches MCP data and passes it to adapters for structured interpretation. This maintains Clean Architecture boundaries.

10. **Daemon data providers use fallback chains.** Code in `backend/daemons/` and `backend/scripts/` should try MCP first, then fall back to SDK/scraper. Never fail silently — always log the fallback. Module infrastructure adapters (`backend/modules/*/infrastructure/`) read ONLY from the Vault (Neon PostgreSQL via TimescaleDataStore). They do NOT have fallback chains to external APIs. See Rule 13.

11. **Simplicity first.** No features beyond what was asked. No abstractions for single-use code. No speculative "flexibility" or "configurability." If 200 lines could be 50, rewrite it. The test: would a senior engineer say this is overcomplicated? If yes, simplify.

12. **Surgical changes.** Every changed line must trace directly to the user's request. Don't "improve" adjacent code, comments, or formatting. Match existing style. If you notice unrelated dead code, mention it — don't delete it. Remove only imports/variables/functions that YOUR changes made unused.

13. **Vault-First data access.** Production modules (everything under `backend/modules/`) MUST read market data exclusively from `TimescaleDataStore` (Neon PostgreSQL). Direct calls to yfinance, requests, httpx, or any external API for market data are FORBIDDEN in modules. Only `backend/daemons/` and `backend/scripts/` may call external APIs. The Vault Daemon is the single writer; modules are readers only.

- `backend/daemons/` — Delivery mechanism (daemon entry points). Not a Clean Architecture application layer — these are background runners equivalent to API routers.

14. **Vault Data Schema — Single Table, Classified Tickers.**

    **ALL time-series data lives in `market.ohlcv_bars`** — stocks, ETFs, and indicators alike. Use `store.load_bars(ticker, "1d")` as the universal read interface. Never create new tables for new data types.

    **`market.ticker_metadata`** classifies each ticker. When adding a new ticker, you MUST upsert its metadata:

    ```python
    store.upsert_ticker_metadata(
        ticker="MY_INDICATOR",
        sector="Category",        # e.g. "Sentiment", "Volatility", "Options Flow"
        industry="INDICATOR",     # asset_type: "STOCK", "ETF", or "INDICATOR"
        market_cap_bucket=None,   # None for indicators, "MEGA"/"LARGE"/etc for stocks
    )
    ```

    **Vault Data Registry** — organized by indicator family. Full reference: [vault_data_registry.md](file:///root/botero-trade/.agents/references/vault/data_registry.md).

    **Storage Convention:** All time-series data lives in `market.ohlcv_bars`. For single-value indicators: `open=high=low=close=value, volume=0`. For breadth indicators: `volume=n_constituents`. Timestamps are midnight UTC (`00:00:00+00`), enforced by `TimescaleDataStore`. `market.ticker_metadata` classifies each ticker (`sector`, `industry`=`STOCK`|`ETF`|`INDICATOR`, `market_cap_bucket`).

    **Summary (by family):**

    | Family | Tickers | Bars each | Range | Interpretation |
    |---|---:|---:|---|---|
    | **S5 Market** (S5TH/FI/TW) | 3 | ~11,500 | 1980→2026 | % SP500 above 200d/50d/20d MA. TH=structural, FI=intermediate, TW=tactical |
    | **SV5 Market** (SV5TH/FI/TW) | 3 | 6,933 | 1999→2026 | % SP500 with vol MA crossover. TH=50v>200v, FI=20v>50v, TW=EMA5v>20v |
    | **S5 Sector** (S5_{ETF}_{TH\|FI\|TW}) | 36 | ~6,900-13,600 | 1972→2026 | Per-sector breadth for 11 sectors + QQQ |
    | **SV5 Sector** (SV5_{ETF}_{TH\|FI\|TW}) | 36 | 6,933 | 1999→2026 | Per-sector volume breadth |
    | **S5CAP Sector** (S5CAP_{ETF}_{TH\|FI\|TW}) | 21 | 6,794 | 1999→2026 | Cap-weighted sector breadth (7 sectors) |
    | **Volatility** | 4 | varies | 1990→2026 | VIX, VVIX, SKEW, SV5_TURBULENCE |
    | **Sentiment** (FG) | 1 | 3,872 | 2011→2026 | CNN Fear & Greed. 0=fear, 100=greed |
    | **Options** (CBOE_PCR) | 1 | 4,924 | 2006→2026 | Put/Call ratio. High=fear |
    | **Credit** (CREDIT_RATIO) | 1 | ~4,800 | 2007→2026 | HYG/LQD ratio. Synthetic METAR station. Low=stress |
    | **Yields** (YIELD_SPREAD) | 1 | ~16,100 | 1962→2026 | TNX−IRX (10Y−13W). Synthetic METAR station. Negative=inverted |
    | **Rotation** (ROTATION_INDEX) | 1 | ~6,900 | 1999→2026 | z(XLY/XLP)+z(XLK/XLU). Synthetic METAR station. Negative=defensive |
    | **Indices** (SPX, NDQ, TNX) | 3 | varies | 1927→2026 | S&P500, Nasdaq, 10Y yield |
    | **ETFs** (SPY, QQQ, XL*, IWM, DIA) | 15 | ~2,000-8,400 | 1993→2026 | Sector + market ETFs. Real OHLCV |
    | **SP500 Stocks** | ~500 | ~1,000-16,000 | varies | Full constituents. Real OHLCV |
    | **TOTAL** | ~628 | **~5.80M bars** | | |

    **Key derived indicators:**

    | Ticker | Formula | Interpretation | Thresholds |
    |---|---|---|---|
    | `SV5_TURBULENCE` | `std(Δ_SV5TW, 10d)` | Institutional volume turbulence. How erratically institutional participation changes | P50=5.97, **>10=crisis proxy** (V40 VIX fallback), P90=12.66, P95=14.87 |
    | `VIX` | CBOE implied vol | Options market fear gauge | <20=calm, 20-28=elevated, **>28=panic** (V36 redirect) |
    | `VVIX` | Vol-of-vol | VIX instability | >120=regime transition |
    | `SKEW` | Tail risk | OTM put demand | >140=tail hedging active |
    | `FG` | CNN composite | Contrarian sentiment | <10=extreme fear (76% WR buy), >90=extreme greed (sell signal) |

    **`market.macro_data`** is LEGACY. It holds yields and breadth ADL as `(time, name, value)` scalars. New data should NOT go here — use `ohlcv_bars` with `industry='INDICATOR'` instead. Existing macro_data will be migrated over time.

    **Indicators as pseudo-OHLCV:** For indicators with only a single daily value (e.g. F&G score), store as `open=high=low=close=value, volume=0`. For indicators with real intraday range (e.g. CBOE PCR), preserve the full OHLCV.

15. **Stateful-First classification.** Every classifier that emits a discrete regime, phase, or state (vol regime, breadth cascade, credit regime, sentiment regime, Wyckoff phase, RSI regime, price phase) MUST persist transitions via `RegimeStatePort` (`shared/domain/ports/regime_state_port.py`). Consumers receive `StateSnapshot` (`shared/domain/entities/state_snapshot.py`) with `current_state`, `previous_state`, `entered_at`, `duration_bars`, and `trigger_event` — not raw strings. Point-in-time classification without temporal context is a design violation. Table: `market.regime_states`. Key format: `{classifier}:{department}:{scope}` (e.g. `vol:quality:MARKET`).

16. **Persist-then-Read for shared state.** If a module produces state that another module consumes, that state MUST be persisted to the Vault (`market.regime_states` via `RegimeStatePort`) before being read. Writers: daemons and dedicated transition use cases only. Readers: gates, entry hubs, risk managers. No in-process state passing between modules. This extends Rule 13 (Vault-First) to regime state.

17. **Decision context logging.** When a gate or use case takes a decision (ALLOW/BLOCK/REDUCE/ACCUMULATE/TRIM), its output MUST include the `StateSnapshot` of every regime it consulted. Format: `VOL_STATE: {state} (day {duration}, prev={previous}, trigger={trigger})`. This bridges live decisions and post-hoc forensic analysis (trade-forensics skill).

18. **Vault Timestamp Standard — Midnight UTC.** All daily (`1d`) OHLCV bars MUST use midnight UTC (`00:00:00+00`) as their timestamp. This is enforced centrally in `TimescaleDataStore.save_bars()`, `upsert_ohlcv_bar()`, and `upsert_ohlcv_bar_candle()` — callers do NOT need to normalize. Never bypass the DataStore to write directly to `market.ohlcv_bars` without midnight normalization. The `volume` field in breadth indicators (S5TH, S5FI, S5TW, S5_XLK_FI, etc.) stores `n_constituents` counted, not trade volume. Historical imported data (pre-daemon) has `volume=0`; daemon-computed data has `volume>0`.

20. **Universal Signal & Action Taxonomy Standard.** All gates, decision engines, and DTOs MUST emit 4-dimensional action codes adhering to the Universal Institutional Taxonomy: `[SCOPE]_[INTENT]_[EXECUTION]`.
    - **Scope Prefixes:** `MKT_` (Market/Macro), `SEC_` (Sector), `STK_` (Individual Stock/Ticker).
    - **Stock Actions (`STK_`):** `STK_ACCUMULATE_STRUCTURAL` (Trend value buy), `STK_BUY_DIP_TACTICAL` (Extreme oversold $2\sigma+$ rebound), `STK_HOLD_STABLE` (Maintain), `STK_TRIM_TACTICAL` (Harvest profit $25\%-33\%$), `STK_DISTRIBUTE_DECAY` (Agotamiento EV $\le -0.015$), `STK_EXIT_THESIS_DEATH` (Moat breach $100\%$), `STK_EXIT_TIME_STOP` (120-day vertical barrier expiry), `STK_BLOCK_CRISIS` (Crisis veto).
    - **Emergency Circuit Breaker:** `MKT_MACRO_CIRCUIT_BREAKER` (Systemic market crash / liquidity emergency — overrides all stock-level signals).
    - **Urgency Tags (FIX Protocol Tag 61/848):** `URGENCY_EMERGENCY`, `URGENCY_HIGH`, `URGENCY_NORMAL`, `URGENCY_LOW`.

21. **Standard JSON Fact Store Metadata Specification.** Every generated JSON probability table, regime tree, or rule file MUST contain a top-level `_documentation` dictionary with mandatory metadata blocks:
    - **`model_purpose`**: Descriptive explanation of the quantitative/physical model.
    - **`return_formula`**: Explicit mathematical definition of the target/return variable.
    - **`state_hierarchy`**: Breakdown of state levels (`L0` to `L3`) and dimension mapping.
    - **`taxonomy`**: Complete mapping of dimension configurations: `{d1: {n_bins, labels, value_edges}, d2: {n_bins, labels, value_edges}, d3: {n_bins, labels, value_edges}}`. Labels live strictly here, decoupling state indexing from naming conventions.
    - **`dimension_thresholds_definition`**: Numerical thresholds, value edges, and physical interpretations.
    - **`field_glossary`**: Complete glossary of every metric key in the data objects (`n`, `p_bull`, `ev`, `sharpe`, `rr_asymmetry`, `fatigue_buckets`, etc.).
    - **`signal_interpretation_policy`**: Explicit Clean Architecture declaration stating that business signals are NOT static strings in JSON, but are dynamically interpreted by pure-domain adapters (`rc_*_lookup.py`, `signal_cataloger.py`, `*_lookup.py`).

22. **Strict User Approval Before Code/File Mutations or Git Commits for Architectural Proposals.** AI agents MUST NEVER create new reference files, mutate codebase logic, or execute `git commit` / `git push` for architectural proposals, taxonomies, or plans until the USER has explicitly reviewed and approved the plan. All initial design proposals and prompts must remain in Planning Mode / Artifacts (`master_taxonomic_homologation_prompt.md`, `implementation_plan.md`) without mutating codebase files or committing to git.

23. **4-Tier Aeronautical Market Alert Taxonomy Standard (METAR / TAF / SIGMET / NOTAM).** All market observation, forecasting, hazard alert, and operational disruption services MUST strictly adhere to the 4-tier aeronautical classification:
    - **`METAR` (Multi-Station Telemetry):** Routine daily observation and 72h kinematic velocity ($\Delta 3d$) across the 11 market stations (VIX, VVIX, PCR, F&G, SV5_Turbulence, SKEW, Credit Stress, Yield Curve, Sector Rotation, BSI, DXY). Always active. Endpoint: `/api/metar/*`.
    - **`TAF` (Terminal Market Forecast):** Stochastic probability matrix and horizon divergence forecast ($P_{bull}, EV$, Capital Velocity at 2.5%, 5.0%, 7.5% scales). Integrated into METAR telemetry.
    - **`SIGMET` (Severe Weather Hazard Bulletins):** Issued ONLY when a station breaches extreme hazard thresholds (VIX $\ge 28$, SKEW $\ge 145$, SV5_Turbulence surge, Yield Curve inversion, Extreme Fear capitulation, Credit Freeze). Returns `status: CLEAR` with empty list `[]` when no severe market weather is present. Endpoint: `/api/sigmet/active`.
    - **`NOTAM` (Operational Disruption Bulletins):** Reserved strictly for infrastructure outages, Neon Vault pipeline staleness, broker API connectivity failures, FOMC blackout periods, or Macro Circuit Breaker halts. Endpoint: `/api/notam/incidents`.

24. **Gaussian Sigma Scale & Symmetric Canonical Taxonomy Standard.** All indicator dimensional classification (D1 Magnitude, D2 Velocity, D3 Station Volatility) MUST use Gaussian Normal Distribution σ-percentile edges applied to the **full historical population** of each indicator in the Neon Vault. **Full policy in [gaussian_scale_calibration_policy.md](file:///root/botero-trade/.agents/references/metar/gaussian_scale_policy.md) and [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md).**
    - **Numeric Vector State Keys:** All Fact Store keys are formatted as normalized numeric strings: `"{d1}__{d2}__{d3}"` where $d1 \in [0..5]$, $d2 \in [0..4]$, $d3 \in [0..4]$. Labels do NOT form state keys.
    - **Centralized Classifier:** All dimension classification and label resolution MUST delegate to [`metar_classifier.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/metar_classifier.py) (`classify_bin()`, `make_state_key()`, `resolve_label()`).
    - **D1 (6 bines, 5 edges):** Percentiles `[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]` → `[-2σ, -1σ, μ, +1σ, +2σ]`.
      Symmetric pattern: `EXTREME_{concept} (0)` / `{concept} (1)` / `NEUTRAL_{bias} (2)` / `NEUTRAL_{antonym_bias} (3)` / `{antonym} (4)` / `EXTREME_{antonym} (5)`.
      - **VIX**: `EXTREME_COMPLACENCY | COMPLACENCY | NEUTRAL_CALM | NEUTRAL_ALERT | PANIC | EXTREME_PANIC`
      - **VVIX**: `EXTREME_STABILITY | STABILITY | NEUTRAL_STABLE | NEUTRAL_UNSTABLE | INSTABILITY | EXTREME_INSTABILITY`
      - **PCR**: `EXTREME_CALL_EUPHORIA | CALL_EUPHORIA | NEUTRAL_CALL_BIAS | NEUTRAL_PUT_BIAS | PUT_PANIC | EXTREME_PUT_PANIC`
      - **FG**: `EXTREME_FEAR | FEAR | NEUTRAL_FEAR | NEUTRAL_GREED | GREED | EXTREME_GREED`
      - **SV5 Turb**: `EXTREME_CALM | CALM | NEUTRAL_CALM | NEUTRAL_TURBULENT | TURBULENT | EXTREME_TURBULENT`
      - **SKEW**: `EXTREME_CONFIDENCE | CONFIDENCE | NEUTRAL_CONFIDENT | NEUTRAL_PARANOID | PARANOIA | EXTREME_PARANOIA`
      - **Credit**: `EXTREME_STRESS | STRESS | NEUTRAL_TIGHT | NEUTRAL_LOOSE | EASE | EXTREME_EASE`
      - **Yield**: `DEEP_INVERSION | MODERATE_INVERSION | FLAT_CURVE | NORMAL_CURVE | STEEPNING_CURVE | EXTREME_STEEPNING`
      - **Rotation**: `EXTREME_DEFENSIVE | DEFENSIVE | NEUTRAL_DEFENSIVE | NEUTRAL_OFFENSIVE | OFFENSIVE | EXTREME_OFFENSIVE`
      - **BSI**: `BREADTH_WASHED_OUT | OVERSOLD_BREADTH | NEUTRAL_LOW_BREADTH | NEUTRAL_HIGH_BREADTH | EXPANSIVE_BREADTH | HYPER_EXPANSIVE_BREADTH`
      - **DXY**: `EXTREME_WEAKNESS | WEAKNESS | NEUTRAL_WEAK | NEUTRAL_STRONG | STRENGTH | EXTREME_STRENGTH`
    - **D2 (5 bines, 4 edges):** Percentiles `[0.0228, 0.1587, 0.8413, 0.9772]` → `[-2σ, -1σ, +1σ, +2σ]`. Labels: `FAST_CRUSH_3D | DECELERATING_DOWN_3D | STABLE_CONTINUATION_3D | ACCELERATING_UP_3D | FAST_SPIKE_3D`.
    - **D3 (5 bines, 4 edges):** Same percentiles as D2. Labels: `VOL_EXTREME_SQUEEZE | VOL_MODERATE_COMPRESSION | VOL_NEUTRAL_BASELINE | VOL_ACCELERATING_EXPANSION | VOL_PEAK_DECELERATION`.
    - **"Extreme" = ±2σ (P2.28% / P97.72%)** — no exceptions. Edges are **empirical quantiles** (`series.quantile()`), NOT parametric `μ ± kσ`. D2 uses `diff(3)`, D3 uses `std(2d)/std(10d)` (V1.1).
    - **Recalibration** required when Vault population grows >20% or after structural regime shift. Run all station generators atomically.
    - **Integrity Guard:** Automated verification enforced by [`test_taxonomy_integrity.py`](file:///root/botero-trade/tests/test_taxonomy_integrity.py) (46 tests).

25. **Same-Day Trading Session Telemetry Freshness Standard for METAR Queries.**
    When responding to a user request for "today's METAR" or market health on an active trading day, the system/agent MUST NEVER present stale data from prior trading days. The agent MUST:
    - Audit the latest bar timestamps in the Neon Vault.
    - If the Vault has not yet ingested today's intraday / session close data for market tickers (`SPY`, `HYG`, `LQD`, `S5TW`, `CREDIT_RATIO`, `VIX`), force an immediate data refresh into `market.ohlcv_bars` and recompute synthetic indicators.
    - Evaluate and return the METAR Convergence Report using **today's exact date**.

26. **Zero Simplification Bias — Complete and Correct Over Convenient.** AI agents MUST NEVER reduce scope, merge modules, flatten architectures, or propose "simpler" alternatives that degrade the mathematical precision, domain-specific physics, or information density of the solution. Specifically:
    - **No scope reduction disguised as optimization.** If 10 components each have domain-specific logic, upgrading all 10 individually is the correct path — not merging them into 1 generic script to "save code." Code duplication is preferable to domain knowledge destruction.
    - **No sycophantic reversals.** If the user challenges a recommendation, the agent MUST either (a) defend the recommendation with evidence, or (b) present the honest tradeoff matrix with all paths and their costs — NOT instantly agree and flip 180° without substance. Intellectual honesty > user appeasement.
    - **No premature generalization.** Each METAR station, trading module, or domain classifier has its own physics. Two modules that "look similar" may encode fundamentally different market mechanics. Always audit the actual domain logic before proposing consolidation.
    - **The test:** Would a senior quant say "this shortcut loses information"? If yes, take the longer path.

