---
name: clean-architecture
description: Enforce Clean & Hexagonal Architecture rules across the Botero Trade Engine codebase. Use this whenever writing new modules, refactoring existing code, or reviewing architecture compliance.
---

# Botero Trade Engine: Clean & Hexagonal Architecture Standard

This document is a mandatory instruction set for any AI agent interacting with the Botero Trade Engine codebase. It dictates the exact structural rules and conventions following **Clean Architecture** (Robert C. Martin) and **Hexagonal Architecture** (Alistair Cockburn) principles.

---

## 1. The Core Paradigm: Modular Hexagonal Architecture

The backend is a **Modular Monolith**. Every business capability is isolated into its own independent feature module under `backend/modules/`.

### The Golden Rule: Dependencies Point INWARD

```
     ┌─────────────────────────────┐
     │   API / Routers  (outer)    │  ← knows about everything below
     ├─────────────────────────────┤
     │   Infrastructure            │  ← implements Ports; knows Domain
     │   (Adapters — Driven Side)  │
     ├─────────────────────────────┤
     │   Domain                    │  ← knows NOTHING outside itself
     │   Use Cases ← Ports (ABCs) │     Depends on Ports, never Adapters
     │   Entities, Rules           │
     └─────────────────────────────┘
```

**Hexagonal terminology:**
- **Ports** = Abstract interfaces (ABCs) declared inside `domain/ports/`. They define *what* the domain needs from the outside world (data fetching, execution, persistence) without knowing *how*.
- **Adapters** = Concrete implementations living in `infrastructure/`. They satisfy the Ports by connecting to yfinance, Alpaca, MongoDB, etc.
- **Driving Side** = API routers, CLI, or orchestrators that *call into* the domain.
- **Driven Side** = Infrastructure adapters that the domain *calls out to* — but only through Ports.

### Module Interaction Rules
- Modules interact via absolute imports starting from `backend.modules.`.
- A module may import another module's **Entities** or call its **Use Cases**.
- A module must NEVER directly import another module's **Infrastructure**.
- Shared foundational types live in `backend/modules/shared/`.

---

## 2. Module Structure (Screaming Architecture)

EVERY module inside `backend/modules/` MUST adhere to this exact directory structure. No exceptions.

```text
backend/modules/<module_name>/
├── __init__.py              # Public API — re-exports key classes for external consumers
├── domain/                  # The pure heart. NO external libraries (except numpy/pandas for math).
│   ├── dtos/                # Data Transfer Objects (pure dataclasses for cross-layer communication)
│   ├── entities/            # Core business models (dataclasses, enums, @property getters ONLY)
│   ├── ports/               # Abstract Base Classes (ABCs) — interfaces for infrastructure
│   ├── rules/               # Constants, thresholds, pure functions, formulas
│   └── use_cases/           # Business logic orchestrators. Depend on Ports, never Adapters.
└── infrastructure/          # External connections (optional — some modules are pure domain)
    └── ...                  # Concrete adapters implementing Ports (yfinance, Alpaca, MongoDB, etc.)
```

---

## 3. File Size and Responsibility Limits

- **No Monolith Engines**: Do not create "god files" like `engine.py`. Break logic down by use-case.
  - *Bad*: `price_engine.py` (doing everything)
  - *Good*: `detect_price_phase.py` and `analyze_rsi.py` (inside `use_cases/`)
- **Entities are Data**: `domain/entities/` files contain `@dataclass`, `Enum`, and simple `@property` getters. They must NEVER execute business logic, fetch data, or import infrastructure.
- **Rules are Pure Logic**: `domain/rules/` files contain static pure functions, constants, and threshold maps. No side effects, no I/O.
- **Use Cases are Orchestrators**: They coordinate business logic by calling Rules and other Use Cases, receiving external data through injected Ports.

---

## 4. The End of Global Domains

There is no global `backend/domain/entities.py`. Foundational entities live in their owning module:

| Entity | Location |
|---|---|
| `Order`, `Trade`, `Broker`, `OrderSide`, `OrderStatus`, `OrderType` | `backend/modules/execution/domain/entities/order_models.py` |
| `Position`, `Portfolio` | `backend/modules/portfolio_management/domain/entities/portfolio_models.py` |
| `Bar` (Market Data) | `backend/modules/shared/domain/entities/market_data.py` |
| `Signal` | `backend/modules/entry_decision/domain/entities/signal.py` |
| `BacktestResult`, `WindowResult`, `BacktestReport` | `backend/modules/simulation/domain/entities/simulation_models.py` |

