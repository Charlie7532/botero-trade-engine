#!/usr/bin/env python3
"""
ESTUDIO WINS vs LOSSES v2 — FG, VVIX, SKEW (METODOLOGÍA CORREGIDA)
====================================================================
ENTRADA: barra de la señal D1 extrema. NO zigzag pivots.
SALIDA: forward 5/10/20/40d desde la barra de entrada.
Evitar clustering: min 10 días entre señales del mismo tipo.

8 DIMENSIONES:
A. Win rate + CI95 bootstrap (2000 iter) — retorno > 0 a 20d
B. Distribución WINS: P25/P50/P75/P90/max magnitud + duración
C. Distribución LOSSES: magnitud, max intra-trade drawdown, wipeouts (>20%)
D. Profit factor, Kelly, EV
E. Rachas de pérdidas (¿agrupadas como 2008?)
F. Timing vs zigzag: días al pivote más cercano, costo de anticipación/retraso
G. Cuchillo cayendo: drawdown >5% desde entrada al pivote, ¿D2/D3 lo advirtió?
H. CALIDAD DE MUESTRA: separar N≥30, 10≤N<30, N<10 — NUNCA mezclar

Estaciones: FG (EXTREME_FEAR), VVIX (EXTREME_VVIX), SKEW (LOW_TAIL_RISK)
Tickers: FG, VVIX, SKEW. Usar venv del proyecto, PYTHONPATH=/root/botero-trade
"""

import sys, os
from pathlib import Path
from datetime import timedelta
from collections import defaultdict, Counter
from itertools import groupby

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.vvix_lookup import VVIXLookupAdapter
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

# ── Bootstrap helpers ───────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for mean."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(sample.mean())
    means = np.sort(means)
    lo = (100 - ci) / 2
    hi = 100 - lo
    return arr.mean(), np.percentile(means, lo), np.percentile(means, hi)


