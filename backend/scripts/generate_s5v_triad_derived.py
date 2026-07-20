"""
S5V Volume Breadth Triad — Derived Table Generator
===================================================
Combines volume breadth data sources to produce s5v_triad_derived.json.
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.append("/root/botero-trade")
os.chdir("/root/botero-trade")
from dotenv import load_dotenv
load_dotenv(".env")

import pandas as pd
import numpy as np
from collections import defaultdict
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

store = TimescaleDataStore()

# Load config
with open("backend/modules/entry_decision/domain/rules/s5v_triad_table.json") as f:
    table = json.load(f)

bin_edges = table["bin_edges"]
bin_labels = table["bin_labels"]
baselines = table["baselines"]
cells = table["cells"]

TIERS = {
    "Defensive": ["XLP", "XLV", "XLU", "XLRE", "XLB"],
    "Mixed": ["XLE", "XLF", "XLC"],
    "Cyclical": ["XLK", "XLY", "XLI"],
}
ETF_TO_TIER = {}
for t, etfs in TIERS.items():
    for e in etfs:
        ETF_TO_TIER[e] = t

ALL_ENTITIES = ["SPY"] + [e for etfs in TIERS.values() for e in etfs]

def get_s5v_tickers(etf: str) -> dict:
    if etf == "SPY":
        return {"structural": "S5VTH", "intermediate": "S5VFI", "tactical": "S5VTW"}
    return {"structural": f"S5_{etf}_VTH", "intermediate": f"S5_{etf}_VFI", "tactical": f"S5_{etf}_VTW"}

def classify_bin(value, edges, labels):
    for i, edge in enumerate(edges):
        if value < edge:
            return labels[i]
    return labels[-1]

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

ZONE_MAP = {
    "<<": "BROKEN",
    "<": "WEAK",
    "~": "NEUTRAL",
    ">": "STRONG",
    ">>": "EUPHORIC"
}

def classify_cascade_phase(th, fi, tw):
    bins_val = {"<<": 0, "<": 1, "~": 2, ">": 3, ">>": 4}
    t, f, w = bins_val[th], bins_val[fi], bins_val[tw]
    if t <= 1 and f <= 1 and w <= 1:
        if w > f or w > t:
            return "EARLY_RECOVERY"
        return "DEEP_CAPITULATION"
    if t >= 3 and f >= 3 and w >= 3:
        if w < f or w < t:
            return "EARLY_DISTRIBUTION"
        return "FULL_EUPHORIA"
    if t <= 1 and f <= 1 and w >= 2:
        return "RECOVERY_CASCADE"
    if t <= 1 and f >= 2 and w >= 2:
        return "MID_RECOVERY"
    if t >= 3 and f >= 3 and w <= 1:
        return "DISTRIBUTION_CASCADE"
    if t >= 3 and f <= 1 and w <= 1:
        return "BREAKDOWN_CASCADE"
    if (t >= 3 and f <= 1) or (t <= 1 and f >= 3):
        return "DIVERGENCE"
    return "TRANSITION"

def classify_signal(net_bias, lift_bot, lift_top, n):
    if n < 20:
        return "RARE_EVENT"
    if net_bias > 20:
        if lift_bot > 3:
            return "STRONG_ACCUMULATE"
        return "ACCUMULATE"
    elif net_bias > 5:
        return "LEAN_ACCUMULATE"
    elif net_bias < -20:
        if lift_top > 3:
            return "STRONG_DISTRIBUTE"
        return "DISTRIBUTE"
    elif net_bias < -5:
        return "LEAN_DISTRIBUTE"
    return "NEUTRAL"

def classify_conviction(signal, n, fwd20_wr):
    if n < 20:
        return "INFORMATIONAL", 0
    score = 40
    if signal in ["STRONG_ACCUMULATE", "STRONG_DISTRIBUTE"]:
        score += 25
    elif signal in ["ACCUMULATE", "DISTRIBUTE"]:
        score += 15
    elif signal in ["LEAN_ACCUMULATE", "LEAN_DISTRIBUTE"]:
        score += 5
    if n >= 200:
        score += 15
    elif n >= 100:
        score += 10
    elif n >= 50:
        score += 5
    if fwd20_wr is not None:
        if fwd20_wr >= 75 or fwd20_wr <= 25:
            score += 15
        elif fwd20_wr >= 65 or fwd20_wr <= 35:
            score += 10
        elif fwd20_wr >= 55 or fwd20_wr <= 45:
            score += 5
    if score >= 80:
        return "HIGH", score
    elif score >= 60:
        return "MEDIUM", score
    return "LOW", score

def classify_signal_type(median_bars_to_target):
    if median_bars_to_target is None:
        return "UNKNOWN"
    if median_bars_to_target <= 10:
        return "LEADING"
    elif median_bars_to_target <= 20:
        return "COINCIDENT"
    else:
        return "LAGGING"

# Load volume breadth from Vault
print("Loading volume breadth data from Vault...")
spy_tickers = get_s5v_tickers("SPY")
s5th = store.load_bars(spy_tickers["structural"], "1d")["close"].astype(float).rename("th")
s5fi = store.load_bars(spy_tickers["intermediate"], "1d")["close"].astype(float).rename("fi")
s5tw = store.load_bars(spy_tickers["tactical"], "1d")["close"].astype(float).rename("tw")

entity_data = {}
for etf in ALL_ENTITIES:
    price_df = store.load_bars(etf, "1d")
    if price_df is None or price_df.empty:
        continue
    
    # Align breadth + price
    tickers = get_s5v_tickers(etf)
    sector_fi = store.load_bars(tickers["intermediate"], "1d")["close"].astype(float)
    sector_th = store.load_bars(tickers["structural"], "1d")["close"].astype(float)
    sector_tw = store.load_bars(tickers["tactical"], "1d")["close"].astype(float)
    
    common = price_df.index.intersection(sector_fi.index).intersection(sector_th.index).intersection(sector_tw.index)
    if len(common) < 100:
        continue
        
    df = pd.DataFrame({
        "close": price_df.loc[common, "close"],
        "TH": sector_th.loc[common],
        "FI": sector_fi.loc[common],
        "TW": sector_tw.loc[common],
    }).dropna()
    
    df["tw_diff"] = df["TW"].diff(1)
    df = df.dropna()
    
    # Classify bins
    df["th_bin"] = df["TH"].apply(lambda v: classify_bin(v, bin_edges["TH"], bin_labels))
    df["fi_bin"] = df["FI"].apply(lambda v: classify_bin(v, bin_edges["FI"], bin_labels))
    df["tw_bin"] = df["TW"].apply(lambda v: classify_bin(v, bin_edges["TW"], bin_labels))
    df["dir_bin"] = df["tw_diff"].apply(lambda v: "+" if v > 0 else "-")
    df["state"] = df["th_bin"] + "|" + df["fi_bin"] + "|" + df["tw_bin"] + "|" + df["dir_bin"]
    
    # Compute zigzag pivots
    zz5 = compute_zigzag(df["close"], 5.0)
    df["zz5"] = zz5
    
    # Forward returns
    for h in [5, 10, 20]:
        df[f"fwd_{h}"] = df["close"].pct_change(h).shift(-h) * 100
        
    # Distance to next ZZ5
    bottoms = df.index[df["zz5"] == -1]
    tops = df.index[df["zz5"] == 1]
    df["bars_to_bot5"] = np.nan
    df["bars_to_top5"] = np.nan
    
    for i, idx in enumerate(df.index):
        future_bots = bottoms[bottoms > idx]
        if len(future_bots) > 0:
            df.loc[idx, "bars_to_bot5"] = df.index.get_loc(future_bots[0]) - df.index.get_loc(idx)
        future_tops = tops[tops > idx]
        if len(future_tops) > 0:
            df.loc[idx, "bars_to_top5"] = df.index.get_loc(future_tops[0]) - df.index.get_loc(idx)
            
    entity_data[etf] = df
    print(f"  {etf}: {len(df)} bars, {df['state'].nunique()} states")

spy_df = entity_data.get("SPY")

print("\nComputing per-state statistics...")
state_stats = {}
for state_key, cell in cells.items():
    global_stats = cell.get("global", {})
    n_total = global_stats.get("n", 0)
    if n_total == 0:
        continue
        
    transitions = []
    bars_to_bot = []
    bars_to_top = []
    fwd5_list = []
    fwd10_list = []
    fwd20_list = []
    alpha20_list = []
    
    tier_stats = defaultdict(lambda: {"fwd20": [], "alpha20": [], "n_trans": 0})
    
    for etf, df in entity_data.items():
        mask = df["state"] == state_key
        state_rows = df[mask]
        if len(state_rows) == 0:
            continue
            
        state_changes = df["state"].ne(df["state"].shift())
        trans_mask = mask & state_changes
        trans_rows = df[trans_mask]
        tier = ETF_TO_TIER.get(etf, "SPY")
        
        for idx in trans_rows.index:
            transitions.append(idx)
            row = df.loc[idx]
            if not np.isnan(row["bars_to_bot5"]):
                bars_to_bot.append(row["bars_to_bot5"])
            if not np.isnan(row["bars_to_top5"]):
                bars_to_top.append(row["bars_to_top5"])
                
            for h, lst in [(5, fwd5_list), (10, fwd10_list), (20, fwd20_list)]:
                val = row[f"fwd_{h}"]
                if not np.isnan(val):
                    lst.append(val)
                    
            if etf != "SPY" and spy_df is not None and idx in spy_df.index:
                spy_fwd20 = spy_df.loc[idx, "fwd_20"]
                sec_fwd20 = row["fwd_20"]
                if not np.isnan(spy_fwd20) and not np.isnan(sec_fwd20):
                    alpha = sec_fwd20 - spy_fwd20
                    alpha20_list.append(alpha)
                    tier_stats[tier]["alpha20"].append(alpha)
            tier_stats[tier]["fwd20"].append(row["fwd_20"] if not np.isnan(row["fwd_20"]) else None)
            tier_stats[tier]["n_trans"] += 1
            
    n_trans = len(transitions)
    parts = state_key.split("|")
    th_bin, fi_bin, tw_bin, dir_bin = parts[0], parts[1], parts[2], parts[3]
    dir_desc = "UP" if dir_bin == "+" else "DOWN"
    
    cascade_phase = classify_cascade_phase(th_bin, fi_bin, tw_bin)
    
    p_bot_50 = global_stats.get("P_bot_5_0", 0)
    p_top_50 = global_stats.get("P_top_5_0", 0)
    lift_bot = global_stats.get("lift_bot_5_0", 1.0)
    lift_top = global_stats.get("lift_top_5_0", 1.0)
    net_bias = global_stats.get("net_bias", 0)
    
    signal = classify_signal(net_bias * 100, lift_bot, lift_top, n_total)
    fwd20_mean = np.mean(fwd20_list) if fwd20_list else None
    fwd20_wr = (sum(1 for x in fwd20_list if x > 0) / len(fwd20_list) * 100) if fwd20_list else None
    conviction_label, conviction_score = classify_conviction(signal, n_total, fwd20_wr)
    
    med_bot = np.median(bars_to_bot) if bars_to_bot else None
    med_top = np.median(bars_to_top) if bars_to_top else None
    p25_bot = np.percentile(bars_to_bot, 25) if len(bars_to_bot) >= 4 else None
    p75_bot = np.percentile(bars_to_bot, 75) if len(bars_to_bot) >= 4 else None
    
    if net_bias > 0.05:
        sig_type = classify_signal_type(med_bot)
    elif net_bias < -0.05:
        sig_type = classify_signal_type(med_top)
    else:
        sig_type = "NEUTRAL"
        
    tier_detail = {}
    for tier_name in ["Cyclical", "Mixed", "Defensive", "SPY"]:
        ts = tier_stats.get(tier_name, {})
        fwd20s = [x for x in ts.get("fwd20", []) if x is not None]
        alpha20s = ts.get("alpha20", [])
        if ts.get("n_trans", 0) > 0:
            tier_detail[tier_name] = {
                "N_transitions": ts["n_trans"],
                "fwd_20d_mean": round(np.mean(fwd20s), 2) if fwd20s else None,
                "alpha_20d_mean": round(np.mean(alpha20s), 2) if alpha20s else None,
            }
            
    zone_desc = f"VTH={ZONE_MAP[th_bin]}, VFI={ZONE_MAP[fi_bin]}, VTW={ZONE_MAP[tw_bin]}, DIR={dir_desc}"
    reading_parts = [zone_desc, f"Phase: {cascade_phase}"]
    if n_trans > 0 and fwd20_mean is not None:
        reading_parts.append(f"Fwd20={fwd20_mean:+.2f}% (WR={fwd20_wr:.0f}%, N_trans={n_trans})")
    if med_bot is not None:
        reading_parts.append(f"Med→Bot={int(med_bot)}d")
    if med_top is not None:
        reading_parts.append(f"Med→Top={int(med_top)}d")
    reading = ". ".join(reading_parts)
    
    state_entry = {
        "identity": {
            "vth_zone": ZONE_MAP[th_bin],
            "vfi_zone": ZONE_MAP[fi_bin],
            "vtw_zone": ZONE_MAP[tw_bin],
            "direction": dir_desc,
            "cascade_phase": cascade_phase,
            "signal": signal,
            "conviction": conviction_label,
            "conviction_score": conviction_score,
        },
        "frequency": {
            "N_observations": n_total,
            "N_transitions": n_trans,
            "pct_of_total": round(n_total / len(df) * 100, 2),
        },
        "pivot_prediction": {
            "bottom": {
                "zz25": {"p_local": round(global_stats.get("P_bot_2_5", 0) * 100, 1)},
                "zz50": {
                    "p_local": round(global_stats.get("P_bot_5_0", 0) * 100, 1),
                    "lift": global_stats.get("lift_bot_5_0", 1.0),
                    "one_in": round(1 / global_stats.get("P_bot_5_0", 1), 1) if global_stats.get("P_bot_5_0", 0) > 0 else 0,
                },
                "zz75": {"p_local": round(global_stats.get("P_bot_7_5", 0) * 100, 1)},
            },
            "top": {
                "zz25": {"p_local": round(global_stats.get("P_top_2_5", 0) * 100, 1)},
                "zz50": {
                    "p_local": round(global_stats.get("P_top_5_0", 0) * 100, 1),
                    "lift": global_stats.get("lift_top_5_0", 1.0),
                },
                "zz75": {"p_local": round(global_stats.get("P_top_7_5", 0) * 100, 1)},
            },
            "asymmetry": {
                "net_bias_pp": round(net_bias * 100, 1) if net_bias is not None else 0.0,
                "bias": "STRONG_BOTTOM" if net_bias > 0.20 else "BOTTOM" if net_bias > 0.05 else "STRONG_TOP" if net_bias < -0.20 else "TOP" if net_bias < -0.05 else "NEUTRAL",
            },
        },
        "anticipation": {
            "median_bars_to_zz5_bottom": int(med_bot) if med_bot is not None else None,
            "p25_bars_to_bottom": int(p25_bot) if p25_bot is not None else None,
            "p75_bars_to_bottom": int(p75_bot) if p75_bot is not None else None,
            "median_bars_to_zz5_top": int(med_top) if med_top is not None else None,
            "signal_type": sig_type,
        },
        "forward_returns": {
            "fwd_5d": {
                "mean_pct": round(np.mean(fwd5_list), 2) if fwd5_list else None,
                "win_rate": round(sum(1 for x in fwd5_list if x > 0) / len(fwd5_list) * 100) if fwd5_list else None,
            },
            "fwd_10d": {
                "mean_pct": round(np.mean(fwd10_list), 2) if fwd10_list else None,
                "win_rate": round(sum(1 for x in fwd10_list if x > 0) / len(fwd10_list) * 100) if fwd10_list else None,
            },
            "fwd_20d": {
                "mean_pct": round(fwd20_mean, 2) if fwd20_mean is not None else None,
                "win_rate": round(fwd20_wr) if fwd20_wr is not None else None,
            },
        },
        "tier_detail": tier_detail,
        "reading": reading,
    }
    state_stats[state_key] = state_entry

output_path = "backend/modules/entry_decision/domain/rules/s5v_triad_derived.json"
output_data = {
    "version": "1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source_table_version": "1.0",
    "methodology": table["training"],
    "n_states": len(state_stats),
    "states": state_stats,
}

with open(output_path, "w") as f:
    json.dump(output_data, f, indent=2, default=str)
print(f"\n✅ Generated {output_path}")
print(f"   {len(state_stats)} states enriched")
store.close()
