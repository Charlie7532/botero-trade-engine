#!/usr/bin/env python3
"""
ESTUDIO WINS vs LOSSES v2 — SV5T, VIX, BSI, CREDIT
====================================================
M E T O D O L O G Í A   C O R R E G I D A:
  - Entrada: BARRA de señal (no pivote zigzag)
  - Salida: forward returns a 5/10/20/40d (trading days)
  - 8 dimensiones con CI95 bootstrap 2000
  - Separar por calidad de muestra (N≥30, N 10-30, N<10)

Estaciones: SV5T (CRISIS_TURBULENCE), VIX (CRISIS_SPIKE),
            BSI (BREADTH_WASHED_OUT), CREDIT (CREDIT_STRESS)

Tick: CREDIT usa ratio HYG/LQD.

D2 = diff(3d), D3 = std(2d)/std(10d) — pitfall #46 correct formula.
"""

import sys, json
from pathlib import Path
from collections import defaultdict, Counter
from itertools import groupby

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import SV5TurbulenceLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter

# ─── Config ─────────────────────────────────────────────────────────────────
MIN_SIGNAL_SPACING = 10  # trading days between signals
FW_HORIZONS = [5, 10, 20, 40]  # trading days
N_BOOT = 2000
BOOT_SEED = 42

STATIONS_CFG = [
    {
        "name": "SV5T",
        "ticker": "SV5_TURBULENCE",
        "adapter_cls": SV5TurbulenceLookupAdapter,
        "method": "lookup_sv5_turbulence_guidance",
        "extreme_d1": ["CRISIS_TURBULENCE"],
        "color": "bold_yellow",
    },
    {
        "name": "VIX",
        "ticker": "VIX",
        "adapter_cls": VIXLookupAdapter,
        "method": "lookup_vix_guidance",
        "extreme_d1": ["CRISIS_SPIKE"],
        "color": "bold_red",
    },
    {
        "name": "BSI",
        "ticker": "S5TW",
        "adapter_cls": BSILookupAdapter,
        "method": "lookup_bsi_guidance",
        "extreme_d1": ["BREADTH_WASHED_OUT"],
        "color": "bold_blue",
    },
    {
        "name": "CREDIT",
        "ticker": "HYG+LQD",  # compound ticker, special handling
        "adapter_cls": CreditLookupAdapter,
        "method": "lookup_credit_guidance",
        "extreme_d1": ["CREDIT_STRESS"],
        "color": "bold_magenta",
    },
]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI95 for mean."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi))


def boot_ci_proportion(wins_bool, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI95 for a proportion (win rate)."""
    arr = np.asarray(wins_bool, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    props = np.empty(n_boot)
    for i in range(n_boot):
        props[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi))


def compute_d2_d3(series):
    """D2 = diff(3d), D3 = std(2d)/std(10d). Pitfall #46."""
    d2 = series.diff(3)
    s2 = series.rolling(2).std()
    s10 = series.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3


# ─── Load Data ───────────────────────────────────────────────────────────────

print("═══ CARGANDO DATOS ═══")

store = TimescaleDataStore()

# SPY
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_dates = list(spy.index)
spy_values = spy.values
print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")

# Build date → index mapping for fast forward lookups
spy_date_to_idx = {d: i for i, d in enumerate(spy_dates)}

# Zigzag legs for timing analysis (dimension F)
repo = ZigzagLegRepository(store)
legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)

# Build pivot lookup: date -> type, price
all_pivots = []
for l in legs25:
    d = pd.to_datetime(l.start_timestamp).normalize()
    all_pivots.append((d, l.start_type, l.start_price))
all_pivots.sort(key=lambda x: x[0])

# For each date, what's the nearest MIN pivot forward and MAX pivot forward
pivot_dates_sorted = sorted(set(d for d, _, _ in all_pivots))

# Precompute nearest pivot distances
def nearest_pivot_after(date, pivot_type):
    """Days from date to nearest pivot_type pivot on or after date."""
    for pd_d, pt, pr in all_pivots:
        if pd_d >= date and pt == pivot_type:
            return (pd_d - date).days, pr, pd_d
    return None, None, None