def boot_ci_median(arr, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for median."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    meds = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        meds.append(np.median(sample))
    meds = np.sort(meds)
    lo = (100 - ci) / 2
    hi = 100 - lo
    return np.median(arr), np.percentile(meds, lo), np.percentile(meds, hi)


def boot_ci_winrate(arr, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for win rate (proportion > 0)."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    props = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        props.append((sample > 0).mean())
    props = np.sort(props)
    lo = (100 - ci) / 2
    hi = 100 - lo
    return (arr > 0).mean(), np.percentile(props, lo), np.percentile(props, hi)


def compute_d2_d3(s):
    """D2 = diff(3d), D3 = std(2d)/std(10d) — pitfall #46 formula."""
    d2 = s.diff(3)
    s2 = s.rolling(2).std()
    s10 = s.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

print("═══ CARGANDO DATOS ═══")
store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# SPY daily prices
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_dates = list(spy.index)
spy_price_map = dict(zip(spy_dates, spy.values))

print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")

# Zigzag legs zz25 — used ONLY for timing analysis (dimension F/G), not entry/exit
legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)
print(f"  zz25 pivots: {len(legs25)}")

# Build pivot arrays for quick lookup
pivot_items = []  # [(date, type, price)]
for leg in legs25:
    d = pd.to_datetime(leg.start_timestamp).normalize()
    pivot_items.append((d, leg.start_type, leg.start_price))
pivot_items.sort(key=lambda x: x[0])
pivot_dates_sorted = [p[0] for p in pivot_items]


def find_nearest_pivot(signal_date):
    """Find nearest zz25 pivot (MIN or MAX) to signal_date.
    Returns (days_diff, pivot_date, pivot_type, pivot_price).
    Positive days_diff = pivot AFTER signal (anticipada).
    Negative days_diff = pivot BEFORE signal (retrasada).
    Zero = same day."""
    best = None
    best_dist = float('inf')
    for pd_d, ptype, pprice in pivot_items:
        dist = (pd_d - signal_date).days
        if abs(dist) < abs(best_dist) if best_dist != float('inf') else True:
            best = (dist, pd_d, ptype, pprice)
            best_dist = abs(dist)
        elif abs(dist) == abs(best_dist) and dist > best[0]:
            best = (dist, pd_d, ptype, pprice)
    return best


def find_next_min_pivot(signal_date):
    """Find next MIN pivot strictly after signal_date.
    Returns (days_diff, pivot_date, price)."""
    for pd_d, ptype, pprice in pivot_items:
        if pd_d > signal_date and ptype == "MIN":
            return (pd_d - signal_date).days, pd_d, pprice
    return None, None, None


# ── Station configs ──────────────────────────────────────────────────────────

STATIONS = [
    {
        "name": "FG",
        "ticker": "FG",
        "adapter": FGLookupAdapter(),
        "extreme_d1": ["EXTREME_FEAR"],
        "method": "lookup_fg_guidance",
    },
    {
        "name": "VVIX",
        "ticker": "VVIX",
        "adapter": VVIXLookupAdapter(),
        "extreme_d1": ["EXTREME_VVIX"],
        "method": "lookup_vvix_guidance",
    },
    {
        "name": "SKEW",
        "ticker": "SKEW",
        "adapter": SkewLookupAdapter(),
        "extreme_d1": ["LOW_TAIL_RISK"],
        "method": "lookup_skew_guidance",
    },
]

CLUSTER_WINDOW = 10  # min calendar days between same-type signals
FORWARD_HORIZONS = [5, 10, 20, 40]

all_results = {}

# ═══════════════════════════════════════════════════════════════════════════════
# PER-STATION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

for station in STATIONS:
    name = station["name"]
    ticker = station["ticker"]
    adapter = station["adapter"]
    extreme_d1 = station["extreme_d1"]
    lookup_fn = getattr(adapter, station["method"])

    print(f"\n{'═'*80}")
    print(f"  {name} — D1 extremo: {extreme_d1}")
    print(f"{'═'*80}")

    # Load station data, align with SPY
    raw = store.load_bars(ticker, "1d")["close"].copy()
    raw.index = pd.to_datetime(raw.index).normalize()
    s = raw[~raw.index.duplicated(keep="last")].sort_index()
    common_dates = sorted(set(s.index) & set(spy.index))
    s = s.loc[common_dates]
    spy_aligned = spy.loc[common_dates]

    print(f"  {ticker}: {s.index[0].date()} → {s.index[-1].date()} ({len(s)} bars aligned)")

    # Compute D2, D3 for station
    d2, d3 = compute_d2_d3(s)

    # Find all bars in extreme D1
    extreme_bars = []
    for i, dt in enumerate(common_dates):
        if dt not in d2.index or dt not in d3.index:
            continue
        val = float(s[dt])
        vel = float(d2[dt]) if not pd.isna(d2[dt]) else 0.0
        vol = float(d3[dt]) if not pd.isna(d3[dt]) else 1.0
        try:
            g = lookup_fn(val=val, d3_speed=vel, vol_norm=vol, vol_d3=0.0)
        except Exception:
            continue
        if g is None:
            continue
        d1_bin = g.state_key.split("__")[0]
        if d1_bin in extreme_d1:
            d2_bin = g.state_key.split("__")[1] if "__" in g.state_key else "?"
            d3_bin = g.state_key.split("__")[2] if g.state_key.count("__") >= 2 else "?"
            # Store raw D2 and D3 values for falling-knife analysis
            extreme_bars.append({
                "idx": i,
                "date": dt,
                "val": val,
                "vel": vel,
                "vol": vol,
                "state_key": g.state_key,
                "d1": d1_bin,
                "d2_bin": d2_bin,
                "d3_bin": d3_bin,
            })

    print(f"  Barras en D1 extremo (raw): {len(extreme_bars)}")

    if len(extreme_bars) == 0:
        print(f"  ⚠️ Sin barras extremas para {name}. Saltando.")
        all_results[name] = None
        continue

    # ── De-cluster: keep only first signal in each cluster window ──
    # Sort by date, then keep only signals separated by >= CLUSTER_WINDOW days
    extreme_bars.sort(key=lambda x: x["date"])
    deduped_bars = []
    last_date = None
    for bar in extreme_bars:
        if last_date is None or (bar["date"] - last_date).days >= CLUSTER_WINDOW:
            deduped_bars.append(bar)
            last_date = bar["date"]

    print(f"  Barras después de de-clustering (≥{CLUSTER_WINDOW}d): {len(deduped_bars)}")

    # ── Build entries: signal bar date → forward returns at 5/10/20/40d ──
    entries = []
    for bar in deduped_bars:
        entry_date = bar["date"]
        entry_price = float(spy_aligned.loc[entry_date]) if entry_date in spy_aligned.index else None
        if entry_price is None:
            continue

        # Forward returns
        fwd_rets = {}
        fwd_end_dates = {}
        for h in FORWARD_HORIZONS:
            target_date = entry_date + timedelta(days=h)
            # Find nearest actual trading day >= target_date
            future_dates = [d for d in spy_dates if d >= target_date]
            if future_dates:
                exit_date = future_dates[0]
                exit_price = spy_price_map[exit_date]
                fwd_rets[h] = (exit_price / entry_price - 1) * 100
                fwd_end_dates[h] = exit_date
            else:
                fwd_rets[h] = np.nan
                fwd_end_dates[h] = None

        # Timing vs zigzag: nearest pivot
        pivot_info = find_nearest_pivot(entry_date)
        pivot_days, pivot_date, pivot_type, pivot_price = pivot_info

        # Find the next MIN pivot for falling-knife evaluation
        next_min_days, next_min_date, next_min_price = find_next_min_pivot(entry_date)

        # Falling knife: drawdown from entry to next MIN pivot
        dd_to_pivot = np.nan
        if next_min_date is not None and pivot_type == "MIN":
            # DD from entry price to next MIN pivot price
            dd_to_pivot = (next_min_price / entry_price - 1) * 100

        # Intra-trade worst drawdown (for each horizon)
        intra_dd = {}
        for h in FORWARD_HORIZONS:
            if h in fwd_end_dates and fwd_end_dates[h] is not None:
                end_dt = fwd_end_dates[h]
                window = spy_aligned.loc[entry_date:end_dt]
                if len(window) > 1:
                    lowest = window.min()
                    intra_dd[h] = (lowest / entry_price - 1) * 100  # negative = drawdown
                else:
                    intra_dd[h] = 0.0
            else:
                intra_dd[h] = np.nan

        entries.append({
            "signal_date": entry_date,
            "entry_price": entry_price,
            "state_key": bar["state_key"],
            "d1": bar["d1"],
            "d2_bin": bar["d2_bin"],
            "d3_bin": bar["d3_bin"],
            "vel": bar["vel"],
            "vol": bar["vol"],
            "fwd_5d": fwd_rets.get(5, np.nan),
            "fwd_10d": fwd_rets.get(10, np.nan),
            "fwd_20d": fwd_rets.get(20, np.nan),
            "fwd_40d": fwd_rets.get(40, np.nan),
            "pivot_days": pivot_days,
            "pivot_type": pivot_type,
            "pivot_price": pivot_price,
            "dd_to_pivot": dd_to_pivot,
            "intra_dd_5d": intra_dd.get(5, np.nan),
            "intra_dd_10d": intra_dd.get(10, np.nan),
            "intra_dd_20d": intra_dd.get(20, np.nan),
            "intra_dd_40d": intra_dd.get(40, np.nan),
        })

    df = pd.DataFrame(entries)
    n_total = len(df)
    print(f"  Entradas válidas: {n_total}")

    if n_total == 0:
        print(f"  ⚠️ Sin entradas para {name}.")
        all_results[name] = None
        continue

    # ════════════════════════════════════════════════════════════════════════
    # ANALYZE EACH HORIZON
    # ════════════════════════════════════════════════════════════════════════

    horizon_results = {}

    for h in FORWARD_HORIZONS:
        col = f"fwd_{h}d"
        returns = df[col].dropna().values
        if len(returns) == 0:
            horizon_results[h] = {"n": 0, "error": "no returns"}
            continue

        n = len(returns)
        wins_mask = returns > 0
        losses_mask = returns <= 0
        wins_ret = returns[wins_mask]
        losses_ret = returns[losses_mask]
        n_wins = wins_mask.sum()
        n_losses = losses_mask.sum()

        # ═══ A. WIN RATE + CI95 ═══
        win_rate, wr_lo, wr_hi = boot_ci_winrate(returns)

        # ═══ B. WINS DISTRIBUTION ═══
        b_ret = {}
        win_durations = df.loc[df[col].notna() & (df[col] > 0), col].values
        if len(wins_ret) > 0:
            for pct in [25, 50, 75, 90]:
                b_ret[f"P{pct}"] = np.percentile(wins_ret, pct)
            b_ret["max"] = wins_ret.max()
            _, b_lo, b_hi = boot_ci_median(wins_ret)
        else:
            b_ret = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan, "max": np.nan}
            b_lo, b_hi = np.nan, np.nan

        # ═══ C. LOSSES DISTRIBUTION ═══
        c_loss = {}
        dd_col = f"intra_dd_{h}d"
        loss_dd = df.loc[df[col].notna() & (df[col] <= 0), dd_col].dropna().values
        if len(losses_ret) > 0:
            for pct in [25, 50, 75, 90]:
                c_loss[f"P{pct}"] = np.percentile(losses_ret, pct)
            c_loss["min"] = losses_ret.min()
            c_loss["max_dd"] = loss_dd.min() if len(loss_dd) > 0 else np.nan
            c_loss["avg_intra_dd"] = loss_dd.mean() if len(loss_dd) > 0 else np.nan
            c_loss["wipeouts_gt20"] = int((losses_ret < -20).sum())
            c_loss["wipeouts_gt20_pct"] = (losses_ret < -20).mean() * 100
        else:
            c_loss = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan,
                      "min": np.nan, "max_dd": np.nan, "avg_intra_dd": np.nan,
                      "wipeouts_gt20": 0, "wipeouts_gt20_pct": 0}

        # ═══ D. PROFIT FACTOR / KELLY / EV ═══
        total_wins = wins_ret.sum() if n_wins > 0 else 0
        total_losses = abs(losses_ret.sum()) if n_losses > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else (np.inf if total_wins > 0 else 0)
        avg_win = wins_ret.mean() if n_wins > 0 else 0
        avg_loss = abs(losses_ret.mean()) if n_losses > 0 else 0
        if avg_loss > 0 and avg_win > 0:
            kelly = win_rate - (1 - win_rate) / (avg_win / avg_loss)
        elif avg_loss > 0:
            kelly = -np.inf
        else:
            kelly = win_rate
        ev, ev_lo, ev_hi = boot_ci(returns)

        # ═══ E. LOSING STREAKS ═══
        streaks = []
        current = 0
        for r in returns:
            if r <= 0:
                current += 1
            else:
                if current > 0:
                    streaks.append(current)
                current = 0
        if current > 0:
            streaks.append(current)
        loss_streaks = np.array(streaks) if streaks else np.array([0])

        # ═══ H. SAMPLE QUALITY ═══
        if n >= 30:
            quality = "ALTA (N≥30)"
        elif n >= 10:
            quality = "MEDIA (10≤N<30)"
        else:
            quality = "BAJA (N<10)"

        horizon_results[h] = {
            "n": n,
            "n_wins": n_wins,
            "n_losses": n_losses,
            "win_rate": win_rate,
            "wr_ci95": (wr_lo, wr_hi),
            "sample_quality": quality,
            # B
            "wins_return": b_ret,
            "wins_median_ci95": (b_lo, b_hi),
            # C
            "losses_return": c_loss,
            # D
            "profit_factor": profit_factor,
            "kelly": kelly,
            "ev": ev,
            "ev_ci95": (ev_lo, ev_hi),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            # E
            "loss_streaks": loss_streaks,
            "max_streak": int(loss_streaks.max()) if len(loss_streaks) > 0 else 0,
            "mean_streak": float(loss_streaks.mean()) if len(loss_streaks) > 0 else 0,
            "n_streaks": len(loss_streaks),
        }

    # ═══ F. TIMING vs ZIGZAG (horizon-independent) ═══
    pivot_days_arr = df["pivot_days"].values
    anticipada_mask = pivot_days_arr > 0
    en_pivote_mask = pivot_days_arr == 0
    retrasada_mask = pivot_days_arr < 0

    n_anticipada = int(anticipada_mask.sum())
    n_en_pivote = int(en_pivote_mask.sum())
    n_retrasada = int(retrasada_mask.sum())

    # Return at 20d by timing category
    ret20 = df["fwd_20d"].values
    ret_anticipada = ret20[anticipada_mask] if n_anticipada > 0 else np.array([])
    ret_en_pivote = ret20[en_pivote_mask] if n_en_pivote > 0 else np.array([])
    ret_retrasada = ret20[retrasada_mask] if n_retrasada > 0 else np.array([])

    # Cost: drawdown for anticipada (from entry to pivot)
    dd_anticipada_arr = df.loc[anticipada_mask, "dd_to_pivot"].dropna().values
    costo_ant, costo_ant_lo, costo_ant_hi = boot_ci(dd_anticipada_arr) if len(
        dd_anticipada_arr) > 0 else (np.nan, np.nan, np.nan)

    timing = {
        "n_anticipada": n_anticipada,
        "n_en_pivote": n_en_pivote,
        "n_retrasada": n_retrasada,
        "ret_anticipada_mean": ret_anticipada.mean() if len(ret_anticipada) > 0 else np.nan,
        "ret_en_pivote_mean": ret_en_pivote.mean() if len(ret_en_pivote) > 0 else np.nan,
        "ret_retrasada_mean": ret_retrasada.mean() if len(ret_retrasada) > 0 else np.nan,
        "costo_anticipada_mean": costo_ant,
        "costo_anticipada_ci95": (costo_ant_lo, costo_ant_hi),
        "pivot_days_stats": {
            "P25": np.percentile(pivot_days_arr, 25),
            "P50": np.percentile(pivot_days_arr, 50),
            "P75": np.percentile(pivot_days_arr, 75),
            "mean": pivot_days_arr.mean(),
            "min": pivot_days_arr.min(),
            "max": pivot_days_arr.max(),
        },
    }

    # ═══ G. FALLING KNIFE (horizon-independent) ═══
    dd_pivot_arr = df["dd_to_pivot"].dropna().values
    cuchillo_mask = dd_pivot_arr < -5  # >5% drawdown from entry to pivot
    n_cuchillo = int(cuchillo_mask.sum())

    if n_cuchillo > 0:
        cuchillo_d2 = df.loc[df["dd_to_pivot"].notna() & (df["dd_to_pivot"] < -5), "d2_bin"].value_counts().to_dict()
        cuchillo_d3 = df.loc[df["dd_to_pivot"].notna() & (df["dd_to_pivot"] < -5), "d3_bin"].value_counts().to_dict()
    else:
        cuchillo_d2 = {}
        cuchillo_d3 = {}

    cuchillo = {
        "n_cuchillo": n_cuchillo,
        "cuchillo_pct": n_cuchillo / n_total * 100 if n_total > 0 else 0,
        "cuchillo_d2_dist": cuchillo_d2,
        "cuchillo_d3_dist": cuchillo_d3,
        "dd_to_pivot_median": np.median(dd_pivot_arr) if len(dd_pivot_arr) > 0 else np.nan,
    }

    # Store
    all_results[name] = {
        "n_entries": n_total,
        "extreme_d1": extreme_d1[0],
        "horizons": horizon_results,
        "timing": timing,
        "cuchillo": cuchillo,
        "df": df,
    }

