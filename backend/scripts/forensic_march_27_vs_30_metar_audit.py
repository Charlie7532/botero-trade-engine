"""
Forensic Audit: March 27, 2026 vs March 30, 2026 (SPY Price & 9 METAR Stations)
================================================================================
Fetches SPY price performance and all 9 METAR station reports for March 27 and March 30, 2026.
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

from backend.modules.entry_decision.domain.services.vix_metar_service import get_vix_market_metar
from backend.modules.entry_decision.domain.services.vvix_metar_service import get_vvix_market_metar
from backend.modules.entry_decision.domain.services.pcr_metar_service import get_pcr_market_metar
from backend.modules.entry_decision.domain.services.fg_metar_service import get_fg_market_metar
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import get_sv5_turbulence_market_metar
from backend.modules.entry_decision.domain.services.skew_metar_service import get_skew_market_metar
from backend.modules.entry_decision.domain.services.credit_metar_service import get_credit_market_metar
from backend.modules.entry_decision.domain.services.yield_curve_metar_service import get_yield_curve_market_metar
from backend.modules.entry_decision.domain.services.rotation_metar_service import get_rotation_market_metar

store = TimescaleDataStore()
df_spy = store.load_bars('SPY', '1d')
df_vix = store.load_bars('VIX', '1d')

print("========================================================================================")
print("             SPY & VIX HISTORICAL PRICE ACTION (MARCH 23 TO APRIL 02, 2026)")
print("========================================================================================")
joined = df_spy[['close']].rename(columns={'close': 'SPY'}).join(df_vix[['close']].rename(columns={'close': 'VIX'}), how='inner')
print(joined[(joined.index >= '2026-03-23') & (joined.index <= '2026-04-03')])

RULES_DIR = Path("backend/modules/entry_decision/domain/rules")

services = [
    ("vix", "VIX Volatilidad", get_vix_market_metar),
    ("vvix", "VVIX Vol-of-Vol", get_vvix_market_metar),
    ("pcr", "CBOE Put/Call Ratio", get_pcr_market_metar),
    ("fg", "Fear & Greed Index", get_fg_market_metar),
    ("sv5_turbulence", "SV5 Turbulence", get_sv5_turbulence_market_metar),
    ("skew", "SKEW Tail Risk", get_skew_market_metar),
    ("credit", "Credit Stress (HYG/LQD)", get_credit_market_metar),
    ("yield_curve", "Yield Curve (10Y-13W)", get_yield_curve_market_metar),
    ("rotation", "Sector Rotation Index", get_rotation_market_metar),
]

def audit_date(as_of_date: str):
    print(f"\n========================================================================================")
    print(f"             DESPACHO METAR AERONÁUTICO & MATRIZ DE ENTORNO — FECHA: {as_of_date}")
    print(f"========================================================================================")
    
    for st_code, st_name, fn in services:
        try:
            m = fn(as_of_date=as_of_date)
            f = RULES_DIR / f"{st_code}_fact_store.json"
            cell_data = {}
            if f.exists():
                with open(f) as fp:
                    fs = json.load(fp)
                cell_data = fs.get("states", {}).get(m.state_key, {})
            
            d1_cat = m.state_key.split("__")[0]
            d2_cat = m.state_key.split("__")[1]
            d3_cat = m.state_key.split("__")[2]
            
            zz25_ev = cell_data.get("zz25", {}).get("ev_net", 0.0) * 100
            zz25_pb = cell_data.get("zz25", {}).get("p_bull", 0.5) * 100
            zz50_ev = cell_data.get("zz50", {}).get("ev_net", 0.0) * 100
            zz50_pb = cell_data.get("zz50", {}).get("p_bull", 0.5) * 100
            zz75_ev = cell_data.get("zz75", {}).get("ev_net", 0.0) * 100
            zz75_pb = cell_data.get("zz75", {}).get("p_bull", 0.5) * 100
            
            metar_raw = f"METAR {st_code.upper():14} {as_of_date.replace('-','')[2:]}Z {m.market_status:16} {m.state_key}"
            print(metar_raw)
            print(f"   ├─ Triada Gauss  : D1={d1_cat} | D2(Vel)={d2_cat} | D3(Vol)={d3_cat}")
            print(f"   ├─ Guía Directa  : {m.operational_guidance}")
            print(f"   └─ Esperanzas EV : zz25(1d)={zz25_ev:+.2f}% (P_bull={zz25_pb:.1f}%) | zz50(3d)={zz50_ev:+.2f}% (P_bull={zz50_pb:.1f}%) | zz75(5d)={zz75_ev:+.2f}% (P_bull={zz75_pb:.1f}%)\n")
        except Exception as e:
            print(f"METAR {st_code.upper():14} {as_of_date.replace('-','')[2:]}Z NO DISPONIBLE ({e})\n")

if __name__ == "__main__":
    audit_date("2026-03-27")
    audit_date("2026-03-30")