# ─── Per-station analysis ────────────────────────────────────────────────────

all_results = {}

for cfg in STATIONS_CFG:
    name = cfg["name"]
    ticker = cfg["ticker"]
    extreme_d1_list = cfg["extreme_d1"]
    adapter = cfg["adapter_cls"]()
    method_name = cfg["method"]
    lookup_fn = getattr(adapter, method_name)

    print(f"\n{'═'*80}")
    print(f"  {name} — D1 extremo: {extreme_d1_list}  |  Ticker: {ticker}")
    print(f"{'═'*80}")

    # ── Load station data ──
    if ticker == "HYG+LQD":
        # Credit: HYG/LQD ratio
        hyg_raw = store.load_bars("HYG", "1d")["close"].copy()
        lqd_raw = store.load_bars("LQD", "1d")["close"].copy()
        hyg_raw.index = pd.to_datetime(hyg_raw.index).normalize()
        lqd_raw.index = pd.to_datetime(lqd_raw.index).normalize()
        hyg = hyg_raw[~hyg_raw.index.duplicated(keep="last")].sort_index()
        lqd = lqd_raw[~lqd_raw.index.duplicated(keep="last")].sort_index()
        # Find common dates
        common = sorted(set(hyg.index) & set(lqd.index) & set(spy.index))
        ratio = pd.Series(
            [float(hyg.loc[d]) / float(lqd.loc[d]) for d in common],
            index=common
        )
        print(f"  HYG/LQD ratio: {ratio.index[0].date()} → {ratio.index[-1].date()} ({len(ratio)} bars)")
        d2, d3 = compute_d2_d3(ratio)
        raw_values = ratio
    else:
        raw = store.load_bars(ticker, "1d")["close"].copy()
        raw.index = pd.to_datetime(raw.index).normalize()
        s = raw[~raw.index.duplicated(keep="last")].sort_index()
        common = sorted(set(s.index) & set(spy.index))
        raw_values = pd.Series([float(s.loc[d]) for d in common], index=common)
        d2, d3 = compute_d2_d3(raw_values)
        print(f"  {ticker}: {raw_values.index[0].date()} → {raw_values.index[-1].date()} ({len(raw_values)} bars aligned)")

    # ── Classify every bar ──
    signal_rows = []  # list of {date, idx_in_spy, val, vel, vol, state_key, d1, d2_bin, d3_bin, n}

    for ci, dt in enumerate(common):
        if dt not in d2.index or dt not in d3.index:
            continue
        val = float(raw_values[dt])
        vel = float(d2[dt]) if not pd.isna(d2[dt]) else 0.0
        vol = float(d3[dt]) if not pd.isna(d3[dt]) else 1.0
        try:
            g = lookup_fn(val=val, d3_speed=vel, vol_norm=vol, vol_d3=0.0)
        except Exception:
            continue
        if g is None:
            continue
        d1_bin = g.state_key.split("__")[0]
        if d1_bin not in extreme_d1_list:
            continue
        d2_bin = g.state_key.split("__")[1] if "__" in g.state_key else "?"
        d3_bin = g.state_key.split("__")[2] if g.state_key.count("__") >= 2 else "?"
        n_state = getattr(g, 'n', 0)

        # Find this date's index in SPY
        spy_idx = spy_date_to_idx.get(dt)
        if spy_idx is None:
            continue

        signal_rows.append({
            "date": dt,
            "spy_idx": spy_idx,
            "val": val,
            "vel": vel,
            "vol": vol,
            "state_key": g.state_key,
            "d1": d1_bin,
            "d2": d2_bin,
            "d3": d3_bin,
            "n_state": n_state,
        })

    print(f"  Barras de señal (D1 extremo): {len(signal_rows)}")

    if len(signal_rows) == 0:
        all_results[name] = None
        continue

    # ── Dedup: min 10 trading days between signals ──
    signal_rows.sort(key=lambda x: x["date"])
    deduped = []
    last_idx = -MIN_SIGNAL_SPACING - 1
    for sr in signal_rows:
        if sr["spy_idx"] - last_idx >= MIN_SIGNAL_SPACING:
            deduped.append(sr)
            last_idx = sr["spy_idx"]

    print(f"  Señales dedup (≥{MIN_SIGNAL_SPACING}d): {len(deduped)}")

    # ── Compute forward returns ──
    # For each signal, compute SPY forward returns at each horizon
    signals = []
    for sr in deduped:
        entry_idx = sr["spy_idx"]
        entry_price = spy_values[entry_idx]
        fwd_returns = {}
        for h in FW_HORIZONS:
            fwd_idx = entry_idx + h
            if fwd_idx >= len(spy_values):
                fwd_returns[h] = None
            else:
                fwd_returns[h] = (spy_values[fwd_idx] / entry_price - 1.0)

        # Timing vs zigzag: distance to nearest MIN pivot
        min_days, min_price, min_date = nearest_pivot_after(sr["date"], "MIN")
        # Drawdown from signal to MIN pivot
        signal_spy_price = float(spy.loc[sr["date"]]) if sr["date"] in spy.index else entry_price
        if min_days is not None and min_days >= 0:
            # window from signal to pivot
            mask = (spy.index >= sr["date"]) & (spy.index <= min_date)
            spy_window = spy[mask]
            if len(spy_window) > 1:
                dd_to_pivot = (spy_window.min() / signal_spy_price - 1.0)
            else:
                dd_to_pivot = (min_price / signal_spy_price - 1.0)
            is_knife = dd_to_pivot < -0.05  # >5% DD = cuchillo cayendo
            pivot_distance = min_days
        else:
            dd_to_pivot = 0.0
            is_knife = False
            pivot_distance = None
            min_date = None

        signals.append({
            "date": sr["date"],
            "spy_idx": entry_idx,
            "entry_price": entry_price,
            "state_key": sr["state_key"],
            "d1": sr["d1"],
            "d2": sr["d2"],
            "d3": sr["d3"],
            "n_state": sr["n_state"],
            "val": sr["val"],
            "vel": sr["vel"],
            "vol": sr["vol"],
            "fwd": fwd_returns,
            "pivot_distance": pivot_distance,
            "pivot_date": min_date,
            "dd_to_pivot": dd_to_pivot,
            "is_knife": is_knife,
        })

    n_total = len(signals)
    print(f"  Señales con forward returns: {n_total}")

    # ── Separate by N quality ──
    n_ge30 = [s for s in signals if s["n_state"] >= 30]
    n_10_30 = [s for s in signals if 10 <= s["n_state"] < 30]
    n_lt10 = [s for s in signals if s["n_state"] < 10]

    print(f"    N≥30: {len(n_ge30)} | N 10-30: {len(n_10_30)} | N<10: {len(n_lt10)}")

    # ── Analysis function for a group of signals ──
    def analyze_signals(signal_list, label, n_quality_label=""):
        if len(signal_list) < 3:
            return {"label": label, "N": len(signal_list), "insufficient": True}

        n = len(signal_list)

        # Extract forward returns for each horizon
        fwd_arrays = {}
        for h in FW_HORIZONS:
            arr = np.array([s["fwd"][h] for s in signal_list if s["fwd"][h] is not None])
            fwd_arrays[h] = arr

        R = {"label": label, "N": n, "n_quality": n_quality_label}

        # ── Dimensión A: Win rate + CI95 for each horizon ──
        R["A_win_rate"] = {}
        R["A_wr_ci95"] = {}
        for h in FW_HORIZONS:
            arr = fwd_arrays[h]
            if len(arr) < 3:
                R["A_win_rate"][h] = np.nan
                R["A_wr_ci95"][h] = [np.nan, np.nan]
                continue
            wins_bool = arr > 0
            wr, wr_lo, wr_hi = boot_ci_proportion(wins_bool)
            R["A_win_rate"][h] = wr
            R["A_wr_ci95"][h] = [wr_lo, wr_hi]

        # ── Dimensión B: Wins distribution ──
        R["B_wins"] = {}
        for h in FW_HORIZONS:
            arr = fwd_arrays[h]
            win_arr = arr[arr > 0]
            if len(win_arr) < 2:
                R["B_wins"][h] = None
                continue
            R["B_wins"][h] = {
                "n": len(win_arr),
                "mean": float(np.mean(win_arr)),
                "median": float(np.median(win_arr)),
                "p25": float(np.percentile(win_arr, 25)) if len(win_arr) >= 4 else np.nan,
                "p75": float(np.percentile(win_arr, 75)) if len(win_arr) >= 4 else np.nan,
                "p90": float(np.percentile(win_arr, 90)) if len(win_arr) >= 10 else np.nan,
                "max": float(np.max(win_arr)),
            }

        # ── Dimensión C: Losses distribution + wipeouts ──
        R["C_losses"] = {}
        for h in FW_HORIZONS:
            arr = fwd_arrays[h]
            loss_arr = arr[arr <= 0]
            if len(loss_arr) < 2:
                R["C_losses"][h] = None
                continue
            wipeouts = loss_arr[loss_arr < -0.20]
            R["C_losses"][h] = {
                "n": len(loss_arr),
                "mean": float(np.mean(loss_arr)),
                "median": float(np.median(loss_arr)),
                "p25": float(np.percentile(loss_arr, 25)) if len(loss_arr) >= 4 else np.nan,
                "p75": float(np.percentile(loss_arr, 75)) if len(loss_arr) >= 4 else np.nan,
                "p90": float(np.percentile(loss_arr, 90)) if len(loss_arr) >= 10 else np.nan,
                "min": float(np.min(loss_arr)),  # worst loss
                "wipeouts_n": len(wipeouts),
                "wipeouts_pct": len(wipeouts) / len(arr) * 100,
                "wipeouts_vals": wipeouts.tolist(),
            }

        # ── Dimensión D: Profit factor, Kelly, EV ──
        R["D_metrics"] = {}
        for h in FW_HORIZONS:
            arr = fwd_arrays[h]
            if len(arr) < 3:
                R["D_metrics"][h] = None
                continue
            wins = arr[arr > 0]
            losses = arr[arr <= 0]
            gross_win = np.sum(wins) if len(wins) > 0 else 0
            gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0
            pf = float(gross_win / gross_loss) if gross_loss > 0 else float('inf')
            wr = np.mean(arr > 0) if len(arr) > 0 else np.nan
            avg_w = np.mean(wins) if len(wins) > 0 else 0
            avg_l = abs(np.mean(losses)) if len(losses) > 0 else 0
            wlr = avg_w / avg_l if avg_l > 0 else float('inf')
            kelly = wr - (1 - wr) / wlr if (avg_l > 0 and wlr > 0) else np.nan
            ev, ev_lo, ev_hi = boot_ci(arr)
            R["D_metrics"][h] = {
                "profit_factor": pf,
                "avg_win": float(avg_w),
                "avg_loss": float(avg_l),
                "win_loss_ratio": float(wlr) if wlr != float('inf') else "inf",
                "kelly": float(kelly) if not np.isnan(kelly) else None,
                "ev": ev,
                "ev_ci95": [ev_lo, ev_hi],
                "sharpe": float(ev / np.std(arr)) if np.std(arr) > 0 else 0.0,
            }

        # ── Dimensión E: Rachas (streaks of losses) ──
        # Use 20d forward as the canonical trade horizon
        arr20 = fwd_arrays[20]
        if len(arr20) >= 3:
            loss_streaks = []
            curr = 0
            for r in arr20:
                if r <= 0:
                    curr += 1
                else:
                    if curr > 0:
                        loss_streaks.append(curr)
                    curr = 0
            if curr > 0:
                loss_streaks.append(curr)
            ls = np.array(loss_streaks) if loss_streaks else np.array([0])
            R["E_streaks"] = {
                "n_streaks": len(loss_streaks),
                "max_streak": int(ls.max()),
                "mean_streak": float(ls.mean()),
                "streak_counts": {int(k): int(v) for k, v in Counter(ls).items()},
            }
        else:
            R["E_streaks"] = None

        # ── Dimensión F: Timing vs zigzag ──
        pivot_dists = np.array([s["pivot_distance"] for s in signal_list if s["pivot_distance"] is not None])
        dd_to_pivots = np.array([s["dd_to_pivot"] for s in signal_list])
        en_pivote = (pivot_dists == 0).sum()
        anticipada = (pivot_dists > 0).sum()
        retrasada = (pivot_dists < 0).sum()
        R["F_timing"] = {
            "n_with_pivot": len(pivot_dists),
            "anticipada": int(anticipada),
            "en_pivote": int(en_pivote),
            "retrasada": int(retrasada),
            "pivot_dist_mean": float(np.mean(pivot_dists)) if len(pivot_dists) > 0 else np.nan,
            "pivot_dist_median": float(np.median(pivot_dists)) if len(pivot_dists) > 0 else np.nan,
            "dd_to_pivot_mean": float(np.mean(dd_to_pivots)),
            "dd_to_pivot_p50": float(np.median(dd_to_pivots)),
            "entry_same_day_pct": float(np.mean(np.abs(dd_to_pivots) < 0.005) * 100),  # <0.5% = same day
        }

        # ── Dimensión G: Cuchillo cayendo ──
        knife = [s for s in signal_list if s["is_knife"]]
        n_knife = len(knife)
        R["G_knife"] = {
            "n": n_knife,
            "pct": n_knife / n * 100 if n > 0 else 0,
        }
        if n_knife > 0:
            R["G_knife"]["dates"] = [str(s["date"].date()) for s in knife]
            R["G_knife"]["dd_values"] = [float(s["dd_to_pivot"]) for s in knife]
            R["G_knife"]["d2_bins"] = [s["d2"] for s in knife]
            R["G_knife"]["d3_bins"] = [s["d3"] for s in knife]
            R["G_knife"]["state_keys"] = [s["state_key"] for s in knife]

        # ── Dimensión H: Calidad de muestra ──
        n_states = np.array([s["n_state"] for s in signal_list])
        R["H_quality"] = {
            "n_total": n,
            "n_ge_30": int(np.sum(n_states >= 30)),
            "n_10_30": int(np.sum((n_states >= 10) & (n_states < 30))),
            "n_lt_10": int(np.sum(n_states < 10)),
            "min_n_state": int(np.min(n_states)),
            "max_n_state": int(np.max(n_states)),
            "median_n_state": float(np.median(n_states)),
            "quality_tier": n_quality_label,
        }

        # ── Forward returns per signal (for debugging) ──
        R["signals_detail"] = [
            {
                "date": str(s["date"].date()),
                "state_key": s["state_key"],
                "d2": s["d2"],
                "d3": s["d3"],
                "n_state": s["n_state"],
                "pivot_dist": s["pivot_distance"],
                "dd_to_pivot": float(s["dd_to_pivot"]),
                "is_knife": s["is_knife"],
                "fwd_5d": float(s["fwd"][5]) if s["fwd"][5] is not None else None,
                "fwd_10d": float(s["fwd"][10]) if s["fwd"][10] is not None else None,
                "fwd_20d": float(s["fwd"][20]) if s["fwd"][20] is not None else None,
                "fwd_40d": float(s["fwd"][40]) if s["fwd"][40] is not None else None,
            }
            for s in signal_list
        ]

        return R

    # ── Analyze each group ──
    results_groups = []
    if len(n_ge30) >= 3:
        results_groups.append(analyze_signals(n_ge30, f"{name} CRISIS N≥30", "N_GE_30"))
    if len(n_10_30) >= 3:
        results_groups.append(analyze_signals(n_10_30, f"{name} CRISIS N10-30", "N_10_30"))
    if len(n_lt10) >= 3:
        results_groups.append(analyze_signals(n_lt10, f"{name} CRISIS N<10", "N_LT_10"))
    # Combined
    combined = analyze_signals(signals, f"{name} CRISIS TODOS", "ALL")
    results_groups.append(combined)

    all_results[name] = {
        "station": name,
        "extreme_d1": extreme_d1_list,
        "ticker": ticker,
        "n_signals_total": n_total,
        "n_signals_deduped": len(deduped),
        "groups": results_groups,
        "all_signals_detail": [
            {
                "date": str(s["date"].date()),
                "state_key": s["state_key"],
                "d2": s["d2"],
                "d3": s["d3"],
                "n_state": s["n_state"],
                "pivot_dist": s["pivot_distance"],
                "dd_to_pivot": float(s["dd_to_pivot"]),
                "is_knife": s["is_knife"],
                "d1": s["d1"],
                "fwd_5d": float(s["fwd"][5]) if s["fwd"][5] is not None else None,
                "fwd_10d": float(s["fwd"][10]) if s["fwd"][10] is not None else None,
                "fwd_20d": float(s["fwd"][20]) if s["fwd"][20] is not None else None,
                "fwd_40d": float(s["fwd"][40]) if s["fwd"][40] is not None else None,
            }
            for s in signals
        ],
    }

