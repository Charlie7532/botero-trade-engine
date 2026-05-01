"""
Execution Factory — Composition Root
=========================================
The ONLY file where environment variables are read and concrete
adapters are instantiated. All domain code receives ports.

V12: JournalRegistry + BlacklistPort + department-scoped wiring.

Usage (in API routers or startup):
    from backend.api.factories.execution_factory import build_orchestrator
    orchestrator = build_orchestrator()
"""
import os
import logging

logger = logging.getLogger(__name__)


# ── Brokers ──────────────────────────────────────────────────

def build_quality_broker():
    """Build the Alpaca BrokerPort for the QUALITY department (new account)."""
    from backend.modules.execution.infrastructure.brokers.alpaca_adapter import AlpacaAdapter
    return AlpacaAdapter(
        api_key=os.getenv("ALPACA_QUALITY_API_KEY", ""),
        secret_key=os.getenv("ALPACA_QUALITY_SECRET_KEY", ""),
        base_url=os.getenv("ALPACA_QUALITY_BASE_URL", "https://paper-api.alpaca.markets"),
    )


def build_speculative_broker():
    """Build the Alpaca BrokerPort for the SPECULATIVE department (existing account)."""
    from backend.modules.execution.infrastructure.brokers.alpaca_adapter import AlpacaAdapter
    return AlpacaAdapter(
        api_key=os.getenv("ALPACA_API_KEY", ""),
        secret_key=os.getenv("ALPACA_SECRET_KEY", ""),
        base_url=os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
    )


def build_broker_registry() -> dict:
    """Build a BrokerRegistry mapping department → BrokerPort."""
    return {
        "QUALITY": build_quality_broker(),
        "SPECULATIVE": build_speculative_broker(),
    }


def build_ib_broker():
    """Build the Interactive Brokers BrokerPort implementation."""
    from backend.modules.execution.infrastructure.brokers.ib_adapter import IBAdapter
    return IBAdapter()


# ── Journals (department-scoped) ─────────────────────────────

def build_quality_journal():
    """Build TradeJournalPort scoped to QUALITY department tables."""
    from backend.modules.execution.infrastructure.postgres_journal_adapter import PostgresTradeJournalAdapter
    dsn = os.getenv("POSTGRES_URL", "")
    return PostgresTradeJournalAdapter(
        dsn=dsn,
        table_name="engine.trade_journal_quality",
        snapshots_table="engine.trade_snapshots_quality",
        patterns_table="engine.trade_patterns_quality",
    )


def build_speculative_journal():
    """Build TradeJournalPort scoped to SPECULATIVE department tables."""
    from backend.modules.execution.infrastructure.postgres_journal_adapter import PostgresTradeJournalAdapter
    dsn = os.getenv("POSTGRES_URL", "")
    return PostgresTradeJournalAdapter(
        dsn=dsn,
        table_name="engine.trade_journal_speculative",
        snapshots_table="engine.trade_snapshots_speculative",
        patterns_table="engine.trade_patterns_speculative",
    )


def build_journal_registry() -> dict:
    """Build JournalRegistry mapping department → TradeJournalPort."""
    return {
        "QUALITY": build_quality_journal(),
        "SPECULATIVE": build_speculative_journal(),
    }


# ── Blacklist ────────────────────────────────────────────────

def build_blacklist():
    """Build InstrumentBlacklistPort (PostgreSQL)."""
    from backend.modules.execution.infrastructure.postgres_blacklist_adapter import PostgresBlacklistAdapter
    dsn = os.getenv("POSTGRES_URL", "")
    return PostgresBlacklistAdapter(dsn=dsn)


# ── Data Providers ───────────────────────────────────────────

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


# ── Entry Hub ────────────────────────────────────────────────

def build_entry_hub():
    """Build EntryIntelligenceHub with all ports wired.

    Memory Guard (pgvector) uses SPECULATIVE journal only —
    the 9D tactical vector has no meaning for QUALITY positions.
    """
    from backend.modules.entry_decision.application.use_cases.evaluate_entry import EntryIntelligenceHub
    return EntryIntelligenceHub(
        market_data=build_market_data(),
        flow_data=build_flow_data(),
        options_provider=build_options_provider(),
        journal=build_speculative_journal(),
        blacklist=build_blacklist(),
    )


# ── Orchestrator ─────────────────────────────────────────────

def build_orchestrator():
    """Build a fully wired PaperTradingOrchestrator with dual registries."""
    from backend.modules.execution.application.use_cases.orchestrate_paper_trading import PaperTradingOrchestrator
    return PaperTradingOrchestrator(
        broker_registry=build_broker_registry(),
        journal_registry=build_journal_registry(),
        market_data=build_market_data(),
        entry_hub=build_entry_hub(),
    )


# ── Position Monitor ────────────────────────────────────────

def build_position_monitor():
    """Build a fully wired PositionMonitor."""
    from backend.modules.execution.application.use_cases.monitor_positions import PositionMonitor
    return PositionMonitor(
        broker_registry=build_broker_registry(),
        journal_registry=build_journal_registry(),
    )


# ── Surveillance Loop ───────────────────────────────────────

def build_surveillance_loop():
    """Build SurveillanceLoop wired to QUALITY journal + blacklist."""
    from backend.modules.execution.application.use_cases.surveillance_loop import SurveillanceLoop
    return SurveillanceLoop(
        quality_journal=build_quality_journal(),
        blacklist=build_blacklist(),
    )

