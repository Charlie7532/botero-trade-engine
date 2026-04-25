"""
Price Analysis Module — Business Rules & Constants
===================================================
ALL thresholds for price phase detection and RSI regime analysis.
Centralized here so ML/ablation can tune them in one place.
"""

# ═══════════════════════════════════════════════════════════════
# PHASE DETECTION (PricePhaseIntelligence)
# ═══════════════════════════════════════════════════════════════

# Distance from SMA20 in ATR units — beyond this = parabolic extension
EXHAUSTION_ATR_DISTANCE = 2.5

# ATR contraction: if last 5 bars < 70% of 20-bar ATR → VCP detected
VCP_RANGE_CONTRACTION = 0.70

# Minimum RVOL to confirm a breakout
BREAKOUT_RVOL_MIN = 1.5

# Maximum RVOL for a healthy correction (volume should be "dry")
CORRECTION_RVOL_MAX = 0.9

# RSI extremes (safety valves — regime-aware zones handle the nuance)
RSI_OVERBOUGHT = 75
RSI_OVERSOLD = 25

# Minimum Risk:Reward ratio to issue FIRE verdict
MIN_RR_RATIO = 3.0


# ═══════════════════════════════════════════════════════════════
# RSI REGIME (Cardwell/Brown)
# ═══════════════════════════════════════════════════════════════

# Bull regime: RSI oscillates between these bounds
BULL_RSI_FLOOR = 40    # RSI rarely drops below 40 in bull
BULL_RSI_CEIL = 80     # RSI can reach 80+ in bull (NOT overbought)

# Bear regime: RSI oscillates between these bounds
BEAR_RSI_FLOOR = 20    # RSI can reach 20 in bear
BEAR_RSI_CEIL = 60     # RSI rarely exceeds 60 in bear

# Divergence detection
SWING_LOOKBACK = 20    # Bars to look back for swing highs/lows
MIN_SWING_DISTANCE = 5 # Min bars between swings

# Slope analysis
SLOPE_LOOKBACK = 10    # Bars for linear regression
PRICE_SLOPE_THRESHOLD = 0.05   # Min normalized slope to be "trending"
RSI_SLOPE_THRESHOLD = 0.3      # Min RSI slope to be "trending"

# RSI Zone acceptable for CORRECTION entry
CORRECTION_RSI_ZONES = {
    "PULLBACK_BUY", "HEALTHY_BULL", "HEALTHY_BEAR",
    "LEAN_BULLISH", "NEUTRAL", "OVERSOLD",
}

# RSI Zones acceptable for MOMENTUM entry
MOMENTUM_RSI_ZONES = {
    "CONTINUATION", "HEALTHY_BULL", "PULLBACK_BUY",
    "LEAN_BULLISH", "NEUTRAL",
}

# Conviction scoring weights
ZONE_SCORES = {
    "PULLBACK_BUY": +0.4,
    "HEALTHY_BULL": +0.2,
    "CONTINUATION": +0.3,
    "EXTREME_BULL": +0.1,
    "BOUNCE_SELL": -0.4,
    "HEALTHY_BEAR": -0.2,
    "CONTINUATION_DOWN": -0.3,
    "EXTREME_BEAR": -0.1,
    "OVERSOLD": +0.2,
    "OVERBOUGHT": -0.2,
    "LEAN_BULLISH": +0.1,
    "LEAN_BEARISH": -0.1,
    "NEUTRAL": 0.0,
}

DIVERGENCE_SCORES = {
    "POSITIVE_REVERSAL": +0.4,
    "CLASSIC_BULLISH_DIV": +0.3,
    "NEGATIVE_REVERSAL": -0.4,
    "CLASSIC_BEARISH_DIV": -0.3,
    "NONE": 0.0,
}
