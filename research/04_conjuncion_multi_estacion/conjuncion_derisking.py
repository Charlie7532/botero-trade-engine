#!/usr/bin/env python3
"""
CONJUNCIÓN DE-RISKING — secuencia (fase) + cascade (dirección) + σ-overflow (colas)
===================================================================================
Hipótesis a validar (dato mata relato):
  La secuencia SHORT (macro-driven CAT1→CAT2→CAT3 + cuchillo CAT1→CAT3→CAT2) es un
  DETECTOR DE DE-RISKING. Combinada con:
    - cascade_conviction (dirección, IC +0.41) → convicción bear = c50 < 0 (t1_low)
    - σ-overflow (±3σ en D1/D2/D3 de las 11 estaciones, MULTI si 2+ dims)
  ... debería dar una señal SHORT más fuerte.

MÉTODO (entrada HONESTA en barra de señal, NO pivote):
1. Replica el clasificador de secuencias (validate_regimes_oos.py): permutación de
   activación CAT1/CAT2/CAT3 con entrada en la BARRA DE SEÑAL = la 3ª categoría que
   dispara su primer SIGMET (la permutación queda completa). Sin look-ahead.
2. Para cada señal de secuencia SHORT, lee cascade_conviction_50 (c50) del MISMO día
   → tercil t1_low/t2/t3 (umbrales del cascade_calibration.json, compositor real).
3. Para cada señal, lee σ-overflow del MISMO día (validate_overflow ±3σ; MULTI si
   2+ dimensiones de la MISMA estación — pitfall #92c).
4. 4 combinaciones × forward 20d/40d (y 5/10/40 completos):
   a) Secuencia SHORT sola
   b) SHORT + cascade bear (c50 < 0)
   c) SHORT + overflow (cualquier dimensión > ±3σ)
   d) SHORT + cascade bear + overflow (triple confirmación)
5. Por combinación: N, mean, CI95 bootstrap 3000, WR, PF, Kelly, wins/losses, wipeouts>20%.
6. Veredicto: ¿la conjunción mejora el edge SHORT? ¿triple confirmación CI95 sin cruzar 0?
7. Baseline SPY = TODOS los días en la ventana elegible.

Intérprete: PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/conjuncion_derisking.py
Salida: consola + data/research/conjuncion_derisking_report.json
"""

import sys
import json
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.sigma_overflow import (
    validate_overflow, STATION_MU_SIGMA,
)

