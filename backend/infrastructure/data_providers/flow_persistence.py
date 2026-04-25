"""Backward-compatible re-export — actual implementation in modules/flow_intelligence/persistence_engine.py"""
from modules.flow_intelligence.persistence_engine import FlowPersistenceAnalyzer, FlowPersistenceSignal

__all__ = ["FlowPersistenceAnalyzer", "FlowPersistenceSignal"]
