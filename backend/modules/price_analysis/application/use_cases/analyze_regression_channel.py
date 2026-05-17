"""
REGRESSION CHANNEL INTELLIGENCE — The Position Framework
==========================================================
Multi-purpose institutional tool measuring POSITION within a statistical
channel. Orthogonal to RSIIntelligence (which measures MOMENTUM).

Five validated functions:
  1. ENTRY TIMING: σ ≤ -1.5 = buy zone (WR=82.2% THESIS, Sharpe=1.326)
  2. FEAR/GREED SCORING: PANIC P(↑)=47.6%, GREED P(↑)=40.4% (7.2pt spread)
  3. TRIM/EXIT DETECTION: σ ≥ +1.5 + wave_flip neg = movement exhausted
  4. EXHAUSTION DETECTION: complacency (all "perfect") → P(↑)=20.8% (worst)
  5. CONVICTION MODULATION: fear_level + slope_conjugation + wave_flip

Slope Conjugation — The Determinant Feature:
  Feature J11 (MTF_SlopeConjugation_5): ranked #11 global, spread -6.7%
  wave_slope - tide_slope < 0 → wave falling, tide rising → PULLBACK
  Entering during the dip yields WR=100% under THESIS geometry.

Empirical basis:
  - 25,190 samples | 30 tickers × 5 years | 1,230 RC entries
  - RC × THESIS: WR 82.2%, Sharpe 1.326, PF 3.583, Return +5,567%
  - CRISIS regime: WR 58.6%, Ret +3.28% (BEST in crisis — contrarian)
  - Top tickers: COST(81%), HON(78%), MA(77%), XOM(73%), JPM(73%)

Reference: The channel is a pure statistical construct. No momentum (RSI),
no pattern recognition (candlesticks), no volume states (Kalman).
Pure mean-reversion at institutional scale.

Usage:
    rc_intel = RegressionChannelIntelligence()
    result = rc_intel.analyze(ohlc_df)
    # result.zone → "DEEP_VALUE" / "SUPPORT" / "FAIR_VALUE" / "OVEREXTENDED"
    # result.action → "BUY" / "TRIM" / "HOLD"
    # result.fear_level → 0-5
    # result.conviction → -1.0 to +1.0
"""
import logging
import numpy as np
import pandas as pd

from backend.modules.price_analysis.domain.entities.price_models import RCIntelligenceResult
from backend.modules.quality_swing.domain.rules.regression_channel import (
    linreg_channel, calc_vwap, sigma_position as calc_sigma,
)
from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle

logger = logging.getLogger(__name__)


