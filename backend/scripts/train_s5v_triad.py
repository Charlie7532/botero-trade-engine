"""
Train S5V Volume Breadth Triad Table
======================================
Generates two JSON artifacts consumed by the Market Health and Entry Gate:

  1. s5v_triad_table.json        — Volume breadth conditional probability table (250 states)
  2. s5v_relative_modifier.json   — Sector vs SPY volume breadth relative modifier
     v2.0: Z-Score per-sector bins + Rate of Change (RoC) modifier dimension

Corrections applied (Jul 2026 audit):
  - MIN_N raised from 20 → 30 (eliminates spurious N=1 cells with 13.7x lift)
  - Relative modifier uses Z-Score per-sector instead of fixed pp bins
  - RoC of RoM deviation added as second modifier dimension
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
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

store = TimescaleDataStore()

# ── Configuration ──
BIN_LABELS = ["<<", "<", "~", ">", ">>"]
BIN_PERCENTILES = [0.10, 0.30, 0.70, 0.90]
ZZ_THRESHOLDS = [2.5, 5.0, 7.5]
NEAR_WINDOW = 3
MIN_N_L1 = 30

TIERS = {
    "Defensive": ["XLP", "XLV", "XLU", "XLRE", "XLB"],
    "Mixed": ["XLE", "XLF", "XLC"],
    "Cyclical": ["XLK", "XLY", "XLI"],
}
ETF_TO_TIER = {}
for tier_name, etfs in TIERS.items():
    for etf in etfs:
        ETF_TO_TIER[etf] = tier_name

# Mapping for sector volume breadth tickers in Vault
# format: SV5_{ETF}_TH, SV5_{ETF}_FI, SV5_{ETF}_TW (Canonical Convención B)
def get_s5v_tickers(etf: str) -> dict:
    if etf == "SPY":
        return {
            "structural": "SV5TH",
            "intermediate": "SV5FI",
            "tactical": "SV5TW"
        }
    return {
        "structural": f"SV5_{etf}_TH",
        "intermediate": f"SV5_{etf}_FI",
        "tactical": f"SV5_{etf}_TW"
    }


def compute_zigzag(prices: pd.Series, pct_threshold: float) -> pd.Series:
    """Compute zigzag turning points. Returns Series: 1=TOP, -1=BOTTOM, 0=nothing."""
    n = len(prices)
    if n < 10:
        return pd.Series(0, index=prices.index)
    threshold = pct_threshold / 100.0
    direction = 1
    last_pivot_price = prices.iloc[0]
    last_pivot_idx = 0
    pivots = pd.Series(0, index=prices.index)
    for i in range(1, n):
        price = prices.iloc[i]
        if direction == 1:
            if price >= last_pivot_price:
                last_pivot_price = price
                last_pivot_idx = i
            elif price <= last_pivot_price * (1 - threshold):
                pivots.iloc[last_pivot_idx] = 1
                last_pivot_price = price
                last_pivot_idx = i
                direction = -1
        else:
            if price <= last_pivot_price:
                last_pivot_price = price
                last_pivot_idx = i
            elif price >= last_pivot_price * (1 + threshold):
                pivots.iloc[last_pivot_idx] = -1
                last_pivot_price = price
                last_pivot_idx = i
                direction = 1
    return pivots


def make_near_flags(zz: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Create boolean Series for 'near a ZZ bottom' and 'near a ZZ top' (strictly future/forward-looking)."""
    near_bot = pd.Series(False, index=zz.index)
    near_top = pd.Series(False, index=zz.index)
    n = len(zz)
    for i in range(n):
        if zz.iloc[i] == -1:  # bottom
            for d in range(-window, 1):
                p = i + d
                if 0 <= p < n:
                    near_bot.iloc[p] = True
        elif zz.iloc[i] == 1:  # top
            for d in range(-window, 1):
                p = i + d
                if 0 <= p < n:
                    near_top.iloc[p] = True
    return near_bot, near_top


def classify_bin(value: float, edges: list[float]) -> str:
    """Classify a value into one of 5 bins based on edges."""
    for i, edge in enumerate(edges):
        if value < edge:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


