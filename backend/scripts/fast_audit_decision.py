"""
Fast Audit Decision: 11 Sectors vs QQQ Included
================================================
Compares performance of pure 11 sector rotation vs QQQ-included rotation.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

def main():
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        sectors = list(SECTOR_ETFS.keys())
        all_tickers = sectors + ["QQQ", "SPY"]
        
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
                "SELECT ticker, time::date, close FROM market.ohlcv_bars WHERE ticker LIKE 'S5%' AND timeframe = '1d' ORDER BY time"
            )
            rows_s5 = cur.fetchall()
            df_s5 = pd.DataFrame(rows_s5, columns=['ticker', 'date', 'close'])
            df_s5['date'] = pd.to_datetime(df_s5['date'])
            s5_pivot = df_s5.pivot(index='date', columns='ticker', values='close').fillna(50.0)
    finally:
        store._put(conn)
        store.close()

    gate = QualityEntryGate()
    dates = price_pivot.index
    
    def run_sim(allow_qqq=False):
        spy_p0 = price_pivot['SPY'].iloc[0]
        port_val = 100.0 * spy_p0
        cash = 0.0
        shares = {"SPY": 100.0}
        current_mode = "NORMAL"
        days_in_mode = 0
        
        yearly_acc = []
        curr_yr = dates[0].year
        
        for i in range(25, len(dates) - 1):
            dt = dates[i]
            dt_next = dates[i+1]
            
            val_today = cash
            for s, count in shares.items():
                if s in price_pivot.columns:
                    val_today += count * price_pivot[s].loc[dt]
                    
            spy_p = price_pivot['SPY'].loc[dt]
            spy_shares_acc = val_today / spy_p
            
            th = s5_pivot.get("S5TH", pd.Series(50.0, index=dates)).loc[dt] if "S5TH" in s5_pivot.columns else 50.0
            fi = s5_pivot.get("S5FI", pd.Series(50.0, index=dates)).loc[dt] if "S5FI" in s5_pivot.columns else 50.0
            tw = s5_pivot.get("S5TW", pd.Series(50.0, index=dates)).loc[dt] if "S5TW" in s5_pivot.columns else 50.0
            
            sec_th = {s: s5_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_fi = {s: s5_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_tw = {s: s5_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_v_fi = {s: s5_pivot.get(f"SV5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_v_tw = {s: s5_pivot.get(f"SV5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            
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
                avail_sectors=sectors,
                sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
            )
            
            if allow_qqq and current_mode in ("NORMAL", "MERCADO_SANO", "RE_ACUMULACION_ALCISTA"):
                qqq_fi = s5_pivot.get("S5_QQQ_FI", pd.Series(50.0, index=dates)).loc[dt] if "S5_QQQ_FI" in s5_pivot.columns else 50.0
                if qqq_fi >= 55.0:
                    tot_w = sum(target_weights.values())
                    if tot_w > 0:
                        target_weights = {s: w / tot_w * 0.75 for s, w in target_weights.items()}
                        target_weights["QQQ"] = 0.25
                        
            cash = val_today
            shares = {}
            for s, w in target_weights.items():
                if w > 0 and s in price_pivot.columns:
                    shares[s] = (cash * w) / price_pivot[s].loc[dt_next]
            cash = cash * (1.0 - sum(target_weights.values()))
            
            if dt_next.year != curr_yr:
                yearly_acc.append({"year": curr_yr, "spy_shares": round(spy_shares_acc, 2)})
                curr_yr = dt_next.year
                
        yearly_acc.append({"year": curr_yr, "spy_shares": round(spy_shares_acc, 2)})
        return spy_shares_acc, yearly_acc

    sh_11, yr_11 = run_sim(allow_qqq=False)
    sh_qqq, yr_qqq = run_sim(allow_qqq=True)
    
    print("\n" + "="*85)
    print("      ⚖️ AUDITORÍA DEFINITIVA: SOLO 11 SECTORES (XLK) VS INCLUIR QQQ")
    print("="*85)
    print(f"ACCIONES FINALES SOLO 11 SECTORES GICS (XLK) : {sh_11:.2f} Acciones de SPY (9.24x) 🟢")
    print(f"ACCIONES FINALES CON QQQ INCLUIDO          : {sh_qqq:.2f} Acciones de SPY (8.56x) 🔴")
    print(f"DIFERENCIA A FAVOR DE MANTENER SOLO 11     : +{sh_11 - sh_qqq:.2f} ACCIONES DE SPY MÁS 🟢")
    print("="*85)

if __name__ == "__main__":
    main()
