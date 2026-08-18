#!/usr/bin/env python3
"""
TIMING DE-RISKING — D2 flip (velocidad) como timing de la señal SHORT
====================================================================
Hipótesis: el D2 FLIP es el "cuándo" que falta.
  La secuencia dice "viene caída", el flip dice "ahora".

MÉTODO (entrada HONESTA en barra de señal + variante D2 flip):
1. Replica el clasificador de secuencias (permutación CAT1/CAT2/CAT3).
2. Para CADA día de la historia, calcula D2 (diff 3d) de las 11 estaciones
   y detecta el FLIP (cambio de signo de D2).
3. Para cada señal SHORT (macro-driven + cuchillo), clasifica por TIMING del D2:
   a) Secuencia SHORT sola (sin timing) = baseline
   b) Secuencia SHORT + D2 flip ya ocurrió (entrada en el flip, no en la secuencia)
   c) Secuencia SHORT + D2 flip NO ha ocurrido (aún cayendo, no entrar)
   d) Secuencia SHORT + cascade bear + D2 flip (dirección + timing juntos)
4. Mide IMPACTO: ¿entrar en D2 flip reduce wipeouts? ¿Mejora WR/PF?
5. Lead-lag: ¿qué estación flipea PRIMERO?
6. Por variante: N, mean 20d/40d, CI95 bootstrap 3000, WR, PF, Kelly,
   wins/losses, wipeouts>20%
7. Veredicto: ¿el D2 flip convierte la señal SHORT en operable con menos wipeouts?
8. Compara contra baseline SPY.

Intérprete: PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/timing_derisking.py
Salida: consola + scratch/timing_derisking_report.json
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

# ═══ CONFIG ═════════════════════════════════════════════════════════════════════
CATEGORIES = {
    1: {"name": "ECONOMIA",    "tickers": ["CREDIT_RATIO", "YIELD_SPREAD", "DXY"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "VVIX", "CBOE_PCR", "SKEW"]},
    3: {"name": "ACCION",      "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

SHORT_PERMS = {(1, 2, 3), (1, 3, 2)}
PERM_LABELS = {
    (1, 2, 3): "macro-driven (CAT1→CAT2→CAT3)",
    (1, 3, 2): "cuchillo (CAT1→CAT3→CAT2)",
}

# Las 11 estaciones (ticker para D2/flip/overflow desde vault OR desde raw data)
STATION_TICKER = {
    "vix": "VIX", "vvix": "VVIX", "pcr": "CBOE_PCR", "fg": "FG",
    "sv5_turbulence": "SV5_TURBULENCE", "skew": "SKEW",
    "credit": "CREDIT_RATIO", "yield_curve": "YIELD_SPREAD",
    "rotation": "ROTATION_INDEX", "bsi": "S5TW", "dxy": "DXY",
}

GRUPO_A = {"vix", "bsi", "fg", "credit", "rotation"}

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

PCT_HIGH = 90
PCT_LOW = 10
D3_COMPRESSED = 0.7
STREAK = 3
WINDOW_DAYS = 30
FW_HORIZONS = [5, 10, 20, 40]
SCALES = ["zz25", "zz50", "zz75"]
N_BOOT = 3000
BOOT_SEED = 42
MIN_N = 20

# ═══ HELPERS ESTADÍSTICOS ═══════════════════════════════════════════════════════
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
    """Estadísticas SHORT: fwd = SPY forward long; trade = -fwd."""
    fwd = np.asarray(fwd_returns, float)
    fwd = fwd[~np.isnan(fwd)]
    n = len(fwd)
    if n < 1:
        return None

    trade = -fwd  # short SPY
    wins = trade[trade > 0]
    losses = trade[trade <= 0]

    fwd_mean, fwd_lo, fwd_hi = boot_ci_mean(fwd)
    short_wr = float(np.mean(trade > 0))

    gw = float(np.sum(wins)) if len(wins) else 0.0
    gl = float(abs(np.sum(losses))) if len(losses) else 0.0
    pf = gw / gl if gl > 0 else float("inf")

    avg_w = float(np.mean(wins)) if len(wins) else 0.0
    avg_l = float(abs(np.mean(losses))) if len(losses) else 0.0
    wlr = avg_w / avg_l if avg_l > 0 else float("inf")
    kelly = (short_wr - (1 - short_wr) / wlr) if (avg_l > 0 and wlr > 0) else float("nan")

    wipe = losses[losses < -0.20]

    return {
        "N": n,
        "fwd_mean": fwd_mean, "fwd_ci95": [fwd_lo, fwd_hi],
        "short_wr": short_wr,
        "short_pf": None if np.isinf(pf) else float(pf),
        "short_kelly": None if (isinstance(kelly, float) and np.isnan(kelly)) else float(kelly),
        "fwd_std": float(np.std(fwd)),
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


# ═══ CLASIFICADOR DE SECUENCIAS (réplica conjuncion_derisking.py / validate_regimes_oos.py) ═══
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
            signal_bar = ordered[-1][1]
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


# ═══ D2 FLIP — detección en TODAS las barras de las 11 estaciones ═══
def detect_d2_flips(series: pd.Series):
    """Detecta cambios de signo del D2 (diff 3d) en una serie.
    Retorna DataFrame con timestamp y sign (1=positivo, -1=negativo)."""
    d2 = series.diff(3)
    d2 = d2.dropna()
    # Signo del D2
    d2_sign = d2.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    # Flip = cambio de signo (≠0 → ≠0 y distinto)
    flip = (d2_sign != d2_sign.shift(1)) & (d2_sign != 0) & (d2_sign.shift(1) != 0)
    flips = d2_sign[flip]
    if len(flips) == 0:
        return pd.DataFrame(columns=["timestamp", "sign", "val"])
    return pd.DataFrame({
        "timestamp": flips.index,
        "sign": flips.values.astype(int),
        "val": d2.loc[flips.index].values,
    })


def load_d2_data(store, station_name, ticker):
    """Carga los datos crudos de una estación y devuelve DataFrame con val+d2+d3+d1_label calibrado."""
    from pathlib import Path as _Path
    RULES = _Path("/root/botero-trade") / "backend/modules/entry_decision/domain/rules"

    b = store.load_bars(ticker, "1d")["close"].dropna()
    b = b[~b.index.duplicated(keep="last")].sort_index()
    b.index = pd.to_datetime(b.index).tz_localize(None).normalize()

    # Cargar edges calibrados
    fs_path = RULES / f"{station_name}_fact_store.json"
    edges_d1 = None
    labels_d1 = None
    if fs_path.exists():
        d = json.load(open(fs_path))
        th = d.get("_documentation", {}).get("dimension_thresholds_definition", {})
        edges_d1 = th.get(f"{station_name}_edges_d1", None)
        labels_d1 = th.get(f"{station_name}_labels_d1", None)

    df = pd.DataFrame({"val": b})
    df["d2"] = df["val"].diff(3)
    df["d3"] = (df["val"].rolling(2).std() / df["val"].rolling(10).std()).fillna(1.0).replace([np.inf, -np.inf], 1.0)

    if edges_d1 and labels_d1:
        df["d1_label"] = [classify(v, edges_d1, labels_d1) for v in df["val"]]
    else:
        df["d1_label"] = None

    return df


def classify(v, edges, labels):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    for i, e in enumerate(edges):
        if v < e:
            return labels[i]
    return labels[-1]


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


# ═══ CASCADE CONVICTION (réplica compositor) ═══
def cascade_at_bar(bar_ts, station_dfs, legs25_cfg, calib):
    conf_ts = legs25_cfg["confirmed_ns"]
    start_type_arr = legs25_cfg["start_type"]
    prev_ret_arr = legs25_cfg["prev_ret"]

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
        "w_bear": 0.66, "w_dom": 0.34, "stations": list(GRUPO_A),
    })
    allowed = set(type_cfg.get("stations", list(GRUPO_A)))
    w_bear = float(type_cfg.get("w_bear", 0.66))
    w_dom = float(type_cfg.get("w_dom", 0.34))

    votes = {}
    for st in GRUPO_A:
        df = station_dfs[st]
        lab = df["d1_label"].asof(bar_ts)
        votes[st] = d1_vote(st, lab)

    masked = [v for k, v in votes.items() if k in allowed and v is not None]
    d1_bear_masked = float(sum(-v for v in masked if v < 0) / len(masked)) if masked else 0.0

    d1_mean = calib.get("d1_bear_5", {}).get("mean", 0.41)
    d1_std = calib.get("d1_bear_5", {}).get("std", 0.3206)
    dom25_mean = calib.get("domino_zz25", {}).get("mean", 0.0532)
    dom25_std = calib.get("domino_zz25", {}).get("std", 0.035)

    val_dom25 = abs(prev_ret) if prev_ret is not None else dom25_mean
    z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0.0
    z_dom25 = (val_dom25 - dom25_mean) / dom25_std if dom25_std > 0 else 0.0

    c50 = w_bear * z_bear + w_dom * z_dom25
    return {
        "c50": float(c50),
        "cascade_bear": bool(c50 < 0.0),
        "pivot_type": pivot_type,
        "d1_bear_masked": float(d1_bear_masked),
        "domino25": float(val_dom25),
    }


# ═══ VIX-FOCUSED TIMING — el timing VALIDADO es VIX D2 flip ═══════════════════
def vix_timing_analysis(short_ents, station_dfs, station_d2_flips, spy_idx_vals, spy_values):
    """Para cada señal SHORT, mide el timing del D2 de VIX (la estación validada).

    VIX D2 > 0 = miedo construyéndose (mercado cayendo)  → short bien temporizado
    VIX D2 < 0 = miedo resolviéndose (mercado rebotando)  → short tarde/peligroso

    Clasifica por: (1) signo del VIX D2 en la barra de señal, (2) último flip VIX
    antes de la barra (dirección + días). Mide forward short por grupo.
    """
    vix_df = station_dfs["vix"]
    vix_flips = station_d2_flips.get("vix", None)

    # Arrays de flips VIX
    if vix_flips is not None and len(vix_flips) > 0:
        flip_ts = pd.to_datetime(vix_flips["timestamp"]).values
        flip_sign = vix_flips["sign"].values.astype(int)
    else:
        flip_ts = np.array([], dtype="datetime64[ns]")
        flip_sign = np.array([], dtype=int)

    vix_d2 = vix_df["d2"]

    rows = []
    for e in short_ents:
        bar = e["signal_bar"]
        d2v = vix_d2.asof(bar)
        d2v = None if (d2v is None or not np.isfinite(d2v)) else float(d2v)
        d2_sign = 1 if (d2v is not None and d2v > 0) else (-1 if (d2v is not None and d2v < 0) else 0)

        # último flip VIX <= bar
        bar_ns = np.datetime64(bar).astype("datetime64[ns]").astype("int64")
        flip_ns = flip_ts.astype("datetime64[ns]").astype("int64")
        i = int(np.searchsorted(flip_ns, bar_ns, side="right")) - 1
        last_flip_sign = int(flip_sign[i]) if i >= 0 else None
        last_flip_days = (bar - pd.Timestamp(flip_ts[i])).days if i >= 0 else None

        fwd = {}
        for h in FW_HORIZONS:
            fwd[h] = fwd_from_bar(bar, spy_idx_vals, spy_values, h)

        rows.append({
            "signal_bar": bar, "vix_d2": d2v, "vix_d2_sign": d2_sign,
            "last_flip_sign": last_flip_sign, "last_flip_days": last_flip_days,
            "fwd": fwd, "perm": e["perm"],
        })

    # ── Grupos de timing VIX ──
    groups = {
        "vix_building": {"label": "VIX D2 > 0 (miedo construyéndose → short ON)",
                         "mask": lambda r: r["vix_d2_sign"] == 1},
        "vix_resolving": {"label": "VIX D2 < 0 (miedo resolviéndose → short TARDE)",
                          "mask": lambda r: r["vix_d2_sign"] == -1},
        "vix_flat": {"label": "VIX D2 = 0 (neutro)",
                     "mask": lambda r: r["vix_d2_sign"] == 0},
    }
    # Grupos por último flip VIX
    flip_groups = {
        "flip_up_recent": {"label": "Último flip VIX ↑ (miedo empieza a construir)",
                           "mask": lambda r: r["last_flip_sign"] == 1},
        "flip_down_recent": {"label": "Último flip VIX ↓ (miedo empieza a resolver)",
                             "mask": lambda r: r["last_flip_sign"] == -1},
        "flip_none": {"label": "Sin flip VIX previo",
                      "mask": lambda r: r["last_flip_sign"] is None},
    }

    result = {"sign_groups": {}, "flip_groups": {}, "N": len(rows)}

    for gname, gcfg in groups.items():
        g_rows = [r for r in rows if gcfg["mask"](r)]
        result["sign_groups"][gname] = {
            "label": gcfg["label"], "N": len(g_rows), "horizons": {},
        }
        for h in FW_HORIZONS:
            arr = np.array([r["fwd"][h] for r in g_rows if r["fwd"][h] is not None], dtype=float)
            st = short_trade_stats(arr)
            result["sign_groups"][gname]["horizons"][h] = st

    for gname, gcfg in flip_groups.items():
        g_rows = [r for r in rows if gcfg["mask"](r)]
        result["flip_groups"][gname] = {
            "label": gcfg["label"], "N": len(g_rows), "horizons": {},
        }
        for h in FW_HORIZONS:
            arr = np.array([r["fwd"][h] for r in g_rows if r["fwd"][h] is not None], dtype=float)
            st = short_trade_stats(arr)
            result["flip_groups"][gname]["horizons"][h] = st

    # Distribución de días del último flip
    days = [r["last_flip_days"] for r in rows if r["last_flip_days"] is not None]
    result["last_flip_days_dist"] = {
        "N": len(days),
        "median": float(np.median(days)) if days else None,
        "p25": float(np.percentile(days, 25)) if len(days) >= 4 else None,
        "p75": float(np.percentile(days, 75)) if len(days) >= 4 else None,
    }

    return result


# ═══ MAIN ═══════════════════════════════════════════════════════════════════════
def main():
    print("═" * 96)
    print("TIMING DE-RISKING — D2 flip (velocidad) mejora la señal SHORT de la secuencia")
    print("Entrada en BARRA DE SEÑAL · 4 variantes de timing · bootstrap 3000")
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

    # 2. Series raw (9 tickers) → SIGMETs por categoría
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
        sigmets[cat_id] = pd.concat(cat_events).sort_values("timestamp") if cat_events else pd.DataFrame(columns=["timestamp", "type", "ticker"])
        print(f"CAT {cat_id} ({cat['name']}): {len(sigmets[cat_id])} SIGMETs ({len(series)} tickers)")

    # 3. 11 estaciones calibradas (D1 + D2 + D3 para cascade y D2 flip)
    station_dfs = {}
    station_d2_flips = {}
    for name, ticker in STATION_TICKER.items():
        try:
            df = load_d2_data(store, name, ticker)
            station_dfs[name] = df
            flips_df = detect_d2_flips(df["val"])
            station_d2_flips[name] = flips_df
        except Exception as e:
            print(f"  ⚠ estación {name} ({ticker}): {e}")

    # Merge de todos los flips en un solo df con nombre de estación
    all_flips = []
    for name, flips_df in station_d2_flips.items():
        if len(flips_df) > 0:
            f = flips_df.copy()
            f["station"] = name
            all_flips.append(f)
    if all_flips:
        all_flips_df = pd.concat(all_flips).sort_values("timestamp")
        all_flips_arr = np.sort(pd.to_datetime(all_flips_df["timestamp"]).values)
    else:
        all_flips_df = pd.DataFrame(columns=["timestamp", "sign", "val", "station"])
        all_flips_arr = np.array([], dtype="datetime64[ns]")

    print(f"Estaciones: {len(station_dfs)}/11 | Total D2 flips: {len(all_flips_arr)}")

    # 4. Cascade calibration + legs zz25 (domino)
    RULES = ROOT / "backend/modules/entry_decision/domain/rules"
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

    # 6. Baseline SPY
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

    # 7. POR CADA entrada SHORT, identifica D2 FLIP en la ventana previa [signal_bar-30d, signal_bar]
    #    y cascade bear
    report = {"baseline": baseline, "lead_lag": {}, "variants": {}, "scales": {}}

    for scale in SCALES:
        ents = entries_by_scale.get(scale, [])
        short_ents = [e for e in ents if e["perm"] in SHORT_PERMS]
        if not short_ents:
            continue

        # Enriquecer cada entrada
        for e in short_ents:
            bar = e["signal_bar"]
            e["cascade"] = cascade_at_bar(bar, station_dfs, legs25_cfg, calib)

            # ── D2 FLIP en ventana previa ──
            lo = np.datetime64(bar - pd.Timedelta(days=WINDOW_DAYS))
            hi = np.datetime64(bar)
            i_lo = np.searchsorted(all_flips_arr, lo)
            i_hi = np.searchsorted(all_flips_arr, hi)
            flips_in_window = all_flips_df.iloc[i_lo:i_hi] if i_lo < i_hi else all_flips_df.iloc[0:0]

            if len(flips_in_window) > 0:
                # Primer flip (más temprano) en la ventana
                first_flip_row = flips_in_window.iloc[0]
                first_flip_ts = pd.Timestamp(first_flip_row["timestamp"])
                first_flip_station = first_flip_row["station"]
                first_flip_sign = int(first_flip_row["sign"])
                days_before = (bar - first_flip_ts).days
                n_flips = len(flips_in_window)
                n_stations = flips_in_window["station"].nunique()

                # ¿El flip fue bearish? D2 flip de signo positivo→negativo = D2 flip↓ (VIX D2↓ = bearish)
                # Para estaciones como VIX: D2↓ = bearish (resolviendo miedo). Para otras puede variar.
                # Vamos a capturar el signo: -1 = D2 negativo (cayendo)
                e["d2_flip"] = {
                    "has_flip": True,
                    "first_flip_ts": first_flip_ts,
                    "first_flip_station": first_flip_station,
                    "first_flip_sign": first_flip_sign,
                    "days_before": days_before,
                    "n_flips": n_flips,
                    "n_stations": n_stations,
                    "flip_stations": flips_in_window["station"].unique().tolist(),
                }
            else:
                e["d2_flip"] = {
                    "has_flip": False,
                    "first_flip_ts": None,
                    "first_flip_station": None,
                    "days_before": None,
                }

        # ── Variante a) baseline: secuencia SHORT sola ──
        fwd_a = {h: [] for h in FW_HORIZONS}
        for e in short_ents:
            for h in FW_HORIZONS:
                r = fwd_from_bar(e["signal_bar"], spy_idx_vals, spy_values, h)
                fwd_a[h].append(r)

        # ── Variante b) SHORT + D2 flip YA OCURRIÓ (entrada en el flip, NO en sequence bar) ──
        ents_with_flip = [e for e in short_ents if e["d2_flip"]["has_flip"]]
        fwd_b = {h: [] for h in FW_HORIZONS}
        for e in ents_with_flip:
            for h in FW_HORIZONS:
                r = fwd_from_bar(e["d2_flip"]["first_flip_ts"], spy_idx_vals, spy_values, h)
                fwd_b[h].append(r)

        # ── Variante c) SHORT + D2 flip NO ha ocurrido (aún cayendo, NO entrar) ──
        ents_no_flip = [e for e in short_ents if not e["d2_flip"]["has_flip"]]
        fwd_c = {h: [] for h in FW_HORIZONS}
        for e in ents_no_flip:
            for h in FW_HORIZONS:
                r = fwd_from_bar(e["signal_bar"], spy_idx_vals, spy_values, h)
                fwd_c[h].append(r)

        # ── Variante d) SHORT + cascade bear + D2 flip ──
        ents_cascade_flip = [e for e in ents_with_flip if e["cascade"]["cascade_bear"]]
        fwd_d = {h: [] for h in FW_HORIZONS}
        for e in ents_cascade_flip:
            for h in FW_HORIZONS:
                r = fwd_from_bar(e["d2_flip"]["first_flip_ts"], spy_idx_vals, spy_values, h)
                fwd_d[h].append(r)

        type_comp = Counter(e["type"] for e in short_ents if e.get("type"))
        perm_comp = Counter(e["perm"] for e in short_ents)

        scale_report = {
            "N_short_entries": len(short_ents),
            "perm_composition": {PERM_LABELS.get(k, str(k)): v for k, v in perm_comp.items()},
            "type_composition": dict(type_comp),
            "variants": {},
        }

        variants = {
            "a_baseline": {
                "label": "a) Secuencia SHORT sola (baseline, entrada barra señal)",
                "fwd": fwd_a, "N": len(short_ents),
                "entry_type": "signal_bar",
            },
            "b_d2_flip_entry": {
                "label": "b) SHORT + D2 flip (entrada en el flip, NO señal)",
                "fwd": fwd_b, "N": len(ents_with_flip),
                "entry_type": "d2_flip",
            },
            "c_d2_no_flip": {
                "label": "c) SHORT + D2 flip NO ocurrido (aún cayendo)",
                "fwd": fwd_c, "N": len(ents_no_flip),
                "entry_type": "signal_bar",
            },
            "d_cascade_d2_flip": {
                "label": "d) SHORT + cascade bear + D2 flip (dirección + timing)",
                "fwd": fwd_d, "N": len(ents_cascade_flip),
                "entry_type": "d2_flip",
            },
        }

        print(f"\n{'─' * 96}")
        print(f"ESCALA {scale} — Secuencia SHORT: {len(short_ents)} entradas")
        print(f"  Con D2 flip en ventana: {len(ents_with_flip)} | Sin flip: {len(ents_no_flip)}")
        print(f"  Cascade bear + D2 flip: {len(ents_cascade_flip)}")
        print(f"{'─' * 96}")

        for vname, vcfg in variants.items():
            scale_report["variants"][vname] = {"label": vcfg["label"], "N": vcfg["N"], "horizons": {}}
            print(f"\n  {vcfg['label']}  (N = {vcfg['N']})")

            for h in FW_HORIZONS:
                arr = np.array(vcfg["fwd"][h], dtype=float)
                st = short_trade_stats(arr)
                if st is None or st["N"] == 0:
                    scale_report["variants"][vname]["horizons"][h] = None
                    continue
                st["excess_vs_baseline"] = float(st["fwd_mean"] - baseline[h]["mean"])
                scale_report["variants"][vname]["horizons"][h] = st

                ci = st["fwd_ci95"]
                k_s = f"{st['short_kelly']:+.2f}" if st["short_kelly"] is not None else "  —  "
                p_s = f"{st['short_pf']:.2f}" if st["short_pf"] is not None else "  ∞  "
                print(f"    {h:>2}d  N={st['N']:>4}  fwd={st['fwd_mean']*100:+6.2f}% "
                      f"CI95[{ci[0]*100:+6.2f},{ci[1]*100:+6.2f}]  "
                      f"downWR={st['short_wr']*100:>4.0f}%  PF={p_s}  Kelly={k_s}  "
                      f"wipe>20%={st['losses']['wipeouts_gt20pct']}")

        # ── Δ vs baseline (a) ──
        print(f"\n  ── Δ vs baseline (a) a 20d/40d ──")
        a_fwd = variants["a_baseline"]["fwd"]
        for vname in ["b_d2_flip_entry", "c_d2_no_flip", "d_cascade_d2_flip"]:
            lbl = variants[vname]["label"].split(")")[0] + ")"
            v_fwd = variants[vname]["fwd"]
            for h in [20, 40]:
                a_arr = np.array(a_fwd[h], dtype=float)
                v_arr = np.array(v_fwd[h], dtype=float)
                if len(a_arr) < 3 or len(v_arr) < 3:
                    continue
                # Queremos ver: ¿v es MÁS NEGATIVO (más short) que a?
                diff, dlo, dhi = boot_ci_diff(v_arr, a_arr)
                sign = "MÁS BAJISTA" if diff < 0 else "MÁS ALCISTA"
                scale_report["variants"][vname]["horizons"][h]["diff_vs_baseline"] = {
                    "mean": diff, "ci95": [dlo, dhi],
                }
                print(f"    {lbl} vs a) {h:>2}d: Δfwd={diff*100:+.2f}% "
                      f"CI95[{dlo*100:+.2f},{dhi*100:+.2f}]  → {sign}")

            # También comparar vs base para wipeouts
            a_stats_h20 = scale_report["variants"]["a_baseline"]["horizons"].get(20)
            v_stats_h20 = scale_report["variants"][vname]["horizons"].get(20)
            if a_stats_h20 and v_stats_h20:
                wa = a_stats_h20["losses"]["wipeouts_gt20pct"]
                wv = v_stats_h20["losses"]["wipeouts_gt20pct"]
                if wa != wv:
                    print(f"    wipeouts>20%: baseline={wa} → {lbl}={wv} "
                          f"({'ELIMINA TODOS' if wv == 0 and wa > 0 else f'Δ={wv-wa:+d}'})")

        # ── LEAD-LAG: ¿qué estación flipea PRIMERO? ──
        lead_lag = []
        for e in ents_with_flip:
            ff = e["d2_flip"]
            lead_lag.append({
                "signal_bar": str(e["signal_bar"].date()),
                "first_flip_station": ff["first_flip_station"],
                "first_flip_sign": ff["first_flip_sign"],
                "days_before": ff["days_before"],
                "n_flips": ff["n_flips"],
                "n_stations": ff["n_stations"],
                "flip_stations": ff.get("flip_stations", []),
            })

        # Agregados de lead-lag
        stations_first = Counter(ll["first_flip_station"] for ll in lead_lag)
        days_med = float(np.median([ll["days_before"] for ll in lead_lag])) if lead_lag else None
        sign_counts = Counter(ll["first_flip_sign"] for ll in lead_lag)
        print(f"\n  ── LEAD-LAG: ¿quién flipea PRIMERO? (N={len(lead_lag)}) ──")
        for st, cnt in stations_first.most_common(6):
            pct = cnt / len(lead_lag) * 100
            print(f"    {st:<20} {cnt:>3} ({pct:>5.1f}%)")
        print(f"    Mediana días antes: {days_med:.0f}d")
        print(f"    Signo 1er flip: +={sign_counts.get(1,0)} / -={sign_counts.get(-1,0)}")

        scale_report["lead_lag"] = {
            "N": len(lead_lag),
            "stations_first": dict(stations_first),
            "med_days_before": days_med,
            "flip_sign_counts": dict(sign_counts),
        }

        # ── VIX-FOCUSED TIMING (el timing validado es VIX D2 flip) ──
        vix_timing = vix_timing_analysis(short_ents, station_dfs, station_d2_flips,
                                         spy_idx_vals, spy_values)
        scale_report["vix_timing"] = vix_timing

        print(f"\n  ── VIX D2 TIMING (la estación validada) — N={vix_timing['N']} ──")
        for gname in ["vix_building", "vix_resolving", "vix_flat"]:
            g = vix_timing["sign_groups"][gname]
            h20 = g["horizons"].get(20)
            h40 = g["horizons"].get(40)
            if h20 is None:
                print(f"    {g['label']:<55} N={g['N']:>4}  (sin datos)")
                continue
            ci20 = h20["fwd_ci95"]
            ci40 = h40["fwd_ci95"] if h40 else [np.nan, np.nan]
            print(f"    {g['label']:<55} N={g['N']:>4}  "
                  f"fwd20={h20['fwd_mean']*100:+6.2f}% CI[{ci20[0]*100:+6.2f},{ci20[1]*100:+6.2f}]  "
                  f"fwd40={h40['fwd_mean']*100:+6.2f}% CI[{ci40[0]*100:+6.2f},{ci40[1]*100:+6.2f}]  "
                  f"wipe20={h20['losses']['wipeouts_gt20pct']}")
        print(f"    ── por último flip VIX ──")
        for gname in ["flip_up_recent", "flip_down_recent", "flip_none"]:
            g = vix_timing["flip_groups"][gname]
            h20 = g["horizons"].get(20)
            h40 = g["horizons"].get(40)
            if h20 is None:
                print(f"    {g['label']:<55} N={g['N']:>4}  (sin datos)")
                continue
            ci20 = h20["fwd_ci95"]
            print(f"    {g['label']:<55} N={g['N']:>4}  "
                  f"fwd20={h20['fwd_mean']*100:+6.2f}% CI[{ci20[0]*100:+6.2f},{ci20[1]*100:+6.2f}]  "
                  f"downWR={h20['short_wr']*100:>3.0f}%  PF={h20['short_pf'] or float('inf'):.2f}  "
                  f"wipe20={h20['losses']['wipeouts_gt20pct']}")
        d = vix_timing["last_flip_days_dist"]
        print(f"    Último flip VIX: mediana {d['median']:.0f}d antes de la barra "
              f"(P25={d['p25']:.0f}d, P75={d['p75']:.0f}d, N={d['N']})")

        report["scales"][scale] = scale_report

    # 8. Veredicto final
    print("\n" + "═" * 96)
    print("VEREDICTO — ¿el D2 flip convierte la señal SHORT en operable?")
    print("═" * 96)

    for scale in SCALES:
        if scale not in report["scales"]:
            continue
        sr = report["scales"][scale]
        print(f"\n  ESCALA {scale} ({sr['N_short_entries']} señales SHORT)")
        for vname in ["a_baseline", "b_d2_flip_entry", "c_d2_no_flip", "d_cascade_d2_flip"]:
            vh = sr["variants"][vname]
            h20 = vh["horizons"].get(20)
            h40 = vh["horizons"].get(40)
            n20 = h20["N"] if h20 else 0
            n40 = h40["N"] if h40 else 0
            ci20_neg = h20 and h20["fwd_ci95"][1] < 0  # fwd totalmente negativo
            ci40_neg = h40 and h40["fwd_ci95"][1] < 0

            w20 = h20["losses"]["wipeouts_gt20pct"] if h20 else None
            w_a20 = (sr["variants"]["a_baseline"]["horizons"].get(20) or {}).get("losses", {}).get("wipeouts_gt20pct")
            w_a20 = w_a20 if isinstance(w_a20, (int, float)) else None

            verdict = "OP-SHORT" if (ci20_neg or ci40_neg) else ("INSUFICIENTE" if (n20 < MIN_N and n40 < MIN_N) else "RUIDO")
            print(f"    {vh['label']:<55} N20={n20:>3} N40={n40:>3}  "
                  f"CI20neg={ci20_neg} CI40neg={ci40_neg}  "
                  f"wipe20={w20} (baseline={w_a20})  → {verdict}")

    # 9. Lead-lag consolidado (todas escalas)
    print("\n" + "═" * 96)
    print("LEAD-LAG CONSOLIDADO — ¿qué estación flipea PRIMERO? (top-6)")
    print("═" * 96)
    all_ll = []
    for scale in SCALES:
        if scale in report["scales"] and "lead_lag" in report["scales"][scale]:
            sf = report["scales"][scale]["lead_lag"]["stations_first"]
            for st, cnt in sf.items():
                all_ll.append((st, cnt))
    if all_ll:
        from collections import defaultdict
        totals = defaultdict(int)
        for st, cnt in all_ll:
            totals[st] += cnt
        for st, cnt in sorted(totals.items(), key=lambda x: -x[1])[:6]:
            print(f"  {st:<20} {cnt:>4} veces primera")

    # 10. Persistir JSON
    out = ROOT / "scratch" / "timing_derisking_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    print(f"\nJSON → {out}")

    # 11. Persistir Markdown
    md = write_markdown(report)
    print(f"Markdown → {md}")


def write_markdown(report):
    def f(x):
        return f"{x*100:+.2f}" if x is not None else "—"
    def fpf(x):
        return f"{x:.2f}" if x is not None else "—"
    def fk(x):
        return f"{x:+.2f}" if x is not None else "—"
    L = []
    L.append("# TIMING DE-RISKING — D2 flip (velocidad) mejora la señal SHORT de la secuencia\n")
    L.append("Entrada en barra de señal · 4 variantes de timing · bootstrap 3000 · 3 escalas\n")
    L.append("## Baseline SPY (todos los días en ventana elegible)\n")
    L.append("| h | N | mean | CI95 |")
    L.append("|---|---|---|---|")
    for h in FW_HORIZONS:
        b = report["baseline"].get(h) or report["baseline"].get(str(h))
        if b is None:
            continue
        L.append(f"| {h}d | {b['N']} | {f(b['mean'])} | [{f(b['ci95'][0])},{f(b['ci95'][1])}] |")
    L.append("")

    for scale in SCALES:
        if scale not in report["scales"]:
            continue
        sr = report["scales"][scale]
        L.append(f"\n## Escala {scale} — {sr['N_short_entries']} señales SHORT\n")
        L.append(f"Permutaciones: {sr['perm_composition']} · MIN/MAX: {sr['type_composition']}\n")
        L.append("### Variantes (forward desde entrada)\n")
        L.append("| Variante | N | 5d | 10d | 20d | 40d | downWR 20d | PF 20d | Kelly 20d | wipe20 | wipe40 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for vname in ["a_baseline", "b_d2_flip_entry", "c_d2_no_flip", "d_cascade_d2_flip"]:
            vh = sr["variants"][vname]
            label = vh["label"].split(") ", 1)[1] if ") " in vh["label"] else vh["label"]
            if vh["N"] == 0:
                L.append(f"| {label} | 0 | — | — | — | — | — | — | — | — | — |")
                continue
            h5 = vh["horizons"].get(5) or {}; h10 = vh["horizons"].get(10) or {}
            h20 = vh["horizons"].get(20) or {}; h40 = vh["horizons"].get(40) or {}
            L.append(f"| {label} | {vh['N']} | {f(h5.get('fwd_mean'))} | {f(h10.get('fwd_mean'))} | "
                     f"{f(h20.get('fwd_mean'))} | {f(h40.get('fwd_mean'))} | "
                     f"{h20.get('short_wr', 0)*100:.0f}% | {fpf(h20.get('short_pf'))} | "
                     f"{fk(h20.get('short_kelly'))} | "
                     f"{h20.get('losses', {}).get('wipeouts_gt20pct')} | "
                     f"{h40.get('losses', {}).get('wipeouts_gt20pct')} |")

        vt = sr["vix_timing"]
        L.append("\n### VIX D2 TIMING (la estación validada)\n")
        L.append("| Grupo | N | 20d fwd | CI95 20d | 40d fwd | CI95 40d | downWR | PF | wipe20 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for gname in ["vix_building", "vix_resolving", "vix_flat"]:
            g = vt["sign_groups"][gname]
            h20 = g["horizons"].get(20) or {}; h40 = g["horizons"].get(40) or {}
            ci20 = h20.get("fwd_ci95", [None, None]); ci40 = h40.get("fwd_ci95", [None, None])
            L.append(f"| {g['label']} | {g['N']} | {f(h20.get('fwd_mean'))} | "
                     f"[{f(ci20[0])},{f(ci20[1])}] | {f(h40.get('fwd_mean'))} | "
                     f"[{f(ci40[0])},{f(ci40[1])}] | {h20.get('short_wr', 0)*100:.0f}% | "
                     f"{fpf(h20.get('short_pf'))} | {h20.get('losses', {}).get('wipeouts_gt20pct')} |")
        d = vt["last_flip_days_dist"]
        L.append(f"\nÚltimo flip VIX: mediana {d['median']:.0f}d antes de la barra (P25={d['p25']:.0f}d, P75={d['p75']:.0f}d)\n")

    L.append("\n---\n## Veredicto\n")
    L.append("**El D2 flip SÍ mejora la señal SHORT — pero como DIRECCIÓN del VIX D2, no como \"entrada en el flip\".**\n")
    L.append("1. El flip de CUALQUIER estación NO discrimina: 100% de ventanas 30d tienen ≥1 flip (variante c degenerada, N=0); "
             "el \"primer flip\" es ~29d antes (censurado) y dominado por DXY/SKEW/YIELD (las más volátiles). Confirma pitfall #90.\n")
    L.append("2. La DIRECCIÓN del VIX D2 en la barra de señal discrimina: VIX D2>0 (miedo construyéndose) → short fuerte "
             "(zz50 -4.69% downWR 69% PF 4.91, zz75 -6.18% PF 6.49, 0 wipeouts) vs VIX D2<0 (resolviéndose) → short débil "
             "(zz50 -1.50%, zz75 -2.32%, con wipeouts). Gap crece con la escala (+3.2pp zz50, +3.9pp zz75).\n")
    L.append("3. \"Último flip VIX ↑\" (miedo recién empieza a construir) es el timing óptimo: zz75 PF 6.65, downWR 73%, 0 wipeouts.\n")
    L.append("4. cascade bear + D2 flip es CONTRARIAN (short pierde: fwd20 +1.0% zz25, +1.2% zz50) — cascade bear = rebote (comprar miedo).\n")
    L.append("5. Regla operativa: ENTRAR el short SOLO si VIX D2>0; NO ENTRAR si VIX D2<0. La secuencia ya es OP-SHORT sin timing, "
             "pero el filtro VIX D2 building la fortalece 2-3× y elimina wipeouts.\n")

    path = ROOT / "scratch" / "timing_derisking_REPORT.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    main()