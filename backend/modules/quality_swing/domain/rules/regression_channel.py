"""
Backward compatibility — functions moved to shared/domain/rules/.

Canonical location: backend/modules/shared/domain/rules/regression_channel.py
This re-export ensures existing imports continue to work.
"""
from backend.modules.shared.domain.rules.regression_channel import (
    linreg_channel,
    calc_vwap,
    sigma_position,
)

__all__ = ["linreg_channel", "calc_vwap", "sigma_position"]