When a module needs a foundational type, it imports explicitly:
```python
from backend.modules.shared.domain.entities.market_data import Bar
from backend.modules.execution.domain.entities.order_models import Broker, Order
```

---

## 5. Ports & Adapters (Hexagonal Wiring)

This is the most critical section for maintaining true Hexagonal compliance.

### The Rule
**Use Cases MUST depend on Ports (ABCs), never on concrete infrastructure.**

### The Pattern

```python
# 1. DEFINE the Port in domain/ports/
# backend/modules/options_gamma/domain/ports/options_data_port.py
from abc import ABC, abstractmethod

class OptionsDataPort(ABC):
    @abstractmethod
    def get_options_chain(self, symbol: str) -> dict: ...

    @abstractmethod
    def get_max_pain(self, symbol: str) -> float: ...
```

```python
# 2. USE the Port in application/use_cases/ (constructor injection)
# backend/modules/options_gamma/application/use_cases/analyze_gamma.py
class OptionsAwareness:
    def __init__(self, options_provider: OptionsDataPort):
        self._provider = options_provider  # Interface, not concrete class

    def analyze(self, symbol: str) -> OptionsAnalysis:
        chain = self._provider.get_options_chain(symbol)
        # ... pure business logic ...
```

```python
# 3. IMPLEMENT the Port in infrastructure/
# backend/modules/options_gamma/infrastructure/yfinance_adapter.py
from backend.modules.options_gamma.domain.ports.options_data_port import OptionsDataPort

class YFinanceOptionsAdapter(OptionsDataPort):
    def get_options_chain(self, symbol: str) -> dict:
        import yfinance as yf
        # ... concrete implementation ...
```

```python
# 4. WIRE at the composition root (API layer, factory, or orchestrator)
adapter = YFinanceOptionsAdapter()
engine = OptionsAwareness(options_provider=adapter)
result = engine.analyze("AAPL")
```

### Why This Matters
- Use Cases become **100% unit-testable** with mock Ports — no network, no API keys
- Swapping yfinance → Interactive Brokers = change 1 adapter file, zero domain changes
- The domain remains a pure, deterministic function of its inputs

---

## 6. Cross-Module Import Matrix

| From ↓ \ To → | Own Entities | Own Rules | Own Use Cases | Own Ports | Own Infra | Other Module Entities | Other Module Use Cases | Other Module Infra | Shared |
|---|---|---|---|---|---|---|---|---|---|
| **domain/entities** | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ Shared only | ❌ | ❌ | ✅ |
| **domain/rules** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **domain/ports** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **application/use_cases** | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |
| **infrastructure** | ✅ | ✅ | ❌ | ✅ (implements) | ✅ | ✅ | ❌ | ❌ | ✅ |
| **API routers** | ✅ | ❌ | ✅ | ❌ | ✅ (wiring) | ✅ | ✅ | ✅ (wiring) | ✅ |

