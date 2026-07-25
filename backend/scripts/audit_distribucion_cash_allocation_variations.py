"""
DISTRIBUCION_PRE_CRASH Allocation Policy Deep Audit (2000-2026)
===============================================================
Persona: Marcos López de Prado & Ray Dalio (Allocations & Cash Drag)

Tests 5 distinct asset allocation policies during DISTRIBUCION_PRE_CRASH:
  - Policy 0: Baseline V37.1 (50% Cash / 50% Defensives: XLP, XLU, XLV)
  - Policy 1: Pure 100% Cash (0% Risk Exposure)
  - Policy 2: 80% Cash / 20% Defensives
  - Policy 3: Dynamic n_dead Cash Escapes (100% Cash when n_dead >= 3)
  - Policy 4: Divergent Leadership Cash Escape (100% Cash when narrow top)
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
            WHERE ticker IN ('SPY', 'S5TH', 'S5FI', 'S5TW', 'SV5TH', 'SV5FI', 'SV5TW')
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

def run_policy_simulation(pivot, sec_pivot, macro_pivot, policy_id=0):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for d in pivot.index:
        spy_p = pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * sec_pivot.loc[d, s] for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]))
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
            
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "mode": current_mode
        })
        
        available_secs = [s for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
        )
        
        # APPLY POLICIES IN DISTRIBUCION_PRE_CRASH
        if current_mode == "DISTRIBUCION_PRE_CRASH":
            def_pool = ["XLP", "XLU", "XLV"]
            tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in def_pool if s in available_secs)
            
            if policy_id == 1:
                # 100% Cash
                target_weights = {s: 0.0 for s in available_secs}
            elif policy_id == 2:
                # 80% Cash / 20% Defensives
                target_weights = {}
                for s in def_pool:
                    if s in available_secs:
                        target_weights[s] = 0.20 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)
            elif policy_id == 3:
                # Dynamic n_dead: n_dead >= 3 -> 100% Cash, n_dead >= 1 -> 75% Cash, n_dead == 0 -> 50% Cash
                n_dead = sum(1 for v in sec_th.values() if v < 25.0)
                if n_dead >= 3:
                    target_weights = {s: 0.0 for s in available_secs}
                elif n_dead >= 1:
                    target_weights = {}
                    for s in def_pool:
                        if s in available_secs:
                            target_weights[s] = 0.25 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)
                else:
                    target_weights = {}
                    for s in def_pool:
                        if s in available_secs:
                            target_weights[s] = 0.50 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)
            elif policy_id == 4:
                # Divergent Leadership Escape -> 100% Cash
                hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
                cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
                is_div = (hot_tw <= 1 and cold_tw >= 7)
                if is_div:
                    target_weights = {s: 0.0 for s in available_secs}
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]) and sec_pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / sec_pivot.loc[d, s]
                portfolio_cash -= allocated
                
    return pd.DataFrame(daily_records)

def main():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA PROFUNDA DE POLÍTICAS DE CASH EN 'DISTRIBUCION_PRE_CRASH' (2000 - 2026)")
    print("="*115)
    
    policies = {
        0: "Baseline V37.1 (50% Cash / 50% Defensivos XLP/XLU/XLV)",
        1: "Pura 100% Cash (0% Riesgo)",
        2: "80% Cash / 20% Defensivos",
        3: "Cash Dinámico por n_dead (100% Cash si n_dead >= 3, 75% Cash si n_dead >= 1)",
        4: "Cash por Liderazgo Divergente (100% Cash si Mercado Estrecho)"
    }
    
    results = {}
    for p_id, p_name in policies.items():
        df_res = run_policy_simulation(pivot, sec_pivot, macro_pivot, policy_id=p_id)
        df_res['ret'] = df_res['equity'].pct_change().fillna(0.0)
        
        dist_df = df_res[df_res['mode'] == 'DISTRIBUCION_PRE_CRASH']
        dist_ret = (np.prod(1.0 + dist_df['ret']) - 1.0) * 100.0 if len(dist_df) > 0 else 0.0
        
        final_shares = df_res.iloc[-1]['spy_shares']
        results[p_id] = {
            "name": p_name,
            "dist_ret": dist_ret,
            "final_shares": final_shares
        }
        
    print(f"\n📊 RESULTADOS DE COMPOUNDING SEGÚN POLÍTICA EN DISTRIBUCION_PRE_CRASH:")
    print(f"{'#':<3s} | {'Nombre de la Política de Asignación':<65s} | {'Retorno en Distribución':<24s} | {'Acciones SPY Compuestas'}")
    print("-" * 115)
    
    base_shares = results[0]['final_shares']
    for p_id, res in results.items():
        delta = res['final_shares'] - base_shares
        d_str = f"({delta:+.2f} acc)" if p_id != 0 else "(Baseline)"
        print(f"{p_id:<3d} | {res['name']:<65s} | {res['dist_ret']:+22.2f}% | {res['final_shares']:8.2f} {d_str}")

    print("\n" + "="*115)
    print("  ANÁLISIS MECÁNICO DEL CIO:")
    best_id = max(results.keys(), key=lambda x: results[x]['final_shares'])
    print(f"  🏆 Política Ganadora Absoluta: Política {best_id} - {results[best_id]['name']}")
    print(f"  • Acciones Logradas: {results[best_id]['final_shares']:.2f} Acciones (vs {base_shares:.2f} en Baseline)")
    print("="*115)

if __name__ == "__main__":
    main()
