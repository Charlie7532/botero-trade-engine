#!/usr/bin/env python3
"""
COORDINATOR — Integrador de los 3 category agents + cascade + sigma overflow
=============================================================================
El "meteorólogo" de la arquitectura METAR. Lee los 3 estados graduados
(CAT1 economía / CAT2 sentimiento / CAT3 acción) + cascade_conviction, usa el
σ-overflow para detectar eventos raros (±3σ en D1×D2×D3, OVERFLOW_MULTI = cisne
negro), determina la SECUENCIA de activación (lead-lag = el RÉGIMEN) y produce
los 3 reportes: METAR (condiciones actuales), TAF (forecast probabilístico con
cono de dispersión multi-escala zz25/zz50/zz75) y SIGMET (solo significancias).

RÉGIMEN = permutación completa de activación (pitfall #83/#84/#85 del workflow):
  CAT1→CAT2→CAT3  macro-driven      (83%,  +2.71% 40d, WR 57%)
  CAT1→CAT3→CAT2  cuchillo cayendo  (6.8%, −3.19% 40d, WR 44%)
  CAT2→CAT3→CAT1  comprar-miedo     (6.2%,  +3.83% 40d, WR 79%)
  CAT2→CAT1→CAT3  protección-lidera (3.0%)
  CAT3→CAT1→CAT2  acción-lidera     (0.9%)  → explosivo / fat tails
  CAT3→CAT2→CAT1  acción-lidera     (0.2%)  → explosivo / fat tails

Regla de oro: probabilidad + CI95 + N. Nunca binario.

Intérprete: backend/.venv/bin/python  (PYTHONPATH=/root/botero-trade)
"""

import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

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
# CONFIG — mapeo categoría → estaciones (11 estaciones METAR)
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORIES = {
    "CAT1_ECONOMIA": [
        {"name": "credit",       "ticker": "CREDIT_RATIO"},
        {"name": "yield_curve",  "ticker": "YIELD_SPREAD"},
        {"name": "dxy",          "ticker": "DXY"},
        {"name": "rotation",     "ticker": "ROTATION_INDEX"},
    ],
    "CAT2_SENTIMIENTO": [
        {"name": "vix",          "ticker": "VIX"},
        {"name": "vvix",         "ticker": "VVIX"},
        {"name": "pcr",          "ticker": "CBOE_PCR"},
        {"name": "skew",         "ticker": "SKEW"},
    ],
    "CAT3_ACCION": [
        {"name": "bsi",          "ticker": "S5TW"},
        {"name": "sv5_turbulence","ticker": "SV5_TURBULENCE"},
        {"name": "fg",           "ticker": "FG"},
        {"name": "rotation",     "ticker": "ROTATION_INDEX"},  # ROTATION es DUAL (CAT1 + CAT3)
    ],
}

# Categoría a la que pertenece cada estación (para el orden de activación)
STATION_CATEGORY = {
    "credit": "CAT1", "yield_curve": "CAT1", "dxy": "CAT1", "rotation": "CAT1",
    "vix": "CAT2", "vvix": "CAT2", "pcr": "CAT2", "skew": "CAT2",
    "bsi": "CAT3", "sv5_turbulence": "CAT3", "fg": "CAT3",
}

# Grupo A (votantes direccionales del cascade_conviction)
GRUPO_A = {"vix", "bsi", "fg", "credit", "rotation"}

# Bins D1 bearish / bullish / half-bearish (réplica del compositor)
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

# GAUSSIAN CDF percentiles de PERCENTILES_D1_GAUSS
GAUSS_CDF = [2.28, 15.87, 50.00, 84.13, 97.72]

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def boot_ci_mean(arr, ci=95, n_boot=3000, seed=42):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return (float(np.nan), float(np.nan), float(np.nan), n)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(arr, size=n, replace=True).mean()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return (float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), n)


