"""
RSI INTELLIGENCE — Cardwell/Brown Regime-Aware RSI Interpretation
==================================================================
Implements:
  1. RSI Range Rules (Constance Brown / Andrew Cardwell):
     - Bull regime: RSI oscillates 40-80, pullbacks to 40-50 are entries
     - Bear regime: RSI oscillates 20-60, rallies to 50-60 are fades
  2. Positive/Negative Reversals (Cardwell):
     - Positive Reversal: Price higher-low + RSI lower-low → BUY in uptrend
     - Negative Reversal: Price lower-high + RSI higher-high → SELL in downtrend
  3. Classic Divergence Detection:
     - Bearish div: Price higher-high + RSI lower-high → trend weakening
     - Bullish div: Price lower-low + RSI higher-low → trend strengthening
  4. RSI Slope comparison vs Price Slope → momentum alignment

Reference: Andrew Cardwell — "RSI Complete Course" / Constance Brown — 
           "Technical Analysis for the Trading Professional"
"""
import numpy as np
import logging
from modules.price_analysis.models import RSIIntelligenceResult
from modules.price_analysis import rules

logger = logging.getLogger(__name__)


class RSIIntelligence:
    """
    Regime-aware RSI interpreter.

    Usage:
        rsi_intel = RSIIntelligence()
        result = rsi_intel.analyze(close_prices, regime_hint="BULL")
    """

    # Constants from centralized rules
    BULL_RSI_FLOOR = rules.BULL_RSI_FLOOR
    BULL_RSI_CEIL = rules.BULL_RSI_CEIL
    BEAR_RSI_FLOOR = rules.BEAR_RSI_FLOOR
    BEAR_RSI_CEIL = rules.BEAR_RSI_CEIL
    SWING_LOOKBACK = rules.SWING_LOOKBACK
    MIN_SWING_DISTANCE = rules.MIN_SWING_DISTANCE

    def analyze(
        self,
        close: np.ndarray,
        regime_hint: str = "NEUTRAL",   # From VP bias, Wyckoff, or SMA slope
        period: int = 14,
    ) -> RSIIntelligenceResult:
        """
        Full regime-aware RSI analysis.

        Args:
            close: Array of close prices (min 50 bars recommended)
            regime_hint: "BULL", "BEAR", or "NEUTRAL" from external regime detector
            period: RSI period (default 14)
        """
        result = RSIIntelligenceResult()

        if len(close) < period + self.SWING_LOOKBACK:
            result.diagnosis = f"Insufficient data ({len(close)} bars, need {period + self.SWING_LOOKBACK})"
            return result

        # ── 1. Calculate RSI series ───────────────────────────
        rsi_series = self._calc_rsi_series(close, period)
        current_rsi = rsi_series[-1]
        result.rsi_value = round(current_rsi, 1)

        # ── 2. Determine RSI Regime (Brown/Cardwell) ──────────
        result.rsi_regime = self._determine_regime(rsi_series, regime_hint)

        # ── 3. Classify RSI Zone (regime-aware) ───────────────
        result.rsi_zone = self._classify_zone(current_rsi, result.rsi_regime)

        # ── 4. Detect Divergences & Reversals (Cardwell) ──────
        div_type, div_strength = self._detect_divergences(
            close, rsi_series, result.rsi_regime
        )
        result.divergence_type = div_type
        result.divergence_strength = round(div_strength, 2)

        # ── 5. Slope analysis (Price vs RSI trendlines) ───────
        price_slope, rsi_slope, alignment = self._slope_analysis(close, rsi_series)
        result.price_slope = round(price_slope, 4)
        result.rsi_slope = round(rsi_slope, 4)
        result.slope_alignment = alignment

        # ── 6. Composite conviction score ─────────────────────
        result.rsi_conviction = self._compute_conviction(result)

        # ── 7. Build diagnosis ────────────────────────────────
        result.diagnosis = self._build_diagnosis(result)

        return result

    # ═══════════════════════════════════════════════════════════
    # INTERNAL METHODS
    # ═══════════════════════════════════════════════════════════

    def _calc_rsi_series(self, close: np.ndarray, period: int) -> np.ndarray:
        """Calculate full RSI series using Wilder's smoothing."""
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        # Wilder's exponential moving average
        avg_gain = np.zeros(len(gains))
        avg_loss = np.zeros(len(gains))

        # Seed with SMA
        avg_gain[period - 1] = np.mean(gains[:period])
        avg_loss[period - 1] = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # First `period` values are unreliable
        rsi[:period] = 50.0
        return rsi

    def _determine_regime(self, rsi_series: np.ndarray, hint: str) -> str:
        """
        Determine RSI regime using Brown's range rules + external hint.

        Bull: RSI oscillates 40-80 (rarely below 40)
        Bear: RSI oscillates 20-60 (rarely above 60)
        """
        recent = rsi_series[-20:]  # Last 20 bars

        rsi_min = float(np.min(recent))
        rsi_max = float(np.max(recent))
        rsi_avg = float(np.mean(recent))

        # Internal RSI-based regime detection
        if rsi_min >= 35 and rsi_avg > 50:
            rsi_regime = "BULL"
        elif rsi_max <= 65 and rsi_avg < 50:
            rsi_regime = "BEAR"
        else:
            rsi_regime = "NEUTRAL"

        # If external hint (VP, Wyckoff) aligns, trust it more
        if hint in ("BULL", "BEAR"):
            # External hint gets priority when RSI is ambiguous
            if rsi_regime == "NEUTRAL":
                return hint
            # When both agree, high confidence
            if rsi_regime == hint:
                return hint
            # Conflict: trust RSI internal reading (it sees momentum)
            return rsi_regime

        return rsi_regime

    def _classify_zone(self, rsi: float, regime: str) -> str:
        """
        Classify current RSI reading into actionable zone per regime.
        """
        if regime == "BULL":
            if rsi <= 45:
                return "PULLBACK_BUY"       # Sweet spot: pullback in uptrend
            elif rsi <= 60:
                return "HEALTHY_BULL"        # Normal bull territory
            elif rsi <= 80:
                return "CONTINUATION"        # Strong momentum, NOT overbought
            else:
                return "EXTREME_BULL"        # >80: very extended, watch for reversal

        elif regime == "BEAR":
            if rsi >= 55:
                return "BOUNCE_SELL"         # Rally into resistance zone
            elif rsi >= 40:
                return "HEALTHY_BEAR"        # Normal bear territory
            elif rsi >= 20:
                return "CONTINUATION_DOWN"   # Strong downward momentum
            else:
                return "EXTREME_BEAR"        # <20: very extended, watch for bounce

        else:  # NEUTRAL
            if rsi <= 35:
                return "OVERSOLD"
            elif rsi >= 65:
                return "OVERBOUGHT"
            elif rsi <= 45:
                return "LEAN_BULLISH"
            elif rsi >= 55:
                return "LEAN_BEARISH"
            else:
                return "NEUTRAL"

    def _detect_divergences(
        self, close: np.ndarray, rsi: np.ndarray, regime: str
    ) -> tuple[str, float]:
        """
        Detect Cardwell Positive/Negative Reversals and Classic Divergences.

        Positive Reversal (Cardwell):
          Price makes HIGHER low, RSI makes LOWER low → BUY (trend continuation)

        Negative Reversal (Cardwell):
          Price makes LOWER high, RSI makes HIGHER high → SELL (trend continuation)

        Classic Bullish Divergence:
          Price makes LOWER low, RSI makes HIGHER low → potential reversal UP

        Classic Bearish Divergence:
          Price makes HIGHER high, RSI makes LOWER high → potential reversal DOWN
        """
        n = len(close)
        lb = min(self.SWING_LOOKBACK, n - 1)

        # Find swing lows in price and RSI
        price_lows = self._find_swing_lows(close[-lb:])
        rsi_lows = self._find_swing_lows(rsi[-lb:])
        price_highs = self._find_swing_highs(close[-lb:])
        rsi_highs = self._find_swing_highs(rsi[-lb:])

        # Need at least 2 swings to compare
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            # Compare the two most recent swing lows
            p_low1, p_low2 = close[-lb:][price_lows[-2]], close[-lb:][price_lows[-1]]
            r_low1, r_low2 = rsi[-lb:][rsi_lows[-2]], rsi[-lb:][rsi_lows[-1]]

            # Positive Reversal: price HL + RSI LL → bullish continuation
            if p_low2 > p_low1 and r_low2 < r_low1:
                strength = min(abs(r_low1 - r_low2) / 10.0, 1.0)
                if regime == "BULL":
                    return "POSITIVE_REVERSAL", strength * 1.0  # Full weight in bull
                return "POSITIVE_REVERSAL", strength * 0.6

            # Classic Bullish Divergence: price LL + RSI HL → potential reversal
            if p_low2 < p_low1 and r_low2 > r_low1:
                strength = min(abs(r_low2 - r_low1) / 10.0, 1.0)
                if regime == "BEAR":
                    return "CLASSIC_BULLISH_DIV", strength * 0.8
                return "CLASSIC_BULLISH_DIV", strength * 0.5

        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            p_hi1, p_hi2 = close[-lb:][price_highs[-2]], close[-lb:][price_highs[-1]]
            r_hi1, r_hi2 = rsi[-lb:][rsi_highs[-2]], rsi[-lb:][rsi_highs[-1]]

            # Negative Reversal: price LH + RSI HH → bearish continuation
            if p_hi2 < p_hi1 and r_hi2 > r_hi1:
                strength = min(abs(r_hi2 - r_hi1) / 10.0, 1.0)
                if regime == "BEAR":
                    return "NEGATIVE_REVERSAL", strength * 1.0
                return "NEGATIVE_REVERSAL", strength * 0.6

            # Classic Bearish Divergence: price HH + RSI LH → potential reversal
            if p_hi2 > p_hi1 and r_hi2 < r_hi1:
                strength = min(abs(r_hi1 - r_hi2) / 10.0, 1.0)
                if regime == "BULL":
                    return "CLASSIC_BEARISH_DIV", strength * 0.8
                return "CLASSIC_BEARISH_DIV", strength * 0.5

        return "NONE", 0.0

    def _slope_analysis(
        self, close: np.ndarray, rsi: np.ndarray, lookback: int = 10
    ) -> tuple[float, float, str]:
        """
        Compare linear regression slopes of price vs RSI.
        Diverging slopes = momentum fading or building.
        """
        if len(close) < lookback or len(rsi) < lookback:
            return 0.0, 0.0, "ALIGNED"

        x = np.arange(lookback, dtype=float)

        # Normalized price slope (% change per bar)
        price_seg = close[-lookback:]
        price_slope = np.polyfit(x, price_seg, 1)[0] / float(np.mean(price_seg)) * 100

        # RSI slope (points per bar)
        rsi_seg = rsi[-lookback:]
        rsi_slope = np.polyfit(x, rsi_seg, 1)[0]

        # Are they aligned?
        if price_slope > 0.05 and rsi_slope > 0.3:
            alignment = "ALIGNED"         # Both rising
        elif price_slope < -0.05 and rsi_slope < -0.3:
            alignment = "ALIGNED"         # Both falling
        elif price_slope > 0.05 and rsi_slope < -0.3:
            alignment = "DIVERGING"       # Price up, RSI down → weakening
        elif price_slope < -0.05 and rsi_slope > 0.3:
            alignment = "CONVERGING"      # Price down, RSI up → strengthening
        else:
            alignment = "ALIGNED"         # Flat / no clear signal

        return price_slope, rsi_slope, alignment

    def _compute_conviction(self, result: RSIIntelligenceResult) -> float:
        """
        Composite conviction score: -1.0 (bearish) to +1.0 (bullish).
        Combines zone, divergence, and slope alignment.
        """
        score = 0.0

        # Zone contribution (±0.4 max)
        score += rules.ZONE_SCORES.get(result.rsi_zone, 0.0)

        # Divergence contribution (±0.4 max)
        score += rules.DIVERGENCE_SCORES.get(result.divergence_type, 0.0) * result.divergence_strength

        # Slope alignment contribution (±0.2 max)
        if result.slope_alignment == "DIVERGING":
            score -= 0.2  # Momentum fading
        elif result.slope_alignment == "CONVERGING":
            score += 0.2  # Momentum building

        return round(max(-1.0, min(1.0, score)), 2)

    def _build_diagnosis(self, r: RSIIntelligenceResult) -> str:
        """Human-readable diagnosis."""
        parts = [f"RSI={r.rsi_value:.0f} Regime={r.rsi_regime} Zone={r.rsi_zone}"]

        if r.divergence_type != "NONE":
            parts.append(f"Signal={r.divergence_type}(str={r.divergence_strength:.0%})")

        if r.slope_alignment != "ALIGNED":
            parts.append(f"Slopes={r.slope_alignment}(price={r.price_slope:+.3f} rsi={r.rsi_slope:+.2f})")

        parts.append(f"Conviction={r.rsi_conviction:+.2f}")
        return " | ".join(parts)

    # ── Swing Detection Helpers ─────────────────────────────
    @staticmethod
    def _find_swing_lows(data: np.ndarray, min_dist: int = 3) -> list[int]:
        """Find local minima indices."""
        lows = []
        for i in range(1, len(data) - 1):
            if data[i] < data[i - 1] and data[i] <= data[i + 1]:
                if not lows or (i - lows[-1]) >= min_dist:
                    lows.append(i)
        return lows

    @staticmethod
    def _find_swing_highs(data: np.ndarray, min_dist: int = 3) -> list[int]:
        """Find local maxima indices."""
        highs = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] >= data[i + 1]:
                if not highs or (i - highs[-1]) >= min_dist:
                    highs.append(i)
        return highs