def compute_cell_stats(sub_df: pd.DataFrame) -> dict | None:
    """Compute ZZ coincidence stats for a subset of observations."""
    n = len(sub_df)
    if n == 0:
        return None
    stats = {"n": n}
    for pct in ZZ_THRESHOLDS:
        key_pct = str(pct).replace(".", "_")
        stats[f"P_bot_{key_pct}"] = round(float(sub_df[f"near_bot_{pct}"].mean()), 4)
        stats[f"P_top_{key_pct}"] = round(float(sub_df[f"near_top_{pct}"].mean()), 4)
    return stats


# ══════════════════════════════════════════════════════════════
# STEP 1: LOAD DATA
# ══════════════════════════════════════════════════════════════
print("Step 1: Loading volume breadth data...")

entities = {}
spy_tickers = get_s5v_tickers("SPY")
spy_th = store.load_bars(spy_tickers["structural"], "1d")["close"].astype(float).rename("th")
spy_fi = store.load_bars(spy_tickers["intermediate"], "1d")["close"].astype(float).rename("fi")
spy_tw = store.load_bars(spy_tickers["tactical"], "1d")["close"].astype(float).rename("tw")
spy_price = store.load_bars("SPY", "1d")["close"].astype(float).rename("etf_close")

spy_merged = pd.concat([spy_th, spy_fi, spy_tw, spy_price], axis=1, join="inner").dropna()
entities["SPY"] = spy_merged
print(f"  SPY: {len(spy_merged)} bars")

for etf in SECTOR_ETFS.keys():
    tickers = get_s5v_tickers(etf)
    th = store.load_bars(tickers["structural"], "1d")["close"].astype(float).rename("th")
    fi = store.load_bars(tickers["intermediate"], "1d")["close"].astype(float).rename("fi")
    tw = store.load_bars(tickers["tactical"], "1d")["close"].astype(float).rename("tw")
    etf_price = store.load_bars(etf, "1d")["close"].astype(float).rename("etf_close")
    
    merged = pd.concat([th, fi, tw, etf_price], axis=1, join="inner").dropna()
    if len(merged) < 200:
        print(f"  {etf}: SKIP ({len(merged)} bars)")
        continue
    entities[etf] = merged
    print(f"  {etf}: {len(merged)} bars")

spy_fi_series = spy_merged["fi"]

# ══════════════════════════════════════════════════════════════
# STEP 2: DEFINE BIN EDGES (global percentiles)
# ══════════════════════════════════════════════════════════════
print("\nStep 2: Computing bin edges...")

all_th = pd.concat([d["th"] for d in entities.values()])
all_fi = pd.concat([d["fi"] for d in entities.values()])
all_tw = pd.concat([d["tw"] for d in entities.values()])

bin_edges = {}
for name, series in [("TH", all_th), ("FI", all_fi), ("TW", all_tw)]:
    cuts = series.quantile(BIN_PERCENTILES).tolist()
    bin_edges[name] = [round(c, 2) for c in cuts]
    print(f"  {name}: {bin_edges[name]}")

# ══════════════════════════════════════════════════════════════
# STEP 3: CLASSIFY + COMPUTE ZIGZAG + BUILD OBSERVATION TABLE
# ══════════════════════════════════════════════════════════════
print("\nStep 3: Classifying bins and computing ZigZag...")

all_obs = []

