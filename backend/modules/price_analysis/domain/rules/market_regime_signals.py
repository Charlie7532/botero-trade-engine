"""
Market Regime Signals — Research-Only Rules (López de Prado Pending)
====================================================================
These signals are LOGGED for validation but NOT used as decision gates.

SIG-003: Market Making Dominance
    When avg trade size is small for 3+ consecutive days, market makers
    dominate flow → breakouts fail. When trade size suddenly increases,
    institutional entry → breakout energy.

SIG-001: Gamma-Vanna Force Confluence
    GEX- (DRIFT) + Vanna BUYING → MELT_UP (dealers amplify + buy)
    GEX- (DRIFT) + Vanna SELLING → MELT_DOWN (dealers amplify + sell)
"""
import logging

logger = logging.getLogger(__name__)


def classify_mm_dominance(
    avg_trade_sizes: list[float],
    window: int = 3,
) -> dict:
    """
    Classify whether market makers dominate recent volume.

    Args:
        avg_trade_sizes: Daily average trade sizes (shares per trade),
                         chronologically ordered. Calculated as volume / trade_count.
        window: Number of consecutive days to evaluate.

    Returns:
        {"regime": "MM_DOMINANT"|"INSTITUTIONAL"|"MIXED",
         "avg_trade_size": float,
         "breakout_energy": bool}
    """
    if len(avg_trade_sizes) < window:
        return {"regime": "UNKNOWN", "avg_trade_size": 0.0, "breakout_energy": False}

    recent = avg_trade_sizes[-window:]
    current = avg_trade_sizes[-1]
    avg_recent = sum(recent) / len(recent)

    # Threshold calibrated from SPY empirical: avg trade ~150-200 shares
    # MM-dominated: smaller, more frequent trades (avg < 120)
    # Institutional: larger block trades (avg > 250)
    if avg_recent < 120:
        regime = "MM_DOMINANT"
    elif avg_recent > 250:
        regime = "INSTITUTIONAL"
    else:
        regime = "MIXED"

    # Breakout energy: MM-dominated for 3+ days then sudden size increase
    breakout_energy = False
    if len(avg_trade_sizes) >= window + 1:
        prior = avg_trade_sizes[-(window + 1):-1]
        prior_avg = sum(prior) / len(prior)
        if prior_avg < 120 and current > 200:
            breakout_energy = True

    return {
        "regime": regime,
        "avg_trade_size": round(avg_recent, 1),
        "breakout_energy": breakout_energy,
    }


def classify_force_confluence(
    gex_regime: str,
    vanna_event: bool,
    vanna_direction: str,
) -> str:
    """
    Detect Gamma-Vanna force confluence (SIG-001).

    GEX- (DRIFT) + Vanna BUYING → MELT_UP (positive feedback loop)
    GEX- (DRIFT) + Vanna SELLING → MELT_DOWN (cascading selling)
    Otherwise → NONE

    This is a RESEARCH signal. Pending López de Prado validation
    before promotion to decision gate.
    """
    if not vanna_event:
        return "NONE"

    if gex_regime in ("DRIFT", "SQUEEZE_UP", "SQUEEZE_DOWN"):
        if vanna_direction == "BUYING":
            return "MELT_UP"
        elif vanna_direction == "SELLING":
            return "MELT_DOWN"

    return "NONE"
