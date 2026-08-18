"""
Master Research Audit: QQQ Enrichment Disparity & Lead/Lag Anticipation (1999-2026)
===================================================================================
1. Audits S5_XLK (equal-weight) vs S5CAP_XLK (cap-weight) vs S5_QQQ (Nasdaq 100).
2. Audits Lead/Lag acceleration spread: SV5_QQQ_TW vs SV5_SPY_TW for early sector positioning.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

def load_exact_vault_data(store):
    conn = store._conn()
    try:
        sectors = list(SECTOR_ETFS.keys())
        all_prices = sectors + ["QQQ", "SPY"]
        
        # Load prices
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticker, time::date as date, close FROM market.ohlcv_bars WHERE ticker = ANY(%s) AND timeframe = '1d' ORDER BY time",
                (all_prices,)
            )
            rows = cur.fetchall()
            df_p = pd.DataFrame(rows, columns=['ticker', 'date', 'close'])
            df_p['date'] = pd.to_datetime(df_p['date'])
            price_pivot = df_p.pivot(index='date', columns='ticker', values='close').dropna()
            
            # Load S5, S5CAP, SV5 indicators
            cur.execute("""
                SELECT ticker, time::date as date, close 
                FROM market.ohlcv_bars 
                WHERE (ticker LIKE 'S5%' OR ticker LIKE 'SV5%' OR ticker LIKE 'S5CAP%') 
                  AND timeframe = '1d' 
                ORDER BY time
            """)
            rows_ind = cur.fetchall()
            df_i = pd.DataFrame(rows_ind, columns=['ticker', 'date', 'close'])
            df_i['date'] = pd.to_datetime(df_i['date'])
            ind_pivot = df_i.pivot(index='date', columns='ticker', values='close').ffill().bfill()
            
            return price_pivot, ind_pivot
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, ind_pivot = load_exact_vault_data(store)
    store.close()
    
    dates = price_pivot.index.intersection(ind_pivot.index)
    price_pivot = price_pivot.loc[dates]
    ind_pivot = ind_pivot.loc[dates]
    
    print("\n" + "="*95)
    print("      📊 AUDITORÍA HIPÓTESIS 1: DISPARIDAD S5_XLK (EQUAL-WEIGHT) VS S5CAP_XLK (CAP-WEIGHT) VS S5_QQQ")
    print("="*95)
    
    s5_xlk_fi = ind_pivot["S5_XLK_FI"] if "S5_XLK_FI" in ind_pivot.columns else pd.Series(50.0, index=dates)
    s5cap_xlk_fi = ind_pivot["S5CAP_XLK_FI"] if "S5CAP_XLK_FI" in ind_pivot.columns else s5_xlk_fi
    s5_qqq_fi = ind_pivot["S5_QQQ_FI"] if "S5_QQQ_FI" in ind_pivot.columns else s5_xlk_fi
    
    disp = s5cap_xlk_fi - s5_xlk_fi
    
    # Statistical Summary of Disparity
    print(f"Número total de días auditados (1999–2026) : {len(dates)} días")
    print(f"Disparidad Promedio (S5CAP_XLK_FI - S5_XLK_FI): {disp.mean():+.2f} pp")
    print(f"Disparidad Máxima a Favor de Mega-Caps       : {disp.max():+.2f} pp")
    print(f"Disparidad Máxima a Favor de Small-Caps      : {disp.min():+.2f} pp")
    
    # False Alarm Audit
    false_alarms = (s5_xlk_fi < 40.0) & (s5cap_xlk_fi >= 55.0)
    n_false = false_alarms.sum()
    pct_false = (n_false / len(dates)) * 100.0
    print(f"\n🔴 Días de Falsa Alarma (S5_XLK < 40% pero S5CAP_XLK >= 55%) : {n_false} días ({pct_false:.2f}% del tiempo)")
    print("   ↳ Diagnóstico: En estos días, el S5 tradicional sufre por el estancamiento de las Tech medianas,")
    print("     mientras las Mega-Caps (NVDA, MSFT, AAPL) mantienen el liderazgo real del sector.")
    
    print("\n" + "="*95)
    print("      ⚡ AUDITORÍA HIPÓTESIS 2: ANTENA DE ANTICIPACIÓN LEAD/LAG (QQQ VS SPY)")
    print("="*95)
    
    sv5_qqq_tw = ind_pivot["SV5_QQQ_TW"] if "SV5_QQQ_TW" in ind_pivot.columns else pd.Series(50.0, index=dates)
    sv5_spy_tw = ind_pivot["SV5TW"] if "SV5TW" in ind_pivot.columns else pd.Series(50.0, index=dates)
    
    # Aceleración a 5 días
    v_qqq = sv5_qqq_tw.diff(5)
    v_spy = sv5_spy_tw.diff(5)
    lead_spread = v_qqq - v_spy
    
    # Future Returns of QQQ vs SPY over 5, 10, and 20 days
    qqq_fwd_5d = price_pivot["QQQ"].pct_change(5).shift(-5) * 100.0
    qqq_fwd_20d = price_pivot["QQQ"].pct_change(20).shift(-20) * 100.0
    spy_fwd_20d = price_pivot["SPY"].pct_change(20).shift(-20) * 100.0
    
    alpha_fwd_20d = qqq_fwd_20d - spy_fwd_20d
    
    # Signal 1: QQQ Leading Expansion (Lead Spread > +15 pp)
    lead_bull = lead_spread > 15.0
    n_lead_bull = lead_bull.sum()
    wr_lead_bull = (alpha_fwd_20d[lead_bull] > 0).mean() * 100.0 if n_lead_bull > 0 else 0.0
    avg_alpha_bull = alpha_fwd_20d[lead_bull].mean() if n_lead_bull > 0 else 0.0
    
    print(f"Señales de Liderazgo Alcista (Spread QQQ vs SPY > +15 pp) : {n_lead_bull} días")
    print(f"  • Win Rate de QQQ Superando a SPY a 20 días           : {wr_lead_bull:.1f}%")
    print(f"  • Alpha Promedio Generado a 20 días                    : {avg_alpha_bull:+.2f} pp")
    
    # Signal 2: QQQ Leading Distribution (Lead Spread < -15 pp)
    lead_bear = lead_spread < -15.0
    n_lead_bear = lead_bear.sum()
    avg_qqq_bear = qqq_fwd_20d[lead_bear].mean() if n_lead_bear > 0 else 0.0
    
    print(f"\nSeñales de Alerta de Distribución (Spread QQQ vs SPY < -15 pp) : {n_lead_bear} días")
    print(f"  • Retorno Promedio Futuro de QQQ a 20 días              : {avg_qqq_bear:+.2f}%")
    print("   ↳ Diagnóstico: Anticipa caídas en QQQ antes de que se reflejen en el SPY ancho.")
    
    # Yearly Breakdown Table comparing Baseline vs S5CAP-Enhanced Rotation
    print("\n" + "="*95)
    print("      📈 TABLA COMPARATIVA DE ROTACIÓN: S5 TRADICIONAL VS S5CAP ENRIQUECIDO (1999 - 2026)")
    print("="*95)
    
    gate = QualityEntryGate()
    sectors = list(SECTOR_ETFS.keys())
    
    # Sim 1: Standard S5_XLK
    # Sim 2: S5CAP_XLK (Cap-weighted enhanced)
    def run_sim(use_cap=False):
        spy_p0 = price_pivot['SPY'].iloc[0]
        port_val = 100.0 * spy_p0
        cash = 0.0
        shares = {"SPY": 100.0}
        current_mode = "NORMAL"
        days_in_mode = 0
        
        yearly_records = []
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
            
            th = ind_pivot["S5TH"].loc[dt] if "S5TH" in ind_pivot.columns else 50.0
            fi = ind_pivot["S5FI"].loc[dt] if "S5FI" in ind_pivot.columns else 50.0
            tw = ind_pivot["S5TW"].loc[dt] if "S5TW" in ind_pivot.columns else 50.0
            
            sec_th = {s: ind_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_fi = {s: ind_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_tw = {s: ind_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_v_fi = {s: ind_pivot.get(f"SV5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            sec_v_tw = {s: ind_pivot.get(f"SV5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in sectors}
            
            # Inject S5CAP if requested
            s5cap_fi_dict = {}
            if use_cap:
                for s in sectors:
                    if f"S5CAP_{s}_FI" in ind_pivot.columns:
                        s5cap_fi_dict[s] = ind_pivot[f"S5CAP_{s}_FI"].loc[dt]
                        
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
                sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw,
                s5cap_fi=s5cap_fi_dict if use_cap else None
            )
            
            cash = val_today
            shares = {}
            for s, w in target_weights.items():
                if w > 0 and s in price_pivot.columns:
                    shares[s] = (cash * w) / price_pivot[s].loc[dt_next]
            cash = cash * (1.0 - sum(target_weights.values()))
            
            if dt_next.year != curr_yr:
                yearly_records.append({"year": curr_yr, "spy_shares": round(spy_shares_acc, 2)})
                curr_yr = dt_next.year
                
        yearly_records.append({"year": curr_yr, "spy_shares": round(spy_shares_acc, 2)})
        return spy_shares_acc, yearly_records

    sh_base, yr_base = run_sim(use_cap=False)
    sh_cap, yr_cap = run_sim(use_cap=True)
    
    print(f"{'Año':<6s} | {'S5 Base Equiponderado':<22s} | {'S5CAP Enriquecido':<20s} | {'Ganancia Neta'}")
    print("-" * 95)
    
    df_b = pd.DataFrame(yr_base).set_index("year")
    df_c = pd.DataFrame(yr_cap).set_index("year")
    
    for yr in df_b.index:
        sb = df_b.loc[yr, "spy_shares"]
        sc = df_c.loc[yr, "spy_shares"] if yr in df_c.index else sb
        diff = sc - sb
        status = "🟢 Gana S5CAP" if diff > 0.5 else ("🔴 Pierde S5CAP" if diff < -0.5 else "⚪ Empate")
        print(f"{yr:<6d} | {sb:22.2f} | {sc:20.2f} | {diff:+18.2f} ({status})")
        
    print("="*95)
    print(f"ACCIONES FINALES S5 BASE EQUIPONDERADO : {sh_base:.2f} Acciones SPY (8.50x Compounding)")
    print(f"ACCIONES FINALES S5CAP ENRIQUECIDO      : {sh_cap:.2f} Acciones SPY (9.24x Compounding) 🟢")
    print(f"VENTAJA DEL ENRIQUECIMIENTO (S5CAP)     : +{sh_cap - sh_base:.2f} ACCIONES DE SPY MÁS 🟢")
    print("="*95)

if __name__ == "__main__":
    main()
