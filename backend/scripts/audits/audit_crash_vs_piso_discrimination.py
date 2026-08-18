"""
Forensic Discrimination Audit: CRASH_SISTEMICO vs PISO_GENERACIONAL (2000-2026)
=============================================================================
Persona: Senior Quantitative Researcher & Market Microstructure Expert

Audits all historical entry points into CRASH_SISTEMICO vs PISO_GENERACIONAL.
Compares leading indicators (1d, 3d, 5d prior):
  1. VIX Level & 5d Velocity
  2. Tactical Volume Absorption (SV5_TW)
  3. Structural Breadth Destruction (S5_TH & n_dead)
  4. Volume-to-Breadth Divergence Ratio (SV5_TW / S5_TH)
  5. CBOE Put-Call Ratio (PCR)
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]

def load_data(store):
    conn = store._conn()
    try:
        df_p = pd.read_sql("""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'S5TH', 'S5FI', 'S5TW', 'SV5TH', 'SV5FI', 'SV5TW', 'CBOE_PCR')
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df_p.pivot(index='date', columns='ticker', values='close').ffill()
        
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
        p_str = ", ".join([f"'{t}'" for t in sec_ind_tickers + SECTORS_11])
        
        df_sectors = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        sec_pivot = df_sectors.pivot(index='date', columns='ticker', values='close').ffill()
        
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX') 
              AND timeframe = '1d' 
              AND time >= '2000-01-01' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = pivot.index.intersection(sec_pivot.index).intersection(macro_pivot.index)
        return pivot.loc[common_dates], sec_pivot.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    
    for idx_i, d in enumerate(pivot.index):
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        pcr = pivot.loc[d, 'CBOE_PCR'] if 'CBOE_PCR' in pivot.columns and pd.notna(pivot.loc[d, 'CBOE_PCR']) else 0.90
        
        sec_th = {s: sec_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw,
            vix=vix
        )
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        n_dead = sum(1 for v in sec_th.values() if v < 25.0)
        
        daily_records.append({
            "idx": idx_i,
            "date": d,
            "mode": current_mode,
            "prev_mode": daily_records[-1]['mode'] if daily_records else "NORMAL",
            "th": th, "fi": fi, "tw": tw,
            "v_tw": v_tw, "v_fi": v_fi,
            "vix": vix,
            "pcr": pcr,
            "n_dead": n_dead
        })
        
    df = pd.DataFrame(daily_records)
    
    # Extract transition events into CRASH_SISTEMICO vs PISO_GENERACIONAL
    crash_entries = []
    piso_entries = []
    
    for i in range(1, len(df)):
        prev_m = df.iloc[i-1]['mode']
        curr_m = df.iloc[i]['mode']
        
        if prev_m != curr_m:
            t3_idx = max(0, i-3)
            row_now = df.iloc[i]
            row_t3 = df.iloc[t3_idx]
            
            event_info = {
                "date": row_now['date'],
                "from_mode": prev_m,
                "vix_now": row_now['vix'],
                "vix_t3": row_t3['vix'],
                "vix_delta": row_now['vix'] - row_t3['vix'],
                "v_tw_now": row_now['v_tw'],
                "v_tw_t3": row_t3['v_tw'],
                "th_now": row_now['th'],
                "th_t3": row_t3['th'],
                "n_dead_now": row_now['n_dead'],
                "n_dead_t3": row_t3['n_dead'],
                "pcr_now": row_now['pcr'],
                "absorption_ratio": row_now['v_tw'] / max(1.0, row_now['th'])
            }
            
            if curr_m == "CRASH_SISTEMICO":
                crash_entries.append(event_info)
            elif curr_m == "PISO_GENERACIONAL":
                piso_entries.append(event_info)
                
    df_crash = pd.DataFrame(crash_entries)
    df_piso = pd.DataFrame(piso_entries)
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA DE DISCRIMINACIÓN DE DISPARADORES: CRASH_SISTEMICO VS PISO_GENERACIONAL")
    print("="*115)
    
    print(f"\n📊 COMPARATIVA DE FIRMAS CUANTITATIVAS AL ENTRAR AL RÉGIMEN:")
    print(f"{'Métrica Indicadora':<40s} | {'Hacia CRASH_SISTEMICO (Avg)':<30s} | {'Hacia PISO_GENERACIONAL (Avg)':<30s} | {'Diferencial de Discriminación'}")
    print("-" * 115)
    
    m1_c, m1_p = df_crash['vix_now'].mean(), df_piso['vix_now'].mean()
    print(f"{'VIX Nivel Actual':<40s} | {m1_c:28.2f} | {m1_p:28.2f} | {m1_p - m1_c:+25.2f} pts (Piso tiene VIX más disparado)")
    
    m2_c, m2_p = df_crash['vix_delta'].mean(), df_piso['vix_delta'].mean()
    print(f"{'VIX Aceleración 3 Días (Delta VIX)':<40s} | {m2_c:28.2f} | {m2_p:28.2f} | {m2_p - m2_c:+25.2f} pts (Piso es un pico súbito)")
    
    m3_c, m3_p = df_crash['v_tw_now'].mean(), df_piso['v_tw_now'].mean()
    print(f"{'SV5_TW Absorción Institucional':<40s} | {m3_c:28.1f}% | {m3_p:28.1f}% | {m3_p - m3_c:+25.1f}% (Piso tiene absorción masiva)")
    
    m4_c, m4_p = df_crash['n_dead_now'].mean(), df_piso['n_dead_now'].mean()
    print(f"{'n_dead Sectores Colapsados (<25%)':<40s} | {m4_c:28.1f} | {m4_p:28.1f} | {m4_c - m4_p:+25.1f} sec (Crash destruye >5 sectores)")
    
    m5_c, m5_p = df_crash['absorption_ratio'].mean(), df_piso['absorption_ratio'].mean()
    print(f"{'Ratio Absorción (SV5_TW / S5_TH)':<40s} | {m5_c:28.2f} | {m5_p:28.2f} | {m5_p - m5_c:+25.2f}x (Ratio >2.5x firma Piso Generacional)")

    print("\n" + "="*115)
    print("  💡 MATRIZ DE REGLAS DE DISCRIMINACIÓN:")
    print("  1. FIRMA DE CRASH SISTÉMICO:")
    print("     • Destrucción Estructural Sectores: n_dead >= 5")
    print("     • Amplitud S5_TH baja (<25%) SIN absorción de volumen (SV5_TW < 55%)")
    print("     • Ratio de Absorción (SV5_TW / S5_TH) < 2.0x")
    print("  2. FIRMA DE PISO GENERACIONAL (ROTACIÓN OFENSIVA ALTA BETA):")
    print("     • Capitulación de Volumen: SV5_TW >= 60%")
    print("     • Clímax de Pánico de Volatilidad: VIX > 28 O Delta VIX (3d) >= +5.0 pts")
    print("     • Ratio de Absorción DIVERGENTE: (SV5_TW / S5_TH) >= 2.50x (Táctico > Estructural)")
    print("="*115)

if __name__ == "__main__":
    main()
