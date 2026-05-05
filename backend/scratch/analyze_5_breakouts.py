"""
TRADE FORENSICS — Institutional Breakout Analysis
Using QuantFeatureEngineer and 1h DB data for AMD, MU, MSTR, IONQ, AFRM.
"""
import logging
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
import pandas as pd
from datetime import date
from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.application.use_cases.engineer_features import QuantFeatureEngineer

logging.basicConfig(level=logging.WARNING)

def analyze_institutional_breakout(ticker: str, store: TimescaleDataStore):
    print(f"\n{'='*80}")
    print(f"  FORENSICS (1h DB Data): {ticker}")
    print(f"{'='*80}")

    df = store.load_bars(ticker, "1h")
    if df.empty or len(df) < 500:
        print("  INSUFFICIENT DATA IN DB")
        return

    # Convert index to be timezone-naive if needed, or ensure it's sorted
    df = df.sort_index()

    # Apply QuantFeatureEngineer
    engineer = QuantFeatureEngineer(data=df, timeframe_minutes=60)
    # We won't use benchmark or macro for this quick scan to keep it isolated
    df_features = engineer.process_all_features()

    if df_features.empty:
        print("  Feature engineering returned empty DataFrame.")
        return

    # To find the breakout, let's look at 5-day (approx 35 hours) returns
    # We calculate rolling 35-bar return
    df_features["ret_35h"] = df_features["close"].pct_change(35) * 100
    
    # Look at the last 3 months (approx 500 hours)
    recent = df_features.tail(500)
    
    # Find the largest 35-hour return
    if recent["ret_35h"].max() < 10:
        print("  No major breakout (>10%) found in the last 3 months of hourly data.")
        return
        
    breakout_candidates = recent[recent["ret_35h"] > 10]
    breakout_start_idx = breakout_candidates.index[0]
    breakout_start_loc = df_features.index.get_loc(breakout_start_idx)
    
    # The trigger is ~35 bars before the peak
    trigger_loc = max(0, breakout_start_loc - 35)
    trigger_date = df_features.index[trigger_loc]
    trigger_row = df_features.iloc[trigger_loc]
    
    current = df_features["close"].iloc[-1]
    trigger_price = trigger_row["close"]
    move_pct = (current - trigger_price) / trigger_price * 100

    print(f"\n  📅 Breakout trigger date: {trigger_date}")
    print(f"  💰 Trigger price: ${trigger_price:.2f} → Current: ${current:.2f} (+{move_pct:.1f}%)")

    print(f"\n  {'─'*60}")
    print(f"  INSTITUTIONAL FEATURES AT TRIGGER (1h resolution)")
    print(f"  {'─'*60}")

    # 1. Microstructure
    vwap_z = trigger_row.get('MS_VWAP_ZScore', 0)
    orderflow_z = trigger_row.get('MS_OrderFlow_ZScore', 0)
    print(f"  🔹 VWAP Z-Score:        {vwap_z:>6.2f}  (>0 = precio soportado por VWAP)")
    print(f"  🔹 Order Flow Z-Score:  {orderflow_z:>6.2f}  (>1 = presión compradora agresiva)")
    
    # 2. Volume Flow
    relvol_z = trigger_row.get('VF_RelVolume_ZScore', 0)
    volaccel_z = trigger_row.get('VF_VolAccel_ZScore', 0)
    cumdelta_z = trigger_row.get('VF_CumDelta_ZScore', 0)
    print(f"  🔹 Rel Volume Z-Score:  {relvol_z:>6.2f}  (>1 = actividad institucional anómala)")
    print(f"  🔹 Vol Accel Z-Score:   {volaccel_z:>6.2f}  (>0 = volumen acelerando)")
    print(f"  🔹 Cum Delta Z-Score:   {cumdelta_z:>6.2f}  (>1 = acumulación constante)")
    
    # 3. Temporal (Volatility Squeeze)
    vol_ratio = trigger_row.get('TS_VolRatio', 1)
    print(f"  🔹 Volatility Ratio:    {vol_ratio:>6.2f}  (<1 = SQUEEZE/VCP, >1 = expansión)")

    # Score synthesis
    score = 0
    if vwap_z > 0: score += 1
    if orderflow_z > 0.5: score += 1
    if relvol_z > 1.0: score += 1
    if volaccel_z > 0: score += 1
    if cumdelta_z > 1.0: score += 1
    if vol_ratio < 1.0: score += 1

    print(f"\n  🎯 INSTITUTIONAL T-SCORE: {score}/6")
    if score >= 4:
        print("  ✅ VERDICT: Strong institutional footprint DETECTED before breakout.")
    elif score >= 2:
        print("  ⚠️ VERDICT: Partial footprint. Mixed signals.")
    else:
        print("  ❌ VERDICT: No clear institutional accumulation detected on 1h timeframe.")


def main():
    tickers = ["AMD", "MU", "MSTR", "IONQ", "AFRM"]
    store = TimescaleDataStore()
    
    for t in tickers:
        analyze_institutional_breakout(t, store)

if __name__ == "__main__":
    main()