def binom_ci95(k, n, z=1.96):
    """CI95 de Wilson para una proporción k/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return (float(max(0.0, centre - margin)), float(min(1.0, centre + margin)))


def classify(v, edges, labels):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    for i, e in enumerate(edges):
        if v < e:
            return labels[i]
    return labels[-1]


def classify_idx(v, edges):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    for i, e in enumerate(edges):
        if v < e:
            return i
    return len(edges)


def graduated_state(value, edges):
    """Estado graduado 0-100% por interpolación σ-CDF sobre D1."""
    if value is None or pd.isna(value):
        return np.nan
    n = len(edges)
    if value < edges[0]:
        frac = value / edges[0] if edges[0] != 0 else 1.0
        return max(0.0, GAUSS_CDF[0] * max(0.0, min(1.0, frac)))
    if value >= edges[-1]:
        return GAUSS_CDF[-1] + (100 - GAUSS_CDF[-1]) * min(
            1.0, (value - edges[-1]) / (edges[-1] - edges[-2]) if n >= 2 else 0.1)
    for i in range(n - 1):
        if value < edges[i + 1]:
            t = (value - edges[i]) / (edges[i + 1] - edges[i]) if edges[i + 1] != edges[i] else 0.5
            return GAUSS_CDF[i] + t * (GAUSS_CDF[i + 1] - GAUSS_CDF[i])
    return 50.0


def load_edges(station):
    d = json.load(open(RULES / f"{station}_fact_store.json"))
    th = d["_documentation"]["dimension_thresholds_definition"]
    return {
        "edges_d1": th[f"{station}_edges_d1"],
        "labels_d1": th[f"{station}_labels_d1"],
        "edges_d2": th[f"{station}_edges_d2"],
        "labels_d2": th[f"{station}_labels_d2"],
        "edges_d3": th[f"{station}_edges_d3"],
        "labels_d3": th[f"{station}_labels_d3"],
        "states": d["states"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CARGA DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

def load_station_series(store, name, ticker, edges):
    b = store.load_bars(ticker, "1d")["close"].dropna()
    b = b[~b.index.duplicated(keep="last")].sort_index()
    df = pd.DataFrame({"val": b})
    df["d2"] = df["val"].diff(3)                       # velocity Δ3d
    df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()  # vol norm std2/std10
    df["d1_label"] = [classify(v, edges["edges_d1"], edges["labels_d1"]) for v in df["val"]]
    df["d2_label"] = [classify(v, edges["edges_d2"], edges["labels_d2"]) for v in df["d2"]]
    df["d3_label"] = [classify(v, edges["edges_d3"], edges["labels_d3"]) for v in df["d3"]]
    df["d1_idx"] = [classify_idx(v, edges["edges_d1"]) for v in df["val"]]
    df["graduated"] = [graduated_state(v, edges["edges_d1"]) for v in df["val"]]
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTES
# ═══════════════════════════════════════════════════════════════════════════════

def metar_word(graduated):
    """Palabra METAR apropiada al estado graduado 0-100% (miedo/estrés)."""
    if np.isnan(graduated):
        return "N/D"
    if graduated >= 97.7:
        return "BOCHORNO EXTREMO"
    if graduated >= 84.13:
        return "BOCHORNO"
    if graduated >= 70:
        return "CÁLIDO-HÚMEDO"
    if graduated >= 50:
        return "NORMAL"
    if graduated >= 30:
        return "FRESCO-SECO"
    if graduated >= 15.87:
        return "AIRE SECO"
    if graduated >= 2.28:
        return "AIRE SECO PROFUNDO"
    return "SEQUÍA EXTREMA"


def build_metar(cat_states):
    """METAR — condiciones actuales por categoría."""
    out = {}
    for cat, sensors in cat_states.items():
        vals = [s["graduated"] for s in sensors if not np.isnan(s["graduated"])]
        mean = float(np.mean(vals)) if vals else float("nan")
        out[cat] = {
            "graduated_mean": round(mean, 2) if not np.isnan(mean) else None,
            "metar_word": metar_word(mean),
            "sensors": [
                {
                    "station": s["station"],
                    "d1": s["d1_label"], "d2": s["d2_label"], "d3": s["d3_label"],
                    "graduated": round(s["graduated"], 2) if not np.isnan(s["graduated"]) else None,
                    "sigma_depth_d1": s["sigma_depth_d1"],
                    "overflow": s["overflow_flag"],
                }
                for s in sensors
            ],
        }
    return out


def build_taf(station_tafs):
    """TAF — cono de dispersión multi-escala zz25/zz50/zz75 por estación."""
    out = {}
    for station, taf in station_tafs.items():
        if taf is None:
            continue
        out[station] = {
            "state_key": taf["state_key"],
            "n": taf["n"],
            "scales": {},
        }
        for scale in ("zz25", "zz50", "zz75"):
            k = taf["kin"].get(scale)
            if not k or k.get("n_pos", 0) + k.get("n_neg", 0) == 0:
                out[station]["scales"][scale] = None
                continue
            n = k.get("n_pos", 0) + k.get("n_neg", 0)
            p_bull = k.get("p_bull", k.get("n_pos", 0) / n)
            out[station]["scales"][scale] = {
                "n": n,
                "p_bull": round(p_bull, 4),
                "direction": "BULL" if p_bull >= 0.5 else "BEAR",
                "ev_net_pct": round(k.get("ev_net", 0.0), 4),
                "e_ret_up_pct": round(k.get("e_ret_max", 0.0), 4),
                "e_ret_down_pct": round(k.get("e_ret_min", 0.0), 4),
                "e_days": round(k.get("e_days", 0.0), 1),
                "ev_per_day": round(float(k.get("ev_per_day", 0.0)), 6),
                "rr_asymmetry": round(k.get("rr_asymmetry", 0.0), 4),
                "confidence": k.get("confidence_tier", "HIGH" if n >= 30 else "MODERATE" if n >= 10 else "LOW"),
            }
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    # 1. Cargar edges + series de las 11 estaciones
    all_edges = {}
    series = {}
    for cat, sensors in CATEGORIES.items():
        for s in sensors:
            name = s["name"]
            if name in all_edges:
                continue
            all_edges[name] = load_edges(name)
            series[name] = load_station_series(store, name, s["ticker"], all_edges[name])

    spy = store.load_bars("SPY", "1d")["close"].dropna()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()

    # 2. Último bar por estación + σ-overflow + estado graduado
    last_state = {}
    overflow_events = []
    for name, df in series.items():
        row = df.iloc[-1]
        d1v = float(row["val"])
        d2v = float(row["d2"]) if not pd.isna(row["d2"]) else None
        d3v = float(row["d3"]) if not pd.isna(row["d3"]) else None
        mu_sig = STATION_MU_SIGMA.get(name, {})
        sd1, f1 = validate_overflow(name, "d1", d1v)
        sd2, f2 = validate_overflow(name, "d2", d2v)
        sd3, f3 = validate_overflow(name, "d3", d3v)
        flags = [f for f in (f1, f2, f3) if f]
        if len(flags) >= 2:
            overflow_flag = "MULTI"
        elif len(flags) == 1:
            overflow_flag = flags[0]
        else:
            overflow_flag = None
        if overflow_flag:
            overflow_events.append({
                "station": name, "flag": overflow_flag,
                "sigma_depth_d1": sd1, "sigma_depth_d2": sd2, "sigma_depth_d3": sd3,
            })
        last_state[name] = {
            "station": name,
            "category": STATION_CATEGORY[name],
            "val": d1v, "d2": d2v, "d3": d3v,
            "d1_label": row["d1_label"], "d2_label": row["d2_label"], "d3_label": row["d3_label"],
            "d1_idx": row["d1_idx"],
            "graduated": row["graduated"],
            "sigma_depth_d1": sd1, "sigma_depth_d2": sd2, "sigma_depth_d3": sd3,
            "overflow_flag": overflow_flag,
        }

    # 3. Cascade conviction (Grupo A vote + domino)
    calib = json.load(open(RULES / "cascade_calibration.json"))
    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    legs25_df = repo.get_confirmed_legs_dataframe("SPY", "zz25")
    last_leg25 = legs25[-1] if legs25 else None
    last_leg50 = legs50[-1] if legs50 else None
    pivot_type = legs25_df.iloc[-1]["start_type"] if len(legs25_df) else "MIN"
    prev_ret25 = abs(float(last_leg25.prev_leg_return)) if last_leg25 else None
    prev_ret50 = abs(float(last_leg50.prev_leg_return)) if last_leg50 else None

    # Grupo A vote direccional
    grupo_a_votes = {}
    for name in GRUPO_A:
        d1 = last_state[name]["d1_label"]
        if d1 in D1_BEARISH_BINS:
            grupo_a_votes[name] = -1.0
        elif d1 in D1_HALF_BEARISH_BINS:
            grupo_a_votes[name] = -0.5
        elif d1 in D1_BULLISH_BINS:
            grupo_a_votes[name] = +1.0
        else:
            grupo_a_votes[name] = 0.0

    type_cfg = calib.get("type_mask", {}).get(pivot_type if pivot_type in ("MIN", "MAX") else "MIN",
                                               {"w_bear": 0.66, "w_dom": 0.34,
                                                "w_bear_c75": 0.5, "w_dom_c75": 0.5,
                                                "stations": ["vix", "bsi", "fg", "credit", "rotation"]})
    allowed = set(type_cfg.get("stations", ["vix", "bsi", "fg", "credit", "rotation"]))
    w_bear = type_cfg.get("w_bear", 0.66)
    w_dom = type_cfg.get("w_dom", 0.34)
    w_bear_c75 = type_cfg.get("w_bear_c75", 0.5)
    w_dom_c75 = type_cfg.get("w_dom_c75", 0.5)

    masked = [v for k, v in grupo_a_votes.items() if k in allowed and v is not None]
    if masked:
        n_bear_frac = sum(-v for v in masked if v < 0)
        d1_bear_masked = n_bear_frac / len(masked)
    else:
        d1_bear_masked = 0.0

    d1_mean = calib.get("d1_bear_5", {}).get("mean", 0.41)
    d1_std = calib.get("d1_bear_5", {}).get("std", 0.3206)
    dom25_mean = calib.get("domino_zz25", {}).get("mean", 0.0532)
    dom25_std = calib.get("domino_zz25", {}).get("std", 0.035)
    dom50_mean = calib.get("domino_zz50", {}).get("mean", 0.1003)
    dom50_std = calib.get("domino_zz50", {}).get("std", 0.0643)
    terc = calib.get("tercile_edges", [-0.387, 0.302])

    val_dom25 = prev_ret25 if prev_ret25 is not None else dom25_mean
    val_dom50 = prev_ret50 if prev_ret50 is not None else dom50_mean
    z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0.0
    z_dom25 = (val_dom25 - dom25_mean) / dom25_std if dom25_std > 0 else 0.0
    z_dom50 = (val_dom50 - dom50_mean) / dom50_std if dom50_std > 0 else 0.0

    c50 = w_bear * z_bear + w_dom * z_dom25
    c75 = w_bear_c75 * z_bear + w_dom_c75 * z_dom50
    c50to75 = 0.15 * z_bear + 0.85 * z_dom50
    cascade_tercile = "t1_low" if c50 < terc[0] else ("t3_high" if c50 > terc[1] else "t2_medium")

    # 4. TAF — estado actual (state_key) → zigzag_kinematic multi-escala
    station_tafs = {}
    for name, df in series.items():
        row = df.iloc[-1]
        state_key = f"{row['d1_label']}__{row['d2_label']}__{row['d3_label']}"
        states = all_edges[name]["states"]
        st = states.get(state_key)
        kin = st.get("zigzag_kinematic", {}) if st else {}
        n = st.get("n", 0) if st else 0
        station_tafs[name] = {"state_key": state_key, "n": n, "kin": kin} if st else None

    # 5. Determinación del RÉGIMEN (secuencia de activación)
    #    Base empírica (pitfall #83, N=470 pivotes zz50):
    REGIME_BASE = {
        "CAT1>CAT2>CAT3": {"label": "MACRO-DRIVEN",      "p": 0.830, "fwd40": 2.71,  "wr": 0.57},
        "CAT1>CAT3>CAT2": {"label": "CUCHILLO CAYENDO",  "p": 0.068, "fwd40": -3.19, "wr": 0.44},
        "CAT2>CAT3>CAT1": {"label": "COMPRAR-MIEDO",     "p": 0.062, "fwd40": 3.83,  "wr": 0.79},
        "CAT2>CAT1>CAT3": {"label": "PROTECCIÓN-LIDERA", "p": 0.030, "fwd40": None,  "wr": None},
        "CAT3>CAT1>CAT2": {"label": "ACCIÓN-LIDERA (EXPLOSIVO)", "p": 0.009, "fwd40": None, "wr": None},
        "CAT3>CAT2>CAT1": {"label": "ACCIÓN-LIDERA (EXPLOSIVO)", "p": 0.002, "fwd40": None, "wr": None},
    }
    N_PIVOTS = 470

    # Orden de activación ACTUAL: categoría con SIGMET/overflow activo más reciente
    # (excluyendo FLIP_D2). Estado actual por categoría:
    cat_activation = {}
    for cat in ("CAT1", "CAT2", "CAT3"):
        members = [last_state[n] for n in STATION_CATEGORY if STATION_CATEGORY[n] == cat]
        # ¿algún EXTREMO_ALTO/BAJO (D1 idx 0 o 5) u overflow activo?
        extremes = [m for m in members
                    if m["d1_idx"] in (0, 5) or m["overflow_flag"] is not None]
        cat_activation[cat] = {
            "n_extreme": len(extremes),
            "max_graduated": max((m["graduated"] for m in members), default=np.nan),
            "extremes": [(m["station"], m["d1_label"], m["overflow_flag"]) for m in extremes],
        }

    # Graduated por categoría (media)
    cat_graduated = {}
    for cat in ("CAT1", "CAT2", "CAT3"):
        vals = [last_state[n]["graduated"] for n in STATION_CATEGORY if STATION_CATEGORY[n] == cat]
        vals = [v for v in vals if not np.isnan(v)]
        cat_graduated[cat] = float(np.mean(vals)) if vals else float("nan")

    # ── Lógica de régimen ──
    # Regla (traducción de #83/#84/#85 a estado graduado + extremos):
    #  - CAT1 lidera si economía sana (graduado alto) y sin estrés → macro-driven.
    #  - CAT2 lidera si protección extrema (VIX/SKEW/PCR alto) → comprar-miedo.
    #  - CAT3 lidera si acción extrema direccional (BSI capitulación/techo, FG extremo).
    #  - SV5T extremo SOLO (dirless) no es liderazgo direccional → early-warning.
    regime_permutation = None
    regime_reason = []

    cat1_stress = any(m["d1_label"] in D1_BEARISH_BINS for m in
                      [last_state[n] for n in ("credit", "yield_curve", "dxy", "rotation")])
    cat2_fear = any(last_state[n]["d1_label"] in D1_BEARISH_BINS for n in ("vix", "vvix", "pcr", "skew"))
    cat3_directional = any(last_state[n]["d1_label"] in (D1_BEARISH_BINS | D1_BULLISH_BINS)
                           for n in ("bsi", "fg"))  # BSI/FG direccionales; SV5T dirless

    if cat1_stress and not cat2_fear and not cat3_directional:
        regime_permutation = "CAT1>CAT2>CAT3"  # macro-driven (estrés macro solo)
        regime_reason.append("CAT1 (economía) es el único con estrés direccional → macro-driven")
    elif cat1_stress and cat3_directional and not cat2_fear:
        regime_permutation = "CAT1>CAT3>CAT2"  # cuchillo (acción antes que sentimiento)
        regime_reason.append("CAT1 estrés + CAT3 acción antes que CAT2 → cuchillo cayendo")
    elif cat2_fear and cat3_directional and not cat1_stress:
        regime_permutation = "CAT2>CAT3>CAT1"  # comprar-miedo (protección lidera)
        regime_reason.append("CAT2 protección + CAT3 acción confirman → comprar-miedo")
    elif cat2_fear and not cat3_directional and not cat1_stress:
        regime_permutation = "CAT2>CAT1>CAT3"  # protección-lidera
        regime_reason.append("CAT2 protección lidera sin acción ni estrés macro")
    elif cat3_directional and not cat1_stress and not cat2_fear:
        regime_permutation = "CAT3>CAT1>CAT2"  # acción-lidera (explosivo)
        regime_reason.append("CAT3 acción direccional lidera → explosivo / fat tails")
    else:
        # Sin extremo direccional: economía sana en expansión = macro-driven por defecto
        regime_permutation = "CAT1>CAT2>CAT3"
        regime_reason.append("Sin extremo direccional — economía sana lidera (macro-driven)")

    # SI SV5T extremo dirless presente → añadir early-warning overlay
    sv5_extreme = last_state["sv5_turbulence"]["d1_idx"] == 5 or last_state["sv5_turbulence"]["overflow_flag"] is not None
    if sv5_extreme and not (cat3_directional):
        regime_reason.append("SV5T extremo (dirless) = batalla formándose → EARLY-WARNING, no régimen direccional")

    reg = REGIME_BASE[regime_permutation]
    p_regime = reg["p"]
    k_regime = round(p_regime * N_PIVOTS)
    ci_lo, ci_hi = binom_ci95(k_regime, N_PIVOTS)

    # 6. VALIDACIÓN GRADE A (reproducción de señales conocidas desde estado actual)
    # PÁNICO TOTAL = VIX D1 label 4-5 AND SKEW D1 label 4-5
    vix_d1 = last_state["vix"]["d1_label"]
    skew_d1 = last_state["skew"]["d1_label"]
    panico = vix_d1 in ("ELEVATED_PANIC", "CRISIS_SPIKE") and skew_d1 in ("TAIL_PARANOIA", "BLACK_SWAN_PARANOIA")

    # CAPITULACIÓN = VIX↑ + S5 colapsó (MIEDO CON VENTA): VIX D1 alto + BSI D2 crush
    bsi_d2 = last_state["bsi"]["d2_label"]
    capitulacion = vix_d1 in ("ELEVATED_PANIC", "CRISIS_SPIKE") and bsi_d2 in ("FAST_CRUSH_3D", "DECELERATING_DOWN_3D")
    # SUB-REACCIÓN = VIX↑ + S5 mantiene (MIEDO SIN VENTA)
    sub_reaccion = vix_d1 in ("ELEVATED_PANIC", "CRISIS_SPIKE") and bsi_d2 in ("ACCELERATING_UP_3D", "FAST_SPIKE_3D")

    grade_a = {
        "PANICO_TOTAL": {"active": panico,
                         "ref": "PF 8.09 @60d, WR 82%, N=55 (raw P85, sin dedup)"},
        "CAPITULACION": {"active": capitulacion,
                         "ref": "PF 2.23 @20d, WR 66%, N=741 (MIEDO CON VENTA)"},
        "SUB_REACCION": {"active": sub_reaccion,
                         "ref": "PF 0.87 @20d, WR 58%, N=193 (MIEDO SIN VENTA)"},
    }

    # 7. Emitir reportes
    print("═" * 90)
    print("  COORDINATOR — Integrador CAT1+CAT2+CAT3 + cascade + σ-overflow")
    print("═" * 90)

    print("\n" + "─" * 90)
    print("  [1] ESTADOS GRADUADOS (último día)")
    print("─" * 90)
    for cat in ("CAT1", "CAT2", "CAT3"):
        mean = cat_graduated[cat]
        w = metar_word(mean)
        print(f"  {cat:<16} {mean:5.1f}%  →  {w}")
    for name, st in last_state.items():
        sd = st["sigma_depth_d1"]
        sd_s = f"{sd:+.2f}σ" if sd is not None else "   —  "
        of = st["overflow_flag"] or ""
        print(f"    {name:<14} D1={str(st['d1_label']):<28} D2={str(st['d2_label']):<24} "
              f"D3={str(st['d3_label']):<24} grad={st['graduated']:5.1f}%  {sd_s:>8}  {of}")

    print("\n" + "─" * 90)
    print("  [2] CASCADE CONVICTION")
    print("─" * 90)
    print(f"  pivot_type={pivot_type}  d1_bear_masked={d1_bear_masked:.3f}  "
          f"z_bear={z_bear:+.2f}  z_dom25={z_dom25:+.2f}  z_dom50={z_dom50:+.2f}")
    print(f"  cascade_50      = {c50:+.3f}  → {cascade_tercile}")
    print(f"  cascade_75      = {c75:+.3f}")
    print(f"  cascade_50to75  = {c50to75:+.3f}")
    print(f"  terciles: t1<{terc[0]}, t3>{terc[1]}")
    print(f"  votes Grupo A: {grupo_a_votes}")

    print("\n" + "─" * 90)
    print("  [3] METAR — CONDICIONES ACTUALES")
    print("─" * 90)
    for cat in ("CAT1", "CAT2", "CAT3"):
        vals = [last_state[n]["graduated"] for n in STATION_CATEGORY if STATION_CATEGORY[n] == cat]
        vals = [v for v in vals if not np.isnan(v)]
        mean = float(np.mean(vals)) if vals else float("nan")
        print(f"  {cat:<16} {metar_word(mean):<20} ({mean:.1f}%)")

    print("\n" + "─" * 90)
    print("  [4] TAF — CONO DE DISPERSIÓN MULTI-ESCALA (zz25/zz50/zz75)")
    print("─" * 90)
    taf_report = build_taf(station_tafs)
    for station, t in taf_report.items():
        print(f"  {station:<14} state={t['state_key']}  n={t['n']}")
        for scale in ("zz25", "zz50", "zz75"):
            sc = t["scales"][scale]
            if sc is None:
                print(f"      {scale}: sin muestra")
                continue
            print(f"      {scale}: p_bull={sc['p_bull']:.2f} {sc['direction']:<5} "
                  f"EV={sc['ev_net_pct']:+.2f}%  up={sc['e_ret_up_pct']:+.2f}% "
                  f"down={sc['e_ret_down_pct']:+.2f}%  e_days={sc['e_days']:.0f}  "
                  f"n={sc['n']}  ({sc['confidence']})")

    print("\n" + "─" * 90)
    print("  [5] SIGMET — SOLO SIGNIFICANCIAS")
    print("─" * 90)
    if overflow_events:
        for e in overflow_events:
            s1 = f"{e['sigma_depth_d1']:+.2f}σ" if e["sigma_depth_d1"] is not None else "—"
            s2 = f"{e['sigma_depth_d2']:+.2f}σ" if e["sigma_depth_d2"] is not None else "—"
            s3 = f"{e['sigma_depth_d3']:+.2f}σ" if e["sigma_depth_d3"] is not None else "—"
            print(f"  ⚠ OVERFLOW {e['flag']:<6} {e['station']:<14} "
                  f"D1={s1}  D2={s2}  D3={s3}")
    else:
        print("  (sin overflow ±3σ activo)")
    # Cortante de viento = SV5T extremo dirless (batalla) sin dirección comprometida
    if sv5_extreme and not cat3_directional:
        print(f"  ⚠ CORTANTE DE VIENTO: SV5T extremo ({last_state['sv5_turbulence']['graduated']:.1f}%) "
              f"sin capitulación ni techo en BSI — turbulencia de volumen sin dirección comprometida")
    # Transiciones (FLIP_D2 reciente)
    for name in GRUPO_A:
        df = series[name]
        if len(df) >= 2:
            d2 = df["d2"].iloc[-1]
            d2_prev = df["d2"].iloc[-2]
            if (d2 is not None and d2_prev is not None and not pd.isna(d2) and not pd.isna(d2_prev)
                    and np.sign(d2) != 0 and np.sign(d2_prev) != 0 and np.sign(d2) != np.sign(d2_prev)):
                print(f"  ⟳ FLIP_D2 (transición) {name}: D2 signo {np.sign(d2_prev):+.0f}→{np.sign(d2):+.0f}")

    print("\n" + "─" * 90)
    print("  [6] RÉGIMEN ACTUAL (secuencia de activación)")
    print("─" * 90)
    print(f"  Secuencia: {regime_permutation}")
    print(f"  RÉGIMEN:   {reg['label']}")
    print(f"  Probabilidad base: {p_regime*100:.1f}%  CI95[{ci_lo*100:.1f}%, {ci_hi*100:.1f}%]  N={N_PIVOTS}")
    if reg["fwd40"] is not None:
        print(f"  Forward 40d esperado: {reg['fwd40']:+.2f}%  (WR {reg['wr']*100:.0f}%)")
    for r in regime_reason:
        print(f"    · {r}")
    print("\n  Distribución completa de regímenes (base empírica N=470):")
    for perm, r in REGIME_BASE.items():
        k = round(r["p"] * N_PIVOTS)
        lo, hi = binom_ci95(k, N_PIVOTS)
        print(f"    {perm:<14} {r['label']:<28} {r['p']*100:5.1f}%  CI95[{lo*100:4.1f},{hi*100:4.1f}]%")

    print("\n" + "─" * 90)
    print("  [7] VALIDACIÓN SEÑALES GRADE A")
    print("─" * 90)
    for name, ga in grade_a.items():
        status = "✓ ACTIVA" if ga["active"] else "— inactiva"
        print(f"  {name:<16} {status:<12}  {ga['ref']}")

    # 8. Guardar JSON
    out = {
        "as_of": str(spy.index[-1].date()) if len(spy) else None,
        "graduated_states": {
            cat: {"mean": cat_graduated[cat], "metar_word": metar_word(cat_graduated[cat])}
            for cat in ("CAT1", "CAT2", "CAT3")
        },
        "per_station": last_state,
        "cascade_conviction": {
            "pivot_type": pivot_type,
            "d1_bear_masked": d1_bear_masked,
            "z_bear": z_bear, "z_dom25": z_dom25, "z_dom50": z_dom50,
            "cascade_50": c50, "cascade_75": c75, "cascade_50to75": c50to75,
            "tercile": cascade_tercile,
            "grupo_a_votes": grupo_a_votes,
        },
        "metar": build_metar({
            cat: [last_state[n] for n in STATION_CATEGORY if STATION_CATEGORY[n] == cat]
            for cat in ("CAT1", "CAT2", "CAT3")
        }),
        "taf": taf_report,
        "sigmet": {
            "overflow_events": overflow_events,
            "cortante_viento": bool(sv5_extreme and not cat3_directional),
        },
        "regimen": {
            "permutation": regime_permutation,
            "label": reg["label"],
            "probability": p_regime,
            "ci95": [ci_lo, ci_hi],
            "N": N_PIVOTS,
            "fwd40_pct": reg["fwd40"],
            "wr": reg["wr"],
            "reasons": regime_reason,
            "all_regimes": [
                {"permutation": perm, "label": r["label"], "p": r["p"],
                 "ci95": list(binom_ci95(round(r["p"] * N_PIVOTS), N_PIVOTS))}
                for perm, r in REGIME_BASE.items()
            ],
        },
        "grade_a": grade_a,
    }
    json.dump(out, open(ROOT / "data/research" / "coordinator_report.json", "w"), indent=2, default=str)
    print(f"\n  Reporte JSON → data/research/coordinator_report.json")

    store.close()


if __name__ == "__main__":
    main()