store.close()

# ═══════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════

print("\n\n")
print("╔" + "═" * 78 + "╗")
print("║" + "  ESTUDIO WINS vs LOSSES v2 — FG · VVIX · SKEW".center(78) + "║")
print("╠" + "═" * 78 + "╣")
print("║" + "  METODOLOGÍA CORREGIDA: entrada en BARRA de señal, NO zigzag.".center(78) + "║")
print("║" + f"  Salida: forward 5/10/20/40d. De-clustering: ≥{CLUSTER_WINDOW}d.".center(78) + "║")
print("║" + "  CI95: bootstrap 2000 iter. D3 = std(2)/std(10).".center(78) + "║")
print("╚" + "═" * 78 + "╝")

for name, results in all_results.items():
    if results is None:
        print(f"\n{'─'*80}\n  {name}: SIN DATOS\n{'─'*80}")
        continue

    extreme_label = results["extreme_d1"]
    print(f"\n{'═'*80}")
    print(f"  {name} — D1: {extreme_label}  |  {results['n_entries']} entradas (de-clustered ≥{CLUSTER_WINDOW}d)")
    print(f"{'═'*80}")

    # ── Dimension H: sample quality summary ──
    print(f"\n  ── H. CALIDAD DE MUESTRA ──")
    for h in FORWARD_HORIZONS:
        hr = results["horizons"].get(h, {})
        print(f"    Forward {h:>2d}d: N={hr.get('n', 0):>3d}  →  {hr.get('sample_quality', 'N/A')}")

    # Per-horizon detail
    for h in FORWARD_HORIZONS:
        hr = results["horizons"].get(h, {})
        if hr.get("n", 0) == 0:
            continue

        print(f"\n  ═══ FORWARD {h}d (N={hr['n']}) ═══")

        # A. Win rate
        print(f"  ── A. WIN RATE ──")
        wr_val = hr.get("win_rate", 0) * 100
        wr_lo = hr["wr_ci95"][0] * 100 if not np.isnan(hr["wr_ci95"][0]) else np.nan
        wr_hi = hr["wr_ci95"][1] * 100 if not np.isnan(hr["wr_ci95"][1]) else np.nan
        print(f"    Wins: {hr['n_wins']} | Losses: {hr['n_losses']} | "
              f"Win rate: {wr_val:.1f}%  CI95=[{wr_lo:.1f}%, {wr_hi:.1f}%]")

        # B. Wins
        print(f"  ── B. WINS (N={hr['n_wins']}) ──")
        br = hr["wins_return"]
        if hr["n_wins"] > 0:
            print(f"    Magnitud: P25={br['P25']:+.2f}%  P50={br['P50']:+.2f}%  "
                  f"P75={br['P75']:+.2f}%  P90={br['P90']:+.2f}%  max={br['max']:+.2f}%")
        else:
            print(f"    (sin wins)")

        # C. Losses
        print(f"  ── C. LOSSES (N={hr['n_losses']}) ──")
        cl = hr["losses_return"]
        if hr["n_losses"] > 0:
            print(f"    Magnitud: P25={cl['P25']:+.2f}%  P50={cl['P50']:+.2f}%  "
                  f"P75={cl['P75']:+.2f}%  P90={cl['P90']:+.2f}%  min={cl['min']:+.2f}%")
            if not np.isnan(cl.get("max_dd", np.nan)):
                print(f"    Max DD intra-trade: {cl['max_dd']:+.2f}%  avg={cl['avg_intra_dd']:+.2f}%")
            print(f"    Wipeouts (>20%): {cl['wipeouts_gt20']} ({cl['wipeouts_gt20_pct']:.0f}% de losses)")
        else:
            print(f"    (sin losses)")

        # D. Cost/benefit
        print(f"  ── D. COSTO/BENEFICIO ──")
        pf = hr["profit_factor"]
        k = hr["kelly"]
        ev = hr["ev"]
        ev_lo, ev_hi = hr["ev_ci95"]
        aw = hr["avg_win"]
        al = hr["avg_loss"]
        print(f"    Profit Factor: {pf:.2f}" if pf != np.inf else f"    Profit Factor: ∞")
        print(f"    Kelly: {k*100:.1f}%" if not np.isinf(k) else f"    Kelly: -∞ (sin wins)")
        print(f"    EV: {ev:+.2f}%  CI95=[{ev_lo:+.2f}%, {ev_hi:+.2f}%]")
        print(f"    Avg Win: {aw:+.2f}%  Avg Loss: {al:.2f}%")
        if al > 0:
            print(f"    Win/Loss ratio: {aw/al:.2f}")

        # E. Streaks
        print(f"  ── E. RACHAS ──")
        ls = hr["loss_streaks"]
        streak_counts = Counter(ls)
        print(f"    Rachas totales: {hr['n_streaks']} | Max: {hr['max_streak']} | "
              f"Media: {hr['mean_streak']:.1f}")
        if len(ls) > 0:
            print(f"    Frec: " + " | ".join(f"{int(k)}×{v}" for k, v in sorted(streak_counts.items())))

    # ── F. Timing vs zigzag ──
    timing = results["timing"]
    print(f"\n  ── F. TIMING vs ZIGZAG ──")
    print(f"    Anticipada (señal antes del pivote): {timing['n_anticipada']} "
          f"({timing['n_anticipada']/results['n_entries']*100:.0f}%)")
    print(f"    En pivote (señal = pivote):         {timing['n_en_pivote']} "
          f"({timing['n_en_pivote']/results['n_entries']*100:.0f}%)")
    print(f"    Retrasada (señal después pivote):    {timing['n_retrasada']} "
          f"({timing['n_retrasada']/results['n_entries']*100:.0f}%)")
    pds = timing["pivot_days_stats"]
    print(f"    Días señal→pivote: P50={pds['P50']:.0f}  mean={pds['mean']:.1f}  "
          f"[{pds['min']:.0f}, {pds['max']:.0f}]")
    if not np.isnan(timing["costo_anticipada_mean"]):
        print(f"    Costo drawdown (anticipada): {timing['costo_anticipada_mean']:+.2f}%  "
              f"CI95=[{timing['costo_anticipada_ci95'][0]:+.2f}%, {timing['costo_anticipada_ci95'][1]:+.2f}%]")
    if not np.isnan(timing["ret_anticipada_mean"]):
        print(f"    Ret 20d anticipada: {timing['ret_anticipada_mean']:+.2f}%  "
              f"en_pivote: {timing['ret_en_pivote_mean']:+.2f}%  "
              f"retrasada: {timing['ret_retrasada_mean']:+.2f}%")

    # ── G. Falling knife ──
    cuchillo = results["cuchillo"]
    print(f"\n  ── G. CUCHILLO CAYENDO (DD >5% entrada→pivote) ──")
    print(f"    Casos: {cuchillo['n_cuchillo']} / {results['n_entries']} "
          f"({cuchillo['cuchillo_pct']:.0f}%)")
    print(f"    DD mediana entrada→pivote: {cuchillo['dd_to_pivot_median']:+.2f}%")
    if cuchillo["cuchillo_d2_dist"]:
        print(f"    D2 en cuchillos: {cuchillo['cuchillo_d2_dist']}")
        print(f"    D3 en cuchillos: {cuchillo['cuchillo_d3_dist']}")

    # Detail table (first 15 entries)
    print(f"\n  ── DETALLE PRIMERAS 15 ENTRADAS ──")
    print(f"    {'Fecha':<12} {'State Key':<50} {'5d':>7} {'10d':>7} {'20d':>7} {'40d':>7} "
          f"{'PivD':>5} {'Tipo':>4}")
    print(f"    {'─'*12} {'─'*50} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*5} {'─'*4}")
    for _, row in results["df"].head(15).iterrows():
        print(f"    {str(row['signal_date'].date()):<12} {row['state_key']:<50} "
              f"{row['fwd_5d']:>+6.2f}% {row['fwd_10d']:>+6.2f}% {row['fwd_20d']:>+6.2f}% "
              f"{row['fwd_40d']:>+6.2f}% {row['pivot_days']:>+4.0f}  {row['pivot_type']:<4}")


