"""
Molienda de Datos Integrada: Estereotipos/Tendencias × Fusión (Macro y Micro)
===========================================================================
Determina la certeza y tasa de fracaso de:
  1. Las 9 Celdas de Fusión Macro (ej. P_COLD × V_HOT)
  2. Las combinaciones crudas de Tríadas Micro (s5_key, s5v_key)

Frente a:
  - Giros estructurados (HH, LH, HL, LL) en t-2 y t-3.
  - Regímenes de tendencia anidados (8 estados continuos UP/DN).
"""
import sys
import os
import json
from datetime import datetime, timezone
from collections import defaultdict

sys.path.append("/root/botero-trade")
os.chdir("/root/botero-trade")
from dotenv import load_dotenv
load_dotenv(".env")

import pandas as pd
import numpy as np
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# 1. Cargar configuraciones de Tríadas para Bins
with open("backend/modules/entry_decision/domain/rules/s5_triad_table.json") as f:
    s5_table = json.load(f)
with open("backend/modules/entry_decision/domain/rules/s5v_triad_table.json") as f:
    s5v_table = json.load(f)

bin_edges = s5_table["bin_edges"]
bin_labels = s5_table["bin_labels"]

def classify_bin(value, edges):
    for i, edge in enumerate(edges):
        if value < edge:
            return bin_labels[i]
    return bin_labels[-1]

def get_regime_label(value):
    if value < 30.0:
        return "COLD"
    elif value > 70.0:
        return "HOT"
    return "NEUTRAL"

def compute_zigzag(prices, pct_threshold):
    n = len(prices)
    if n < 10:
        return pd.Series(0, index=prices.index)
    threshold = pct_threshold / 100.0
    direction = 1
    last_pivot_price = prices.iloc[0]
    last_pivot_idx = 0
    pivots = pd.Series(0, index=prices.index)
    for i in range(1, n):
        p = prices.iloc[i]
        if direction == 1:
            if p > last_pivot_price:
                last_pivot_price = p
                last_pivot_idx = i
            elif p <= last_pivot_price * (1 - threshold):
                pivots.iloc[last_pivot_idx] = 1
                last_pivot_price = p
                last_pivot_idx = i
                direction = -1
        else:
            if p < last_pivot_price:
                last_pivot_price = p
                last_pivot_idx = i
            elif p >= last_pivot_price * (1 + threshold):
                pivots.iloc[last_pivot_idx] = -1
                last_pivot_price = p
                last_pivot_idx = i
                direction = 1
    return pivots

def classify_stereotypes(prices, pivots):
    stereotypes = pd.Series("NONE", index=prices.index)
    pivot_indices = pivots[pivots != 0].index
    
    for i in range(2, len(pivot_indices)):
        curr_idx = pivot_indices[i]
        prev_same_idx = pivot_indices[i-2]
        
        curr_price = prices.loc[curr_idx]
        prev_price = prices.loc[prev_same_idx]
        
        if pivots.loc[curr_idx] == 1: # Techo (Zig)
            if curr_price > prev_price:
                stereotypes.loc[curr_idx] = "HH"
            else:
                stereotypes.loc[curr_idx] = "LH"
        elif pivots.loc[curr_idx] == -1: # Suelo (Zag)
            if curr_price > prev_price:
                stereotypes.loc[curr_idx] = "HL"
            else:
                stereotypes.loc[curr_idx] = "LL"
                
    return stereotypes

def get_trend_regimes(prices, pivots_75, pivots_50, pivots_25):
    def get_dir_series(pivots):
        dir_series = pd.Series(index=prices.index, dtype=float)
        dir_series.loc[pivots == -1] = 1.0
        dir_series.loc[pivots == 1] = -1.0
        dir_series = dir_series.ffill().fillna(1.0)
        return dir_series.apply(lambda x: "UP" if x > 0 else "DN")

    t_75 = get_dir_series(pivots_75)
    t_50 = get_dir_series(pivots_50)
    t_25 = get_dir_series(pivots_25)
    
    return t_75 + "|" + t_50 + "|" + t_25

