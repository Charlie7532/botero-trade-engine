#!/usr/bin/env python3
"""
CONJUNCIÓN POSICIONAMIENTO: PCR + SKEW
========================================
¿Dos extremos simultáneos mejoran la señal?

Pregunta: PCR EXTREME_PUT_PANIC + SKEW LOW_TAIL_RISK simultáneos
          ¿mejoran la señal vs uno solo?

GRUPOS:
  A. PCR solo (EXTREME_PUT_PANIC, SKEW NO LOW_TAIL_RISK)
  B. SKEW solo (LOW_TAIL_RISK, PCR NO EXTREME_PUT_PANIC)
  C. CONJUNCIÓN (AMBOS extremos simultáneos)
  D. ANY (PCR extremo O SKEW extremo — unión para baseline)

METODOLOGÍA:
  - Entrada en BARRA de señal (no zigzag pivot)
  - Salida: forward 5/10/20/40d desde la barra
  - De-clustering: ≥10d entre señales del mismo grupo
  - CI95: bootstrap 2000 iter
  - D2 = diff(3), D3 = std(2)/std(10) — pitfall #46 formula
  - Dato mata relato — pitfall #40: PCR+SKEW = POSITIONING IMBALANCE

Dimensiones:
  A. Win rate + CI95
  B. Distribución WINS: P25/P50/P75/P90/max
  C. Distribución LOSSES: P25/P50/P75/P90/min, wipeouts >20%
  D. Profit factor, Kelly, EV, avg win/loss
  E. Rachas de pérdidas
  F. Timing vs zigzag
  G. Cuchillo cayendo (DD >5% entrada→pivote)
  H. Calidad de muestra (N≥30 / 10≤N<30 / N<10)
"""

import sys, os, json
from pathlib import Path
from datetime import timedelta
from collections import Counter

import numpy as np
import pandas as pd
from arnes.timing import classify_single_delta

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.pcr_lookup import PCRLookupAdapter
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

# ── Bootstrap helpers ───────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=2000, seed=42):
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


def boot_ci_winrate(arr, ci=95, n_boot=2000, seed=42):
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

# ── SPY daily prices ──
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_dates = list(spy.index)
spy_price_map = dict(zip(spy_dates, spy.values))
print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")

# ── Zigzag legs zz25 — ONLY for timing analysis (dimension F/G), not entry/exit ──
legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)
print(f"  zz25 pivots: {len(legs25)}")

pivot_items = []
for leg in legs25:
    d = pd.to_datetime(leg.start_timestamp).normalize()
    pivot_items.append((d, leg.start_type, leg.start_price))
pivot_items.sort(key=lambda x: x[0])

def find_nearest_pivot(signal_date):
    """Returns (delta_days, slot, pivot_date, pivot_type, pivot_price).
    delta_days = (signal_date - pivot_date).days
    slot = 't-2' | 't-1' | 't=0' | 't+1' | 't+2' | 'ENTRE'
    """
    best = None
    best_dist = float('inf')
    for pd_d, ptype, pprice in pivot_items:
        dist = (signal_date - pd_d).days
        if abs(dist) < best_dist:
            best = (dist, pd_d, ptype, pprice)
            best_dist = abs(dist)
        elif abs(dist) == best_dist and dist > best[0]:
            best = (dist, pd_d, ptype, pprice)
    slot = classify_single_delta(best[0])
    return best[0], slot, best[1], best[2], best[3]

# ── PCR data ──
pcr_raw = store.load_bars("CBOE_PCR", "1d")["close"].copy()
pcr_raw.index = pd.to_datetime(pcr_raw.index).normalize()
pcr_s = pcr_raw[~pcr_raw.index.duplicated(keep="last")].sort_index()

# ── SKEW data ──
skew_raw = store.load_bars("SKEW", "1d")["close"].copy()
skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew_s = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()

# ── Align all three to common dates ──
common_dates = sorted(set(spy.index) & set(pcr_s.index) & set(skew_s.index))
spy_aligned = spy.loc[common_dates]
pcr_aligned = pcr_s.loc[common_dates]
skew_aligned = skew_s.loc[common_dates]
print(f"  Common aligned bars: {len(common_dates)} → {common_dates[0].date()} → {common_dates[-1].date()}")

# ── Adapters ──
pcr_adapter = PCRLookupAdapter()
skew_adapter = SkewLookupAdapter()
print(f"  PCR edges D1: {pcr_adapter.edges_d1}")
print(f"  PCR labels D1: {pcr_adapter.labels_d1}")
print(f"  SKEW edges D1: {skew_adapter.edges_d1}")
print(f"  SKEW labels D1: {skew_adapter.labels_d1}")

