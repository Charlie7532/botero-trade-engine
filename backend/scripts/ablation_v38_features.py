"""
Ablation Study for V38 Directives (2000-2026)
==============================================
Isolates the exact alpha contribution of each user directive:
  Variant A: Baseline V37.1 (525.36 acc)
  Variant B: Baseline + 100% Cash in CRASH_SISTEMICO (0% ETF exposure)
  Variant C: Variant B + High-Beta Beaten-Down Sector Accumulation in PISO_GENERACIONAL
  Variant D: Variant C + Re-classification of n_dead=0 Distribution as RE_ACUMULACION_SALUDABLE
  Variant E: Variant D + Scaled Cash in Structural Distribution (n_dead >= 2 -> 50% cash, n_dead >= 4 -> 100% cash)
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

def run_variant(pivot, sec_pivot, macro_pivot, var_code='A'):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for idx_i, d in enumerate(pivot.index):
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
            
        available_secs = [s for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s])]
        n_dead = sum(1 for v in sec_th.values() if v < 25.0)
        
        # -------------------------------------------------------------
        # VARIANTS APPLY LOGIC
        # -------------------------------------------------------------
        if var_code == 'A':
            # Baseline V37.1
            target_weights = gate.calculate_target_weights(
                mode=current_mode, sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
            )
        elif var_code == 'B':
            # Baseline + 100% Cash in CRASH_SISTEMICO
            if current_mode == "CRASH_SISTEMICO":
                target_weights = {s: 0.0 for s in available_secs}
            else:
                target_weights = gate.calculate_target_weights(
                    mode=current_mode, sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                    avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                )
        elif var_code == 'C':
            # Variant B + High-Beta Beaten-Down in PISO_GENERACIONAL
            if current_mode == "CRASH_SISTEMICO":
                target_weights = {s: 0.0 for s in available_secs}
            elif current_mode == "PISO_GENERACIONAL":
                past_idx = max(0, idx_i - 20)
                past_date = pivot.index[past_idx]
                non_def = [s for s in available_secs if s not in ["XLP", "XLU", "XLV"]]
                rets = {s: (sec_pivot.loc[d, s] / sec_pivot.loc[past_date, s]) - 1.0 for s in non_def if sec_pivot.loc[past_date, s] > 0}
                sorted_beaten = [x[0] for x in sorted(rets.items(), key=lambda x: x[1])[:3]]
                target_weights = {s: 0.0 for s in available_secs}
                for s in sorted_beaten:
                    target_weights[s] = 1.0 / len(sorted_beaten)
            else:
                target_weights = gate.calculate_target_weights(
                    mode=current_mode, sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                    avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                )
        elif var_code == 'D':
            # Variant C + Re-classification of n_dead=0 Distribution as RE_ACUMULACION_SALUDABLE
            if current_mode == "CRASH_SISTEMICO":
                target_weights = {s: 0.0 for s in available_secs}
            elif current_mode == "PISO_GENERACIONAL":
                past_idx = max(0, idx_i - 20)
                past_date = pivot.index[past_idx]
                non_def = [s for s in available_secs if s not in ["XLP", "XLU", "XLV"]]
                rets = {s: (sec_pivot.loc[d, s] / sec_pivot.loc[past_date, s]) - 1.0 for s in non_def if sec_pivot.loc[past_date, s] > 0}
                sorted_beaten = [x[0] for x in sorted(rets.items(), key=lambda x: x[1])[:3]]
                target_weights = {s: 0.0 for s in available_secs}
                for s in sorted_beaten:
                    target_weights[s] = 1.0 / len(sorted_beaten)
            elif current_mode == "DISTRIBUCION_PRE_CRASH":
                if n_dead == 0:
                    # Healthy re-accumulation (100% Core Sector Rotation)
                    target_weights = gate.calculate_target_weights(
                        mode="RE_ACUMULACION_ALCISTA", sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                        avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                    )
                else:
                    # Baseline 50/50 in structural distribution
                    target_weights = gate.calculate_target_weights(
                        mode="DISTRIBUCION_PRE_CRASH", sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                        avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                    )
            else:
                target_weights = gate.calculate_target_weights(
                    mode=current_mode, sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                    avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                )
        elif var_code == 'E':
            # Variant D + Scaled Cash (n_dead >= 2 -> 50% cash, n_dead >= 4 -> 100% cash)
            if current_mode == "CRASH_SISTEMICO":
                target_weights = {s: 0.0 for s in available_secs}
            elif current_mode == "PISO_GENERACIONAL":
                past_idx = max(0, idx_i - 20)
                past_date = pivot.index[past_idx]
                non_def = [s for s in available_secs if s not in ["XLP", "XLU", "XLV"]]
                rets = {s: (sec_pivot.loc[d, s] / sec_pivot.loc[past_date, s]) - 1.0 for s in non_def if sec_pivot.loc[past_date, s] > 0}
                sorted_beaten = [x[0] for x in sorted(rets.items(), key=lambda x: x[1])[:3]]
                target_weights = {s: 0.0 for s in available_secs}
                for s in sorted_beaten:
                    target_weights[s] = 1.0 / len(sorted_beaten)
            elif current_mode == "DISTRIBUCION_PRE_CRASH":
                if n_dead == 0:
                    target_weights = gate.calculate_target_weights(
                        mode="RE_ACUMULACION_ALCISTA", sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                        avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                    )
                elif n_dead >= 4:
                    target_weights = {s: 0.0 for s in available_secs}
                elif n_dead >= 2:
                    def_pool = ["XLP", "XLU", "XLV"]
                    tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in def_pool if s in available_secs)
                    target_weights = {s: 0.50 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap) for s in def_pool if s in available_secs}
                else:
                    def_pool = ["XLP", "XLU", "XLV"]
                    tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in def_pool if s in available_secs)
                    target_weights = {s: 0.75 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap) for s in def_pool if s in available_secs}
            else:
                target_weights = gate.calculate_target_weights(
                    mode=current_mode, sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                    avail_sectors=available_secs, sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                )
                
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares
        })
        
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
    print("      🔬 ESTUDIO DE ABLACIÓN V38: DESGLOSE COMPONENTE POR COMPONENTE (2000 - 2026)")
    print("="*115)
    
    variants = {
        'A': "Baseline V37.1 (525.36 acciones)",
        'B': "Variante B: Baseline + 100% Cash en CRASH_SISTEMICO",
        'C': "Variante C: Variante B + Acumulación Alta Beta en PISO_GENERACIONAL",
        'D': "Variante D: Variante C + Re-clasificación n_dead=0 como RE_ACUMULACION",
        'E': "Variante E: Variante D + Escalamiento de Cash por n_dead (>=2 -> 50% cash, >=4 -> 100% cash)"
    }
    
    results = {}
    for code, desc in variants.items():
        df_res = run_variant(pivot, sec_pivot, macro_pivot, var_code=code)
        sh = df_res.iloc[-1]['spy_shares']
        results[code] = sh
        
    base_sh = results['A']
    print(f"\n📊 RESUMEN DE RESULTADOS POR COMPONENTE:")
    for code, desc in variants.items():
        sh = results[code]
        delta = sh - base_sh
        d_str = f"({delta:+.2f} acc)" if code != 'A' else "(Baseline)"
        print(f"  • {desc:<85s} : {sh:8.2f} {d_str}")
        
    print("\n" + "="*115)
    print("  DIAGNÓSTICO ARQUITECTÓNICO DEL CIO:")
    print("="*115)

if __name__ == "__main__":
    main()
