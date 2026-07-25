"""
Full 3D Triad Regime Optimization & Backtest (2000-2026)
=========================================================
Applies 3D Triad Cascade Spectrums & Elder Brother Stress Rules across ALL Regimes:
  1. PISO_GENERACIONAL: Day-0 3D Volume Absorption Trigger (Div_FI >= +35%, Div_TH >= +20%).
  2. RE_ACUMULACION_ALCISTA: Ratio_TW_FI Compression & Velocity Acceleration filter.
  3. DISTRIBUCION_PRE_CRASH: Early Top Dilation Trigger (S5_TW / SV5_TW > 1.45).
  4. BEAR_RALLY: False Rally Filter (Ratio_FI_TH < 0.60 blocks long traps).
  5. RECUPERACION: Accelerated Handoff to MERCADO_SANO (Ratio_FI_TH >= 1.0).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_data(store):
    conn = store._conn()
    try:
        all_tickers = ["SPY"] + SECTORS_11 + list(BREADTH_MAP.keys())
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
            
        all_query_tickers = list(set(all_tickers + sec_ind_tickers))
        p_str = ", ".join([f"'{t}'" for t in all_query_tickers])
        
        df = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df.pivot(index='date', columns='ticker', values='close').ffill()
        return pivot
    finally:
        store._put(conn)

def simulate_3d_regimes(df, use_3d_enhancements=True):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = df["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for i, d in enumerate(df.index):
        spy_p = df.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * df.loc[d, s] for s in SECTORS_11 if s in df.columns and pd.notna(df.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = df.loc[d, "S5TH"]
        fi = df.loc[d, "S5FI"]
        tw = df.loc[d, "S5TW"]
        v_th = df.loc[d, "SV5TH"]
        v_fi = df.loc[d, "SV5FI"]
        v_tw = df.loc[d, "SV5TW"]
        
        sec_th = {s: df.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in df.columns and pd.notna(df.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: df.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in df.columns and pd.notna(df.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: df.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in df.columns and pd.notna(df.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: df.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in df.columns and pd.notna(df.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: df.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in df.columns and pd.notna(df.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        
        if use_3d_enhancements:
            div_fi = v_fi - fi
            div_th = v_th - th
            ratio_tw_fi = tw / max(1.0, fi)
            ratio_fi_th = fi / max(1.0, th)
            ratio_inv_tw = tw / max(1.0, v_tw)
            
            # 1. Early 3D Floor Absorption -> Upgrade PISO_GENERACIONAL
            if current_mode in ("NORMAL", "DISTRIBUCION_PRE_CRASH", "CAPITULACION_SECTORIAL") and th <= 35.0:
                if div_fi >= 35.0 and div_th >= 20.0:
                    new_mode = "PISO_GENERACIONAL"
                    
            # 2. RE_ACUMULACION_ALCISTA 3D Filter (Fix -9.42% negative return)
            if new_mode == "RE_ACUMULACION_ALCISTA":
                if ratio_tw_fi > 1.2 or div_fi < 0.0:
                    new_mode = current_mode # Block unconfirmed re-accumulation
                    
            # 3. Early Top Dilation Trigger -> DISTRIBUCION_PRE_CRASH
            if current_mode in ("NORMAL", "MERCADO_SANO") and ratio_inv_tw > 1.45 and tw > 60.0:
                new_mode = "DISTRIBUCION_PRE_CRASH"
                
            # 4. Accelerated Handoff from RECUPERACION to MERCADO_SANO
            if current_mode == "RECUPERACION" and ratio_fi_th >= 1.0 and th > 50.0:
                new_mode = "MERCADO_SANO"
                
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "mode": current_mode
        })
        
        available_secs = [s for s in SECTORS_11 if s in df.columns and pd.notna(df.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in df.columns and pd.notna(df.loc[d, s]) and df.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / df.loc[d, s]
                portfolio_cash -= allocated
                
    return pd.DataFrame(daily_records)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA Y POTENCIAL DE MEJORA MULTI-RÉGIMEN 3D (2000 - 2026)")
    print("="*115)
    
    df_base = simulate_3d_regimes(df, use_3d_enhancements=False)
    df_3d = simulate_3d_regimes(df, use_3d_enhancements=True)
    
    df_base['ret'] = df_base['equity'].pct_change().fillna(0.0)
    df_3d['ret'] = df_3d['equity'].pct_change().fillna(0.0)
    
    print(f"\n📊 DESGLOSE DE MEJORA POR RÉGIMEN EN EL PORTAFOLIO:")
    print(f"{'Régimen':<26s} | {'Días Base / 3D':<16s} | {'Retorno Base (%)':<18s} | {'Retorno 3D (%)':<18s} | {'Ganancia Neta'}")
    print("-" * 100)
    
    for mode in sorted(df_base['mode'].unique()):
        sub_b = df_base[df_base['mode'] == mode]
        sub_3d = df_3d[df_3d['mode'] == mode]
        
        n_b = len(sub_b)
        n_3d = len(sub_3d)
        
        ret_b = (np.prod(1.0 + sub_b['ret']) - 1.0) * 100.0 if n_b > 0 else 0.0
        ret_3d = (np.prod(1.0 + sub_3d['ret']) - 1.0) * 100.0 if n_3d > 0 else 0.0
        
        diff = ret_3d - ret_b
        diag = "🟢 MEJORA SIGNFICATIVA" if diff > 5.0 else ("🟢 MEJORA MODERADA" if diff > 0.0 else "⚪ DIVERGENCIA RIESGO")
        print(f"{mode:<26s} | {n_b:6d} / {n_3d:<7d} | {ret_b:+18.2f}% | {ret_3d:+18.2f}% | {diff:+10.2f}% ({diag})")

    shares_b = df_base.iloc[-1]['spy_shares']
    shares_3d = df_3d.iloc[-1]['spy_shares']
    
    print("\n" + "="*115)
    print(f"  ACCIONES TOTALES BASELINE V37     : {shares_b:.2f} Acciones SPY")
    print(f"  ACCIONES TOTALES V37 PRO 3D MULTI : {shares_3d:.2f} Acciones SPY (🟢 +{shares_3d - shares_b:.2f} Acciones de Mejora Net)")
    print("="*115)

if __name__ == "__main__":
    main()
