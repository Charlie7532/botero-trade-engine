"""
Shared fixtures for Botero Trade test suite.
"""
import os
import sys
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC
from unittest.mock import MagicMock

# Load .env BEFORE anything else so MONGODB_URI is available
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from pymongo import MongoClient

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Test MongoDB URI — uses the same Atlas cluster with a test-specific database
_TEST_MONGODB_URI = os.getenv(
    "MONGODB_URI", "mongodb://localhost:27017"
)
_TEST_DB_NAME = "botero_trade_test"


@pytest.fixture
def mongo_db():
    """
    Provides a clean MongoDB test database.
    Drops test collections before AND after each test for isolation.
    Uses collection-level drops (Atlas free tier doesn't allow dropDatabase).
    """
    client = MongoClient(_TEST_MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client[_TEST_DB_NAME]

    # Clean before test (in case previous run crashed)
    _clean_test_collections(db)

    yield db

    # Clean after test
    _clean_test_collections(db)
    client.close()


def _clean_test_collections(db):
    """Drop all test collections individually (Atlas-compatible)."""
    for name in db.list_collection_names():
        db.drop_collection(name)


@pytest.fixture
def tmp_journal_dir(mongo_db, monkeypatch):
    """
    Provides a clean MongoDB-backed TradeJournal.
    Patches module-level DB function to use test database.

    Also creates a temporary filesystem dir for any file-based
    operations that might still exist in adjacent code.
    """
    tmp = tempfile.mkdtemp()
    journal_dir = Path(tmp) / "journal"
    journal_dir.mkdir()

    # Patch the module-level _get_mongo_db to return test DB
    monkeypatch.setattr(
        "backend.application.trade_journal._get_mongo_db",
        lambda: mongo_db,
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
