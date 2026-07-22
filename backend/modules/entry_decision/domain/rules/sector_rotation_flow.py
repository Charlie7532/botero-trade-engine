"""
Sector Rotation Flow Rule — Inter-Sector Liquidity Flow Classifier
==================================================================
Calculates the dynamic flow of capital between Risk-On (cyclical) and
Risk-Off (defensive) sectors using multi-scale breadth.

This is a domain rule — pure Python, no infra dependencies.
"""
from dataclasses import dataclass
from typing import Dict, List
import numpy as np


@dataclass(frozen=True)
class SectorRotationFlow:
    """Represents the dynamic state of capital flow between sectors."""

    # Risk-On / Risk-Off Attribution
    cyclical_breadth_mean: float     # Average S5TW for (XLK, XLF, XLY, XLI)
    defensive_breadth_mean: float    # Average S5TW for (XLP, XLV, XLU, XLRE)
    risk_spread: float               # Cyclical - Defensive (pp)

    # Dispersion & Leadership
    sector_dispersion: float         # Standard deviation of S5TW across all 11 sectors
    hot_sectors_count: int           # Sectores with S5TW > 50
    cold_sectors_count: int          # Sectores with S5TW < 20
    is_divergent_leadership: bool    # True if hot <= 2 and cold >= 5 (Veto flag)

    # Rotation Regime
    rotation_regime: str             # "RISK_ON_EXPANSION" | "RISK_OFF_FLIGHT" | "DIVERGENT_TRAMP" | "NEUTRAL"
    sizing_modifier: float           # Multiplier for entry sizing (0.70 - 1.30)


def evaluate_rotation_flow(
    sec_tw: Dict[str, float]
) -> SectorRotationFlow:
    """
    Evaluates the inter-sector capital flow from the tactical breadth of 11 sectors.
    """
    cyclical_sectors = ["XLK", "XLF", "XLY", "XLI"]
    defensive_sectors = ["XLP", "XLV", "XLU", "XLRE"]
    all_sectors = ["XLK", "XLF", "XLY", "XLI", "XLP", "XLV", "XLU", "XLRE", "XLB", "XLE", "XLC"]

    # Calculate means
    cyc_vals = [sec_tw.get(s, 50.0) for s in cyclical_sectors]
    def_vals = [sec_tw.get(s, 50.0) for s in defensive_sectors]
    all_vals = [sec_tw.get(s, 50.0) for s in all_sectors if s in sec_tw]

    cyclical_breadth_mean = float(np.mean(cyc_vals)) if cyc_vals else 50.0
    defensive_breadth_mean = float(np.mean(def_vals)) if def_vals else 50.0
    risk_spread = cyclical_breadth_mean - defensive_breadth_mean

    # Calculate dispersion and counts
    sector_dispersion = float(np.std(all_vals)) if all_vals else 0.0
    hot_sectors_count = sum(1 for s in all_sectors if sec_tw.get(s, 50.0) > 50.0)
    cold_sectors_count = sum(1 for s in all_sectors if sec_tw.get(s, 50.0) < 20.0)

    # Divergent Leadership Veto (bear trap indicator)
    is_divergent_leadership = (hot_sectors_count <= 2 and cold_sectors_count >= 5)

    # Classify Regime
    if is_divergent_leadership:
        rotation_regime = "DIVERGENT_TRAMP"
        sizing_modifier = 0.70
    elif risk_spread > 5.0:
        rotation_regime = "RISK_ON_EXPANSION"
        sizing_modifier = 1.30
    elif risk_spread < -5.0:
        rotation_regime = "RISK_OFF_FLIGHT"
        sizing_modifier = 0.85
    else:
        rotation_regime = "NEUTRAL"
        sizing_modifier = 1.0

    return SectorRotationFlow(
        cyclical_breadth_mean=cyclical_breadth_mean,
        defensive_breadth_mean=defensive_breadth_mean,
        risk_spread=risk_spread,
        sector_dispersion=sector_dispersion,
        hot_sectors_count=hot_sectors_count,
        cold_sectors_count=cold_sectors_count,
        is_divergent_leadership=is_divergent_leadership,
        rotation_regime=rotation_regime,
        sizing_modifier=sizing_modifier
    )
