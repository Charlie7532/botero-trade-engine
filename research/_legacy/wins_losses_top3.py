#!/usr/bin/env python3
"""
ESTUDIO WINS vs LOSSES — FG, VVIX, SKEW (top 3 ENTRY)
=======================================================
Para cada estación en su D1 extremo, medir 7 dimensiones sobre entradas LONG
en pivotes MIN (zz25), salida en siguiente MAX.

Estaciones: FG (EXTREME_FEAR), VVIX (EXTREME_VVIX), SKEW (LOW_TAIL_RISK)

7 DIMENSIONES:
A. Win rate + CI95 + N
B. Distribución WINS (magnitud, duración)
C. Distribución LOSSES (magnitud, maxDD, wipeouts >20%)
D. Costo/beneficio (profit factor, Kelly, EV)
E. Rachas de pérdidas
F. Timing vs zigzag: anticipada, en_pivote, retrasada + costo
G. Cuchillo cayendo: drawdown >5% antes del pivote + ¿qué lo advirtió?

⚠️ Usar state_key del METAR (D1__D2__D3). D3 = std(2)/std(10).
⚠️ NO promediar sin separar wins/losses.
⚠️ CI95 bootstrap 2000 iter.
"""

import sys, json, os
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

# ── Helpers ────────────────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for mean of array. Returns (mean, lo, hi)."""
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

def compute_d2_d3(s):
    """D2 = diff(3d), D3 = std(2d)/std(10d) — per pitfall #46 correct formula."""
    d2 = s.diff(3)
    s2 = s.rolling(2).std()
    s10 = s.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3

# ── Load Data ──────────────────────────────────────────────────────────────

print("═══ CARGANDO DATOS ═══")
store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# SPY
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_prices = dict(zip(spy.index, spy.values))

print(f"  SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} bars)")

# Zigzag legs zz25
legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)
print(f"  zz25 pivots: {len(legs25)}")

# Build pivot lookups
# For each date, what pivots start on that date?
min_pivots_by_date = defaultdict(list)  # date -> [(timestamp, price, type)]
max_pivots_by_date = defaultdict(list)
all_pivots = []  # sorted list of (date, type, price)

for l in legs25:
    d = pd.to_datetime(l.start_timestamp).normalize()
    all_pivots.append((d, l.start_type, l.start_price))
    if l.start_type == "MIN":
        min_pivots_by_date[d].append((l.start_timestamp, l.start_price, l.start_type))
    else:
        max_pivots_by_date[d].append((l.start_timestamp, l.start_price, l.start_type))

all_pivots.sort(key=lambda x: x[0])
pivot_dates = sorted(set(d for d, _, _ in all_pivots))

# ── Per-station analysis ───────────────────────────────────────────────────

STATIONS = [
    {
        "name": "FG",
        "ticker": "FG",
        "adapter": FGLookupAdapter(),
        "extreme_d1": ["EXTREME_FEAR"],  # miedo extremo → comprar en MIN
        "method": "lookup_fg_guidance",
    },
    {
        "name": "VVIX",
        "ticker": "VVIX",
        "adapter": VVIXLookupAdapter(),
        "extreme_d1": ["EXTREME_VVIX"],  # VVIX extremo → entrada long en MIN
        "method": "lookup_vvix_guidance",
    },
    {
        "name": "SKEW",
        "ticker": "SKEW",
        "adapter": SkewLookupAdapter(),
        "extreme_d1": ["LOW_TAIL_RISK"],  # skew bajo → entrada long en MIN
        "method": "lookup_skew_guidance",
    },
]

all_results = {}

