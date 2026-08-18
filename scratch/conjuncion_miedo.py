#!/usr/bin/env python3
"""
CONJUNCIÓN MIEDO — VIX + VVIX + FG
====================================
Mide retorno forward cuando 1, 2, o 3 estaciones del cluster MIEDO están
en extremo simultáneamente. ¿La conjunción mejora vs 1 estación sola?

CLUSTER: VIX, VVIX, FG (miden miedo/euforia desde ángulos distintos).
EXTREMOS D1: VIX=CRISIS_SPIKE+ELEVATED_PANIC, VVIX=EXTREME_VVIX, FG=EXTREME_FEAR.

MÉTODO (pitfall #70): entrada en BARRA de señal, NO zigzag.
- Forward 5/10/20/40d, min 10d entre señales.
- CI95 bootstrap 2000, separar wins/losses, Kelly.
- D3 = std(2d)/std(10d) (pitfall #46).
- Calidad N: N≥30 ALTA, 10≤N<30 MEDIA, N<10 BAJA (pitfall #66).
"""

import sys
from pathlib import Path
from datetime import timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.vvix_lookup import VVIXLookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter

# ── Bootstrap helpers ───────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=2000, seed=42):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return arr.mean(), np.percentile(means, lo), np.percentile(means, hi)


def boot_ci_winrate(arr, ci=95, n_boot=2000, seed=42):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    props = (rng.choice(arr, size=(n_boot, len(arr)), replace=True) > 0).mean(axis=1)
    props.sort()
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

# SPY daily prices
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_dates = list(spy.index)
spy_map = dict(zip(spy_dates, spy.values))
print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")

# ── Station configs ──────────────────────────────────────────────────────────

STATIONS_CONFIG = {
    "VIX": {
        "ticker": "VIX",
        "adapter": VIXLookupAdapter(),
        "method": "lookup_vix_guidance",
        "extreme_d1": ["CRISIS_SPIKE", "ELEVATED_PANIC"],
    },
    "VVIX": {
        "ticker": "VVIX",
        "adapter": VVIXLookupAdapter(),
        "method": "lookup_vvix_guidance",
        "extreme_d1": ["EXTREME_VVIX"],
    },
    "FG": {
        "ticker": "FG",
        "adapter": FGLookupAdapter(),
        "method": "lookup_fg_guidance",
        "extreme_d1": ["EXTREME_FEAR"],
    },
}

CLUSTER_WINDOW = 10  # min calendar days between same-type signals
FORWARD_HORIZONS = [5, 10, 20, 40]

# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFY EACH BAR FOR EACH STATION
# ═══════════════════════════════════════════════════════════════════════════════

# Build boolean masks: for each station, which dates are in extreme D1
extreme_masks = {}
station_series = {}

for name, cfg in STATIONS_CONFIG.items():
    print(f"\n  {name} ({cfg['ticker']}) …")
    raw = store.load_bars(cfg["ticker"], "1d")["close"].copy()
    raw.index = pd.to_datetime(raw.index).normalize()
    s = raw[~raw.index.duplicated(keep="last")].sort_index()
    station_series[name] = s

    # Align with SPY
    common = sorted(set(s.index) & set(spy.index))
    s_aligned = s.loc[common]
    d2, d3 = compute_d2_d3(s_aligned)

    adapter = cfg["adapter"]
    lookup_fn = getattr(adapter, cfg["method"])
    extreme_set = set(cfg["extreme_d1"])

    extreme_dates = set()
    for dt in common:
        if dt not in d2.index or dt not in d3.index:
            continue
        val = float(s_aligned[dt])
        vel = float(d2[dt]) if not pd.isna(d2[dt]) else 0.0
        vol = float(d3[dt]) if not pd.isna(d3[dt]) else 1.0
        try:
            g = lookup_fn(val=val, d3_speed=vel, vol_norm=vol, vol_d3=0.0)
        except Exception:
            continue
        if g is None:
            continue
        d1_bin = g.state_key.split("__")[0]
        if d1_bin in extreme_set:
            extreme_dates.add(dt)

    extreme_masks[name] = extreme_dates
    print(f"    Barras extremas (raw): {len(extreme_dates)}")

