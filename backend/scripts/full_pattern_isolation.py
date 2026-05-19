"""
full_pattern_isolation.py — The Definitive Pattern Alpha Scanner
=================================================================
Tests EVERY pattern at EVERY timeframe against the blind DLR baseline.

Layers:
  MICRO  = 3 daily bars (patterns of 1, 2, 3 candles)
  MACRO  = 3 super-candles (5 bars each = 15 days)
  HYPER  = 3 hyper-candles (3 super-candles each = 15 bars each = 45 days total)

For each layer, we ask: does THIS specific pattern beat buying blind in this DLR regime?
Only patterns with ΔWR > 3pp AND N >= 20 are flagged as Alpha candidates.
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
from backend.modules.simulation.infrastructure.signal_adapters import PatternSignalAdapter
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

    regimes = ["MUY_BAJISTA", "BAJISTA", "HORIZONTAL", "ALCISTA", "MUY_ALCISTA"]

    # Baseline: all bars per regime (buy blind)
    baseline = {r: [] for r in regimes}

    # Per-layer, per-pattern, per-regime: list of (ret_3d, ret_5d, ret_10d)
    layers = ["MICRO", "MACRO", "HYPER"]
    results = {}
    for layer in layers:
        results[layer] = {}  # pattern -> {regime -> [rets]}

    print("=" * 110)
    print(f"{'FULL PATTERN ALPHA SCANNER — ALL PATTERNS × ALL TIMEFRAMES × ALL REGIMES':^110}")
    print(f"{'Universe: 30 Quality Tickers | Execution: Open[T+1] + 10% ATR Slippage':^110}")
    print(f"{'MICRO=3 bars | MACRO=3×5=15 bars | HYPER=3×15=45 bars':^110}")
    print("=" * 110)

    for ti, ticker in enumerate(QUALITY_TICKERS):
        print(f"  [{ti+1}/{len(QUALITY_TICKERS)}] {ticker}...", flush=True)
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
            open_next = opens[i + 1]
            tr_next = highs[i + 1] - lows[i + 1]
            slippage = tr_next * 0.10
            exec_price = open_next + slippage
            if exec_price <= 0:
                continue

            ret_3d = (closes[i + 3] - exec_price) / exec_price * 100
            ret_5d = (closes[i + 5] - exec_price) / exec_price * 100
            ret_10d = (closes[i + 10] - exec_price) / exec_price * 100
            rets = (ret_3d, ret_5d, ret_10d)

            baseline[trend].append(rets)

            # ── MICRO (3 daily bars) ──
            micro_window = df.iloc[max(0, i - 2):i + 1].copy()
            micro_v = engine.detect(micro_window)
            if micro_v.primary_pattern != "NONE":
                pat = micro_v.primary_pattern
                if pat not in results["MICRO"]:
                    results["MICRO"][pat] = {r: [] for r in regimes}
                results["MICRO"][pat][trend].append(rets)

            # ── MACRO (3 super-candles = 15 bars) ──
            super_df = PatternSignalAdapter.synthesize_super_candles(
                ohlc, end_idx=i, group_size=5, n_groups=3
            )
            if super_df is not None and len(super_df) >= 3:
                super_df.columns = [c.capitalize() for c in super_df.columns]
                macro_v = engine.detect(super_df)
                if macro_v.primary_pattern != "NONE":
                    pat = macro_v.primary_pattern
                    if pat not in results["MACRO"]:
                        results["MACRO"][pat] = {r: [] for r in regimes}
                    results["MACRO"][pat][trend].append(rets)

            # ── HYPER (3 hyper-candles = 45 bars) ──
            hyper_df = PatternSignalAdapter.synthesize_hyper_candles(ohlc, end_idx=i)
            if hyper_df is not None and len(hyper_df) >= 3:
                hyper_v = engine.detect(hyper_df)
                if hyper_v.primary_pattern != "NONE":
                    pat = hyper_v.primary_pattern
                    if pat not in results["HYPER"]:
                        results["HYPER"][pat] = {r: [] for r in regimes}
                    results["HYPER"][pat][trend].append(rets)

    store.close()

    # ── REPORT ──
    print("\n\n")
    print("=" * 130)
    print(f"{'ALPHA CANDIDATES (ΔWR@10d > +3pp AND N >= 20)':^130}")
    print("=" * 130)

    alpha_candidates = []

    for layer in layers:
        print(f"\n{'━' * 130}")
        print(f"  LAYER: {layer}")
        timeframe = {"MICRO": "3 bars", "MACRO": "15 bars (3 weeks)", "HYPER": "45 bars (9 weeks)"}[layer]
        print(f"  Timeframe: {timeframe}")
        print(f"{'━' * 130}")
        print(f"  {'Pattern':<22} | {'Regime':<14} | {'N':>5} | "
              f"{'Blind WR@10d':>12} | {'Pattern WR@10d':>14} | {'ΔWR':>7} | {'Blind Avg':>9} | {'Pat Avg':>9} | {'ΔAvg':>7} | Verdict")
        print(f"  {'-' * 22}-+-{'-' * 14}-+-{'-' * 5}-+-{'-' * 12}-+-{'-' * 14}-+-{'-' * 7}-+-{'-' * 9}-+-{'-' * 9}-+-{'-' * 7}-+-{'-' * 10}")

        for pattern in sorted(results[layer].keys()):
            for regime in regimes:
                pat_data = results[layer][pattern][regime]
                base_data = baseline[regime]

                if len(pat_data) < 20 or len(base_data) < 30:
                    continue

                pat_arr = np.array(pat_data)
                base_arr = np.array(base_data)

                pat_wr10 = (pat_arr[:, 2] > 0).mean() * 100
                base_wr10 = (base_arr[:, 2] > 0).mean() * 100
                delta_wr = pat_wr10 - base_wr10

                pat_avg10 = pat_arr[:, 2].mean()
                base_avg10 = base_arr[:, 2].mean()
                delta_avg = pat_avg10 - base_avg10

                if abs(delta_wr) > 3.0:
                    verdict = "✅ ALPHA" if delta_wr > 3.0 else "🔻 ANTI-ALPHA"
                    alpha_candidates.append({
                        "layer": layer, "pattern": pattern, "regime": regime,
                        "n": len(pat_data), "delta_wr": delta_wr, "delta_avg": delta_avg,
                        "pat_wr": pat_wr10, "base_wr": base_wr10,
                    })
                else:
                    verdict = "— noise"

                if abs(delta_wr) > 3.0:
                    print(f"  {pattern:<22} | {regime:<14} | {len(pat_data):>5} | "
                          f"{base_wr10:>11.1f}% | {pat_wr10:>13.1f}% | {delta_wr:>+6.1f}% | "
                          f"{base_avg10:>8.2f}% | {pat_avg10:>8.2f}% | {delta_avg:>+6.2f}% | {verdict}")

    # ── SUMMARY ──
    print("\n\n")
    print("=" * 130)
    print(f"{'FINAL ALPHA REGISTRY — PATTERNS THAT ADD INDEPENDENT ALPHA':^130}")
    print("=" * 130)

    alpha_only = [c for c in alpha_candidates if c["delta_wr"] > 3.0]
    anti_only = [c for c in alpha_candidates if c["delta_wr"] < -3.0]

    alpha_only.sort(key=lambda x: x["delta_wr"], reverse=True)
    anti_only.sort(key=lambda x: x["delta_wr"])

    print(f"\n  🏆 ALPHA PATTERNS (buy signal — {len(alpha_only)} found):")
    for c in alpha_only:
        print(f"    {c['layer']:<6} | {c['pattern']:<22} | {c['regime']:<14} | N={c['n']:>4} | ΔWR={c['delta_wr']:>+5.1f}pp | ΔRet={c['delta_avg']:>+5.2f}%")

    print(f"\n  🔻 ANTI-ALPHA PATTERNS (fade/avoid — {len(anti_only)} found):")
    for c in anti_only:
        print(f"    {c['layer']:<6} | {c['pattern']:<22} | {c['regime']:<14} | N={c['n']:>4} | ΔWR={c['delta_wr']:>+5.1f}pp | ΔRet={c['delta_avg']:>+5.2f}%")

    # Save CSV
    log_dir = Path(_root / "backend/scripts/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(alpha_candidates).to_csv(log_dir / "alpha_pattern_registry.csv", index=False)
    print(f"\n  Saved to: {log_dir / 'alpha_pattern_registry.csv'}")


if __name__ == "__main__":
    main()
