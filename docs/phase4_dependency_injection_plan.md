# Phase 4: Dependency Injection — Remaining Clean Architecture Work

> **Status**: Ready to execute  
> **Prerequisite**: Phases 1-3 completed (78% compliance)  
> **Target**: 92% compliance  
> **Estimated effort**: ~3 hours  
> **Skill reference**: `.agent/clean_architecture_skill.md` (read this FIRST)

---

## Context

The Botero Trade Engine backend follows a Modular Hexagonal Architecture. Phases 1-3 established:
- All 10 modules have the standard 5-folder domain structure
- 11 Port ABCs are defined across 6 modules
- All legacy import paths are fixed
- All domain/rules files are pure (no SDK/infra imports)

**The remaining work is Phase 4**: refactor 17 Use Case constructors to accept Port interfaces via dependency injection instead of directly importing infrastructure adapters.

---

## The Pattern

Every fix follows this exact pattern:

### Before (violation)
```python
# domain/use_cases/some_use_case.py
class SomeUseCase:
    def __init__(self):
        from backend.modules.x.infrastructure.y_adapter import YAdapter  # ❌ VIOLATION
        self._provider = YAdapter()
```

### After (compliant)
```python
# domain/use_cases/some_use_case.py
from backend.modules.x.domain.ports.y_port import YPort

class SomeUseCase:
    def __init__(self, provider: YPort):  # ✅ Injected Port
        self._provider = provider
```

### Wiring (composition root)
```python
# In API router or factories.py
from backend.modules.x.infrastructure.y_adapter import YAdapter
from backend.modules.x.domain.use_cases.some_use_case import SomeUseCase

use_case = SomeUseCase(provider=YAdapter())
```

---

## Violations to Fix (17 total, ordered by priority)

### 🔴 Priority 1: `portfolio_management` (8 violations)

#### File: `backend/modules/portfolio_management/domain/use_cases/scan_alpha.py`
**5 violations** — Lines 139, 145, 151, 157, 163

| Line | Current Import | Target Port |
|---|---|---|
| 139 | `backend.infrastructure.data_providers.finnhub_intelligence.FinnhubIntelligence` | `FundamentalDataPort` |
| 145 | `backend.infrastructure.data_providers.gurufocus_intelligence.GuruFocusIntelligence` | `FundamentalDataPort` |
| 151 | `backend.infrastructure.data_providers.finviz_intelligence.FinvizIntelligence` | `ScreenerPort` |
| 157 | `backend.infrastructure.data_providers.sector_flow.SectorFlowEngine` | `ScreenerPort` |
| 163 | `backend.infrastructure.data_providers.uw_intelligence.UnusualWhalesIntelligence` | `WhaleFlowPort` (from `flow_intelligence`) |

**Action**: Refactor `AlphaScanner.__init__()` to accept `FundamentalDataPort`, `ScreenerPort`, and `WhaleFlowPort` as constructor parameters.

Port locations:
- `backend/modules/portfolio_management/domain/ports/fundamental_data_port.py`
- `backend/modules/portfolio_management/domain/ports/screener_port.py`
- `backend/modules/flow_intelligence/domain/ports/whale_flow_port.py`

#### File: `backend/modules/portfolio_management/domain/use_cases/filter_universe.py`
**3 violations** — Lines 35, 40, 45

| Line | Current Import | Target Port |
|---|---|---|
| 35 | `backend.infrastructure.data_providers.gurufocus_intelligence.GuruFocusIntelligence` | `FundamentalDataPort` |
| 40 | `backend.infrastructure.data_providers.options_awareness.OptionsAwareness` | `OptionsDataPort` (from `options_gamma`) |
| 45 | `backend.infrastructure.data_providers.market_breadth.MarketBreadthProvider` | New: `MarketBreadthPort` or fold into `ScreenerPort` |

**Action**: Refactor `UniverseFilter.__init__()` to accept injected ports.

Port locations:
- `backend/modules/portfolio_management/domain/ports/fundamental_data_port.py`
- `backend/modules/options_gamma/domain/ports/options_data_port.py`

---

### 🟡 Priority 2: `shared` (3 violations)

#### File: `backend/modules/shared/domain/use_cases/shared_use_cases.py`
**3 violations** — Lines 10, 11, 12

| Line | Current Import | Target Port |
|---|---|---|
| 10 | `backend.modules.simulation.infrastructure.backtrader.data_feeds.create_data_feed` | `BrokerPort` or new `BacktestPort` |
| 11 | `backend.modules.simulation.infrastructure.backtrader.base_strategy.BaseStrategy` | Part of simulation infrastructure |
| 12 | `backend.modules.execution.infrastructure.brokers.base.BrokerAdapter` | `BrokerPort` |

