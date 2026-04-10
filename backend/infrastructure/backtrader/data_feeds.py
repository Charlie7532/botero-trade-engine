from datetime import datetime

import backtrader as bt
import pandas as pd

from domain.entities import Bar


def bars_to_dataframe(bars: list[Bar]) -> pd.DataFrame:
    """Convert a list of Bar entities into a Backtrader-compatible DataFrame."""
    df = pd.DataFrame([{
        "datetime": b.timestamp,
        "open": b.open,
        "high": b.high,
        "low": b.low,
        "close": b.close,
        "volume": b.volume,
        "openinterest": 0,
    } for b in bars])
    df.set_index("datetime", inplace=True)
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    return df


def create_data_feed(bars: list[Bar]) -> bt.feeds.PandasData:
    """Create a Backtrader PandasData feed from a list of Bar entities.

    Usage:
        bars = await broker.get_bars("AAPL", "1d", start, end)
        feed = create_data_feed(bars)
        cerebro.adddata(feed)
    """
    df = bars_to_dataframe(bars)
    return bt.feeds.PandasData(dataname=df)
