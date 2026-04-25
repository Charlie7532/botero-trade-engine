"""Backward-compatible re-export — actual implementation in modules/pattern_recognition/pattern_engine.py"""
from modules.pattern_recognition.pattern_engine import PatternRecognitionIntelligence, PatternVerdict

__all__ = ["PatternRecognitionIntelligence", "PatternVerdict"]