store.close()

# ═══════════════════════════════════════════════════════════════════════════════
# BUILD CONJUNCTION SIGNALS
# ═══════════════════════════════════════════════════════════════════════════════

# Common dates where ALL three stations have data
all_common = sorted(
    set(extreme_masks["VIX"]) | set(extreme_masks["VVIX"]) | set(extreme_masks["FG"])
)

# Find the intersection of ALL station series dates (not just extreme)
vi = set(station_series["VIX"].index)
vv = set(station_series["VVIX"].index)
fg_dates = set(station_series["FG"].index)
common_all = sorted(vi & vv & fg_dates & set(spy_dates))
print(f"\n  Fechas con datos de las 3 estaciones + SPY: {len(common_all)}")

# For each common date, classify conjunction level
conjuncion_signals = {
    1: [],  # 1 station in extreme
    2: [],  # 2 stations in extreme
    3: [],  # 3 stations in extreme
}

for dt in common_all:
    n_extreme = 0
    which = []
    for name in ["VIX", "VVIX", "FG"]:
        if dt in extreme_masks[name]:
            n_extreme += 1
            which.append(name)
    if n_extreme >= 1:
        conjuncion_signals[n_extreme].append({
            "date": dt,
            "stations": tuple(which),
        })

for level in [1, 2, 3]:
    print(f"  Señales brutas conjunción-{level}: {len(conjuncion_signals[level])}")

# ═══════════════════════════════════════════════════════════════════════════════
# DE-CLUSTER: min CLUSTER_WINDOW days between signals of same conjunction level
# ═══════════════════════════════════════════════════════════════════════════════

deduped_signals = {}
for level in [1, 2, 3]:
    signals = sorted(conjuncion_signals[level], key=lambda x: x["date"])
    deduped = []
    last_date = None
    for sig in signals:
        if last_date is None or (sig["date"] - last_date).days >= CLUSTER_WINDOW:
            deduped.append(sig)
            last_date = sig["date"]
    deduped_signals[level] = deduped
    print(f"  Señales conjunción-{level} de-clustered (≥{CLUSTER_WINDOW}d): {len(deduped)}")

# ── Also build single-station signals for comparison ──
single_deduped = {}
for name in ["VIX", "VVIX", "FG"]:
    signals = sorted(extreme_masks[name])
    deduped = []
    last_date = None
    for dt in signals:
        if last_date is None or (dt - last_date).days >= CLUSTER_WINDOW:
            deduped.append(dt)
            last_date = dt
    single_deduped[name] = deduped
    print(f"  Señales {name} SOLA de-clustered: {len(deduped)}")

# ═══════════════════════════════════════════════════════════════════════════════
# COMPUTE FORWARD RETURNS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_forward_returns(signal_dates, label):
    """For each signal date, compute forward SPY returns at 5/10/20/40d."""
    entries = []
    for dt in signal_dates:
        if dt not in spy_map:
            continue
        entry_price = spy_map[dt]

        fwd = {}
        for h in FORWARD_HORIZONS:
            target = dt + timedelta(days=h)
            future = [d for d in spy_dates if d >= target]
            if future:
                exit_date = future[0]
                exit_price = spy_map[exit_date]
                fwd[h] = (exit_price / entry_price - 1) * 100
            else:
                fwd[h] = np.nan

        entries.append({
            "date": dt,
            "entry_price": entry_price,
            **{f"fwd_{h}d": fwd.get(h, np.nan) for h in FORWARD_HORIZONS},
        })

    return pd.DataFrame(entries)


print("\n═══ COMPUTANDO RETORNOS FORWARD ═══")

results = {}

