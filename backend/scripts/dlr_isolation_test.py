"""
dlr_isolation_test.py — The Killer Question
=============================================
Does the Alpha come from the PATTERN or from the DLR TREND alone?

Test: Compare forward returns of:
  A) ALL bars where DLR = MUY_BAJISTA (no pattern filter)
  B) Bars where DLR = MUY_BAJISTA AND micro_pattern = HAMMER
  C) Bars where DLR = MUY_BAJISTA AND micro_pattern = NONE (no pattern detected)

If A ≈ B, the pattern adds nothing — DLR is the real signal.
If B >> A >> C, the pattern adds genuine independent information.
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import linregress
from pathlib import Path

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.pattern_recognition.application.use_cases.detect_patterns import PatternRecognitionIntelligence
from backend.scripts.calibrate_passports import QUALITY_TICKERS

import logging
logging.getLogger("backend.modules.pattern_recognition").setLevel(logging.ERROR)


def get_trend_state(closes, i, lookback=60):
    y = closes[i-lookback:i]
    if len(y) < lookback or y[0] <= 0:
        return "HORIZONTAL"
    x = np.arange(lookback)
    y_norm = y / y[0]
    slope, _, _, _, _ = linregress(x, y_norm)
    if slope > 0.0020:     return "MUY_ALCISTA"
    elif slope > 0.0005:   return "ALCISTA"
    elif slope > -0.0005:  return "HORIZONTAL"
    elif slope > -0.0020:  return "BAJISTA"
    else:                  return "MUY_BAJISTA"


def main():
    store = TimescaleDataStore()
    engine = PatternRecognitionIntelligence()

    # Buckets: DLR regime → list of (ret_3d, ret_5d, ret_10d)
    # Group A: ALL bars in that regime (buy blindly)
    # Group B: Bars where pattern == specific pattern
    # Group C: Bars where pattern == NONE
    regimes = ["MUY_BAJISTA", "BAJISTA", "HORIZONTAL", "ALCISTA", "MUY_ALCISTA"]
    
    buckets_all = {r: [] for r in regimes}
    buckets_hammer = {r: [] for r in regimes}
    buckets_inv_hammer = {r: [] for r in regimes}
    buckets_none = {r: [] for r in regimes}
    buckets_any_bull = {r: [] for r in regimes}  # Any BULLISH pattern

    print("=" * 100)
    print(f"{'DLR ISOLATION TEST — IS IT THE TREND OR THE PATTERN?':^100}")
    print(f"{'Universe: 30 Quality Tickers | Execution: Open[T+1] + 10% ATR Slippage':^100}")
    print("=" * 100)

    for ticker in QUALITY_TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue

        df = ohlc.copy()
        df.columns = [c.capitalize() for c in df.columns]
        closes = df['Close'].values
        opens = df['Open'].values
        highs = df['High'].values
        lows = df['Low'].values

        for i in range(60, len(df) - 11):
            trend = get_trend_state(closes, i)
            
            # Execution reality
            open_next = opens[i+1]
            tr_next = highs[i+1] - lows[i+1]
            slippage = tr_next * 0.10
            exec_price = open_next + slippage  # Always buying
            
            if exec_price <= 0:
                continue

            ret_3d = (closes[i+3] - exec_price) / exec_price * 100
            ret_5d = (closes[i+5] - exec_price) / exec_price * 100
            ret_10d = (closes[i+10] - exec_price) / exec_price * 100
            rets = (ret_3d, ret_5d, ret_10d)

            # Group A: ALL bars in this regime (the "blind DLR" baseline)
            buckets_all[trend].append(rets)

            # Detect pattern
            micro_window = df.iloc[max(0, i-2):i+1].copy()
            verdict = engine.detect(micro_window)
            pattern = verdict.primary_pattern

            if pattern == "NONE":
                buckets_none[trend].append(rets)
            elif pattern == "HAMMER":
                buckets_hammer[trend].append(rets)
            elif pattern == "INVERTED_HAMMER":
                buckets_inv_hammer[trend].append(rets)
            
            if verdict.sentiment == "BULLISH":
                buckets_any_bull[trend].append(rets)

    store.close()

    # ── REPORT ──
    for regime in regimes:
        all_rets = buckets_all[regime]
        hammer_rets = buckets_hammer[regime]
        inv_hammer_rets = buckets_inv_hammer[regime]
        none_rets = buckets_none[regime]
        any_bull_rets = buckets_any_bull[regime]

        if len(all_rets) < 30:
            continue

        print(f"\n{'─' * 100}")
        print(f"  RÉGIMEN: {regime}  (N total = {len(all_rets):,})")
        print(f"{'─' * 100}")
        print(f"  {'Strategy':<35} | {'N':>6} | {'WR 3d':>7} {'Avg 3d':>7} | {'WR 5d':>7} {'Avg 5d':>7} | {'WR 10d':>7} {'Avg 10d':>7}")
        print(f"  {'-'*35}-+-{'-'*6}-+-{'-'*15}-+-{'-'*15}-+-{'-'*15}")

        def print_row(label, data):
            if len(data) < 5:
                print(f"  {label:<35} | {len(data):>6} | {'N/A':>15} | {'N/A':>15} | {'N/A':>15}")
                return
            arr = np.array(data)
            wr3 = (arr[:, 0] > 0).mean() * 100
            wr5 = (arr[:, 1] > 0).mean() * 100
            wr10 = (arr[:, 2] > 0).mean() * 100
            avg3 = arr[:, 0].mean()
            avg5 = arr[:, 1].mean()
            avg10 = arr[:, 2].mean()
            print(f"  {label:<35} | {len(data):>6} | {wr3:>6.1f}% {avg3:>6.2f}% | {wr5:>6.1f}% {avg5:>6.2f}% | {wr10:>6.1f}% {avg10:>6.2f}%")

        print_row("A) BUY BLIND (all bars)", all_rets)
        print_row("B) BUY when pattern=HAMMER", hammer_rets)
        print_row("C) BUY when pattern=INV_HAMMER", inv_hammer_rets)
        print_row("D) BUY when ANY bullish pattern", any_bull_rets)
        print_row("E) BUY when pattern=NONE", none_rets)

        # Delta analysis
        if len(hammer_rets) >= 5 and len(all_rets) >= 30:
            all_arr = np.array(all_rets)
            ham_arr = np.array(hammer_rets)
            delta_wr = (ham_arr[:, 2] > 0).mean() * 100 - (all_arr[:, 2] > 0).mean() * 100
            delta_ret = ham_arr[:, 2].mean() - all_arr[:, 2].mean()
            verdict = "PATTERN ADDS ALPHA ✅" if delta_wr > 3.0 else ("MARGINAL ⚠️" if delta_wr > 0 else "PATTERN IS NOISE ❌")
            print(f"\n  >> HAMMER vs BLIND: ΔWR@10d = {delta_wr:+.1f}pp, ΔReturn@10d = {delta_ret:+.2f}% → {verdict}")

    print("\n" + "=" * 100)
    print("INTERPRETATION:")
    print("  If A ≈ B: The pattern adds nothing. DLR is the real signal.")
    print("  If B >> A: The pattern adds genuine independent information.")
    print("  If E ≈ A: Pattern detection is irrelevant — it's ALL about the trend.")
    print("=" * 100)


if __name__ == "__main__":
    main()
