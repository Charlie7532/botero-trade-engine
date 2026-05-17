"""
Price Analysis Module
=====================
Responsible for:
  - RSI regime-aware interpretation (Cardwell/Brown)
  - Regression Channel position analysis (σ, fear/greed, trim)
  - Price phase classification (CORRECTION, BREAKOUT, etc.)
  - Entry verdict generation (FIRE, STALK, ABORT)

Components:
  models.py                    → EntryVerdict, RSIIntelligenceResult, RCIntelligenceResult
  rules.py                     → All thresholds and constants
  analyze_rsi.py               → RSIIntelligence (regime-aware RSI — MOMENTUM)
  analyze_regression_channel.py → RegressionChannelIntelligence (channel — POSITION)
  detect_price_phase.py        → PricePhaseIntelligence (phase classification)
"""
from backend.modules.price_analysis.domain.entities.price_models import (
    EntryVerdict,
    RSIIntelligenceResult,
    RCIntelligenceResult,
)
import backend.modules.price_analysis.domain.rules.price_rules as rules

__all__ = ["EntryVerdict", "RSIIntelligenceResult", "RCIntelligenceResult", "rules"]

