#!/usr/bin/env python3
"""
RECALIBRAR CASCADE — edges trailing 3 años (tail(756))
=======================================================
Los fact stores fueron regenerados con edges trailing 3 años. El cascade OOS
cayó de +0.348 a +0.204 (−41%). Este script RECALIBRA los pesos del cascade
sobre los NUEVOS edges para recuperar IC.

MECANISMO (igual que decay_check_cascade_conviction.py):
  - cascade_50    = w_bear     × z(d1_bear_5) + (1−w_bear)     × z(|prev_leg_return_zz25|)
  - cascade_75    = w_bear_c75 × z(d1_bear_5) + (1−w_bear_c75) × z(|prev_leg_return_zz50|)
  - cascade_50to75= w          × z(d1_bear_5) + (1−w)          × z(|prev_leg_return_zz50|)
  - d1_bear_5 = promedio de votos D1 del Grupo A (VIX, BSI, FG, Credit, Rotation)
    con type_mask (FG excluido en MAX), igual que decay_check.
  - z_dom25 = z-score de |prev_leg_return| (NO cambia con edges — es zigzag puro).

GRID SEARCH:
  - w_bear ∈ [0.10, 0.90] paso 0.05, para cada target.
  - Para cada w, IC IS (Spearman) sobre todos los pivotes (μ/σ full-sample).
  - Walk-forward OOS (26 folds expanding window) con el w óptimo (μ/σ refit por fold).

Script: research/02_cascade_conviction/recalibrar_cascade_trailing.py
NO modifica código de producción.
"""
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta
from scipy.stats import spearmanr

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import (
    STATION_CONFIG, d1_directional_vote, GRUPO_A_PREDICTORS, CALIBRATION_FILE,
)

# ── Calibration (type_mask ausente → fallback defaults de decay_check) ─────
with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
    calibration = json.load(f)
type_mask_cfg = calibration.get("type_mask", {})

# Pesos viejos (validados OOS) — para comparar
VIEJOS = {
    "cascade_50":     {"w_bear": 0.66},
    "cascade_75":     {"w_bear_c75": 0.50},
    "cascade_50to75": {"w": 0.15},
}
VIEJO_OOS_C50 = 0.348  # referencia OOS viejo cascade_50

GRID_START, GRID_END, GRID_STEP = 0.10, 0.90, 0.05
N_FOLDS = 26
RNG_SEED = 42


def compute_ic(score, target):
    """Spearman IC entre score y target."""
    s = np.asarray(score, dtype=float)
    t = np.asarray(target, dtype=float)
    valid = ~np.isnan(s) & ~np.isnan(t)
    s, t = s[valid], t[valid]
    if len(s) < 10 or np.std(s) == 0 or np.std(t) == 0:
        return np.nan
    ic, _ = spearmanr(s, t)
    return float(ic) if not np.isnan(ic) else np.nan


# ═══════════════════════════════════════════════════════════════════════════
# 1. CARGAR DATOS (réplica exacta de walkforward_trailing.py / decay_check)
# ═══════════════════════════════════════════════════════════════════════════
print("═" * 74)
print("1. CARGANDO DATOS — TimescaleDataStore + ZigzagLegRepository")
print("═" * 74)

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")

starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
starts75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return} for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["abs_prev_leg_return"] = df25["prev_leg_return"].abs()
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)
df25["cascade_75"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
)

df50_legs = pd.DataFrame([
    {"start_timestamp": pd.to_datetime(l.start_timestamp), "prev_leg_return_zz50": l.prev_leg_return}
    for l in legs50
]).dropna().sort_values("start_timestamp").reset_index(drop=True)
df50_legs["abs_prev_leg_return_zz50"] = df50_legs["prev_leg_return_zz50"].abs()

df25_sorted = df25.sort_values("start_timestamp").copy()
df25_sorted["ts"] = pd.to_datetime(df25_sorted["start_timestamp"])
df50_sorted = df50_legs.sort_values("start_timestamp").copy()
df50_sorted["ts"] = pd.to_datetime(df50_sorted["start_timestamp"])

df25_merged = pd.merge_asof(
    df25_sorted, df50_sorted[["ts", "abs_prev_leg_return_zz50"]],
    on="ts", direction="backward",
)

df50 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return} for l in legs50
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df50["pivot_date"] = pd.to_datetime(df50["start_timestamp"]).dt.date
df50["abs_prev_leg_return"] = df50["prev_leg_return"].abs()
df50["cascade_50to75"] = df50["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
)

# Series de indicadores
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
    date_features[f"{code}_vel"] = vel
    date_features[f"{code}_vol"] = vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()