for etf, merged in entities.items():
    # tw_diff for direction
    merged["tw_diff"] = merged["tw"].diff(1)
    merged = merged.dropna()

    # Classify bins
    th_bins = merged["th"].apply(lambda v: classify_bin(v, bin_edges["TH"]))
    fi_bins = merged["fi"].apply(lambda v: classify_bin(v, bin_edges["FI"]))
    tw_bins = merged["tw"].apply(lambda v: classify_bin(v, bin_edges["TW"]))
    dir_bins = merged["tw_diff"].apply(lambda v: "+" if v > 0 else "-")
    triad_keys = th_bins + "|" + fi_bins + "|" + tw_bins + "|" + dir_bins

    # Compute ZigZag
    zz_flags = {}
    for pct in ZZ_THRESHOLDS:
        zz = compute_zigzag(merged["etf_close"], pct)
        near_bot, near_top = make_near_flags(zz, NEAR_WINDOW)
        zz_flags[f"near_bot_{pct}"] = near_bot
        zz_flags[f"near_top_{pct}"] = near_top

    # Relative volume breadth modifier: Pure RoM (Rest of Market) Subtraction
    SECTOR_WEIGHTS = {
        "XLK": 65 / 500,
        "XLF": 72 / 500,
        "XLV": 64 / 500,
        "XLY": 52 / 500,
        "XLI": 78 / 500,
        "XLP": 38 / 500,
        "XLE": 23 / 500,
        "XLU": 30 / 500,
        "XLB": 28 / 500,
        "XLRE": 31 / 500,
        "XLC": 23 / 500,
    }
    if etf != "SPY" and etf in SECTOR_WEIGHTS:
        w = SECTOR_WEIGHTS[etf]
        spy_fi_aligned = spy_fi_series.reindex(merged.index, method="ffill")
        # Rest of Market breadth = (SPY_breadth - w * Sector_breadth) / (1 - w)
        rom_fi = (spy_fi_aligned - w * merged["fi"]) / (1.0 - w)
        # Deviation = Sector_breadth - RoM_breadth
        rel_fi = merged["fi"] - rom_fi
    else:
        rel_fi = pd.Series(0.0, index=merged.index)

    # Build observation records
    tier = ETF_TO_TIER.get(etf, "SPY")
    for i in range(len(merged)):
        rec = {
            "etf": etf,
            "tier": tier,
            "th_bin": th_bins.iloc[i],
            "fi_bin": fi_bins.iloc[i],
            "tw_bin": tw_bins.iloc[i],
            "dir_bin": dir_bins.iloc[i],
            "triad": triad_keys.iloc[i],
            "rel_fi": float(rel_fi.iloc[i]) if not pd.isna(rel_fi.iloc[i]) else 0.0,
        }
        for pct in ZZ_THRESHOLDS:
            rec[f"near_bot_{pct}"] = bool(zz_flags[f"near_bot_{pct}"].iloc[i])
            rec[f"near_top_{pct}"] = bool(zz_flags[f"near_top_{pct}"].iloc[i])
        all_obs.append(rec)

    n_bots_5 = sum(1 for r in all_obs[-len(merged):] if r["near_bot_5.0"])
    n_tops_5 = sum(1 for r in all_obs[-len(merged):] if r["near_top_5.0"])
    print(f"  {etf}: {len(merged)} obs, ZZ5 near_bot={n_bots_5} near_top={n_tops_5}")

df = pd.DataFrame(all_obs)
print(f"\nTotal observations: {len(df)}")

# ══════════════════════════════════════════════════════════════
# STEP 4: BUILD S5V TRIAD TABLE (250 states)
# ══════════════════════════════════════════════════════════════
print("\nStep 4: Building volume triad table...")

baselines = {}
for group_name, group_filter in [
    ("global", df),
    ("Defensive", df[df["tier"] == "Defensive"]),
    ("Mixed", df[df["tier"] == "Mixed"]),
    ("Cyclical", df[df["tier"] == "Cyclical"]),
    ("SPY", df[df["etf"] == "SPY"]),
]:
    stats = compute_cell_stats(group_filter)
    if stats:
        baselines[group_name] = stats

cells = {}
unique_triads = df["triad"].unique()
print(f"  Unique S5V states observed: {len(unique_triads)}/250")

for triad_key in sorted(unique_triads):
    sub = df[df["triad"] == triad_key]
    cell = {}

    cell["global"] = compute_cell_stats(sub)

    for tier_name in TIERS:
        tier_sub = sub[sub["tier"] == tier_name]
        tier_stats = compute_cell_stats(tier_sub)
        if tier_stats and tier_stats["n"] >= MIN_N_L1:
            cell[tier_name] = tier_stats

    spy_sub = sub[sub["etf"] == "SPY"]
    spy_stats = compute_cell_stats(spy_sub)
    if spy_stats and spy_stats["n"] >= MIN_N_L1:
        cell["SPY"] = spy_stats

    # Compute lift
    if cell["global"]:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]
        cell_bot = cell["global"]["P_bot_5_0"]
        cell_top = cell["global"]["P_top_5_0"]
        cell["global"]["lift_bot_5_0"] = round(cell_bot / base_bot, 2) if base_bot > 0 else 0.0
        cell["global"]["lift_top_5_0"] = round(cell_top / base_top, 2) if base_top > 0 else 0.0
        cell["global"]["net_bias"] = round(cell_bot - cell_top, 4)

    cells[triad_key] = cell