class RegressionChannelIntelligence:
    """Regression Channel Intelligence — Multi-Purpose Position Tool.

    Usage:
        rc_intel = RegressionChannelIntelligence()

        # Single-bar analysis (production, real-time)
        result = rc_intel.analyze(ohlc_df)

        # Use the output
        if result.action == "BUY" and result.conviction > 0.5:
            # Entry with high conviction
            ...
        elif result.action == "TRIM":
            # Reduce position by result.trim_pct
            ...
    """

    # ── Configuration ────────────────────────────────────────
    LONG_WINDOW = 200       # Tide regression (fixed, institutional)
    VWAP_WINDOW = 20        # VWAP lookback (institutional fair price)

    # ── σ Zone Thresholds (from forensic audit) ──────────────
    DEEP_VALUE_SIGMA = -2.0      # 2.5th percentile → rare opportunity
    SUPPORT_SIGMA = -1.5         # 16th percentile → entry zone
    RESISTANCE_SIGMA = 1.5       # 84th percentile → overextended
    EXTREME_GREED_SIGMA = 2.0    # 97.5th percentile → trim heavily

    # ── Regime Thresholds ────────────────────────────────────
    BULL_SLOPE_MIN = 0.01        # Tide slope for BULL classification
    BEAR_SLOPE_MAX = -0.01       # Tide slope for BEAR classification
    SHALLOW_BEAR_LIMIT = -0.03   # Below this = structural collapse (UNH rule)

    def analyze(
        self,
        ohlc: pd.DataFrame,
        idx: int | None = None,
    ) -> RCIntelligenceResult:
        """Full regression channel analysis at a single point in time.

        Args:
            ohlc: DataFrame with 'open', 'high', 'low', 'close', 'volume'.
            idx: Bar index to analyze (default: last bar).

        Returns:
            RCIntelligenceResult with zone, action, fear_level, conviction.
        """
        result = RCIntelligenceResult()

        if idx is None:
            idx = len(ohlc) - 1

        if idx < self.LONG_WINDOW + 5:
            result.diagnosis = f"Insufficient data ({idx} bars, need {self.LONG_WINDOW + 5})"
            return result

        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)
        price_window = close[:idx + 1]
        current_price = close[idx]

        # ══════════════════════════════════════════════════════
        # LAYER 1: TIDE — Long regression (200 bars)
        # ══════════════════════════════════════════════════════
        reg_value, tide_slope, residual_std = linreg_channel(price_window, self.LONG_WINDOW)
        sig_pos = calc_sigma(current_price, reg_value, residual_std)

        result.reg_value = round(reg_value, 2)
        result.residual_std = round(residual_std, 4)
        result.tide_slope = round(tide_slope, 4)
        result.sigma_position = round(sig_pos, 2)

        # ══════════════════════════════════════════════════════
        # LAYER 2: WAVE — Short regression (cycle-adaptive)
        # ══════════════════════════════════════════════════════
        dominant_cycle = detect_dominant_cycle(close)
        short_window = max(10, min(dominant_cycle, 60))
        _, wave_slope, _ = linreg_channel(price_window, short_window)
        result.wave_slope = round(wave_slope, 4)

        # Slope conjugation: the angle between the two lines
        result.slope_conjugation = round(wave_slope - tide_slope, 4)

        # ══════════════════════════════════════════════════════
        # LAYER 3: VWAP — Institutional fair price
        # ══════════════════════════════════════════════════════
        vwap_val = calc_vwap(
            close[:idx + 1], high[:idx + 1], low[:idx + 1], volume[:idx + 1],
            self.VWAP_WINDOW,
        )
        result.vwap = round(vwap_val, 2)
        result.below_vwap = current_price < vwap_val

        # ══════════════════════════════════════════════════════
        # LAYER 4: FEAR/GREED — Per-ticker contrarian bias
        # ══════════════════════════════════════════════════════
        bias = compute_ticker_fear_level(ohlc, idx, self.LONG_WINDOW, short_window)
        if bias is not None:
            result.fear_level = bias.fear_level
            result.fear_label = bias.fear_label
            result.tide_accel = round(bias.tide_accel, 6)
            result.wave_flip = bias.wave_flip
            result.wave_flip_direction = bias.wave_flip_direction

        # ══════════════════════════════════════════════════════
        # LAYER 5: REGIME — From tide slope
        # ══════════════════════════════════════════════════════
        if tide_slope > self.BULL_SLOPE_MIN:
            result.regime = "BULL"
        elif tide_slope < self.BEAR_SLOPE_MAX:
            result.regime = "BEAR"
        else:
            result.regime = "FLAT"

        # ══════════════════════════════════════════════════════
        # LAYER 6: VOLUME UP/DOWN — Distribution detection
        # ══════════════════════════════════════════════════════
        result.vol_up_down_ratio = round(
            self._compute_vol_ratio(close, volume, idx), 2
        )

        # ══════════════════════════════════════════════════════
        # ZONE CLASSIFICATION
        # ══════════════════════════════════════════════════════
        result.zone = self._classify_zone(sig_pos, result.fear_level)

        # ══════════════════════════════════════════════════════
        # ACTION DETERMINATION
        # ══════════════════════════════════════════════════════
        result.action = self._determine_action(result)

        # ══════════════════════════════════════════════════════
        # COMPOSITE CONVICTION (-1.0 to +1.0)
        # ══════════════════════════════════════════════════════
        result.conviction = self._compute_conviction(result)

        # ══════════════════════════════════════════════════════
        # DIAGNOSIS
        # ══════════════════════════════════════════════════════
        result.diagnosis = self._build_diagnosis(result, current_price)

        return result

    # ═══════════════════════════════════════════════════════════
    # INTERNAL METHODS
    # ═══════════════════════════════════════════════════════════

    def _classify_zone(self, sigma: float, fear_level: int) -> str:
        """Classify position into actionable zone.

        Zones combine statistical position (σ) with sentiment (fear_level)
        for a more nuanced classification than σ alone.

        Statistical basis:
          68% of prices within ±1σ → normal fluctuation
          95% within ±2σ → entry at -2σ = 2.5th percentile
        """
        if sigma <= self.DEEP_VALUE_SIGMA:
            return "DEEP_VALUE"         # Rare statistical extreme → max opportunity
        elif sigma <= self.SUPPORT_SIGMA:
            return "SUPPORT"            # Entry zone → opportunity
        elif sigma >= self.EXTREME_GREED_SIGMA and fear_level <= 1:
            return "EXTREME_GREED"      # Overextended + complacent → max trim
        elif sigma >= self.RESISTANCE_SIGMA:
            return "OVEREXTENDED"       # Overextended → consider trim
        elif -0.5 <= sigma <= 0.5:
            return "FAIR_VALUE"         # Near regression line → hold
        elif sigma > 0.5:
            return "RESISTANCE"         # Above fair value → reducing edge
        else:
            return "DISCOUNT"           # Below fair value, not yet support

    def _determine_action(self, r: RCIntelligenceResult) -> str:
        """Determine actionable recommendation.

        BUY conditions (validated forensic):
          BULL + σ ≤ -1.5 + below VWAP → WR=82.2%, Sharpe=1.326
          FLAT + σ ≤ -2.0 → WR=91.7% (mean reversion)
          BEAR + shallow + σ ≤ -2.0 + short turning → contrarian

        TRIM conditions:
          σ ≥ +2.0 AND fear=0 (GREED) → P(↑)=40.4%
          σ ≥ +1.5 AND fear≤1
          Wave flip negative + σ ≥ +1.0 + fear≤1
        """
        # ── BUY Logic ──
        if r.regime == "BULL" and r.sigma_position <= self.SUPPORT_SIGMA and r.below_vwap:
            return "BUY"

        if r.regime == "FLAT" and r.sigma_position <= self.DEEP_VALUE_SIGMA:
            return "BUY"

        if (r.regime == "BEAR" and r.tide_slope > self.SHALLOW_BEAR_LIMIT
                and r.sigma_position <= self.DEEP_VALUE_SIGMA
                and r.wave_slope > 0):
            return "BUY"

        # ── TRIM Logic ──
        if r.sigma_position >= self.EXTREME_GREED_SIGMA and r.fear_level == 0:
            return "TRIM"

        if r.sigma_position >= self.RESISTANCE_SIGMA and r.fear_level <= 1:
            return "TRIM"

        if (r.sigma_position >= 1.0 and r.wave_flip
                and r.wave_flip_direction == -1 and r.fear_level <= 1):
            return "TRIM"

        return "HOLD"

    def _compute_conviction(self, r: RCIntelligenceResult) -> float:
        """Composite conviction score: -1.0 (bearish) to +1.0 (bullish).

        Combines:
          - σ position (deeper = more bullish for BUY, more bearish for TRIM)
          - Fear level (PANIC = bullish contrarian, GREED = bearish)
          - Slope conjugation (negative = pullback opportunity)
          - Volume ratio (accumulation vs distribution)
          - VWAP position (below = institutional discount)
        """
        score = 0.0

        # σ position contribution (±0.30 max)
        if r.sigma_position <= -2.0:
            score += 0.30       # Deep value
        elif r.sigma_position <= -1.5:
            score += 0.20       # Support zone
        elif r.sigma_position >= 2.0:
            score -= 0.30       # Extreme overextension
        elif r.sigma_position >= 1.5:
            score -= 0.20       # Overextended

        # Fear level contribution (±0.25 max) — contrarian
        fear_scores = {5: +0.25, 4: +0.20, 3: +0.10, 2: 0.0, 1: -0.10, 0: -0.20}
        score += fear_scores.get(r.fear_level, 0.0)

        # Slope conjugation (±0.20 max)
        if r.slope_conjugation < -0.05:
            score += 0.20       # Deep pullback → opportunity
        elif r.slope_conjugation < -0.02:
            score += 0.10       # Mild pullback
        elif r.slope_conjugation > 0.10:
            score -= 0.15       # Parabolic → exhaustion risk

        # Volume ratio (±0.10 max)
        if r.vol_up_down_ratio < 0.8:
            score -= 0.10       # Stealth distribution
        elif r.vol_up_down_ratio > 1.5:
            score += 0.10       # Strong accumulation

        # VWAP position (±0.10 max)
        if r.below_vwap:
            score += 0.10       # Institutional discount
        elif r.sigma_position > 1.0:
            score -= 0.05       # Above VWAP + extended

        # Wave flip bonus (±0.10 max)
        if r.wave_flip:
            if r.wave_flip_direction == 1:
                score += 0.10   # Knife stopped falling → max signal
            elif r.wave_flip_direction == -1:
                score -= 0.10   # Knife started falling → caution

        return round(max(-1.0, min(1.0, score)), 2)

    @staticmethod
    def _compute_vol_ratio(close: np.ndarray, volume: np.ndarray, idx: int) -> float:
        """Compute volume UP/DOWN ratio over last 5 bars."""
        if idx < 5:
            return 1.0

        up_vol = 0.0
        down_vol = 0.0
        up_n = 0
        down_n = 0

        for j in range(max(1, idx - 4), idx + 1):
            if close[j] > close[j - 1]:
                up_vol += volume[j]
                up_n += 1
            else:
                down_vol += volume[j]
                down_n += 1

        avg_up = up_vol / max(up_n, 1)
        avg_down = down_vol / max(down_n, 1)
        return avg_up / avg_down if avg_down > 0 else 2.0

    def _build_diagnosis(self, r: RCIntelligenceResult, price: float) -> str:
        """Human-readable diagnosis."""
        parts = [
            f"σ={r.sigma_position:+.1f}",
            f"Regime={r.regime}",
            f"Zone={r.zone}",
            f"Fear={r.fear_label}({r.fear_level})",
        ]

        # Slopes
        parts.append(f"Tide={r.tide_slope:+.3f}")
        parts.append(f"Wave={r.wave_slope:+.3f}")
        parts.append(f"Conj={r.slope_conjugation:+.3f}")

        # Key signals
        if r.wave_flip:
            flip_dir = "↑" if r.wave_flip_direction == 1 else "↓"
            parts.append(f"WaveFlip={flip_dir}")

        if r.below_vwap:
            parts.append(f"<VWAP({r.vwap:.0f})")

        if r.vol_up_down_ratio < 1.0:
            parts.append(f"VolRatio={r.vol_up_down_ratio:.1f}⚠️")

        parts.append(f"→ {r.action}")
        parts.append(f"Conv={r.conviction:+.2f}")

        return " | ".join(parts)
