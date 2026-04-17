"""
Tests for TradeJournal — Institutional trade recording system.

Tests verify:
- Opening a trade persists to SQLite and JSON
- Closing a trade updates all fields
- Querying open trades returns correct results
- Pattern storage and retrieval
"""
import json
import pytest
import sqlite3
from datetime import datetime, UTC
from dataclasses import asdict

from backend.application.trade_journal import TradeJournal, TradeJournalEntry


class TestTradeJournalOpenClose:

    def test_open_trade_persists_to_db(self, tmp_journal_dir, sample_trade_entry):
        """Opening a trade should create a DB record with status OPEN."""
        journal = TradeJournal(db_path=str(tmp_journal_dir / "test.db"))
        trade_id = journal.open_trade(sample_trade_entry)

        assert trade_id == "test-001"

        # Verify in DB
        conn = sqlite3.connect(str(tmp_journal_dir / "test.db"))
        row = conn.execute(
            "SELECT ticker, status, entry_price FROM trades WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "AAPL"
        assert row[1] == "OPEN"
        assert row[2] == 175.50

    def test_open_trade_creates_json_file(self, tmp_journal_dir, sample_trade_entry):
        """Opening a trade should also create a JSON sidecar file."""
        journal = TradeJournal(db_path=str(tmp_journal_dir / "test.db"))
        journal.open_trade(sample_trade_entry)

        json_file = tmp_journal_dir / "test-001.json"
        assert json_file.exists()

        with open(json_file) as f:
            data = json.load(f)
        assert data["ticker"] == "AAPL"
        assert data["alpha_score"] == 78.5

    def test_close_trade_updates_status_and_pnl(
        self, tmp_journal_dir, sample_trade_entry
    ):
        """Closing a trade should set status=CLOSED and record PnL."""
        journal = TradeJournal(db_path=str(tmp_journal_dir / "test.db"))
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

        conn = sqlite3.connect(str(tmp_journal_dir / "test.db"))
        row = conn.execute(
            "SELECT status, pnl_dollars, was_winner, exit_reason FROM trades WHERE trade_id = ?",
            ("test-001",),
        ).fetchone()
        conn.close()

        assert row[0] == "CLOSED"
        assert row[1] == 1450.0
        assert row[2] == 1  # True → 1 in SQLite
        assert row[3] == "TAKE_PROFIT"

    def test_get_open_trades_returns_only_open(
        self, tmp_journal_dir, sample_trade_entry
    ):
        """get_open_trades should return only OPEN status trades."""
        journal = TradeJournal(db_path=str(tmp_journal_dir / "test.db"))

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


class TestTradeJournalPatterns:

    def test_close_with_patterns_stores_tags(
        self, tmp_journal_dir, sample_trade_entry
    ):
        """Pattern tags should be stored in the patterns table on close."""
        journal = TradeJournal(db_path=str(tmp_journal_dir / "test.db"))
        journal.open_trade(sample_trade_entry)

        sample_trade_entry.exit_price = 190.0
        sample_trade_entry.pnl_dollars = 1450.0
        sample_trade_entry.pnl_r_multiple = 2.1
        sample_trade_entry.was_winner = True
        sample_trade_entry.exit_reason = "STOP_HIT"
        sample_trade_entry.grade = "A"
        sample_trade_entry.pattern_tags = ["breakout", "insider_signal", "with_tide"]

        journal.close_trade(sample_trade_entry)

        conn = sqlite3.connect(str(tmp_journal_dir / "test.db"))
        patterns = conn.execute(
            "SELECT pattern_name, outcome FROM patterns WHERE trade_id = ?",
            ("test-001",),
        ).fetchall()
        conn.close()

        assert len(patterns) == 3
        names = [p[0] for p in patterns]
        assert "breakout" in names
        assert "insider_signal" in names
        assert all(p[1] == "WIN" for p in patterns)