RULES = ROOT / "backend/modules/entry_decision/domain/rules"

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — clasificador de secuencias (réplica EXACTA de validate_regimes_oos.py)
# ═══════════════════════════════════════════════════════════════════════════════
CATEGORIES = {
    1: {"name": "ECONOMIA",    "tickers": ["CREDIT_RATIO", "YIELD_SPREAD", "DXY"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "VVIX", "CBOE_PCR", "SKEW"]},
    3: {"name": "ACCION",      "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

# Secuencia SHORT = macro-driven (1,2,3) + cuchillo (1,3,2) — las 2 OP-SHORT del validador OOS
SHORT_PERMS = {(1, 2, 3), (1, 3, 2)}
PERM_LABELS = {
    (1, 2, 3): "macro-driven (CAT1→CAT2→CAT3)",
    (1, 3, 2): "cuchillo (CAT1→CAT3→CAT2)",
}

PCT_HIGH = 90
PCT_LOW = 10
D3_COMPRESSED = 0.7
STREAK = 3
WINDOW_DAYS = 30
FW_HORIZONS = [5, 10, 20, 40]
VERDICT_HORIZONS = [20, 40]
SCALES = ["zz25", "zz50", "zz75"]
N_BOOT = 3000
BOOT_SEED = 42
MIN_N = 20  # mínimo de entradas para veredicto (regla del proyecto)

# ── 4 combinaciones (definición central, réplica de los task items 4a-d) ──
# Las funciones mask se definen después de enriquecer las entradas con cascade/overflow.
# Aquí solo los labels; las masks se crean en el loop principal.
COMBO_NAMES = {
    "a_secuencia_short":       "a) Secuencia SHORT sola",
    "b_short_cascade_bear":    "b) SHORT + cascade bear (c50<0, t1_low o negativa)",
    "c_short_overflow":        "c) SHORT + overflow (cualquier dim >±3σ)",
    "d_triple_confirmacion":   "d) SHORT + cascade bear + overflow (triple)",
    "e_short_cascade_t3high":  "e) SHORT + cascade t3_high (voto bear alto) [signo correcto]",
    "f_short_t3high_overflow": "f) SHORT + cascade t3_high + overflow [triple signo correcto]",
}

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — cascade_conviction (réplica compositor real + coordinator)
# ═══════════════════════════════════════════════════════════════════════════════
GRUPO_A = {"vix", "bsi", "fg", "credit", "rotation"}

STATION_TICKER = {
    "credit": "CREDIT_RATIO", "yield_curve": "YIELD_SPREAD", "dxy": "DXY",
    "rotation": "ROTATION_INDEX", "vix": "VIX", "vvix": "VVIX", "pcr": "CBOE_PCR",
    "skew": "SKEW", "bsi": "S5TW", "sv5_turbulence": "SV5_TURBULENCE", "fg": "FG",
}

D1_BEARISH_BINS = {
    "CRISIS_SPIKE", "ELEVATED_PANIC", "EXTREME_VVIX", "ELEVATED_VVIX",
    "EXTREME_PUT_PANIC", "HIGH_PUT_PANIC", "EXTREME_FEAR", "FEAR",
    "CRISIS_TURBULENCE", "ELEVATED_TURBULENCE", "BLACK_SWAN_PARANOIA", "TAIL_PARANOIA",
    "CREDIT_CRISIS", "CREDIT_STRESS", "ELEVATED_CREDIT_STRESS",
    "DEEP_INVERSION", "MODERATE_INVERSION", "DEFENSIVE_CAPITULATION", "DEFENSIVE",
    "BREADTH_WASHED_OUT", "DOLLAR_SPIKE_CRISIS", "ELEVATED_DOLLAR_STRESS",
}
D1_BULLISH_BINS = {
    "DEEP_COMPLACENCY", "LOW_VOL", "EXTREME_COMPLACENCY", "LOW_VVIX",
    "EXTREME_CALL_HEAVY", "BULLISH_PCR", "EXTREME_GREED", "EUPHORIA",
    "QUIET_FLOW", "LOW_TURBULENCE", "LOW_TAIL_RISK", "DEEP_CREDIT_EASE", "CREDIT_EASE",
    "EXTREME_STEEPNING", "STEEPNING_CURVE", "AGGRESSIVE_ROTATION", "CYCLICAL_LEADERSHIP",
    "HYPER_EXPANSIVE_BREADTH", "EXPANSIVE_BREADTH", "DEEP_DOLLAR_CRUSH", "WEAK_DOLLAR",
}
D1_HALF_BEARISH_BINS = {"OVERSOLD_BREADTH"}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS ESTADÍSTICOS
# ═══════════════════════════════════════════════════════════════════════════════
def boot_ci_mean(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(arr.mean()), float(lo), float(hi)


def boot_ci_diff(a, b, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """CI95 bootstrap de la diferencia de medias (a - b)."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ma = rng.choice(a, size=(n_boot, len(a)), replace=True).mean(axis=1)
    mb = rng.choice(b, size=(n_boot, len(b)), replace=True).mean(axis=1)
    diffs = ma - mb
    lo, hi = np.percentile(diffs, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(a.mean() - b.mean()), float(lo), float(hi)


def short_trade_stats(fwd_returns):
    """Estadísticas de la OPERACIÓN SHORT (short SPY) sobre returns forward long.

    fwd_returns = returns forward de SPY (perspectiva long).
    Trade SHORT: retorno = -fwd. Win = SPY bajó (fwd<0). Loss = SPY subió (fwd>=0).
    Devuelve la métrica primaria (forward long) + la perspectiva SHORT.
    """
    fwd = np.asarray(fwd_returns, float)
    fwd = fwd[~np.isnan(fwd)]
    n = len(fwd)
    if n < 1:
        return None

    trade = -fwd  # short SPY
    wins = trade[trade > 0]      # short ganó (SPY cayó)
    losses = trade[trade <= 0]   # short perdió (SPY subió o plana)

    fwd_mean, fwd_lo, fwd_hi = boot_ci_mean(fwd)
    short_wr = float(np.mean(trade > 0))          # P(SPY baja) = down-win-rate

    gw = float(np.sum(wins)) if len(wins) else 0.0
    gl = float(abs(np.sum(losses))) if len(losses) else 0.0
    pf = gw / gl if gl > 0 else float("inf")

    avg_w = float(np.mean(wins)) if len(wins) else 0.0
    avg_l = float(abs(np.mean(losses))) if len(losses) else 0.0
    wlr = avg_w / avg_l if avg_l > 0 else float("inf")
    kelly = (short_wr - (1 - short_wr) / wlr) if (avg_l > 0 and wlr > 0) else float("nan")

    # wipeout SHORT = pérdida > 20% = SPY subió > +20%
    wipe = losses[losses < -0.20]

    return {
        "N": n,
        # — perspectiva long (métrica primaria de la hipótesis: negativo = edge short) —
        "fwd_mean": fwd_mean,
        "fwd_ci95": [fwd_lo, fwd_hi],
        # — perspectiva SHORT (operación real) —
        "short_wr": short_wr,
        "short_pf": None if np.isinf(pf) else float(pf),
        "short_kelly": None if (isinstance(kelly, float) and np.isnan(kelly)) else float(kelly),
        "wins": {
            "n": int(len(wins)),
            "mean": float(np.mean(wins)) if len(wins) else None,
            "median": float(np.median(wins)) if len(wins) else None,
            "p75": float(np.percentile(wins, 75)) if len(wins) >= 4 else None,
            "p90": float(np.percentile(wins, 90)) if len(wins) >= 10 else None,
            "max": float(np.max(wins)) if len(wins) else None,
        },
        "losses": {
            "n": int(len(losses)),
            "mean": float(np.mean(losses)) if len(losses) else None,
            "median": float(np.median(losses)) if len(losses) else None,
            "p25": float(np.percentile(losses, 25)) if len(losses) >= 4 else None,
            "p10": float(np.percentile(losses, 10)) if len(losses) >= 10 else None,
            "min": float(np.min(losses)) if len(losses) else None,
            "wipeouts_gt20pct": int(len(wipe)),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLASIFICADOR DE SECUENCIAS (réplica validate_regimes_oos.py)
# ═══════════════════════════════════════════════════════════════════════════════
def load_raw_series(store, tickers):
    series = {}
    for t in tickers:
        try:
            b = store.load_bars(t, "1d")
            if b is not None and len(b) > 0:
                c = b["close"].copy()
                c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
                c = c[~c.index.duplicated(keep="last")].sort_index().dropna()
                if len(c) > 0:
                    series[t] = c
        except Exception:
            pass
    return series


def compute_d1_d2_d3(series):
    df = pd.DataFrame({"val": series})
    df["d2"] = df["val"].diff(3)
    s2 = df["val"].rolling(2).std()
    s10 = df["val"].rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan)
    df["d3"] = d3.fillna(1.0)
    df["d1_pct"] = df["val"].expanding().rank(pct=True) * 100
    return df


def detect_sigmet(df, pct_high=PCT_HIGH, pct_low=PCT_LOW, d3_comp=D3_COMPRESSED, streak=STREAK):
    events = []
    prev_sign = None
    d2_streak = 0
    d3_streak = 0
    for row in df.itertuples():
        pct = row.d1_pct
        d2 = row.d2
        d3 = row.d3
        if pd.isna(pct) or pd.isna(d2):
            continue
        sign = 1 if d2 > 0 else (-1 if d2 < 0 else 0)
        if sign != 0:
            d2_streak = d2_streak + 1 if sign == prev_sign else 1
        else:
            d2_streak = 0
        d3_streak = d3_streak + 1 if (pd.notna(d3) and d3 < d3_comp) else 0
        sig_type = None
        if 70 <= pct < pct_high and d2_streak >= streak and d3_streak >= streak:
            sig_type = "ANTICIPACION_ALTA"
        elif pct_low < pct <= 30 and d2_streak >= streak and d3_streak >= streak and sign < 0:
            sig_type = "ANTICIPACION_BAJA"
        elif pct >= pct_high:
            sig_type = "EXTREMO_ALTO"
        elif pct <= pct_low:
            sig_type = "EXTREMO_BAJO"
        if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
            if sig_type is None:
                sig_type = "FLIP_D2"
        if sign != 0:
            prev_sign = sign
        if sig_type:
            events.append({"timestamp": row.Index, "type": sig_type})
    return pd.DataFrame(events)


def build_regime_entries(pivots_df, sigmets, window_days=WINDOW_DAYS):
    """Por cada pivote, permutación de 1ª activación + barra de señal (3ª activación)."""
    cat_ts = {}
    for cat_id in [1, 2, 3]:
        ev = sigmets.get(cat_id)
        if ev is None or len(ev) == 0:
            cat_ts[cat_id] = None
        else:
            cat_ts[cat_id] = np.sort(pd.to_datetime(ev["timestamp"]).values)

    entries = []
    for _, leg in pivots_df.iterrows():
        pivot_ts = pd.to_datetime(leg["start_timestamp"]).tz_localize(None).normalize()
        lo = np.datetime64(pivot_ts - pd.Timedelta(days=window_days))
        hi = np.datetime64(pivot_ts)
        first = {}
        for cat_id in [1, 2, 3]:
            arr = cat_ts[cat_id]
            if arr is None:
                continue
            i = np.searchsorted(arr, lo)
            if i < len(arr) and arr[i] <= hi:
                first[cat_id] = pd.Timestamp(arr[i])
        if len(first) == 3:
            ordered = sorted(first.items(), key=lambda x: x[1])
            perm = tuple(c for c, _ in ordered)
            signal_bar = ordered[-1][1]  # barra donde la permutación queda completa
            entries.append({
                "signal_bar": signal_bar,
                "perm": perm,
                "pivot": pivot_ts,
                "type": leg.get("start_type", None),
                "cat_times": first,
            })
    return entries


def fwd_from_bar(bar_ts, spy_idx_vals, spy_values, h):
    pos = int(np.searchsorted(spy_idx_vals, np.datetime64(bar_ts)))
    if pos >= len(spy_values):
        return None
    if pos + h < len(spy_values):
        return float(spy_values[pos + h] / spy_values[pos] - 1.0)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CARGA DE ESTACIONES (edges calibrados) + cascade + overflow
# ═══════════════════════════════════════════════════════════════════════════════
def classify(v, edges, labels):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    for i, e in enumerate(edges):
        if v < e:
            return labels[i]
    return labels[-1]


def load_edges(station):
    d = json.load(open(RULES / f"{station}_fact_store.json"))
    th = d["_documentation"]["dimension_thresholds_definition"]
    return {
        "edges_d1": th[f"{station}_edges_d1"],
        "labels_d1": th[f"{station}_labels_d1"],
    }


def load_station_series(store, name):
    """Series crudas + d1_label calibrado + d2/d3 (para overflow)."""
    ticker = STATION_TICKER[name]
    b = store.load_bars(ticker, "1d")["close"].dropna()
    b = b[~b.index.duplicated(keep="last")].sort_index()
    b.index = pd.to_datetime(b.index).tz_localize(None).normalize()
    edges = load_edges(name)
    df = pd.DataFrame({"val": b})
    df["d2"] = df["val"].diff(3)
    df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()
    df["d1_label"] = [classify(v, edges["edges_d1"], edges["labels_d1"]) for v in df["val"]]
    return df, edges


def d1_vote(station, label):
    if label is None:
        return None
    if label in D1_BEARISH_BINS:
        return -1.0
    if label in D1_HALF_BEARISH_BINS:
        return -0.5
    if label in D1_BULLISH_BINS:
        return +1.0
    return 0.0


def cascade_at_bar(bar_ts, station_dfs, legs25_cfg, calib):
    """cascade_conviction_50 (c50) + tercil en una barra, réplica del compositor."""
    conf_ts = legs25_cfg["confirmed_ns"]
    start_type_arr = legs25_cfg["start_type"]
    prev_ret_arr = legs25_cfg["prev_ret"]

    # último leg confirmado (confirmed_at <= bar_ts)
    ts_ns = np.datetime64(bar_ts).astype("datetime64[ns]").astype("int64")
    i = int(np.searchsorted(conf_ts, ts_ns, side="right")) - 1
    if i < 0:
        pivot_type = "MIN"
        prev_ret = None
    else:
        pivot_type = start_type_arr[i]
        prev_ret = prev_ret_arr[i]

    if pivot_type not in ("MIN", "MAX"):
        pivot_type = "MIN"

    type_cfg = calib.get("type_mask", {}).get(pivot_type, {
        "w_bear": 0.66, "w_dom": 0.34, "stations": ["vix", "bsi", "fg", "credit", "rotation"],
    })
    allowed = set(type_cfg.get("stations", ["vix", "bsi", "fg", "credit", "rotation"]))
    w_bear = float(type_cfg.get("w_bear", 0.66))
    w_dom = float(type_cfg.get("w_dom", 0.34))

    votes = {}
    for st in GRUPO_A:
        df = station_dfs[st]
        lab = df["d1_label"].asof(bar_ts)
        votes[st] = d1_vote(st, lab)

    masked = [v for k, v in votes.items() if k in allowed and v is not None]
    if masked:
        d1_bear_masked = float(sum(-v for v in masked if v < 0) / len(masked))
    else:
        d1_bear_masked = 0.0

    d1_mean = calib.get("d1_bear_5", {}).get("mean", 0.41)
    d1_std = calib.get("d1_bear_5", {}).get("std", 0.3206)
    dom25_mean = calib.get("domino_zz25", {}).get("mean", 0.0532)
    dom25_std = calib.get("domino_zz25", {}).get("std", 0.035)
    terc_edges = calib.get("tercile_edges", [-0.387, 0.302])

    val_dom25 = abs(prev_ret) if prev_ret is not None else dom25_mean
    z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0.0
    z_dom25 = (val_dom25 - dom25_mean) / dom25_std if dom25_std > 0 else 0.0

    c50 = w_bear * z_bear + w_dom * z_dom25
    if c50 < terc_edges[0]:
        tercile = "t1_low"
    elif c50 > terc_edges[1]:
        tercile = "t3_high"
    else:
        tercile = "t2_medium"

    return {
        "c50": float(c50),
        "tercile": tercile,
        "cascade_bear": bool(c50 < 0.0),
        "pivot_type": pivot_type,
        "d1_bear_masked": float(d1_bear_masked),
        "domino25": float(val_dom25),
    }


def overflow_at_bar(bar_ts, station_dfs):
    """σ-overflow en una barra: cualquier estación con alguna dim > ±3σ; MULTI si 2+ dims misma estación."""
    any_overflow = False
    multi = False
    detail = {}
    for name, df in station_dfs.items():
        d1v = df["val"].asof(bar_ts)
        d2v = df["d2"].asof(bar_ts)
        d3v = df["d3"].asof(bar_ts)
        d1v = None if (d1v is None or not np.isfinite(d1v)) else float(d1v)
        d2v = None if (d2v is None or not np.isfinite(d2v)) else float(d2v)
        d3v = None if (d3v is None or not np.isfinite(d3v)) else float(d3v)
        sd1, f1 = validate_overflow(name, "d1", d1v)
        sd2, f2 = validate_overflow(name, "d2", d2v)
        sd3, f3 = validate_overflow(name, "d3", d3v)
        flags = [f for f in (f1, f2, f3) if f]
        if len(flags) >= 2:
            multi = True
            any_overflow = True
        elif len(flags) == 1:
            any_overflow = True
        if flags:
            detail[name] = {"flags": flags,
                            "sigma_depth": {"d1": sd1, "d2": sd2, "d3": sd3}}
    return {
        "overflow_any": any_overflow,
        "overflow_multi": multi,
        "detail": detail,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("═" * 96)
    print("CONJUNCIÓN DE-RISKING — secuencia (fase) + cascade (dirección) + σ-overflow (colas)")
    print("Entrada HONESTA en barra de señal · forward 5/10/20/40d · bootstrap 3000")
    print("═" * 96)

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    # 1. SPY
    spy_raw = store.load_bars("SPY", "1d")["close"].copy()
    spy_raw.index = pd.to_datetime(spy_raw.index).tz_localize(None).normalize()
    spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
    spy_values = spy.values
    spy_idx_vals = spy.index.values
    print(f"SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} barras)")

    # 2. Series raw (clasificador de secuencias, 9 tickers reducidos) → SIGMETs
    sigmets = {}
    for cat_id, cat in CATEGORIES.items():
        series = load_raw_series(store, cat["tickers"])
        cat_events = []
        for t, s in series.items():
            df = compute_d1_d2_d3(s)
            ev = detect_sigmet(df)
            if len(ev) > 0:
                ev = ev.copy()
                ev["ticker"] = t
                cat_events.append(ev)
        if cat_events:
            sigmets[cat_id] = pd.concat(cat_events).sort_values("timestamp")
        else:
            sigmets[cat_id] = pd.DataFrame(columns=["timestamp", "type", "ticker"])
        print(f"CAT {cat_id} ({cat['name']}): {len(sigmets[cat_id])} SIGMETs "
              f"({len(series)} tickers)")

    # 3. Estaciones calibradas (11) — cascade vote + overflow
    station_dfs = {}
    for name in STATION_TICKER:
        try:
            df, edges = load_station_series(store, name)
            station_dfs[name] = df
        except Exception as e:
            print(f"  ⚠ estación {name}: {e}")
    print(f"Estaciones calibradas: {len(station_dfs)}/11")

    # 4. Cascade calibration + legs zz25 (para domino)
    calib = json.load(open(RULES / "cascade_calibration.json"))
    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs25_cfg = {
        "confirmed_ns": np.array([
            pd.to_datetime(l.confirmed_at_timestamp).tz_localize(None).normalize().value
            for l in legs25
        ]),
        "start_type": [l.start_type for l in legs25],
        "prev_ret": [l.prev_leg_return for l in legs25],
    }
    print(f"zz25 legs (domino): {len(legs25)}")

    # 5. Entradas por escala → barra de señal
    entries_by_scale = {}
    for scale in SCALES:
        pivots_df = repo.get_confirmed_legs_dataframe("SPY", scale)
        if pivots_df is None or len(pivots_df) == 0:
            entries_by_scale[scale] = []
            continue
        ents = build_regime_entries(pivots_df, sigmets)
        entries_by_scale[scale] = ents
        perm_counts = Counter(e["perm"] for e in ents)
        print(f"{scale}: {len(pivots_df)} legs → {len(ents)} entradas "
              f"({dict(sorted(perm_counts.items(), key=lambda x: -x[1]))})")

    store.close()

    all_signal_bars = [e["signal_bar"] for ents in entries_by_scale.values() for e in ents]
    if not all_signal_bars:
        print("⚠ SIN ENTRADAS — abortando")
        return
    eligible_start = min(all_signal_bars)
    eligible_end = max(all_signal_bars)
    print(f"\nVentana elegible: {eligible_start.date()} → {eligible_end.date()}")

    # 6. Baseline SPY — TODOS los días en la ventana elegible
    baseline = {}
    for h in FW_HORIZONS:
        rets = []
        for i in range(len(spy_values)):
            if not (eligible_start <= spy.index[i] <= eligible_end):
                continue
            if i + h < len(spy_values):
                rets.append(spy_values[i + h] / spy_values[i] - 1.0)
        arr = np.array(rets)
        mean, lo, hi = boot_ci_mean(arr)
        baseline[h] = {"N": len(arr), "mean": mean, "ci95": [lo, hi]}
        print(f"  baseline SPY {h:>2}d: {mean*100:+.2f}% CI95[{lo*100:+.2f},{hi*100:+.2f}] N={len(arr)}")

    # 7. Enriquecer entradas SHORT con cascade + overflow, medir combinaciones
    report = {"baseline": baseline, "combinations": {}, "scales": {}}
    verdict_rows = []

    for scale in SCALES:
        ents = entries_by_scale.get(scale, [])
        short_ents = [e for e in ents if e["perm"] in SHORT_PERMS]
        if not short_ents:
            continue

        # enriquecer cada entrada SHORT
        for e in short_ents:
            bar = e["signal_bar"]
            e["cascade"] = cascade_at_bar(bar, station_dfs, legs25_cfg, calib)
            e["overflow"] = overflow_at_bar(bar, station_dfs)

        # forward returns por entrada y horizonte
        fwd_by_entry = {h: [] for h in FW_HORIZONS}
        for e in short_ents:
            for h in FW_HORIZONS:
                r = fwd_from_bar(e["signal_bar"], spy_idx_vals, spy_values, h)
                fwd_by_entry[h].append(r)

        # composición MIN/MAX
        type_comp = Counter(e["type"] for e in short_ents if e.get("type"))
        perm_comp = Counter(e["perm"] for e in short_ents)

        # ── Combinaciones ──
        combos = {
            "a_secuencia_short": {
                "label": "a) Secuencia SHORT sola",
                "mask": lambda e: True,
            },
            "b_short_cascade_bear": {
                "label": "b) SHORT + cascade bear (c50<0)",
                "mask": lambda e: e["cascade"]["cascade_bear"],
            },
            "c_short_overflow": {
                "label": "c) SHORT + overflow (cualquier dim >±3σ)",
                "mask": lambda e: e["overflow"]["overflow_any"],
            },
            "d_triple_confirmacion": {
                "label": "d) SHORT + cascade bear + overflow",
                "mask": lambda e: e["cascade"]["cascade_bear"] and e["overflow"]["overflow_any"],
            },
            "e_short_cascade_t3high": {
                "label": "e) SHORT + cascade t3_high (voto bear alto)",
                "mask": lambda e: e["cascade"]["tercile"] == "t3_high",
            },
            "f_short_t3high_overflow": {
                "label": "f) SHORT + cascade t3_high + overflow",
                "mask": lambda e: e["cascade"]["tercile"] == "t3_high" and e["overflow"]["overflow_any"],
            },
        }

        report["scales"][scale] = {
            "N_short_entries": len(short_ents),
            "perm_composition": {PERM_LABELS.get(k, str(k)): v for k, v in perm_comp.items()},
            "type_composition": dict(type_comp),
            "combinations": {},
        }
        print(f"\n{'─' * 96}")
        print(f"ESCALA {scale} — Secuencia SHORT (macro-driven + cuchillo): {len(short_ents)} entradas "
              f"(comp MIN/MAX: {dict(type_comp)})")
        print(f"{'─' * 96}")

        for cname, ccfg in combos.items():
            c_entries = [e for e in short_ents if ccfg["mask"](e)]
            c_fwd = {h: [fwd_by_entry[h][i] for i, e in enumerate(short_ents)
                         if ccfg["mask"](e) and fwd_by_entry[h][i] is not None]
                     for h in FW_HORIZONS}
            report["scales"][scale]["combinations"][cname] = {
                "label": ccfg["label"], "N_entries": len(c_entries), "horizons": {},
            }
            print(f"\n  {ccfg['label']}  (N entradas = {len(c_entries)})")

            for h in FW_HORIZONS:
                arr = np.array([fwd_by_entry[h][i] for i, e in enumerate(short_ents)
                                if ccfg["mask"](e)], dtype=float)
                st = short_trade_stats(arr)
                if st is None or st["N"] == 0:
                    report["scales"][scale]["combinations"][cname]["horizons"][h] = None
                    continue
                st["excess_vs_baseline"] = float(st["fwd_mean"] - baseline[h]["mean"])
                report["scales"][scale]["combinations"][cname]["horizons"][h] = st
                verdict_rows.append({"scale": scale, "combo": cname, "horizon": h, **st})

            # print tabla para 20/40 (y 5/10 compacto)
            for h in FW_HORIZONS:
                st = report["scales"][scale]["combinations"][cname]["horizons"][h]
                if st is None:
                    continue
                ci = st["fwd_ci95"]
                kelly = st["short_kelly"]
                pf = st["short_pf"]
                k_s = f"{kelly:+.2f}" if kelly is not None else "  —  "
                p_s = f"{pf:.2f}" if pf is not None else "  ∞  "
                print(f"    {h:>2}d  N={st['N']:>4}  fwd={st['fwd_mean']*100:+6.2f}% "
                      f"CI95[{ci[0]*100:+6.2f},{ci[1]*100:+6.2f}]  "
                      f"downWR={st['short_wr']*100:>4.0f}%  PF={p_s}  Kelly={k_s}  "
                      f"wipe>20%={st['losses']['wipeouts_gt20pct']}")

        # ── Comparativa vs secuencia sola (diferencia de medias forward) ──
        print(f"\n  ── Δ vs Secuencia SHORT sola (forward 20/40d) ──")
        a_stats = report["scales"][scale]["combinations"]["a_secuencia_short"]["horizons"]
        for cname in ["b_short_cascade_bear", "c_short_overflow", "d_triple_confirmacion",
                       "e_short_cascade_t3high", "f_short_t3high_overflow"]:
            lbl = report["scales"][scale]["combinations"][cname]["label"]
            for h in VERDICT_HORIZONS:
                a_h = a_stats[h]
                c_h = report["scales"][scale]["combinations"][cname]["horizons"][h]
                if a_h is None or c_h is None or a_h["N"] < 3 or c_h["N"] < 3:
                    continue
                a_arr = np.array([fwd_by_entry[h][i] for i, e in enumerate(short_ents)
                                  if combos["a_secuencia_short"]["mask"](e)], dtype=float)
                c_arr = np.array([fwd_by_entry[h][i] for i, e in enumerate(short_ents)
                                  if combos[cname]["mask"](e)], dtype=float)
                diff, dlo, dhi = boot_ci_diff(c_arr, a_arr)
                sign = "MÁS BAJISTA" if diff < 0 else "MÁS ALCISTA"
                report["scales"][scale]["combinations"][cname]["horizons"][h]["diff_vs_a"] = {
                    "mean": diff, "ci95": [dlo, dhi],
                }
                print(f"    {lbl.split(')')[0]}) vs a) {h:>2}d: Δfwd={diff*100:+.2f}% "
                      f"CI95[{dlo*100:+.2f},{dhi*100:+.2f}]  → {sign}")

        # ── DIAGNÓSTICO: descomposición por tercil cascade (resuelve signo) ──
        print(f"\n  ── DIAGNÓSTICO: forward por tercil cascade_conviction (c50) ──")
        terc_labels = {"t1_low": "t1_low (c50<-0.387, convicción BAJA)",
                       "t2_medium": "t2_medium (neutral)",
                       "t3_high": "t3_high (c50>+0.302, convicción ALTA = voto bear alto)"}
        terc_split = {}
        for e in short_ents:
            t = e["cascade"]["tercile"]
            terc_split.setdefault(t, []).append(e)
        for t in ["t1_low", "t2_medium", "t3_high"]:
            ents_t = terc_split.get(t, [])
            if not ents_t:
                print(f"    {terc_labels[t]:<52} N=0")
                continue
            idxs_t = [i for i, e in enumerate(short_ents) if e["cascade"]["tercile"] == t]
            row = f"    {terc_labels[t]:<52}"
            for h in VERDICT_HORIZONS:
                arr = np.array([fwd_by_entry[h][i] for i in idxs_t], dtype=float)
                st = short_trade_stats(arr)
                if st is None or st["N"] == 0:
                    row += f"  {h}d N=0"
                    continue
                ci = st["fwd_ci95"]
                row += f"  {h}d N={st['N']:>3} fwd={st['fwd_mean']*100:+5.2f}%[{ci[0]*100:+.1f},{ci[1]*100:+.1f}]"
            print(row)
            report["scales"][scale]["cascade_tercile_split"] = report["scales"][scale].get(
                "cascade_tercile_split", {})
            report["scales"][scale]["cascade_tercile_split"][t] = {
                "N": len(ents_t),
                **{str(h): short_trade_stats(np.array(
                    [fwd_by_entry[h][i] for i in idxs_t], dtype=float))
                   for h in VERDICT_HORIZONS},
            }

        # alternativa de signo: "cascade bear = t3_high (voto bear alto)"
        idxs_t3 = [i for i, e in enumerate(short_ents) if e["cascade"]["tercile"] == "t3_high"]
        print(f"    ── ALT (signo opuesto): SHORT + cascade t3_high (voto bear alto) ──")
        for h in VERDICT_HORIZONS:
            arr = np.array([fwd_by_entry[h][i] for i in idxs_t3], dtype=float)
            st = short_trade_stats(arr)
            if st is None or st["N"] == 0:
                continue
            ci = st["fwd_ci95"]
            print(f"      {h:>2}d  N={st['N']:>4}  fwd={st['fwd_mean']*100:+6.2f}% "
                  f"CI95[{ci[0]*100:+6.2f},{ci[1]*100:+6.2f}]  downWR={st['short_wr']*100:>4.0f}%")

    # 8. Tabla de veredictos finales
    print("\n" + "═" * 96)
    print("VEREDICTO — ¿la conjunción mejora el edge SHORT?")
    print("═" * 96)
    for scale in SCALES:
        if scale not in report["scales"]:
            continue
        combos_r = report["scales"][scale]["combinations"]
        a20 = combos_r["a_secuencia_short"]["horizons"].get(20)
        a40 = combos_r["a_secuencia_short"]["horizons"].get(40)
        print(f"\n  {scale}  (Secuencia sola: N={a20['N'] if a20 else 0}, "
              f"fwd20={a20['fwd_mean']*100:+.2f}% [{a20['fwd_ci95'][0]*100:+.2f},{a20['fwd_ci95'][1]*100:+.2f}]"
              if a20 else f"  {scale}  (sin datos)")
        for cname, clabel in COMBO_NAMES.items():
            h20 = combos_r[cname]["horizons"].get(20)
            h40 = combos_r[cname]["horizons"].get(40)
            n20 = h20["N"] if h20 else 0
            n40 = h40["N"] if h40 else 0
            # ¿CI95 sin cruzar 0 (todo negativo)?
            ci20_neg = (h20 and h20["fwd_ci95"][1] < 0)
            ci40_neg = (h40 and h40["fwd_ci95"][1] < 0)
            verdict = "OP-SHORT" if (ci20_neg or ci40_neg) else ("INSUFICIENTE" if (n20 < MIN_N and n40 < MIN_N) else "ruido/débil")
            print(f"    {clabel:<42} N20={n20:>3} N40={n40:>3}  "
                  f"CI95_20_todo-neg={ci20_neg}  CI95_40_todo-neg={ci40_neg}  → {verdict}")

    # 9. Persistir JSON
    out = ROOT / "data/research" / "conjuncion_derisking_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON → {out}")


if __name__ == "__main__":
    main()
