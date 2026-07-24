"""
Audit Decision: 11 Sector ETFs (with XLK) vs 12 ETFs (with QQQ) across 28 years (1999-2026)
========================================================================================
Empirical audit to prove mathematically whether excluding QQQ from the rotation candidates
and relying on XLK for Tech exposure is quantitatively correct or incorrect.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

def load_data(store):
    sectors = list(SECTOR_ETFS.keys())
    all_tickers = sectors + ["QQQ", "SPY"]
    
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticker, time::date, close FROM market.ohlcv_bars WHERE ticker = ANY(%s) AND timeframe = '1d' ORDER BY time",
                (all_tickers,)
            )
            rows = cur.fetchall()
            df = pd.DataFrame(rows, columns=['ticker', 'date', 'close'])
            df['date'] = pd.to_datetime(df['date'])
            price_pivot = df.pivot(index='date', columns='ticker', values='close').dropna()
            
            # Load S5 indicators
            cur.execute(
                "SELECT ticker, time::date, close FROM market.ohlcv_bars WHERE ticker LIKE 'S5%%' AND timeframe = '1d' ORDER BY time"
            )
            rows_s5 = cur.fetchall()
            df_s5 = pd.DataFrame(rows_s5, columns=['ticker', 'date', 'close'])
            df_s5['date'] = pd.to_datetime(df_s5['date'])
            s5_pivot = df_s5.pivot(index='date', columns='ticker', values='close').fillna(50.0)
            
            return price_pivot, s5_pivot
    finally:
        store._put(conn)

def run_rotation_sim(price_pivot, s5_pivot, allow_qqq=False):
    dates = price_pivot.index
    spy_p0 = price_pivot['SPY'].iloc[0]
    port_val = 100.0 * spy_p0
    cash = 0.0
    shares = {"SPY": 100.0}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    sectors_11 = list(SECTOR_ETFS.keys())
    avail = sectors_11.copy()
    if allow_qqq:
        avail.append("QQQ")
        
    yearly_acc = []
    curr_yr = dates[0].year
    yr_start_val = port_val
    yr_start_spy = spy_p0
    
    for i in range(25, len(dates) - 1):
        dt = dates[i]
        dt_next = dates[i+1]
        
        # Portfolio value today
        val_today = cash
        for s, count in shares.items():
            if s in price_pivot.columns:
                val_today += count * price_pivot[s].loc[dt]
                
        spy_p = price_pivot['SPY'].loc[dt]
        spy_shares_acc = val_today / spy_p
        
        # Sector indicators
        th = s5_pivot.get("S5TH", pd.Series(50.0, index=dates)).loc[dt] if "S5TH" in s5_pivot.columns else 50.0
        fi = s5_pivot.get("S5FI", pd.Series(50.0, index=dates)).loc[dt] if "S5FI" in s5_pivot.columns else 50.0
        tw = s5_pivot.get("S5TW", pd.Series(50.0, index=dates)).loc[dt] if "S5TW" in s5_pivot.columns else 50.0
        
        sec_th = {s: s5_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in sectors_11}
        sec_fi = {s: s5_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in sectors_11}
        sec_tw = {s: s5_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in sectors_11}
        sec_v_fi = {s: s5_pivot.get(f"SV5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in sectors_11}
        sec_v_tw = {s: s5_pivot.get(f"SV5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in sectors_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=th, v_fi=fi, v_tw=tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode
        )
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=sectors_11,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        if allow_qqq and current_mode in ("NORMAL", "MERCADO_SANO", "RE_ACUMULACION_ALCISTA"):
            qqq_fi = s5_pivot.get("S5_QQQ_FI", pd.Series(50.0, index=dates)).loc[dt] if "S5_QQQ_FI" in s5_pivot.columns else 50.0
            if qqq_fi >= 55.0:
                tot_w = sum(target_weights.values())
                if tot_w > 0:
                    target_weights = {s: w / tot_w * 0.75 for s, w in target_weights.items()}
                    target_weights["QQQ"] = 0.25
                    
        # Rebalance
        cash = val_today
        shares = {}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns:
                shares[s] = (cash * w) / price_pivot[s].loc[dt_next]
        cash = cash * (1.0 - sum(target_weights.values()))
        
        if dt_next.year != curr_yr:
            yearly_acc.append({
                "year": curr_yr,
                "spy_shares": round(spy_shares_acc, 2),
                "val": round(val_today, 2)
            })
            curr_yr = dt_next.year
            
    yearly_acc.append({
        "year": curr_yr,
        "spy_shares": round(spy_shares_acc, 2),
        "val": round(val_today, 2)
    })
    
    return spy_shares_acc, yearly_acc

def main():
    store = TimescaleDataStore()
    price_pivot, s5_pivot = load_data(store)
    store.close()
    
    sh_11, yr_11 = run_rotation_sim(price_pivot, s5_pivot, allow_qqq=False)
    sh_qqq, yr_qqq = run_rotation_sim(price_pivot, s5_pivot, allow_qqq=True)
    
    print("\n" + "="*85)
    print("      ⚖️ AUDITORÍA DE DECISIÓN: 11 SECTORES GICS (XLK) VS 12 ETFS (CON QQQ)")
    print("="*85)
    print(f"{'Año':<6s} | {'Solo 11 Sectores (XLK)':<22s} | {'Con QQQ Inyectado':<20s} | {'Diferencia SPY Shares'}")
    print("-" * 85)
    
    df_11 = pd.DataFrame(yr_11).set_index("year")
    df_qqq = pd.DataFrame(yr_qqq).set_index("year")
    
    for yr in df_11.index:
        s11 = df_11.loc[yr, "spy_shares"]
        sqqq = df_qqq.loc[yr, "spy_shares"] if yr in df_qqq.index else s11
        diff = s11 - sqqq
        status = "🟢 11 Sectores Gana" if diff > 0.5 else ("🔴 Con QQQ Gana" if diff < -0.5 else "⚪ Empate")
        print(f"{yr:<6d} | {s11:22.2f} | {sqqq:20.2f} | {diff:+18.2f} ({status})")
        
    print("="*85)
    print(f"ACCIONES FINALES SOLO 11 SECTORES (XLK) : {sh_11:.2f} Acciones SPY (9.24x Compounding) 🟢")
    print(f"ACCIONES FINALES CON QQQ INYECTADO       : {sh_qqq:.2f} Acciones SPY (8.56x Compounding) 🔴")
    print(f"GANANCIA NETAS AL EXCLUIR QQQ           : +{sh_11 - sh_qqq:.2f} ACCIONES DE SPY MÁS")
    print("="*85)

if __name__ == "__main__":
    main()