# ═══════════════════════════════════════════════════════════════════════════════
# TABLA RESUMEN COMPARATIVA — por horizonte
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═'*80}")
print(f"  TABLA RESUMEN — FG vs VVIX vs SKEW (METODOLOGÍA CORREGIDA)")
print(f"{'═'*80}")

for h in FORWARD_HORIZONS:
    print(f"\n  ═══ FORWARD {h}d ═══")
    header = f"  {'Métrica':<28}"
    for name in ["FG", "VVIX", "SKEW"]:
        r = all_results.get(name)
        if r and h in r["horizons"]:
            header += f" {name + ' (N=' + str(r['horizons'][h]['n']) + ')':<30}"
        else:
            header += f" {name:<30}"
    print(header)
    print(f"  {'─'*28}{'─'*30}{'─'*30}{'─'*30}")

    rows = [
        ("Win rate", lambda hr: f"{hr['win_rate']*100:.1f}%  CI95=[{hr['wr_ci95'][0]*100:.1f}%, {hr['wr_ci95'][1]*100:.1f}%]"),
        ("Mediana win", lambda hr: f"{hr['wins_return']['P50']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("P90 win", lambda hr: f"{hr['wins_return']['P90']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("Max win", lambda hr: f"{hr['wins_return']['max']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("Mediana loss", lambda hr: f"{hr['losses_return']['P50']:+.2f}%" if hr['n_losses'] > 0 else "n/a"),
        ("Min loss", lambda hr: f"{hr['losses_return']['min']:+.2f}%" if hr['n_losses'] > 0 else "n/a"),
        ("Wipeouts >20%", lambda hr: f"{hr['losses_return'].get('wipeouts_gt20', 0)}" if hr['n_losses'] > 0 else "0"),
        ("Profit Factor", lambda hr: f"{hr['profit_factor']:.2f}" if hr['profit_factor'] != np.inf else "∞"),
        ("Kelly", lambda hr: f"{hr['kelly']*100:.1f}%" if not np.isinf(hr['kelly']) else "-∞"),
        ("EV", lambda hr: f"{hr['ev']:+.2f}%  [{hr['ev_ci95'][0]:+.2f}%, {hr['ev_ci95'][1]:+.2f}%]"),
        ("Max streak", lambda hr: f"{hr['max_streak']}"),
        ("Calidad", lambda hr: hr['sample_quality']),
    ]
    for label, fn in rows:
        line = f"  {label:<28}"
        for name in ["FG", "VVIX", "SKEW"]:
            r = all_results.get(name)
            if r and h in r["horizons"] and r["horizons"][h].get("n", 0) > 0:
                val = fn(r["horizons"][h])
                line += f" {val:<30}"
            else:
                line += f" {'—':<30}"
        print(line)

# Timing summary
print(f"\n\n  ═══ TIMING vs ZIGZAG (20d) ═══")
header_t = f"  {'Métrica':<28}"
for name in ["FG", "VVIX", "SKEW"]:
    r = all_results.get(name)
    if r:
        header_t += f" {name + ' (N=' + str(r['n_entries']) + ')':<30}"
    else:
        header_t += f" {name:<30}"
print(header_t)
print(f"  {'─'*28}{'─'*30}{'─'*30}{'─'*30}")

for label, key in [
    ("Anticipada %", "n_anticipada"),
    ("En pivote %", "n_en_pivote"),
    ("Retrasada %", "n_retrasada"),
    ("Costo anticipación", "costo_anticipada_mean"),
    ("Cuchillo cayendo %", "n_cuchillo_pct"),
]:
    line = f"  {label:<28}"
    for name in ["FG", "VVIX", "SKEW"]:
        r = all_results.get(name)
        if r:
            if key == "n_anticipada":
                val = f"{r['timing']['n_anticipada']/r['n_entries']*100:.0f}%"
            elif key == "n_en_pivote":
                val = f"{r['timing']['n_en_pivote']/r['n_entries']*100:.0f}%"
            elif key == "n_retrasada":
                val = f"{r['timing']['n_retrasada']/r['n_entries']*100:.0f}%"
            elif key == "costo_anticipada_mean":
                m = r["timing"]["costo_anticipada_mean"]
                val = f"{m:+.2f}%" if not np.isnan(m) else "n/a"
            elif key == "n_cuchillo_pct":
                val = f"{r['cuchillo']['cuchillo_pct']:.0f}%"
            else:
                val = "?"
            line += f" {val:<30}"
        else:
            line += f" {'—':<30}"
    print(line)

print(f"\n{'═'*80}")
print(f"  FIN — ESTUDIO WINS vs LOSSES v2")
print(f"{'═'*80}")