store.close()

# ═══════════════════════════════════════════════════════════════════════════════
# REPORTE
# ═══════════════════════════════════════════════════════════════════════════════

print("\n\n")
print("╔" + "═" * 98 + "╗")
print("║" + "  ESTUDIO WINS vs LOSSES v2 — SV5T · VIX · BSI · CREDIT".center(98) + "║")
print("╠" + "═" * 98 + "╣")
print("║" + "  METODOLOGÍA CORREGIDA: Entrada en BARRA de señal (NO pivote).".center(98) + "║")
print("║" + "  Forward: 5/10/20/40d trading. CI95 bootstrap 2000. D3=std(2)/std(10).".center(98) + "║")
print("║" + "  Dedup: ≥10 trading days entre señales. 8 dimensiones.".center(98) + "║")
print("╚" + "═" * 98 + "╝")

for name, station_r in all_results.items():
    if station_r is None:
        print(f"\n{'─'*100}\n  {name}: SIN DATOS\n{'─'*100}")
        continue

    print(f"\n{'═'*100}")
    print(f"  {name} → D1: {station_r['extreme_d1']}  |  {station_r['n_signals_deduped']} señales")
    print(f"{'═'*100}")

    for grp in station_r["groups"]:
        label = grp["label"]
        n_grp = grp["N"]
        q_label = grp.get("n_quality", "")

        if grp.get("insufficient"):
            print(f"\n  ── {label}: N={n_grp} INSUFICIENTE (<3) ──")
            continue

        print(f"\n  ┌─ {'─'*90}")
        print(f"  │ {label}  (N={n_grp})")
        print(f"  ├─ {'─'*90}")

        # Quality header
        hq = grp.get("H_quality", {})
        print(f"  │ H. CALIDAD: N≥30={hq.get('n_ge_30',0)}, 10-30={hq.get('n_10_30',0)}, <10={hq.get('n_lt_10',0)}  "
              f"min={hq.get('min_n_state',0)}, med={hq.get('median_n_state',0):.0f}, max={hq.get('max_n_state',0)}")

        # --- TABLE: Forward returns at each horizon ---
        print(f"  │")
        print(f"  │ {'Horizon':>6} │ {'WR':>7} {'CI95':>22} │ {'Win Med':>8} {'Win P90':>8} │ {'Loss Med':>8} {'Loss Min':>8} │ {'PF':>6} {'Kelly':>7} {'EV':>8} │")
        print(f"  │ {'─'*6}─┼─{'─'*7}─{'─'*22}─┼─{'─'*8}─{'─'*8}─┼─{'─'*8}─{'─'*8}─┼─{'─'*6}─{'─'*7}─{'─'*8}─┤")

        for h in FW_HORIZONS:
            wr = grp["A_win_rate"].get(h, np.nan)
            wr_ci = grp["A_wr_ci95"].get(h, [np.nan, np.nan])
            b_w = grp.get("B_wins", {}).get(h, {}) or {}
            c_l = grp.get("C_losses", {}).get(h, {}) or {}
            d_m = grp.get("D_metrics", {}).get(h, {}) or {}

            wr_str = f"{wr*100:.0f}%" if not np.isnan(wr) else "N/A"
            ci_str = f"[{wr_ci[0]*100:.0f}%,{wr_ci[1]*100:.0f}%]" if not np.isnan(wr) else "N/A"
            w_med = f"{b_w.get('median',0)*100:+.1f}%" if b_w else "N/A"
            w_p90 = f"{b_w.get('p90',0)*100:+.1f}%" if b_w and not np.isnan(b_w.get('p90', np.nan)) else "N/A"
            l_med = f"{c_l.get('median',0)*100:+.1f}%" if c_l else "N/A"
            l_min = f"{c_l.get('min',0)*100:+.1f}%" if c_l else "N/A"
            pf = f"{d_m.get('profit_factor',0):.1f}" if d_m else "N/A"
            kl = f"{d_m.get('kelly',0)*100:.0f}%" if d_m and d_m.get('kelly') else "N/A"
            ev = f"{d_m.get('ev',0)*100:+.1f}%" if d_m else "N/A"

            print(f"  │ {f'{h}d':>6} │ {wr_str:>7} {ci_str:>22} │ {w_med:>8} {w_p90:>8} │ {l_med:>8} {l_min:>8} │ {pf:>6} {kl:>7} {ev:>8} │")

        # --- Wipeouts ---
        print(f"  │")
        for h in FW_HORIZONS:
            c_l = grp.get("C_losses", {}).get(h, {}) or {}
            if c_l:
                wo_n = c_l.get("wipeouts_n", 0)
                wo_pct = c_l.get("wipeouts_pct", 0)
                if wo_n > 0:
                    wo_vals = c_l.get("wipeouts_vals", [])
                    print(f"  │ {f'{h}d WIPEOUTS >20%:':>8} {wo_n} ({wo_pct:.0f}%) → {[f'{v*100:.1f}%' for v in wo_vals[:5]]}")

        # --- Streaks ---
        e_s = grp.get("E_streaks")
        if e_s:
            print(f"  │")
            print(f"  │ E. RACHAS (target 20d): {e_s['n_streaks']} rachas, max={e_s['max_streak']}, "
                  f"avg={e_s['mean_streak']:.1f}")

        # --- Timing ---
        ft = grp.get("F_timing", {})
        print(f"  │")
        print(f"  │ F. TIMING vs ZIGZAG: anticipada={ft.get('anticipada',0)} en_pivote={ft.get('en_pivote',0)} "
              f"retrasada={ft.get('retrasada',0)}")
        print(f"  │    Distancia a pivote: mediana={ft.get('pivot_dist_median',0):.0f}d")
        print(f"  │    DD hasta pivote: mean={ft.get('dd_to_pivot_mean',0)*100:+.2f}%  "
              f"P50={ft.get('dd_to_pivot_p50',0)*100:+.2f}%")
        print(f"  │    Mismo día (±0.5%): {ft.get('entry_same_day_pct',0):.0f}%")

        # --- Cuchillo ---
        gk = grp.get("G_knife", {})
        print(f"  │")
        print(f"  │ G. CUCHILLO CAYENDO (DD>5% señal→pivote): {gk.get('n',0)}/{n_grp} ({gk.get('pct',0):.0f}%)")
        if gk.get("n", 0) > 0:
            zipped = list(zip(
                gk.get("dates", []), gk.get("dd_values", []),
                gk.get("d2_bins", []), gk.get("d3_bins", [])
            ))
            for i, (dt, dd_v, d2b, d3b) in enumerate(zipped[:5]):
                print(f"  │    {dt}: DD={dd_v*100:.1f}%  D2={d2b}  D3={d3b}")

        print(f"  └─ {'─'*90}")

        # --- Signal detail (first 8) ---
        detail = grp.get("signals_detail", [])
        if detail:
            print(f"  │")
            print(f"  │ DETALLE DE SEÑALES (primeras 8):")
            print(f"  │ {'Date':>12} {'State Key':<50} {'N':>4} {'5d':>8} {'10d':>8} {'20d':>8} {'40d':>8} {'Knife':>6}")
            print(f"  │ {'─'*12} {'─'*50} {'─'*4} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*6}")
            for sd in detail[:8]:
                f5 = f"{sd['fwd_5d']*100:+.1f}%" if sd['fwd_5d'] is not None else "N/A"
                f10 = f"{sd['fwd_10d']*100:+.1f}%" if sd['fwd_10d'] is not None else "N/A"
                f20 = f"{sd['fwd_20d']*100:+.1f}%" if sd['fwd_20d'] is not None else "N/A"
                f40 = f"{sd['fwd_40d']*100:+.1f}%" if sd['fwd_40d'] is not None else "N/A"
                kn = "◀ KNIFE" if sd['is_knife'] else ""
                print(f"  │ {sd['date']:>12} {sd['state_key']:<50} {sd['n_state']:>4} {f5:>8} {f10:>8} {f20:>8} {f40:>8} {kn:>6}")

