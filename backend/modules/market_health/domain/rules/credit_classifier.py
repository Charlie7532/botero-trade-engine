"""
Credit Regime Classifier — Domain Rule

Classifies credit health from HYG/LQD ratio z-score.
A narrowing spread (HYG outperforming LQD) = risk appetite.
A widening spread (LQD outperforming HYG) = flight to quality.

Evidence Status: HYPOTHESIS — thresholds need DSR calibration.
"""
import numpy as np

STRESS = "STRESS"
NORMAL = "NORMAL"
RISK_ON = "RISK_ON"

# HYPOTHESIS thresholds
Z_STRESS = -1.5     # HYG/LQD ratio well below mean = credit stress
Z_RISK_ON = 1.0     # HYG/LQD ratio well above mean = risk appetite


def classify_credit(
    hyg_prices: list[float],
    lqd_prices: list[float],
    lookback: int = 60,
) -> tuple[str, float]:
    """Classify credit regime from HYG and LQD price histories.

    Args:
        hyg_prices: HYG close prices (most recent last), min 20 values.
        lqd_prices: LQD close prices (most recent last), same length.
        lookback: Rolling window for z-score (default 60 days).

    Returns:
        (credit_regime, z_score) tuple.
    """
    if len(hyg_prices) < 20 or len(lqd_prices) < 20:
        return NORMAL, 0.0

    min_len = min(len(hyg_prices), len(lqd_prices))
    hyg = np.array(hyg_prices[-min_len:], dtype=float)
    lqd = np.array(lqd_prices[-min_len:], dtype=float)

    # HYG/LQD ratio — rising = risk appetite, falling = credit stress
    lqd_safe = np.where(lqd > 0, lqd, np.nan)
    ratio = hyg / lqd_safe

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
