#!/usr/bin/env python3
"""Extractor de overflows cinemáticos vela-a-vela desde el Vault.

Lee las series diarias COMPLETAS desde TimescaleDataStore (Neon PostgreSQL),
computa D1 (valor raw), D2 (diff(3) = velocidad 3d), D3 (std(2)/std(10) = turbulencia),
calcula z-scores contra STATION_MU_SIGMA, y extrae TODOS los eventos ≥2σ.

Luego cruza con los pivotes de zigzag de SPY para determinar:
  - ¿Cuántos overflows coinciden con un pivote (±3 días)?
  - ¿Cuántos NO coinciden? (overflows "libres" = señales continuas)
  - Forward returns a 1d/5d/10d/20d de cada overflow

Genera: data/research/signals/overflows_vela_a_vela.json
"""
import json
import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.sigma_overflow import STATION_MU_SIGMA

# Map station names to Vault tickers
STATION_TO_TICKER = {
    "vix": "VIX",
    "vvix": "VVIX",
    "pcr": "CBOE_PCR",
    "fg": "FG",
    "sv5_turbulence": "SV5_TURBULENCE",
    "skew": "SKEW",
    "credit": "CREDIT_RATIO",
    "yield_curve": "YIELD_SPREAD",
    "rotation": "ROTATION_INDEX",
    "dxy": "DXY",
    "bsi": "S5TW",  # Breadth ≈ S5TW (% above 20d MA)
}

DIM_LABELS = {
    "d1": "NIVEL",
    "d2": "VELOCIDAD_3D",
    "d3": "TURBULENCIA",
}


