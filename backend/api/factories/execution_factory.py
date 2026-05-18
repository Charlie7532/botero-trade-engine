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


def build_fred():
    """Build FRED macro intelligence adapter."""
    from backend.modules.flow_intelligence.infrastructure.fred_adapter import FREDMacroIntelligence
    return FREDMacroIntelligence()


def build_finnhub():
    """Build Finnhub intelligence adapter."""
    from backend.modules.flow_intelligence.infrastructure.finnhub_api import FinnhubIntelligence
    return FinnhubIntelligence()


def build_rotation_adapter():
    """Build YahooRotationAdapter (with yfinance fallback, no MCP required)."""
    from backend.modules.rotation_intelligence.infrastructure.yahoo_rotation_adapter import YahooRotationAdapter
    return YahooRotationAdapter()


def build_rotation_scanner():
    """Build a RotationScanner with a live rotation adapter."""
    from backend.modules.rotation_intelligence.application.use_cases.rotation_scanner import RotationScanner
    return RotationScanner(data_port=build_rotation_adapter())


def build_fundamental_data():
    """Build FundamentalDataPort (GuruFocus cache → parser bridge)."""
    from backend.modules.portfolio_management.infrastructure.gurufocus_fundamental_adapter import GuruFocusFundamentalAdapter
    return GuruFocusFundamentalAdapter()


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
        fundamental_data=build_fundamental_data(),
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
    """Build SurveillanceLoop wired to QUALITY journal, SEC adapter, and blacklist."""
    from backend.modules.execution.application.use_cases.surveillance_loop import SurveillanceLoop
    from backend.modules.portfolio_management.infrastructure.sec_filings_adapter import SecFilingsAdapter
    
    sec_adapter = SecFilingsAdapter()
    
    return SurveillanceLoop(
        quality_journal=build_quality_journal(),
        sec_adapter=sec_adapter,
        blacklist=build_blacklist(),
    )


# ── Live CIO Mandate ────────────────────────────────────────