# ── Conjunction signals ──
for level in [1, 2, 3]:
    label = f"CONJUNCIÓN-{level}"
    signal_dates = [s["date"] for s in deduped_signals[level]]
    df = compute_forward_returns(signal_dates, label)
    results[label] = df
    print(f"  {label}: {len(df)} entradas")

# ── Single station signals ──
for name in ["VIX", "VVIX", "FG"]:
    label = f"{name} SOLO"
    df = compute_forward_returns(single_deduped[name], label)
    results[label] = df
    print(f"  {label}: {len(df)} entradas")

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYZE EACH HORIZON FOR EACH SIGNAL TYPE
# ═══════════════════════════════════════════════════════════════════════════════

print("\n\n")
print("╔" + "═" * 78 + "╗")
print("║" + "  CONJUNCIÓN MIEDO — VIX + VVIX + FG".center(78) + "║")
print("╠" + "═" * 78 + "╣")
print("║" + "  Pregunta: ¿La conjunción de estaciones mejora la señal?".center(78) + "║")
print("║" + f"  Método: entrada en barra, forward 5/10/20/40d, ≥{CLUSTER_WINDOW}d cluster.".center(78) + "║")
print("║" + "  CI95 bootstrap 2000. D3 = std(2)/std(10).".center(78) + "║")
print("╚" + "═" * 78 + "╝")

analysis = {}

all_labels = ["CONJUNCIÓN-1", "CONJUNCIÓN-2", "CONJUNCIÓN-3",
              "VIX SOLO", "VVIX SOLO", "FG SOLO"]

