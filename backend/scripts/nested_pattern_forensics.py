"""
nested_pattern_forensics.py — Fractal Pattern Decomposition
==============================================================
"Patterns are words. Super-candles are sentences. Hyper-candles are paragraphs."

For each validated HYPER/MACRO pattern, decompose it into its internal
microstructure to read the NARRATIVE of how the pattern formed.

Questions this answers:
  1. When we see HYPER THREE_BLACK_CROWS, what MACRO patterns live inside
     each of the 3 hyper-candles? Are they Marubozus (pure selling) or
     Dojis (indecision)?
  2. Does the internal composition predict the QUALITY of the signal?
     A HYPER 3BC made of 3 MACRO Bearish Marubozus = "deep capitulation"
     vs a HYPER 3BC made of 3 MACRO Dojis = "slow grind" — different alpha?
  3. At the MICRO level within each super-candle: what 3-day patterns
     form the building blocks? Hammers at the end = buyers stepping in.

Output: Hierarchical narrative signatures with forward returns.
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import linregress
from pathlib import Path
from collections import defaultdict

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

EXTENDED_TICKERS = list(QUALITY_TICKERS) + ["SPY", "QQQ"]


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


def detect_micro_at(engine, df, i):
    """Detect MICRO pattern at index i (3 daily bars)."""
    window = df.iloc[max(0, i - 2):i + 1].copy()
    if len(window) < 2:
        return "NONE"
    window.columns = [c.capitalize() for c in window.columns]
    v = engine.detect(window)
    return v.primary_pattern


def decompose_hyper_event(engine, ohlc, end_idx, super_size=5, n_supers=3, n_hypers=3):
    """Decompose a HYPER event into its full narrative hierarchy.

    Returns: {
        'hyper_pattern': str,          # Pattern at HYPER level
        'macro_narratives': [str]*3,   # MACRO pattern inside each hyper-candle
        'micro_narratives': [[str]*3]*3, # MICRO patterns inside each super-candle
        'sentence': str,               # Human-readable narrative
    }
    """
    bars_per_hyper = super_size * n_supers  # 15
    total = bars_per_hyper * n_hypers       # 45
    start = end_idx - total + 1
    if start < 0:
        return None

    # 1. Detect HYPER pattern
    hyper_df = PatternSignalAdapter.synthesize_hyper_candles(ohlc, end_idx=end_idx)
    if hyper_df is None or len(hyper_df) < 3:
        return None
    hyper_verdict = engine.detect(hyper_df)
    hyper_pattern = hyper_verdict.primary_pattern
    if hyper_pattern == "NONE":
        return None

    # 2. For each hyper-candle, detect its MACRO pattern (3 super-candles inside)
    macro_narratives = []
    micro_narratives = []

    for h in range(n_hypers):
        h_start = start + h * bars_per_hyper
        h_end = h_start + bars_per_hyper  # 15 bars for this hyper-candle

        # Build 3 super-candles from the 15 bars inside this hyper-candle
        super_candles = []
        micro_in_supers = []
        # Select only OHLCV columns to avoid mixed-dtype iloc issues
        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in ohlc.columns]
        ohlc_clean = ohlc[ohlcv_cols]
        for s in range(n_supers):
            s_start = h_start + s * super_size
            s_end = s_start + super_size
            grp = ohlc_clean.iloc[s_start:s_end]
            if len(grp) < super_size:
                super_candles.append(None)
                micro_in_supers.append(["NONE"] * 3)
                continue

            super_candles.append({
                "Open": float(grp.iloc[0]["open"]),
                "High": float(grp["high"].max()),
                "Low": float(grp["low"].min()),
                "Close": float(grp.iloc[-1]["close"]),
                "Volume": float(grp["volume"].sum()),
            })

            # 3. For each super-candle, detect MICRO patterns at the END
            #    (last 3 bars of the super-candle tell the closing narrative)
            micro_end = s_end - 1
            micro_pat = detect_micro_at(engine, ohlc_clean, micro_end)
            micro_in_supers.append(micro_pat)

        # Detect MACRO pattern from the 3 super-candles
        if all(sc is not None for sc in super_candles):
            macro_df = pd.DataFrame(super_candles)
            macro_verdict = engine.detect(macro_df)
            macro_narratives.append(macro_verdict.primary_pattern)
        else:
            macro_narratives.append("NONE")

        micro_narratives.append(micro_in_supers)

    # 4. Build the "sentence"
    macro_str = " → ".join(macro_narratives)
    sentence = f"HYPER[{hyper_pattern}] = [{macro_str}]"

    return {
        "hyper_pattern": hyper_pattern,
        "macro_narratives": macro_narratives,
        "micro_narratives": micro_narratives,
        "sentence": sentence,
    }


def decompose_macro_event(engine, ohlc, end_idx, super_size=5, n_supers=3):
    """Decompose a MACRO event into its MICRO narratives."""
    total = super_size * n_supers
    start = end_idx - total + 1
    if start < 0:
        return None

    super_df = PatternSignalAdapter.synthesize_super_candles(
        ohlc, end_idx=end_idx, group_size=super_size, n_groups=n_supers
    )
    if super_df is None or len(super_df) < 3:
        return None
    super_df.columns = [c.capitalize() for c in super_df.columns]
    macro_verdict = engine.detect(super_df)
    macro_pattern = macro_verdict.primary_pattern
    if macro_pattern == "NONE":
        return None

    # Detect MICRO at the end of each super-candle
    micro_pats = []
    for s in range(n_supers):
        s_end = start + (s + 1) * super_size - 1
        micro_pat = detect_micro_at(engine, ohlc, s_end)
        micro_pats.append(micro_pat)

    micro_str = " → ".join(micro_pats)
    sentence = f"MACRO[{macro_pattern}] = [{micro_str}]"

    return {
        "macro_pattern": macro_pattern,
        "micro_narratives": micro_pats,
        "sentence": sentence,
    }


def main():
    store = TimescaleDataStore()
    engine = PatternRecognitionIntelligence()

    print("=" * 130)
    print(f"{'NESTED PATTERN FORENSICS — FRACTAL DECOMPOSITION':^130}")
    print(f"{'Patterns are words. Super-candles are sentences. Hyper-candles are paragraphs.':^130}")
    print(f"{'Universe: 32 tickers | Execution: Open[T+1] + 10% ATR Slippage':^130}")
    print("=" * 130)

    # ── Collect events with full decomposition ──
    hyper_events = []   # Full HYPER decompositions
    macro_events = []   # Full MACRO decompositions

    for ti, ticker in enumerate(EXTENDED_TICKERS):
        print(f"  [{ti+1}/{len(EXTENDED_TICKERS)}] {ticker}...", flush=True)
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue

        closes = ohlc["close"].values
        opens = ohlc["open"].values
        highs = ohlc["high"].values
        lows = ohlc["low"].values

        for i in range(60, len(ohlc) - 11):
            trend = get_trend_state(closes, i)
            open_next = opens[i+1]
            tr_next = highs[i+1] - lows[i+1]
            slippage = tr_next * 0.10
            exec_price = open_next + slippage
            if exec_price <= 0:
                continue
            ret_10d = (closes[i+10] - exec_price) / exec_price * 100

            # HYPER decomposition
            hyper_decomp = decompose_hyper_event(engine, ohlc, i)
            if hyper_decomp is not None:
                hyper_decomp["trend"] = trend
                hyper_decomp["ret_10d"] = ret_10d
                hyper_decomp["ticker"] = ticker
                hyper_decomp["date"] = ohlc.index[i]
                hyper_events.append(hyper_decomp)

            # MACRO decomposition
            macro_decomp = decompose_macro_event(engine, ohlc, i)
            if macro_decomp is not None:
                macro_decomp["trend"] = trend
                macro_decomp["ret_10d"] = ret_10d
                macro_decomp["ticker"] = ticker
                macro_decomp["date"] = ohlc.index[i]
                macro_events.append(macro_decomp)

    store.close()
    print(f"\n  HYPER events: {len(hyper_events):,} | MACRO events: {len(macro_events):,}")

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS 1: HYPER NARRATIVES — What stories do the paragraphs tell?
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'━' * 130}")
    print(f"  ANALYSIS 1: HYPER NARRATIVE DECOMPOSITION")
    print(f"  Question: When HYPER THREE_BLACK_CROWS fires in MUY_BAJISTA,")
    print(f"  what MACRO patterns live inside each hyper-candle?")
    print(f"{'━' * 130}")

    # Focus on validated setup: HYPER_3BC + MUY_BAJISTA
    target_hypers = [e for e in hyper_events
                     if e["hyper_pattern"] == "THREE_BLACK_CROWS"
                     and e["trend"] == "MUY_BAJISTA"]

    print(f"\n  HYPER THREE_BLACK_CROWS in MUY_BAJISTA: {len(target_hypers)} events")

    # Count narrative signatures
    narrative_stats = defaultdict(lambda: {"rets": [], "count": 0})
    for ev in target_hypers:
        sig = tuple(ev["macro_narratives"])
        narrative_stats[sig]["rets"].append(ev["ret_10d"])
        narrative_stats[sig]["count"] += 1

    print(f"\n  {'Narrative Signature (3 MACRO patterns inside)':<65} | {'N':>4} | {'WR':>6} | {'Avg Ret':>8} | Verdict")
    print(f"  {'-'*65}-+-{'-'*4}-+-{'-'*6}-+-{'-'*8}-+-{'-'*15}")

    for sig, stats in sorted(narrative_stats.items(), key=lambda x: -x[1]["count"]):
        if stats["count"] < 3:
            continue
        arr = np.array(stats["rets"])
        wr = (arr > 0).mean() * 100
        avg = arr.mean()
        sig_str = " → ".join(sig)
        verdict = "🔥 DEEP" if wr > 70 else ("✅ OK" if wr > 55 else "⚠️  WEAK")
        print(f"  {sig_str:<65} | {stats['count']:>4} | {wr:>5.1f}% | {avg:>+7.2f}% | {verdict}")

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS 2: MACRO NARRATIVES — What words compose each sentence?
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'━' * 130}")
    print(f"  ANALYSIS 2: MACRO NARRATIVE DECOMPOSITION — MICRO PATTERNS INSIDE SUPER-CANDLES")
    print(f"  Question: When MACRO BEARISH_MARUBOZU fires, what MICRO patterns close each week?")
    print(f"{'━' * 130}")

    # Focus on: MACRO patterns in MUY_BAJISTA (our validated territory)
    for target_macro_pat in ["BEARISH_MARUBOZU", "HAMMER", "THREE_BLACK_CROWS", "TWEEZER_BOTTOM"]:
        target_macros = [e for e in macro_events
                         if e["macro_pattern"] == target_macro_pat
                         and e["trend"] == "MUY_BAJISTA"]

        if len(target_macros) < 10:
            continue

        print(f"\n  MACRO {target_macro_pat} in MUY_BAJISTA: {len(target_macros)} events")

        micro_stats = defaultdict(lambda: {"rets": [], "count": 0})
        for ev in target_macros:
            sig = tuple(ev["micro_narratives"])
            micro_stats[sig]["rets"].append(ev["ret_10d"])
            micro_stats[sig]["count"] += 1

        print(f"  {'MICRO Narrative (3 closing patterns)':<55} | {'N':>4} | {'WR':>6} | {'Avg':>8} | Verdict")
        print(f"  {'-'*55}-+-{'-'*4}-+-{'-'*6}-+-{'-'*8}-+-{'-'*15}")

        for sig, stats in sorted(micro_stats.items(), key=lambda x: -x[1]["count"]):
            if stats["count"] < 3:
                continue
            arr = np.array(stats["rets"])
            wr = (arr > 0).mean() * 100
            avg = arr.mean()
            sig_str = " → ".join(sig)
            verdict = "🔥 DEEP" if wr > 70 else ("✅ OK" if wr > 55 else "⚠️  WEAK")
            print(f"  {sig_str:<55} | {stats['count']:>4} | {wr:>5.1f}% | {avg:>+7.2f}% | {verdict}")

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS 3: CROSS-LAYER CONJUGATION — Do narratives improve signals?
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'━' * 130}")
    print(f"  ANALYSIS 3: CROSS-LAYER CONJUGATION — NARRATIVE QUALITY vs BASELINE")
    print(f"  Question: Does knowing the internal story improve the signal?")
    print(f"{'━' * 130}")

    # For HYPER 3BC in MUY_BAJISTA, compare:
    # - "All 3 hyper-candles have BEARISH internal MACRO" vs "mixed internals"
    if target_hypers:
        all_bearish_internal = [e for e in target_hypers
                                if all(m in ["BEARISH_MARUBOZU", "BEARISH_ENGULFING",
                                              "THREE_BLACK_CROWS", "DARK_CLOUD_COVER"]
                                       for m in e["macro_narratives"] if m != "NONE")]

        mixed_internal = [e for e in target_hypers
                          if any(m in ["BULLISH_ENGULFING", "HAMMER", "MORNING_STAR",
                                       "BULLISH_MARUBOZU", "THREE_WHITE_SOLDIERS"]
                                 for m in e["macro_narratives"])]

        neutral_internal = [e for e in target_hypers
                            if e not in all_bearish_internal and e not in mixed_internal]

        print(f"\n  HYPER THREE_BLACK_CROWS + MUY_BAJISTA Decomposition:")
        for label, subset in [("ALL BEARISH internals", all_bearish_internal),
                               ("MIXED (bull + bear)", mixed_internal),
                               ("NEUTRAL/NONE internals", neutral_internal),
                               ("FULL SAMPLE (baseline)", target_hypers)]:
            if len(subset) < 3:
                print(f"    {label:<30}: N={len(subset)} (insufficient)")
                continue
            arr = np.array([e["ret_10d"] for e in subset])
            wr = (arr > 0).mean() * 100
            avg = arr.mean()
            print(f"    {label:<30}: N={len(subset):>4} | WR={wr:>5.1f}% | Avg={avg:>+6.2f}% | "
                  f"{'🔥 ENRICHED' if wr > 70 else '✅ BASE' if wr > 60 else '⚠️  DILUTED'}")

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS 4: TEMPORAL NARRATIVE — Beginning vs End of the pattern
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'━' * 130}")
    print(f"  ANALYSIS 4: TEMPORAL NARRATIVE — Does the ENDING of the pattern matter?")
    print(f"  The last MACRO candle inside a HYPER pattern is the 'conclusion' of the story.")
    print(f"{'━' * 130}")

    if target_hypers:
        # Group by the LAST macro narrative (the "conclusion")
        ending_stats = defaultdict(lambda: {"rets": [], "count": 0})
        for ev in target_hypers:
            last_macro = ev["macro_narratives"][-1]  # The conclusion
            ending_stats[last_macro]["rets"].append(ev["ret_10d"])
            ending_stats[last_macro]["count"] += 1

        print(f"\n  HYPER 3BC in MUY_BAJISTA — grouped by LAST hyper-candle's MACRO pattern:")
        print(f"  {'Concluding MACRO Pattern':<30} | {'N':>4} | {'WR':>6} | {'Avg':>8} | Interpretation")
        print(f"  {'-'*30}-+-{'-'*4}-+-{'-'*6}-+-{'-'*8}-+-{'-'*25}")

        for pat, stats in sorted(ending_stats.items(), key=lambda x: -x[1]["count"]):
            if stats["count"] < 3:
                continue
            arr = np.array(stats["rets"])
            wr = (arr > 0).mean() * 100
            avg = arr.mean()
            # Interpretation
            if pat in ["BEARISH_MARUBOZU", "THREE_BLACK_CROWS"]:
                interp = "Pure capitulation end"
            elif pat in ["HAMMER", "TWEEZER_BOTTOM", "MORNING_STAR"]:
                interp = "Buyers emerging at end"
            elif pat in ["DOJI", "SPINNING_TOP"]:
                interp = "Indecision at end"
            else:
                interp = "Mixed"
            print(f"  {pat:<30} | {stats['count']:>4} | {wr:>5.1f}% | {avg:>+7.2f}% | {interp}")

    # Save
    log_dir = _root / "backend/scripts/logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Save hyper narratives
    rows = []
    for ev in hyper_events:
        rows.append({
            "date": ev["date"], "ticker": ev["ticker"], "trend": ev["trend"],
            "hyper_pattern": ev["hyper_pattern"],
            "macro_1": ev["macro_narratives"][0],
            "macro_2": ev["macro_narratives"][1],
            "macro_3": ev["macro_narratives"][2],
            "ret_10d": ev["ret_10d"],
            "sentence": ev["sentence"],
        })
    pd.DataFrame(rows).to_csv(log_dir / "nested_pattern_narratives.csv", index=False)
    print(f"\n  Saved to: {log_dir / 'nested_pattern_narratives.csv'}")


if __name__ == "__main__":
    main()