def extract_overflows_from_vault():
    store = TimescaleDataStore()

    # Load SPY for forward returns
    spy = store.load_bars("SPY", "1d")
    if spy is None or len(spy) == 0:
        print("ERROR: No SPY data in Vault")
        return
    spy = spy.sort_index()
    spy_close = spy["close"]

    # Compute SPY forward returns
    fwd_1d = spy_close.pct_change(1).shift(-1)
    fwd_5d = spy_close.pct_change(5).shift(-5)
    fwd_10d = spy_close.pct_change(10).shift(-10)
    fwd_20d = spy_close.pct_change(20).shift(-20)

    # Load zigzag pivots for cross-reference
    pivots_path = ROOT / "data" / "research" / "pivots" / "quants_obs.pkl"
    qo = pd.read_pickle(pivots_path)
    pivot_dates_raw = set(pd.to_datetime(qo["pivot_date"]).dt.tz_localize(None).dt.normalize())
    # Pre-expand to ±3 days for O(1) lookup
    pivot_window = set()
    for p in pivot_dates_raw:
        for delta in range(-3, 4):
            pivot_window.add(p + timedelta(days=delta))

    print(f"SPY: {len(spy)} barras ({spy.index[0].date()} → {spy.index[-1].date()})")
    print(f"Pivotes ZZ: {len(pivot_dates_raw)} fechas únicas ({len(pivot_window)} con ventana ±3d)")
    print()

    # Normalize SPY forward return indexes
    fwd_1d.index = fwd_1d.index.tz_localize(None).normalize()
    fwd_5d.index = fwd_5d.index.tz_localize(None).normalize()
    fwd_10d.index = fwd_10d.index.tz_localize(None).normalize()
    fwd_20d.index = fwd_20d.index.tz_localize(None).normalize()

    all_overflows = []
    summary = {}

    for station, dims in STATION_MU_SIGMA.items():
        ticker = STATION_TO_TICKER.get(station)
        if not ticker:
            print(f"  {station}: no Vault ticker mapped, SKIP")
            continue

        bars = store.load_bars(ticker, "1d")
        if bars is None or len(bars) < 30:
            print(f"  {station} ({ticker}): no data or <30 bars")
            continue

        bars = bars.sort_index()
        raw_val = bars["close"]  # D1 = close value

        for dim_name, (mu, sigma) in dims.items():
            if sigma <= 0:
                continue

            # Compute the dimension series
            if dim_name == "d1":
                series = raw_val
            elif dim_name == "d2":
                series = raw_val.diff(3)  # 3-day velocity
            elif dim_name == "d3":
                series = raw_val.rolling(2).std() / raw_val.rolling(10).std()
            else:
                continue

            series = series.dropna()
            if len(series) < 30:
                continue

            # Compute z-scores
            z = (series - mu) / sigma

            # Detect overflows
            ovf_mask_2s = z.abs() >= 2.0
            ovf_mask_3s = z.abs() >= 3.0
            n_2s = int(ovf_mask_2s.sum())
            n_3s = int(ovf_mask_3s.sum())

            if n_2s == 0:
                continue

            # Classify each overflow
            ovf_dates = z[ovf_mask_2s].index
            n_at_pivot = 0
            n_free = 0
            fwd_at_pivot = {"1d": [], "5d": [], "10d": [], "20d": []}
            fwd_free = {"1d": [], "5d": [], "10d": [], "20d": []}
            z_at_pivot = []
            z_free = []

            for dt in ovf_dates:
                dt_norm = pd.Timestamp(dt).tz_localize(None).normalize()
                is_near_pivot = dt_norm in pivot_window

                z_val = float(z.loc[dt])

                if is_near_pivot:
                    n_at_pivot += 1
                    z_at_pivot.append(z_val)
                    # Forward returns from SPY
                    if dt_norm in fwd_1d.index:
                        for horizon, fwd_series in [("1d", fwd_1d), ("5d", fwd_5d), ("10d", fwd_10d), ("20d", fwd_20d)]:
                            v = fwd_series.get(dt_norm)
                            if v is not None and not np.isnan(v):
                                fwd_at_pivot[horizon].append(float(v))
                else:
                    n_free += 1
                    z_free.append(z_val)
                    if dt_norm in fwd_1d.index:
                        for horizon, fwd_series in [("1d", fwd_1d), ("5d", fwd_5d), ("10d", fwd_10d), ("20d", fwd_20d)]:
                            v = fwd_series.get(dt_norm)
                            if v is not None and not np.isnan(v):
                                fwd_free[horizon].append(float(v))

            # Compute WR
            def _wr(arr):
                return round(float(np.mean([v > 0 for v in arr])), 4) if len(arr) >= 3 else None

            def _mean(arr):
                return round(float(np.mean(arr)), 6) if arr else None

            entry = {
                "estacion": station,
                "ticker_vault": ticker,
                "dimension": dim_name,
                "dim_label": DIM_LABELS[dim_name],
                "n_barras_total": int(len(series)),
                "n_overflow_2sigma": n_2s,
                "n_overflow_3sigma": n_3s,
                "pct_overflow": round(n_2s / len(series) * 100, 2),
                "z_mean": round(float(z[ovf_mask_2s].mean()), 2),
                "z_max_abs": round(float(z[ovf_mask_2s].abs().max()), 2),
                "n_upper": int((z[ovf_mask_2s] > 0).sum()),
                "n_lower": int((z[ovf_mask_2s] < 0).sum()),
                "en_pivote_zz_3d": {
                    "n": n_at_pivot,
                    "pct_del_total": round(n_at_pivot / n_2s * 100, 1) if n_2s > 0 else 0,
                    "z_mean": round(float(np.mean(z_at_pivot)), 2) if z_at_pivot else None,
                    "fwd_1d_wr": _wr(fwd_at_pivot["1d"]),
                    "fwd_5d_wr": _wr(fwd_at_pivot["5d"]),
                    "fwd_10d_wr": _wr(fwd_at_pivot["10d"]),
                    "fwd_20d_wr": _wr(fwd_at_pivot["20d"]),
                    "fwd_20d_mean": _mean(fwd_at_pivot["20d"]),
                },
                "libre_no_pivote": {
                    "n": n_free,
                    "pct_del_total": round(n_free / n_2s * 100, 1) if n_2s > 0 else 0,
                    "z_mean": round(float(np.mean(z_free)), 2) if z_free else None,
                    "fwd_1d_wr": _wr(fwd_free["1d"]),
                    "fwd_5d_wr": _wr(fwd_free["5d"]),
                    "fwd_10d_wr": _wr(fwd_free["10d"]),
                    "fwd_20d_wr": _wr(fwd_free["20d"]),
                    "fwd_20d_mean": _mean(fwd_free["20d"]),
                },
            }

            all_overflows.append(entry)
            print(f"  {station:18s}.{dim_name:3s} ({ticker:20s}) | N_bars={len(series):6d} | N_2σ={n_2s:5d} ({entry['pct_overflow']:.1f}%) | "
                  f"en_pivot={n_at_pivot:4d} ({entry['en_pivote_zz_3d']['pct_del_total']:.0f}%) | "
                  f"libres={n_free:4d} ({entry['libre_no_pivote']['pct_del_total']:.0f}%)")

    # Summary statistics
    total_2s = sum(e["n_overflow_2sigma"] for e in all_overflows)
    total_3s = sum(e["n_overflow_3sigma"] for e in all_overflows)
    total_pivot = sum(e["en_pivote_zz_3d"]["n"] for e in all_overflows)
    total_free = sum(e["libre_no_pivote"]["n"] for e in all_overflows)

    result = {
        "fuente": "Vault (TimescaleDataStore) — barras diarias completas",
        "metodo": "z = (valor - mu) / sigma con mu/sigma de STATION_MU_SIGMA (calibrados sobre población completa)",
        "total_overflows_2sigma": total_2s,
        "total_overflows_3sigma": total_3s,
        "total_en_pivote_zz_3d": total_pivot,
        "total_libres_no_pivote": total_free,
        "pct_en_pivote": round(total_pivot / total_2s * 100, 1) if total_2s > 0 else 0,
        "pct_libres": round(total_free / total_2s * 100, 1) if total_2s > 0 else 0,
        "eventos": all_overflows,
    }

    out_path = ROOT / "data" / "research" / "signals" / "overflows_vela_a_vela.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*80}")
    print(f"TOTAL: {total_2s} overflows ≥2σ | {total_3s} ≥3σ")
    print(f"  En pivotes ZZ (±3d): {total_pivot} ({result['pct_en_pivote']:.1f}%)")
    print(f"  Libres (no pivote):  {total_free} ({result['pct_libres']:.1f}%)")
    print(f"\nSalvado: {out_path}")


if __name__ == "__main__":
    extract_overflows_from_vault()
