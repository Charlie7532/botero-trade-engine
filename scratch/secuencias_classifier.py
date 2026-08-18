#!/usr/bin/env python3
"""
CLASIFICADOR DE SECUENCIAS — Régimen por orden de activación (v1)
==================================================================
Concepto central: el régimen = la SECUENCIA en que las 3 categorías
se activan alrededor de cada pivote zigzag.

NO mide etiquetas (bull/bear). Mide la PERMUTACIÓN del lead:
  CAT1→CAT2→CAT3, CAT1→CAT3→CAT2, CAT2→CAT1→CAT3, ...

Cada permutación = un régimen distinto, con su firma de forward returns,
volatilidad, y frecuencia de eventos especiales.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from collections import Counter

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── Config ──────────────────────────────────────────────────────────────
CATEGORIES = {
    1: {"name": "ECONOMIA", "tickers": ["CREDIT_RATIO", "YIELD_SPREAD", "DXY", "ROTATION_INDEX"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "VVIX", "CBOE_PCR", "SKEW"]},
    3: {"name": "ACCION", "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

# Los 6 nombres de permutaciones
PERMUTATION_NAMES = {
    (1,2,3): "CAT1→CAT2→CAT3 (macro-driven)",
    (1,3,2): "CAT1→CAT3→CAT2 (acción adelanta sentimiento)",
    (2,1,3): "CAT2→CAT1→CAT3 (protección lidera)",
    (2,3,1): "CAT2→CAT3→CAT1 (protección→acción→economía)",
    (3,1,2): "CAT3→CAT1→CAT2 (acción lidera — violento)",
    (3,2,1): "CAT3→CAT2→CAT1 (acción→sentimiento→economía)",
}


def load_series(store, tickers):
    series = {}
    for t in tickers:
        try:
            b = store.load_bars(t, "1d")
            if len(b) > 0:
                series[t] = b["close"].dropna()
        except Exception:
            pass
    return series


def compute_d1_d2_d3(series_dict):
    result = {}
    for t, s in series_dict.items():
        df = pd.DataFrame({"val": s})
        df["d2"] = df["val"].diff(3)
        df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()
        df["d1_pct"] = df["val"].expanding().rank(pct=True) * 100
        result[t] = df
    return result


def detect_sigmet(df, pct_high=90, pct_low=10, d3_comp=0.7, streak=3):
    """SIGMET con trayectoria D2/D3 (misma lógica del skeleton)."""
    events = []
    prev_sign = None
    d2_streak = 0
    d3_streak = 0
    for ts, row in df.iterrows():
        pct, d2, d3 = row["d1_pct"], row["d2"], row["d3"]
        if pd.isna(pct) or pd.isna(d2):
            continue
        sign = 1 if d2 > 0 else (-1 if d2 < 0 else 0)
        d2_streak = d2_streak + 1 if (sign != 0 and sign == prev_sign) else (1 if sign != 0 else 0)
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
            events.append({"timestamp": ts, "type": sig_type})
    return pd.DataFrame(events)


def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    print("═" * 70)
    print("CLASIFICADOR DE SECUENCIAS — Régimen por orden de activación")
    print("═" * 70)

    # 1. Cargar series + SIGMETs por categoría
    sigmets = {}
    for cat_id, cat in CATEGORIES.items():
        series = load_series(store, cat["tickers"])
        computed = compute_d1_d2_d3(series)
        cat_ev = []
        for t, df in computed.items():
            ev = detect_sigmet(df)
            if len(ev) > 0:
                ev["ticker"] = t
                cat_ev.append(ev)
        if cat_ev:
            sigmets[cat_id] = pd.concat(cat_ev)

    # 2. Pivotes zigzag — MULTI-ESCALA
    spy = store.load_bars("SPY", "1d")["close"]

    for scale in ["zz25", "zz50", "zz75"]:
        pivots_df = repo.get_confirmed_legs_dataframe("SPY", scale)
        if len(pivots_df) == 0:
            print(f"\n[zz{scale[-2:]}] SIN DATOS")
            continue

        # 3. Para cada pivote, determinar la SECUENCIA completa (permutación)
        sequences = []  # lista de (pivot_ts, permutation_tuple, is_full)
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
                permutation = tuple(cat for cat, _ in ordered)
                sequences.append((pivot_ts, permutation, len(ordered) == 3))

        if not sequences:
            continue

        # 4. Distribución de permutaciones
        perm_counts = Counter(s[1] for s in sequences)
        total = len(sequences)
        print(f"\n{'═'*70}")
        print(f"ESCALA {scale} — {total} pivotes")
        print(f"{'═'*70}")
        print(f"{'Permutación':<45} {'N':>5} {'%':>6}")
        print("-" * 58)
        for perm in sorted(perm_counts, key=perm_counts.get, reverse=True):
            name = PERMUTATION_NAMES.get(perm, str(perm))
            pct = perm_counts[perm] / total * 100
            print(f"  {name:<43} {perm_counts[perm]:>5} {pct:>5.1f}%")

    # 5. Caracterización detallada SOLO en zz50 (la escala operacional)
    print(f"\n{'═'*70}")
    print("CARACTERIZACIÓN DETALLADA — zz50 (escala operacional)")
    print(f"{'═'*70}")
    pivots_df = repo.get_confirmed_legs_dataframe("SPY", "zz50")
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
            permutation = tuple(cat for cat, _ in ordered)
            sequences.append((pivot_ts, permutation, len(ordered) == 3))

    perm_counts = Counter(s[1] for s in sequences)
    top4 = sorted(perm_counts, key=perm_counts.get, reverse=True)[:4]

    def fwd_returns(pivot_dates, spy_series, horizons=[5,10,20,40]):
        results = {h: [] for h in horizons}
        for p in pivot_dates:
            if p in spy_series.index:
                i = spy_series.index.get_loc(p)
                for h in horizons:
                    if i + h < len(spy_series):
                        results[h].append(spy_series.iloc[i+h] / spy_series.iloc[i] - 1)
        return {h: np.array(v) for h, v in results.items()}

    for perm in top4:
        name = PERMUTATION_NAMES.get(perm, str(perm))
        pivots = [s[0] for s in sequences if s[1] == perm]
        fwd = fwd_returns(pivots, spy)
        print(f"\n  {perm_counts[perm]} pivotes — {name}")
        print(f"  {'Horizonte':<10} {'Retorno':>10} {'Win%':>7} {'Vol(std)':>10}")
        for h in [5,10,20,40]:
            r = fwd.get(h, np.array([]))
            if len(r) > 0:
                print(f"  {h:<10}d {r.mean()*100:>+9.2f}% {(r>0).mean()*100:>6.0f}% {r.std()*100:>9.2f}%")

    print("\n═" * 70)
    print("CLASIFICADOR COMPLETADO — las permutaciones SON los regímenes")
    print("═" * 70)

    store.close()


if __name__ == "__main__":
    main()