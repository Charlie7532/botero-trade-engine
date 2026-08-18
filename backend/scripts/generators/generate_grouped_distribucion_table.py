"""
Grouped DISTRIBUCION_PRE_CRASH Audit Table with SPY Return Column Generator
===========================================================================
Adds SPY % Return column after Duration (Días) to measure Opportunity Cost:
  - SPY Return = (SPY_end / SPY_start - 1) * 100
  - Statistical Rows (MAXIMO, MINIMO, PROMEDIO) include SPY Return stats per group.
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

def main():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
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
            "mode": current_mode,
            "spy": pivot.loc[d, "SPY"],
            "th": th, "fi": fi, "tw": tw,
            "v_fi": v_fi, "v_tw": v_tw,
            "vix": vix,
            "n_dead": sum(1 for v in sec_th.values() if v < 25.0)
        })
        
    df = pd.DataFrame(daily_records)
    
    # Extract contiguous episodes
    episodes = []
    in_dist = False
    start_date = None
    start_idx = 0
    
    for i in range(len(df)):
        mode = df.iloc[i]['mode']
        d = df.iloc[i]['date']
        
        if mode == 'DISTRIBUCION_PRE_CRASH' and not in_dist:
            in_dist = True
            start_date = d
            start_idx = i
        elif mode != 'DISTRIBUCION_PRE_CRASH' and in_dist:
            in_dist = False
            end_date = df.iloc[i-1]['date']
            duration = (i - start_idx)
            next_mode = mode
            exit_row = df.iloc[i]
            
            # SPY % return during episode
            spy_start = df.iloc[start_idx]['spy']
            spy_end = df.iloc[i-1]['spy']
            spy_ret = ((spy_end / spy_start) - 1.0) * 100.0
            
            # 2 days before exit (t-2)
            t2_idx = max(start_idx, i - 2)
            row_t2 = df.iloc[t2_idx]
            
            episodes.append({
                "start": start_date,
                "end": end_date,
                "duration": duration,
                "spy_ret": spy_ret,
                "next_mode": next_mode,
                "th_t2": row_t2['th'],
                "fi_t2": row_t2['fi'],
                "n_dead_t2": row_t2['n_dead'],
                "th_exit": exit_row['th'],
                "fi_exit": exit_row['fi'],
                "v_tw_exit": exit_row['v_tw'],
                "n_dead_exit": exit_row['n_dead']
            })
            
    df_ep = pd.DataFrame(episodes)
    groups = ["CRASH_SISTEMICO", "RE_ACUMULACION_ALCISTA", "MERCADO_SANO", "PISO_GENERACIONAL"]
    
    md_out = "# 📊 AUDITORÍA AGRUPADA DE EPISODIOS `DISTRIBUCION_PRE_CRASH` CON VARIACIÓN DE SPY (COSTO DE OPORTUNIDAD)\n\n"
    md_out += "**Total Episodios**: 106 Episodios (2000 - 2026)\n"
    md_out += "**Nueva Columna**: `Variación SPY (%)` insertada inmediatamente después de la columna `Días` para evaluar costo de oportunidad / riesgo evitado.\n"
    md_out += "**Estadísticas**: Incluye MÁXIMO, MÍNIMO y PROMEDIO para días, rendimiento SPY, estado $t-2$ y estado $t_{exit}$.\n\n"
    
    for g_idx, g_name in enumerate(groups, 1):
        sub = df_ep[df_ep['next_mode'] == g_name]
        if len(sub) == 0:
            continue
            
        md_out += f"---\n\n"
        md_out += f"### 🏛️ GRUPO {g_idx}: TRANSICIÓN HACIA `{g_name}` (Total: {len(sub)} Episodios)\n\n"
        md_out += "| # | Fecha Inicio | Fecha Fin | Días | Variación SPY (%) | Estado t-2 días (S5TH, S5FI, n_dead) | Estado Transición t_exit (S5TH, S5FI, SV5TW, n_dead) |\n"
        md_out += "| :---: | :---: | :---: | :---: | :---: | :--- | :--- |\n"
        
        for ep_i, row in enumerate(sub.itertuples(), 1):
            t2_str = f"S5TH={row.th_t2:.1f}%, S5FI={row.fi_t2:.1f}%, n_dead={row.n_dead_t2}"
            exit_str = f"S5TH={row.th_exit:.1f}%, S5FI={row.fi_exit:.1f}%, SV5TW={row.v_tw_exit:.1f}%, n_dead={row.n_dead_exit}"
            spy_str = f"{row.spy_ret:+6.2f}%"
            md_out += f"| **{ep_i}** | {row.start} | {row.end} | {row.duration} | **{spy_str}** | {t2_str} | {exit_str} |\n"
            
        # Add 3 Statistical Lines
        max_dur, min_dur, avg_dur = sub['duration'].max(), sub['duration'].min(), sub['duration'].mean()
        max_spy, min_spy, avg_spy = sub['spy_ret'].max(), sub['spy_ret'].min(), sub['spy_ret'].mean()
        
        max_t2_th, min_t2_th, avg_t2_th = sub['th_t2'].max(), sub['th_t2'].min(), sub['th_t2'].mean()
        max_t2_fi, min_t2_fi, avg_t2_fi = sub['fi_t2'].max(), sub['fi_t2'].min(), sub['fi_t2'].mean()
        max_t2_nd, min_t2_nd, avg_t2_nd = sub['n_dead_t2'].max(), sub['n_dead_t2'].min(), sub['n_dead_t2'].mean()
        
        max_ex_th, min_ex_th, avg_ex_th = sub['th_exit'].max(), sub['th_exit'].min(), sub['th_exit'].mean()
        max_ex_fi, min_ex_fi, avg_ex_fi = sub['fi_exit'].max(), sub['fi_exit'].min(), sub['fi_exit'].mean()
        max_ex_vtw, min_ex_vtw, avg_ex_vtw = sub['v_tw_exit'].max(), sub['v_tw_exit'].min(), sub['v_tw_exit'].mean()
        max_ex_nd, min_ex_nd, avg_ex_nd = sub['n_dead_exit'].max(), sub['n_dead_exit'].min(), sub['n_dead_exit'].mean()
        
        md_out += f"| 🔴 | **ESTADÍSTICA** | **MÁXIMO** | **{max_dur}** | **{max_spy:+6.2f}%** | **S5TH={max_t2_th:.1f}%, S5FI={max_t2_fi:.1f}%, n_dead={max_t2_nd}** | **S5TH={max_ex_th:.1f}%, S5FI={max_ex_fi:.1f}%, SV5TW={max_ex_vtw:.1f}%, n_dead={max_ex_nd}** |\n"
        md_out += f"| 🔵 | **ESTADÍSTICA** | **MÍNIMO** | **{min_dur}** | **{min_spy:+6.2f}%** | **S5TH={min_t2_th:.1f}%, S5FI={min_t2_fi:.1f}%, n_dead={min_t2_nd}** | **S5TH={min_ex_th:.1f}%, S5FI={min_ex_fi:.1f}%, SV5TW={min_ex_vtw:.1f}%, n_dead={min_ex_nd}** |\n"
        md_out += f"| 🟢 | **ESTADÍSTICA** | **PROMEDIO** | **{avg_dur:.1f}** | **{avg_spy:+6.2f}%** | **S5TH={avg_t2_th:.1f}%, S5FI={avg_t2_fi:.1f}%, n_dead={avg_t2_nd:.1f}** | **S5TH={avg_ex_th:.1f}%, S5FI={avg_ex_fi:.1f}%, SV5TW={avg_ex_vtw:.1f}%, n_dead={avg_ex_nd:.1f}** |\n\n"

    with open("/root/.gemini/antigravity-ide/brain/747582b8-bd87-4653-8f63-949c0849b8a4/tabla_episodios_distribucion_agrupada.md", "w") as f:
        f.write(md_out)
        
    print("\n" + "="*115)
    print("      📊 TABLA AGRUPADA CON COLUMNA DE VARIACIÓN SPY GENERADA EXITOSAMENTE")
    print("="*115)
    print("📌 Se ha actualizado la tabla completa en: tabla_episodios_distribucion_agrupada.md")

if __name__ == "__main__":
    main()
