"""Backward-compatible re-export — actual implementation in modules/volume_intelligence/profile_engine.py"""
from modules.volume_intelligence.profile_engine import VolumeProfileAnalyzer
from modules.volume_intelligence.models import VolumeNode, VolumeProfileResult, DualProfileResult

__all__ = ["VolumeProfileAnalyzer", "VolumeNode", "VolumeProfileResult", "DualProfileResult"]
