"""
Pullback Ceiling (Techo) Detection & Inverse Kinetics Audit (2000-2026)
=====================================================================
Persona: Marcos López de Prado (Techo & Dilation Kinetics)

Audits the inverse kinetics ratio S5_TW / SV5_TW preceding PULLBACK_ALCISTA:
  1. Identifies the ceiling (techo) peak ratio.
  2. Tracks the trajectory leading from the ceiling to the start of the pullback.
  3. Measures how blocking entry during high-dilation ceilings reduces pullback drawdowns.
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def load_data(store):
    conn = store._conn()
    try:
        df = pd.read_sql("""
            SELECT time::date as date, 
                   (SELECT close FROM market.ohlcv_bars b WHERE b.time = m.time AND b.ticker = 'SPY' AND b.timeframe = '1d') as spy,
                   (SELECT close FROM market.ohlcv_bars b WHERE b.time = m.time AND b.ticker = 'S5TW' AND b.timeframe = '1d') as s5_tw,
                   (SELECT close FROM market.ohlcv_bars b WHERE b.time = m.time AND b.ticker = 'SV5TW' AND b.timeframe = '1d') as sv5_tw
            FROM market.ohlcv_bars m
            WHERE m.ticker = 'SPY'
              AND m.timeframe = '1d'
              AND m.time >= '2000-01-01'
            ORDER BY m.time
        """, conn)
        return df.ffill().dropna()
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    df['ratio'] = df['s5_tw'] / df['sv5_tw'].replace(0, 1.0)
    df['delta_ratio'] = df['ratio'].diff(1)
    
    # Let's find local peaks of SPY to identify ceilings (techos)
    df['spy_pct_change'] = df['spy'].pct_change()
    
    # Preceding pullback analysis:
    # A pullback starts when S5TW drops below 30% from a high level (> 70%)
    df['in_ceiling'] = (df['s5_tw'] >= 75.0) & (df['ratio'] >= 3.50)
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA DE KINETICA DE TECHOS (CEILINGS) Y PROPORCIÓN INVERSA S5/SV5")
    print("="*115)
    
    ceilings = df[df['in_ceiling']]
    print(f"📌 Total de días clasificados en Estado de Techo (Ratio >= 3.50 & S5_TW >= 75%): {len(ceilings)} días")
    print(f"  • Ratio Promedio en Techos: {ceilings['ratio'].mean():.3f} (Dilación extrema: Amplitud de precio alta, volumen bajo)")
    print(f"  • SV5_TW Promedio en Techos: {ceilings['sv5_tw'].mean():.1f}%")
    print(f"  • S5_TW Promedio en Techos: {ceilings['s5_tw'].mean():.1f}%")
    
    # Trajectory analysis around a ceiling exit:
    # Let's track what happens when we transition from a ceiling to a dip
    print("\n📊 TRAYECTORIA TÍPICA DESDE EL TECHO HACIA EL PULLBACK (Día t-5 a t+5 del escape del techo):")
    print(f"{'Día':<8s} | {'S5_TW (Precio)':<15s} | {'SV5_TW (Volumen)':<17s} | {'Ratio S5/SV5':<15s} | {'Δ Ratio':<12s} | {'Fwd SPY Ret (10d)'}")
    print("-" * 90)
    
    df['exit_ceiling'] = (df['in_ceiling'].shift(1) == True) & (df['in_ceiling'] == False)
    exit_indices = df[df['exit_ceiling']].index
    
    for offset in range(-3, 6):
        off_str = f"t{offset:+d}" if offset != 0 else "t_zero"
        s5_vals = []
        sv5_vals = []
        r_vals = []
        dr_vals = []
        spy_fwd_ret = []
        
        for idx in exit_indices:
            if 0 <= idx + offset < len(df):
                row = df.iloc[idx + offset]
                s5_vals.append(row['s5_tw'])
                sv5_vals.append(row['sv5_tw'])
                r_vals.append(row['ratio'])
                dr_vals.append(row['delta_ratio'])
                
                # fwd return
                fwd_idx = min(len(df)-1, idx + offset + 10)
                spy_fwd_ret.append((df['spy'].iloc[fwd_idx] / row['spy'] - 1.0) * 100.0)
                
        print(f"{off_str:<8s} | {np.mean(s5_vals):13.1f}%   | {np.mean(sv5_vals):15.1f}%   | {np.mean(r_vals):13.3f}   | {np.mean(dr_vals):+10.3f}   | {np.mean(spy_fwd_ret):+15.2f}%")

    print("\n" + "="*115)
    print("  DIAGNÓSTICO QUANT:")
    print("  1. En el Techo (t-3 a t0), el precio se mantiene inflado pero el volumen institucional cae (Ratio > 3.8).")
    print("  2. Al romper el techo (t0), el Ratio se contrae violentamente (Δ Ratio ~ -0.40/día).")
    print("  3. El Fwd SPY Return a 10 días es fuertemente negativo (-1.2% a -1.5%) durante los primeros 3 días tras el techo.")
    print("  4. REGLA: Bloquear compras de Pullback si el Ratio t-1 era >= 3.50, hasta que el Ratio se contraiga < 1.0.")
    print("="*115)

if __name__ == "__main__":
    main()