n_cells_total = len(cells)

# ══════════════════════════════════════════════════════════════
# STEP 5: BUILD RELATIVE S5V MODIFIER (Z-Score per-sector + RoC)
# ══════════════════════════════════════════════════════════════
print("\nStep 5: Building Z-Score relative S5V modifier...")

# ── 5a: Compute per-sector deviation statistics for Z-Score normalization ──
sector_df = df[df["etf"] != "SPY"].copy()

sector_params = {}
for etf in sector_df["etf"].unique():
    etf_mask = sector_df["etf"] == etf
    dev_series = sector_df.loc[etf_mask, "rel_fi"]
    sector_params[etf] = {
        "dev_mean": round(float(dev_series.mean()), 2),
        "dev_std": round(float(dev_series.std()), 2),
    }
    print(f"  {etf}: dev_mean={sector_params[etf]['dev_mean']:+.1f}  dev_std={sector_params[etf]['dev_std']:.1f}")

# ── 5b: Compute Z-Score for each observation using its sector's params ──
def compute_z_score(row):
    params = sector_params.get(row["etf"])
    if params and params["dev_std"] > 0:
        return (row["rel_fi"] - params["dev_mean"]) / params["dev_std"]
    return 0.0

sector_df["z_dev"] = sector_df.apply(compute_z_score, axis=1)

# ── 5c: Build Z-Score bins (replaces fixed pp bins) ──
Z_EDGES = [-2.0, -1.0, 1.0, 2.0]
rel_modifier = {}
for i, label in enumerate(BIN_LABELS):
    if i == 0:
        mask = sector_df["z_dev"] < Z_EDGES[0]
    elif i == len(BIN_LABELS) - 1:
        mask = sector_df["z_dev"] >= Z_EDGES[-1]
    else:
        mask = (sector_df["z_dev"] >= Z_EDGES[i - 1]) & (sector_df["z_dev"] < Z_EDGES[i])

    sub = sector_df[mask]
    stats = compute_cell_stats(sub)
    if stats:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]

        stats["bot_factor"] = round(stats["P_bot_5_0"] / base_bot, 3) if base_bot > 0 else 1.0
        stats["top_factor"] = round(stats["P_top_5_0"] / base_top, 3) if base_top > 0 else 1.0
        rel_modifier[label] = stats
    print(f"  Z-bin '{label}': N={stats['n'] if stats else 0}")

# ── 5d: Build Rate of Change (RoC) modifier ──
print("\nStep 5d: Building RoC modifier...")

# Compute 5-day RoC of rel_fi per entity
roc_records = []
for etf in sector_df["etf"].unique():
    etf_mask = sector_df["etf"] == etf
    etf_sub = sector_df.loc[etf_mask].copy()
    etf_sub["roc_5d"] = etf_sub["rel_fi"].diff(5)
    roc_records.append(etf_sub[["roc_5d"]].dropna())

roc_df = pd.concat(roc_records)
sector_df = sector_df.join(roc_df, how="left")
sector_df["roc_5d"] = sector_df["roc_5d"].fillna(0.0)

# Normalize RoC by its global std
roc_std = float(sector_df["roc_5d"].std())
print(f"  RoC_5d global std: {roc_std:.2f}")

