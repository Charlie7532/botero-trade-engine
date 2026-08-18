#!/usr/bin/env python3
"""
CALIBRADOR SIGMET + CLASIFICADOR DE SECUENCIAS (v2, con bandas σ)
==================================================================
Reemplaza los percentiles crudos (P90/P10, expanding-rank) por las
BANDAS σ CALIBRADAS del fact store (PERCENTILES_D1_GAUSS):

  Label 0 = < -2σ  (P2.3)   → EXTREMO BAJO (complacencia profunda)
  Label 1 = -2σ..-1σ (P15.9) → BAJO (anticipación baja)
  Label 2/3 = -1σ..+1σ       → NORMAL (en límites)
  Label 4 = +1σ..+2σ (P84.1) → ALTO (anticipación alta)
  Label 5 = > +2σ  (P97.7)   → EXTREMO ALTO (crisis)

SIGMETs:
  EXTREMO_ALTO  = Label 5 (crisis)
  EXTREMO_BAJO  = Label 0 (complacencia profunda)
  ANTICIPACION_ALTA = Label 4 + D2 acelerando + D3 comprimida
  ANTICIPACION_BAJA = Label 1 + D2 acelerando (hacia abajo) + D3 comprimida
  FLIP_D2       = cambio de signo de velocidad

El D1 se clasifica con los edges CALIBRADOS (no percentiles crudos).
"""

import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd
from collections import Counter

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── Mapping ticker → station fact store ────────────────────────────────
TICKER_TO_STATION = {
    "VIX": "vix",
    "VVIX": "vvix",
    "CBOE_PCR": "pcr",
    "SKEW": "skew",
    "FG": "fg",
    "S5TW": "bsi",
    "SV5_TURBULENCE": "sv5_turbulence",
    "CREDIT_RATIO": "credit",
    "YIELD_SPREAD": "yield_curve",
    "DXY": "dxy",
    "ROTATION_INDEX": "rotation",
}

