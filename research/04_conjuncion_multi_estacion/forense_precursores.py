#!/usr/bin/env python3
"""
Forense de precursores de crash — ¿qué vectores de estado predicen el fracaso?

Para cada señal registrada:
1. Divide fires en WINNERS (fwd > 0) y LOSERS (fwd < 0)
2. Para cada estación, compara distribución D1/D2/D3 en LOSERS vs WINNERS
3. Calcula lift = P(state | LOSER) / P(state | WINNER) 
   lift > 1 = estado sobrerepresentado en crashes → WARNING
   lift < 1 = estado protector
4. Reporta los top precursores con lift > 1.5 y N >= 5
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from collections import defaultdict

# Import signals — directory starts with '01_', can't use normal import
import importlib.util
from research._lib.research_paths import ROOT
_spec = importlib.util.spec_from_file_location(
    "medir_senal", ROOT / "research" / "01_señales_entry_exit" / "medir_senal.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SEÑALES, cargar_datos = _mod.SEÑALES, _mod.cargar_datos

STATIONS = ['vix', 'vvix', 'pcr', 'fg', 'sv5_turbulence', 'skew',
            'credit', 'yield_curve', 'rotation', 'bsi', 'dxy']


def analizar_precursores(señal_nombre, df, forward_col="next_leg"):
    """Compara vectores de estado entre WINNERS y LOSERS de una señal."""
    if señal_nombre not in SEÑALES:
        return None
    
    señal = SEÑALES[señal_nombre](df).astype(bool)
    
    if forward_col == "next_leg":
        fwd = df["prev_leg_return"].shift(-1)
    else:
        fwd = df[forward_col]
    
    mask_activa = señal & fwd.notna()
    winners = mask_activa & (fwd > 0)
    losers = mask_activa & (fwd <= 0)
    
    n_win = int(winners.sum())
    n_lose = int(losers.sum())
    
    if n_win < 5 or n_lose < 3:
        return None
    
    resultados = {
        "señal": señal_nombre,
        "n_total": int(mask_activa.sum()),
        "n_winners": n_win,
        "n_losers": n_lose,
        "wr": round(n_win / (n_win + n_lose), 4),
        "precursores": [],
        "protectores": [],
        "by_station": {},
    }
    
    for station in STATIONS:
        sk_col = f"{station}_sk"
        if sk_col not in df.columns:
            continue
        
        sk_series = df[sk_col]
        parts = sk_series.str.split("__", expand=True)
        if parts.shape[1] < 3:
            continue
        
        d1 = parts[0]
        d2 = parts[1]
        d3 = parts[2]
        
        station_analysis = {"d1": {}, "d2": {}, "d3": {}, "d1xd2": {}}
        
        for dim_name, dim_series in [("d1", d1), ("d2", d2), ("d3", d3)]:
            win_dist = dim_series[winners].value_counts(normalize=True)
            lose_dist = dim_series[losers].value_counts(normalize=True)
            win_counts = dim_series[winners].value_counts()
            lose_counts = dim_series[losers].value_counts()
            
            all_states = set(win_dist.index) | set(lose_dist.index)
            
            for state in sorted(all_states):
                if pd.isna(state):
                    continue
                p_win = win_dist.get(state, 0)
                p_lose = lose_dist.get(state, 0)
                n_w = int(win_counts.get(state, 0))
                n_l = int(lose_counts.get(state, 0))
                
                if n_w + n_l < 3:
                    continue
                
                lift = p_lose / p_win if p_win > 0.01 else (10.0 if p_lose > 0 else 1.0)
                
                entry = {
                    "station": station,
                    "dim": dim_name,
                    "state": state,
                    "n_win": n_w,
                    "n_lose": n_l,
                    "pct_win": round(p_win * 100, 1),
                    "pct_lose": round(p_lose * 100, 1),
                    "lift": round(lift, 2),
                }
                
                station_analysis[dim_name][state] = entry
                
                if lift >= 1.5 and n_l >= 3:
                    resultados["precursores"].append(entry)
                elif lift <= 0.5 and n_w >= 3:
                    resultados["protectores"].append(entry)
        
        # D1×D2 cross (most informative)
        d1d2 = d1.astype(str) + "×" + d2.astype(str)
        win_dist_x = d1d2[winners].value_counts(normalize=True)
        lose_dist_x = d1d2[losers].value_counts(normalize=True)
        win_counts_x = d1d2[winners].value_counts()
        lose_counts_x = d1d2[losers].value_counts()
        
        for state in sorted(set(win_dist_x.index) | set(lose_dist_x.index)):
            if "nan" in state:
                continue
            p_win = win_dist_x.get(state, 0)
            p_lose = lose_dist_x.get(state, 0)
            n_w = int(win_counts_x.get(state, 0))
            n_l = int(lose_counts_x.get(state, 0))
            
            if n_w + n_l < 3:
                continue
            
            lift = p_lose / p_win if p_win > 0.01 else (10.0 if p_lose > 0 else 1.0)
            
            entry = {
                "station": station,
                "dim": "d1×d2",
                "state": state,
                "n_win": n_w,
                "n_lose": n_l,
                "pct_win": round(p_win * 100, 1),
                "pct_lose": round(p_lose * 100, 1),
                "lift": round(lift, 2),
            }
            
            station_analysis["d1xd2"][state] = entry
            
            if lift >= 1.5 and n_l >= 3:
                resultados["precursores"].append(entry)
            elif lift <= 0.5 and n_w >= 5:
                resultados["protectores"].append(entry)
        
        resultados["by_station"][station] = station_analysis
    
    resultados["precursores"].sort(key=lambda x: -x["lift"])
    resultados["protectores"].sort(key=lambda x: x["lift"])
    
    return resultados


def main():
    df, spy = cargar_datos()
    
    target_signals = [
        'credit_easing_k1', 'pcr_put_panic', 'bsi_washed_out',
        'credit_stress', 'vvix_entry', 'capitulacion',
    ]
    
    all_results = {}
    
    for sig in target_signals:
        print(f"\n{'='*100}")
        print(f"FORENSE: {sig}")
        print(f"{'='*100}")
        
        res = analizar_precursores(sig, df)
        if res is None:
            print(f"  Insuficientes datos")
            continue
        
        all_results[sig] = res
        
        print(f"  Total={res['n_total']}  W={res['n_winners']}  L={res['n_losers']}  WR={res['wr']:.1%}")
        
        print(f"\n  🔴 PRECURSORES DE CRASH (lift ≥ 1.5, N_lose ≥ 3):")
        if not res["precursores"]:
            print(f"    Ninguno encontrado")
        else:
            for p in res["precursores"][:15]:
                print(f"    lift={p['lift']:5.2f}  {p['station']:18s}.{p['dim']:5s} = {p['state']:45s}  "
                      f"W={p['n_win']:3d}({p['pct_win']:5.1f}%)  L={p['n_lose']:3d}({p['pct_lose']:5.1f}%)")
        
        print(f"\n  🟢 PROTECTORES (lift ≤ 0.5, N_win ≥ 3):")
        if not res["protectores"]:
            print(f"    Ninguno encontrado")
        else:
            for p in res["protectores"][:10]:
                print(f"    lift={p['lift']:5.2f}  {p['station']:18s}.{p['dim']:5s} = {p['state']:45s}  "
                      f"W={p['n_win']:3d}({p['pct_win']:5.1f}%)  L={p['n_lose']:3d}({p['pct_lose']:5.1f}%)")
    
    # Cross-signal: universal precursors
    print(f"\n\n{'='*100}")
    print(f"PRECURSORES UNIVERSALES (aparecen en ≥2 señales)")
    print(f"{'='*100}")
    
    precursor_counts = defaultdict(list)
    for sig, res in all_results.items():
        for p in res.get("precursores", []):
            key = f"{p['station']}.{p['dim']}={p['state']}"
            precursor_counts[key].append({"signal": sig, "lift": p["lift"], "n_lose": p["n_lose"]})
    
    universal = [(k, v) for k, v in precursor_counts.items() if len(v) >= 2]
    universal.sort(key=lambda x: -len(x[1]))
    
    for key, signals in universal:
        sigs = ", ".join(f"{s['signal']}(lift={s['lift']:.1f},N={s['n_lose']})" for s in signals)
        print(f"  {key:60s}  → {len(signals)} señales: {sigs}")


if __name__ == "__main__":
    main()
