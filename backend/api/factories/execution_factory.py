"""
Execution Factory — Composition Root
=========================================
The ONLY file where environment variables are read and concrete
adapters are instantiated. All domain code receives ports.

Usage (in API routers or startup):
    from backend.api.factories.execution_factory import build_orchestrator
    orchestrator = build_orchestrator()
"""
import os
import logging

logger = logging.getLogger(__name__)


def build_broker():
    """Build the default BrokerPort implementation (Alpaca Paper)."""
    from backend.modules.execution.infrastructure.brokers.alpaca_adapter import AlpacaAdapter
    return AlpacaAdapter()


def build_journal():
    """Build the default TradeJournalPort implementation (PostgreSQL)."""
    from backend.modules.execution.infrastructure.postgres_journal_adapter import PostgresTradeJournalAdapter
    dsn = os.getenv("POSTGRES_URL", "")
    return PostgresTradeJournalAdapter(dsn=dsn)


def build_market_data():
    """Build the default EntryMarketDataPort implementation (yfinance)."""
    from backend.modules.entry_decision.infrastructure.market_data_fetcher import MarketDataFetcher
    return MarketDataFetcher()


def build_options_provider():
    """Build the default OptionsDataPort implementation (yfinance)."""
    from backend.modules.options_gamma.infrastructure.yfinance_adapter import YFinanceOptionsAdapter
    return YFinanceOptionsAdapter()


def build_flow_data():
    """Build the default FlowDataPort implementation (UW adapter)."""
    from backend.modules.flow_intelligence.infrastructure.uw_adapter import UnusualWhalesIntelligence
    return UnusualWhalesIntelligence()


def build_entry_hub():
    """Build EntryIntelligenceHub with all ports wired."""
    from backend.modules.entry_decision.domain.use_cases.evaluate_entry import EntryIntelligenceHub
    return EntryIntelligenceHub(
        market_data=build_market_data(),
        flow_data=build_flow_data(),
        options_provider=build_options_provider(),
        journal=build_journal(),
    )


def build_orchestrator():
    """Build a fully wired PaperTradingOrchestrator."""
    from backend.modules.execution.domain.use_cases.orchestrate_paper_trading import PaperTradingOrchestrator
    return PaperTradingOrchestrator(
        broker=build_broker(),
        journal=build_journal(),
        market_data=build_market_data(),
        entry_hub=build_entry_hub(),
    )


def build_position_monitor():
    """Build a fully wired PositionMonitor."""
    from backend.modules.execution.domain.use_cases.monitor_positions import PositionMonitor
    return PositionMonitor(
        broker=build_broker(),
        journal=build_journal(),
    )
