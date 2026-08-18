#!/usr/bin/env python3
"""
AUDITOR DE CASCADE — Test D2/D3 como modulador de cascade_conviction.
SOLO MIDE. No modifica código de producción.
Pregunta: ¿D2 o D3 como modulador MEJORA o DEGRADA el IC de cascade_50?

Test 1 (D3): modulated = cascade × (1 - w × z(D3_global))   — D3 alto (caos) = menos cascade
Test 2 (D2): modulated = cascade × gate                    — D2 flip reciente = gate (0 o descuento)

Pipeline: replica EXACTAMENTE decay_check_cascade_conviction.py (adapters reales,
dispatch por estación, type-mask, z-scores de cascade_calibration.json).
"""
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta
from scipy.stats import spearmanr

sys.path.insert(0, "/root/botero-trade")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import (
    STATION_CONFIG, d1_directional_vote, CALIBRATION_FILE,
)

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]

with open(CALIBRATION_FILE) as f:
    cal = json.load(f)

d1_mean = cal["d1_bear_5"]["mean"]
d1_std = cal["d1_bear_5"]["std"]
dom25_mean = cal["domino_zz25"]["mean"]
dom25_std = cal["domino_zz25"]["std"]

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return} for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)
df25["abs_prev_leg_return"] = np.abs(df25["prev_leg_return"])

# ---- Indicator series (D2 velocity + D3 volatility), same as decay_check ----
indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    df_ind = store.load_bars(cfg["ticker"], "1d")
    if df_ind is not None and not df_ind.empty:
        s = df_ind["close"].copy()
        s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
        indicator_series[code] = s