def synthesize_live_mandate(cio=None):
    """
    Connect Market Health snapshot + GEX to the CIO for a dynamic mandate.

    Vault-First (Rule 13): reads MH snapshot from Neon Vault.
    Fallback: yfinance + rotation scanner if snapshot unavailable.
    """
    from backend.modules.portfolio_management.application.use_cases.cio_orchestrator import CIOOrchestrator

    cio = cio or CIOOrchestrator()

    # ── Vault-First: read MH snapshot ──
    mh_snapshot = None
    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.market_health.domain.entities.health_snapshot import MarketHealthSnapshot
        store = TimescaleDataStore()
        mh_raw = store.load_mcp_latest("market/health", "MARKET")
        if mh_raw:
            mh_snapshot = MarketHealthSnapshot.from_dict(mh_raw)
    except Exception as e:
        logger.debug(f"MH snapshot load failed (will fallback): {e}")

    # ── GEX Regime from Neon vault ──
    gex_regime = "UNKNOWN"
    try:
        gamma_snap = store.load_mcp_latest("flow/gex", "SPY")
        if gamma_snap and isinstance(gamma_snap, dict):
            gex_regime = gamma_snap.get("gamma_regime", "UNKNOWN")
    except Exception as e:
        logger.debug(f"GEX regime load skipped: {e}")

    try:
        store.close()
    except Exception:
        pass

    if mh_snapshot:
        # ── FAST PATH: Vault-backed (no API calls) ──
        # Map MH snapshot fields to CIO params
        vix_estimate = 20.0  # Default; MH snapshot gives regime, not raw VIX
        if mh_snapshot.vol_regime_quality == "CRISIS":
            vix_estimate = 35.0
        elif mh_snapshot.vol_regime_quality == "ELEVATED":
            vix_estimate = 25.0
        elif mh_snapshot.vol_regime_quality == "COMPLACENT":
            vix_estimate = 14.0

        breadth = mh_snapshot.breadth_participation * 100

        yield_inverted = mh_snapshot.yield_curve_signal == "INVERTED"

        # Rotation data from snapshot (basic mapping)
        rotation_data = {
            "cycle_phase": mh_snapshot.rotation_phase,
        }

        mandate = cio.synthesize_mandate(
            vix=vix_estimate,
            market_breadth=breadth,
            macro_news_sentiment=0.0,
            yield_curve_inverted=yield_inverted,
            cycle_phase=rotation_data.get("cycle_phase", "UNKNOWN"),
            gex_regime=gex_regime,
        )

        logger.info(
            f"🏛️ Live Mandate (Vault): {mandate.regime} | "
            f"Q={mandate.quality_budget_pct*100:.0f}% S={mandate.speculative_budget_pct*100:.0f}% | "
            f"Vol={mh_snapshot.vol_regime_quality} Breadth={breadth:.0f}% "
            f"YC={'INV' if yield_inverted else 'OK'} "
            f"F&G={mh_snapshot.fg_score:.0f}({mh_snapshot.fg_action})"
        )
        return mandate

    # ── FALLBACK: yfinance + rotation scanner (legacy) ──
    logger.warning("synthesize_live_mandate: MH snapshot unavailable — using legacy yfinance path")
    import yfinance as yf

    # 1. VIX (live from yfinance)
    try:
        vix_data = yf.download("^VIX", period="5d", progress=False)
        if vix_data is not None and not vix_data.empty:
            close = vix_data["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            vix = float(close.iloc[-1])
        else:
            vix = 20.0
    except Exception:
        vix = 20.0

    # 2. Rotation Intelligence (unified scanner — provides breadth + flows)
    rotation_data = {}
    breadth = 50.0
    try:
        scanner = build_rotation_scanner()
        rotation_result = scanner.scan()
        rotation_data = {
            "sector_flows": getattr(rotation_result, "sector_flows", {}),
            "international_flows": getattr(rotation_result, "international_flows", {}),
            "asset_class_flows": getattr(rotation_result, "asset_class_flows", {}),
            "cycle_phase": getattr(rotation_result, "cycle_phase", "UNKNOWN"),
            "capitulation_level": getattr(rotation_result, "capitulation_level", 0),
            "fear_greed_score": getattr(rotation_result, "fear_greed_score", 50.0),
        }
        breadth = getattr(rotation_result, "market_breadth_pct", 50.0)
    except Exception as e:
        logger.warning(f"Rotation scan failed (non-fatal): {e}")

    # 3. FRED Macro (yield curve from yfinance)
    try:
        ust10 = yf.download("^TNX", period="5d", progress=False)
        ust2 = yf.download("^IRX", period="5d", progress=False)
        if ust10 is not None and ust2 is not None and not ust10.empty:
            t10_close = ust10["Close"]
            t2_close = ust2["Close"]
            if hasattr(t10_close, "columns"):
                t10_close = t10_close.iloc[:, 0]
            if hasattr(t2_close, "columns"):
                t2_close = t2_close.iloc[:, 0]
            spread = float(t10_close.iloc[-1]) - float(t2_close.iloc[-1]) / 100
            yield_inverted = spread < 0
        else:
            yield_inverted = False
    except Exception:
        yield_inverted = False

    # 4. Synthesize
    mandate = cio.synthesize_mandate(
        vix=vix,
        market_breadth=breadth,
        macro_news_sentiment=0.0,
        yield_curve_inverted=yield_inverted,
        sector_flows=rotation_data.get("sector_flows"),
        international_flows=rotation_data.get("international_flows"),
        asset_class_flows=rotation_data.get("asset_class_flows"),
        cycle_phase=rotation_data.get("cycle_phase", "UNKNOWN"),
        gex_regime=gex_regime,
    )

    cap_level = rotation_data.get("capitulation_level", 0)
    logger.info(
        f"🏛️ Live Mandate (Legacy): {mandate.regime} | "
        f"Q={mandate.quality_budget_pct*100:.0f}% S={mandate.speculative_budget_pct*100:.0f}% | "
        f"VIX={vix:.1f} Breadth={breadth:.0f}% YC={'INV' if yield_inverted else 'OK'} "
        f"Cap_L{cap_level}"
    )
    return mandate