for station in STATIONS:
    name = station["name"]
    ticker = station["ticker"]
    adapter = station["adapter"]
    extreme_d1 = station["extreme_d1"]
    method_name = station["method"]
    lookup_fn = getattr(adapter, method_name)

    print(f"\n{'═'*80}")
    print(f"  {name} — D1 extremo: {extreme_d1}")
    print(f"{'═'*80}")

    # Load station OHLCV
    raw = store.load_bars(ticker, "1d")["close"].copy()
    raw.index = pd.to_datetime(raw.index).normalize()
    s = raw[~raw.index.duplicated(keep="last")].sort_index()
    # Align with SPY
    common_dates = sorted(set(s.index) & set(spy.index))
    s = s.loc[common_dates]
    spy_aligned = spy.loc[common_dates]
    print(f"  {ticker}: {s.index[0].date()} → {s.index[-1].date()} ({len(s)} bars aligned)")

    # Compute D2, D3
    d2, d3 = compute_d2_d3(s)

    # Find all bars in extreme D1
    extreme_bars = []  # list of (date_idx, date, val, vel, vol, state_key, d1, d2_bin, d3_bin)
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
            extreme_bars.append((i, dt, val, vel, vol, g.state_key, d1_bin, d2_bin, d3_bin))

    print(f"  Barras en D1 extremo: {len(extreme_bars)}")

    if len(extreme_bars) == 0:
        print(f"  ⚠️ Sin barras extremas para {name}. Saltando.")
        all_results[name] = None
        continue

    # For each extreme bar, find next MIN pivot
    signals_to_pivots = []  # list of (signal_bar, min_pivot_date, min_pivot_price)
    pivot_to_signal = {}  # pivot_date -> (signal_bar_info)

    for sbi, sdt, sval, svel, svol, skey, sd1, sd2, sd3 in extreme_bars:
        # Find the nearest MIN pivot on or after this bar's date
        # Look through all_pivots
        best_min = None
        for pd_d, ptype, pprice in all_pivots:
            if pd_d >= sdt and ptype == "MIN":
                best_min = (pd_d, pprice)
                break
        if best_min is None:
            continue
        pivot_date, pivot_price = best_min
        # Keep only the EARLIEST signal for each pivot
        if pivot_date not in pivot_to_signal or sdt < pivot_to_signal[pivot_date][1]:
            pivot_to_signal[pivot_date] = (
                {"date": sdt, "val": sval, "vel": svel, "vol": svol,
                 "state_key": skey, "d1": sd1, "d2": sd2, "d3": sd3},
                sdt,
                pivot_price,
                pivot_date,
            )

    print(f"  Señales únicas (dedup por pivote): {len(pivot_to_signal)}")

    # For each unique signal→pivot, build the trade
    trades = []
    for pivot_date, (sig, sig_date, pivot_price, pdate) in sorted(pivot_to_signal.items(), key=lambda x: x[0]):
        # Find next MAX pivot after this MIN pivot
        exit_max = None
        for pd_d, ptype, pprice in all_pivots:
            if pd_d > pivot_date and ptype == "MAX":
                exit_max = (pd_d, pprice)
                break
        if exit_max is None:
            # Use last price date as exit
            last_date = max(spy.index)
            exit_date = last_date
            exit_price = float(spy.loc[last_date]) if last_date in spy.index else pivot_price
        else:
            exit_date, exit_price = exit_max

        # Compute return
        ret_pct = (exit_price / pivot_price - 1) * 100

        # Duration
        dur = (exit_date - pivot_date).days
        if dur <= 0:
            dur = 1

        # Signal-to-pivot: days from signal bar to pivot
        sig_to_pivot_days = (pivot_date - sig_date).days

        # Drawdown from signal bar to pivot (cuchillo cayendo)
        signal_spy_price = float(spy_aligned.loc[sig_date]) if sig_date in spy_aligned.index else pivot_price
        # Find min SPY price between signal_date and pivot_date
        spy_window = spy[(spy.index >= sig_date) & (spy.index <= pivot_date)]
        if len(spy_window) > 0:
            min_price_in_window = float(spy_window.min())
            dd_from_signal = (min_price_in_window / signal_spy_price - 1) * 100
            # Drawdown at pivot vs signal
            dd_at_pivot = (pivot_price / signal_spy_price - 1) * 100
        else:
            dd_from_signal = 0.0
            dd_at_pivot = 0.0

        # Intra-trade max drawdown (from entry to worst point before exit)
        trade_spy = spy[(spy.index >= pivot_date) & (spy.index <= exit_date)]
        if len(trade_spy) > 1:
            entry_px = float(trade_spy.iloc[0])
            lowest_px = float(trade_spy.min())
            intra_dd = (lowest_px / entry_px - 1) * 100  # negative = drawdown
        else:
            intra_dd = 0.0

        trades.append({
            "signal_date": sig_date,
            "signal_state_key": sig["state_key"],
            "signal_d2": sig["d2"],
            "signal_d3": sig["d3"],
            "entry_date": pivot_date,
            "entry_price": pivot_price,
            "exit_date": exit_date,
            "exit_price": exit_price,
            "return_pct": ret_pct,
            "duration_days": dur,
            "sig_to_pivot_days": sig_to_pivot_days,
            "dd_from_signal": dd_from_signal,
            "dd_at_pivot": dd_at_pivot,
            "intra_dd": intra_dd,
        })

    df_trades = pd.DataFrame(trades)
    n_trades = len(df_trades)
    print(f"  Trades válidos: {n_trades}")

    if n_trades == 0:
        print(f"  ⚠️ Sin trades para {name}.")
        all_results[name] = None
        continue

    # Split wins/losses
    returns = df_trades["return_pct"].values
    wins_mask = returns > 0
    losses_mask = returns <= 0
    wins_ret = returns[wins_mask]
    losses_ret = returns[losses_mask]
    n_wins = wins_mask.sum()
    n_losses = losses_mask.sum()

    # ════════════════════════════════════════════════════════════════════════
    # A. WIN RATE + CI95 + N
    # ════════════════════════════════════════════════════════════════════════
    win_rate = n_wins / n_trades if n_trades > 0 else 0
    # Bootstrap CI95 for win rate
    rng_wr = np.random.default_rng(42)
    wr_boot = []
    for _ in range(2000):
        sample = rng_wr.choice(returns, size=len(returns), replace=True)
        wr_boot.append((sample > 0).mean())
    wr_boot = np.sort(wr_boot)
    wr_lo = np.percentile(wr_boot, 2.5)
    wr_hi = np.percentile(wr_boot, 97.5)

    # ════════════════════════════════════════════════════════════════════════
    # B. DISTRIBUCIÓN WINS
    # ════════════════════════════════════════════════════════════════════════
    win_dur = df_trades.loc[wins_mask, "duration_days"].values
    b_ret = {}
    b_dur = {}
    if len(wins_ret) > 0:
        for pct in [25, 50, 75, 90]:
            b_ret[f"P{pct}"] = np.percentile(wins_ret, pct)
            b_dur[f"P{pct}"] = np.percentile(win_dur, pct) if len(win_dur) > 0 else np.nan
        b_ret["max"] = wins_ret.max()
        b_dur["max_dur"] = win_dur.max() if len(win_dur) > 0 else np.nan
        # Bootstrap CI95 for median win
        _, wr_ci_lo, wr_ci_hi = boot_ci_median(wins_ret)
    else:
        b_ret = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan, "max": np.nan}
        b_dur = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan, "max_dur": np.nan}
        wr_ci_lo, wr_ci_hi = np.nan, np.nan

    # ════════════════════════════════════════════════════════════════════════
    # C. DISTRIBUCIÓN LOSSES (magnitud, maxDD, wipeouts >20%)
    # ════════════════════════════════════════════════════════════════════════
    loss_dur = df_trades.loc[losses_mask, "duration_days"].values
    c_loss = {}
    if len(losses_ret) > 0:
        for pct in [25, 50, 75, 90]:
            c_loss[f"P{pct}"] = np.percentile(losses_ret, pct)
        c_loss["min"] = losses_ret.min()  # worst loss (most negative)
        c_loss["max_dd"] = df_trades.loc[losses_mask, "intra_dd"].min() if len(df_trades.loc[losses_mask]) > 0 else np.nan  # worst intra-trade DD
        c_loss["avg_intra_dd"] = df_trades.loc[losses_mask, "intra_dd"].mean() if len(df_trades.loc[losses_mask]) > 0 else np.nan
        c_loss["wipeouts_gt20"] = (losses_ret < -20).sum()
        c_loss["wipeouts_gt20_pct"] = (losses_ret < -20).mean() * 100 if len(losses_ret) > 0 else 0
    else:
        c_loss = {"P25": np.nan, "P50": np.nan, "P75": np.nan, "P90": np.nan,
                  "min": np.nan, "max_dd": np.nan, "wipeouts_gt20": 0, "wipeouts_gt20_pct": 0}

    # ════════════════════════════════════════════════════════════════════════
    # D. COSTO/BENEFICIO (profit factor, Kelly, EV)
    # ════════════════════════════════════════════════════════════════════════
    total_wins = wins_ret.sum() if len(wins_ret) > 0 else 0
    total_losses = abs(losses_ret.sum()) if len(losses_ret) > 0 else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else np.inf

    avg_win = wins_ret.mean() if len(wins_ret) > 0 else 0
    avg_loss = abs(losses_ret.mean()) if len(losses_ret) > 0 else 0
    kelly = win_rate - (1 - win_rate) / (avg_win / avg_loss) if avg_loss > 0 else win_rate
    # EV (expected value per trade)
    ev, ev_lo, ev_hi = boot_ci(returns)

    # ════════════════════════════════════════════════════════════════════════
    # E. RACHAS DE PÉRDIDAS
    # ════════════════════════════════════════════════════════════════════════
    streaks = []
    current_streak = 0
    all_streaks = []
    for r in returns:
        if r <= 0:
            current_streak += 1
        else:
            if current_streak > 0:
                all_streaks.append(current_streak)
            current_streak = 0
    if current_streak > 0:
        all_streaks.append(current_streak)
    loss_streaks = np.array(all_streaks) if all_streaks else np.array([0])

    # ════════════════════════════════════════════════════════════════════════
    # F. TIMING vs ZIGZAG
    # ════════════════════════════════════════════════════════════════════════
    sig_days = df_trades["sig_to_pivot_days"].values
    # anticipada: sig_to_pivot < 0 (signal BEFORE pivot — shouldn't happen since we look forward)
    # Actually: 0 = same day, >0 = signal days before pivot
    # "Anticipada" means signal arrived BEFORE the pivot (positive sig_to_pivot_days)
    # "En pivote" means signal same day as pivot
    # "Retrasada" means signal AFTER pivot (negative, shouldn't happen with our logic)
    anticipada = (sig_days > 0).sum()
    en_pivote = (sig_days == 0).sum()
    retrasada = (sig_days < 0).sum()

    # Costo: drawdown from signal to pivot for anticipada entries
    anticipada_mask = sig_days > 0
    if anticipada_mask.sum() > 0:
        dd_anticipada = df_trades.loc[anticipada_mask, "dd_at_pivot"].values
        costo_anticipada_mean, costo_lo, costo_hi = boot_ci(dd_anticipada)
    else:
        costo_anticipada_mean = costo_lo = costo_hi = np.nan

    # Return difference: anticipada vs en_pivote
    ret_anticipada = returns[anticipada_mask] if anticipada_mask.sum() > 0 else np.array([])
    ret_en_pivote = returns[sig_days == 0] if en_pivote > 0 else np.array([])

    # ════════════════════════════════════════════════════════════════════════
    # G. CUCHILLO CAYENDO: drawdown >5% antes del pivote
    # ════════════════════════════════════════════════════════════════════════
    dd_from_signal_arr = df_trades["dd_from_signal"].values
    cuchillo_mask = dd_from_signal_arr < -5  # >5% DD from signal to pivot
    n_cuchillo = cuchillo_mask.sum()
    cuchillo_pct = n_cuchillo / n_trades * 100 if n_trades > 0 else 0

    # For cuchillo trades, what did D2/D3 look like at signal?
    cuchillo_d2 = df_trades.loc[cuchillo_mask, "signal_d2"].values if n_cuchillo > 0 else np.array([])
    cuchillo_d3 = df_trades.loc[cuchillo_mask, "signal_d3"].values if n_cuchillo > 0 else np.array([])

    # Non-cuchillo D2/D3 for comparison
    no_cuchillo_mask = ~cuchillo_mask
    no_cuchillo_d2 = df_trades.loc[no_cuchillo_mask, "signal_d2"].values if no_cuchillo_mask.sum() > 0 else np.array([])
    no_cuchillo_d3 = df_trades.loc[no_cuchillo_mask, "signal_d3"].values if no_cuchillo_mask.sum() > 0 else np.array([])

    # ── Store results ──
    all_results[name] = {
        "n_trades": n_trades,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": win_rate,
        "win_rate_ci95": (wr_lo, wr_hi),
        # B
        "wins_return": b_ret,
        "wins_duration": b_dur,
        "wins_median_ci95": (wr_ci_lo, wr_ci_hi),
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
        "max_streak": loss_streaks.max() if len(loss_streaks) > 0 else 0,
        "mean_streak": loss_streaks.mean() if len(loss_streaks) > 0 else 0,
        "n_streaks": len(loss_streaks),
        # F
        "anticipada": anticipada,
        "en_pivote": en_pivote,
        "retrasada": retrasada,
        "costo_anticipada_mean": costo_anticipada_mean,
        "costo_anticipada_ci95": (costo_lo, costo_hi),
        "ret_anticipada_mean": ret_anticipada.mean() if len(ret_anticipada) > 0 else np.nan,
        "ret_en_pivote_mean": ret_en_pivote.mean() if len(ret_en_pivote) > 0 else np.nan,
        # G
        "n_cuchillo": n_cuchillo,
        "cuchillo_pct": cuchillo_pct,
        "cuchillo_d2": cuchillo_d2,
        "cuchillo_d3": cuchillo_d3,
        "no_cuchillo_d2": no_cuchillo_d2,
        "no_cuchillo_d3": no_cuchillo_d3,
        # Raw data
        "df_trades": df_trades,
    }

