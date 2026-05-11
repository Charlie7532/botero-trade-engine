"""
Market Structure Port — SMC Analysis Abstraction
===================================================
Decouples simulation from the concrete smartmoneyconcepts library.
Provides BOS, CHoCH, Order Blocks, FVG, and liquidity sweep detection.

Implementor: smc_adapter.py (Phase 2)

NOTE: Canonical location is now shared/domain/ports/market_structure_port.py.
This file re-exports for backward compatibility.
"""
from backend.modules.shared.domain.ports.market_structure_port import (  # noqa: F401
    MarketStructurePort,
    MarketStructureResult,
)