# Compute D2, D3
pcr_d2, pcr_d3 = compute_d2_d3(pcr_aligned)
skew_d2, skew_d3 = compute_d2_d3(skew_aligned)

# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFY EACH BAR
# ═══════════════════════════════════════════════════════════════════════════════

PCR_EXTREME = "EXTREME_PUT_PANIC"
SKEW_EXTREME = "LOW_TAIL_RISK"

bars_pcr_extreme = set()
bars_skew_extreme = set()
bar_info = {}  # date -> {pcr_state_key, skew_state_key, pcr_val, skew_val, ...}

for dt in common_dates:
    # PCR
    pcr_val = float(pcr_aligned[dt])
    pcr_vel = float(pcr_d2[dt]) if dt in pcr_d2.index and not pd.isna(pcr_d2[dt]) else 0.0
    pcr_vol = float(pcr_d3[dt]) if dt in pcr_d3.index and not pd.isna(pcr_d3[dt]) else 1.0

    # SKEW
    skew_val = float(skew_aligned[dt])
    skew_vel = float(skew_d2[dt]) if dt in skew_d2.index and not pd.isna(skew_d2[dt]) else 0.0
    skew_vol = float(skew_d3[dt]) if dt in skew_d3.index and not pd.isna(skew_d3[dt]) else 1.0

    pcr_d1 = "?"
    skew_d1 = "?"
    pcr_sk = "?"
    skew_sk = "?"
    pcr_d2_bin = "?"
    skew_d2_bin = "?"

    try:
        g_pcr = pcr_adapter.lookup_pcr_guidance(val=pcr_val, d3_speed=pcr_vel, vol_norm=pcr_vol, vol_d3=0.0)
        if g_pcr is not None:
            pcr_sk = g_pcr.state_key
            pcr_d1 = pcr_sk.split("__")[0]
            pcr_d2_bin = pcr_sk.split("__")[1] if "__" in pcr_sk else "?"
    except Exception:
        pass

    try:
        g_skew = skew_adapter.lookup_skew_guidance(val=skew_val, d3_speed=skew_vel, vol_norm=skew_vol, vol_d3=0.0)
        if g_skew is not None:
            skew_sk = g_skew.state_key
            skew_d1 = skew_sk.split("__")[0]
            skew_d2_bin = skew_sk.split("__")[1] if "__" in skew_sk else "?"
    except Exception:
        pass

    is_pcr_extreme = (pcr_d1 == PCR_EXTREME)
    is_skew_extreme = (skew_d1 == SKEW_EXTREME)

    if is_pcr_extreme:
        bars_pcr_extreme.add(dt)
    if is_skew_extreme:
        bars_skew_extreme.add(dt)

    bar_info[dt] = {
        "pcr_val": pcr_val, "pcr_d1": pcr_d1, "pcr_d2_bin": pcr_d2_bin,
        "pcr_vel": pcr_vel, "pcr_vol": pcr_vol, "pcr_state_key": pcr_sk,
        "skew_val": skew_val, "skew_d1": skew_d1, "skew_d2_bin": skew_d2_bin,
        "skew_vel": skew_vel, "skew_vol": skew_vol, "skew_state_key": skew_sk,
        "is_pcr_extreme": is_pcr_extreme,
        "is_skew_extreme": is_skew_extreme,
    }

# ── Define groups ──
print(f"\n═══ DISTRIBUCIÓN DE EXTREMOS ═══")
print(f"  PCR EXTREME_PUT_PANIC: {len(bars_pcr_extreme)} barras")
print(f"  SKEW LOW_TAIL_RISK: {len(bars_skew_extreme)} barras")

conjunction_bars = sorted(bars_pcr_extreme & bars_skew_extreme)
pcr_solo_bars = sorted(bars_pcr_extreme - bars_skew_extreme)
skew_solo_bars = sorted(bars_skew_extreme - bars_pcr_extreme)
any_extreme_bars = sorted(bars_pcr_extreme | bars_skew_extreme)

print(f"  PCR SOLO (PCR extreme, SKEW NO extreme): {len(pcr_solo_bars)} barras")
print(f"  SKEW SOLO (SKEW extreme, PCR NO extreme): {len(skew_solo_bars)} barras")
print(f"  CONJUNCIÓN (AMBOS extremos): {len(conjunction_bars)} barras")
print(f"  ANY (PCR o SKEW extreme): {len(any_extreme_bars)} barras")

