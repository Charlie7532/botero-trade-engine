"""
Credit Regime Classifier — Domain Rule

Classifies credit health from HYG/TLT ratio z-score.
A narrowing spread (HYG outperforming TLT) = risk appetite.
A widening spread (TLT outperforming HYG) = flight to safety.

Evidence Status: HYPOTHESIS — thresholds need DSR calibration.
"""
import numpy as np

STRESS = "STRESS"
NORMAL = "NORMAL"
RISK_ON = "RISK_ON"

# HYPOTHESIS thresholds
Z_STRESS = -1.5     # HYG/TLT ratio well below mean = credit stress
Z_RISK_ON = 1.0     # HYG/TLT ratio well above mean = risk appetite


def classify_credit(
    hyg_prices: list[float],
    tlt_prices: list[float],
    lookback: int = 60,
) -> tuple[str, float]:
    """Classify credit regime from HYG and TLT price histories.

    Args:
        hyg_prices: HYG close prices (most recent last), min 20 values.
        tlt_prices: TLT close prices (most recent last), same length.
        lookback: Rolling window for z-score (default 60 days).

    Returns:
        (credit_regime, z_score) tuple.
    """
    if len(hyg_prices) < 20 or len(tlt_prices) < 20:
        return NORMAL, 0.0

    min_len = min(len(hyg_prices), len(tlt_prices))
    hyg = np.array(hyg_prices[-min_len:], dtype=float)
    tlt = np.array(tlt_prices[-min_len:], dtype=float)

    # HYG/TLT ratio — rising = risk appetite, falling = credit stress
    tlt_safe = np.where(tlt > 0, tlt, np.nan)
    ratio = hyg / tlt_safe

    # Remove NaN
    valid = ratio[~np.isnan(ratio)]
    if len(valid) < 20:
        return NORMAL, 0.0

    # Rolling z-score (use full available window, capped at lookback)
    window = min(lookback, len(valid))
    recent = valid[-window:]
    mean = np.mean(recent)
    std = np.std(recent)
    if std < 1e-9:
        return NORMAL, 0.0

    z = float((valid[-1] - mean) / std)

    if z < Z_STRESS:
        return STRESS, z
    elif z > Z_RISK_ON:
        return RISK_ON, z
    else:
        return NORMAL, z
