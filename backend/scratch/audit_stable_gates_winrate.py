#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import text

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from unified_pretrainer_v2 import (
    load_feature_lake,
    label_swing_exit,
    label_short_entry,
    label_bounce_height,
    label_trend_reversal
)

def main():
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    
    print("Loading Feature Lake and OHLCV cache...")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    print(f"Loaded {len(df):,d} feature rows.")
    
    # 1. Compute labels
    print("\nComputing labels for the 4 Stable Gates...")
    
    # We will slice a copy of df to ensure no modifications warnings
    df_work = df.copy()
    
    print("  Computing label_swing_exit...")
    y_swing = label_swing_exit(df_work, ohlcv_cache)
    df_work['y_swing'] = y_swing
    
    print("  Computing label_short_entry...")
    y_short = label_short_entry(df_work, ohlcv_cache)
    df_work['y_short'] = y_short
    
    print("  Computing label_bounce_height...")
    y_bounce = label_bounce_height(df_work, ohlcv_cache)
    df_work['y_bounce'] = y_bounce
    
    print("  Computing label_trend_reversal...")
    y_reversal = label_trend_reversal(df_work, ohlcv_cache, profiles)
    df_work['y_reversal'] = y_reversal
    
    # 2. Analyze overall win rates vs trend-classified win rates
    # Trend classification:
    # Bull Trend = tide_slope > 0
    # Bear Trend = tide_slope < 0
    
    print("\n" + "=" * 95)
    print("  STABLE GATES WIN RATES & TREND COHERENCE AUDIT")
    print("=" * 95)
    print(f"{'Gate / Label':30s} │ {'Overall Hit %':>13s} │ {'Bull (Tide > 0) %':>17s} │ {'Bear (Tide < 0) %':>17s} │ {'Improvement'}")
    print("-" * 95)
    
    for col, name, favorable_trend in [
        ('y_swing', 'Swing Exit (Exit Long)', 'Bear'), # Swing exits should be highly active/favorable in Bear trend
        ('y_short', 'Short Entry (Go Short)', 'Bear'), # Shorts are favorable in Bear trend
        ('y_bounce', 'Bounce Height (Bounce Size)', 'Bull'), # Bounces are highly favorable/larger in Bull trend
        ('y_reversal', 'Trend Reversal (Major Turn)', 'Bull') # Reversals (Bullish turns) are favorable in Bull trend
    ]:
        vals = df_work[col].dropna()
        if len(vals) == 0:
            print(f"  {name:30s} │ {'—':>13s} │ {'—':>17s} │ {'—':>17s} │ No data")
            continue
            
        overall_pct = (vals == 1).mean() * 100
        
        # Bull subset
        bull_mask = df_work['tide_slope'] > 0
        bull_vals = df_work[bull_mask][col].dropna()
        bull_pct = (bull_vals == 1).mean() * 100 if len(bull_vals) > 0 else 0
        
        # Bear subset
        bear_mask = df_work['tide_slope'] < 0
        bear_vals = df_work[bear_mask][col].dropna()
        bear_pct = (bear_vals == 1).mean() * 100 if len(bear_vals) > 0 else 0
        
        # Calculate Delta and Coherence Verdict
        fav_pct = bull_pct if favorable_trend == 'Bull' else bear_pct
        unfav_pct = bear_pct if favorable_trend == 'Bull' else bull_pct
        delta = fav_pct - unfav_pct
        
        verdict = f"🟢 Favorable in {favorable_trend} (Δ = +{delta:.1f}%)" if delta > 0 else f"🔴 Unfavorable (Δ = {delta:.1f}%)"
        
        print(f"  {name:30s} │ {overall_pct:>12.2f}% │ {bull_pct:>16.2f}% │ {bear_pct:>16.2f}% │ {verdict}")
        
    store.close()
    ps.close()

if __name__ == "__main__":
    main()