# ═══════════════════════════════════════════════════════════════════════════════
# DE-CLUSTER & BUILD ENTRIES
# ═══════════════════════════════════════════════════════════════════════════════

CLUSTER_WINDOW = 10
FORWARD_HORIZONS = [5, 10, 20, 40]

GROUPS = {
    "PCR_SOLO": {"bars": pcr_solo_bars, "label": "PCR solo (EXTREME_PUT_PANIC, sin SKEW LOW_TAIL_RISK)"},
    "SKEW_SOLO": {"bars": skew_solo_bars, "label": "SKEW solo (LOW_TAIL_RISK, sin PCR EXTREME_PUT_PANIC)"},
    "CONJUNCION": {"bars": conjunction_bars, "label": "CONJUNCIÓN (PCR EXTREME_PUT_PANIC + SKEW LOW_TAIL_RISK simultáneos)"},
    "ANY": {"bars": any_extreme_bars, "label": "ANY (PCR extremo O SKEW extremo — unión baseline)"},
}


def de_cluster(dates, window=CLUSTER_WINDOW):
    """Keep only first signal in each window."""
    dates = sorted(dates)
    if not dates:
        return []
    result = [dates[0]]
    for d in dates[1:]:
        if (d - result[-1]).days >= window:
            result.append(d)
    return result


def build_entries(signal_dates, spy_aligned, spy_dates, spy_price_map):
    """Build entry records for a set of signal dates."""
    entries = []
    for entry_date in signal_dates:
        if entry_date not in spy_aligned.index:
            continue
        entry_price = float(spy_aligned.loc[entry_date])

        # Forward returns
        fwd_rets = {}
        fwd_end_dates = {}
        for h in FORWARD_HORIZONS:
            target_date = entry_date + timedelta(days=h)
            future_dates = [d for d in spy_dates if d >= target_date]
            if future_dates:
                exit_date = future_dates[0]
                exit_price = spy_price_map[exit_date]
                fwd_rets[h] = (exit_price / entry_price - 1) * 100
                fwd_end_dates[h] = exit_date
            else:
                fwd_rets[h] = np.nan
                fwd_end_dates[h] = None

        # Timing vs zigzag
        pivot_info = find_nearest_pivot(entry_date)
        pivot_days, slot, pivot_date, pivot_type, pivot_price = pivot_info

        # Falling knife DD
        dd_to_pivot = np.nan
        if pivot_type == "MIN" and pivot_price is not None:
            dd_to_pivot = (pivot_price / entry_price - 1) * 100

        # Intra-trade worst drawdown
        intra_dd = {}
        for h in FORWARD_HORIZONS:
            if h in fwd_end_dates and fwd_end_dates[h] is not None:
                end_dt = fwd_end_dates[h]
                window_slice = spy_aligned.loc[entry_date:end_dt]
                if len(window_slice) > 1:
                    lowest = window_slice.min()
                    intra_dd[h] = (lowest / entry_price - 1) * 100
                else:
                    intra_dd[h] = 0.0
            else:
                intra_dd[h] = np.nan

        info = bar_info.get(entry_date, {})
        entries.append({
            "signal_date": entry_date,
            "entry_price": entry_price,
            "pcr_state_key": info.get("pcr_state_key", "?"),
            "skew_state_key": info.get("skew_state_key", "?"),
            "pcr_d2_bin": info.get("pcr_d2_bin", "?"),
            "skew_d2_bin": info.get("skew_d2_bin", "?"),
            "pcr_val": info.get("pcr_val", np.nan),
            "skew_val": info.get("skew_val", np.nan),
            "pcr_vel": info.get("pcr_vel", np.nan),
            "skew_vel": info.get("skew_vel", np.nan),
            "fwd_5d": fwd_rets.get(5, np.nan),
            "fwd_10d": fwd_rets.get(10, np.nan),
            "fwd_20d": fwd_rets.get(20, np.nan),
            "fwd_40d": fwd_rets.get(40, np.nan),
            "pivot_days": pivot_days,
            "slot": slot,
            "pivot_type": pivot_type,
            "pivot_price": pivot_price,
            "dd_to_pivot": dd_to_pivot,
            "intra_dd_5d": intra_dd.get(5, np.nan),
            "intra_dd_10d": intra_dd.get(10, np.nan),
            "intra_dd_20d": intra_dd.get(20, np.nan),
            "intra_dd_40d": intra_dd.get(40, np.nan),
        })
    return pd.DataFrame(entries)


all_group_results = {}

