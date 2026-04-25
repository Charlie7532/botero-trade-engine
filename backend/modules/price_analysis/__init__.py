"""
Price Analysis Module
=====================
Responsible for:
  - RSI regime-aware interpretation (Cardwell/Brown)
  - Price phase classification (CORRECTION, BREAKOUT, etc.)
  - Entry verdict generation (FIRE, STALK, ABORT)

Components:
  models.py     → EntryVerdict, RSIIntelligenceResult
  rules.py      → All thresholds and constants
  rsi_engine.py → RSIIntelligence (regime-aware RSI)
  phase_engine.py → PricePhaseIntelligence (phase classification)
"""
from modules.price_analysis.models import EntryVerdict, RSIIntelligenceResult
from modules.price_analysis import rules

__all__ = ["EntryVerdict", "RSIIntelligenceResult", "rules"]
