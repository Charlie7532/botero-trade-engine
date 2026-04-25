"""
Volume Intelligence Module — Business Rules & Constants
========================================================
"""

# ═══════════════════════════════════════════════════════════════
# VOLUME PROFILE (VolumeProfileAnalyzer)
# ═══════════════════════════════════════════════════════════════

# Shape detection
P_SHAPE_SKEW_THRESHOLD = 0.15     # Skew > 0.15 = P-shape (accumulation)
B_SHAPE_SKEW_THRESHOLD = -0.15    # Skew < -0.15 = b-shape (distribution)

# POC Migration
POC_MIGRATION_THRESHOLD = 0.5     # >0.5% migration = significant

# Value Area
VALUE_AREA_PCT = 0.70             # Standard 70% value area

# Volume Node classification
HVN_THRESHOLD = 1.5              # >1.5x avg volume = High Volume Node
LVN_THRESHOLD = 0.5              # <0.5x avg volume = Low Volume Node

# VP Distribution Gate (used by Entry Decision Hub)
VP_DISTRIBUTION_CONFIDENCE_THRESHOLD = 75


# ═══════════════════════════════════════════════════════════════
# KALMAN VOLUME TRACKER
# ═══════════════════════════════════════════════════════════════

# Kalman filter process noise
KALMAN_PROCESS_NOISE = 0.01
KALMAN_MEASUREMENT_NOISE = 0.1

# Wyckoff state thresholds
WYCKOFF_ACCUMULATION_VEL = 0.5    # Positive velocity + low price
WYCKOFF_MARKUP_VEL = 1.0          # High positive velocity
WYCKOFF_DISTRIBUTION_VEL = -0.3   # Negative velocity + high price
WYCKOFF_MARKDOWN_VEL = -1.0       # High negative velocity
