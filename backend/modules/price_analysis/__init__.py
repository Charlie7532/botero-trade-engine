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
from backend.modules.price_analysis.domain.entities.price_models import EntryVerdict, RSIIntelligenceResult
import backend.modules.price_analysis.domain.rules.price_rules as rules

__all__ = ["EntryVerdict", "RSIIntelligenceResult", "rules"]
