"""Backward-compatible re-export — actual implementation in modules/flow_intelligence/whale_engine.py"""
from modules.flow_intelligence.whale_engine import EventFlowIntelligence, WhaleFlowReader, MacroEvent, WhaleVerdict, MacroEventCalendar

__all__ = ["EventFlowIntelligence", "WhaleFlowReader", "MacroEvent", "WhaleVerdict", "MacroEventCalendar"]