# Inicializar almacenamiento
store = TimescaleDataStore()
sectors = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLI", "XLE", "XLU", "XLRE", "XLB", "XLC"]
scales = [2.5, 5.0, 7.5]

# Estructura de resultados finales (Macro y Micro)
results = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "methodology": "Validación out-of-sample y concurrente cruzando niveles Macro (9 celdas) y Micro (combinaciones crudas).",
    "macro": {
        "trend_regimes": {},
        "pivot_stereotypes": {}
    },
    "micro": {
        "trend_regimes": {},
        "pivot_stereotypes": {}
    }
}

csv_rows = []
total_counts_micro = defaultdict(int)
total_counts_macro = defaultdict(int)

# Molienda por ETF
for etf in sectors:
    print(f"Moliendo datos para {etf}...")
    
    price = store.load_bars(etf, "1d")
    s5_th = store.load_bars(f"S5_{etf}_TH", "1d")
    s5_fi = store.load_bars(f"S5_{etf}_FI", "1d")
    s5_tw = store.load_bars(f"S5_{etf}_TW", "1d")
    
    s5v_th = store.load_bars(f"SV5_{etf}_TH", "1d")
    s5v_fi = store.load_bars(f"SV5_{etf}_FI", "1d")
    s5v_tw = store.load_bars(f"SV5_{etf}_TW", "1d")
    
    if any(x is None or x.empty for x in [price, s5_th, s5_fi, s5_tw, s5v_th, s5v_fi, s5v_tw]):
        print(f"  {etf}: Saltado por datos incompletos")
        continue
        
    common = price.index.intersection(s5_th.index).intersection(s5_fi.index).intersection(s5_tw.index)
    common = common.intersection(s5v_th.index).intersection(s5v_fi.index).intersection(s5v_tw.index)
    
    df = pd.DataFrame({
        "price": price.loc[common, "close"].astype(float),
        "s5_th": s5_th.loc[common, "close"].astype(float),
        "s5_fi": s5_fi.loc[common, "close"].astype(float),
        "s5_tw": s5_tw.loc[common, "close"].astype(float),
        "s5v_th": s5v_th.loc[common, "close"].astype(float),
        "s5v_fi": s5v_fi.loc[common, "close"].astype(float),
        "s5v_tw": s5v_tw.loc[common, "close"].astype(float),
    }).sort_index()
    
    df["s5_tw_diff"] = df["s5_tw"].diff(1)
    df["s5v_tw_diff"] = df["s5v_tw"].diff(1)
    df = df.dropna()
    
    # ── 1. CLASIFICACIÓN MICRO (Tríadas Crudas) ──
    df["s5_key"] = (
        df["s5_th"].apply(lambda v: classify_bin(v, bin_edges["TH"])) + "|" +
        df["s5_fi"].apply(lambda v: classify_bin(v, bin_edges["FI"])) + "|" +
        df["s5_tw"].apply(lambda v: classify_bin(v, bin_edges["TW"])) + "|" +
        df["s5_tw_diff"].apply(lambda v: "+" if v > 0 else "-")
    )
    df["s5v_key"] = (
        df["s5v_th"].apply(lambda v: classify_bin(v, bin_edges["TH"])) + "|" +
        df["s5v_fi"].apply(lambda v: classify_bin(v, bin_edges["FI"])) + "|" +
        df["s5v_tw"].apply(lambda v: classify_bin(v, bin_edges["TW"])) + "|" +
        df["s5v_tw_diff"].apply(lambda v: "+" if v > 0 else "-")
    )
    
    # ── 2. CLASIFICACIÓN MACRO (9 Celdas de Fusión) ──
    df["p_regime"] = df["s5_fi"].apply(get_regime_label)
    df["v_regime"] = df["s5v_fi"].apply(get_regime_label)
    df["macro_cell"] = "P_" + df["p_regime"] + " × V_" + df["v_regime"]
    
    # Contar ocurrencias totales del par en todo el dataset (acumulado global)
    for i in range(len(df)):
        pair = (df.iloc[i]["s5_key"], df.iloc[i]["s5v_key"])
        total_counts_micro[pair] += 1
        total_counts_macro[df.iloc[i]["macro_cell"]] += 1
        
    # Calcular ZigZags y Tendencias
    p_75 = compute_zigzag(df["price"], 7.5)
    p_50 = compute_zigzag(df["price"], 5.0)
    p_25 = compute_zigzag(df["price"], 2.5)
    df["trend_regime"] = get_trend_regimes(df["price"], p_75, p_50, p_25)
    
    # ── A. PROCESAR TENDENCIAS CONTINUAS (Dimensión B) ──
    for i in range(len(df)):
        row = df.iloc[i]
        regime = row["trend_regime"]
        macro = row["macro_cell"]
        s5_key = row["s5_key"]
        s5v_key = row["s5v_key"]
        pair_str = f"({s5_key} × {s5v_key})"
        
        # Registrar en CSV
        csv_rows.append({
            "date": df.index[i].strftime("%Y-%m-%d"),
            "sector": etf,
            "price": row["price"],
            "s5_key": s5_key,
            "s5v_key": s5v_key,
            "macro_cell": macro,
            "trend_triad": regime,
            "pivot_type": "NONE",
            "stereotype": "NONE",
            "days_to_pivot": 0
        })
        
        # Macro Trends
        if regime not in results["macro"]["trend_regimes"]:
            results["macro"]["trend_regimes"][regime] = {"total_days": 0, "signals": {}}
        results["macro"]["trend_regimes"][regime]["total_days"] += 1
        
        node_macro = results["macro"]["trend_regimes"][regime]["signals"]
        if macro not in node_macro:
            node_macro[macro] = {"coincidences": 0, "total_observed": 0}
        node_macro[macro]["coincidences"] += 1
        
        # Micro Trends
        if regime not in results["micro"]["trend_regimes"]:
            results["micro"]["trend_regimes"][regime] = {"total_days": 0, "signals": {}}
        results["micro"]["trend_regimes"][regime]["total_days"] += 1
        
        node_micro = results["micro"]["trend_regimes"][regime]["signals"]
        if pair_str not in node_micro:
            node_micro[pair_str] = {"coincidences": 0, "total_observed": 0}
        node_micro[pair_str]["coincidences"] += 1
        
    # ── B. PROCESAR PUNTOS DE GIRO (Dimensión A) ──
    for scale in scales:
        scale_key = f"scale_{scale:.1f}"
        
        # Inicializar nodos
        if scale_key not in results["macro"]["pivot_stereotypes"]:
            results["macro"]["pivot_stereotypes"][scale_key] = {"Zig": {"HH": {}, "LH": {}}, "Zag": {"HL": {}, "LL": {}}}
        if scale_key not in results["micro"]["pivot_stereotypes"]:
            results["micro"]["pivot_stereotypes"][scale_key] = {"Zig": {"HH": {}, "LH": {}}, "Zag": {"HL": {}, "LL": {}}}
            
        pivots = p_75 if scale == 7.5 else p_50 if scale == 5.0 else p_25
        stereotypes = classify_stereotypes(df["price"], pivots)
        
        pivot_indices = pivots[pivots != 0].index
        for idx in pivot_indices:
            loc = df.index.get_loc(idx)
            ster = stereotypes.loc[idx]
            p_type = "Zig" if pivots.loc[idx] == 1 else "Zag"
            
            if ster == "NONE":
                continue
                
            for offset in [2, 3]:
                signal_loc = loc - offset
                if signal_loc >= 0:
                    row = df.iloc[signal_loc]
                    s5_key = row["s5_key"]
                    s5v_key = row["s5v_key"]
                    pair_str = f"({s5_key} × {s5v_key})"
                    macro = row["macro_cell"]
                    
                    csv_rows.append({
                        "date": df.index[signal_loc].strftime("%Y-%m-%d"),
                        "sector": etf,
                        "price": row["price"],
                        "s5_key": s5_key,
                        "s5v_key": s5v_key,
                        "macro_cell": macro,
                        "trend_triad": row["trend_regime"],
                        "pivot_type": p_type,
                        "stereotype": ster,
                        "days_to_pivot": offset
                    })
                    
                    # Macro Pivots
                    node_macro = results["macro"]["pivot_stereotypes"][scale_key][p_type][ster]
                    if macro not in node_macro:
                        node_macro[macro] = {"coincidences": 0, "total_observed": 0}
                    node_macro[macro]["coincidences"] += 1
                    
                    # Micro Pivots
                    node_micro = results["micro"]["pivot_stereotypes"][scale_key][p_type][ster]
                    if pair_str not in node_micro:
                        node_micro[pair_str] = {"coincidences": 0, "total_observed": 0}
                    node_micro[pair_str]["coincidences"] += 1