# ═══════════════════════════════════════════════════════════════════════════════
# TABLA RESUMEN — TODAS LAS ESTACIONES (grupo ALL)
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═'*100}")
print(f"  TABLA RESUMEN — ENTRADA EN BARRA DE SEÑAL (NO PIVOTE)")
print(f"{'═'*100}")

for h in FW_HORIZONS:
    header = f"  ── Forward {h}d ──"
    print(f"\n{header}")
    print(f"  {'Station':<10} {'N':>5} {'N≥30':>5} {'WR':>7} {'CI95':>22} {'Win P50':>8} {'Loss P50':>8} {'PF':>6} {'Kelly':>7} {'EV':>8} {'Knife%':>7}")
    print(f"  {'─'*10} {'─'*5} {'─'*5} {'─'*7} {'─'*22} {'─'*8} {'─'*8} {'─'*6} {'─'*7} {'─'*8} {'─'*7}")

    for name, station_r in all_results.items():
        if station_r is None:
            continue
        for grp in station_r["groups"]:
            if grp.get("insufficient") or grp.get("n_quality", "") != "ALL":
                continue
            n = grp["N"]
            hq = grp.get("H_quality", {})
            n_ge = hq.get("n_ge_30", 0)

            wr = grp["A_win_rate"].get(h, np.nan)
            wr_ci = grp["A_wr_ci95"].get(h, [np.nan, np.nan])
            b_w = grp.get("B_wins", {}).get(h, {}) or {}
            c_l = grp.get("C_losses", {}).get(h, {}) or {}
            d_m = grp.get("D_metrics", {}).get(h, {}) or {}

            wr_s = f"{wr*100:.0f}%" if not np.isnan(wr) else "N/A"
            ci_s = f"[{wr_ci[0]*100:.0f}%,{wr_ci[1]*100:.0f}%]" if not np.isnan(wr) else "N/A"
            w50 = f"{b_w.get('median',0)*100:+.1f}%" if b_w else "N/A"
            l50 = f"{c_l.get('median',0)*100:+.1f}%" if c_l else "N/A"
            pf = f"{d_m.get('profit_factor',0):.1f}" if d_m else "N/A"
            kl = f"{d_m.get('kelly',0)*100:.0f}%" if d_m and d_m.get('kelly') else "N/A"
            ev = f"{d_m.get('ev',0)*100:+.1f}%" if d_m else "N/A"
            kn = f"{grp['G_knife']['pct']:.0f}%"

            print(f"  {name:<10} {n:>5} {n_ge:>5} {wr_s:>7} {ci_s:>22} {w50:>8} {l50:>8} {pf:>6} {kl:>7} {ev:>8} {kn:>7}")

# ─── Save results ────────────────────────────────────────────────────────────

def ser(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray):
        return [ser(x) for x in obj]
    if isinstance(obj, list):
        return [ser(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): ser(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [ser(x) for x in obj]
    return obj

out_path = ROOT / "data/research/misc/wins_losses_entry47_v2_report.json"
with open(out_path, "w") as f:
    json.dump(ser(all_results), f, indent=2, default=str)

print(f"\n\nReporte completo guardado en: {out_path}")
print("DONE — ESTUDIO WINS vs LOSSES v2 COMPLETO.")