for group_name, group_config in GROUPS.items():
    raw_bars = group_config["bars"]
    label = group_config["label"]

    print(f"\n{'═'*80}")
    print(f"  {group_name}: {label}")
    print(f"  Barras raw: {len(raw_bars)}")
    print(f"{'═'*80}")

    deduped = de_cluster(raw_bars)
    print(f"  Después de de-clustering (≥{CLUSTER_WINDOW}d): {len(deduped)}")

    if len(deduped) == 0:
        print(f"  ⚠️ Sin señales para {group_name}.")
        all_group_results[group_name] = None
        continue

    df = build_entries(deduped, spy_aligned, spy_dates, spy_price_map)
    n_total = len(df)
    print(f"  Entradas válidas: {n_total}")

    if n_total == 0:
        all_group_results[group_name] = None
        continue

    # ── Per-horizon analysis ──
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
        n_wins = int(wins_mask.sum())
        n_losses = int(losses_mask.sum())

        # A. Win rate + CI95
        wr, wr_lo, wr_hi = boot_ci_winrate(returns)

        # B. Wins distribution
        b_ret = {}
        if n_wins > 0:
            for pct_val in [25, 50, 75, 90]:
                b_ret[f"P{pct_val}"] = float(np.percentile(wins_ret, pct_val))
            b_ret["max"] = float(wins_ret.max())
        else:
            b_ret = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan, "max": np.nan}

        # C. Losses distribution
        c_loss = {}
        if n_losses > 0:
            for pct_val in [25, 50, 75, 90]:
                c_loss[f"P{pct_val}"] = float(np.percentile(losses_ret, pct_val))
            c_loss["min"] = float(losses_ret.min())
            dd_col = f"intra_dd_{h}d"
            loss_dd = df.loc[df[col].notna() & (df[col] <= 0), dd_col].dropna().values
            c_loss["max_dd"] = float(loss_dd.min()) if len(loss_dd) > 0 else np.nan
            c_loss["avg_intra_dd"] = float(loss_dd.mean()) if len(loss_dd) > 0 else np.nan
            c_loss["wipeouts_gt20"] = int((losses_ret < -20).sum())
            c_loss["wipeouts_gt20_pct"] = float((losses_ret < -20).mean() * 100)
        else:
            c_loss = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan,
                      "min": np.nan, "max_dd": np.nan, "avg_intra_dd": np.nan,
                      "wipeouts_gt20": 0, "wipeouts_gt20_pct": 0.0}

        # D. Profit factor / Kelly / EV
        total_wins = float(wins_ret.sum()) if n_wins > 0 else 0.0
        total_losses = abs(float(losses_ret.sum())) if n_losses > 0 else 0.0
        pf = total_wins / total_losses if total_losses > 0 else (np.inf if total_wins > 0 else 0.0)
        avg_win = float(wins_ret.mean()) if n_wins > 0 else 0.0
        avg_loss = abs(float(losses_ret.mean())) if n_losses > 0 else 0.0
        if avg_loss > 0 and avg_win > 0:
            kelly = wr - (1 - wr) / (avg_win / avg_loss)
        elif avg_loss > 0:
            kelly = -np.inf
        else:
            kelly = wr
        ev, ev_lo, ev_hi = boot_ci(returns)

        # E. Losing streaks
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

        # H. Sample quality
        if n >= 30:
            quality = "ALTA (N≥30)"
        elif n >= 10:
            quality = "MEDIA (10≤N<30)"
        else:
            quality = "BAJA (N<10)"

        horizon_results[h] = {
            "n": n, "n_wins": n_wins, "n_losses": n_losses,
            "win_rate": float(wr), "wr_ci95": [float(wr_lo), float(wr_hi)],
            "sample_quality": quality,
            "wins_return": b_ret,
            "losses_return": c_loss,
            "profit_factor": float(pf) if pf != np.inf else "inf",
            "kelly": float(kelly) if not np.isinf(kelly) else ("-inf" if kelly < 0 else "inf"),
            "ev": float(ev), "ev_ci95": [float(ev_lo), float(ev_hi)],
            "avg_win": float(avg_win), "avg_loss": float(avg_loss),
            "loss_streaks": [int(x) for x in loss_streaks],
            "max_streak": int(loss_streaks.max()) if len(loss_streaks) > 0 else 0,
            "mean_streak": float(loss_streaks.mean()) if len(loss_streaks) > 0 else 0.0,
            "n_streaks": len(loss_streaks),
        }

    # F. Timing vs zigzag (6 Slots Canónicos: t-2, t-1, t=0, t+1, t+2, ENTRE)
    pivot_days_arr = df["pivot_days"].values
    slots_arr = df["slot"].values
    counts = {s: int((slots_arr == s).sum()) for s in ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]}
    n_ant = counts["t-2"] + counts["t-1"]
    n_exa = counts["t=0"]
    n_ret = counts["t+1"] + counts["t+2"]
    n_fue = counts["ENTRE"]
    n_rng = n_ant + n_exa + n_ret

    ret20 = df["fwd_20d"].values
    dd_pivot_arr = df["dd_to_pivot"].dropna().values

    timing = {
        "slots": counts,
        "n_en_rango": n_rng,
        "pct_en_rango": float(n_rng / n_total * 100) if n_total > 0 else 0.0,
        "n_anticipada": n_ant,
        "pct_anticipada": float(n_ant / n_total * 100) if n_total > 0 else 0.0,
        "n_exacta": n_exa,
        "pct_exacta": float(n_exa / n_total * 100) if n_total > 0 else 0.0,
        "n_retrasada": n_ret,
        "pct_retrasada": float(n_ret / n_total * 100) if n_total > 0 else 0.0,
        "n_fuera_de_rango": n_fue,
        "pct_fuera_de_rango": float(n_fue / n_total * 100) if n_total > 0 else 0.0,
        "ret_anticipada_mean": float(ret20[df["slot"].isin(["t-2", "t-1"])].mean()) if n_ant > 0 else np.nan,
        "ret_exacta_mean": float(ret20[df["slot"] == "t=0"].mean()) if n_exa > 0 else np.nan,
        "ret_retrasada_mean": float(ret20[df["slot"].isin(["t+1", "t+2"])].mean()) if n_ret > 0 else np.nan,
        "ret_fuera_mean": float(ret20[df["slot"] == "ENTRE"].mean()) if n_fue > 0 else np.nan,
        "pivot_days_stats": {
            "P25": float(np.percentile(pivot_days_arr, 25)),
            "P50": float(np.percentile(pivot_days_arr, 50)),
            "P75": float(np.percentile(pivot_days_arr, 75)),
            "mean": float(pivot_days_arr.mean()),
            "min": int(pivot_days_arr.min()),
            "max": int(pivot_days_arr.max()),
        },
    }

    # G. Falling knife
    cuchillo_mask = dd_pivot_arr < -5
    n_cuchillo = int(cuchillo_mask.sum())
    cuchillo = {
        "n_cuchillo": n_cuchillo,
        "cuchillo_pct": float(n_cuchillo / n_total * 100) if n_total > 0 else 0.0,
        "dd_to_pivot_median": float(np.median(dd_pivot_arr)) if len(dd_pivot_arr) > 0 else np.nan,
    }

    all_group_results[group_name] = {
        "n_entries": n_total,
        "label": label,
        "horizons": horizon_results,
        "timing": timing,
        "cuchillo": cuchillo,
        "n_raw_bars": len(raw_bars),
        "n_deduped": len(deduped),
    }

