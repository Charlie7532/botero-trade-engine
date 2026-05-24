"""
TickerProfile — Per-Ticker Calibrated Parameters
====================================================
Value object containing all per-ticker calibrated thresholds,
percentile tables, and ML model outputs. Trained by
train_ticker_profiles.py, consumed by SwingGate, RSIIntelligence,
and the Unified Pre-Trainer.

Replaces 18 hardcoded constants with empirically calibrated
per-ticker parameters:
  - TSI/ADI percentile tables (×3 regressions each)
  - RSI regime bands (Cardwell per-ticker)
  - Dominant cycle period
  - ML entry/exit probability thresholds

Pipeline position: PIEZA 0 (calibration layer)
  0. TickerProfile (this) — trained offline
  1. ChannelSnapshot → features
  2. PreTrainer → model + thresholds
  3. Production Gate → GO/NO-GO + sizing

No external dependencies beyond numpy. Pure domain entity.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np


@dataclass
class TickerProfile:
    """Per-ticker calibrated parameters. Trained, not hardcoded.

    Audit origin (2026-05-23, 93,776 observations):
      - AAPL std(tide_slope) = 0.195 → 1.89× global
      - PEP  std(tide_slope) = 0.052 → 0.50× global
      - Same slope means radically different things per ticker.

    TSI/ADI percentile tables normalize each ticker to its own
    historical distribution, making cross-ticker comparisons valid.
    """

    ticker: str = ""

    # ── TSI: Trend Strength Index (percentile tables) ────────
    # Shape: (101,) → slope threshold at each percentile 0..100
    # Computed from ALL historical channel_snapshots for this ticker.
    tsi_tide_percentiles: list = field(default_factory=list)
    tsi_current_percentiles: list = field(default_factory=list)
    tsi_wave_percentiles: list = field(default_factory=list)

    # ── ADI: Accumulation/Distribution Index (percentile tables)
    # Shape: (101,) → tension threshold at each percentile 0..100
    adi_tide_percentiles: list = field(default_factory=list)
    adi_current_percentiles: list = field(default_factory=list)
    adi_wave_percentiles: list = field(default_factory=list)

    # ── RSI regime bands (per-ticker Cardwell) ───────────────
    # Calibrated from RSI distribution filtered by regime.
    rsi_bull_floor: float = 40.0    # P5 of RSI when regime=BULL
    rsi_bull_ceil: float = 80.0     # P95 of RSI when regime=BULL
    rsi_bear_floor: float = 20.0    # P5 of RSI when regime=BEAR
    rsi_bear_ceil: float = 60.0     # P95 of RSI when regime=BEAR

    # ── Dominant cycle (for RSI adaptive period) ─────────────
    dominant_cycle: int = 28        # Bars (from autocorrelation)

    # ── ML model thresholds (set by unified pre-trainer) ─────
    entry_p_threshold: float = 0.65   # P(win) >= this → entry signal
    exit_p_threshold: float = 0.65    # P(win) >= this → trim signal

    # ── Feature importance (for interpretability) ────────────
    top_entry_features: list = field(default_factory=list)
    top_exit_features: list = field(default_factory=list)

    # ── Metadata ─────────────────────────────────────────────
    n_observations: int = 0           # How many snapshots were used
    version: int = 1                  # Schema version
    trained_at: str = ""              # ISO timestamp

    def to_dict(self) -> dict:
        """Serialize to dict for JSON/JSONB storage."""
        d = asdict(self)
        # numpy arrays → lists for JSON serialization
        for key in d:
            if isinstance(d[key], np.ndarray):
                d[key] = d[key].tolist()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TickerProfile":
        """Deserialize from dict (loaded from JSONB)."""
        return cls(**{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__
        })

    def get_tsi(self, regression: str, slope: float) -> int:
        """Compute TSI for a given regression and slope value.

        Args:
            regression: 'tide', 'current', or 'wave'
            slope: Current slope value

        Returns:
            TSI 0-100 (percentile rank in this ticker's history)
        """
        pcts = getattr(self, f"tsi_{regression}_percentiles", [])
        if not pcts:
            return 50  # No calibration → neutral
        arr = np.asarray(pcts)
        return int(np.clip(np.searchsorted(arr, slope, side="right"), 0, 100))

    def get_adi(self, regression: str, tension: float) -> int:
        """Compute ADI for a given regression and tension value.

        Args:
            regression: 'tide', 'current', or 'wave'
            tension: Current tension value (sigma_reg - sigma_vwap)

        Returns:
            ADI 0-100 (0=Strong Accumulation, 100=Strong Distribution)
        """
        pcts = getattr(self, f"adi_{regression}_percentiles", [])
        if not pcts:
            return 50
        arr = np.asarray(pcts)
        return int(np.clip(np.searchsorted(arr, tension, side="right"), 0, 100))
