"""
Trade Journal — Domain Port Re-Export
========================================
The canonical implementation is in infrastructure/mongo_journal_adapter.py.
The Port interface is in domain/ports/trade_journal_port.py.

This file re-exports TradeJournalPort as TradeJournal for backward
compatibility during the migration. New code should use TradeJournalPort.
"""
from backend.modules.execution.domain.ports.trade_journal_port import TradeJournalPort

# Backward compat alias — existing consumers import TradeJournal from here
TradeJournal = TradeJournalPort
