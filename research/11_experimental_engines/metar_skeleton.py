#!/usr/bin/env python3
"""
PROTOTIPO ESQUELETO — Sistema METAR multi-categoría (v1)
=========================================================
Demuestra los 3 conceptos núcleo de la arquitectura:

1. SIGMET como BUS COMÚN: cada categoría emite SIGMET cuando detecta
   un cambio significativo (extremo D1, flip D2, transición D3).
2. LEAD-LAG EMPÍRICO: para cada pivote zigzag, medir QUÉ categoría
   emitió SIGMET primero (sin asumir la secuencia 1→2→3).
3. SEPARACIÓN benchmark/calificador: el benchmark solo ve datos hasta T;
   los calificadores usan el zigzag para clasificar anticipada/retrasada.

NO es el sistema completo. Es el ESQUELETO que valida la arquitectura.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── Configuración ─────────────────────────────────────────────────────────
CATEGORIES = {
    1: {"name": "ECONOMIA", "tickers": ["CREDIT_RATIO", "YIELD_SPREAD", "DXY", "ROTATION_INDEX"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "VVIX", "CBOE_PCR", "SKEW"]},
    3: {"name": "ACCION", "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

# Umbrales SIGMET (significancia) — percentiles de la historia de cada serie
SIGMET_EXTREME_PCT = 95  # D1 en P95+ = extremo alto
SIGMET_COMPLACENCY_PCT = 5  # D1 en P5- = extremo bajo (complacencia)


def load_series(store, tickers):
    """Carga las series y las alinea por fecha."""
    series = {}
    for t in tickers:
        try:
            b = store.load_bars(t, "1d")
            if len(b) > 0:
                series[t] = b["close"].dropna()
        except Exception as e:
            print(f"  ⚠️ {t}: {str(e)[:50]}")
    return series


def compute_d1_d2_d3(series_dict):
    """Computa D1 (nivel), D2 (velocidad diff3), D3 (vol std2/std10) por serie.

    D1 = valor normalizado por percentil histórico (0-100%).
    D2 = signo de diff(3) — building (+) / resolving (-).
    D3 = std(2)/std(10) — comprimido (<0.5) / caos (>1.0).
    """
    result = {}
    for t, s in series_dict.items():
        df = pd.DataFrame({"val": s})
        df["d2"] = df["val"].diff(3)  # velocidad 3d
        df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()  # vol norm
        # D1 como percentil expandido (0-100) — aproximación graduada
        df["d1_pct"] = df["val"].expanding().rank(pct=True) * 100
        result[t] = df
    return result


def detect_sigmet(df, pct_high=90, pct_low=10, d3_compressed=0.7, streak=3):
    """Detecta SIGMETs con TRAYECTORIA (no un solo punto).

    ANTICIPACIÓN = TRAYECTORIA de D2 acelerando durante `streak` días consecutivos
      + D1 acercándose al extremo + D3 comprimida (calma pre-tormenta).

    La trayectoria distingue el "bochorno" real (humedad subiendo gradual)
    del ruido de un solo día.
    """
    events = []
    prev_d2_sign = None
    d2_streak = 0  # días consecutivos con D2 en la misma dirección
    d3_compress_streak = 0  # días consecutivos con D3 comprimida
    prev_d3 = None

    for ts, row in df.iterrows():
        pct = row["d1_pct"]
        d2 = row["d2"]
        d3 = row["d3"]
        if pd.isna(pct) or pd.isna(d2):
            continue

        # Trayectoria de D2 (racha en la misma dirección)
        sign = 1 if d2 > 0 else (-1 if d2 < 0 else 0)
        if sign != 0:
            if sign == prev_d2_sign:
                d2_streak += 1
            else:
                d2_streak = 1
        else:
            d2_streak = 0

        # Trayectoria de D3 (racha comprimida)
        if pd.notna(d3) and d3 < d3_compressed:
            d3_compress_streak += 1
        else:
            d3_compress_streak = 0

        sigmet_type = None

        # ANTICIPACIÓN ALTA: trayectoria D2 subiendo + D3 comprimida + D1 acercándose
        if (70 <= pct < pct_high and d2_streak >= streak
                and d3_compress_streak >= streak):
            sigmet_type = "ANTICIPACION_ALTA"
        # ANTICIPACIÓN BAJA
        elif (pct_low < pct <= 30 and d2_streak >= streak
                and d3_compress_streak >= streak and sign < 0):
            sigmet_type = "ANTICIPACION_BAJA"
        # CONFIRMACIÓN: en el extremo
        elif pct >= pct_high:
            sigmet_type = "EXTREMO_ALTO"
        elif pct <= pct_low:
            sigmet_type = "EXTREMO_BAJO"

        # Flip de D2
        if prev_d2_sign is not None and sign != 0 and prev_d2_sign != 0 and sign != prev_d2_sign:
            if sigmet_type is None:
                sigmet_type = "FLIP_D2"

        if sign != 0:
            prev_d2_sign = sign
        prev_d3 = d3

        if sigmet_type:
            events.append({
                "timestamp": ts,
                "type": sigmet_type,
                "d1_pct": pct,
                "d2": d2,
                "d2_streak": d2_streak,
                "d3": d3,
                "d3_streak": d3_compress_streak,
            })
    return pd.DataFrame(events)


def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    print("═" * 70)
    print("PROTOTIPO ESQUELETO — Sistema METAR multi-categoría")
    print("═" * 70)

    # 1. Cargar series por categoría
    print("\n[1] Cargando series...")
    all_series = {}
    for cat_id, cat in CATEGORIES.items():
        s = load_series(store, cat["tickers"])
        all_series[cat_id] = s
        print(f"  CAT {cat_id} ({cat['name']}): {list(s.keys())}")

    # 2. Cargar pivotes zigzag (SPY)
    print("\n[2] Cargando pivotes zigzag SPY...")
    pivots = {}
    for scale in ["zz25", "zz50", "zz75"]:
        df = repo.get_confirmed_legs_dataframe("SPY", scale)
        if len(df) > 0:
            pivots[scale] = df
            print(f"  {scale}: {len(df)} legs")
        else:
            print(f"  {scale}: SIN DATOS")

    store.close()

    # 3. Computar D1/D2/D3 + SIGMETs por categoría
    print("\n[3] Detectando SIGMETs por categoría...")
    sigmets = {}
    for cat_id, cat in CATEGORIES.items():
        series = all_series[cat_id]
        computed = compute_d1_d2_d3(series)
        cat_events = []
        for t, df in computed.items():
            ev = detect_sigmet(df)
            if len(ev) > 0:
                ev["ticker"] = t
                ev["category"] = cat_id
                cat_events.append(ev)
        if cat_events:
            sigmets[cat_id] = pd.concat(cat_events)
            print(f"  CAT {cat_id} ({cat['name']}): {len(sigmets[cat_id])} SIGMETs")
        else:
            print(f"  CAT {cat_id} ({cat['name']}): 0 SIGMETs")

    # 4. Lead-lag: para cada pivote, medir anticipación REAL
    print("\n[4] Lead-lag empírico (ANTICIPACIÓN — ¿quién avisa primero?)...")
    if "zz50" in pivots:
        zz50 = pivots["zz50"]
        lead_counts = {1: 0, 2: 0, 3: 0}
        lead_days = {1: [], 2: [], 3: []}
        antip_counts = {1: 0, 2: 0, 3: 0}
        n_pivots_with_anticip = 0
        for _, leg in zz50.iterrows():
            pivot_ts = pd.Timestamp(leg["start_timestamp"])
            first_cat = None
            first_delta = None
            for cat_id in [1, 2, 3]:
                if cat_id in sigmets:
                    ev = sigmets[cat_id]
                    # Solo ANTICIPACION (pre-síntoma) en ventana 30 días
                    window = ev[(ev["timestamp"] >= pivot_ts - pd.Timedelta(days=30)) &
                                (ev["timestamp"] <= pivot_ts) &
                                (ev["type"].str.startswith("ANTICIPACION"))]
                    if len(window) > 0:
                        delta = (pivot_ts - window["timestamp"].max()).days
                        if first_delta is None or delta < first_delta:
                            first_delta = delta
                            first_cat = cat_id
            if first_cat is not None:
                lead_counts[first_cat] += 1
                lead_days[first_cat].append(first_delta)
                n_pivots_with_anticip += 1
                antip_counts[first_cat] += 1

        total_anticip = sum(antip_counts.values())
        print(f"  Pivotes con ANTICIPACION previa: {n_pivots_with_anticip}/{len(zz50)}")
        if total_anticip > 0:
            print(f"  LEAD (categoría que ANTICIPA primero):")
            for cat_id in [1, 2, 3]:
                pct = antip_counts[cat_id] / total_anticip * 100
                med = np.median(lead_days[cat_id]) if lead_days[cat_id] else float('nan')
                mean_days = np.mean(lead_days[cat_id]) if lead_days[cat_id] else float('nan')
                print(f"    CAT {cat_id} ({CATEGORIES[cat_id]['name']}): "
                      f"{antip_counts[cat_id]} ({pct:.0f}%) "
                      f"lead med={med:.1f}d mean={mean_days:.1f}d")
        else:
            print("  ⚠️ Ningún pivote tuvo ANTICIPACION detectada")

        # 4b. También medir con TODOS los eventos (confirmación incluida)
        print("\n[4b] Con TODOS los SIGMETs (anticipación + extrema + flip)...")
        lead_counts_all = {1: 0, 2: 0, 3: 0}
        lead_days_all = {1: [], 2: [], 3: []}
        for _, leg in zz50.iterrows():
            pivot_ts = pd.Timestamp(leg["start_timestamp"])
            first_cat = None
            first_delta = None
            for cat_id in [1, 2, 3]:
                if cat_id in sigmets:
                    ev = sigmets[cat_id]
                    window = ev[(ev["timestamp"] >= pivot_ts - pd.Timedelta(days=30)) &
                                (ev["timestamp"] <= pivot_ts)]
                    if len(window) > 0:
                        delta = (pivot_ts - window["timestamp"].max()).days
                        if first_delta is None or delta < first_delta:
                            first_delta = delta
                            first_cat = cat_id
            if first_cat is not None:
                lead_counts_all[first_cat] += 1
                lead_days_all[first_cat].append(first_delta)

        total_all = sum(lead_counts_all.values())
        for cat_id in [1, 2, 3]:
            pct = lead_counts_all[cat_id] / total_all * 100 if total_all > 0 else 0
            med = np.median(lead_days_all[cat_id]) if lead_days_all[cat_id] else float('nan')
            print(f"    CAT {cat_id}: {lead_counts_all[cat_id]} ({pct:.0f}%) med lead={med:.1f}d")

        # 5. El caso RARO: CAT 3 (acción) lidera — ¿explota?
        print("\n[5] Caso RARO: pivotes donde CAT 3 (ACCIÓN) lidera — ¿explota?")
        sp_store = TimescaleDataStore()
        spy = sp_store.load_bars("SPY", "1d")["close"]
        sp_store.close()
        cat3_lead_events = []
        cat1_lead_events = []
        for _, leg in zz50.iterrows():
            pivot_ts = pd.Timestamp(leg["start_timestamp"])
            first_cat = None
            first_delta = None
            for cat_id in [1, 2, 3]:
                if cat_id in sigmets:
                    ev = sigmets[cat_id]
                    window = ev[(ev["timestamp"] >= pivot_ts - pd.Timedelta(days=30)) &
                                (ev["timestamp"] <= pivot_ts) &
                                (ev["type"].str.startswith("ANTICIPACION"))]
                    if len(window) > 0:
                        delta = (pivot_ts - window["timestamp"].max()).days
                        if first_delta is None or delta < first_delta:
                            first_delta = delta
                            first_cat = cat_id
            if first_cat == 3:
                cat3_lead_events.append(pivot_ts)
            elif first_cat == 1:
                cat1_lead_events.append(pivot_ts)

        def fwd_returns(pivot_dates, spy_series, horizons=[5, 10, 20, 40]):
            results = {h: [] for h in horizons}
            for p in pivot_dates:
                if p in spy_series.index:
                    i = spy_series.index.get_loc(p)
                    for h in horizons:
                        if i + h < len(spy_series):
                            results[h].append(spy_series.iloc[i + h] / spy_series.iloc[i] - 1)
            return {h: np.array(v) for h, v in results.items()}

        cat3_fwd = fwd_returns(cat3_lead_events, spy)
        cat1_fwd = fwd_returns(cat1_lead_events, spy)
        print(f"  CAT 3 lidera (raro): {len(cat3_lead_events)} pivotes")
        print(f"  CAT 1 lidera (normal): {len(cat1_lead_events)} pivotes")
        print(f"  {'Horizonte':<10} {'CAT 3 (raro)':>16} {'CAT 1 (normal)':>16}")
        for h in [5, 10, 20, 40]:
            c3 = cat3_fwd.get(h, np.array([]))
            c1 = cat1_fwd.get(h, np.array([]))
            c3s = f"{c3.mean()*100:+.2f}% (±{c3.std()*100:.1f})" if len(c3) > 0 else "n/d"
            c1s = f"{c1.mean()*100:+.2f}% (±{c1.std()*100:.1f})" if len(c1) > 0 else "n/d"
            print(f"  {h:<10}d {c3s:>16} {c1s:>16}")
        # ¿explota? — medir el rango (max-min) de los retornos
        if len(cat3_fwd.get(20, [])) > 0 and len(cat1_fwd.get(20, [])) > 0:
            r3 = cat3_fwd[20]
            r1 = cat1_fwd[20]
            print(f"\n  Volatilidad 20d: CAT3 std={r3.std()*100:.2f}% vs CAT1 std={r1.std()*100:.2f}%")
            print(f"  ¿Explota CAT3? {'SÍ — más volátil' if r3.std() > r1.std() else 'NO — igual o menos volátil'}")

    print("\n═" * 70)
    print("ESQUELETO COMPLETADO — arquitectura validada a nivel estructural")
    print("═" * 70)


if __name__ == "__main__":
    main()
