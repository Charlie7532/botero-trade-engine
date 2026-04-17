"""
Finviz MCP Intelligence Adapter
==================================
Bridges Finviz MCP tools (35 capabilities) to the Botero Trade engine.

Replaces fragile `finvizfinance` web scrapers in:
- SectorFlowEngine (sector_flow.py)
- MarketBreadth (market_breadth.py)
- AlphaScanner (alpha_scanner.py)

MCP Tools Consumed:
- get_sector_performance → sector_flow.get_sector_performance()
- get_industry_performance → sector_flow enrichment
- volume_surge_screener → alpha_scanner movers
- get_relative_volume_stocks → sector_flow unusual volume
- get_market_overview → market_breadth overview
- earnings_screener / earnings_winners_screener → alpha_scanner earnings plays
- get_stock_fundamentals → quality enrichment
- custom_screener → flexible filtering
- get_moving_average_position → breadth and RS calculations
- get_stock_news / get_sector_news → sentiment input
- get_sec_filings → trade journal context
"""
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SectorPerformance:
    """Structured sector performance data."""
    sector: str
    perf_1d: float = 0.0
    perf_1w: float = 0.0
    perf_1m: float = 0.0
    perf_3m: float = 0.0
    perf_ytd: float = 0.0
    perf_1y: float = 0.0
    relative_volume: float = 1.0
    momentum_score: float = 0.0  # Composite momentum


@dataclass
class VolumesSurge:
    """Stock with unusual volume activity."""
    ticker: str
    price: float = 0.0
    change_pct: float = 0.0
    volume: float = 0.0
    relative_volume: float = 1.0
    market_cap: str = ""


@dataclass 
class EarningsPlay:
    """Stock with earnings catalyst."""
    ticker: str
    earnings_date: str = ""
    earnings_timing: str = ""  # before, after
    price: float = 0.0
    change_pct: float = 0.0
    market_cap: str = ""


