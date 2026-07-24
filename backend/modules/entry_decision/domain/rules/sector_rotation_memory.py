"""
Sector Rotation Memory — Multi-Scale Intelligence
====================================================
Pure domain entity that computes rotation intelligence from S5 breadth data.

Empirical evidence (5,462 days × 11 sectors):
  - Ranking Top 3 by Δ stocks/5d: +783.5% vs SPY +530.6% (272 periods)
  - TH 200d ≥8 sectors ≤20%: SPY fwd 120d +14.43%, WR=81.1% (N=169)
  - FI 50d ≥8 sectors ≤20%: SPY fwd 20d +3.59%, WR=70.4% (N=216)
  - Black Swan (vel < -2σ): SPY fwd 5d +0.84%, WR=67.3% (N=202)
  - Total Panic (>8 distributing): 329 losses avoided at -4.23% avg

No infrastructure dependencies. Receives data, returns snapshots.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.modules.shared.domain.constants.sectors import (
    SECTOR_CONSTITUENT_COUNTS,
    SECTOR_ETFS,
    TOTAL_SP500_CONSTITUENTS,
)

logger = logging.getLogger(__name__)

# ── Thresholds (empirically calibrated) ─────────────────────

# Stocks above/below threshold for flow regime
ACCUMULATING_THRESHOLD = 2.0   # > 2 stocks gained in 5d = accumulating
DISTRIBUTING_THRESHOLD = -2.0  # > 2 stocks lost in 5d = distributing

# Extreme thresholds for convergence signals
EXTREME_LOW_TH = 20.0    # TH ≤ 20% = deep structural low
EXTREME_LOW_FI = 20.0    # FI ≤ 20% = intermediate capitulation
EXTREME_LOW_TW = 20.0    # TW ≤ 20% = tactical oversold
EXTREME_HIGH_TH = 80.0   # TH ≥ 80% = structural bull
EXTREME_HIGH_FI = 80.0   # FI ≥ 80% = intermediate healthy
EXTREME_HIGH_TW = 80.0   # TW ≥ 80% = tactical overbought (but still bullish)

# Sectors needed for convergence alerts
CONVERGENCE_THRESHOLD = 8  # ≥8 of 11 sectors
PANIC_THRESHOLD = 8        # ≥8 sectors distributing

# Tactical trap: gains at 5d but loses at 20d
TRAP_GAIN_THRESHOLD = 2.0
TRAP_LOSS_THRESHOLD = -3.0


# ── Data Classes ────────────────────────────────────────────

@dataclass(frozen=True)
class ScaleSnapshot:
    """State of a sector at one temporal scale."""
    scale: str                       # "structural" | "intermediate" | "tactical"
    raw_pct: float                   # S5 value 0-100
    stocks_above: float              # Real stock count above MA
    pct_of_spy: float                # % of total SPY breadth this sector contributes
    delta_5d: float                  # Δ stocks in 5 days
    delta_20d: float                 # Δ stocks in 20 days
    accel_5d: float                  # delta_5d now - delta_5d 5 days ago
    rank_by_delta_5d: int            # 1=most gained, 11=most lost
    is_extreme_low: bool             # raw_pct ≤ threshold
    is_extreme_high: bool            # raw_pct ≥ threshold


@dataclass(frozen=True)
class SectorRotationSnapshot:
    """Complete state of one sector across all 3 scales."""
    sector_etf: str
    n_constituents: int

    structural: ScaleSnapshot        # TH 200d — operational horizon 120d
    intermediate: ScaleSnapshot      # FI 50d  — operational horizon 60d
    tactical: ScaleSnapshot          # TW 20d  — operational horizon 20d

    flow_regime: str                 # ACCUMULATING | DISTRIBUTING | NEUTRAL (FI-based)
    is_tactical_trap: bool           # delta_5d > +2 AND delta_20d < -3 (FI)

    sv5_fi: Optional[float] = None   # SV5_FI value (0-100) for conviction


@dataclass(frozen=True)
class RotationSignal:
    """Output of the rotation intelligence engine."""
    sizing: float                    # Multiplicative sizing modifier (0.5 - 1.5)
    alerts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarketRotationSnapshot:
    """Global market state: convergence across all sectors."""
    sectors: dict[str, SectorRotationSnapshot]

    # Convergence counts (extreme low)
    n_sectors_extreme_low_th: int
    n_sectors_extreme_low_fi: int
    n_sectors_extreme_low_tw: int

    # Convergence counts (extreme high)
    n_sectors_extreme_high_th: int
    n_sectors_extreme_high_fi: int
    n_sectors_extreme_high_tw: int

    # Velocity
    total_velocity_zscore: float     # Z-score of total SPY breadth velocity

    # Panic
    n_sectors_distributing: int      # >8 = total panic


# ── Computation ─────────────────────────────────────────────

def _compute_scale_snapshot(
    history: list[float],
    scale: str,
    n_constituents: int,
    rank_by_delta_5d: int,
    extreme_low: float,
    extreme_high: float,
) -> Optional[ScaleSnapshot]:
    """Compute ScaleSnapshot from a history of S5 values (latest last)."""
    if len(history) < 21:
        return None

    latest = history[-1]
    stocks_now = (latest / 100.0) * n_constituents

    # Delta in STOCKS (not percentages)
    stocks_5d_ago = (history[-6] / 100.0) * n_constituents if len(history) >= 6 else stocks_now
    stocks_20d_ago = (history[-21] / 100.0) * n_constituents if len(history) >= 21 else stocks_now

    delta_5d = stocks_now - stocks_5d_ago
    delta_20d = stocks_now - stocks_20d_ago

    # Acceleration: Δ5d now vs Δ5d 5 days ago
    if len(history) >= 11:
        stocks_10d_ago = (history[-11] / 100.0) * n_constituents
        prev_delta_5d = stocks_5d_ago - stocks_10d_ago
        accel = delta_5d - prev_delta_5d
    else:
        accel = 0.0

    return ScaleSnapshot(
        scale=scale,
        raw_pct=latest,
        stocks_above=round(stocks_now, 1),
        pct_of_spy=round(stocks_now / TOTAL_SP500_CONSTITUENTS * 100, 2),
        delta_5d=round(delta_5d, 1),
        delta_20d=round(delta_20d, 1),
        accel_5d=round(accel, 1),
        rank_by_delta_5d=rank_by_delta_5d,
        is_extreme_low=latest <= extreme_low,
        is_extreme_high=latest >= extreme_high,
    )


def compute_market_rotation_snapshot(
    s5_histories: dict[str, dict[str, list[float]]],
    sv5_fi_values: Optional[dict[str, float]] = None,
) -> Optional[MarketRotationSnapshot]:
    """
    Build full market rotation snapshot from S5 histories.

    Args:
        s5_histories: {sector_etf: {scale: [values...latest_last]}}
                      scale in ("structural", "intermediate", "tactical")
        sv5_fi_values: {sector_etf: sv5_fi_value} (optional)

    Returns:
        MarketRotationSnapshot or None if insufficient data.
    """
    if s5_histories is None or (isinstance(s5_histories, (dict, list)) and len(s5_histories) == 0) or (hasattr(s5_histories, "empty") and s5_histories.empty):
        return None

    sv5 = sv5_fi_values or {}
    sectors: dict[str, SectorRotationSnapshot] = {}

    # First pass: compute deltas for ranking
    scale_deltas: dict[str, dict[str, float]] = {
        "structural": {}, "intermediate": {}, "tactical": {},
    }

    for etf, scale_histories in s5_histories.items():
        n = SECTOR_CONSTITUENT_COUNTS.get(etf, 50)
        for scale, history in scale_histories.items():
            if len(history) >= 6:
                latest = (history[-1] / 100.0) * n
                prev = (history[-6] / 100.0) * n
                scale_deltas[scale][etf] = latest - prev

    # Compute rankings per scale
    scale_rankings: dict[str, dict[str, int]] = {}
    for scale, deltas in scale_deltas.items():
        sorted_etfs = sorted(deltas.keys(), key=lambda e: deltas[e], reverse=True)
        scale_rankings[scale] = {etf: rank + 1 for rank, etf in enumerate(sorted_etfs)}

    # Second pass: build sector snapshots
    for etf, scale_histories in s5_histories.items():
        n = SECTOR_CONSTITUENT_COUNTS.get(etf, 50)

        scale_snaps: dict[str, Optional[ScaleSnapshot]] = {}
        for scale, (extreme_lo, extreme_hi) in [
            ("structural", (EXTREME_LOW_TH, EXTREME_HIGH_TH)),
            ("intermediate", (EXTREME_LOW_FI, EXTREME_HIGH_FI)),
            ("tactical", (EXTREME_LOW_TW, EXTREME_HIGH_TW)),
        ]:
            history = scale_histories.get(scale, [])
            rank = scale_rankings.get(scale, {}).get(etf, 6)
            scale_snaps[scale] = _compute_scale_snapshot(
                history, scale, n, rank, extreme_lo, extreme_hi,
            )

        # Need at least intermediate for flow regime
        fi_snap = scale_snaps.get("intermediate")
        if fi_snap is None:
            continue

        # Flow regime based on FI delta_5d
        if fi_snap.delta_5d > ACCUMULATING_THRESHOLD:
            flow_regime = "ACCUMULATING"
        elif fi_snap.delta_5d < DISTRIBUTING_THRESHOLD:
            flow_regime = "DISTRIBUTING"
        else:
            flow_regime = "NEUTRAL"

        # Tactical trap: gains at 5d but loses at 20d (FI scale)
        is_trap = (
            fi_snap.delta_5d > TRAP_GAIN_THRESHOLD
            and fi_snap.delta_20d < TRAP_LOSS_THRESHOLD
        )

        sectors[etf] = SectorRotationSnapshot(
            sector_etf=etf,
            n_constituents=n,
            structural=scale_snaps.get("structural", fi_snap),
            intermediate=fi_snap,
            tactical=scale_snaps.get("tactical", fi_snap),
            flow_regime=flow_regime,
            is_tactical_trap=is_trap,
            sv5_fi=sv5.get(etf),
        )

    if not sectors:
        return None

    # Convergence counts
    n_lo_th = sum(1 for s in sectors.values() if s.structural.is_extreme_low)
    n_lo_fi = sum(1 for s in sectors.values() if s.intermediate.is_extreme_low)
    n_lo_tw = sum(1 for s in sectors.values() if s.tactical.is_extreme_low)
    n_hi_th = sum(1 for s in sectors.values() if s.structural.is_extreme_high)
    n_hi_fi = sum(1 for s in sectors.values() if s.intermediate.is_extreme_high)
    n_hi_tw = sum(1 for s in sectors.values() if s.tactical.is_extreme_high)

    # Total velocity Z-score (approximate: use FI deltas)
    fi_deltas = [s.intermediate.delta_5d for s in sectors.values()]
    total_vel = sum(fi_deltas)
    if len(fi_deltas) > 2:
        import statistics
        mean_vel = statistics.mean(fi_deltas)
        std_vel = statistics.stdev(fi_deltas)
        vel_z = (total_vel - mean_vel * len(fi_deltas)) / (std_vel * len(fi_deltas) ** 0.5) if std_vel > 0 else 0.0
    else:
        vel_z = 0.0

    # Panic count
    n_dist = sum(1 for s in sectors.values() if s.flow_regime == "DISTRIBUTING")

    return MarketRotationSnapshot(
        sectors=sectors,
        n_sectors_extreme_low_th=n_lo_th,
        n_sectors_extreme_low_fi=n_lo_fi,
        n_sectors_extreme_low_tw=n_lo_tw,
        n_sectors_extreme_high_th=n_hi_th,
        n_sectors_extreme_high_fi=n_hi_fi,
        n_sectors_extreme_high_tw=n_hi_tw,
        total_velocity_zscore=round(vel_z, 2),
        n_sectors_distributing=n_dist,
    )


# ── Intelligence Rules ──────────────────────────────────────

def evaluate_rotation_intelligence(
    snap: MarketRotationSnapshot,
    sector_etf: str,
) -> RotationSignal:
    """
    Produce sizing modifier and alerts from rotation intelligence.

    6 empirically validated rules:
      1. Generational Opportunity (TH 200d convergence)
      2. Intermediate Capitulation (FI 50d convergence)
      3. Relative Ranking (Top 3 vs Bottom 3)
      4. Tactical Trap (Weinstein)
      5. Black Swan Contrarian
      6. Total Panic
    """
    sector = snap.sectors.get(sector_etf)
    if sector is None:
        return RotationSignal(sizing=1.0)

    sizing = 1.0
    alerts: list[str] = []

    # ── Rule 1: Generational Opportunity (TH 200d) ──
    # ≥8 sectors with S5_TH ≤ 20% = SPY fwd 120d: +14.43%, WR=81.1%
    if snap.n_sectors_extreme_low_th >= CONVERGENCE_THRESHOLD:
        sizing = 1.50
        alerts.append(
            "🏛️ OPORTUNIDAD GENERACIONAL: "
            f"≥{CONVERGENCE_THRESHOLD} sectores bajo MA200 — "
            "ACUMULACIÓN MASIVA (SPY +14.43% a 120d, WR=81.1%)"
        )
    elif snap.n_sectors_extreme_low_th >= 6:
        sizing = max(sizing, 1.30)
        alerts.append(
            "🏛️ CAPITULACIÓN ESTRUCTURAL: "
            f"{snap.n_sectors_extreme_low_th} sectores bajo MA200 — "
            "ACUMULAR PISO (SPY +12.38% a 120d, WR=77.4%)"
        )

    # ── Rule 2: Intermediate Capitulation (FI 50d) ──
    # ≥8 sectors with S5_FI ≤ 20% = SPY fwd 20d: +3.59%, WR=70.4%
    if snap.n_sectors_extreme_low_fi >= CONVERGENCE_THRESHOLD:
        sizing = max(sizing, 1.25)
        alerts.append(
            "📊 CAPITULACIÓN INTERMEDIA: "
            f"≥{CONVERGENCE_THRESHOLD} sectores bajo MA50 — "
            "SPY +3.59% a 20d (WR=70.4%, N=216)"
        )

    # ── Rule 3: Relative Ranking & Cap-Weight Protection ──
    rank = sector.intermediate.rank_by_delta_5d
    if rank <= 3:
        sizing *= 1.10  # Top 3 = boost
    elif rank >= 9:
        # Cap-Weight Protection: Do not penalize Mega-Cap Growth sectors (XLK/XLC/XLF) for temporary breadth drop
        from backend.modules.shared.domain.constants.sectors import SECTOR_CAP_WEIGHTS
        cap_w = SECTOR_CAP_WEIGHTS.get(sector_etf, 0.05)
        if cap_w < 0.08:
            sizing *= 0.85  # Small sector laggard = penalize
        else:
            sizing *= 0.95  # Mega-cap sector = minor adjustment only

    # ── Rule 4: Tactical Trap (Weinstein) ──
    if sector.is_tactical_trap:
        sizing *= 0.80
        alerts.append(
            f"⚠️ TACTICAL_TRAP: {sector_etf} — "
            f"gana {sector.intermediate.delta_5d:+.1f} acc/5d "
            f"pero pierde {sector.intermediate.delta_20d:+.1f} acc/20d"
        )

    # ── Rule 5: Black Swan Contrarian (WR=67.3%, N=202) ──
    if snap.total_velocity_zscore < -2.0:
        alerts.append(
            f"🦢 BLACK_SWAN: Velocidad breadth Z={snap.total_velocity_zscore:.1f} — "
            "señal contraria de acumulación (WR=67.3%)"
        )

    # ── Rule 6: Thesis Death / Stage 4 Decay (S5_TH < 40% for sector) ──
    # Only applies when market is NOT in a Generational Dip (where all sectors drop together)
    if sector.structural.raw_pct < 40.0 and snap.n_sectors_extreme_low_th < 6:
        sizing *= 0.75
        alerts.append(
            f"🥀 THESIS_DECAY: {sector_etf} S5_TH={sector.structural.raw_pct:.1f}% < 40% — "
            "sector fuera de moda (Stage 4 decay)"
        )

    # ── Rule 7: Total Panic Warning (Contextual Alert, No Cash Drag) ──
    if snap.n_sectors_distributing >= PANIC_THRESHOLD:
        alerts.append(
            f"🚨 TOTAL_PANIC_ALERT: {snap.n_sectors_distributing}/11 "
            "sectores distribuyendo — preparar compra de piso en Tollkeepers"
        )

    # ── NO-Rule: High extreme does NOT penalize ──
    # Data shows S5 high → market keeps rising (WR=77-81% at 120d)

    return RotationSignal(sizing=round(sizing, 2), alerts=alerts)

