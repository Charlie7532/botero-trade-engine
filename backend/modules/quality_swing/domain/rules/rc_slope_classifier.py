"""
RC Slope Classifier — Pure Domain Rule (López de Prado Volatility Standardization)
==================================================================================
Classifies T/C/W slopes into 6 levels each:
  +++ / ++ / + / - / -- / ---

Uses empirically calibrated 100% census asymmetric quantiles from Neon Vault (4.57M samples)
normalizing by local volatility ATR%:
  slope_norm = slope / max(atr_pct, 0.005)

Input: 3 floats (tide_slope, current_slope, wave_slope) and optional atr_pct (default 0.01)
Output: SlopeState dataclass with levels, tripleta, and semantics
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

THRESHOLDS_JSON = Path(__file__).parent / "rc_vol_normalized_thresholds.json"


def _load_vol_thresholds() -> dict:
    if THRESHOLDS_JSON.exists():
        try:
            with open(THRESHOLDS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo cargar rc_vol_normalized_thresholds.json ({e}). Usando fallbacks.")
    return {}


_VOL_TH = _load_vol_thresholds()

_SLOPE_TH = {
    "T": _VOL_TH.get("tide_slope_norm", {}),
    "C": _VOL_TH.get("current_slope_norm", {}),
    "W": _VOL_TH.get("wave_slope_norm", {}),
}


@dataclass(frozen=True)
class SlopeState:
    """Classified slope state for T/C/W channels."""
    tide_level: str      # T+++, T++, T+, T-, T--, T---
    current_level: str   # C+++, C++, C+, C-, C--, C---
    wave_level: str      # W+++, W++, W+, W-, W--, W---
    tripleta: str        # "T+/C-/W---"

    @property
    def tide_sign(self) -> int:
        return 1 if "+" in self.tide_level else -1

    @property
    def current_sign(self) -> int:
        return 1 if "+" in self.current_level else -1

    @property
    def wave_sign(self) -> int:
        return 1 if "+" in self.wave_level else -1

    @property
    def all_positive(self) -> bool:
        return self.tide_sign > 0 and self.current_sign > 0 and self.wave_sign > 0

    @property
    def all_negative(self) -> bool:
        return self.tide_sign < 0 and self.current_sign < 0 and self.wave_sign < 0

    @property
    def wave_diverges_tide(self) -> bool:
        """Wave opposes Tide — pullback or reversal."""
        return self.tide_sign != self.wave_sign


def _classify_norm_one(slope_norm: float, channel_key: str, channel_prefix: str) -> str:
    """Classify a volatility-normalized slope using 100% census quantiles."""
    q = _VOL_TH.get(channel_key, {})
    p97_5 = q.get("p97_5", 5.0)
    p90 = q.get("p90", 0.86)
    p75 = q.get("p75", 0.16)
    p25 = q.get("p25", -0.01)
    p10 = q.get("p10", -0.12)
    p2_5 = q.get("p2_5", -1.37)

    if slope_norm >= p97_5:
        return f"{channel_prefix}+++"
    elif slope_norm >= p90:
        return f"{channel_prefix}++"
    elif slope_norm >= p75:
        return f"{channel_prefix}+"
    elif slope_norm <= p2_5:
        return f"{channel_prefix}---"
    elif slope_norm <= p10:
        return f"{channel_prefix}--"
    elif slope_norm <= p25:
        return f"{channel_prefix}-"
    else:
        return f"{channel_prefix}~"


def _classify_one(value: float, channel: str, atr_pct: float = 0.01) -> str:
    """Backward compatible helper wrapper for single slope classification with auto-sanitization."""
    if atr_pct > 1.0:
        atr_pct = atr_pct / 100.0
    channel_map = {"T": ("tide_slope_norm", "T"), "C": ("current_slope_norm", "C"), "W": ("wave_slope_norm", "W")}
    key, prefix = channel_map.get(channel, ("wave_slope_norm", channel))
    atr_eff = max(atr_pct, 0.005)
    slope_norm = value / atr_eff
    return _classify_norm_one(slope_norm, key, prefix)


def classify_slopes(
    tide_slope: float,
    current_slope: float,
    wave_slope: float,
    atr_pct: float = 0.01,
) -> SlopeState:
    """Classify 3 slopes into a unified SlopeState using Volatility Normalization.

    Args:
        tide_slope: 240-bar regression slope
        current_slope: 60-bar regression slope
        wave_slope: cycle-adaptive regression slope
        atr_pct: 14-day ATR % of asset (default 0.01 = 1%)

    Returns:
        SlopeState with levels, tripleta, and derived properties
    """
    t = _classify_one(tide_slope, "T", atr_pct)
    c = _classify_one(current_slope, "C", atr_pct)
    w = _classify_one(wave_slope, "W", atr_pct)

    return SlopeState(
        tide_level=t,
        current_level=c,
        wave_level=w,
        tripleta=f"{t}/{c}/{w}",
    )
