"""
Multi-Asset Zigzag Breadth Spectrum Generator (SPY, QQQ, 11 Sector ETFs)
=======================================================================
Generates multi-asset spectrum signatures for 2.5%, 5.0%, 7.5% Zigzags across:
  - SPY (Broad Market)
  - QQQ (Tech / Growth Leader)
  - 11 Sector ETFs (XLK, XLC, XLF, XLI, XLV, XLP, XLU, XLRE, XLB, XLE, XLY)
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
TARGET_ASSETS = ["SPY", "QQQ"] + SECTORS_11

BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def identify_zigzag(series, threshold_pct=0.05):
    p = series.values
    n = len(p)
    pivots = np.zeros(n, dtype=int)
    if n == 0:
        return pivots

    up = True
    last_p_idx = 0
    last_p_val = p[0]
    
    for i in range(1, n):
        val = p[i]
        if up:
            if val > last_p_val:
                last_p_val = val
                last_p_idx = i
            elif val <= last_p_val * (1.0 - threshold_pct):
                pivots[last_p_idx] = 1
                up = False
                last_p_val = val
                last_p_idx = i
        else:
            if val < last_p_val:
                last_p_val = val
                last_p_idx = i
            elif val >= last_p_val * (1.0 + threshold_pct):
                pivots[last_p_idx] = -1
                up = True
                last_p_val = val
                last_p_idx = i
    return pivots

def load_data(store):
    conn = store._conn()
    try:
        all_tickers = TARGET_ASSETS + list(BREADTH_MAP.keys())
        # Also include sector-specific S5 indicators
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

def clean_val(val, default=0.0):
    if val is None or pd.isna(val) or np.isnan(val) or np.isinf(val):
        return default
    return round(float(val), 2)

def clean_mean(arr, default=0.0):
    valid = [v for v in arr if v is not None and not pd.isna(v) and not np.isnan(v)]
    if not valid:
        return default
    return clean_val(np.mean(valid), default)

def main():
    store = TimescaleDataStore()
    pivot = load_data(store)
    store.close()
    
    scales = [
        ("zz_2.5", 0.025, "PULLBACK_TACTICO", "Retroceso menor en tendencia alcista (2.5%)"),
        ("zz_5.0", 0.050, "CORRECCION_MENOR", "Corrección de mediano plazo (5.0%)"),
        ("zz_7.5", 0.075, "CORRECCION_MAYOR", "Corrección severa de largo plazo (7.5%)")
    ]
    
    spectrum_data = {
        "version": "v36.2_multi_asset",
        "generated_by": "Marcos Lopez de Prado - Quant Engine",
        "description": "Firma espectral de velocidad y aceleración por activo (SPY, QQQ, 11 Sectores) alrededor de giros Zigzag (2.5%, 5.0%, 7.5%)",
        "entities": TARGET_ASSETS,
        "scales": {}
    }
    
    for key, thresh, name, desc in scales:
        scale_obj = {
            "name": name,
            "description": desc,
            "assets": {}
        }
        
        for asset in TARGET_ASSETS:
            if asset not in pivot.columns:
                continue
                
            df_asset = pd.DataFrame(index=pivot.index)
            df_asset['price'] = pivot[asset]
            
            # Determine breadth source (Broad market for SPY/QQQ, sector-specific for Sector ETFs)
            if asset in ["SPY", "QQQ"]:
                df_asset['tw'] = pivot['S5TW'] if 'S5TW' in pivot.columns else 50.0
                df_asset['v_tw'] = pivot['SV5TW'] if 'SV5TW' in pivot.columns else 50.0
            else:
                df_asset['tw'] = pivot[f'S5_{asset}_TW'] if f'S5_{asset}_TW' in pivot.columns else pivot['S5TW']
                df_asset['v_tw'] = pivot[f'SV5_{asset}_TW'] if f'SV5_{asset}_TW' in pivot.columns else pivot['SV5TW']
                
            df_asset['vel_tw'] = df_asset['tw'].diff(1)
            df_asset['acel_tw'] = df_asset['vel_tw'].diff(1)
            df_asset['sv5_div'] = df_asset['v_tw'] - df_asset['tw']
            
            zz_col = 'zz'
            df_asset[zz_col] = identify_zigzag(df_asset['price'], thresh)
            
            bottoms_idx = [i for i in np.where(df_asset[zz_col] == -1)[0] if 5 <= i < len(df_asset) - 5]
            tops_idx = [i for i in np.where(df_asset[zz_col] == 1)[0] if 5 <= i < len(df_asset) - 5]
            
            asset_obj = {
                "pivots": {
                    "bottom": {
                        "total_events": len(bottoms_idx),
                        "window_spectrum": {}
                    },
                    "top": {
                        "total_events": len(tops_idx),
                        "window_spectrum": {}
                    }
                }
            }
            
            # Bottom spectrum
            for offset in range(-5, 6):
                off_str = f"t{offset:+d}" if offset != 0 else "t_zero"
                v_tw_vals = [df_asset['vel_tw'].iloc[i+offset] for i in bottoms_idx]
                a_tw_vals = [df_asset['acel_tw'].iloc[i+offset] for i in bottoms_idx]
                div_vals  = [df_asset['sv5_div'].iloc[i+offset] for i in bottoms_idx]
                s5_tw_vals = [df_asset['tw'].iloc[i+offset] for i in bottoms_idx]
                
                asset_obj["pivots"]["bottom"]["window_spectrum"][off_str] = {
                    "v_tw_mean": clean_mean(v_tw_vals),
                    "a_tw_mean": clean_mean(a_tw_vals),
                    "sv5_div_mean": clean_mean(div_vals),
                    "s5_tw_mean": clean_mean(s5_tw_vals)
                }
                
            # Top spectrum
            for offset in range(-5, 6):
                off_str = f"t{offset:+d}" if offset != 0 else "t_zero"
                v_tw_vals = [df_asset['vel_tw'].iloc[i+offset] for i in tops_idx]
                a_tw_vals = [df_asset['acel_tw'].iloc[i+offset] for i in tops_idx]
                div_vals  = [df_asset['sv5_div'].iloc[i+offset] for i in tops_idx]
                s5_tw_vals = [df_asset['tw'].iloc[i+offset] for i in tops_idx]
                
                asset_obj["pivots"]["top"]["window_spectrum"][off_str] = {
                    "v_tw_mean": clean_mean(v_tw_vals),
                    "a_tw_mean": clean_mean(a_tw_vals),
                    "sv5_div_mean": clean_mean(div_vals),
                    "s5_tw_mean": clean_mean(s5_tw_vals)
                }
                
            scale_obj["assets"][asset] = asset_obj
            
        spectrum_data["scales"][key] = scale_obj
        
    out_dir = "/root/botero-trade/backend/modules/entry_decision/infrastructure"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "zigzag_spectrum_signatures.json")
    
    with open(out_path, "w") as f:
        json.dump(spectrum_data, f, indent=2)
        
    print(f"✅ Archivo Multi-Activo JSON de Espectro Generado Exitosamente: {out_path}")

if __name__ == "__main__":
    main()