def build_obs(pivots_df):
    """Réplica exacta de build_obs_df() de decay_check (con type_mask)."""
    obs = []
    for _, row in pivots_df.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]

        votes = {}
        for code, adapter in adapters.items():
            val = feats.get(f"{code}_val")
            vel = feats.get(f"{code}_vel", 0.0)
            vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val):
                continue
            if pd.isna(vel):
                vel = 0.0
            if pd.isna(vol):
                vol = 1.0
            try:
                method_name = STATION_CONFIG[code]["method"]
                lookup_fn = getattr(adapter, method_name)
                res = lookup_fn(val=float(val), d3_speed=float(vel),
                                vol_norm=float(vol), vol_d3=float(vol))
                if res and res.state_key:
                    votes[code] = d1_directional_vote(res.state_key)
            except Exception:
                continue

        p_type = row.get("start_type", "MIN")
        type_cfg = type_mask_cfg.get(p_type, {
            "stations": ["vix", "bsi", "fg", "credit", "rotation"]
            if p_type == "MIN"
            else ["vix", "bsi", "credit", "rotation"],
        })
        allowed = set(type_cfg.get("stations", GRUPO_A_PREDICTORS))
        m_votes = [v for c, v in votes.items() if c in allowed]
        if not m_votes:
            continue
        m_bear = sum(-v for v in m_votes if v < 0)  # conteo fraccional

        rec = {
            "pivot_date": pd_,
            "pivot_type": p_type,
            "abs_prev_leg_return": row["abs_prev_leg_return"],
            "d1_bear_5": m_bear / len(m_votes),
        }
        if "abs_prev_leg_return_zz50" in row:
            rec["abs_prev_leg_return_zz50"] = row["abs_prev_leg_return_zz50"]
        for col in ["cascade_50", "cascade_75", "cascade_50to75"]:
            if col in row:
                rec[col] = row[col]
        obs.append(rec)
    return pd.DataFrame(obs)


df_obs_25 = build_obs(df25_merged).sort_values("pivot_date").reset_index(drop=True)
df_obs_50 = build_obs(df50).sort_values("pivot_date").reset_index(drop=True)

print(f"  zz25 observaciones: {len(df_obs_25)}")
print(f"  zz50 observaciones: {len(df_obs_50)}")
print(f"  cascade_50  prevalencia: {df_obs_25['cascade_50'].mean():.2%}")
print(f"  cascade_75  prevalencia: {df_obs_25['cascade_75'].mean():.2%}")
print(f"  cascade_50to75 prevalencia: {df_obs_50['cascade_50to75'].mean():.2%}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. GRID SEARCH — IC IS (Spearman) sobre todos los pivotes, μ/σ full-sample
# ═══════════════════════════════════════════════════════════════════════════
TARGETS = [
    ("cascade_50",     df_obs_25, "abs_prev_leg_return",     "cascade_50"),
    ("cascade_75",     df_obs_25, "abs_prev_leg_return_zz50", "cascade_75"),
    ("cascade_50to75", df_obs_50, "abs_prev_leg_return",     "cascade_50to75"),
]

print("\n" + "═" * 74)
print("2. GRID SEARCH w_bear ∈ [0.10, 0.90] paso 0.05 — IC IS (Spearman)")
print("═" * 74)

grid_results = {}

for label, obs_df, dom_col, target_col in TARGETS:
    z_bear = (obs_df["d1_bear_5"] - obs_df["d1_bear_5"].mean()) / obs_df["d1_bear_5"].std()
    z_dom = (obs_df[dom_col] - obs_df[dom_col].mean()) / obs_df[dom_col].std()

    best_w, best_ic = None, -np.inf
    rows = []
    for w in np.arange(GRID_START, GRID_END + 1e-9, GRID_STEP):
        w = round(float(w), 2)
        score = w * z_bear + (1 - w) * z_dom
        ic = compute_ic(score, obs_df[target_col].values)
        rows.append((w, ic))
        if ic is not None and not np.isnan(ic) and ic > best_ic:
            best_ic, best_w = ic, w

    grid_results[label] = {"best_w": best_w, "best_ic": best_ic, "grid": rows}

    print(f"\n  {label:<14s} (target {target_col}, dom {dom_col})")
    print(f"  {'w_bear':>7s} {'IC IS':>8s}")
    for w, ic in rows:
        marker = " ← óptimo" if (ic is not None and w == best_w) else ""
        print(f"  {w:>7.2f} {ic:>+8.4f}{marker}")
    print(f"  → w óptimo = {best_w:.2f}  (IC IS {best_ic:+.4f})")


# ═══════════════════════════════════════════════════════════════════════════
# 2.5. DESCOMPOSICIÓN DE SEÑAL — ¿qué componente degradó?
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 74)
print("2.5. DESCOMPOSICIÓN DE SEÑAL — z_bear (d1_bear_5) vs z_dom (domino)")
print("═" * 74)

