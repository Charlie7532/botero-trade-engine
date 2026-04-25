"""Backward-compatible re-export — actual implementation in modules/entry_decision/hub.py"""
from modules.entry_decision.hub import EntryIntelligenceHub
from modules.entry_decision.models import EntryIntelligenceReport

__all__ = ["EntryIntelligenceHub", "EntryIntelligenceReport"]
