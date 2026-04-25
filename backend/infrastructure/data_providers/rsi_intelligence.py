"""Backward-compatible re-export — actual implementation in modules/price_analysis/rsi_engine.py"""
from modules.price_analysis.rsi_engine import RSIIntelligence
from modules.price_analysis.models import RSIIntelligenceResult

__all__ = ["RSIIntelligence", "RSIIntelligenceResult"]