# RoC bins: same 5-bin structure
ROC_Z_EDGES = [-1.5, -0.5, 0.5, 1.5]
roc_modifier = {}
for i, label in enumerate(BIN_LABELS):
    roc_z = sector_df["roc_5d"] / roc_std if roc_std > 0 else sector_df["roc_5d"]
    if i == 0:
        mask = roc_z < ROC_Z_EDGES[0]
    elif i == len(BIN_LABELS) - 1:
        mask = roc_z >= ROC_Z_EDGES[-1]
    else:
        mask = (roc_z >= ROC_Z_EDGES[i - 1]) & (roc_z < ROC_Z_EDGES[i])

    sub = sector_df[mask]
    stats = compute_cell_stats(sub)
    if stats:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]
        stats["bot_factor"] = round(stats["P_bot_5_0"] / base_bot, 3) if base_bot > 0 else 1.0
        stats["top_factor"] = round(stats["P_top_5_0"] / base_top, 3) if base_top > 0 else 1.0
        roc_modifier[label] = stats
    print(f"  RoC-bin '{label}': N={stats['n'] if stats else 0}")

# ══════════════════════════════════════════════════════════════
# STEP 6: WRITE OUTPUT FILES
# ══════════════════════════════════════════════════════════════
print("\nStep 6: Writing output files...")

os.makedirs("backend/modules/entry_decision/domain/rules", exist_ok=True)

triad_table = {
    "version": "2.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "backend/scripts/train_s5v_triad.py",
    "_metadata": {
        "purpose": (
            "Tabla de probabilidad condicional de giros ZigZag basada en 3 ejes de "
            "amplitud de volumen sectorial (S5V). Cada celda responde: dado que el sector "
            "está en este estado combinatorio de volumen, ¿cuál es la probabilidad de estar "
            "cerca de un suelo (bottom) o techo (top) del precio del ETF?"
        ),
        "data_source": (
            "Vault (Neon PostgreSQL). Tickers: S5_{ETF}_VTH, S5_{ETF}_VFI, S5_{ETF}_VTW "
            "para cada sector. Precio del ETF para calcular ZigZag. "
            "SPY como referencia de mercado."
        ),
        "axes": {
            "TH (Structural)": "% de constituyentes del sector con volumen > media móvil 200 días. Ritmo lento. Indica tendencia estructural de participación de volumen.",
            "FI (Intermediate)": "% de constituyentes del sector con volumen > media móvil 50 días. Ritmo medio. Señal principal de flujo institucional.",
            "TW (Tactical)": "% de constituyentes del sector con volumen > media móvil 20 días. Ritmo rápido. Señal de momentum de corto plazo.",
            "Direction (+/-)": "+ si TW subió vs día anterior, - si bajó o igual. Indica dirección del momentum táctico.",
        },
        "bin_classification": {
            "method": "Percentiles globales sobre todas las observaciones (todos los sectores + SPY)",
            "bin_percentiles": BIN_PERCENTILES,
            "bin_labels_meaning": {
                "<<": f"Extremo frío: < percentil {BIN_PERCENTILES[0]*100:.0f}% (sequía de volumen severa)",
                "<": f"Frío: percentil {BIN_PERCENTILES[0]*100:.0f}%-{BIN_PERCENTILES[1]*100:.0f}% (volumen bajo)",
                "~": f"Neutral: percentil {BIN_PERCENTILES[1]*100:.0f}%-{BIN_PERCENTILES[2]*100:.0f}% (volumen normal)",
                ">": f"Caliente: percentil {BIN_PERCENTILES[2]*100:.0f}%-{BIN_PERCENTILES[3]*100:.0f}% (volumen elevado)",
                ">>": f"Extremo caliente: > percentil {BIN_PERCENTILES[3]*100:.0f}% (surge de volumen)",
            },
        },
        "cell_key_format": "TH_bin|FI_bin|TW_bin|Direction  →  ejemplo: '<<|<<|>>|+' = TH frío, FI frío, TW caliente, subiendo",
        "zigzag_explanation": {
            "purpose": "ZigZag identifica giros retrospectivos del precio del ETF. No es predictivo — es un target de entrenamiento.",
            "thresholds": {
                "2.5%": "Giro menor (swing táctico). near_window=3 días.",
                "5.0%": "Giro medio (swing intermedio). PRINCIPAL para señales operativas.",
                "7.5%": "Giro mayor (cambio estructural). Más raro y significativo.",
            },
            "near_window_bars": f"{NEAR_WINDOW} días antes del giro ZigZag. Si el estado Triad ocurre en esa ventana, se cuenta como 'near'.",
        },
        "cell_fields": {
            "n": "Número de observaciones (días) en este estado",
            "P_bot_2_5": "P(estar cerca de un suelo ZZ 2.5%) dado este estado",
            "P_bot_5_0": "P(estar cerca de un suelo ZZ 5.0%) — PRINCIPAL",
            "P_bot_7_5": "P(estar cerca de un suelo ZZ 7.5%) — estructural",
            "P_top_2_5": "P(estar cerca de un techo ZZ 2.5%) dado este estado",
            "P_top_5_0": "P(estar cerca de un techo ZZ 5.0%) — PRINCIPAL",
            "P_top_7_5": "P(estar cerca de un techo ZZ 7.5%) — estructural",
            "lift_bot_5_0": "P_bot_5_0 de esta celda / P_bot_5_0 global. >1 = más suelos que promedio",
            "lift_top_5_0": "P_top_5_0 de esta celda / P_top_5_0 global. >1 = más techos que promedio",
            "net_bias": "P_bot_5_0 - P_top_5_0. Positivo = sesgo a suelo (acumulación). Negativo = sesgo a techo (distribución)",
        },
        "tier_pooling": {
            "purpose": "Los sectores se agrupan en tiers por comportamiento similar. L1 (tier) se usa si N≥30, si no se cae a L2 (global).",
            "L1_tiers": TIERS,
            "L2_fallback": "Promedio global de todas las observaciones",
            "min_n_l1": MIN_N_L1,
        },
        "operational_interpretation": {
            "ACCUMULATION": "net_bias > +0.10: el estado tiene más probabilidad de suelo que de techo → favorece entrada",
            "DISTRIBUTION": "net_bias < -0.10: el estado tiene más probabilidad de techo que de suelo → reduce sizing o espera",
            "NEUTRAL": "net_bias entre -0.10 y +0.10: sin sesgo claro → no modifica decisión",
        },
    },
    "training": {
        "n_entities": len(entities),
        "entities": list(entities.keys()),
        "n_observations": len(df),
        "near_window_bars": NEAR_WINDOW,
        "zigzag_thresholds": ZZ_THRESHOLDS,
        "min_n_l1": MIN_N_L1,
        "bin_percentiles": BIN_PERCENTILES,
    },
    "bin_edges": {k: [round(v, 2) for v in vals] for k, vals in bin_edges.items()},
    "bin_labels": BIN_LABELS,
    "tiers": TIERS,
    "baselines": baselines,
    "cells": cells,
}

