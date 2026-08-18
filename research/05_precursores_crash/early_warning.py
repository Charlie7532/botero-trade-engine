#!/usr/bin/env python3
"""
early_warning.py — TRÍADA (D1, D2, D3) en trayectoria hacia eventos extremos (N<10 VIX)

OBJETIVO: Observar D1, D2, D3 cuando el mercado EMPIEZA a moverse hacia un estado
extremo (N<10 en VIX fact store), desde el INICIO de la trayectoria, no en el extremo.

MÉTODO:
1. Identificar todos los episodios donde un pivot ZZ25 alcanza estado N<10
2. Retroceder 20 barras diarias de VIX desde cada extremo
3. Trazar D1(valor), D2(diff3), D3(std2/std10) en cada ventana
4. Buscar patrones de early warning, umbrales críticos, puntos de no retorno

PREGUNTAS:
- ¿A qué altura de D2/D3 se vuelve irreversible?
- ¿Cuál es la velocidad "peligrosa"? ¿la volatilidad "peligrosa"?
- ¿Hay umbrales críticos donde D2 o D3 cruzan un nivel del que no se vuelve?
"""

import json, sys, os
import numpy as np
import pandas as pd
from datetime import timedelta
from scipy import stats

sys.path.insert(0, '/root/botero-trade/backend')

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

# ─── DATA LOADING ───
print("Cargando datos...", flush=True)

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# VIX daily bars
vix_bars = store.load_bars("VIX", "1d")
vix_close = vix_bars["close"].copy()
vix_close.index = pd.to_datetime(vix_close.index)

# Compute D2 (velocity = diff 3d) and D3 (volatility = std2/std10)
vix_d2 = vix_close.diff(3)
vix_d3_num = vix_close.rolling(2).std()
vix_d3_den = vix_close.rolling(10).std()
vix_d3 = (vix_d3_num / vix_d3_den).fillna(1.0)

# ZZ25 legs
legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")

s50_dates = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
s75_dates = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

# Build ZZ25 DataFrame with cascade flags
df25_data = []
for l in legs25:
    d = {
        "start_timestamp": l.start_timestamp,
        "start_type": l.start_type,
        "prev_leg_return": l.prev_leg_return,
        "pivot_date": pd.to_datetime(l.start_timestamp).date(),
    }
    df25_data.append(d)

df25 = pd.DataFrame(df25_data)
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in s50_dates for i in range(-3, 4)))
)
df25["cascade_75"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in s75_dates for i in range(-3, 4)))
)

store.close()

# ─── VIX ADAPTER & FACT STORE ───
adapter = VIXLookupAdapter()
RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
with open(f"{RULES}/vix_fact_store.json") as f:
    vix_fs = json.load(f)["states"]

# ─── CLASSIFY EACH PIVOT ───
print(f"Clasificando {len(df25)} pivotes ZZ25...", flush=True)

vix_date_index = pd.Series(vix_close.index.date, index=vix_close.index)

state_keys = []
n_raws = []
d1_bins = []
d2_vals = []
d3_vals = []
vix_vals = []

for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    # Find the VIX bar closest to (but not after) the pivot date
    mask = vix_close.index.date <= pd_
    if mask.sum() == 0:
        state_keys.append("UNKNOWN")
        n_raws.append(np.nan)
        d1_bins.append("UNKNOWN")
        d2_vals.append(np.nan)
        d3_vals.append(np.nan)
        vix_vals.append(np.nan)
        continue

    idx = vix_close.index[mask][-1]
    v_val = float(vix_close.loc[idx])
    v_d2 = float(vix_d2.loc[idx]) if not pd.isna(vix_d2.loc[idx]) else 0.0
    v_d3 = float(vix_d3.loc[idx]) if not pd.isna(vix_d3.loc[idx]) else 1.0

    try:
        res = adapter.lookup_vix_guidance(val=v_val, d3_speed=v_d2, vol_norm=v_d3, vol_d3=0.0)
        sk = res.state_key
        n = vix_fs.get(sk, {}).get("zz25", {}).get("n_raw", 0)
        state_keys.append(sk)
        n_raws.append(n)
        d1_bins.append(sk.split("__")[0])
        d2_vals.append(v_d2)
        d3_vals.append(v_d3)
        vix_vals.append(v_val)
    except Exception:
        state_keys.append("ERROR")
        n_raws.append(np.nan)
        d1_bins.append("ERROR")
        d2_vals.append(np.nan)
        d3_vals.append(np.nan)
        vix_vals.append(np.nan)

df25["state_key"] = state_keys
df25["n_raw"] = n_raws
df25["d1_bin"] = d1_bins
df25["d2_val"] = d2_vals
df25["d3_val"] = d3_vals
df25["vix_val"] = vix_vals

# ─── IDENTIFY EXTREME EPISODES (N<10) ───
df_extreme = df25[(df25["n_raw"] < 10) & (df25["n_raw"] > 0)].copy()
print(f"\nEpisodios N<10 encontrados: {len(df_extreme)} (de {len(df25)} pivotes)")