# Población final de los totales observados globales acumulados para el cálculo de porcentaje
for regime, data in results["macro"]["trend_regimes"].items():
    for macro, stats in data["signals"].items():
        stats["total_observed"] = total_counts_macro[macro]

for regime, data in results["micro"]["trend_regimes"].items():
    for pair_str, stats in data["signals"].items():
        # Parse key pair back from string "(s5_key × s5v_key)"
        clean_str = pair_str.strip("()")
        parts = clean_str.split(" × ")
        stats["total_observed"] = total_counts_micro[(parts[0], parts[1])]

for scale_key, types in results["macro"]["pivot_stereotypes"].items():
    for p_type, sters in types.items():
        for ster, signals in sters.items():
            for macro, stats in signals.items():
                stats["total_observed"] = total_counts_macro[macro]

for scale_key, types in results["micro"]["pivot_stereotypes"].items():
    for p_type, sters in types.items():
        for ster, signals in sters.items():
            for pair_str, stats in signals.items():
                clean_str = pair_str.strip("()")
                parts = clean_str.split(" × ")
                stats["total_observed"] = total_counts_micro[(parts[0], parts[1])]

# Calcular estadísticas finales (certeza, fracaso y falsas alarmas)
def compute_final_stats(node):
    for pair, stats in list(node.items()):
        stats["outside_occurrences"] = stats["total_observed"] - stats["coincidences"]
        stats["outside_occurrences"] = max(0, stats["outside_occurrences"])
        if stats["total_observed"] > 0:
            stats["certainty_pct"] = round(stats["coincidences"] / stats["total_observed"] * 100, 2)
            stats["failure_pct"] = round(stats["outside_occurrences"] / stats["total_observed"] * 100, 2)
        if stats["total_observed"] < 5:
            del node[pair]

