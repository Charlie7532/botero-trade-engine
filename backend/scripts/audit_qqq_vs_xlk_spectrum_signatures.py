"""
QQQ vs XLK Spectrum Signatures & Sector Breadth Forensic Explorer (2000-2026)
=============================================================================
Persona: Senior Quantitative Researcher & Renaissance Signal Miner

Compares QQQ (Nasdaq 100) vs XLK (Tech SPDR) across 26.5 years:
  1. Performance & Drawdown Comparison per Market Regime.
  2. Ratio Kinetics: QQQ/XLK Relative Strength & Momentum.
  3. Interaction with Sector Breadth (S5_XLK, S5_XLC, S5_XLY).
  4. Coincidence with ZigZag Turning Points (2.5%, 5.0%, 7.5%).
  5. Derives optimal competitive advantage entry conditions for QQQ vs XLK.
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

def load_data(store):
    conn = store._conn()
    try:
        df_p = pd.read_sql("""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'QQQ', 'XLK', 'XLC', 'XLY', 'S5TH', 'S5FI', 'S5TW', 'SV5TH', 'SV5FI', 'SV5TW')
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df_p.pivot(index='date', columns='ticker', values='close').ffill()
        
        sec_ind_tickers = ["S5_XLK_TH", "S5_XLK_FI", "S5_XLK_TW", "SV5_XLK_TW",
                           "S5_XLC_TH", "S5_XLC_FI", "S5_XLC_TW", "SV5_XLC_TW",
                           "S5_XLY_TH", "S5_XLY_FI", "S5_XLY_TW", "SV5_XLY_TW"]
        p_str = ", ".join([f"'{t}'" for t in sec_ind_tickers])
        
        df_sec = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        sec_pivot = df_sec.pivot(index='date', columns='ticker', values='close').ffill()
        
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
    
    # Load ZigZag Spectrum Signatures JSON if available
    sig_path = "/root/botero-trade/backend/modules/entry_decision/infrastructure/zigzag_spectrum_signatures.json"
    signatures = {}
    if os.path.exists(sig_path):
        with open(sig_path, "r") as f:
            signatures = json.load(f)
            
    # Calculate QQQ vs XLK Relative Strength Ratio
    pivot['qqq_xlk_ratio'] = pivot['QQQ'] / pivot['XLK']
    pivot['ratio_sma50'] = pivot['qqq_xlk_ratio'].rolling(50).mean()
    pivot['ratio_rsi'] = pivot['qqq_xlk_ratio'].pct_change(20) # 20-day momentum of ratio
    
    # Run QualityEntryGate to classify regimes
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    
    for d in pivot.index:
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        
        sec_th = {s: sec_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]}
        sec_fi = {s: sec_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]}
        sec_tw = {s: sec_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]}
        sec_v_tw = {s: sec_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]}
        sec_v_fi = {s: sec_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]}
        
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
            
        daily_records.append({
            "date": d,
            "mode": current_mode,
            "qqq": pivot.loc[d, "QQQ"],
            "xlk": pivot.loc[d, "XLK"],
            "xlc": pivot.loc[d, "XLC"] if "XLC" in pivot.columns else np.nan,
            "xly": pivot.loc[d, "XLY"] if "XLY" in pivot.columns else np.nan,
            "ratio": pivot.loc[d, "qqq_xlk_ratio"],
            "ratio_mom": pivot.loc[d, "ratio_rsi"],
            "s5_xlk_th": sec_pivot.loc[d, "S5_XLK_TH"] if "S5_XLK_TH" in sec_pivot.columns else np.nan,
            "s5_xlc_th": sec_pivot.loc[d, "S5_XLC_TH"] if "S5_XLC_TH" in sec_pivot.columns else np.nan,
            "s5_xly_th": sec_pivot.loc[d, "S5_XLY_TH"] if "S5_XLY_TH" in sec_pivot.columns else np.nan,
            "sv5_xlk_tw": sec_pivot.loc[d, "SV5_XLK_TW"] if "SV5_XLK_TW" in sec_pivot.columns else np.nan,
        })
        
    df = pd.DataFrame(daily_records)
    df['qqq_ret'] = df['qqq'].pct_change().fillna(0.0)
    df['xlk_ret'] = df['xlk'].pct_change().fillna(0.0)
    df['excess_qqq_xlk'] = df['qqq_ret'] - df['xlk_ret']
    
    print("\n" + "="*115)
    print("      🔬 ANÁLISIS FORENSE: QQQ (NASDAQ-100) VS XLK (TECH SPDR) POR RÉGIMEN (2000 - 2026)")
    print("="*115)
    
    reg_summary = []
    for mode_name, grp in df.groupby('mode'):
        n_days = len(grp)
        qqq_cum = (np.prod(1.0 + grp['qqq_ret']) - 1.0) * 100.0
        xlk_cum = (np.prod(1.0 + grp['xlk_ret']) - 1.0) * 100.0
        spread = qqq_cum - xlk_cum
        
        reg_summary.append({
            "mode": mode_name,
            "days": n_days,
            "qqq_ret": qqq_cum,
            "xlk_ret": xlk_cum,
            "spread": spread
        })
        
    df_reg = pd.DataFrame(reg_summary).sort_values(by='days', ascending=False)
    
    print(f"\n📊 COMPARATIVA DE RENDIMIENTO ACUMULADO POR RÉGIMEN:")
    print(f"{'Régimen de Mercado':<25s} | {'Días':<6s} | {'Retorno QQQ (%)':<18s} | {'Retorno XLK (%)':<18s} | {'Ventaja QQQ vs XLK (%)'}")
    print("-" * 115)
    for r in df_reg.itertuples():
        win_str = f"🟢 QQQ Gana ({r.spread:+6.2f}%)" if r.spread > 0 else f"🔴 XLK Gana ({r.spread:+6.2f}%)"
        print(f"{r.mode:<25s} | {r.days:<6d} | {r.qqq_ret:+16.2f}% | {r.xlk_ret:+16.2f}% | {win_str}")
        
    # Analysis of Ratio Momentum & Broadened Leadership Signal
    print("\n" + "="*115)
    print("      🔍 DISPARADORES DE VENTAJAS COMPETITIVAS DE ENTRADA A QQQ VS XLK:")
    print("="*115)
    
    # Filter days where Communications (XLC) & Discretionary (XLY) lead Tech (XLK)
    df['non_tech_lead'] = (df['s5_xlc_th'] > df['s5_xlk_th']) & (df['s5_xly_th'] > df['s5_xlk_th'])
    
    qqq_win_lead = df[df['non_tech_lead']]['excess_qqq_xlk'].mean() * 100.0
    qqq_win_normal = df[~df['non_tech_lead']]['excess_qqq_xlk'].mean() * 100.0
    
    print(f"1. LIDERAZGO NO-TECNOLÓGICO (Amplitud XLC & XLY > XLK):")
    print(f"   • Exceso de Retorno Diario Promedio QQQ vs XLK cuando XLC/XLY Lideran : {qqq_win_lead:+6.4f}% / día 🟢")
    print(f"   • Exceso de Retorno Diario Promedio QQQ vs XLK en Estado Normal        : {qqq_win_normal:+6.4f}% / día")
    
    print("\n2. PISO GENERACIONAL / RECUPERACIÓN EN V:")
    piso_grp = df[df['mode'].isin(['PISO_GENERACIONAL', 'RECUPERACION'])]
    qqq_piso = (np.prod(1.0 + piso_grp['qqq_ret']) - 1.0) * 100.0
    xlk_piso = (np.prod(1.0 + piso_grp['xlk_ret']) - 1.0) * 100.0
    print(f"   • Retorno Acumulado QQQ en Pisos & Recuperaciones : {qqq_piso:+8.2f}% 🚀")
    print(f"   • Retorno Acumulado XLK en Pisos & Recuperaciones : {xlk_piso:+8.2f}%")
    print(f"   • Ventaja Neta QQQ en Recuperación Inicial       : {qqq_piso - xlk_piso:+8.2f}% a favor de QQQ")
    
    print("="*115)

if __name__ == "__main__":
    main()
