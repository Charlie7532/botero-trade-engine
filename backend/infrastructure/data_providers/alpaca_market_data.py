"""
Alpaca Market Data Adapter
============================
Bridges Alpaca MCP + SDK to the Botero Trade engine for market data.

IMPORTANT CONTEXT:
- Alpaca is on the FREE plan (paper trading / testing)
- Will migrate to Interactive Brokers in the future
- This adapter sits behind MarketDataPort abstraction for easy swap

Data provided:
- OHLCV bars (1min → 1month)
- Latest quotes and trades
- Snapshots (real-time price data)

Alpaca Free Tier Limitations:
- No real-time data (15-min delay on market data)
- Limited to US equities
- Rate limits apply

Priority hierarchy:
- Finviz Elite → Primary for screening data
- Yahoo Finance → VIX, yields, options chains (free, no rate limit)
- Alpaca → OHLCV history + execution
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class OHLCV:
    """Standardized OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float = 0.0
    trade_count: int = 0


@dataclass
class Quote:
    """Real-time (or delayed) quote."""
    ticker: str
    bid: float = 0.0
    ask: float = 0.0
    bid_size: int = 0
    ask_size: int = 0
    last_price: float = 0.0
    last_size: int = 0
    timestamp: str = ""


class AlpacaMarketData:
    """
    Market data adapter for Alpaca.

    Uses Alpaca SDK directly (not MCP) for data retrieval.
    MCP tools are used by the orchestrator for execution.

    This adapter will be replaced by InteractiveBrokersMarketData
    when the broker migration happens — both implement MarketDataPort.
    """

    def __init__(self):
        self._client = None
        self._trading_client = None
        self.logger = logging.getLogger(f"{__name__}.AlpacaMarketData")

    def _get_data_client(self):
        """Lazy init of Alpaca Stock Historical data client."""
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            api_key = os.environ.get("ALPACA_API_KEY", "")
            secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
            if not api_key:
                raise ValueError("ALPACA_API_KEY not set in environment")
            self._client = StockHistoricalDataClient(api_key, secret_key)
        return self._client

    def _get_trading_client(self):
        """Lazy init of Alpaca Trading client."""
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            api_key = os.environ.get("ALPACA_API_KEY", "")
            secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
            self._trading_client = TradingClient(api_key, secret_key, paper=True)
        return self._trading_client

    # ═══════════════════════════════════════════════════════════
    # OHLCV BARS
    # ═══════════════════════════════════════════════════════════

    def get_bars(
        self,
        ticker: str,
        timeframe: str = "1Day",
        start: datetime = None,
        end: datetime = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """
        Get historical OHLCV bars.

        Args:
            ticker: Stock symbol
            timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day', '1Week', '1Month'
            start: Start datetime (default: 200 bars back)
            end: End datetime (default: now)
            limit: Maximum bars

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume, VWAP
        """
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            tf_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, "Min"),
                "15Min": TimeFrame(15, "Min"),
                "1Hour": TimeFrame.Hour,
                "1Day": TimeFrame.Day,
                "1Week": TimeFrame.Week,
                "1Month": TimeFrame.Month,
            }

            if start is None:
                start = datetime.now(UTC) - timedelta(days=365)

            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=tf_map.get(timeframe, TimeFrame.Day),
                start=start,
                end=end,
                limit=limit,
            )

            client = self._get_data_client()
            bars = client.get_stock_bars(request)

            if not bars or ticker not in bars.data:
                self.logger.warning(f"No data for {ticker}")
                return pd.DataFrame()

            rows = []
            for bar in bars.data[ticker]:
                rows.append({
                    "Open": bar.open,
                    "High": bar.high,
                    "Low": bar.low,
                    "Close": bar.close,
                    "Volume": bar.volume,
                    "VWAP": bar.vwap if hasattr(bar, 'vwap') else 0,
                    "TradeCount": bar.trade_count if hasattr(bar, 'trade_count') else 0,
                })

            df = pd.DataFrame(rows)
            self.logger.info(f"Alpaca bars {ticker}: {len(df)} bars ({timeframe})")
            return df

        except Exception as e:
            self.logger.error(f"Error getting Alpaca bars for {ticker}: {e}")
            return pd.DataFrame()

    def get_bars_multi(
        self,
        tickers: list[str],
        timeframe: str = "1Day",
        start: datetime = None,
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """Get bars for multiple tickers in one call."""
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            tf_map = {
                "1Day": TimeFrame.Day,
                "1Hour": TimeFrame.Hour,
                "1Week": TimeFrame.Week,
            }

            if start is None:
                start = datetime.now(UTC) - timedelta(days=200)

            request = StockBarsRequest(
                symbol_or_symbols=tickers,
                timeframe=tf_map.get(timeframe, TimeFrame.Day),
                start=start,
                limit=limit,
            )

            client = self._get_data_client()
            bars = client.get_stock_bars(request)

            result = {}
            for ticker in tickers:
                if ticker in bars.data:
                    rows = [{
                        "Open": b.open, "High": b.high, "Low": b.low,
                        "Close": b.close, "Volume": b.volume,
                    } for b in bars.data[ticker]]
                    result[ticker] = pd.DataFrame(rows)

            self.logger.info(f"Alpaca multi-bars: {len(result)}/{len(tickers)} tickers")
            return result

        except Exception as e:
            self.logger.error(f"Error getting multi bars: {e}")
            return {}

    # ═══════════════════════════════════════════════════════════
    # LATEST QUOTE / SNAPSHOT
    # ═══════════════════════════════════════════════════════════

    def get_latest_quote(self, ticker: str) -> Quote:
        """Get latest quote for a ticker."""
        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            client = self._get_data_client()
            request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quotes = client.get_stock_latest_quote(request)

            if ticker in quotes:
                q = quotes[ticker]
                return Quote(
                    ticker=ticker,
                    bid=q.bid_price,
                    ask=q.ask_price,
                    bid_size=q.bid_size,
                    ask_size=q.ask_size,
                    timestamp=str(q.timestamp),
                )

        except Exception as e:
            self.logger.error(f"Error getting quote for {ticker}: {e}")

        return Quote(ticker=ticker)

    # ═══════════════════════════════════════════════════════════
    # ACCOUNT / POSITIONS (convenience wrappers)
    # ═══════════════════════════════════════════════════════════

    def get_account_summary(self) -> dict:
        """Get account equity, cash, and buying power."""
        try:
            client = self._get_trading_client()
            acct = client.get_account()
            return {
                "equity": float(acct.equity),
                "cash": float(acct.cash),
                "buying_power": float(acct.buying_power),
                "portfolio_value": float(acct.portfolio_value),
                "day_pnl": float(acct.equity) - float(acct.last_equity),
                "day_pnl_pct": (float(acct.equity) - float(acct.last_equity)) / float(acct.last_equity) * 100 if float(acct.last_equity) > 0 else 0,
            }
        except Exception as e:
            self.logger.error(f"Error getting account: {e}")
            return {}

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        try:
            client = self._get_trading_client()
            positions = client.get_all_positions()
            return [
                {
                    "ticker": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
                    "market_value": float(p.market_value),
                }
                for p in positions
            ]
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
