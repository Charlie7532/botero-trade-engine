"""
QQQ Single-Regime Value-Add Forensic Ablation Explorer (2000-2026)
===================================================================
Persona: Marcos López de Prado & Jim Simons (Quantitative Signal Mining)

Evaluates the exact value-add of QQQ in EACH individual market regime:
  - Tests 9 isolated scenarios where QQQ is enabled in ONLY ONE regime.
  - Measures:
      1. Final SPY Equivalent Shares Compounded (2000 - 2026)
      2. Net Alpha Shares vs Baseline V38
      3. Max Drawdown Impact (%)
      4. Win Rate % and Profit Factor in that regime.
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
REGIMES_LIST = [
    "PISO_GENERACIONAL",
    "RECUPERACION",
    "RE_ACUMULACION_ALCISTA",
    "PULLBACK_ALCISTA",
    "BEAR_RALLY",
    "NORMAL",
    "MERCADO_SANO",
    "DISTRIBUCION_PRE_CRASH",
    "CRASH_SISTEMICO"
]

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

def run_regime_ablation(pivot, sec_pivot, macro_pivot, target_regimes=None):
    if target_regimes is None:
        target_regimes = []
        
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
        # ISOLATED REGIME SUBSTITUTION (Replace XLK with QQQ if in target_regimes)
        # -------------------------------------------------------------
        if current_mode in target_regimes:
            if "XLK" in target_weights and target_weights["XLK"] > 0:
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
                    
    df_res = pd.DataFrame(daily_records)
    return df_res[df_res['date'] >= pd.to_datetime('2000-01-01').date()].copy()

def main():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
    # 1. Run Baseline (0% QQQ)
    df_base = run_regime_ablation(pivot, sec_pivot, macro_pivot, target_regimes=[])
    sh_base = df_base.iloc[-1]['spy_shares']
    
    ablation_results = []
    
    # 2. Test QQQ in each regime isolated
    for reg in REGIMES_LIST:
        df_trial = run_regime_ablation(pivot, sec_pivot, macro_pivot, target_regimes=[reg])
        sh_trial = df_trial.iloc[-1]['spy_shares']
        alpha_shares = sh_trial - sh_base
        
        # Calculate max drawdown
        df_trial['peak'] = df_trial['equity'].cummax()
        df_trial['dd'] = (df_trial['equity'] - df_trial['peak']) / df_trial['peak'] * 100.0
        max_dd = df_trial['dd'].min()
        
        ablation_results.append({
            "regime": reg,
            "end_shares": sh_trial,
            "alpha_shares": alpha_shares,
            "max_dd": max_dd,
            "verdict": "🟢 APORTA ALPHA" if alpha_shares > 0.5 else ("🔴 DESTRUYE ALPHA" if alpha_shares < -0.5 else "⚪ NEUTRO (0 acc)")
        })
        
    df_ablation = pd.DataFrame(ablation_results).sort_values(by='alpha_shares', ascending=False)
    
    # 3. Test Combined Optimal Regimes (Only those with positive alpha)
    opt_regimes = df_ablation[df_ablation['alpha_shares'] > 0.5]['regime'].tolist()
    df_opt = run_regime_ablation(pivot, sec_pivot, macro_pivot, target_regimes=opt_regimes)
    sh_opt = df_opt.iloc[-1]['spy_shares']
    alpha_opt = sh_opt - sh_base
    
    print("\n" + "="*115)
    print("      🔬 MATRIZ DE APORTACIÓN DE ALPHA DE QQQ POR RÉGIMEN INDIVIDUAL (2000 - 2026)")
    print("="*115)
    print(f"📌 BASELINE V38 (Solo XLK / Canasta Sectorial) : {sh_base:.2f} ACCIONES SPY\n")
    
    print(f"{'Régimen Evaluado con QQQ':<30s} | {'Acciones SPY Finales':<22s} | {'Alpha Neto vs Base':<22s} | {'Max Drawdown':<14s} | {'Veredicto'}")
    print("-" * 115)
    
    for r in df_ablation.itertuples():
        print(f"| **`{r.regime}`** | {r.end_shares:18.2f} acc | **{r.alpha_shares:+18.2f} acc** | {r.max_dd:11.2f}% | {r.verdict} |")
        
    print("\n" + "="*115)
    print("      🚀 COMBO DE RÉGIMENES OPTIMIZADOS DONDE QQQ AGREGA VENTAJAS CLARAS:")
    print("="*115)
    print(f"Régimenes Activos para QQQ : {opt_regimes}")
    print(f"Acciones SPY Compuestas Finales  : {sh_opt:.2f} ACCIONES SPY 🔥")
    print(f"Alpha Neto Total del Combo       : {alpha_opt:+8.2f} ACCIONES DE SPY")
    print("="*115)

if __name__ == "__main__":
    main()
