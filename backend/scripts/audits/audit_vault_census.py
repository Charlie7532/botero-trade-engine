#!/usr/bin/env python3
"""
Audit Vault Census
==================
Measures exact current population of Neon PostgreSQL (market.ohlcv_bars)
dynamically. Resolves P12 and prevents static drift in documentation.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def get_vault_census():
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        # 1. Global timeframes summary
        tf_query = """
            SELECT 
                timeframe,
                COUNT(DISTINCT ticker) as tickers,
                COUNT(*) as bars
            FROM market.ohlcv_bars
            GROUP BY timeframe
            ORDER BY bars DESC;
        """
        tf_df = pd.read_sql(tf_query, conn)
        grand_total_tickers_query = "SELECT COUNT(DISTINCT ticker) as total_tickers FROM market.ohlcv_bars;"
        grand_tickers = int(pd.read_sql(grand_total_tickers_query, conn).iloc[0]["total_tickers"])
        grand_bars = int(tf_df["bars"].sum())

        print("=" * 80)
        print(f"VAULT GLOBAL CENSUS — market.ohlcv_bars (as of {now_utc})")
        print("=" * 80)
        print(f"Total Unique Tickers (All Timeframes): {grand_tickers}")
        print(f"Total Bars in Pozo (All Timeframes):    {grand_bars:,}")
        print("-" * 80)
        print(f"{'Timeframe':12s} | {'Tickers':8s} | {'Bars':12s}")
        print("-" * 38)
        for _, r in tf_df.iterrows():
            print(f"{r['timeframe']:12s} | {r['tickers']:8d} | {r['bars']:12,d}")
        print("-" * 38)

        # 2. Daily (1d) census by family
        query = """
            SELECT 
                ticker,
                COUNT(*) as count,
                MIN(time) as min_time,
                MAX(time) as max_time
            FROM market.ohlcv_bars
            WHERE timeframe = '1d'
            GROUP BY ticker
            ORDER BY count DESC;
        """
        df = pd.read_sql(query, conn)
        total_1d_tickers = len(df)
        total_1d_bars = int(df["count"].sum())
        min_date = df["min_time"].min()
        max_date = df["max_time"].max()

        print(f"\n1D DAILY CENSUS (752 daily tickers + CBOE_PCR_5M = 753 total)")
        print(f"Time Span: {str(min_date)[:10]} -> {str(max_date)[:10]}")
        print("-" * 80)

        # Categorize families
        def categorize(t: str) -> str:
            if t in ("S5TH", "S5FI", "S5TW"):
                return "S5 Market"
            elif t in ("SV5TH", "SV5FI", "SV5TW"):
                return "SV5 Market"
            elif t.startswith("S5_") and any(t.endswith(sfx) for sfx in ("_TH", "_FI", "_TW")):
                return "S5 Sector"
            elif t.startswith("SV5_") and any(t.endswith(sfx) for sfx in ("_TH", "_FI", "_TW")):
                return "SV5 Sector"
            elif t.startswith("S5CAP_"):
                return "S5CAP Sector"
            elif t.startswith("VBI_"):
                return "VBI Sector"
            elif t in ("VIX", "VVIX", "SKEW", "SV5_TURBULENCE"):
                return "Volatility"
            elif t == "FG":
                return "Sentiment"
            elif t == "CBOE_PCR":
                return "Options"
            elif t == "CREDIT_RATIO":
                return "Credit"
            elif t == "YIELD_SPREAD":
                return "Yields"
            elif t == "ROTATION_INDEX":
                return "Rotation"
            elif t in ("SPX", "NDQ", "TNX"):
                return "Indices"
            elif t in ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLV", "XLF", "XLY", "XLP", "XLI", "XLE", "XLU", "XLRE", "XLB", "XLC"):
                return "ETFs"
            else:
                return "SP500 Stocks"

        df["family"] = df["ticker"].apply(categorize)
        fam_agg = df.groupby("family").agg(
            tickers=("ticker", "count"),
            bars=("count", "sum"),
            min_date=("min_time", lambda s: str(s.min())[:10]),
            max_date=("max_time", lambda s: str(s.max())[:10])
        ).loc[[
            "S5 Market", "SV5 Market", "S5 Sector", "SV5 Sector", "S5CAP Sector", "VBI Sector",
            "Volatility", "Sentiment", "Options", "Credit", "Yields", "Rotation",
            "Indices", "ETFs", "SP500 Stocks"
        ]]

        print(f"{'Family':20s} | {'Tickers':7s} | {'Bars':10s} | {'Range':23s}")
        print("-" * 68)
        for fam, row in fam_agg.iterrows():
            rng = f"{row['min_date'][:4]} -> {row['max_date'][:4]}"
            print(f"{fam:20s} | {row['tickers']:7d} | {row['bars']:10,d} | {rng:23s}")
        print("-" * 68)
        print(f"{'TOTAL 1D':20s} | {total_1d_tickers:7d} | {total_1d_bars:10,d} |")
        print(f"{'TOTAL GLOBAL':20s} | {grand_tickers:7d} | {grand_bars:10,d} | (includes 5m/5min)")
        print("=" * 80)
        return grand_tickers, grand_bars, now_utc
    finally:
        store._put(conn)
        store.close()

if __name__ == "__main__":
    get_vault_census()