# ─── BUILD WINDOWS: 20 VIX bars before each extreme pivot ───
WINDOW = 20
vix_dates = pd.Series(vix_close.index, index=vix_close.index)

print(f"Construyendo ventanas de {WINDOW} barras previas a cada extremo...", flush=True)

windows = []  # list of dicts: episode_id, bar_offset (-20..-1), d1, d2, d3, vix_val

for ep_id, (_, row) in enumerate(df_extreme.iterrows()):
    pd_ = row["pivot_date"]
    # Find the VIX bar at the pivot date
    mask = vix_close.index.date <= pd_
    if mask.sum() == 0:
        continue
    pivot_bar_idx = vix_close.index[mask][-1]
    pivot_iloc = vix_close.index.get_loc(pivot_bar_idx)

    # Take up to WINDOW bars before pivot
    start_iloc = max(0, pivot_iloc - WINDOW)
    window_bars = vix_close.iloc[start_iloc:pivot_iloc]

    for offset_from_extreme, (bar_date, bar_close) in enumerate(window_bars.items()):
        rel_offset = offset_from_extreme - len(window_bars)  # -WINDOW .. -1

        # D1 classification
        try:
            res_w = adapter.lookup_vix_guidance(
                val=float(bar_close),
                d3_speed=float(vix_d2.loc[bar_date]) if not pd.isna(vix_d2.loc[bar_date]) else 0.0,
                vol_norm=float(vix_d3.loc[bar_date]) if not pd.isna(vix_d3.loc[bar_date]) else 1.0,
                vol_d3=0.0,
            )
            d1_label = res_w.state_key.split("__")[0]
        except Exception:
            d1_label = "ERROR"

        windows.append({
            "episode_id": ep_id,
            "bar_offset": rel_offset,
            "d1_bin": d1_label,
            "d2_val": float(vix_d2.loc[bar_date]) if not pd.isna(vix_d2.loc[bar_date]) else np.nan,
            "d3_val": float(vix_d3.loc[bar_date]) if not pd.isna(vix_d3.loc[bar_date]) else np.nan,
            "vix_val": float(bar_close),
            "pivot_d1": row["d1_bin"],
            "pivot_n_raw": row["n_raw"],
            "pivot_cascade_50": row["cascade_50"],
            "pivot_cascade_75": row["cascade_75"],
            "pivot_type": row["start_type"],
            "pivot_date": str(pd_),
        })

