"""
Shared fixtures for Botero Trade test suite.
"""
import os
import sys
import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, UTC
from unittest.mock import MagicMock

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite database for TradeJournal tests."""
    return str(tmp_path / "test_journal.db")


@pytest.fixture
def tmp_journal_dir(tmp_path, monkeypatch):
    """Temporary journal directory — patches module-level constants."""
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    monkeypatch.setattr(
        "backend.application.trade_journal.JOURNAL_DIR", journal_dir
    )
    monkeypatch.setattr(
        "backend.application.trade_journal.DB_PATH", journal_dir / "test.db"
    )
    return journal_dir


@pytest.fixture
def sample_trade_entry():
    """Minimal valid TradeJournalEntry for testing."""
    from backend.application.trade_journal import TradeJournalEntry

    return TradeJournalEntry(
        trade_id="test-001",
        ticker="AAPL",
        direction="LONG",
        entry_price=175.50,
        entry_time=datetime.now(UTC).isoformat(),
        entry_thesis="Strong RS + insider cluster buy",
        alpha_score=78.5,
        qualifier_grade="A-",
        rs_vs_spy=1.12,
        insider_signal="strong_buy",
        sector_alignment="WITH_TIDE",
    )


@pytest.fixture
def risk_guardian():
    """Pre-configured RiskGuardian for testing."""
    from backend.application.portfolio_intelligence import RiskGuardian

    return RiskGuardian(
        max_portfolio_dd=0.15,
        max_daily_loss=0.03,
        vix_reduce_threshold=30,
        vix_emergency_threshold=40,
        cooldown_hours=48,
    )


@pytest.fixture
def trailing_stop():
    """Pre-configured AdaptiveTrailingStop for testing."""
    from backend.application.portfolio_intelligence import AdaptiveTrailingStop

    return AdaptiveTrailingStop()
