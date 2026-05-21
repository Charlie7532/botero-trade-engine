"""
ChannelSnapshot — Unified Market Position Snapshot
=====================================================
Value object containing ALL regression channel + VWAP derivatives
computed at a single point in time. Produced by compute_channel_snapshot(),
consumed by RCIntelligence, RSIIntelligence, Oracle, SwingGate, and
the MetaLabeler pipeline.

Three regression lines (TIDE/CURRENT/WAVE) + three VWAPs with matching
windows. All derivatives (sigmas, slopes, accelerations, conjugations,
spreads) computed in one pass with zero duplication.

Pipeline position: PIEZA 1 of 4
  1. ChannelSnapshot (this)
  2. PreTrainer/Digestor → IndicatorSnapshot
  3. MetaLabeler/Trainer → TrainedSignalProfile
  4. Production Gate → GO/NO-GO + sizing
"""
from dataclasses import dataclass, asdict


@dataclass
class ChannelSnapshot:
    """Complete market position snapshot from triple regression + triple VWAP.

    All fields are computed by compute_channel_snapshot() in one pass.
    Consumers should never recompute these values.

    Forensic v13 grades (2026-05-21, 17 tickers, 6,775 samples):
      sigma_tide(240):        ★★ STRONG  (RSI r=-0.119, RC r=-0.100)
      vwap_sigma_wave:        ★★ STRONG  (RSI r=-0.103, 82% tickers, ✅ stable)
      tide_accel:             ★★ STRONG  (RC r=-0.103)
      spread_tide_current:    ★  MODERATE (RSI+RC, ✅ temporally stable)
      vwap_sigma_current:     ★  MODERATE (RSI r=-0.099, 88% tickers, ✅ stable)
      conj_wave_tide:         ★  MODERATE (RSI r=-0.070, 82% tickers)
    """

    # ── Windows Used ─────────────────────────────────────────
    tide_window: int = 240          # ~1 year, macro institutional trend
    current_window: int = 60        # ~1 quarter, medium-term trend
    wave_window: int = 30           # cycle-adaptive (8-50 bars), surfs the wave

    # ── 3 Regression Sigmas ──────────────────────────────────
    # Price position in σ units within each regression channel.
    # Negative = below channel center (cheap). Positive = above (expensive).
    sigma_tide: float = 0.0         # vs 240-bar regression  ★★ VALIDATED
    sigma_current: float = 0.0      # vs 60-bar regression
    sigma_wave: float = 0.0         # vs cycle-adaptive regression

    # ── 3 Regression Values (for downstream if needed) ───────
    reg_value_tide: float = 0.0     # Regression line value at current bar
    reg_value_current: float = 0.0
    reg_value_wave: float = 0.0

    # ── 3 Residual Stds (channel width) ──────────────────────
    residual_std_tide: float = 1.0
    residual_std_current: float = 1.0
    residual_std_wave: float = 1.0

    # ── 3 VWAP Sigmas ───────────────────────────────────────
    # Price distance from VWAP in VWAP-std units.
    # Captures institutional flow (volume-weighted) vs statistical position.
    # Pattern inverted vs regression: short VWAP is STRONGEST (not long).
    vwap_sigma_tide: float = 0.0    # vs 240-bar VWAP  ★ MODERATE
    vwap_sigma_current: float = 0.0 # vs 60-bar VWAP   ★ MODERATE (88% tickers)
    vwap_sigma_wave: float = 0.0    # vs cycle VWAP    ★★ STRONG (RSI only)

    # ── 3 VWAP Values ───────────────────────────────────────
    vwap_tide: float = 0.0
    vwap_current: float = 0.0
    vwap_wave: float = 0.0

    # ── 3 Slopes (normalized % of mean price per bar) ────────
    tide_slope: float = 0.0         # Macro direction
    current_slope: float = 0.0      # Medium-term direction
    wave_slope: float = 0.0         # Short-term direction

    # ── 3 Accelerations (slope change vs previous bar) ───────
    tide_accel: float = 0.0         # ★★ STRONG (RC r=-0.103)
    current_accel: float = 0.0      # ★ MODERATE (RSI)
    wave_accel: float = 0.0

    # ── 3 Conjugations (slope differences between pairs) ─────
    # Measures the angle between two regression lines.
    # Negative = wave falling while longer rising → PULLBACK (entry opportunity)
    # Very positive = parabolic → EXHAUSTION (trim risk)
    conj_wave_current: float = 0.0  # wave_slope - current_slope
    conj_wave_tide: float = 0.0     # wave_slope - tide_slope  ★ MODERATE (82%)
    conj_current_tide: float = 0.0  # current_slope - tide_slope  ★ MODERATE (RC)

    # ── 3 Sigma Spreads (sigma differences between lines) ────
    # Measures divergence between timeframes.
    # Large spread_tide_current → trimestral deviating from macro.
    spread_tide_current: float = 0.0  # σ_tide - σ_current  ★ MODERATE (✅ stable)
    spread_tide_wave: float = 0.0     # σ_tide - σ_wave
    spread_current_wave: float = 0.0  # σ_current - σ_wave

    # ── 3 VWAP Spreads ──────────────────────────────────────
    # Percentage difference between VWAP levels.
    vwap_spread_tide_current: float = 0.0
    vwap_spread_tide_wave: float = 0.0
    vwap_spread_current_wave: float = 0.0

    # ── Derived from slopes (0 recalculation) ────────────────
    fear_level: int = 2             # 0=GREED → 5=PANIC (contrarian)
    fear_label: str = "NEUTRAL"     # Human-readable
    wave_flip: bool = False         # Did wave change sign vs previous bar?
    wave_flip_direction: int = 0    # +1 knife stopped falling, -1 knife started

    # ── Regime (from tide_slope thresholds) ──────────────────
    regime: str = "FLAT"            # BULL / BEAR / FLAT

    # ── Volume Confirmation ──────────────────────────────────
    vol_up_down_ratio: float = 1.0  # Volume on UP days / DOWN days (5 bars)
                                    # > 1.0 = accumulation, < 1.0 = distribution

    # ── Composite Flags ──────────────────────────────────────
    below_all_vwaps: bool = False   # Price below all 3 VWAPs = institutional discount
    above_all_vwaps: bool = False   # Price above all 3 VWAPs = anti-signal (WR=38.6%)

    def to_dict(self) -> dict:
        """Serialize to dict for DB storage or JSON."""
        return asdict(self)