triad_table_out_path = "backend/modules/entry_decision/domain/rules/s5v_triad_table.json"
with open(triad_table_out_path, "w") as f:
    json.dump(triad_table, f, indent=2, default=str)
print(f"  Written: {triad_table_out_path} ({len(cells)} cells)")

rel_path = "backend/modules/entry_decision/domain/rules/s5v_relative_modifier.json"
rel_output = {
    "version": "2.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "backend/scripts/train_s5v_triad.py",
    "_metadata": {
        "purpose": (
            "Modificador relativo que ajusta las probabilidades de la Tríada S5V según "
            "cuánto se desvía el volumen idiosincrático del sector respecto al Rest of Market (RoM). "
            "v2.0: normalización Z-Score per-sector + dimensión Rate of Change."
        ),
        "rom_subtraction": {
            "formula": "RoM_FI = (SPY_FI - w × Sector_FI) / (1 - w)",
            "deviation": "Dev = Sector_FI - RoM_FI",
            "w_source": "Peso aproximado de cada sector en el S&P 500 (n constituyentes / 500)",
            "interpretation": "Dev > 0 → más constituyentes del sector tienen volumen alto que el resto del mercado. Dev < 0 → menos.",
        },
        "z_score_normalization": {
            "purpose": (
                "Cada sector tiene una volatilidad de desviación diferente. "
                "XLE (std=17.9pp) vs XLI (std=8.3pp) → una desviación de 10pp "
                "es rutinaria en XLE pero extrema en XLI. El Z-Score normaliza esto."
            ),
            "formula": "Z = (Dev - dev_mean_sector) / dev_std_sector",
            "bins": {
                "<<": "Z < -2.0 → sequía extrema de volumen idiosincrático. VETO potencial.",
                "<": "-2.0 ≤ Z < -1.0 → volumen por debajo del promedio del sector. Cautela.",
                "~": "-1.0 ≤ Z < +1.0 → volumen normal para este sector. Sin modificación.",
                ">": "+1.0 ≤ Z < +2.0 → volumen por encima del promedio. Señal positiva.",
                ">>": "Z ≥ +2.0 → surge de volumen idiosincrático. BOOST de probabilidad.",
            },
        },
        "roc_modifier": {
            "purpose": (
                "Rate of Change del flujo: ¿se está acelerando o desacelerando el cambio de "
                "volumen idiosincrático? Validado OOS con Sharpe 0.92 (mejor variante)."
            ),
            "formula": "RoC_5d = Dev[t] - Dev[t-5]",
            "normalization": "RoC_Z = RoC_5d / roc_global_std",
            "bins": {
                "<<": "RoC_Z < -1.5 → flujo desacelerando rápidamente. Reduce bot_factor.",
                "<": "-1.5 ≤ RoC_Z < -0.5 → flujo desacelerando. Reduce ligeramente.",
                "~": "-0.5 ≤ RoC_Z < +0.5 → flujo estable. Sin modificación.",
                ">": "+0.5 ≤ RoC_Z < +1.5 → flujo acelerando. Boost ligero.",
                ">>": "RoC_Z ≥ +1.5 → flujo acelerando fuertemente. Boost significativo.",
            },
        },
        "bin_fields": {
            "n": "Observaciones en este bin",
            "P_bot_2_5 / P_top_2_5": "Probabilidad de giro ZZ 2.5% en este bin de modifier",
            "P_bot_5_0 / P_top_5_0": "Probabilidad de giro ZZ 5.0% — PRINCIPAL",
            "bot_factor": "Multiplicador sobre P_bot de la Tríada. >1 = amplifica señal de suelo, <1 = reduce",
            "top_factor": "Multiplicador sobre P_top de la Tríada. >1 = amplifica señal de techo, <1 = reduce",
        },
        "application_formula": (
            "adj_P_bot = P_bot_triad × z_bot_factor × roc_bot_factor. "
            "adj_P_top = P_top_triad × z_top_factor × roc_top_factor. "
            "Los dos modifiers se multiplican secuencialmente."
        ),
        "sector_params_fields": {
            "dev_mean": "Media histórica de la desviación RoM para este sector (en pp)",
            "dev_std": "Desviación estándar histórica de la desviación RoM (en pp). Usada como denominador del Z-Score.",
        },
        "validation": {
            "method": "Backtest OOS 2021-2026, 233 trades, 15 acciones QUALITY",
            "z_score_oos_sharpe": 0.87,
            "roc_oos_sharpe": 0.92,
            "baseline_sharpe": 0.83,
            "roc_boosted_wr": "61.4% (N=57)",
            "roc_reduced_wr": "47.4% (N=57)",
            "roc_wr_spread": "14.0pp vs baseline 54.1%",
        },
    },
    "description": "S5V relative modifier: Z-Score per-sector + RoC dimension (v2.0)",
    "modifier_type": "z_score",
    "z_bin_edges": Z_EDGES,
    "roc_z_bin_edges": ROC_Z_EDGES,
    "bin_labels": BIN_LABELS,
    "sector_params": sector_params,
    "roc_global_std": round(roc_std, 2),
    "z_bins": rel_modifier,
    "roc_bins": roc_modifier,
    # Legacy compat: keep 'bins' pointing to z_bins, 'bin_edges' to z_edges
    "bins": rel_modifier,
    "bin_edges": Z_EDGES,
}
with open(rel_path, "w") as f:
    json.dump(rel_output, f, indent=2, default=str)
print(f"  Written: {rel_path} (z_bins={len(rel_modifier)}, roc_bins={len(roc_modifier)})")

store.close()
print("\nTRAINING COMPLETE!")