store.close()

# ══════════════════════════════════════════════════════════════════════════════
# REPORTE POR ESTACIÓN
# ══════════════════════════════════════════════════════════════════════════════

print("\n\n")
print("╔" + "═" * 78 + "╗")
print("║" + "  ESTUDIO WINS vs LOSSES — FG · VVIX · SKEW (top 3 ENTRY)".center(78) + "║")
print("╠" + "═" * 78 + "╣")
print("║" + "  Entrada: LONG en pivote MIN (zz25). Salida: siguiente MAX.".center(78) + "║")
print("║" + "  CI95: bootstrap 2000 iter. D3 = std(2)/std(10).".center(78) + "║")
print("║" + "  Escala: state_key METAR (D1__D2__D3).".center(78) + "║")
print("╚" + "═" * 78 + "╝")

for name, r in all_results.items():
    if r is None:
        print(f"\n{'─'*80}\n  {name}: SIN DATOS (sin barras extremas o sin trades)\n{'─'*80}")
        continue

    extreme_label = {"FG": "EXTREME_FEAR", "VVIX": "EXTREME_VVIX", "SKEW": "LOW_TAIL_RISK"}[name]

    print(f"\n{'═'*80}")
    print(f"  {name} — D1 extremo: {extreme_label}")
    print(f"{'═'*80}")

    # ── A. WIN RATE ──
    print(f"\n  ── A. WIN RATE ──")
    print(f"    Trades totales:    {r['n_trades']}")
    print(f"    Wins:              {r['n_wins']}")
    print(f"    Losses:            {r['n_losses']}")
    print(f"    Win rate:          {r['win_rate']*100:.1f}%  CI95=[{r['win_rate_ci95'][0]*100:.1f}%, {r['win_rate_ci95'][1]*100:.1f}%]")

    # ── B. DISTRIBUCIÓN WINS ──
    print(f"\n  ── B. DISTRIBUCIÓN WINS (N={r['n_wins']}) ──")
    if r['n_wins'] > 0:
        br = r['wins_return']
        bd = r['wins_duration']
        print(f"    Magnitud (%):      P25={br['P25']:+.2f}%  P50={br['P50']:+.2f}%  P75={br['P75']:+.2f}%  P90={br['P90']:+.2f}%  max={br['max']:+.2f}%")
        print(f"    Mediana CI95:      [{r['wins_median_ci95'][0]:+.2f}%, {r['wins_median_ci95'][1]:+.2f}%]")
        print(f"    Duración (días):   P25={bd['P25']:.0f}  P50={bd['P50']:.0f}  P75={bd['P75']:.0f}  P90={bd['P90']:.0f}  max={bd['max_dur']:.0f}")
    else:
        print(f"    (sin wins)")

    # ── C. DISTRIBUCIÓN LOSSES ──
    print(f"\n  ── C. DISTRIBUCIÓN LOSSES (N={r['n_losses']}) ──")
    if r['n_losses'] > 0:
        cl = r['losses_return']
        print(f"    Magnitud (%):      P25={cl['P25']:+.2f}%  P50={cl['P50']:+.2f}%  P75={cl['P75']:+.2f}%  P90={cl['P90']:+.2f}%  min={cl['min']:+.2f}%")
        print(f"    Max DD intra-trade: {cl['max_dd']:+.2f}%  (avg={cl['avg_intra_dd']:+.2f}%)")
        print(f"    Wipeouts (>20%):   {cl['wipeouts_gt20']} ({cl['wipeouts_gt20_pct']:.0f}% de losses)")
    else:
        print(f"    (sin losses)")

    # ── D. COSTO/BENEFICIO ──
    print(f"\n  ── D. COSTO/BENEFICIO ──")
    print(f"    Profit Factor:     {r['profit_factor']:.2f}")
    print(f"    Kelly:             {r['kelly']:.1%}")
    print(f"    EV (por trade):    {r['ev']:+.2f}%  CI95=[{r['ev_ci95'][0]:+.2f}%, {r['ev_ci95'][1]:+.2f}%]")
    print(f"    Avg Win:           {r['avg_win']:+.2f}%")
    print(f"    Avg Loss:          {r['avg_loss']:.2f}%  (magnitud)")
    print(f"    Win/Loss ratio:    {r['avg_win']/r['avg_loss']:.2f}" if r['avg_loss'] > 0 else f"    Win/Loss ratio:    ∞")

    # ── E. RACHAS ──
    print(f"\n  ── E. RACHAS DE PÉRDIDAS ──")
    ls = r['loss_streaks']
    print(f"    Rachas totales:    {r['n_streaks']}")
    print(f"    Máxima racha:      {r['max_streak']}")
    print(f"    Media racha:       {r['mean_streak']:.1f}")
    if len(ls) > 0:
        print(f"    Distribución:      P50={np.median(ls):.0f}  P75={np.percentile(ls,75):.0f}  P90={np.percentile(ls,90):.0f}  max={ls.max()}")
        streak_counts = Counter(ls)
        print(f"    Frecuencia:        " + " | ".join(f"{k}×{v}" for k, v in sorted(streak_counts.items())))

    # ── F. TIMING vs ZIGZAG ──
    print(f"\n  ── F. TIMING vs ZIGZAG ──")
    print(f"    Anticipada (>0d):  {r['anticipada']} ({r['anticipada']/r['n_trades']*100:.0f}%)")
    print(f"    En pivote (0d):    {r['en_pivote']} ({r['en_pivote']/r['n_trades']*100:.0f}%)")
    print(f"    Retrasada (<0d):   {r['retrasada']} ({r['retrasada']/r['n_trades']*100:.0f}%)")
    if not np.isnan(r['costo_anticipada_mean']):
        print(f"    Costo drawdown     {r['costo_anticipada_mean']:+.2f}%  CI95=[{r['costo_anticipada_ci95'][0]:+.2f}%, {r['costo_anticipada_ci95'][1]:+.2f}%]")
    if not np.isnan(r['ret_anticipada_mean']):
        print(f"    Ret anticipada:    {r['ret_anticipada_mean']:+.2f}%  vs en_pivote: {r['ret_en_pivote_mean']:+.2f}%")

    # ── G. CUCHILLO CAYENDO ──
    print(f"\n  ── G. CUCHILLO CAYENDO (DD >5% señal→pivote) ──")
    print(f"    Casos:             {r['n_cuchillo']} / {r['n_trades']} ({r['cuchillo_pct']:.0f}%)")
    if r['n_cuchillo'] > 0:
        cd2 = r['cuchillo_d2']
        cd3 = r['cuchillo_d3']
        ncd2 = r['no_cuchillo_d2']
        ncd3 = r['no_cuchillo_d3']
        print(f"    D2 en cuchillo:    {cd2}")
        print(f"    D3 en cuchillo:    {cd3}")
        if len(ncd2) > 0:
            print(f"    D2 NO cuchillo:    contador={Counter(ncd2).most_common(3)}")
        if len(ncd3) > 0:
            print(f"    D3 NO cuchillo:    contador={Counter(ncd3).most_common(3)}")
    print(f"    ¿Advierte D2/D3?   Vea distribuciones arriba — comparar cuchillo vs no-cuchillo")

    # ── Trade-level detail ──
    print(f"\n  ── DETALLE DE TRADES (primeros 12) ──")
    detail_cols = ["signal_date", "signal_state_key", "entry_date", "exit_date",
                   "return_pct", "duration_days", "sig_to_pivot_days", "dd_from_signal"]
    for i, row in r["df_trades"][detail_cols].head(12).iterrows():
        print(f"    {str(row['signal_date'])[:10]} | {row['signal_state_key']:<45} | "
              f"ent={str(row['entry_date'])[:10]} exit={str(row['exit_date'])[:10]} | "
              f"ret={row['return_pct']:+.2f}% | dur={row['duration_days']:>3d}d | "
              f"sig2piv={row['sig_to_pivot_days']:>3d}d | dd={row['dd_from_signal']:+.2f}%")