class FinvizIntelligence:
    """
    Adapter for Finviz MCP tools.

    Like GuruFocusIntelligence, this class receives pre-fetched MCP
    data and returns structured objects for engine consumption.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.FinvizIntelligence")

    # ═══════════════════════════════════════════════════════════
    # SECTOR PERFORMANCE (replaces finvizfinance group.performance)
    # ═══════════════════════════════════════════════════════════

    def parse_sector_performance(self, mcp_response: dict) -> list[SectorPerformance]:
        """
        Parse MCP: get_sector_performance response.

        Replaces the `finvizfinance.group('Sector', 'Performance')`
        scraper in SectorFlowEngine.get_sector_performance().
        """
        try:
            sectors = []
            data = mcp_response if isinstance(mcp_response, (dict, list)) else {}
            items = data if isinstance(data, list) else data.get("data", data.get("sectors", []))

            for item in items:
                sp = SectorPerformance(
                    sector=str(item.get("sector", item.get("name", "Unknown"))),
                    perf_1d=self._safe_float(item.get("perf_1d", item.get("1D", 0))),
                    perf_1w=self._safe_float(item.get("perf_1w", item.get("1W", 0))),
                    perf_1m=self._safe_float(item.get("perf_1m", item.get("1M", 0))),
                    perf_3m=self._safe_float(item.get("perf_3m", item.get("3M", 0))),
                    perf_ytd=self._safe_float(item.get("perf_ytd", item.get("YTD", 0))),
                    perf_1y=self._safe_float(item.get("perf_1y", item.get("1Y", 0))),
                    relative_volume=self._safe_float(item.get("relative_volume", 1.0)),
                )
                # Composite momentum: weighted average of timeframes
                sp.momentum_score = (
                    sp.perf_1d * 0.1 + sp.perf_1w * 0.2 +
                    sp.perf_1m * 0.3 + sp.perf_3m * 0.4
                )
                sectors.append(sp)

            sectors.sort(key=lambda s: s.momentum_score, reverse=True)
            self.logger.info(f"Parsed {len(sectors)} sector performances")
            return sectors

        except Exception as e:
            self.logger.error(f"Error parsing sector performance: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # VOLUME SURGE (replaces finvizfinance screener for unusual volume)
    # ═══════════════════════════════════════════════════════════

    def parse_volume_surge(self, mcp_response: dict) -> list[VolumesSurge]:
        """
        Parse MCP: volume_surge_screener or get_relative_volume_stocks.

        Replaces `finvizfinance` screener queries for unusual volume
        in SectorFlowEngine.get_unusual_volume().
        """
        try:
            items = self._extract_items(mcp_response)
            surges = []

            for item in items:
                surges.append(VolumesSurge(
                    ticker=str(item.get("ticker", item.get("Ticker", ""))),
                    price=self._safe_float(item.get("price", item.get("Price", 0))),
                    change_pct=self._safe_float(item.get("change_pct", item.get("Change", 0))),
                    volume=self._safe_float(item.get("volume", item.get("Volume", 0))),
                    relative_volume=self._safe_float(
                        item.get("relative_volume", item.get("Relative Volume", 1.0))
                    ),
                    market_cap=str(item.get("market_cap", item.get("Market Cap", ""))),
                ))

            self.logger.info(f"Parsed {len(surges)} volume surges")
            return surges

        except Exception as e:
            self.logger.error(f"Error parsing volume surge: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # EARNINGS PLAYS (new capability from Finviz MCP)
    # ═══════════════════════════════════════════════════════════

    def parse_earnings_screener(self, mcp_response: dict) -> list[EarningsPlay]:
        """
        Parse MCP: earnings_screener / earnings_winners_screener.

        New capability not available via the finvizfinance library.
        """
        try:
            items = self._extract_items(mcp_response)
            plays = []

            for item in items:
                plays.append(EarningsPlay(
                    ticker=str(item.get("ticker", item.get("Ticker", ""))),
                    earnings_date=str(item.get("earnings_date", "")),
                    earnings_timing=str(item.get("earnings_timing", "")),
                    price=self._safe_float(item.get("price", item.get("Price", 0))),
                    change_pct=self._safe_float(item.get("change_pct", item.get("Change", 0))),
                    market_cap=str(item.get("market_cap", item.get("Market Cap", ""))),
                ))

            self.logger.info(f"Parsed {len(plays)} earnings plays")
            return plays

        except Exception as e:
            self.logger.error(f"Error parsing earnings screener: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # MARKET OVERVIEW (replaces multiple finviz scraper queries)
    # ═══════════════════════════════════════════════════════════

    def parse_market_overview(self, mcp_response: dict) -> dict:
        """
        Parse MCP: get_market_overview.

        Provides a single-call summary of market state — replaces
        multiple finvizfinance screener queries.
        """
        try:
            data = mcp_response if isinstance(mcp_response, dict) else {}
            return {
                "market_status": data.get("market_status", "unknown"),
                "sp500_change": self._safe_float(data.get("sp500_change", 0)),
                "dow_change": self._safe_float(data.get("dow_change", 0)),
                "nasdaq_change": self._safe_float(data.get("nasdaq_change", 0)),
                "vix": self._safe_float(data.get("vix", 0)),
                "advances": int(self._safe_float(data.get("advances", 0))),
                "declines": int(self._safe_float(data.get("declines", 0))),
                "new_highs": int(self._safe_float(data.get("new_highs", 0))),
                "new_lows": int(self._safe_float(data.get("new_lows", 0))),
                "raw_data": data,
            }
        except Exception as e:
            self.logger.error(f"Error parsing market overview: {e}")
            return {}

    # ═══════════════════════════════════════════════════════════
    # SEC FILINGS (new capability for TradeJournal context)
    # ═══════════════════════════════════════════════════════════

    def parse_sec_filings(self, ticker: str, mcp_response: dict) -> list[dict]:
        """
        Parse MCP: get_sec_filings / get_major_sec_filings.

        Provides SEC filing context for TradeJournal entries.
        """
        try:
            items = self._extract_items(mcp_response)
            return [
                {
                    "ticker": ticker,
                    "form_type": item.get("form_type", item.get("Form", "")),
                    "date": item.get("date", item.get("Date", "")),
                    "title": item.get("title", item.get("Title", "")),
                    "url": item.get("url", item.get("URL", "")),
                }
                for item in items[:10]
            ]
        except Exception as e:
            self.logger.error(f"Error parsing SEC filings for {ticker}: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # NEWS (for FinBERT sentiment pipeline)
    # ═══════════════════════════════════════════════════════════

    def parse_stock_news(self, ticker: str, mcp_response: dict) -> list[dict]:
        """
        Parse MCP: get_stock_news / get_sector_news.

        Returns headlines for the FinBERT sentiment scorer.
        """
        try:
            items = self._extract_items(mcp_response)
            return [
                {
                    "ticker": ticker,
                    "headline": item.get("headline", item.get("title", item.get("Title", ""))),
                    "source": item.get("source", item.get("Source", "")),
                    "date": item.get("date", item.get("Date", "")),
                    "url": item.get("url", item.get("URL", "")),
                }
                for item in items[:20]
            ]
        except Exception as e:
            self.logger.error(f"Error parsing news for {ticker}: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Safely convert value to float."""
        if value is None:
            return default
        try:
            val_str = str(value).replace('%', '').replace(',', '').strip()
            return float(val_str) if val_str else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _extract_items(mcp_response) -> list:
        """Extract list of items from various MCP response formats."""
        if not mcp_response:
            return []
        if isinstance(mcp_response, list):
            return mcp_response
        if isinstance(mcp_response, dict):
            for key in ["data", "results", "stocks", "items", "entries"]:
                if key in mcp_response and isinstance(mcp_response[key], list):
                    return mcp_response[key]
        return []