all_dates = set()
for s in indicator_series.values():
    all_dates.update(s.index)
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    vel = s.diff(3)
    std_2, std_10 = s.rolling(2).std(), s.rolling(10).std()
    vol = (std_2 / std_10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    date_features[f"{code}_val"] = s
    date_features[f"{code}_vel"] = vel          # D2 velocity (Δ3d)
    date_features[f"{code}_vel_prev3"] = vel.shift(3)  # D2 velocity 3 days ago (for flip)
    date_features[f"{code}_vol"] = vol          # D3 volatility (std2/std10)

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()

# ---- Build observations ----
obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index:
        continue
    feats = date_features.loc[pd_]
    votes = {}
    vels, vols, flips = {}, {}, {}
    for code in GRUPO_A:
        val = feats.get(f"{code}_val")
        vel = feats.get(f"{code}_vel", 0.0)
        vel_prev3 = feats.get(f"{code}_vel_prev3", 0.0)
        vol = feats.get(f"{code}_vol", 1.0)
        if pd.isna(val):
            continue
        if pd.isna(vel): vel = 0.0
        if pd.isna(vel_prev3): vel_prev3 = 0.0
        if pd.isna(vol): vol = 1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(
                val=float(val), d3_speed=float(vel),
                vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                votes[code] = d1_directional_vote(res.state_key)
                vels[code] = float(vel)
                vols[code] = float(vol)
                # D2 flip reciente: sign(vel_t) != sign(vel_{t-3})  (velocidad cruzó cero en ~3d)
                flips[code] = int(np.sign(vel) * np.sign(vel_prev3) < 0) if (vel != 0 and vel_prev3 != 0) else 0
        except Exception:
            continue

    p_type = row["start_type"]
    allowed = set(cal["type_mask"].get(p_type, {}).get("stations", GRUPO_A))
    w_bear = float(cal["type_mask"].get(p_type, {}).get("w_bear", 0.66))
    w_dom = float(cal["type_mask"].get(p_type, {}).get("w_dom", 0.34))

    m_votes = [v for c, v in votes.items() if c in allowed]
    if not m_votes:
        continue
    d1_bear_masked = sum(-v for v in m_votes if v < 0) / len(m_votes)
    z_bear = (d1_bear_masked - d1_mean) / d1_std
    z_dom25 = (row["abs_prev_leg_return"] - dom25_mean) / dom25_std
    cc_base = w_bear * z_bear + w_dom * z_dom25

    rec = {
        "pivot_date": pd_,
        "cascade_50": row["cascade_50"],
        "start_type": p_type,
        "cc_base": cc_base,
        "z_bear": z_bear,
        "z_dom25": z_dom25,
    }
    # D3 global = media de vol_norm sobre estaciones disponibles (Grupo A)
    rec["d3_global"] = np.mean(list(vols.values())) if vols else np.nan
    # D2 global = media de velocidad (signo) y |velocidad|
    rec["d2_mean"] = np.mean(list(vels.values())) if vels else np.nan
    rec["d2_abs_mean"] = np.mean([abs(v) for v in vels.values()]) if vels else np.nan
    # D2 flip: fracción de estaciones con flip reciente, y booleano "any flip"
    rec["d2_flip_frac"] = np.mean(list(flips.values())) if flips else 0.0
    rec["d2_any_flip"] = int(any(flips.values()))
    obs.append(rec)

df = pd.DataFrame(obs)
y = df["cascade_50"].values.astype(float)


def ic(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 30:
        return np.nan, int(m.sum())
    return float(spearmanr(a[m], b[m])[0]), int(m.sum())


print("=" * 74)
print("AUDITOR DE CASCADE — ¿D2/D3 modulan cascade_50? (MEJORA vs DEGRADA)")
print("=" * 74)
print(f"N pivots observables: {len(df)}")
base_ic, n_base = ic(df["cc_base"], y)
print(f"\nBASELINE cascade_50 (w_bear={cal['type_mask']['MIN']['w_bear']:.2f}, "
      f"w_dom={cal['type_mask']['MIN']['w_dom']:.2f}, type-mask):  IC = {base_ic:+.4f}  (N={n_base})")

# Sanity: standalone correlation of D3/D2 with cascade_50
d3_ic, _ = ic(df["d3_global"], y)
d2_ic, _ = ic(df["d2_mean"], y)
d2abs_ic, _ = ic(df["d2_abs_mean"], y)
print(f"\nSanity — señal cruda hacia cascade_50:")
print(f"  IC(D3_global, cascade_50)      = {d3_ic:+.4f}")
print(f"  IC(D2_mean (signo), cascade_50) = {d2_ic:+.4f}")
print(f"  IC(|D2|_mean, cascade_50)       = {d2abs_ic:+.4f}")

# ---- Test 1: D3 como modulador multiplicativo ----
print("\n" + "=" * 74)
print("TEST 1 — D3 modulator: cascade × (1 − w × z(D3_global))")
print("        (D3 alto = caos → menos cascade)")
print("=" * 74)
d3 = df["d3_global"].astype(float)
z_d3 = (d3 - d3.mean()) / d3.std()   # z-score centrado
for w in [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]:
    mod = df["cc_base"] * (1.0 - w * z_d3)
    r, n = ic(mod, y)
    delta = r - base_ic
    print(f"  w={w:>4}: IC = {r:+.4f}  (Δ vs baseline {delta:+.4f}, N={n})")

# ---- Test 2: D2 flip como gate ----
print("\n" + "=" * 74)
print("TEST 2 — D2 flip gate: cascade × gate (flip reciente = D2 cambió de signo)")
print("=" * 74)
for mode, gate_desc in [("kill", "gate=0 si flip (descarta), 1 si no"),
                        ("discount_half", "gate=0.5 si flip, 1 si no")]:
    for flip_key in ["d2_any_flip", "d2_flip_frac"]:
        if flip_key == "d2_any_flip":
            gate = np.where(df["d2_any_flip"].values == 1, 0.0, 1.0)
        else:
            gate = 1.0 - df["d2_flip_frac"].values  # gate continuo por fracción
        if mode == "discount_half":
            gate = np.where(gate == 0.0, 0.5, gate)
        mod = df["cc_base"] * gate
        r, n = ic(mod, y)
        delta = r - base_ic
        print(f"  [{flip_key}] {gate_desc:<34} IC = {r:+.4f}  (Δ {delta:+.4f}, N={n})")

# ---- Walk-forward OOS para baseline y mejores candidatos ----
print("\n" + "=" * 74)
print("WALK-FORWARD OOS (expanding window, 20 folds, pesos FIJOS — sin refit)")
print("=" * 74)


def wf_oos_ic(score_series, target, n_folds=20):
    score = np.asarray(score_series, dtype=float)
    tgt = np.asarray(target, dtype=float)
    order = np.argsort(df["pivot_date"].values)
    score, tgt = score[order], tgt[order]
    n = len(score)
    fold_size = n // n_folds
    ics = []
    for k in range(1, n_folds):
        lo = k * fold_size
        if lo >= n:
            break
        r, nn = ic(score[lo:], tgt[lo:])
        if not np.isnan(r):
            ics.append(r)
    return ics


base_wf = wf_oos_ic(df["cc_base"], y)
# Test1 w=0.25 y w=0.5
z_d3_arr = np.asarray(z_d3, dtype=float)
t1_w25 = df["cc_base"] * (1.0 - 0.25 * z_d3_arr)
t1_w50 = df["cc_base"] * (1.0 - 0.50 * z_d3_arr)
wf_t1_25 = wf_oos_ic(t1_w25, y)
wf_t1_50 = wf_oos_ic(t1_w50, y)

def summ(name, ics):
    arr = np.array(ics)
    pos = (arr > 0).mean() * 100
    print(f"  {name:<28} OOS IC mean={arr.mean():+.4f}  "
          f"mediana={np.median(arr):+.4f}  folds>0={pos:.0f}%  (n={len(arr)})")

summ("baseline cascade_50", base_wf)
summ("Test1 D3 w=0.25", wf_t1_25)
summ("Test1 D3 w=0.50", wf_t1_50)

print("\nConclusión (IC in-sample + OOS):")
print(f"  baseline IS={base_ic:+.4f}")
print(f"  Test1 mejor (D3 mod) IS={max(ic(df['cc_base']*(1.0-w*z_d3), y)[0] for w in [0.1,0.25,0.5,0.75,1.0]):+.4f}")