print(f"\n{'═'*80}")
print(f"  FIN DEL ESTUDIO")
print(f"{'═'*80}")

# ══════════════════════════════════════════════════════════════════════════════
# TABLA RESUMEN COMPARATIVA
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n\n{'═'*80}")
print(f"  TABLA RESUMEN — FG vs VVIX vs SKEW")
print(f"{'═'*80}")
print(f"  {'Métrica':<30} {'FG (EXTREME_FEAR)':<25} {'VVIX (EXTREME_VVIX)':<25} {'SKEW (LOW_TAIL_RISK)':<25}")
print(f"  {'─'*30} {'─'*25} {'─'*25} {'─'*25}")

for label, key, fmt in [
    ("N trades", "n_trades", "d"),
    ("Win rate", "win_rate", ".1%"),
    ("WR CI95 lo", "win_rate_ci95_lo", ".1%"),
    ("WR CI95 hi", "win_rate_ci95_hi", ".1%"),
    ("Mediana win", "wins_return_med", ".2f"),
    ("P90 win", "wins_return_p90", ".2f"),
    ("Max win", "wins_return_max", ".2f"),
    ("Duración mediana (d)", "wins_dur_med", ".0f"),
    ("Profit Factor", "profit_factor", ".2f"),
    ("Kelly", "kelly", ".1%"),
    ("EV por trade", "ev", ".2f"),
    ("Anticipada %", "anticipada_pct", ".0%"),
    ("Costo anticipada", "costo_anticipada_mean", ".2f"),
    ("Cuchillo %", "cuchillo_pct", ".0f"),
]:
    vals = []
    for name, r in all_results.items():
        if r is None:
            vals.append("—")
            continue
        if key == "n_trades":
            vals.append(f"{r['n_trades']}")
        elif key == "win_rate":
            vals.append(f"{r['win_rate']*100:.1f}%")
        elif key == "win_rate_ci95_lo":
            vals.append(f"{r['win_rate_ci95'][0]*100:.1f}%")
        elif key == "win_rate_ci95_hi":
            vals.append(f"{r['win_rate_ci95'][1]*100:.1f}%")
        elif key == "wins_return_med":
            vals.append(f"{r['wins_return']['P50']:+.2f}%" if r['n_wins'] > 0 else "n/a")
        elif key == "wins_return_p90":
            vals.append(f"{r['wins_return']['P90']:+.2f}%" if r['n_wins'] > 0 else "n/a")
        elif key == "wins_return_max":
            vals.append(f"{r['wins_return']['max']:+.2f}%" if r['n_wins'] > 0 else "n/a")
        elif key == "wins_dur_med":
            vals.append(f"{r['wins_duration']['P50']:.0f}" if r['n_wins'] > 0 else "n/a")
        elif key == "profit_factor":
            vals.append(f"{r['profit_factor']:.1f}")
        elif key == "kelly":
            vals.append(f"{r['kelly']*100:.1f}%")
        elif key == "ev":
            vals.append(f"{r['ev']:+.2f}%")
        elif key == "anticipada_pct":
            vals.append(f"{r['anticipada']/r['n_trades']*100:.0f}%")
        elif key == "costo_anticipada_mean":
            vals.append(f"{r['costo_anticipada_mean']:+.2f}%" if not np.isnan(r['costo_anticipada_mean']) else "n/a")
        elif key == "cuchillo_pct":
            vals.append(f"{r['cuchillo_pct']:.0f}%")
        else:
            vals.append("?")
    print(f"  {label:<30} {vals[0]:<25} {vals[1]:<25} {vals[2]:<25}")