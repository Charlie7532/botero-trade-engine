#!/usr/bin/env python3
"""Probe: which station tickers exist, their date ranges, and zigzag leg counts."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# Candidate tickers for the 11 stations + SPY + BSI alternates
candidates = {
    "vix": "VIX", "vvix": "VVIX", "pcr": "CBOE_PCR", "fg": "FG",
    "sv5_turbulence": "SV5_TURBULENCE", "skew": "SKEW", "credit": "CREDIT_RATIO",
    "yield_curve": "YIELD_SPREAD", "rotation": "ROTATION_INDEX",
    "bsi_s5fi": "S5FI", "bsi_s5tw": "S5TW", "dxy": "DXY", "spy": "SPY",
}

print("=" * 90)
print("TICKER AVAILABILITY (market.ohlcv_bars, 1d)")
print("=" * 90)
print(f"{'code':<16}{'ticker':<18}{'bars':>8}{'first':>14}{'last':>14}{'last_close':>12}")
for code, tk in candidates.items():
    try:
        df = store.load_bars(tk, "1d")
        if df is None or df.empty:
            print(f"{code:<16}{tk:<18}{'EMPTY':>8}")
            continue
        first = df.index.min().date()
        last = df.index.max().date()
        print(f"{code:<16}{tk:<18}{len(df):>8}{str(first):>14}{str(last):>14}{df['close'].iloc[-1]:>12.4f}")
    except Exception as e:
        print(f"{code:<16}{tk:<18}ERROR: {e}")

print()
print("=" * 90)
print("ZIGZAG LEGS (SPY)")
print("=" * 90)
for scale in ["zz25", "zz50", "zz75"]:
    legs = repo.get_confirmed_legs("SPY", scale)
    if legs:
        d0 = pd.to_datetime(legs[0].start_timestamp).date()
        d1 = pd.to_datetime(legs[-1].start_timestamp).date()
        n_min = sum(1 for l in legs if l.start_type == "MIN")
        n_max = sum(1 for l in legs if l.start_type == "MAX")
        print(f"  {scale}: N={len(legs)} (MIN={n_min}, MAX={n_max})  {d0} .. {d1}")

# Also list all distinct tickers present (sanity check for BSI naming)
print()
print("=" * 90)
print("DISTINCT TICKERS in market.ohlcv_bars (1d)")
print("=" * 90)
try:
    df = pd.read_sql("SELECT DISTINCT ticker FROM market.ohlcv_bars WHERE timeframe='1d' ORDER BY ticker",
                     store.engine)
    print("  ", ", ".join(df["ticker"].tolist()))
except Exception as e:
    print("  ERROR:", e)

store.close()
