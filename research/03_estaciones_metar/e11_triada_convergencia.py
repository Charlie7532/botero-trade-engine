#!/usr/bin/env python3
"""E11a — Sign-Consistency Test (Triada ZZ Convergencia/Divergencia)

Pregunta: ¿Las 3 escalas ZZ (zz25/zz50/zz75) están de acuerdo en la dirección?
Método: Para cada estado de cada estación, clasificar p_bull cross-scale:
  - CONVERGENT_BULL: 3 escalas > 0.52
  - CONVERGENT_BEAR: 3 escalas < 0.48
  - DIVERGENT_EXHAUSTION: táctico bull / estructural bear (zz25 > 0.52, zz75 < 0.48)
  - DIVERGENT_REVERSAL: táctico bear / estructural bull (zz25 < 0.48, zz75 > 0.52)
  - MIXED: no clasifica
Criterio de corte: EV_CONVERGENT > 2× EV_MIXED en ≥3 estaciones.

prompt_cierre_opus_v3 E11a (31-Ago-2026)
"""
import sys, json
from typing import Any
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

STATIONS = {
    "vix": ("VIX", "vix_fact_store.json"),
    "vvix": ("VVIX", "vvix_fact_store.json"),
    "pcr": ("CBOE_PCR", "pcr_fact_store.json"),
    "fg": ("FG", "fg_fact_store.json"),
    "sv5_turbulence": ("SV5_TURBULENCE", "sv5_turbulence_fact_store.json"),
    "skew": ("SKEW", "skew_fact_store.json"),
    "credit": ("CREDIT_RATIO", "credit_fact_store.json"),
    "yield_curve": ("YIELD_SPREAD", "yield_curve_fact_store.json"),
    "rotation": ("ROTATION_INDEX", "rotation_fact_store.json"),
    "bsi": ("S5TW", "bsi_fact_store.json"),
    "dxy": ("DXY", "dxy_fact_store.json"),
}

FS_DIR = ROOT / "backend" / "modules" / "entry_decision" / "domain" / "rules"


def load_fact_store(station: str) -> dict:
    """Load a station's fact store JSON."""
    _, fname = STATIONS[station]
    path = FS_DIR / fname
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def classify_triada(p25: float, p50: float, p75: float) -> str:
    """Classify the p_bull triada."""
    if p25 > 0.52 and p50 > 0.52 and p75 > 0.52:
        return "CONVERGENT_BULL"
    elif p25 < 0.48 and p50 < 0.48 and p75 < 0.48:
        return "CONVERGENT_BEAR"
    elif p25 > 0.52 and p75 < 0.48:
        return "DIVERGENT_EXHAUSTION"
    elif p25 < 0.48 and p75 > 0.52:
        return "DIVERGENT_REVERSAL"
    else:
        return "MIXED"


def classify_ev_gradient(ev25: float, ev50: float, ev75: float) -> str:
    """E11b: EV Gradient classification."""
    gradient = ev75 - ev25
    if gradient > 0.002:
        return "AMPLIFYING"
    elif gradient < -0.002:
        return "DECAYING"
    else:
        return "FLAT"


def classify_ftt_ratio(ftt25: Any, ftt75: Any) -> tuple:
    """E11c: Safe FTT compression classification (BULL or BEAR)."""
    if not isinstance(ftt25, (int, float)) or not isinstance(ftt75, (int, float)) or ftt25 <= 0:
        return "NO_DATA", None
    ratio = float(ftt75 / ftt25)
    if ratio < 3.0:
        return "COMPRESSED", round(ratio, 2)
    elif ratio > 10.0:
        return "STRETCHED", round(ratio, 2)
    else:
        return "NORMAL", round(ratio, 2)


