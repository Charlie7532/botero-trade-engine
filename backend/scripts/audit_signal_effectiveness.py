#!/usr/bin/env python3
"""
AUDITORÍA FORENSE DE EFECTIVIDAD POR SEÑAL — RC COMBINED (4.5M SNAPSHOTS)
========================================================================
Calcula la efectividad cuantitativa (Win Rate %, Operaciones Acertadas vs Erradas,
Retorno Promedio, Expectancia Neto, Profit Factor) para cada tipo de señal
en `rc_combined_derived.json` leyendo directamente del caché Parquet del Vault.

Clean Architecture: Script (delivery mechanism).
"""
import json
import logging
from pathlib import Path
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AuditSignalEffectiveness")

ROOT = Path(__file__).resolve().parent.parent.parent
DERIVED_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_combined_derived.json"
CACHE_PATH = ROOT / "backend/scratch/cache/snapshots_ohlcv_cache.parquet"


def main():
    logger.info("=== AUDITORÍA FORENSE DE EFECTIVIDAD POR SEÑAL — RC COMBINED ===")
    
    # 1. Cargar el JSON de señales derivadas
    with open(DERIVED_PATH) as f:
        derived_data = json.load(f)
        
    states_dict = derived_data.get("states", {})
    logger.info(f"Cargados {len(states_dict)} estados L3 desde {DERIVED_PATH.name}")
    
    state_to_signal = {}
    for state_key, info in states_dict.items():
        state_to_signal[state_key] = info["identity"]["signal"]
        
    # 2. Cargar el caché Parquet de 4.5M de snapshots
    logger.info(f"Cargando dataset desde {CACHE_PATH}...")
    df = pd.read_parquet(CACHE_PATH)
    logger.info(f"Cargados {len(df):,} registros históricos.")
    
    # 3. Mapear estado L3 a tipo de señal
    # state_l3 format: "T+++|C---|<<"
    df["signal"] = df["state_l3"].map(state_to_signal).fillna("UNMAPPED")
    
    # 4. Calcular forward return a 20 días por ticker usando shift de precio futuro
    # Como el df está ordenado por ticker y timestamp:
    df["fwd_price_20d"] = df.groupby("ticker")["close"].shift(-20)
    df["fwd_ret_20d"] = (df["fwd_price_20d"] / df["close"]) - 1.0
    
    df_valid = df.dropna(subset=["fwd_ret_20d"]).copy()
    logger.info(f"Evaluando {len(df_valid):,} muestras válidas con forward return 20d.")
    
    # 5. Generar la Tabla de Atribución por Tipo de Señal
    signal_stats = []
    
    for sig_name, group in df_valid.groupby("signal"):
        n_total = len(group)
        if n_total == 0: continue
        
        wins = (group["fwd_ret_20d"] > 0).sum()
        losses = (group["fwd_ret_20d"] <= 0).sum()
        win_rate = (wins / n_total) * 100.0
        
        avg_ret = group["fwd_ret_20d"].mean() * 100.0
        median_ret = group["fwd_ret_20d"].median() * 100.0
        
        win_rets = group[group["fwd_ret_20d"] > 0]["fwd_ret_20d"]
        loss_rets = group[group["fwd_ret_20d"] <= 0]["fwd_ret_20d"]
        
        avg_win = win_rets.mean() * 100.0 if len(win_rets) > 0 else 0.0
        avg_loss = abs(loss_rets.mean() * 100.0) if len(loss_rets) > 0 else 1.0
        
        profit_factor = (win_rets.sum() / abs(loss_rets.sum())) if abs(loss_rets.sum()) > 0 else 0.0
        expectancy = (win_rate/100.0 * avg_win) - ((1.0 - win_rate/100.0) * avg_loss)
        
        signal_stats.append({
            "Señal": sig_name,
            "Total Muestras": n_total,
            "Acertadas (Win)": wins,
            "Erradas (Loss)": losses,
            "Win Rate (%)": win_rate,
            "Retorno Prom 20d (%)": avg_ret,
            "Profit Factor": profit_factor,
            "Expectancia (%)": expectancy
        })
        
    df_stats = pd.DataFrame(signal_stats).sort_values(by="Total Muestras", ascending=False)
    
    print("\n" + "="*115)
    print("      🎯 ATRIBUCIÓN FORENSE DE EFECTIVIDAD POR TIPO DE SEÑAL — RC COMBINED (2000 - 2026)")
    print("      Evaluación cuantitativa sobre forward return 20 días en 4.5M de snapshots del Vault")
    print("="*115)
    print(f"{'Señal':<15} | {'Total Muestras':<14} | {'Acertadas (Win)':<16} | {'Erradas (Loss)':<16} | {'Win Rate (%)':<12} | {'Ret. Prom 20d':<14} | Expectancia")
    print("-" * 115)
    
    for _, r in df_stats.iterrows():
        flag = "🟢 Alcista" if r["Win Rate (%)"] >= 55.0 else ("🔴 Bajista/Piso" if r["Win Rate (%)"] <= 45.0 else "⚪ Neutral")
        print(f"{r['Señal']:<15} | {r['Total Muestras']:<14,d} | {r['Acertadas (Win)']:<16,d} | {r['Erradas (Loss)']:<16,d} | {r['Win Rate (%)']:11.1f}% | {r['Retorno Prom 20d (%)']:+13.2f}% | {r['Expectancia (%)']:+10.2f}% {flag}")
        
    print("="*115)
    
    out_json = ROOT / "backend/scratch/rc_combined_signal_effectiveness_baseline.json"
    df_stats.to_json(out_json, orient="records", indent=2)
    logger.info(f"Resultados guardados en {out_json}")

if __name__ == "__main__":
    main()