CATEGORIES = {
    1: {"name": "ECONOMIA", "tickers": ["CREDIT_RATIO", "YIELD_SPREAD", "DXY", "ROTATION_INDEX"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "VVIX", "CBOE_PCR", "SKEW"]},
    3: {"name": "ACCION", "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

PERMUTATION_NAMES = {
    (1,2,3): "CAT1→CAT2→CAT3 (macro-driven)",
    (1,3,2): "CAT1→CAT3→CAT2 (cuchillo)",
    (2,1,3): "CAT2→CAT1→CAT3 (protección lidera)",
    (2,3,1): "CAT2→CAT3→CAT1 (comprar miedo)",
    (3,1,2): "CAT3→CAT1→CAT2 (acción lidera)",
    (3,2,1): "CAT3→CAT2→CAT1 (acción→sentimiento)",
}


def load_calibrated_edges():
    """Carga edges y labels D1 calibrados de cada fact store."""
    result = {}
    for ticker, station in TICKER_TO_STATION.items():
        path = ROOT / f"backend/modules/entry_decision/domain/rules/{station}_fact_store.json"
        try:
            d = json.load(open(path))
            th = d["_documentation"]["dimension_thresholds_definition"]
            edges_key = f"{station}_edges_d1"
            labels_key = f"{station}_labels_d1"
            if edges_key in th and labels_key in th:
                result[ticker] = {
                    "edges": th[edges_key],
                    "labels": th[labels_key],
                }
        except Exception:
            pass
    return result


def classify_d1_calibrated(val, edges, labels):
    """Clasifica D1 usando los edges calibrados (bandas σ)."""
    if val is None or pd.isna(val):
        return None
    for i, e in enumerate(edges):
        if val < e:
            return labels[i]
    return labels[-1]


def detect_sigmet_calibrated(df, edges, labels, d3_comp=0.7, streak=3):
    """Detecta SIGMETs con D1 CALIBRADO (bandas σ) + trayectoria D2/D3."""
    events = []
    prev_sign = None
    d2_streak = 0
    d3_streak = 0

    for ts, row in df.iterrows():
        val = row["val"]
        d2 = row["d2"]
        d3 = row["d3"]

        if pd.isna(val) or pd.isna(d2):
            continue

        label = classify_d1_calibrated(val, edges, labels)
        label_idx = labels.index(label) if label in labels else -1

        sign = 1 if d2 > 0 else (-1 if d2 < 0 else 0)
        d2_streak = d2_streak + 1 if (sign != 0 and sign == prev_sign) else (1 if sign != 0 else 0)
        d3_streak = d3_streak + 1 if (pd.notna(d3) and d3 < d3_comp) else 0

        sig_type = None

        # EXTREMO ALTO: label 5 (> +2σ)
        if label_idx == 5:
            sig_type = "EXTREMO_ALTO"
        # EXTREMO BAJO: label 0 (< -2σ)
        elif label_idx == 0:
            sig_type = "EXTREMO_BAJO"
        # ANTICIPACIÓN ALTA: label 4 (+1σ..+2σ) + D2 subiendo + D3 comprimida
        elif label_idx == 4 and d2_streak >= streak and d3_streak >= streak and sign > 0:
            sig_type = "ANTICIPACION_ALTA"
        # ANTICIPACIÓN BAJA: label 1 (-2σ..-1σ) + D2 bajando + D3 comprimida
        elif label_idx == 1 and d2_streak >= streak and d3_streak >= streak and sign < 0:
            sig_type = "ANTICIPACION_BAJA"

        # FLIP D2
        if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
            if sig_type is None:
                sig_type = "FLIP_D2"

        if sign != 0:
            prev_sign = sign

        if sig_type:
            events.append({
                "timestamp": ts,
                "type": sig_type,
                "label": label,
                "d2_streak": d2_streak,
                "d3_streak": d3_streak,
            })

    return pd.DataFrame(events)


def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    print("═" * 70)
    print("CALIBRADOR SIGMET + CLASIFICADOR — bandas σ del fact store")
    print("═" * 70)

    # 1. Cargar edges calibrados
    calibrated = load_calibrated_edges()
    print(f"\n[1] Edges calibrados cargados: {len(calibrated)}/11 estaciones")

    # 2. Cargar series + detectar SIGMETs calibrados
    sigmets = {}
    for cat_id, cat in CATEGORIES.items():
        cat_ev = []
        for ticker in cat["tickers"]:
            if ticker not in calibrated:
                continue
            try:
                b = store.load_bars(ticker, "1d")
                if len(b) == 0:
                    continue
                s = b["close"].dropna()
                df = pd.DataFrame({"val": s})
                df["d2"] = df["val"].diff(3)
                df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()
                edges = calibrated[ticker]["edges"]
                labels = calibrated[ticker]["labels"]
                ev = detect_sigmet_calibrated(df, edges, labels)
                if len(ev) > 0:
                    ev["ticker"] = ticker
                    cat_ev.append(ev)
            except Exception as e:
                print(f"  ⚠️ {ticker}: {str(e)[:50]}")
        if cat_ev:
            sigmets[cat_id] = pd.concat(cat_ev)
            print(f"  CAT {cat_id} ({cat['name']}): {len(sigmets[cat_id])} SIGMETs calibrados")

    # 3. Clasificar secuencias (multi-escala)
    spy = store.load_bars("SPY", "1d")["close"]

    for scale in ["zz25", "zz50", "zz75"]:
        pivots_df = repo.get_confirmed_legs_dataframe("SPY", scale)
        if len(pivots_df) == 0:
            continue
        sequences = []
        for _, leg in pivots_df.iterrows():
            pivot_ts = pd.Timestamp(leg["start_timestamp"])
            first_sigmet = {}
            for cat_id in [1, 2, 3]:
                if cat_id in sigmets:
                    ev = sigmets[cat_id]
                    window = ev[(ev["timestamp"] >= pivot_ts - pd.Timedelta(days=30)) &
                                (ev["timestamp"] <= pivot_ts)]
                    if len(window) > 0:
                        first_sigmet[cat_id] = window["timestamp"].min()
            if len(first_sigmet) >= 2:
                ordered = sorted(first_sigmet.items(), key=lambda x: x[1])
                sequences.append(tuple(cat for cat, _ in ordered))

        if not sequences:
            continue

        perm_counts = Counter(sequences)
        total = len(sequences)
        print(f"\n{'═'*70}")
        print(f"ESCALA {scale} — {total} pivotes")
        print(f"{'═'*70}")
        print(f"{'Permutación':<43} {'N':>5} {'%':>6}")
        print("-" * 58)
        for perm in sorted(perm_counts, key=perm_counts.get, reverse=True):
            name = PERMUTATION_NAMES.get(perm, str(perm))
            pct = perm_counts[perm] / total * 100
            print(f"  {name:<41} {perm_counts[perm]:>5} {pct:>5.1f}%")

    store.close()

    print("\n═" * 70)
    print("CALIBRADOR COMPLETADO — SIGMETs con bandas σ calibradas")
    print("═" * 70)


if __name__ == "__main__":
    main()
