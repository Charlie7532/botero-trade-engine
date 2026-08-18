import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
vix = store.load_bars("VIX","1d")["close"].copy(); spy = store.load_bars("SPY","1d")["close"].copy()
vix.index = pd.to_datetime(vix.index); spy.index = pd.to_datetime(spy.index)
store.close()

vix_vel = vix.diff(3)

# Find VIX extreme peaks: VIX >= 30, then find the CONFIRMATION BAR
# Confirmation: first bar where D2 flips negative AND VIX is below the local peak

results = []
vix_vals = vix.values; vix_dates = vix.index; vel_vals = vix_vel.values

for i in range(20, len(vix_vals)-20):
    if vix_vals[i] >= 30:
        # This is an extreme bar. Look for the PEAK within ±10 bars
        window = vix_vals[max(0,i-10):i+10]
        peak_val = max(window)
        peak_idx = i-10 + np.argmax(window)
        
        # Look for confirmation bar AFTER the peak
        for j in range(peak_idx+1, min(peak_idx+10, len(vix_vals))):
            if vel_vals[j] < 0 and vix_vals[j] < peak_val * 0.95:
                # Confirmed! Now measure:
                # 1. Does VIX revisit the peak in next 20 bars?
                future = vix_vals[j:j+20]
                revisit = any(future >= peak_val * 0.98)
                
                # 2. SPY return from confirmation bar
                if j+5 < len(spy.values):
                    spy_ret_5d = spy.values[j+5] / spy.values[j] - 1
                else:
                    spy_ret_5d = np.nan
                if j+20 < len(spy.values):
                    spy_ret_20d = spy.values[j+20] / spy.values[j] - 1
                else:
                    spy_ret_20d = np.nan
                
                # 3. Cascade-like: does the VIX drop continue for 5+ days?
                vix_cont = vix_vals[j:j+5].mean() < peak_val * 0.9
                
                results.append({
                    "peak_val": peak_val,
                    "conf_val": vix_vals[j],
                    "conf_day": str(vix_dates[j])[:10],
                    "days_to_confirm": j - peak_idx,
                    "revisit": revisit,
                    "spy_5d": spy_ret_5d,
                    "spy_20d": spy_ret_20d,
                    "vix_continues_down": vix_cont
                })
                break

df = pd.DataFrame(results)
if len(df) == 0: 
    print("No confirmations found. Adjusting threshold...")
else:
    print(f"═══ BARRAS DE CONFIRMACIÓN — VIX ≥ 30 (N={len(df)}) ═══\n")
    print(f"  Días hasta confirmación: media={df['days_to_confirm'].mean():.1f}, mediana={df['days_to_confirm'].median():.0f}")
    print(f"  ¿Revisitó el pico?  {df['revisit'].mean()*100:.0f}% de las veces")
    print(f"  ¿VIX siguió bajando (>10%)? {df['vix_continues_down'].mean()*100:.0f}%")
    print(f"  SPY retorno 5d desde confirmación:  media={df['spy_5d'].mean()*100:+.2f}%")
    print(f"  SPY retorno 20d desde confirmación: media={df['spy_20d'].mean()*100:+.2f}%")
    print(f"\n  ── Split by revisit ──")
    for label, mask in [("NO revisitó (V-bottom)", ~df["revisit"]), ("SÍ revisitó (W-bottom)", df["revisit"])]:
        if mask.sum() > 0:
            print(f"  {label}: N={mask.sum()}, SPY 5d={df.loc[mask,'spy_5d'].mean()*100:+.2f}%, SPY 20d={df.loc[mask,'spy_20d'].mean()*100:+.2f}%")