**Key rules:**
- `application/use_cases/` → ❌ NEVER imports from any `infrastructure/` (use Ports instead)
- `infrastructure/` → ❌ NEVER imports from `application/use_cases/` (adapters don't orchestrate)
- Cross-module infrastructure imports are ALWAYS forbidden

---

## 7. Import Standards

- **Always use absolute imports** starting from `backend.modules.`:
  ```python
  # ✅ CORRECT
  from backend.modules.price_analysis.application.use_cases.detect_price_phase import PricePhaseIntelligence

  # ❌ WRONG — legacy pattern, must be migrated
  from modules.price_analysis.application.use_cases.detect_price_phase import PricePhaseIntelligence
  ```
- **Never use relative imports** spanning across modules.
- **Never use `from modules.` without the `backend.` prefix** — this is a legacy pattern that must be eliminated.

---

## 8. Testing Architecture

Clean Architecture's core benefit is **testability without external dependencies**.

### Unit Tests (Domain Layer)
- Test Use Cases by injecting **mock/stub Ports** — never real adapters.
- Domain tests must run with **zero network access**, zero API keys, zero databases.
- Example:
  ```python
  class MockOptionsPort(OptionsDataPort):
      def get_options_chain(self, symbol):
          return {"calls": [...], "puts": [...]}  # Deterministic test data

  def test_gamma_analysis():
      engine = OptionsAwareness(options_provider=MockOptionsPort())
      result = engine.analyze("AAPL")
      assert result.gamma_regime in ("PIN", "DRIFT", "SQUEEZE")
  ```

### Integration Tests (Infrastructure Layer)
- Test that adapters correctly implement their Ports.
- These tests MAY require network access or API keys.
- Keep them separate from domain unit tests.

### Verification Command
Before finalizing any restructuring or file movement:
```bash
PYTHONPATH=backend python3 -m compileall backend/
```

---

## 9. Known Violations (Technical Debt)

The following are acknowledged violations of the architecture that exist in the current codebase. They should be incrementally fixed but must NEVER be used as precedent for new code.

### Domain → Infrastructure Imports (18 violations)
Use Cases that directly import infrastructure adapters instead of going through Ports:

| File | Violation |
|---|---|
| `options_gamma/application/use_cases/analyze_gamma.py` | Imports `infrastructure.yfinance_adapter` (Port exists — unwired) |
| `entry_decision/application/use_cases/evaluate_entry.py` | Imports `infrastructure.market_data_fetcher` (Port exists — unwired) |
| `entry_decision/application/use_cases/evaluate_entry.py` | Imports `flow_intelligence/infrastructure.uw_adapter` (Port exists — unwired) |
| `execution/application/use_cases/orchestrate_paper_trading.py` | Imports Alpaca SDK directly + `infrastructure.data_providers` + `os.getenv` |
| `execution/application/use_cases/orchestrate_scans.py` | Imports `backend.infrastructure.data_providers.fundamental_cache` |
| `execution/application/use_cases/monitor_positions.py` | Imports Alpaca SDK directly + `os.environ` |
| `execution/application/use_cases/journal_trades.py` | Reads `os.getenv('MONGODB_URI')` — domain must not know DB credentials |
| `portfolio_management/application/use_cases/scan_alpha.py` | Imports `backend.infrastructure.data_providers.*` (×5) + `yfinance` |
| `portfolio_management/application/use_cases/filter_universe.py` | Imports `backend.infrastructure.data_providers.*` (×3) |
| `portfolio_management/application/use_cases/qualify_ticker.py` | `import yfinance as yf` at top level |
| `simulation/application/use_cases/calibrate_strategy.py` | Imports `infrastructure.data_harmonizer` |
| `simulation/application/use_cases/pre_trade_gate.py` | Imports `infrastructure.data_harmonizer` |
| `shared/application/use_cases/shared_use_cases.py` | Imports `backtrader`, `simulation/infrastructure/backtrader/*`, `execution/infrastructure/brokers/base` |

**Fix pattern:** Define a Port ABC in `domain/ports/`, make the adapter implement it, inject the Port into the Use Case constructor.

### External SDK Imports in Domain (7 violations)
Domain layer imports external libraries that should only exist in infrastructure:

| File | Import |
|---|---|
| `execution/application/use_cases/orchestrate_paper_trading.py` | `yfinance`, `alpaca.trading.client`, `alpaca.data` |
| `execution/application/use_cases/monitor_positions.py` | `alpaca.trading.client`, `alpaca.trading.enums` |
| `portfolio_management/application/use_cases/qualify_ticker.py` | `yfinance` |
| `portfolio_management/application/use_cases/scan_alpha.py` | `yfinance` |
| `shared/application/use_cases/shared_use_cases.py` | `backtrader` |

### Legacy Import Paths
✅ **Resolved.** No remaining `from modules.` (without `backend.` prefix) imports found.

### Ports Status
7 of 10 modules now have real Port definitions with abstract methods. Remaining modules without ports:
- `price_analysis` — pure domain, no infra needed ✅
- `volume_intelligence` — pure domain, no infra needed ✅
- `pattern_recognition` — pure domain, no infra needed ✅

### God Files (>500 LOC in domain)
| File | LOC |
|---|---|
| `execution/application/use_cases/orchestrate_paper_trading.py` | 793 |
| `entry_decision/application/use_cases/evaluate_entry.py` | 682 |
| `portfolio_management/application/use_cases/qualify_ticker.py` | 601 |

---

## 10. Adding New Code — Decision Tree

```
Is it a data structure with no behavior?
  → domain/entities/ (dataclass + enums + @property)

Is it a constant, threshold, or pure formula?
  → domain/rules/ (static functions, no I/O)

Is it an interface for external data/services?
  → domain/ports/ (ABC with abstract methods)

Is it business logic orchestrating rules and entities?
  → application/use_cases/ (receives Ports via constructor)

Is it a connection to an external API, DB, or SDK?
  → infrastructure/ (implements a Port from domain/ports/)

Is it cross-module data transfer prep?
  → domain/dtos/ (pure dataclass, no logic)
```

---

By following this skill set, the Botero Trade Engine remains highly testable, horizontally scalable, and resilient against framework or external provider changes.