store.close()

# ═══════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════

print("\n\n")
print("╔" + "═" * 78 + "╗")
print("║" + "  CONJUNCIÓN POSICIONAMIENTO: PCR + SKEW".center(78) + "║")
print("╠" + "═" * 78 + "╣")
print("║" + "  ¿Dos extremos simultáneos mejoran la señal?".center(78) + "║")
print("║" + "  PCR EXTREME_PUT_PANIC + SKEW LOW_TAIL_RISK".center(78) + "║")
print("║" + f"  Metodología: entrada en BARRA, forward 5/10/20/40d, decluster ≥{CLUSTER_WINDOW}d".center(78) + "║")
print("╚" + "═" * 78 + "╝")

COMPARISON_ORDER = ["PCR_SOLO", "SKEW_SOLO", "CONJUNCION", "ANY"]

for group_name in COMPARISON_ORDER:
    results = all_group_results.get(group_name)
    if results is None:
        print(f"\n{'─'*80}\n  {group_name}: SIN DATOS\n{'─'*80}")
        continue

    label = results["label"]
    n = results["n_entries"]
    print(f"\n{'═'*80}")
    print(f"  {group_name}: {label}")
    print(f"  Entradas: {n} (raw: {results['n_raw_bars']}, deduped: {results['n_deduped']})")
    print(f"{'═'*80}")

    # H. Sample quality
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

        # A
        print(f"  ── A. WIN RATE ──")
        wr_val = hr["win_rate"] * 100
        wr_lo = hr["wr_ci95"][0] * 100
        wr_hi = hr["wr_ci95"][1] * 100
        print(f"    Wins: {hr['n_wins']} | Losses: {hr['n_losses']} | "
              f"Win rate: {wr_val:.1f}%  CI95=[{wr_lo:.1f}%, {wr_hi:.1f}%]")

        # B
        print(f"  ── B. WINS (N={hr['n_wins']}) ──")
        br = hr["wins_return"]
        if hr["n_wins"] > 0:
            print(f"    Magnitud: P25={br['P25']:+.2f}%  P50={br['P50']:+.2f}%  "
                  f"P75={br['P75']:+.2f}%  P90={br['P90']:+.2f}%  max={br['max']:+.2f}%")
        else:
            print(f"    (sin wins)")

        # C
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

        # D
        print(f"  ── D. COSTO/BENEFICIO ──")
        pf = hr["profit_factor"]
        k = hr["kelly"]
        ev = hr["ev"]
        ev_lo, ev_hi = hr["ev_ci95"]
        aw = hr["avg_win"]
        al = hr["avg_loss"]
        pf_str = f"{pf:.2f}" if isinstance(pf, float) else str(pf)
        print(f"    Profit Factor: {pf_str}")
        k_str = f"{k*100:.1f}%" if isinstance(k, float) else str(k)
        print(f"    Kelly: {k_str}")
        print(f"    EV: {ev:+.2f}%  CI95=[{ev_lo:+.2f}%, {ev_hi:+.2f}%]")
        print(f"    Avg Win: {aw:+.2f}%  Avg Loss: {al:.2f}%")
        if al > 0:
            print(f"    Win/Loss ratio: {aw/al:.2f}")

        # E
        print(f"  ── E. RACHAS ──")
        ls = hr["loss_streaks"]
        streak_counts = Counter(ls)
        print(f"    Rachas totales: {hr['n_streaks']} | Max: {hr['max_streak']} | "
              f"Media: {hr['mean_streak']:.1f}")
        if len(ls) > 0:
            print(f"    Frec: " + " | ".join(f"{k}×{v}" for k, v in sorted(streak_counts.items())))

    # F. Timing
    timing = results["timing"]
    print(f"\n  ── F. TIMING vs ZIGZAG (6 Slots Canónicos) ──")
    print(f"    EN RANGO ([-2t, +2t]): {timing['n_en_rango']} / {n} ({timing['pct_en_rango']:.0f}%)")
    print(f"      • Anticipada  (t-2, t-1): {timing['n_anticipada']} ({timing['pct_anticipada']:.0f}%)  [t-2: {timing['slots']['t-2']}, t-1: {timing['slots']['t-1']}]")
    print(f"      • Exacta      (t=0):     {timing['n_exacta']} ({timing['pct_exacta']:.0f}%)")
    print(f"      • Retrasada   (t+1, t+2): {timing['n_retrasada']} ({timing['pct_retrasada']:.0f}%)  [t+1: {timing['slots']['t+1']}, t+2: {timing['slots']['t+2']}]")
    print(f"    FUERA DE RANGO (ENTRE):    {timing['n_fuera_de_rango']} ({timing['pct_fuera_de_rango']:.0f}%)")
    pds = timing["pivot_days_stats"]
    print(f"    Días señal→pivote: P50={pds['P50']:.0f}  mean={pds['mean']:.1f}  [{pds['min']}, {pds['max']}]")

    # G. Cuchillo
    cuchillo = results["cuchillo"]
    print(f"\n  ── G. CUCHILLO CAYENDO (DD >5% entrada→pivote) ──")
    print(f"    Casos: {cuchillo['n_cuchillo']} / {n} ({cuchillo['cuchillo_pct']:.0f}%)")
    print(f"    DD mediana entrada→pivote: {cuchillo['dd_to_pivot_median']:+.2f}%")

