"""
Tests for TradeJournal — Institutional trade recording system.

Tests verify:
- Opening a trade persists to MongoDB
- Closing a trade updates all fields
- Querying open trades returns correct results
- Pattern storage and retrieval
"""
import json
import pytest
from datetime import datetime, UTC
from dataclasses import asdict

from backend.application.trade_journal import TradeJournal, TradeJournalEntry


class TestTradeJournalOpenClose:

    def test_open_trade_persists_to_db(self, mongo_db, sample_trade_entry):
        """Opening a trade should create a MongoDB document with status OPEN."""
        journal = TradeJournal(db=mongo_db)
        trade_id = journal.open_trade(sample_trade_entry)

        assert trade_id == "test-001"

        # Verify in MongoDB
        doc = mongo_db["trades"].find_one({"trade_id": trade_id}, {"_id": 0})

        assert doc is not None
        assert doc["ticker"] == "AAPL"
        assert doc["status"] == "OPEN"
        assert doc["entry_price"] == 175.50

    def test_open_trade_stores_complete_document(self, mongo_db, sample_trade_entry):
        """Opening a trade should store the complete document natively (no JSON blob)."""
        journal = TradeJournal(db=mongo_db)
        journal.open_trade(sample_trade_entry)

        doc = mongo_db["trades"].find_one({"trade_id": "test-001"}, {"_id": 0})

        # All fields should be queryable directly — no full_data TEXT blob
        assert doc["alpha_score"] == 78.5
        assert doc["qualifier_grade"] == "A-"
        assert doc["rs_vs_spy"] == 1.12
        assert doc["insider_signal"] == "strong_buy"
        assert doc["sector_alignment"] == "WITH_TIDE"
        assert doc["entry_thesis"] == "Strong RS + insider cluster buy"

    def test_close_trade_updates_status_and_pnl(
        self, mongo_db, sample_trade_entry
    ):
        """Closing a trade should set status=CLOSED and record PnL."""
        journal = TradeJournal(db=mongo_db)
        journal.open_trade(sample_trade_entry)

        # Simulate close
        sample_trade_entry.exit_price = 190.00
        sample_trade_entry.exit_time = datetime.now(UTC).isoformat()
        sample_trade_entry.exit_reason = "TAKE_PROFIT"
        sample_trade_entry.pnl_dollars = 1450.0
        sample_trade_entry.pnl_pct = 8.26
        sample_trade_entry.pnl_r_multiple = 2.1
        sample_trade_entry.was_winner = True
        sample_trade_entry.lesson_learned = "Let winners run"
        sample_trade_entry.grade = "A"
        sample_trade_entry.status = "CLOSED"

        journal.close_trade(sample_trade_entry)

        doc = mongo_db["trades"].find_one({"trade_id": "test-001"}, {"_id": 0})

        assert doc["status"] == "CLOSED"
        assert doc["pnl_dollars"] == 1450.0
        assert doc["was_winner"] is True
        assert doc["exit_reason"] == "TAKE_PROFIT"

    def test_get_open_trades_returns_only_open(
        self, mongo_db, sample_trade_entry
    ):
        """get_open_trades should return only OPEN status trades."""
        journal = TradeJournal(db=mongo_db)

        # Open two trades
        journal.open_trade(sample_trade_entry)

        entry2 = TradeJournalEntry(
            trade_id="test-002", ticker="MSFT", direction="LONG",
            entry_price=420.0, entry_time=datetime.now(UTC).isoformat(),
        )
        journal.open_trade(entry2)

        # Close the first
        sample_trade_entry.exit_price = 180.0
        sample_trade_entry.pnl_dollars = 450.0
        sample_trade_entry.was_winner = True
        sample_trade_entry.exit_reason = "STOP_HIT"
        sample_trade_entry.grade = "B"
        journal.close_trade(sample_trade_entry)

        open_trades = journal.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0]["ticker"] == "MSFT"

    def test_get_trade_full_data(self, mongo_db, sample_trade_entry):
        """get_trade_full_data should return the complete document."""
        journal = TradeJournal(db=mongo_db)
        journal.open_trade(sample_trade_entry)

        data = journal.get_trade_full_data("test-001")
        assert data is not None
        assert data["ticker"] == "AAPL"
        assert data["alpha_score"] == 78.5
        assert data["entry_price"] == 175.50


class TestTradeJournalPatterns:

    def test_close_with_patterns_stores_tags(
        self, mongo_db, sample_trade_entry
    ):
        """Pattern tags should be stored in the patterns collection on close."""
        journal = TradeJournal(db=mongo_db)
        journal.open_trade(sample_trade_entry)

        sample_trade_entry.exit_price = 190.0
        sample_trade_entry.pnl_dollars = 1450.0
        sample_trade_entry.pnl_r_multiple = 2.1
        sample_trade_entry.was_winner = True
        sample_trade_entry.exit_reason = "STOP_HIT"
        sample_trade_entry.grade = "A"
        sample_trade_entry.pattern_tags = ["breakout", "insider_signal", "with_tide"]

        journal.close_trade(sample_trade_entry)

        patterns = list(mongo_db["patterns"].find(
            {"trade_id": "test-001"},
            {"_id": 0},
        ))

        assert len(patterns) == 3
        names = [p["pattern_name"] for p in patterns]
        assert "breakout" in names
        assert "insider_signal" in names
        assert all(p["outcome"] == "WIN" for p in patterns)
