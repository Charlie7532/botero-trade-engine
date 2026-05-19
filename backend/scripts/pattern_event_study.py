"""
pattern_event_study.py — Forensic Event Study for Candlestick Patterns
======================================================================
Evaluates the raw statistical predictive power of the PatternRecognitionIntelligence
engine without any trading strategy logic, execution delays, or stop-losses.

For every pattern detected (both at the Micro/Daily and Macro/Supercandle layer),
it computes the exact forward returns at T+5, T+10, and T+20 days.

This reveals the "naked truth" of each pattern: which ones actually have a
statistical edge and are worth integrating into the production Gate.
"""
import sys
import logging
import argparse
import pandas as pd
import numpy as np
from scipy.stats import linregress
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PatternForensics")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.pattern_recognition.application.use_cases.detect_patterns import PatternRecognitionIntelligence
from backend.modules.simulation.infrastructure.signal_adapters import PatternSignalAdapter

# Full 30-ticker Quality Universe
from backend.scripts.calibrate_passports import QUALITY_TICKERS

OOS_TICKERS = ["TSLA", "NFLX", "UBER"]

def get_trend_state(closes: np.ndarray, current_idx: int, lookback: int = 60) -> str:
    """Calculates the 60-day linear regression slope and classifies the trend."""
    y = closes[current_idx-lookback:current_idx]
    if len(y) < lookback or y[0] <= 0:
        return "HORIZONTAL"
        
    x = np.arange(lookback)
    y_norm = y / y[0]  # Normalize to get comparable percentage drift
    slope, _, _, _, _ = linregress(x, y_norm)
    
    # slope represents the average daily percentage change of the regression line
    if slope > 0.0020:     # > 0.20% daily drift (~50% annualized)
        return "MUY_ALCISTA"
    elif slope > 0.0005:   # > 0.05% daily drift (~12% annualized)
        return "ALCISTA"
    elif slope > -0.0005:  # Flat / Ranging
        return "HORIZONTAL"
    elif slope > -0.0020:  # < -0.05% daily drift
        return "BAJISTA"
    else:                  # < -0.20% daily drift
        return "MUY_BAJISTA"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oos", action="store_true", help="Run on Out-Of-Sample tickers")
    args = parser.parse_args()
    
    TEST_TICKERS = OOS_TICKERS if args.oos else QUALITY_TICKERS
    
    store = TimescaleDataStore()
    engine = PatternRecognitionIntelligence()
    
    events = []
    
    logger.info("=" * 80)
    mode = "OUT-OF-SAMPLE VALIDATION" if args.oos else "IN-SAMPLE CALIBRATION"
    logger.info(f"PATTERN FORENSIC EVENT STUDY ({mode})")
    logger.info(f"Universe: {len(TEST_TICKERS)} tickers")
    logger.info("=" * 80)

    for ticker in TEST_TICKERS:
        logger.info(f"Processing {ticker}...")
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue
            
        # Normalize columns for the engine
        df = ohlc.copy()
        df.columns = [c.capitalize() for c in df.columns]
        
        closes = df['Close'].values
        
        # Iterate through history
        # Start at 60 to allow 60 bars for regression + 20 days forward return
        for i in range(60, len(df) - 20):
            # ── TREND CLASSIFICATION (T=0) ──
            trend = get_trend_state(closes, i, lookback=60)
            
            # ── MICRO LAYER (Last 3 real bars) ──
            micro_window = df.iloc[i-2:i+1]
            micro_verdict = engine.detect(micro_window)
            micro_pattern = micro_verdict.primary_pattern
            
            # ── MACRO LAYER (3 Super-candles = 15 bars ending at i) ──
            # Re-using the adapter's synthetic generator with original lowercase df
            super_df = PatternSignalAdapter.synthesize_super_candles(
                ohlc, end_idx=i, group_size=5, n_groups=3
            )
            macro_pattern = "NONE"
            if super_df is not None and len(super_df) >= 3:
                # Engine needs Title Case columns
                super_df.columns = [c.capitalize() for c in super_df.columns]
                macro_verdict = engine.detect(super_df)
                macro_pattern = macro_verdict.primary_pattern
            
            # ── EXECUTION MODELING (1-bar delay + slippage) ──
            # Signal generated at Close[i]. We execute at Open[i+1].
            # Slippage is modeled as 10% of the True Range of the execution day.
            open_next = df['Open'].values[i+1]
            tr_next = df['High'].values[i+1] - df['Low'].values[i+1]
            slippage = tr_next * 0.10
            
            exec_price_bull = open_next + slippage  # Buying means worse (higher) price
            exec_price_bear = open_next - slippage  # Shorting means worse (lower) price
            
            if open_next <= 0:
                continue
                
            if micro_pattern != "NONE":
                exec_price = exec_price_bull if micro_verdict.sentiment == "BULLISH" else exec_price_bear
                ret_3d = (closes[i+3] - exec_price) / exec_price * 100
                ret_5d = (closes[i+5] - exec_price) / exec_price * 100
                ret_10d = (closes[i+10] - exec_price) / exec_price * 100
                
                events.append({
                    "ticker": ticker,
                    "date": df.index[i].strftime("%Y-%m-%d"),
                    "trend": trend,
                    "layer": "MICRO (Daily)",
                    "pattern": micro_pattern,
                    "sentiment": micro_verdict.sentiment,
                    "entry_price": round(exec_price, 2),
                    "price_3d": round(closes[i+3], 2),
                    "ret_3d": round(ret_3d, 2),
                    "price_5d": round(closes[i+5], 2),
                    "ret_5d": round(ret_5d, 2),
                    "price_10d": round(closes[i+10], 2),
                    "ret_10d": round(ret_10d, 2),
                })
                
            if macro_pattern != "NONE":
                exec_price = exec_price_bull if macro_verdict.sentiment == "BULLISH" else exec_price_bear
                ret_3d = (closes[i+3] - exec_price) / exec_price * 100
                ret_5d = (closes[i+5] - exec_price) / exec_price * 100
                ret_10d = (closes[i+10] - exec_price) / exec_price * 100
                
                events.append({
                    "ticker": ticker,
                    "date": df.index[i].strftime("%Y-%m-%d"),
                    "trend": trend,
                    "layer": "MACRO (Weekly)",
                    "pattern": macro_pattern,
                    "sentiment": macro_verdict.sentiment,
                    "entry_price": round(exec_price, 2),
                    "price_3d": round(closes[i+3], 2),
                    "ret_3d": round(ret_3d, 2),
                    "price_5d": round(closes[i+5], 2),
                    "ret_5d": round(ret_5d, 2),
                    "price_10d": round(closes[i+10], 2),
                    "ret_10d": round(ret_10d, 2),
                })
                
            if micro_pattern != "NONE" and macro_pattern != "NONE":
                if micro_verdict.sentiment == macro_verdict.sentiment:
                    exec_price = exec_price_bull if micro_verdict.sentiment == "BULLISH" else exec_price_bear
                    ret_3d = (closes[i+3] - exec_price) / exec_price * 100
                    ret_5d = (closes[i+5] - exec_price) / exec_price * 100
                    ret_10d = (closes[i+10] - exec_price) / exec_price * 100
                    
                    events.append({
                        "ticker": ticker,
                        "date": df.index[i].strftime("%Y-%m-%d"),
                        "trend": trend,
                        "layer": "CONJUGATION",
                        "pattern": f"M[{macro_pattern}] + m[{micro_pattern}]",
                        "sentiment": micro_verdict.sentiment,
                        "entry_price": round(exec_price, 2),
                        "price_3d": round(closes[i+3], 2),
                        "ret_3d": round(ret_3d, 2),
                        "price_5d": round(closes[i+5], 2),
                        "ret_5d": round(ret_5d, 2),
                        "price_10d": round(closes[i+10], 2),
                        "ret_10d": round(ret_10d, 2),
                    })

    store.close()
    
    if not events:
        logger.error("No events found!")
        return 1
        
    events_df = pd.DataFrame(events)
    
    # Save raw forensic log to CSV
    log_dir = Path(_root / "backend/scripts/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    csv_path = log_dir / "pattern_forensics_log.csv"
    events_df.to_csv(csv_path, index=False)
    logger.info(f"Saved raw forensic event log to: {csv_path}")
    
    # ── AGGREGATION & REPORTING ──
    print("\n" + "=" * 110)
    print(f"{'CONDITIONAL PROBABILITY EDGE (PATTERN + REGRESSION TREND)':^110}")
    print("=" * 110)
    
    for layer in ["MICRO (Daily)", "MACRO (Weekly)", "CONJUGATION"]:
        print(f"\n>> {layer.upper()} LAYER")
        print("-" * 110)
        print(f"{'Pattern':<40} | {'Trend':<12} | {'Sent':<4} | {'N':>4} | {'WinR 3d':>8} {'Avg 3d':>7} | {'WinR 5d':>8} {'Avg 5d':>7} | {'WinR 10d':>8} {'Avg 10d':>7}")
        print("-" * 110)
        
        layer_df = events_df[events_df["layer"] == layer]
        
        # Group by pattern AND trend
        grouped = layer_df.groupby(["pattern", "trend"])
        
        results = []
        for (pattern, trend), group in grouped:
            sent = group.iloc[0]["sentiment"][:4]  # BULL or BEAR
            n = len(group)
            
            # Require minimum sample size to avoid statistical noise
            # Reduce to 5 for CONJUGATION since it's rare
            min_n = 5 if layer == "CONJUGATION" else 15
            if n < min_n:
                continue
                
            is_bull = sent == "BULL"
            
            wr_3d = (group["ret_3d"] > 0).mean() * 100 if is_bull else (group["ret_3d"] < 0).mean() * 100
            avg_3d = group["ret_3d"].mean()
            
            wr_5d = (group["ret_5d"] > 0).mean() * 100 if is_bull else (group["ret_5d"] < 0).mean() * 100
            avg_5d = group["ret_5d"].mean()
            
            wr_10d = (group["ret_10d"] > 0).mean() * 100 if is_bull else (group["ret_10d"] < 0).mean() * 100
            avg_10d = group["ret_10d"].mean()
            
            results.append({
                "pattern": pattern, "trend": trend, "sent": sent, "n": n,
                "wr_3d": wr_3d, "avg_3d": avg_3d,
                "wr_5d": wr_5d, "avg_5d": avg_5d,
                "wr_10d": wr_10d, "avg_10d": avg_10d,
            })
            
        # Sort by Win Rate 10d descending
        results.sort(key=lambda x: x["wr_10d"], reverse=True)
        
        for r in results:
            print(f"{r['pattern']:<40} | {r['trend']:<12} | {r['sent']:<4} | {r['n']:>4} | "
                  f"{r['wr_3d']:>7.1f}% {r['avg_3d']:>6.2f}% | "
                  f"{r['wr_5d']:>7.1f}% {r['avg_5d']:>6.2f}% | "
                  f"{r['wr_10d']:>7.1f}% {r['avg_10d']:>6.2f}%")

    print("=" * 90)
    print("NOTE: 'WinR' (Win Rate) is directionally adjusted.")
    print("      For BULLISH patterns, WinR = % of trades > 0.")
    print("      For BEARISH patterns, WinR = % of trades < 0.")
    print("      'Avg' is the absolute unadjusted average return in %.")
    print("=" * 90)

if __name__ == "__main__":
    sys.exit(main())