# ═══════════════════════════════════════════════════════════════════════════════
# TABLA COMPARATIVA: CONJUNCIÓN vs SOLO
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═'*80}")
print(f"  TABLA COMPARATIVA — PCR solo vs SKEW solo vs CONJUNCIÓN")
print(f"  Dato mata relato: ¿dos extremos > uno?")
print(f"{'═'*80}")

for h in FORWARD_HORIZONS:
    print(f"\n  ═══ FORWARD {h}d ═══")

    # Build header dynamically from groups with data
    active_groups = []
    for gn in COMPARISON_ORDER:
        r = all_group_results.get(gn)
        if r and h in r["horizons"] and r["horizons"][h].get("n", 0) > 0:
            active_groups.append(gn)

    header = f"  {'Métrica':<28}"
    col_width = 28
    for gn in active_groups:
        r = all_group_results[gn]
        nn = r["horizons"][h]["n"]
        header += f" {gn + ' (N=' + str(nn) + ')':<{col_width}}"
    print(header)
    print(f"  {'─'*28}{'─'*col_width * len(active_groups)}")

    rows = [
        ("Win rate", lambda hr: f"{hr['win_rate']*100:.1f}%  [{hr['wr_ci95'][0]*100:.1f}%, {hr['wr_ci95'][1]*100:.1f}%]"),
        ("Mediana win", lambda hr: f"{hr['wins_return']['P50']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("P90 win", lambda hr: f"{hr['wins_return']['P90']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("Max win", lambda hr: f"{hr['wins_return']['max']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("Mediana loss", lambda hr: f"{hr['losses_return']['P50']:+.2f}%" if hr['n_losses'] > 0 else "n/a"),
        ("Min loss", lambda hr: f"{hr['losses_return']['min']:+.2f}%" if hr['n_losses'] > 0 else "n/a"),
        ("Wipeouts >20%", lambda hr: f"{hr['losses_return'].get('wipeouts_gt20', 0)} ({hr['losses_return'].get('wipeouts_gt20_pct', 0):.0f}%)"),
        ("Profit Factor", lambda hr: f"{hr['profit_factor']:.2f}" if isinstance(hr['profit_factor'], float) else str(hr['profit_factor'])),
        ("Kelly", lambda hr: f"{hr['kelly']*100:.1f}%" if isinstance(hr['kelly'], float) else str(hr['kelly'])),
        ("EV (expected value)", lambda hr: f"{hr['ev']:+.2f}%  [{hr['ev_ci95'][0]:+.2f}%, {hr['ev_ci95'][1]:+.2f}%]"),
        ("Avg Win", lambda hr: f"{hr['avg_win']:+.2f}%"),
        ("Avg Loss", lambda hr: f"{hr['avg_loss']:+.2f}%"),
        ("Max streak", lambda hr: f"{hr['max_streak']}"),
        ("Calidad", lambda hr: hr['sample_quality']),
    ]
    for label, fn in rows:
        line = f"  {label:<28}"
        for gn in active_groups:
            r = all_group_results[gn]
            if r and h in r["horizons"] and r["horizons"][h].get("n", 0) > 0:
                val = fn(r["horizons"][h])
                line += f" {val:<{col_width}}"
            else:
                line += f" {'—':<{col_width}}"
        print(line)

# ── Timing comparison ──
print(f"\n\n  ═══ TIMING vs ZIGZAG ═══")
active_gt = [gn for gn in COMPARISON_ORDER if all_group_results.get(gn)]
header_t = f"  {'Métrica':<28}"
for gn in active_gt:
    r = all_group_results[gn]
    header_t += f" {gn + ' (N=' + str(r['n_entries']) + ')':<{col_width}}"
print(header_t)
print(f"  {'─'*28}{'─'*col_width * len(active_gt)}")

for label, getter in [
    ("En Rango % ([-2t, +2t])", lambda r: f"{r['timing']['pct_en_rango']:.0f}%"),
    ("Anticipada % (t-2, t-1)", lambda r: f"{r['timing']['pct_anticipada']:.0f}%"),
    ("Exacta % (t=0)",          lambda r: f"{r['timing']['pct_exacta']:.0f}%"),
    ("Retrasada % (t+1, t+2)",   lambda r: f"{r['timing']['pct_retrasada']:.0f}%"),
    ("Fuera de Rango % (ENTRE)", lambda r: f"{r['timing']['pct_fuera_de_rango']:.0f}%"),
    ("Cuchillo cayendo %",       lambda r: f"{r['cuchillo']['cuchillo_pct']:.0f}%"),
]:
    line = f"  {label:<28}"
    for gn in active_gt:
        r = all_group_results[gn]
        if r:
            line += f" {getter(r):<{col_width}}"
        else:
            line += f" {'—':<{col_width}}"
    print(line)

# ═══════════════════════════════════════════════════════════════════════════════
# ANSWER: ¿Mejora la conjunción?
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═'*80}")
print(f"  RESPUESTA: ¿DOS EXTREMOS SIMULTÁNEOS MEJORAN LA SEÑAL?")
print(f"{'═'*80}")

conj = all_group_results.get("CONJUNCION")
pcr_s = all_group_results.get("PCR_SOLO")
skew_s = all_group_results.get("SKEW_SOLO")
any_r = all_group_results.get("ANY")

for h in FORWARD_HORIZONS:
    print(f"\n  ── FORWARD {h}d ──")
    conj_hr = conj["horizons"][h] if conj and h in conj["horizons"] else None
    pcr_hr = pcr_s["horizons"][h] if pcr_s and h in pcr_s["horizons"] else None
    skew_hr = skew_s["horizons"][h] if skew_s and h in skew_s["horizons"] else None

    if conj_hr and conj_hr.get("n", 0) > 0:
        conj_wr = conj_hr["win_rate"] * 100
        conj_ev = conj_hr["ev"]
        conj_k = conj_hr["kelly"] if isinstance(conj_hr["kelly"], float) else np.nan
        conj_n = conj_hr["n"]

        print(f"    CONJUNCIÓN: WR={conj_wr:.1f}%  EV={conj_ev:+.2f}%  "
              f"Kelly={conj_k*100:.1f}%  N={conj_n}")

        if pcr_hr and pcr_hr.get("n", 0) > 0:
            delta_wr = conj_wr - pcr_hr["win_rate"] * 100
            delta_ev = conj_ev - pcr_hr["ev"]
            print(f"    vs PCR solo:  ΔWR={delta_wr:+.1f}pp  ΔEV={delta_ev:+.2f}pp  "
                  f"(conjunción {'MEJORA' if delta_ev > 0 else 'EMPEORA'} EV)")

        if skew_hr and skew_hr.get("n", 0) > 0:
            delta_wr = conj_wr - skew_hr["win_rate"] * 100
            delta_ev = conj_ev - skew_hr["ev"]
            print(f"    vs SKEW solo: ΔWR={delta_wr:+.1f}pp  ΔEV={delta_ev:+.2f}pp  "
                  f"(conjunción {'MEJORA' if delta_ev > 0 else 'EMPEORA'} EV)")
    else:
        print(f"    CONJUNCIÓN: SIN DATOS (N insuficiente)")

# ── Final verdict ──
print(f"\n  ═══ VEREDICTO ═══")
conj_20 = conj["horizons"][20] if conj and 20 in conj["horizons"] else None
pcr_20 = pcr_s["horizons"][20] if pcr_s and 20 in pcr_s["horizons"] else None
skew_20 = skew_s["horizons"][20] if skew_s and 20 in skew_s["horizons"] else None

if conj_20 and conj_20.get("n", 0) >= 10:
    verdict_parts = [f"La CONJUNCIÓN PCR+SKEW tiene N={conj_20['n']} entradas de-clustered."]

    if pcr_20 and pcr_20.get("n", 0) > 0:
        delta_ev_20 = conj_20["ev"] - pcr_20["ev"]
        verdict_parts.append(
            f"vs PCR solo ΔEV={delta_ev_20:+.2f}pp — "
            f"{'la conjunción MEJORA la señal' if delta_ev_20 > 0 else 'la conjunción NO mejora la señal'}")
    if skew_20 and skew_20.get("n", 0) > 0:
        delta_ev_skew_20 = conj_20["ev"] - skew_20["ev"]
        verdict_parts.append(
            f"vs SKEW solo ΔEV={delta_ev_skew_20:+.2f}pp — "
            f"{'la conjunción MEJORA la señal' if delta_ev_skew_20 > 0 else 'la conjunción NO mejora la señal'}")

    # Caveats about N
    if conj_20["n"] < 30:
        verdict_parts.append(
            f"⚠️ CALIDAD MEDIA/BAJA (N={conj_20['n']}<30): "
            f"los resultados tienen alta incertidumbre. "
            f"La conjunción ocurre ~{conj['n_entries']} veces en {conj['n_raw_bars']} barras raw "
            f"— es un evento RARO.")
    else:
        verdict_parts.append(f"✓ N={conj_20['n']}≥30: calidad ALTA, resultados confiables.")

    for vp in verdict_parts:
        print(f"    {vp}")
elif conj_20:
    print(f"    CONJUNCIÓN: N={conj_20.get('n', 0)} — MUESTRA INSUFICIENTE para veredicto.")
    print(f"    La conjunción de ambos extremos es tan rara que no hay suficientes")
    print(f"    observaciones independientes para comparar estadísticamente vs solo.")
else:
    print(f"    CONJUNCIÓN: SIN DATOS suficientes para emitir veredicto.")

print(f"\n{'═'*80}")
print(f"  FIN — CONJUNCIÓN POSICIONAMIENTO PCR + SKEW")
print(f"{'═'*80}")