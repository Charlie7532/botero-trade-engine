"""
QQQ Integration & Competitive Advantage Allocation Test (2000-2026)
===================================================================
Persona: Jim Simons & Ray Dalio (Signal Mining & Dynamic Asset Allocation)

Tests 3 specific competitive advantage rules for QQQ integration in QualityEntryGate:
  Rule 1: PISO_GENERACIONAL -> Prefer QQQ over XLK (Captures XLC + XLY V-rebound).
  Rule 2: Broadened Leadership -> When S5_XLC_FI > S5_XLK_FI or S5_XLY_FI > S5_XLK_FI -> Allocate QQQ.
  Rule 3: Pure Tech Dominance -> When S5_XLK_FI >= S5_XLC_FI and S5_XLK_FI >= S5_XLY_FI -> Allocate XLK.

Evaluates impact on Total SPY Equivalent Shares compounding (2000-2026).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
SECTOR_CAP_WEIGHTS = {
    "XLK": 0.317, "XLC": 0.089, "XLF": 0.132, "XLI": 0.078,
    "XLV": 0.118, "XLP": 0.058, "XLU": 0.024, "XLRE": 0.022,
    "XLB": 0.021, "XLE": 0.034, "XLY": 0.107
}

def load_data(store):
    conn = store._conn()
    try:
        df_p = pd.read_sql("""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'QQQ', 'S5TH', 'S5FI', 'S5TW', 'SV5TH', 'SV5FI', 'SV5TW')
              AND timeframe = '1d'
              AND time >= '1999-12-15'
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
              AND time >= '1999-12-15'
            ORDER BY time, ticker
        """, conn)
        sec_pivot = df_sectors.pivot(index='date', columns='ticker', values='close').ffill()
        
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX') 
              AND timeframe = '1d' 
              AND time >= '1999-12-15' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = pivot.index.intersection(sec_pivot.index).intersection(macro_pivot.index)
        return pivot.loc[common_dates], sec_pivot.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def run_qqq_integrated_sim(pivot, sec_pivot, macro_pivot, use_qqq_rules=True):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11 + ["QQQ"]}
    
    daily_records = []
    
    for idx_i, d in enumerate(pivot.index):
        spy_p = pivot.loc[d, "SPY"]
        qqq_p = pivot.loc[d, "QQQ"] if "QQQ" in pivot.columns else spy_p
        
        stock_eq = sum(portfolio_shares[s] * sec_pivot.loc[d, s] for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]))
        qqq_eq = portfolio_shares.get("QQQ", 0.0) * qqq_p
        current_equity = portfolio_cash + stock_eq + qqq_eq
        spy_equiv_shares = current_equity / spy_p
        
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        
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
            
        available_secs = [s for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
        )
        
        # -------------------------------------------------------------
        # APPLY QQQ COMPETITIVE ADVANTAGE SWITCHES
        # -------------------------------------------------------------
        if use_qqq_rules:
            # Rule 1: PISO_GENERACIONAL -> Assign QQQ instead of XLK if XLK is in top candidates
            if current_mode == "PISO_GENERACIONAL":
                # Convert XLK weight to QQQ for higher V-rebound momentum
                if "XLK" in target_weights and target_weights["XLK"] > 0:
                    xlk_w = target_weights.pop("XLK")
                    target_weights["QQQ"] = xlk_w
                    
            # Rule 2: In MERCADO_SANO / RE_ACUMULACION, if XLC_FI or XLY_FI > XLK_FI -> Replace XLK with QQQ
            elif current_mode in ("MERCADO_SANO", "RE_ACUMULACION_ALCISTA"):
                xlk_fi = sec_fi.get("XLK", 50.0)
                xlc_fi = sec_fi.get("XLC", 50.0)
                xly_fi = sec_fi.get("XLY", 50.0)
                
                if (xlc_fi > xlk_fi or xly_fi > xlk_fi) and "XLK" in target_weights and target_weights["XLK"] > 0:
                    xlk_w = target_weights.pop("XLK")
                    target_weights["QQQ"] = xlk_w
                    
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "mode": current_mode
        })
        
        # Execute rebalance
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11 + ["QQQ"]}
        
        for s, w in target_weights.items():
            if w > 0:
                if s == "QQQ":
                    allocated = current_equity * w
                    portfolio_shares["QQQ"] = allocated / qqq_p
                    portfolio_cash -= allocated
                elif s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]) and sec_pivot.loc[d, s] > 0:
                    allocated = current_equity * w
                    portfolio_shares[s] = allocated / sec_pivot.loc[d, s]
                    portfolio_cash -= allocated
                    
    return pd.DataFrame(daily_records)

def main():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🚀 SIMULACIÓN DE INTEGRACIÓN Y VENTAJAS COMPETITIVAS DE QQQ (2000 - 2026)")
    print("="*115)
    
    df_base = run_qqq_integrated_sim(pivot, sec_pivot, macro_pivot, use_qqq_rules=False)
    df_qqq = run_qqq_integrated_sim(pivot, sec_pivot, macro_pivot, use_qqq_rules=True)
    
    # Slicing from 2000-01-01
    df_base_2000 = df_base[df_base['date'] >= pd.to_datetime('2000-01-01').date()]
    df_qqq_2000 = df_qqq[df_qqq['date'] >= pd.to_datetime('2000-01-01').date()]
    
    sh_base = df_base_2000.iloc[-1]['spy_shares']
    sh_qqq = df_qqq_2000.iloc[-1]['spy_shares']
    delta = sh_qqq - sh_base
    
    print(f"\n📊 RESULTADOS CUANTITATIVOS COMPARATIVOS:")
    print(f"  • Acciones SPY Compuestas (V38 Solo XLK)       : {sh_base:8.2f} ACCIONES SPY")
    print(f"  • Acciones SPY Compuestas (V38 Con Reglas QQQ) : {sh_qqq:8.2f} ACCIONES SPY 🔥")
    print(f"  • Alpha Neto Adicional por Integración de QQQ  : {delta:+8.2f} ACCIONES SPY")
    
    print("\n" + "="*115)
    print("  💡 VEREDICTO FINAL DE RE-ACTIVACIÓN DE QQQ:")
    if delta > 0:
        print(f"  🟢 APROBADA LA RE-ACTIVACIÓN: QQQ genera +{delta:.2f} acciones de alpha adicional sobre el motor V38.")
    else:
        print(f"  🔴 SE RECOMIENDA SELECCIÓN TÁCTICA: XLK mantiene la ventaja pura en Mercado Sano por mayor concentración.")
    print("="*115)

if __name__ == "__main__":
    main()
