"""
Sector Breadth Gate — Pure Domain Rule
=========================================
Computes S5 sizing modifier from sector breadth state.
Zero infrastructure dependencies. Pure function, fully testable.

Empirical Evidence (engine.s5_backtest_signals, 765 signals, 3 audit rounds):
  Rule 1: COLD → boost 1.15 (N=155, WR=80.0%, Avg=+7.33%, 10/11 sectors)
  Rule 2: COLD + IMPROVING → boost 1.25 (N=29, WR=75.9%, Avg=+9.62%)
  Rule 3: NEUTRAL + ETF < MA200 → boost 1.15 (N=55, WR=87.3%, 6/6 sectors)
  Rule 4: HOT → advisory only, no penalty (N=77, WR=63.6%, still positive)
"""
from dataclasses import dataclass


# Tier-calibrated thresholds from empirical validation.
# Tier 1 (defensive) uses tighter bands; Tier 3 (cyclical) uses wider.
TIER_THRESHOLDS: dict[int, tuple[float, float]] = {
    1: (20.0, 75.0),   # Defensive: XLP, XLV, XLU, XLRE, XLB
    2: (22.0, 70.0),   # Mixed: XLE, XLF, XLC
    3: (25.0, 65.0),   # Cyclical: XLK, XLY, XLI
}


@dataclass(frozen=True)
class SectorBreadthSnapshot:
    """Immutable snapshot of sector breadth state at signal time."""

    sector_etf: str
    s5_fi_value: float
    s5_fi_market: float
    s5_fi_zone: str                    # COLD, NEUTRAL, HOT
    relative_breadth: float            # sector_fi - market_fi
    relative_roc_10d: float            # 10-day change in relative breadth
    relative_direction: str            # IMPROVING, STABLE, LOSING
    is_golden_signal: bool             # COLD + IMPROVING
    etf_above_ma200: bool
    sizing_modifier: float             # 1.0, 1.15, or 1.25
    context_label: str                 # Human-readable alert for report


def compute_sector_breadth_snapshot(
    s5_fi_sector: float,
    s5_fi_market: float,
    etf_above_ma200: bool,
    tier: int = 2,
    s5_fi_history: list[float] | None = None,
    mkt_fi_history: list[float] | None = None,
    sector_etf: str = "",
) -> SectorBreadthSnapshot:
    """
    Pure domain rule: compute S5 sizing modifier.

    Args:
        s5_fi_sector: Current S5_FI for the sector (0-100).
        s5_fi_market: Current S5FI for SPY (0-100).
        etf_above_ma200: True if sector ETF is above its 200-DMA.
        tier: 1 (defensive), 2 (mixed), 3 (cyclical).
        s5_fi_history: Last 10+ daily values of sector S5_FI (oldest first).
        mkt_fi_history: Last 10+ daily values of market S5FI (oldest first).
        sector_etf: Sector ETF symbol (e.g. 'XLK').

    Returns:
        SectorBreadthSnapshot with sizing_modifier and context.
    """
    cold_th, hot_th = TIER_THRESHOLDS.get(tier, (22.0, 70.0))

    # ── Zone classification ──
    if s5_fi_sector < cold_th:
        zone = "COLD"
    elif s5_fi_sector > hot_th:
        zone = "HOT"
    else:
        zone = "NEUTRAL"

    # ── Relative breadth (sector vs market) ──
    relative = s5_fi_sector - s5_fi_market

    # ── Relative RoC (10-day change in relative breadth) ──
    roc = 0.0
    if (
        s5_fi_history
        and mkt_fi_history
        and len(s5_fi_history) >= 10
        and len(mkt_fi_history) >= 10
    ):
        rel_now = s5_fi_history[-1] - mkt_fi_history[-1]
        rel_10d_ago = s5_fi_history[-10] - mkt_fi_history[-10]
        roc = rel_now - rel_10d_ago

    # ── Direction classification ──
    if roc > 3.0:
        direction = "IMPROVING"
    elif roc < -3.0:
        direction = "LOSING"
    else:
        direction = "STABLE"

    # ── Golden signal: COLD + IMPROVING ──
    golden = zone == "COLD" and direction == "IMPROVING"

    # ── Sizing rules (empirical) ──
    sizing = 1.0
    label_parts = []

    if zone == "COLD":
        if golden:
            sizing = 1.25
            label_parts.append(
                f"🏆 S5_GOLDEN: {s5_fi_sector:.1f}% < {cold_th}% (COLD) + IMPROVING "
                f"(RoC={roc:+.1f}pp) → sizing 1.25x"
            )
        else:
            sizing = 1.15
            label_parts.append(
                f"✅ S5_COLD: {s5_fi_sector:.1f}% < {cold_th}% → sizing 1.15x"
            )

    elif zone == "NEUTRAL" and not etf_above_ma200:
        # NEUTRAL + ETF below MA200 = SwingGate accumulation signal
        sizing = 1.15
        label_parts.append(
            f"✅ S5_ACCUMULATION: S5={s5_fi_sector:.1f}% (NEUTRAL) + "
            f"ETF < MA200 → sizing 1.15x"
        )

    elif zone == "HOT":
        sizing = 1.0
        label_parts.append(
            f"⚠️ S5_HOT: {s5_fi_sector:.1f}% > {hot_th}% — advisory, no penalty"
        )

    else:
        label_parts.append(
            f"S5_NEUTRAL: {s5_fi_sector:.1f}% — standard sizing"
        )

    # Add relative context
    label_parts.append(
        f"(S5_mkt={s5_fi_market:.1f}%, rel={relative:+.1f}pp, "
        f"dir={direction}, ETF_trend={'BULL' if etf_above_ma200 else 'BEAR'})"
    )

    return SectorBreadthSnapshot(
        sector_etf=sector_etf,
        s5_fi_value=s5_fi_sector,
        s5_fi_market=s5_fi_market,
        s5_fi_zone=zone,
        relative_breadth=relative,
        relative_roc_10d=roc,
        relative_direction=direction,
        is_golden_signal=golden,
        etf_above_ma200=etf_above_ma200,
        sizing_modifier=sizing,
        context_label=" ".join(label_parts),
    )