decomp = {}
for label, obs_df, dom_col, target_col in TARGETS:
    z_bear = (obs_df["d1_bear_5"] - obs_df["d1_bear_5"].mean()) / obs_df["d1_bear_5"].std()
    z_dom = (obs_df[dom_col] - obs_df[dom_col].mean()) / obs_df[dom_col].std()
    ic_bear_is = compute_ic(z_bear, obs_df[target_col].values)
    ic_dom_is = compute_ic(z_dom, obs_df[target_col].values)

    # OOS standalone (z_dom no depende de edges → debe ser estable)
    fold_bear, fold_dom = [], []
    n = len(obs_df)
    fold_size = max(n // N_FOLDS, 1)
    for i in range(1, N_FOLDS):
        split_idx = i * fold_size
        if split_idx >= n - fold_size:
            break
        train = obs_df.iloc[:split_idx]
        test = obs_df.iloc[split_idx:split_idx + fold_size]
        if len(train) < 30 or len(test) < 10:
            continue
        d1_tr, dom_tr = train["d1_bear_5"].dropna(), train[dom_col].dropna()
        if len(d1_tr) < 10 or len(dom_tr) < 10:
            continue
        d1_m, d1_s = d1_tr.mean(), d1_tr.std()
        dom_m, dom_s = dom_tr.mean(), dom_tr.std()
        if d1_s == 0 or dom_s == 0:
            continue
        td1 = test["d1_bear_5"].values.astype(float)
        tdom = test[dom_col].values.astype(float)
        tgt = test[target_col].values.astype(float)
        valid = ~np.isnan(td1) & ~np.isnan(tdom)
        if valid.sum() < 10:
            continue
        zb = (td1[valid] - d1_m) / d1_s
        zd = (tdom[valid] - dom_m) / dom_s
        icb = compute_ic(zb, tgt[valid])
        icd = compute_ic(zd, tgt[valid])
        if not np.isnan(icb):
            fold_bear.append(icb)
        if not np.isnan(icd):
            fold_dom.append(icd)

    oos_bear = np.mean(fold_bear) if fold_bear else np.nan
    oos_dom = np.mean(fold_dom) if fold_dom else np.nan
    decomp[label] = {"ic_bear_is": ic_bear_is, "ic_dom_is": ic_dom_is,
                     "oos_bear": oos_bear, "oos_dom": oos_dom}
    print(f"\n  {label}:")
    print(f"    IC IS  z_bear (d1_bear_5): {ic_bear_is:+.4f}")
    print(f"    IC IS  z_dom  (domino):    {ic_dom_is:+.4f}")
    print(f"    OOS     z_bear (d1_bear_5): {oos_bear:+.4f}")
    print(f"    OOS     z_dom  (domino):    {oos_dom:+.4f}")


# ═══════════════════════════════════════════════════════════════════════════
# 3. WALK-FORWARD OOS — 26 folds expanding window con pesos óptimos
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 74)
print("3. WALK-FORWARD OOS — 26 folds expanding window (μ/σ refit por fold)")
print("═" * 74)