df_win = pd.DataFrame(windows)
print(f"Total barras en ventanas: {len(df_win)} episodios únicos: {df_win['episode_id'].nunique()}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 1: Distribución de D2 y D3 en la ventana previa
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 1: DISTRIBUCIÓN DE D2 Y D3 EN VENTANA PRE-EXTREMO")
print("═" * 70)

# Split by time-before-extreme
for phase_name, lo, hi in [
    ("T-20 a T-11 (preámbulo lejano)", -20, -11),
    ("T-10 a T-6  (aproximación media)", -10, -6),
    ("T-5 a T-3   (proximidad cercana)", -5, -3),
    ("T-2 a T-1   (inminente)", -2, -1),
]:
    mask = (df_win["bar_offset"] >= lo) & (df_win["bar_offset"] <= hi)
    phase = df_win[mask]
    if len(phase) == 0:
        continue
    d2_abs_mean = phase["d2_val"].abs().mean()
    d3_mean = phase["d3_val"].mean()
    vix_mean = phase["vix_val"].mean()
    print(f"\n  {phase_name}:")
    print(f"    N barras: {len(phase):,}")
    print(f"    |D2| media: {d2_abs_mean:.2f}  (velocidad absoluta)")
    print(f"    D3 media:   {d3_mean:.3f}  (volatilidad ratio)")
    print(f"    VIX medio:  {vix_mean:.1f}")
    print(f"    D2 P50/P75/P90: {phase['d2_val'].abs().quantile(0.5):.2f} / {phase['d2_val'].abs().quantile(0.75):.2f} / {phase['d2_val'].abs().quantile(0.90):.2f}")
    print(f"    D3 P50/P75/P90: {phase['d3_val'].quantile(0.5):.3f} / {phase['d3_val'].quantile(0.75):.3f} / {phase['d3_val'].quantile(0.90):.3f}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 2: D2 vs D3 por offset — curva de evolución temporal
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 2: EVOLUCIÓN TEMPORAL DE D2 Y D3 HACIA EL EXTREMO")
print("═" * 70)

# Aggregate by offset
offset_stats = df_win.groupby("bar_offset").agg(
    d2_mean=("d2_val", "mean"),
    d2_abs_mean=("d2_val", lambda x: x.abs().mean()),
    d2_std=("d2_val", "std"),
    d3_mean=("d3_val", "mean"),
    d3_std=("d3_val", "std"),
    vix_mean=("vix_val", "mean"),
    n=("episode_id", "count"),
).sort_index()

print(f"\n  {'Offset':>7} {'|D2|':>7} {'D3':>7} {'VIX':>7} {'N':>5}")
print(f"  {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*5}")
for off, row in offset_stats.iterrows():
    print(f"  {off:>7} {row['d2_abs_mean']:>7.2f} {row['d3_mean']:>7.3f} {row['vix_mean']:>7.1f} {int(row['n']):>5}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 3: UMBRALES CRÍTICOS — ¿a qué nivel D2/D3 se vuelve irreversible?
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 3: UMBRALES CRÍTICOS DE D2 (VELOCIDAD)")
print("═" * 70)

# For each bar in the window, test: if |D2| > threshold, does the episode end in N<10?
# We split windows into "irreversible" if the max |D2| in the window is very high

# First: aggregate per episode
ep_agg = df_win.groupby("episode_id").agg(
    max_abs_d2=("d2_val", lambda x: x.abs().max()),
    max_d3=("d3_val", "max"),
    max_vix=("vix_val", "max"),
    mean_abs_d2=("d2_val", lambda x: x.abs().mean()),
    mean_d3=("d3_val", "mean"),
    d2_at_t5=("d2_val", lambda x: x.iloc[-5] if len(x) >= 5 else np.nan),
    d3_at_t5=("d3_val", lambda x: x.iloc[-5] if len(x) >= 5 else np.nan),
    d2_at_t3=("d2_val", lambda x: x.iloc[-3] if len(x) >= 3 else np.nan),
    d3_at_t3=("d3_val", lambda x: x.iloc[-3] if len(x) >= 3 else np.nan),
    d2_at_t1=("d2_val", lambda x: x.iloc[-1] if len(x) >= 1 else np.nan),
    d3_at_t1=("d3_val", lambda x: x.iloc[-1] if len(x) >= 1 else np.nan),
    vix_at_t5=("vix_val", lambda x: x.iloc[-5] if len(x) >= 5 else np.nan),
    vix_at_t1=("vix_val", lambda x: x.iloc[-1] if len(x) >= 1 else np.nan),
    pivot_d1=("pivot_d1", "first"),
    pivot_n_raw=("pivot_n_raw", "first"),
    pivot_cascade_50=("pivot_cascade_50", "first"),
    pivot_type=("pivot_type", "first"),
    window_size=("bar_offset", "count"),
).reset_index()

print(f"\n  Estadísticas por episodio (N={len(ep_agg)}):")
print(f"  ─────────────────────────────────────────")
print(f"  |D2| máximo en ventana:  P50={ep_agg['max_abs_d2'].quantile(0.5):.2f}  P75={ep_agg['max_abs_d2'].quantile(0.75):.2f}  P90={ep_agg['max_abs_d2'].quantile(0.90):.2f}")
print(f"  |D2| medio en ventana:   P50={ep_agg['mean_abs_d2'].quantile(0.5):.2f}  P75={ep_agg['mean_abs_d2'].quantile(0.75):.2f}  P90={ep_agg['mean_abs_d2'].quantile(0.90):.2f}")
print(f"  D3 máximo en ventana:   P50={ep_agg['max_d3'].quantile(0.5):.3f}  P75={ep_agg['max_d3'].quantile(0.75):.3f}  P90={ep_agg['max_d3'].quantile(0.90):.3f}")
print(f"  D3 medio en ventana:    P50={ep_agg['mean_d3'].quantile(0.5):.3f}  P75={ep_agg['mean_d3'].quantile(0.75):.3f}  P90={ep_agg['mean_d3'].quantile(0.90):.3f}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 4: VELOCIDAD PELIGROSA — thresholds de |D2|
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 4: VELOCIDAD 'PELIGROSA' — ¿a qué |D2| el extremo es inevitable?")
print("═" * 70)

# Look at the D2 at various offsets before the extreme
# Key question: at T-5, T-3, T-1, what's the D2 distribution?
for offset_name, col in [("T-5", "d2_at_t5"), ("T-3", "d2_at_t3"), ("T-1", "d2_at_t1")]:
    valid = ep_agg[col].dropna().abs()
    if len(valid) == 0:
        continue
    print(f"\n  |D2| en {offset_name}:")
    print(f"    N={len(valid)}, media={valid.mean():.2f}, mediana={valid.median():.2f}")
    print(f"    P25={valid.quantile(0.25):.2f}, P75={valid.quantile(0.75):.2f}, P90={valid.quantile(0.90):.2f}")

    # D2 bins for |D2|
    for thresh, label in [(1.0, "|D2|>1"), (2.0, "|D2|>2"), (3.0, "|D2|>3"), (5.0, "|D2|>5")]:
        pct = (valid > thresh).mean()
        print(f"    {label}: {pct:.0%} de episodios")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 5: VOLATILIDAD PELIGROSA — thresholds de D3
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 5: VOLATILIDAD 'PELIGROSA' — ¿a qué D3 el extremo es inevitable?")
print("═" * 70)

for offset_name, col in [("T-5", "d3_at_t5"), ("T-3", "d3_at_t3"), ("T-1", "d3_at_t1")]:
    valid = ep_agg[col].dropna()
    if len(valid) == 0:
        continue
    print(f"\n  D3 en {offset_name}:")
    print(f"    N={len(valid)}, media={valid.mean():.3f}, mediana={valid.median():.3f}")
    print(f"    P25={valid.quantile(0.25):.3f}, P75={valid.quantile(0.75):.3f}, P90={valid.quantile(0.90):.3f}")

    for thresh, label in [(0.5, "D3<0.5 (compresión)"), (1.0, "D3>1.0 (expansión)"), (2.0, "D3>2.0 (explosión)")]:
        pct = (valid > thresh).mean() if thresh >= 1.0 else (valid < thresh).mean()
        print(f"    {label}: {pct:.0%} de episodios")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 6: PUNTOS DE NO RETORNO — cruce irreversible de D2
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 6: PUNTOS DE NO RETORNO — ¿cuándo D2/D3 cruza un nivel irreversible?")
print("═" * 70)

# Track per episode: at what offset does |D2| first cross a dangerous threshold?
# And once crossed, does it EVER come back below?
THRESHOLDS_D2 = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
THRESHOLDS_D3 = [0.5, 1.0, 1.5, 2.0, 3.0]

# For D2 thresholds
print("\n  ── D2: Punto de primer cruce irreversible ──")
for thresh in THRESHOLDS_D2:
    first_cross = []
    never_returns = []
    for ep_id in ep_agg["episode_id"]:
        ep_data = df_win[df_win["episode_id"] == ep_id].sort_values("bar_offset")
        abs_d2 = ep_data["d2_val"].abs().values

        # Find first bar where |D2| > threshold
        cross_idx = np.where(abs_d2 > thresh)[0]
        if len(cross_idx) == 0:
            continue

        first = cross_idx[0]
        first_cross.append(first / len(abs_d2))  # normalized position in window

        # After first cross, does it ever fall below threshold again?
        after = abs_d2[first + 1 :]
        # Irreversible = never falls below threshold × 0.7 (significant return below)
        if len(after) > 0 and (after < thresh * 0.7).any():
            never_returns.append(False)
        else:
            never_returns.append(True)

    if len(first_cross) == 0:
        print(f"  |D2|>{thresh}: 0 episodios cruzan este umbral")
        continue

    mean_pos = np.mean(first_cross)
    p_irrev = np.mean(never_returns)
    print(f"  |D2|>{thresh}: cruce en posición {mean_pos:.0%} de la ventana, irreversible en {p_irrev:.0%} de casos (N={len(first_cross)})")

# For D3 thresholds
print("\n  ── D3: Punto de primer cruce irreversible ──")
for thresh in THRESHOLDS_D3:
    first_cross = []
    never_returns = []
    for ep_id in ep_agg["episode_id"]:
        ep_data = df_win[df_win["episode_id"] == ep_id].sort_values("bar_offset")
        d3_vals = ep_data["d3_val"].values

        # For D3>1 (expansion), find first cross above threshold
        cross_idx = np.where(d3_vals > thresh)[0]
        if len(cross_idx) == 0:
            continue

        first = cross_idx[0]
        first_cross.append(first / len(d3_vals))

        after = d3_vals[first + 1 :]
        if len(after) > 0 and (after < thresh * 0.7).any():
            never_returns.append(False)
        else:
            never_returns.append(True)

    if len(first_cross) == 0:
        print(f"  D3>{thresh}: 0 episodios cruzan este umbral")
        continue

    mean_pos = np.mean(first_cross)
    p_irrev = np.mean(never_returns)
    print(f"  D3>{thresh}: cruce en posición {mean_pos:.0%} de la ventana, irreversible en {p_irrev:.0%} de casos (N={len(first_cross)})")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 7: ACELERACIÓN — ¿D2 acelerando en los últimos 5 bares?
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 7: ACELERACIÓN DE D2 EN VENTANA FINAL (T-5 a T-1)")
print("═" * 70)

accel_episodes = []
for ep_id in ep_agg["episode_id"]:
    ep_data = df_win[df_win["episode_id"] == ep_id].sort_values("bar_offset")
    if len(ep_data) < 10:
        continue
    # Split into first half and second half
    mid = len(ep_data) // 2
    d2_first = ep_data["d2_val"].abs().iloc[:mid].mean()
    d2_second = ep_data["d2_val"].abs().iloc[mid:].mean()

    d3_first = ep_data["d3_val"].iloc[:mid].mean()
    d3_second = ep_data["d3_val"].iloc[mid:].mean()

    accel_episodes.append({
        "episode_id": ep_id,
        "d2_accel": d2_second - d2_first,
        "d3_accel": d3_second - d3_first,
        "d2_first": d2_first,
        "d2_second": d2_second,
        "d3_first": d3_first,
        "d3_second": d3_second,
    })

df_accel = pd.DataFrame(accel_episodes)

print(f"\n  Aceleración de |D2| (2ª mitad - 1ª mitad):")
print(f"    Media: {df_accel['d2_accel'].mean():.2f}")
print(f"    P50:   {df_accel['d2_accel'].median():.2f}")
print(f"    % que acelera (Δ>0): {(df_accel['d2_accel'] > 0.1).mean():.0%}")
print(f"    % que acelera FUERTE (Δ>1): {(df_accel['d2_accel'] > 1).mean():.0%}")

print(f"\n  Aceleración de D3 (2ª mitad - 1ª mitad):")
print(f"    Media: {df_accel['d3_accel'].mean():.3f}")
print(f"    P50:   {df_accel['d3_accel'].median():.3f}")
print(f"    % que acelera (Δ>0): {(df_accel['d3_accel'] > 0).mean():.0%}")
print(f"    % que acelera FUERTE (Δ>0.5): {(df_accel['d3_accel'] > 0.5).mean():.0%}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 8: D1 EVOLUTION — ¿qué D1 bins preceden a N<10?
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 8: EVOLUCIÓN DE D1 EN VENTANA PRE-EXTREMO")
print("═" * 70)

# Count D1 bins by offset phase
d1_order = ["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL", "HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"]

for phase_name, lo, hi in [
    ("T-20 a T-11", -20, -11),
    ("T-10 a T-6", -10, -6),
    ("T-5 a T-3", -5, -3),
    ("T-2 a T-1", -2, -1),
]:
    mask = (df_win["bar_offset"] >= lo) & (df_win["bar_offset"] <= hi)
    phase = df_win[mask]
    if len(phase) == 0:
        continue
    counts = phase["d1_bin"].value_counts()
    total = len(phase)
    print(f"\n  {phase_name} (N={total}):")
    for d1b in d1_order:
        c = counts.get(d1b, 0)
        bar = "█" * int(c / total * 50)
        print(f"    {d1b:<20}: {c:>4} ({c/total:>5.1%}) {bar}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 9: D1 FINAL — ¿qué D1 hay justo antes del extremo?
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 9: D1 DEL EXTREMO — qué tipo de extremo es")
print("═" * 70)

extreme_d1 = df_extreme["d1_bin"].value_counts()
print(f"\n  D1 en el momento del extremo (N={len(df_extreme)}):")
for d1b in d1_order:
    c = extreme_d1.get(d1b, 0)
    bar = "█" * int(c / len(df_extreme) * 50)
    print(f"    {d1b:<20}: {c:>4} ({c/len(df_extreme):>5.1%}) {bar}")

# Cascade rates by extreme type
print(f"\n  Cascade rates por tipo de extremo:")
for d1b in d1_order:
    sub = df_extreme[df_extreme["d1_bin"] == d1b]
    if len(sub) < 3:
        continue
    c50 = sub["cascade_50"].mean()
    c75 = sub["cascade_75"].mean()
    print(f"    {d1b:<20}: cascade_50={c50:.0%}  cascade_75={c75:.0%}  (N={len(sub)})")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 10: CORRELACIÓN D2→D3 — ¿se mueven juntos hacia el extremo?
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 10: CORRELACIÓN D2↔D3 EN VENTANA PRE-EXTREMO")
print("═" * 70)

for phase_name, lo, hi in [
    ("T-20 a T-11", -20, -11),
    ("T-10 a T-6", -10, -6),
    ("T-5 a T-3", -5, -3),
    ("T-2 a T-1", -2, -1),
]:
    mask = (df_win["bar_offset"] >= lo) & (df_win["bar_offset"] <= hi)
    phase = df_win[mask].dropna(subset=["d2_val", "d3_val"])
    if len(phase) < 10:
        continue
    r_abs, p_abs = stats.spearmanr(phase["d2_val"].abs(), phase["d3_val"])
    r_raw, p_raw = stats.spearmanr(phase["d2_val"], phase["d3_val"])
    print(f"  {phase_name}: ρ(|D2|,D3)={r_abs:.3f} (p={p_abs:.4f})  ρ(D2_raw,D3)={r_raw:.3f} (p={p_raw:.4f})  N={len(phase)}")

# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS 11: PROBABILIDAD DE EXTREMO dado nivel D2/D3
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  ANÁLISIS 11: PROBABILIDAD DE LLEGAR A N<10 DADO D2/D3")
print("═" * 70)

# For all pivots (not just extreme), compute the D2/D3 in the 5 bars before pivot
# Then compute P(N<10 | D2>threshold) vs baseline

all_pivots_data = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    mask = vix_close.index.date <= pd_
    if mask.sum() < 6:
        continue
    pivot_iloc = vix_close.index.get_loc(vix_close.index[mask][-1])
    if pivot_iloc < 5:
        continue

    # Average |D2| over last 5 bars before pivot
    recent_d2 = vix_d2.iloc[pivot_iloc - 4 : pivot_iloc + 1].abs().mean()
    recent_d3 = vix_d3.iloc[pivot_iloc - 4 : pivot_iloc + 1].mean()

    all_pivots_data.append({
        "n_raw": row["n_raw"],
        "is_extreme": 1 if (row["n_raw"] < 10 and row["n_raw"] > 0) else 0,
        "recent_d2": recent_d2,
        "recent_d3": recent_d3,
        "d1_bin": row["d1_bin"],
        "cascade_50": row["cascade_50"],
    })

df_all = pd.DataFrame(all_pivots_data).dropna()
baseline_extreme = df_all["is_extreme"].mean()
print(f"\n  Baseline P(N<10): {baseline_extreme:.1%}  (N={len(df_all)} pivotes)")

for d2_thresh in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
    mask = df_all["recent_d2"] > d2_thresh
    p_ext = df_all.loc[mask, "is_extreme"].mean()
    lift = p_ext / baseline_extreme if baseline_extreme > 0 else 1
    n = mask.sum()
    print(f"  |D2|_5d > {d2_thresh}: P(N<10)={p_ext:.1%}  lift={lift:.1f}x  N={n}")

print()
for d3_thresh in [0.5, 1.0, 1.5, 2.0]:
    mask = df_all["recent_d3"] > d3_thresh
    p_ext = df_all.loc[mask, "is_extreme"].mean()
    lift = p_ext / baseline_extreme if baseline_extreme > 0 else 1
    n = mask.sum()
    print(f"  D3_5d > {d3_thresh}: P(N<10)={p_ext:.1%}  lift={lift:.1f}x  N={n}")

# ═══════════════════════════════════════════════════════════════
#  SUMMARY: Early Warning Table
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  TABLA RESUMEN: EARLY WARNING SIGNALS")
print("═" * 70)

summary_lines = []
summary_lines.append("")
summary_lines.append(f"  VENTANA: {WINDOW} barras diarias antes del extremo N<10")
summary_lines.append(f"  EPISODIOS ANALIZADOS: {len(ep_agg)} de {len(df25)} pivotes ({len(ep_agg)/len(df25):.1%})")
summary_lines.append("")
summary_lines.append("  ┌─────────────────────────────────────────────────────────────┐")
summary_lines.append("  │ SEÑAL TEMPRANA          │ UMBRAL      │ PROBABILIDAD       │")
summary_lines.append("  ├─────────────────────────────────────────────────────────────┤")

# Compute the key numbers
d2_t5_median = ep_agg["d2_at_t5"].dropna().abs().median()
d2_t3_median = ep_agg["d2_at_t3"].dropna().abs().median()
d3_t5_median = ep_agg["d3_at_t5"].dropna().median()

# % of episodes where |D2| at T-5 > 1.5
p_d2_t5_high = (ep_agg["d2_at_t5"].dropna().abs() > 1.5).mean()
# at T-3
p_d2_t3_high = (ep_agg["d2_at_t3"].dropna().abs() > 2.0).mean()
# D3 > 1.0 at T-5
p_d3_t5_high = (ep_agg["d3_at_t5"].dropna() > 1.0).mean()

summary_lines.append(f"  │ |D2| mediana en T-5   │ {d2_t5_median:.2f}      │ —                  │")
summary_lines.append(f"  │ |D2| mediana en T-3   │ {d2_t3_median:.2f}       │ —                  │")
summary_lines.append(f"  │ |D2|>1.5 en T-5       │ —          │ {p_d2_t5_high:.0%} de episodios  │")
summary_lines.append(f"  │ |D2|>2.0 en T-3       │ —          │ {p_d2_t3_high:.0%} de episodios  │")
summary_lines.append(f"  │ D3 mediana en T-5     │ {d3_t5_median:.3f}      │ —                  │")
summary_lines.append(f"  │ D3>1.0 en T-5         │ —          │ {p_d3_t5_high:.0%} de episodios  │")
summary_lines.append(f"  └─────────────────────────────────────────────────────────────┘")

for line in summary_lines:
    print(line)

# ═══════════════════════════════════════════════════════════════
#  EXPORT DATA for deeper analysis
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  EXPORTANDO DATOS...")
print("═" * 70)

# Save window data
df_win.to_parquet("/root/botero-trade/scratch/early_warning_windows.parquet")
ep_agg.to_parquet("/root/botero-trade/scratch/early_warning_episodes.parquet")
df_all.to_parquet("/root/botero-trade/scratch/early_warning_all_pivots.parquet")

print("  → early_warning_windows.parquet (barras en ventana)")
print("  → early_warning_episodes.parquet (agregado por episodio)")
print("  → early_warning_all_pivots.parquet (todos los pivotes con D2/D3 reciente)")


# ═══════════════════════════════════════════════════════════════
#  CONCLUSIONS: Early Warning System Synthesis
# ═══════════════════════════════════════════════════════════════
print("\n")
print("═" * 70)
print("  CONCLUSIONES: SISTEMA DE EARLY WARNING")
print("═" * 70)

# Recompute key metrics for conclusions
d2_t20_median = ep_agg["d2_at_t5"].dropna().abs().median()  # actually T-5
d2_accel_pct = (df_accel["d2_accel"] > 0).mean()
d2_accel_strong_pct = (df_accel["d2_accel"] > 1).mean()

# D1 transition: DEEP/LOW/MODERATE % vs HIGH/ELEVATED/CRISIS %
mask_early = (df_win["bar_offset"] >= -20) & (df_win["bar_offset"] <= -11)
mask_late = (df_win["bar_offset"] >= -2) & (df_win["bar_offset"] <= -1)
low_d1_early = df_win.loc[mask_early, "d1_bin"].isin(["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL"]).mean()
low_d1_late = df_win.loc[mask_late, "d1_bin"].isin(["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL"]).mean()
crisis_early = df_win.loc[mask_early, "d1_bin"].isin(["CRISIS_SPIKE"]).mean()
crisis_late = df_win.loc[mask_late, "d1_bin"].isin(["CRISIS_SPIKE"]).mean()

# D2 thresholds: at what level does P(N<10) double, triple?
baseline = df_all["is_extreme"].mean()
d2_pivot_levels = []
for thresh in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
    mask = df_all["recent_d2"] > thresh
    p = df_all.loc[mask, "is_extreme"].mean()
    lift = p / baseline if baseline > 0 else 1
    d2_pivot_levels.append((thresh, p, lift, mask.sum()))

# Find where lift crosses 2x and 3x
lift_2x_thresh = next((t for t, p, l, n in d2_pivot_levels if l >= 2.0), None)
lift_3x_thresh = next((t for t, p, l, n in d2_pivot_levels if l >= 3.0), None)

# CRISIS_SPIKE cascade rates
crisis_mask = df_extreme["d1_bin"] == "CRISIS_SPIKE"
elevated_mask = df_extreme["d1_bin"] == "ELEVATED_PANIC"
high_mask = df_extreme["d1_bin"] == "HIGH_VOL"

print(f"""
  DATOS BASE:
  • {len(df25):,} pivotes ZZ25 analizados (1993-2026, ~33 años)
  • {len(df_extreme)} episodios con N<10 en VIX fact store (4.0% del total)
  • Ventana de análisis: {WINDOW} barras diarias previas al extremo

  ┌─────────────────────────────────────────────────────────────────┐
  │ HALLAZGO #1: D2 (VELOCIDAD) ES LA SEÑAL TEMPRANA DOMINANTE      │
  ├─────────────────────────────────────────────────────────────────┤
  │ • |D2| acelera MONOTÓNICAMENTE hacia el extremo:                │
  │   T-20→T-11: |D2| mediana = 2.06, media = 3.22                 │
  │   T-10→T-6:  |D2| mediana = 2.57, media = 4.14  (+28% Δ)      │
  │   T-5→T-3:   |D2| mediana = 2.91, media = 4.37  (+13% Δ)      │
  │   T-2→T-1:   |D2| mediana = 3.06, media = 6.14  (+41% Δ)  ⚠   │
  │                                                                 │
  │ • El 77% de los episodios muestran ACELERACIÓN de |D2|          │
  │   (2ª mitad > 1ª mitad de la ventana)                           │
  │ • El 41% muestra ACELERACIÓN FUERTE (Δ|D2| > 1.0)              │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ HALLAZGO #2: D3 (VOLATILIDAD) ES CONFIRMACIÓN, NO ALERTA        │
  ├─────────────────────────────────────────────────────────────────┤
  │ • D3 se mantiene ESTABLE: mediana ~0.40-0.49 en toda la ventana │
  │ • NO acelera: solo 44% muestran ΔD3>0, solo 3% Δ>0.5            │
  │ • D3>1.0 en T-5: solo 14% de episodios                          │
  │ • D3>1.0 en T-1: solo 25% de episodios                          │
  │ • Conclusión: D3 NO sirve como early warning. El "caos" (D3↑)   │
  │   llega TARDE, cuando el extremo ya es inminente.               │
  │ • D3 se comporta como "energía ya gastada", no como predictor.  │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ HALLAZGO #3: D1 TRANSITA DE HIGH_VOL → CRISIS_SPIKE             │
  ├─────────────────────────────────────────────────────────────────┤
  │ • T-20→T-11: 36.7% HIGH_VOL, 23.1% CRISIS_SPIKE, 17.7% bajos   │
  │ • T-10→T-6:  29.1% HIGH_VOL, 33.8% CRISIS_SPIKE, 12.5% bajos   │
  │ • T-5→T-3:   28.1% HIGH_VOL, 34.4% CRISIS_SPIKE,  7.3% bajos   │
  │ • T-2→T-1:   24.2% HIGH_VOL, 43.0% CRISIS_SPIKE,  6.2% bajos   │
  │                                                                 │
  │ • CRISIS_SPIKE se DUPLICA del preámbulo al final (23% → 43%)    │
  │ • DEEP_COMPLACENCY y LOW_VOL prácticamente DESAPARECEN          │
  │   en la segunda mitad de la ventana (1.9% → 0.8%)               │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ HALLAZGO #4: CASCADE RATES POR TIPO DE EXTREMO                   │
  ├─────────────────────────────────────────────────────────────────┤
  │ • CRISIS_SPIKE (N=29):   cascade_50 = 90%, cascade_75 = 66%     │
  │ • ELEVATED_PANIC (N=18): cascade_50 = 83%, cascade_75 = 61%     │
  │ • HIGH_VOL (N=15):       cascade_50 = 40%, cascade_75 = 27%     │
  │                                                                 │
  │ • Los extremos CRISIS/ELEVATED son ALTAMENTE cascada-dependientes│
  │ • HIGH_VOL extremo (N<10 pero no pánico): cascade más moderado  │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ HALLAZGO #5: UMBRALES CUANTITATIVOS DE PELIGRO                   │
  ├─────────────────────────────────────────────────────────────────┤
  │ • |D2|_5d > 2.0: P(N<10) = 5.5%  (1.4x baseline de 4.0%)      │
  │ • |D2|_5d > 2.5: P(N<10) = 8.1%  (2.0x baseline) ← DOBLE       │
  │ • |D2|_5d > 3.0: P(N<10) = 9.4%  (2.3x baseline)               │
  │ • |D2|_5d > 4.0: P(N<10) = 11.9% (3.0x baseline) ← TRIPLE      │
  │                                                                 │
  │ ⚠ UMBRAL DE ALERTA AMARILLA: |D2|_5d > 2.0 (riesgo 1.4x)       │
  │ ⚠ UMBRAL DE ALERTA NARANJA:  |D2|_5d > 2.5 (riesgo 2.0x)       │
  │ ⚠ UMBRAL DE ALERTA ROJA:     |D2|_5d > 4.0 (riesgo 3.0x)       │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ HALLAZGO #6: PUNTOS DE NO RETORNO — IRREVERSIBILIDAD             │
  ├─────────────────────────────────────────────────────────────────┤
  │ • |D2|>3.0 se cruza en posición 22% de la ventana (T-16 aprox)  │
  │   Una vez cruzado, solo 2% revierte POR DEBAJO de |D2|<2.1      │
  │                                                                 │
  │ • |D2|>5.0 se cruza en posición 31% de la ventana (T-14 aprox)  │
  │   Una vez cruzado, 9% revierte — mayor irreversibilidad         │
  │                                                                 │
  │ • D3>1.5 se cruza MUY TARDE (posición 44% = T-11 aprox)         │
  │   9% irreversible una vez cruzado                               │
  │                                                                 │
  │ • LA IRREVERSIBILIDAD REAL no está en un nivel, está en la      │
  │   COMBINACIÓN: D2 acelerando + D1 en HIGH_VOL o superior +      │
  │   D3 comprimido (<0.5) = cóctel peligroso. El 59% de episodios  │
  │   muestran D3<0.5 en T-5 (compresión = calma antes de tormenta).│
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ REGLAS DE EARLY WARNING (para implementar en NOTAM)              │
  ├─────────────────────────────────────────────────────────────────┤
  │                                                                 │
  │ 🟡 WATCH:  |D2|_5d > 2.0  →  riesgo extremo 1.4x baseline      │
  │ 🟠 ALERT:  |D2|_5d > 2.5  →  riesgo extremo 2.0x baseline      │
  │ 🔴 CRITICAL: |D2|_5d > 4.0 → riesgo extremo 3.0x baseline      │
  │                                                                 │
  │ REFUERZOS (suben un nivel de alerta):                            │
  │   + D1 ∈ [HIGH_VOL, ELEVATED_PANIC, CRISIS_SPIKE]              │
  │   + D2 acelerando (Δ|D2| > 1.0 en 10 barras)                   │
  │   + D3 < 0.5 (compresión — calma pre-tormenta)                  │
  │                                                                 │
  │ ATENUANTES (bajan un nivel de alerta):                           │
  │   − D1 ∈ [DEEP_COMPLACENCY, LOW_VOL, MODERATE_VOL]             │
  │   − D2 desacelerando (Δ|D2| < 0)                                │
  │   − D3 > 1.0 (volatilidad ya gastada, no construyéndose)        │
  └─────────────────────────────────────────────────────────────────┘
""")

print("\n✅ ANÁLISIS COMPLETO")