**Action**: This file orchestrates across modules. Consider either:
1. Converting functions to accept ports as arguments, or
2. Moving these orchestration functions to the API layer (they're really composition root logic)

Port location:
- `backend/modules/execution/domain/ports/broker_port.py` — `BrokerPort`

---

### 🟡 Priority 3: `entry_decision` (2 violations)

#### File: `backend/modules/entry_decision/domain/use_cases/evaluate_entry.py`
**2 violations** — Lines 59, 103

| Line | Current Import | Target Port |
|---|---|---|
| 59 | `backend.modules.entry_decision.infrastructure.market_data_fetcher.MarketDataFetcher` | `EntryMarketDataPort` |
| 103 | `backend.modules.flow_intelligence.infrastructure.uw_adapter.UnusualWhalesIntelligence` | `FlowDataPort` |

**Action**: Refactor `EntryIntelligenceHub.__init__()` to accept `EntryMarketDataPort` and `FlowDataPort`.

Port locations:
- `backend/modules/entry_decision/domain/ports/market_data_port.py` — `EntryMarketDataPort`
- `backend/modules/entry_decision/domain/ports/flow_data_port.py` — `FlowDataPort`

---

### 🟡 Priority 4: `execution` (2 violations)

#### File: `backend/modules/execution/domain/use_cases/orchestrate_paper_trading.py`
**1 violation** — Line 538

| Line | Current Import | Target Port |
|---|---|---|
| 538 | `backend.infrastructure.data_providers.event_flow_intelligence.EventFlowIntelligence` | Refactor to use `EventFlowIntelligence` from `flow_intelligence/domain/use_cases/` directly (it's already a use case, not infra) |

#### File: `backend/modules/execution/domain/use_cases/orchestrate_scans.py`
**1 violation** — Line 93

| Line | Current Import | Target Port |
|---|---|---|
| 93 | `backend.infrastructure.data_providers.fundamental_cache.FundamentalCache` | `FundamentalDataPort` |

---

### 🟢 Priority 5: Single violations

#### `backend/modules/options_gamma/domain/use_cases/analyze_gamma.py`
**1 violation** — Line 27

| Line | Current Import | Target Port |
|---|---|---|
| 27 | `backend.modules.options_gamma.infrastructure.yfinance_adapter.YFinanceOptionsAdapter` | `OptionsDataPort` |

Port: `backend/modules/options_gamma/domain/ports/options_data_port.py`

#### `backend/modules/simulation/domain/use_cases/run_backtest.py`
**1 violation** — Line 44

| Line | Current Import | Target Port |
|---|---|---|
| 44 | `backend.infrastructure.data_providers.volume_dynamics` | Dead import — verify if still needed, or refactor to use `volume_intelligence/domain/use_cases/` |

---

## Composition Root

After refactoring all Use Cases, create a composition root to wire everything:

### File to create: `backend/modules/factories.py`

```python
"""
Composition Root — wires concrete infrastructure adapters into domain Use Cases.

This is the ONLY place where infrastructure meets domain.
API routers and orchestrators call these factories.
"""

# === Options Gamma ===
def create_options_awareness():
    from backend.modules.options_gamma.infrastructure.yfinance_adapter import YFinanceOptionsAdapter
    from backend.modules.options_gamma.domain.use_cases.analyze_gamma import OptionsAwareness
    return OptionsAwareness(options_provider=YFinanceOptionsAdapter())

# === Entry Decision ===
def create_entry_hub():
    from backend.modules.entry_decision.infrastructure.market_data_fetcher import MarketDataFetcher
    from backend.modules.entry_decision.domain.use_cases.evaluate_entry import EntryIntelligenceHub
    return EntryIntelligenceHub(market_data=MarketDataFetcher())

# === Portfolio Management ===
def create_alpha_scanner():
    from backend.modules.portfolio_management.domain.use_cases.scan_alpha import AlphaScanner
    # Wire all 5 providers here
    return AlphaScanner(
        # fundamental_data=...,
        # screener=...,
        # whale_flow=...,
    )

# ... one factory per Use Case that needs infrastructure ...
```

Then update API routers to use factories:
```python
# backend/api/routers/strategy.py
from backend.modules.factories import create_entry_hub

@router.post("/evaluate/{ticker}")
async def evaluate(ticker: str):
    hub = create_entry_hub()
    return hub.evaluate(ticker)
```

---

## Verification Checklist

After completing all fixes, run:

```bash
# 1. Compile check
PYTHONPATH=backend python3 -m compileall backend/

# 2. Zero domain→infra imports remaining
grep -rn "infrastructure" backend/modules/*/domain/use_cases/ --include="*.py" | grep -v __pycache__
# Expected: ZERO results (or only comments/docstrings)

# 3. All Ports have implementations
grep -rn "class.*Port.*ABC\|class.*ABC" backend/modules/*/domain/ports/ --include="*.py"
# Expected: 11+ Port definitions

# 4. Run existing tests
PYTHONPATH=backend python3 -m pytest tests/ -v

# 5. Audit script
PYTHONPATH=backend python3 -c "
import subprocess
r = subprocess.run(['grep','-rn','infrastructure','--include=*.py'] + 
    ['backend/modules/'+m+'/domain/use_cases/' for m in 
     ['entry_decision','execution','flow_intelligence','options_gamma',
      'pattern_recognition','portfolio_management','price_analysis',
      'simulation','volume_intelligence','shared']],
    capture_output=True, text=True)
lines = [l for l in r.stdout.strip().split(chr(10)) if l and 'import' in l]
print(f'Domain→Infra violations: {len(lines)}')
if lines:
    for l in lines: print(f'  {l[:120]}')
else:
    print('✅ ALL USE CASES ARE FULLY ISOLATED')
"
```

---

## Important Notes for the Executing Agent

1. **Read `.agent/clean_architecture_skill.md` before starting** — it contains all rules.
2. **Some violations reference `backend.infrastructure.data_providers/`** — this is a legacy path that no longer exists as a directory. These imports are dead code from before the modular migration. Verify whether the referenced classes were already migrated into module infrastructure folders, or if they need to be.
3. **The `shared/use_cases.py` violations are architectural** — the functions there (`run_backtest`, `place_order`) are orchestration logic that arguably belongs in the API layer, not in a shared use case. Consider moving them.
4. **Don't break backward compatibility** — when refactoring a constructor, ensure all callers pass the new parameters. Search for class instantiation sites.
5. **Test after each file** — run `PYTHONPATH=backend python3 -m compileall backend/` after every modification.