def walkforward(obs_df, target_col, dom_col, w_bear):
    """Expanding-window walk-forward. score = w*z_bear + (1-w)*z_dom,
    con z-scores re-normalizados sobre training data de cada fold (OOS estricto)."""
    n = len(obs_df)
    fold_size = max(n // N_FOLDS, 1)
    fold_ics = []
    fold_details = []

    for i in range(1, N_FOLDS):
        split_idx = i * fold_size
        if split_idx >= n - fold_size:
            break
        train = obs_df.iloc[:split_idx]
        test = obs_df.iloc[split_idx:split_idx + fold_size]
        if len(train) < 30 or len(test) < 10:
            continue

        d1_tr = train["d1_bear_5"].dropna()
        dom_tr = train[dom_col].dropna()
        if len(d1_tr) < 10 or len(dom_tr) < 10:
            continue
        d1_m, d1_s = d1_tr.mean(), d1_tr.std()
        dom_m, dom_s = dom_tr.mean(), dom_tr.std()
        if d1_s == 0 or dom_s == 0:
            continue

        td1 = test["d1_bear_5"].values.astype(float)
        tdom = test[dom_col].values.astype(float)
        valid = ~np.isnan(td1) & ~np.isnan(tdom)
        if valid.sum() < 10:
            continue

        z_b = (td1[valid] - d1_m) / d1_s
        z_d = (tdom[valid] - dom_m) / dom_s
        scores = w_bear * z_b + (1 - w_bear) * z_d
        targets = test[target_col].values[valid].astype(float)

        ic_val = compute_ic(scores, targets)
        if not np.isnan(ic_val):
            fold_ics.append(ic_val)
            fold_details.append({
                "fold": i, "train_n": len(train), "test_n": valid.sum(),
                "ic": ic_val,
                "test_start": test["pivot_date"].iloc[0],
                "test_end": test["pivot_date"].iloc[-1],
            })

    return fold_ics, fold_details


def report_oos(label, fold_ics, fold_details, rng_seed):
    ics = np.array([v for v in fold_ics if not np.isnan(v)])
    if len(ics) == 0:
        print(f"  {label}: ⚠ sin folds válidos")
        return None
    mean = np.mean(ics)
    med = np.median(ics)
    pos = np.mean(ics > 0)
    rng = np.random.default_rng(rng_seed)
    bs = [np.mean(rng.choice(ics, size=len(ics), replace=True)) for _ in range(2000)]
    ci = np.percentile(bs, [2.5, 97.5])
    print(f"\n  ── {label} ──")
    print(f"  w óptimo:        {grid_results[label]['best_w']:.2f}")
    print(f"  OOS IC mean:     {mean:+.4f}")
    print(f"  OOS IC median:   {med:+.4f}")
    print(f"  Folds > 0:       {np.sum(ics > 0)}/{len(ics)} ({pos*100:.0f}%)")
    print(f"  IC min/max:      {np.min(ics):+.4f} / {np.max(ics):+.4f}")
    print(f"  Bootstrap CI95:  [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    return {"mean": mean, "median": med, "folds_pos": pos, "n_folds": len(ics), "ci95": ci}


results = {}
seeds = {"cascade_50": 42, "cascade_75": 43, "cascade_50to75": 44}
for label, obs_df, dom_col, target_col in TARGETS:
    w_opt = grid_results[label]["best_w"]
    fold_ics, fold_details = walkforward(obs_df, target_col, dom_col, w_opt)
    results[label] = report_oos(label, fold_ics, fold_details, seeds[label])


# ═══════════════════════════════════════════════════════════════════════════
# 4. COMPARACIÓN vs VIEJO (+0.348)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 74)
print("4. RESUMEN — RECALIBRACIÓN vs VIEJO")
print("═" * 74)

print(f"\n  {'Target':<14s} {'w viejo':>8s} {'w nuevo':>8s} {'OOS viejo':>10s} {'OOS nuevo':>10s} {'Δ':>8s}")
print(f"  {'─'*14} {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*8}")

old_w = {"cascade_50": 0.66, "cascade_75": 0.50, "cascade_50to75": 0.15}
old_oos = {"cascade_50": 0.348, "cascade_75": 0.2596, "cascade_50to75": 0.3388}

for label in ["cascade_50", "cascade_75", "cascade_50to75"]:
    w_new = grid_results[label]["best_w"]
    oos_new = results[label]["mean"] if results[label] else np.nan
    oos_old = old_oos[label]
    delta = oos_new - oos_old if not np.isnan(oos_new) else np.nan
    print(f"  {label:<14s} {old_w[label]:>8.2f} {w_new:>8.2f} "
          f"{oos_old:>+10.4f} {oos_new:>+10.4f} {delta:>+8.4f}")

# Análisis cascade_50 específico
print("\n  ANÁLISIS cascade_50 (el objetivo central):")
if results["cascade_50"]:
    m = results["cascade_50"]
    delta = m["mean"] - VIEJO_OOS_C50
    pct = (delta / abs(VIEJO_OOS_C50)) * 100
    print(f"    OOS nuevo (recalibrado):  {m['mean']:+.4f}")
    print(f"    OOS viejo:                {VIEJO_OOS_C50:+.4f}")
    print(f"    Δ:                        {delta:+.4f} ({pct:+.1f}%)")
    print(f"    ¿Volvemos cerca de +0.35? {'✅ SÍ' if m['mean'] >= 0.30 else '⚠ PARCIAL' if m['mean'] >= 0.25 else '❌ NO'}")

# Guardar resultados
out = {
    "grid_search": {k: {"best_w": v["best_w"], "best_ic_is": v["best_ic"],
                        "grid": [(w, ic) for w, ic in v["grid"]]}
                    for k, v in grid_results.items()},
    "walkforward_oos": {k: ({"mean": v["mean"], "median": v["median"],
                             "folds_pos": v["folds_pos"], "n_folds": v["n_folds"],
                             "ci95": [float(x) for x in v["ci95"]]} if v else None)
                        for k, v in results.items()},
    "old_oos": old_oos,
    "old_w": old_w,
}
out_path = Path(__file__).parent / "recalibrar_cascade_trailing_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)

print(f"\n💾 Resultados guardados en {out_path}")
print("\n✅ Recalibración completa.")
