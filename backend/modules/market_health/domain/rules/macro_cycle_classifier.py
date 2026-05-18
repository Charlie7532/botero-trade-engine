"""
Macro Cycle Classifier — Domain Rule

Classifies economic cycle phase from yield curve and FRED macro data.
Distinguishes between:
  - cycle_detection.py (price frequency, Simons) — NOT this
  - Pring cycle (bonds→stocks→commodities rotation) — NOT this
  - Dalio macro cycle (GDP/yields/fed stance) — THIS

Evidence Status:
  Yield inversion → recession: VALIDATED (7/8 since 1970).
  FRED macro_regime thresholds: HYPOTHESIS.
"""

# Yield curve signals
NORMAL = "NORMAL"
FLAT = "FLAT"
INVERTED = "INVERTED"
STEEPENING = "STEEPENING"

# HYPOTHESIS thresholds
FLAT_THRESHOLD = 0.25    # spread < 25bp = essentially flat
STEEP_THRESHOLD = 0.50   # spread rising > 50bp from negative = steepening


def classify_yield_curve(
    yields_10y: list[float],
    yields_3m: list[float],
    lookback: int = 20,
) -> str:
    """Classify yield curve signal from 10Y and 3M yields.

    Args:
        yields_10y: 10-year yield history (most recent last).
        yields_3m: 3-month yield history (most recent last).
        lookback: Window for steepening detection.

    Returns:
        Yield curve signal: NORMAL/FLAT/INVERTED/STEEPENING.
    """
    if not yields_10y or not yields_3m:
        return NORMAL

    spread_now = yields_10y[-1] - yields_3m[-1]

    # Check for steepening: was inverted, now rising
    if len(yields_10y) >= lookback and len(yields_3m) >= lookback:
        spread_past = yields_10y[-lookback] - yields_3m[-lookback]
        if spread_past < 0 and spread_now > spread_past + STEEP_THRESHOLD:
            return STEEPENING

    if spread_now < 0:
        return INVERTED
    elif spread_now < FLAT_THRESHOLD:
        return FLAT
    else:
        return NORMAL


def extract_fred_regime(fred_snapshot: dict | None) -> tuple[str, str]:
    """Extract macro_regime and fed_stance from FRED MCP snapshot.

    The vault_anomaly_scan.py confirmed that macro/fred_real snapshots
    already contain computed 'macro_regime' and 'fed_stance' fields.

    Returns:
        (macro_regime, fed_stance) tuple. Defaults to ("UNKNOWN", "UNKNOWN").
    """
    if not fred_snapshot or not isinstance(fred_snapshot, dict):
        return "UNKNOWN", "UNKNOWN"

    macro_regime = fred_snapshot.get("macro_regime", "UNKNOWN")
    fed_stance = fred_snapshot.get("fed_stance", "UNKNOWN")

    return str(macro_regime), str(fed_stance)
