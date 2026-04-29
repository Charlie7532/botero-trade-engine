"""
Execution Intent — Pre-Trade Gate Output DTO
===============================================
Immutable data transfer object emitted by PreTradeGate when a trade
is approved. This is the handoff to the execution module.

The execution module consumes this to place orders without needing
to know about simulation internals.
"""
from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass(frozen=True)
class ExecutionIntent:
    """
    Approved trade intent — ready for execution module handoff.

    Frozen (immutable) to prevent mutation after gate approval.
    """
    # ── What to trade ─────────────────────────────────────
    ticker: str
    direction: str = "LONG"         # LONG | SHORT
    category: str = ""              # InvestmentCategory.value

    # ── Sizing ────────────────────────────────────────────
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    position_scale: float = 1.0     # 0.0-1.0 (MacroGate adjusted)
    risk_reward: float = 0.0

    # ── Gate Provenance ───────────────────────────────────
    snapshot_id: str = ""           # Links back to TradeSnapshot
    gate_conviction: float = 0.0   # 0-1 composite conviction
    oracle_ceiling: float = 0.0    # Alpha ceiling Sharpe
    ml_confidence: float = 0.0     # ML model confidence

    # ── Metadata ──────────────────────────────────────────
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    portfolio_id: str = ""