# Macro Regimes
for regime, data in results["macro"]["trend_regimes"].items():
    compute_final_stats(data["signals"])

# Micro Regimes
for regime, data in results["micro"]["trend_regimes"].items():
    compute_final_stats(data["signals"])

# Macro Pivots
for scale_key, types in results["macro"]["pivot_stereotypes"].items():
    for p_type, sters in types.items():
        for ster, signals in sters.items():
            compute_final_stats(signals)

# Micro Pivots
for scale_key, types in results["micro"]["pivot_stereotypes"].items():
    for p_type, sters in types.items():
        for ster, signals in sters.items():
            compute_final_stats(signals)

# Guardar Resultados
os.makedirs("backend/scripts/logs", exist_ok=True)
csv_df = pd.DataFrame(csv_rows)
csv_df.to_csv("backend/scripts/logs/fusion_stereotypes_audit.csv", index=False)
print(f"✅ CSV de auditoría guardado en backend/scripts/logs/fusion_stereotypes_audit.csv ({len(csv_df)} filas)")

with open("backend/modules/entry_decision/domain/rules/s5_s5v_stereotypes_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("✅ Matriz de resultados JSON guardada en backend/modules/entry_decision/domain/rules/s5_s5v_stereotypes_results.json")

store.close()
print("PROCESO TERMINADO.")