def run():
    results_by_station = {}

    for station in STATIONS:
        fs = load_fact_store(station)
        states = fs.get("states", fs.get("data", {}))

        triada_counts = {"CONVERGENT_BULL": 0, "CONVERGENT_BEAR": 0,
                         "DIVERGENT_EXHAUSTION": 0, "DIVERGENT_REVERSAL": 0, "MIXED": 0}
        triada_ev = {k: [] for k in triada_counts}
        triada_n = {k: [] for k in triada_counts}
        gradient_counts = {"AMPLIFYING": 0, "DECAYING": 0, "FLAT": 0}
        gradient_ev = {k: [] for k in gradient_counts}

        # E11c: FTT tracking (Dual BULL/BEAR)
        ftt_bull_counts = {"COMPRESSED": 0, "NORMAL": 0, "STRETCHED": 0, "NO_DATA": 0}
        ftt_bear_counts = {"COMPRESSED": 0, "NORMAL": 0, "STRETCHED": 0, "NO_DATA": 0}
        ftt_compressed_bear_states = []
        ftt_compressed_bull_states = []

        total_states = 0
        for state_key, state_data in states.items():
            if not isinstance(state_data, dict):
                continue
            zz25 = state_data.get("zz25", {})
            zz50 = state_data.get("zz50", {})
            zz75 = state_data.get("zz75", {})

            if not all(isinstance(z, dict) for z in [zz25, zz50, zz75]):
                continue

            p25 = zz25.get("p_bull", 0.5)
            p50 = zz50.get("p_bull", 0.5)
            p75 = zz75.get("p_bull", 0.5)
            ev25 = zz25.get("ev_net", 0.0)
            ev50 = zz50.get("ev_net", 0.0)
            ev75 = zz75.get("ev_net", 0.0)
            n = state_data.get("n", 0)

            total_states += 1

            # E11a: Sign-Consistency
            triada = classify_triada(p25, p50, p75)
            triada_counts[triada] += 1
            triada_ev[triada].append(ev75)
            triada_n[triada].append(n)

            # E11b: EV Gradient
            gradient = classify_ev_gradient(ev25, ev50, ev75)
            gradient_counts[gradient] += 1
            gradient_ev[gradient].append(ev75)

            # E11c: FTT Collapse (Kinematic layer)
            zk = state_data.get("zigzag_kinematic", {})
            if isinstance(zk, dict):
                zk25 = zk.get("zz25", {}) or {}
                zk75 = zk.get("zz75", {}) or {}
                # Bull FTT
                cat_bull, r_bull = classify_ftt_ratio(zk25.get("ftt_bull_days"), zk75.get("ftt_bull_days"))
                ftt_bull_counts[cat_bull] += 1
                if cat_bull == "COMPRESSED":
                    ftt_compressed_bull_states.append({"state_key": state_key, "ratio": r_bull, "n": n})
                # Bear FTT
                cat_bear, r_bear = classify_ftt_ratio(zk25.get("ftt_bear_days"), zk75.get("ftt_bear_days"))
                ftt_bear_counts[cat_bear] += 1
                if cat_bear == "COMPRESSED":
                    ftt_compressed_bear_states.append({"state_key": state_key, "ratio": r_bear, "n": n})

        # Compute means with correct units (bps = * 10000, pct = * 100)
        triada_mean_ev_pct = {}
        triada_mean_ev_bps = {}
        for k, vals in triada_ev.items():
            if vals:
                weighted = np.average(vals, weights=triada_n[k]) if triada_n[k] else np.mean(vals)
                triada_mean_ev_pct[k] = round(float(weighted) * 100, 4)
                triada_mean_ev_bps[k] = round(float(weighted) * 10000, 2)
            else:
                triada_mean_ev_pct[k] = None
                triada_mean_ev_bps[k] = None

        gradient_mean_ev_pct = {}
        gradient_mean_ev_bps = {}
        for k, vals in gradient_ev.items():
            if vals:
                m = float(np.mean(vals))
                gradient_mean_ev_pct[k] = round(m * 100, 4)
                gradient_mean_ev_bps[k] = round(m * 10000, 2)
            else:
                gradient_mean_ev_pct[k] = None
                gradient_mean_ev_bps[k] = None

        # Test criterion: CONVERGENT > 2× MIXED
        conv_bull_ev = triada_mean_ev_bps.get("CONVERGENT_BULL")
        mixed_ev = triada_mean_ev_bps.get("MIXED")
        passes_criterion = False
        if conv_bull_ev is not None and mixed_ev is not None and mixed_ev != 0:
            passes_criterion = conv_bull_ev > 2 * abs(mixed_ev)

        results_by_station[station] = {
            "total_states": total_states,
            "triada_counts": triada_counts,
            "triada_mean_ev_pct": triada_mean_ev_pct,
            "triada_mean_ev_bps": triada_mean_ev_bps,
            "passes_criterion_conv_gt_2x_mixed": passes_criterion,
            "gradient_counts": gradient_counts,
            "gradient_mean_ev_pct": gradient_mean_ev_pct,
            "gradient_mean_ev_bps": gradient_mean_ev_bps,
            "ftt_bull_counts": ftt_bull_counts,
            "ftt_bear_counts": ftt_bear_counts,
            "ftt_compressed_bear_count": len(ftt_compressed_bear_states),
            "ftt_compressed_bull_count": len(ftt_compressed_bull_states),
            "ftt_compressed_bear_states": ftt_compressed_bear_states[:5],
        }

    # Summary
    n_pass = sum(1 for v in results_by_station.values() if v["passes_criterion_conv_gt_2x_mixed"])
    print(f"\n{'='*110}")
    print(f"E11a — Sign-Consistency Test: {n_pass}/11 estaciones pasan (criterio: ≥3)")
    print(f"{'='*110}")
    print(f"\n{'Station':<18} {'Total':>5} {'CONV_BULL':>10} {'CONV_BEAR':>10} {'DIV_EXHST':>10} {'DIV_REV':>10} {'MIXED':>10} | {'EV_BULL(bps)':>12} {'EV_BEAR(bps)':>12} {'EV_MIXED(bps)':>14} {'PASS':>5}")
    print("-" * 130)
    for st, d in results_by_station.items():
        tc = d["triada_counts"]
        te = d["triada_mean_ev_bps"]
        print(f"{st:<18} {d['total_states']:>5} {tc['CONVERGENT_BULL']:>10} {tc['CONVERGENT_BEAR']:>10} {tc['DIVERGENT_EXHAUSTION']:>10} {tc['DIVERGENT_REVERSAL']:>10} {tc['MIXED']:>10} | {(te['CONVERGENT_BULL'] or 0):>+12.1f} {(te['CONVERGENT_BEAR'] or 0):>+12.1f} {(te['MIXED'] or 0):>+14.1f} {'✅' if d['passes_criterion_conv_gt_2x_mixed'] else '❌':>5}")

    print(f"\n{'='*110}")
    print(f"E11b — EV Gradient (Unidades corregidas: bps)")
    print(f"{'='*110}")
    print(f"\n{'Station':<18} {'AMPLIFYING':>10} {'DECAYING':>10} {'FLAT':>10} | {'EV_AMP(bps)':>12} {'EV_DEC(bps)':>12} {'EV_FLAT(bps)':>12}")
    print("-" * 90)
    for st, d in results_by_station.items():
        gc = d["gradient_counts"]
        ge = d["gradient_mean_ev_bps"]
        print(f"{st:<18} {gc['AMPLIFYING']:>10} {gc['DECAYING']:>10} {gc['FLAT']:>10} | {(ge['AMPLIFYING'] or 0):>+12.1f} {(ge['DECAYING'] or 0):>+12.1f} {(ge['FLAT'] or 0):>+12.1f}")

    print(f"\n{'='*110}")
    print(f"E11c — FTT Collapse Test (Dual: BULL vs BEAR)")
    print(f"{'='*110}")
    print(f"\n{'Station':<18} {'BULL_COMP':>10} {'BULL_NORM':>10} {'BULL_STR':>10} | {'BEAR_COMP':>10} {'BEAR_NORM':>10} {'BEAR_STR':>10} | {'BEAR_COMP_N':>12}")
    print("-" * 110)
    for st, d in results_by_station.items():
        bc = d["ftt_bull_counts"]
        rc = d["ftt_bear_counts"]
        print(f"{st:<18} {bc['COMPRESSED']:>10} {bc['NORMAL']:>10} {bc['STRETCHED']:>10} | {rc['COMPRESSED']:>10} {rc['NORMAL']:>10} {rc['STRETCHED']:>10} | {d['ftt_compressed_bear_count']:>12}")

    # Save
    out_path = ROOT / "data" / "research" / "metar_triada_convergencia_divergencia.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "exercise": "E11a_sign_consistency + E11b_ev_gradient + E11c_ftt_collapse",
            "source": "prompt_cierre_opus_v3_v2",
            "criterion": "EV_CONVERGENT_BULL > 2x |EV_MIXED| in ≥3 stations",
            "n_stations_pass": n_pass,
            "results": results_by_station,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Guardado: {out_path}")


if __name__ == "__main__":
    run()
