"""
MarketHealthSnapshot — 6D Convergence + F&G Contrarian Layer.

Pure domain entity. No infrastructure dependencies.
Produced by compute_market_health(), persisted by daemon,
read by SwingGate, QualityEntryGate, CIO, and SpeculativeEntryHub.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, UTC


@dataclass
class MarketHealthSnapshot:
    """6-dimensional market health at a point in time.

    Convergence score counts how many of 6 orthogonal dimensions
    agree on direction (RISK_ON or RISK_OFF). F&G is NOT a convergence
    dimension — it is a contrarian signal layer that validates or
    diverges from the internal score.
    """
    timestamp: str = ""

    # ── G1: Breadth Cascade (Structure) ──────────────────────
    cascade_state: int = 0              # 0=HEALTH, 1=PULLBACK, 2=CORRECTION, 3=BEAR
    cascade_spread: float = 0.0         # (S5TH - S5TW) / 100
    narrow_market: bool = False         # SPY↑ but S5FI↓
    breadth_participation: float = 0.5  # mean(S5TH, S5FI, S5TW) / 100

    # ── G2: Volatility Regime (Protection) ───────────────────
    vol_regime_quality: str = "NORMAL"       # COMPLACENT/NORMAL/ELEVATED/CRISIS
    vol_regime_speculative: str = "STALK"    # STALK/STRIKE/HARVEST/RETREAT

    # ── G3: Institutional Flow ───────────────────────────────
    flow_direction: str = "NEUTRAL"     # BULLISH/NEUTRAL/BEARISH

    # ── G4: Credit Health ────────────────────────────────────
    credit_regime: str = "NORMAL"       # STRESS/NORMAL/RISK_ON
    credit_spread_zscore: float = 0.0

    # ── G5: Sector Rotation ──────────────────────────────────
    rotation_phase: str = "UNKNOWN"     # Pring cycle phase
    dominant_rotation: str = "NEUTRAL"
    capitulation_level: int = 0         # 0-4

    # ── G6: Macro Cycle (Dalio) ──────────────────────────────
    yield_curve_signal: str = "NORMAL"  # NORMAL/FLAT/INVERTED/STEEPENING
    macro_regime: str = "UNKNOWN"       # from FRED snapshot
    fed_stance: str = "UNKNOWN"         # HAWKISH/NEUTRAL/DOVISH

    # ── Convergence Composite (6 dimensions) ─────────────────
    convergence_score: int = 0              # 0-6 dimensions converging
    convergence_direction: str = "NEUTRAL"  # RISK_ON/NEUTRAL/RISK_OFF

    # ── Fear & Greed: Contrarian Signal Layer ────────────────
    # NOT a convergence dimension. Operates independently.
    # F&G is LAGGING (corr +0.61 same-day) but extreme LEVELS
    # predict forward returns (FG-H01 VALIDATED, t=6.39).
    fg_score: float = 50.0                  # Raw 0-100
    fg_regime: str = "NEUTRAL"              # EXTREME_FEAR/FEAR/NEUTRAL/GREED/EXTREME_GREED
    fg_zscore: float = 0.0                  # Rolling 60d z-score
    fg_velocity: float = 0.0               # 5d ROC z-scored
    fg_direction: str = "STABLE"            # FALLING/STABLE/RISING
    fg_action: str = "NONE"                 # CAPITULATION_BUY/FEAR_BUY/NONE/
                                            # GREED_CAUTION/GREED_TRAP
    fg_duration: int = 0                    # Consecutive days in extreme regime
    fg_urgency: str = "NORMAL"              # HIGH (day 1-3) / NORMAL / DECAYING (day 10+)
    fg_confirms_internal: bool = True       # F&G agrees with convergence_direction?
    fg_divergence_type: str = "NONE"        # CONFIRMING/STEALTH_ACCUMULATION/
                                            # DISTRIBUTION_WARNING/CONTRARIAN_BUY

    def to_dict(self) -> dict:
        """Serialize for mcp_snapshot persistence."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MarketHealthSnapshot":
        """Deserialize from mcp_snapshot dict."""
        if not d:
            return cls()
        # Only pass fields that exist in the dataclass
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid}
        return cls(**filtered)