for label in all_labels:
    df = results[label]
    if df is None or len(df) == 0:
        analysis[label] = None
        continue

    n_total = len(df)
    horizon_analysis = {}

    for h in FORWARD_HORIZONS:
        col = f"fwd_{h}d"
        returns = df[col].dropna().values
        if len(returns) == 0:
            horizon_analysis[h] = {"n": 0}
            continue

        n = len(returns)
        wins_mask = returns > 0
        losses_mask = returns <= 0
        wins = returns[wins_mask]
        losses = returns[losses_mask]
        n_wins = int(wins_mask.sum())
        n_losses = int(losses_mask.sum())

        # A. Win rate
        win_rate, wr_lo, wr_hi = boot_ci_winrate(returns)

        # B. Wins distribution
        if n_wins > 0:
            w_dist = {f"P{p}": float(np.percentile(wins, p)) for p in [25, 50, 75, 90]}
            w_dist["max"] = float(wins.max())
            w_dist["mean"] = float(wins.mean())
            _, w_med_lo, w_med_hi = boot_ci_winrate(wins)  # reuse for CI
        else:
            w_dist = {"P25": np.nan, "P50": np.nan, "P75": np.nan,
                      "P90": np.nan, "max": np.nan, "mean": np.nan}
            w_med_lo, w_med_hi = np.nan, np.nan

        # C. Losses distribution
        if n_losses > 0:
            l_dist = {f"P{p}": float(np.percentile(losses, p)) for p in [25, 50, 75, 90]}
            l_dist["min"] = float(losses.min())
            l_dist["mean"] = float(losses.mean())
            l_dist["wipeouts_gt20"] = int((losses < -20).sum())
            l_dist["wipeouts_gt20_pct"] = float((losses < -20).mean() * 100)
        else:
            l_dist = {"P25": np.nan, "P50": np.nan, "P75": np.nan,
                      "P90": np.nan, "min": np.nan, "mean": np.nan,
                      "wipeouts_gt20": 0, "wipeouts_gt20_pct": 0}

        # D. Profit factor / Kelly / EV
        total_wins = float(wins.sum()) if n_wins > 0 else 0
        total_losses = abs(float(losses.sum())) if n_losses > 0 else 0
        pf = total_wins / total_losses if total_losses > 0 else (np.inf if total_wins > 0 else 0)
        avg_win = float(wins.mean()) if n_wins > 0 else 0
        avg_loss = abs(float(losses.mean())) if n_losses > 0 else 0
        if avg_loss > 0 and avg_win > 0:
            kelly = win_rate - (1 - win_rate) / (avg_win / avg_loss)
        elif avg_loss > 0:
            kelly = -np.inf
        else:
            kelly = win_rate
        ev, ev_lo, ev_hi = boot_ci(returns)

        # Sample quality
        if n >= 30:
            quality = "ALTA (N≥30)"
        elif n >= 10:
            quality = "MEDIA (10≤N<30)"
        else:
            quality = "BAJA (N<10)"

        # E. Loss streaks
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

        horizon_analysis[h] = {
            "n": n, "n_wins": n_wins, "n_losses": n_losses,
            "win_rate": float(win_rate), "wr_ci95": (float(wr_lo), float(wr_hi)),
            "sample_quality": quality,
            "wins": w_dist,
            "losses": l_dist,
            "profit_factor": float(pf) if pf != np.inf else "∞",
            "kelly": float(kelly) if not np.isinf(kelly) else -999,
            "ev": float(ev), "ev_ci95": (float(ev_lo), float(ev_hi)),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "max_streak": int(loss_streaks.max()) if len(loss_streaks) > 0 else 0,
            "mean_streak": float(loss_streaks.mean()) if len(loss_streaks) > 0 else 0,
            "n_streaks": int(len(loss_streaks)),
        }

    analysis[label] = {
        "n_entries": n_total,
        "horizons": horizon_analysis,
        "df": df,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# PRINT REPORT
# ═══════════════════════════════════════════════════════════════════════════════

for label in all_labels:
    a = analysis[label]
    if a is None:
        print(f"\n{'─'*80}\n  {label}: SIN DATOS\n{'─'*80}")
        continue

    print(f"\n{'═'*80}")
    print(f"  {label}  |  {a['n_entries']} entradas (de-clustered ≥{CLUSTER_WINDOW}d)")
    print(f"{'═'*80}")

    # Quality summary
    print(f"\n  ── CALIDAD DE MUESTRA ──")
    for h in FORWARD_HORIZONS:
        hr = a["horizons"].get(h, {})
        q = hr.get("sample_quality", "N/A")
        n = hr.get("n", 0)
        print(f"    Forward {h:>2d}d: N={n:>3d}  →  {q}")

    # Per-horizon detail
    for h in FORWARD_HORIZONS:
        hr = a["horizons"].get(h, {})
        n = hr.get("n", 0)
        if n == 0:
            continue

        print(f"\n  ═══ FORWARD {h}d (N={n}) ═══")

        # A. Win rate
        wr = hr["win_rate"] * 100
        wr_l, wr_h = hr["wr_ci95"][0] * 100, hr["wr_ci95"][1] * 100
        print(f"    Win rate: {wr:.1f}%  CI95=[{wr_l:.1f}%, {wr_h:.1f}%]")
        print(f"    Wins: {hr['n_wins']}  Losses: {hr['n_losses']}")

        # B. Wins
        w = hr["wins"]
        if hr["n_wins"] > 0:
            print(f"    WINS:  P25={w['P25']:+.2f}%  P50={w['P50']:+.2f}%  "
                  f"P75={w['P75']:+.2f}%  P90={w['P90']:+.2f}%  "
                  f"max={w['max']:+.2f}%  mean={w['mean']:+.2f}%")

        # C. Losses
        l = hr["losses"]
        if hr["n_losses"] > 0:
            print(f"    LOSSES: P25={l['P25']:+.2f}%  P50={l['P50']:+.2f}%  "
                  f"P75={l['P75']:+.2f}%  P90={l['P90']:+.2f}%  "
                  f"min={l['min']:+.2f}%  mean={l['mean']:+.2f}%")
            print(f"    Wipeouts (>20%): {l['wipeouts_gt20']} ({l['wipeouts_gt20_pct']:.0f}%)")

        # D. Cost/benefit
        pf = hr["profit_factor"]
        k = hr["kelly"]
        ev = hr["ev"]
        ev_l, ev_h = hr["ev_ci95"]
        aw = hr["avg_win"]
        al = hr["avg_loss"]
        pf_str = f"{pf:.2f}" if isinstance(pf, float) else "∞"
        print(f"    Profit Factor: {pf_str}")
        k_str = f"{k*100:.1f}%" if k != -999 else "N/A"
        print(f"    Kelly: {k_str}")
        print(f"    EV: {ev:+.2f}%  CI95=[{ev_l:+.2f}%, {ev_h:+.2f}%]")
        print(f"    Avg Win: {aw:+.2f}%  Avg Loss: {al:+.2f}%")
        if al > 0 and aw > 0:
            print(f"    Win/Loss ratio: {aw/al:.2f}")

        # E. Streaks
        print(f"    Max loss streak: {hr['max_streak']}  "
              f"Mean: {hr['mean_streak']:.1f}  "
              f"Total streaks: {hr['n_streaks']}")

    # ── Detail table ──
    print(f"\n  ── PRIMERAS 20 ENTRADAS ──")
    hdr = f"    {'Fecha':<12} {'5d':>7} {'10d':>7} {'20d':>7} {'40d':>7}"
    print(hdr)
    print(f"    {'─'*12} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    for _, row in a["df"].head(20).iterrows():
        print(f"    {str(row['date'].date()):<12} "
              f"{row['fwd_5d']:>+6.2f}% {row['fwd_10d']:>+6.2f}% "
              f"{row['fwd_20d']:>+6.2f}% {row['fwd_40d']:>+6.2f}%")


# ═══════════════════════════════════════════════════════════════════════════════
# COMPARISON TABLE — CONJUNCTION vs SINGLE
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═'*100}")
print(f"  TABLA COMPARATIVA — CONJUNCIÓN vs ESTACIONES SOLAS")
print(f"{'═'*100}")

for h in FORWARD_HORIZONS:
    print(f"\n  ═══ FORWARD {h}d ═══")
    labels_to_show = ["CONJUNCIÓN-1", "CONJUNCIÓN-2", "CONJUNCIÓN-3",
                      "VIX SOLO", "VVIX SOLO", "FG SOLO"]

    # Header
    hdr = f"  {'Métrica':<26}"
    for lbl in labels_to_show:
        a = analysis.get(lbl)
        n_str = f"(N={a['horizons'][h]['n']})" if a and h in a["horizons"] and a["horizons"][h].get("n", 0) > 0 else ""
        hdr += f" {lbl + ' ' + n_str:<26}"
    print(hdr)
    print(f"  {'─'*26}{'─'*26 * len(labels_to_show)}")

    metrics = [
        ("N", lambda hr: f"{hr['n']}"),
        ("Win rate", lambda hr: f"{hr['win_rate']*100:.1f}% [{hr['wr_ci95'][0]*100:.1f}%, {hr['wr_ci95'][1]*100:.1f}%]"),
        ("Mediana win", lambda hr: f"{hr['wins']['P50']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("Max win", lambda hr: f"{hr['wins']['max']:+.2f}%" if hr['n_wins'] > 0 else "n/a"),
        ("Mediana loss", lambda hr: f"{hr['losses']['P50']:+.2f}%" if hr['n_losses'] > 0 else "n/a"),
        ("Min loss", lambda hr: f"{hr['losses']['min']:+.2f}%" if hr['n_losses'] > 0 else "n/a"),
        ("Wipeouts >20%", lambda hr: f"{hr['losses'].get('wipeouts_gt20', 0)}"),
        ("Profit Factor", lambda hr: f"{hr['profit_factor']:.2f}" if isinstance(hr['profit_factor'], float) else "∞"),
        ("Kelly", lambda hr: f"{hr['kelly']*100:.1f}%" if hr['kelly'] != -999 else "N/A"),
        ("EV", lambda hr: f"{hr['ev']:+.2f}% [{hr['ev_ci95'][0]:+.2f}%, {hr['ev_ci95'][1]:+.2f}%]"),
        ("Avg Win", lambda hr: f"{hr['avg_win']:+.2f}%"),
        ("Avg Loss", lambda hr: f"{hr['avg_loss']:+.2f}%"),
        ("Max streak", lambda hr: f"{hr['max_streak']}"),
        ("Calidad", lambda hr: hr['sample_quality']),
    ]

    for metric_name, fn in metrics:
        line = f"  {metric_name:<26}"
        for lbl in labels_to_show:
            a = analysis.get(lbl)
            if a and h in a["horizons"] and a["horizons"][h].get("n", 0) > 0:
                val = fn(a["horizons"][h])
                line += f" {str(val):<26}"
            else:
                line += f" {'—':<26}"
        print(line)


# ═══════════════════════════════════════════════════════════════════════════════
# KEY QUESTION: ¿MEJORA LA CONJUNCIÓN?
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═'*80}")
print(f"  RESPUESTA: ¿MEJORA LA CONJUNCIÓN?")
print(f"{'═'*80}")

for h in FORWARD_HORIZONS:
    print(f"\n  ── FORWARD {h}d ──")

    # Get EV + CI95 for each
    for lbl in ["CONJUNCIÓN-1", "CONJUNCIÓN-2", "CONJUNCIÓN-3",
                "VIX SOLO", "VVIX SOLO", "FG SOLO"]:
        a = analysis.get(lbl)
        if not a or h not in a["horizons"] or a["horizons"][h].get("n", 0) == 0:
            continue
        hr = a["horizons"][h]
        n = hr["n"]
        ev, ev_l, ev_h = hr["ev"], hr["ev_ci95"][0], hr["ev_ci95"][1]
        wr = hr["win_rate"] * 100
        wr_l, wr_h = hr["wr_ci95"][0] * 100, hr["wr_ci95"][1] * 100
        k = hr["kelly"] * 100 if hr["kelly"] != -999 else None
        quality = hr["sample_quality"]

        k_str = f"Kelly={k:.1f}%" if k is not None else "Kelly=N/A"
        print(f"    {lbl:<20} N={n:>3d}  WR={wr:.1f}% [{wr_l:.1f},{wr_h:.1f}]  "
              f"EV={ev:+.2f}% [{ev_l:+.2f},{ev_h:+.2f}]  {k_str}  [{quality}]")

# ── Bootstrap test: is CONJUNCIÓN-3 EV > best single? ──
print(f"\n  ── BOOTSTRAP TEST: CONJUNCIÓN-3 vs MEJOR ESTACIÓN SOLA ──")

for h in FORWARD_HORIZONS:
    c3 = analysis.get("CONJUNCIÓN-3")
    if not c3 or h not in c3["horizons"]:
        continue
    c3_vals = c3["df"][f"fwd_{h}d"].dropna().values

    # Find best single station at this horizon
    best_single = None
    best_single_name = None
    for name in ["VIX", "VVIX", "FG"]:
        lbl = f"{name} SOLO"
        a = analysis.get(lbl)
        if a and h in a["horizons"] and a["horizons"][h].get("n", 0) >= 5:
            ev_s = a["horizons"][h]["ev"]
            if best_single is None or ev_s > best_single:
                best_single = ev_s
                best_single_name = lbl

    if best_single_name and len(c3_vals) >= 3:
        best_vals = analysis[best_single_name]["df"][f"fwd_{h}d"].dropna().values

        # Bootstrap difference
        rng = np.random.default_rng(42)
        diffs = []
        for _ in range(2000):
            s3 = rng.choice(c3_vals, size=len(c3_vals), replace=True)
            sb = rng.choice(best_vals, size=len(best_vals), replace=True)
            diffs.append(s3.mean() - sb.mean())
        diffs = np.sort(diffs)
        lo = np.percentile(diffs, 2.5)
        hi = np.percentile(diffs, 97.5)
        p_pos = (np.array(diffs) > 0).mean()

        print(f"    {h}d: CONJUNCIÓN-3 (N={len(c3_vals)}) vs {best_single_name} (N={len(best_vals)})")
        print(f"         ΔEV = {c3_vals.mean() - best_vals.mean():+.2f}%  "
              f"CI95=[{lo:+.2f}%, {hi:+.2f}%]  P(Δ>0)={p_pos:.1%}")

# ── Similarly test CONJUNCIÓN-2 vs best single ──
print(f"\n  ── BOOTSTRAP TEST: CONJUNCIÓN-2 vs MEJOR ESTACIÓN SOLA ──")

for h in FORWARD_HORIZONS:
    c2 = analysis.get("CONJUNCIÓN-2")
    if not c2 or h not in c2["horizons"]:
        continue
    c2_vals = c2["df"][f"fwd_{h}d"].dropna().values

    best_single = None
    best_single_name = None
    for name in ["VIX", "VVIX", "FG"]:
        lbl = f"{name} SOLO"
        a = analysis.get(lbl)
        if a and h in a["horizons"] and a["horizons"][h].get("n", 0) >= 5:
            ev_s = a["horizons"][h]["ev"]
            if best_single is None or ev_s > best_single:
                best_single = ev_s
                best_single_name = lbl

    if best_single_name and len(c2_vals) >= 3:
        best_vals = analysis[best_single_name]["df"][f"fwd_{h}d"].dropna().values
        rng = np.random.default_rng(42)
        diffs = []
        for _ in range(2000):
            s2 = rng.choice(c2_vals, size=len(c2_vals), replace=True)
            sb = rng.choice(best_vals, size=len(best_vals), replace=True)
            diffs.append(s2.mean() - sb.mean())
        diffs = np.sort(diffs)
        lo = np.percentile(diffs, 2.5)
        hi = np.percentile(diffs, 97.5)
        p_pos = (np.array(diffs) > 0).mean()

        print(f"    {h}d: CONJUNCIÓN-2 (N={len(c2_vals)}) vs {best_single_name} (N={len(best_vals)})")
        print(f"         ΔEV = {c2_vals.mean() - best_vals.mean():+.2f}%  "
              f"CI95=[{lo:+.2f}%, {hi:+.2f}%]  P(Δ>0)={p_pos:.1%}")

# ── Trend: does signal quality improve monotonically with conjunction level? ──
print(f"\n  ── MONOTONICIDAD: ¿CONJUNCIÓN-1 < CONJUNCIÓN-2 < CONJUNCIÓN-3? ──")
for h in FORWARD_HORIZONS:
    evals = []
    for lvl in [1, 2, 3]:
        lbl = f"CONJUNCIÓN-{lvl}"
        a = analysis.get(lbl)
        if a and h in a["horizons"] and a["horizons"][h].get("n", 0) >= 3:
            evals.append((lvl, a["horizons"][h]["ev"], a["horizons"][h]["win_rate"],
                          a["horizons"][h]["n"]))
    if len(evals) >= 2:
        parts = []
        for lvl, ev, wr, n in evals:
            parts.append(f"C{lvl}: N={n} EV={ev:+.2f}% WR={wr*100:.1f}%")
        print(f"    {h}d: {' → '.join(parts)}")
        # Check monotonicity
        evs = [x[1] for x in evals]
        is_mono = all(evs[i] < evs[i+1] for i in range(len(evs)-1))
        print(f"         EV monótono: {'✓ SÍ' if is_mono else '✗ NO'}")

print(f"\n{'═'*80}")
print(f"  FIN — CONJUNCIÓN MIEDO")
print(f"{'═'*80}")