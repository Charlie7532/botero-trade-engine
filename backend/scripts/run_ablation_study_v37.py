"""
Systematic Step-by-Step Ablation Study for V37 3D Enhancements (2000-2026)
==========================================================================
Persona: Marcos López de Prado (Ablation & Marginal Attribution Protocol)

Evaluates 4 isolated steps:
  Step 0: Baseline V36/V37 (Current Production)
  Step 1: Isolated PULLBACK_ALCISTA 3D Rules
  Step 2: Isolated PISO_GENERACIONAL Day-0 3D Rules
  Step 3: Isolated RE_ACUMULACION_ALCISTA 3D Rules
  Step 4: Combined Approved V37 Architecture (Full Synergy)
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

def run_ablation_step(df, step=0):
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
        
        # Base V37 Gate evaluation
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        
        div_fi = v_fi - fi
        div_th = v_th - th
        ratio_tw_fi = tw / max(1.0, fi)
        
        # STEP 1: PULLBACK_ALCISTA 3D Ablation
        if step in (1, 4):
            if new_mode == "PULLBACK_ALCISTA" and ratio_tw_fi > 0.85:
                new_mode = current_mode # Block false pullback
                
        # STEP 2: PISO_GENERACIONAL Day-0 3D Ablation
        if step in (2, 4):
            if current_mode in ("NORMAL", "DISTRIBUCION_PRE_CRASH", "CAPITULACION_SECTORIAL") and th <= 35.0:
                if div_fi >= 35.0 and div_th >= 20.0:
                    new_mode = "PISO_GENERACIONAL"
                    
        # STEP 3: RE_ACUMULACION_ALCISTA 3D Ablation
        if step in (3, 4):
            if new_mode == "RE_ACUMULACION_ALCISTA" and (ratio_tw_fi > 1.2 or div_fi < 0.0):
                new_mode = current_mode
                
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
    print("      🔬 ESTUDIO DE ABLACIÓN PASO A PASO (MARGGINAL ATTRIBUTION AUDIT)")
    print("="*115)
    
    steps = [
        (0, "Línea Base V37 Actual"),
        (1, "Ablación Paso 1: Rules 3D en PULLBACK_ALCISTA"),
        (2, "Ablación Paso 2: Rules 3D en PISO_GENERACIONAL"),
        (3, "Ablación Paso 3: Rules 3D en RE_ACUMULACION"),
        (4, "Combinado Final Aprobado V37.1")
    ]
    
    results = []
    
    for st, name in steps:
        df_res = run_ablation_step(df, step=st)
        df_res['ret'] = df_res['equity'].pct_change().fillna(0.0)
        
        shares = df_res.iloc[-1]['spy_shares']
        tot_ret = ((df_res.iloc[-1]['equity'] / df_res.iloc[0]['equity']) - 1.0) * 100.0
        
        # Max Drawdown
        df_res['cum_max'] = df_res['equity'].cummax()
        df_res['dd'] = (df_res['equity'] - df_res['cum_max']) / df_res['cum_max']
        mdd = df_res['dd'].min() * 100.0
        
        # Pullback ret & WR
        pb_sub = df_res[df_res['mode'] == 'PULLBACK_ALCISTA']
        pb_days = len(pb_sub)
        pb_ret = (np.prod(1.0 + pb_sub['ret']) - 1.0) * 100.0 if pb_days > 0 else 0.0
        
        results.append({
            "step": st,
            "name": name,
            "shares": shares,
            "tot_ret": tot_ret,
            "mdd": mdd,
            "pb_days": pb_days,
            "pb_ret": pb_ret
        })
        
    print(f"\n{'Paso':<5s} | {'Nombre de la Prueba':<45s} | {'Acciones SPY':<15s} | {'Ret. Total (%)':<16s} | {'Max DD (%)':<12s} | {'PB Retorno (%)'}")
    print("-" * 115)
    
    base_shares = results[0]['shares']
    for r in results:
        delta_s = r['shares'] - base_shares
        print(f"{r['step']:<5d} | {r['name']:<45s} | {r['shares']:15.2f} | {r['tot_ret']:+16.2f}% | {r['mdd']:12.2f}% | {r['pb_ret']:+14.2f}% (Δ {delta_s:+6.2f})")

if __name__ == "__main__":
    main()
