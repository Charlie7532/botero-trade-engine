"""
Breadth Cascade Classifier — Domain Rule

Classifies market breadth state from S5TW/S5FI/S5TH indicators.
Ported from engineer_features.py L1132-1141.

Evidence Status: HYPOTHESIS — thresholds need DSR calibration.
"""
import pandas as pd
import numpy as np


# CascadeState integer encoding
HEALTH = 0
PULLBACK = 1
CORRECTION = 2
BEAR = 3

LABELS = {HEALTH: "HEALTH", PULLBACK: "PULLBACK", CORRECTION: "CORRECTION", BEAR: "BEAR"}


def classify_cascade(
    s5tw: float,
    s5fi: float,
    s5th: float,
) -> int:
    """Classify breadth cascade state from current readings.

    Args:
        s5tw: % of S&P 500 above 20-DMA (tactical, 0-100)
        s5fi: % of S&P 500 above 50-DMA (intermediate, 0-100)
        s5th: % of S&P 500 above 200-DMA (structural, 0-100)

    Returns:
        CascadeState int: 0=HEALTH, 1=PULLBACK, 2=CORRECTION, 3=BEAR
    """
    # HEALTH: all timeframes healthy
    if s5tw >= 40 and s5fi >= 40 and s5th >= 40:
        return HEALTH

    # PULLBACK: tactical washed, structure intact
    if s5tw < 40 and s5fi >= 50 and s5th >= 60:
        return PULLBACK

    # CORRECTION: tactical + intermediate failing, structure holds
    if s5tw < 30 and s5fi < 40 and s5th >= 50:
        return CORRECTION

    # BEAR: default (all failing or non-standard combination)
    return BEAR


def compute_cascade_spread(s5th: float, s5tw: float) -> float:
    """Gap between structural and tactical breadth.

    Positive = healthy pullback (structure intact, tactical washed).
    Negative = bear rally trap (tactical bounced, structure broken).
    """
    return (s5th - s5tw) / 100.0


def detect_narrow_market(
    spy_pct_change_20d: float,
    s5fi_change_20d: float,
) -> bool:
    """SPY rising but breadth falling = fragile rally.

    Args:
        spy_pct_change_20d: SPY 20-day return (e.g. 0.03 = +3%)
        s5fi_change_20d: S5FI 20-day absolute change (e.g. -5.0)
    """
    return spy_pct_change_20d > 0.02 and s5fi_change_20d < -5.0


def compute_breadth_participation(s5tw: float, s5fi: float, s5th: float) -> float:
    """Mean of all 3 breadth layers, normalized 0-1."""
    return (s5tw + s5fi + s5th) / 300.0
