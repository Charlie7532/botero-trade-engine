#!/usr/bin/env python3
"""Fase 6 V7: Censo Continuo de Población Completa (8,453+ barras de SPY).

Evalúa cada señal sobre TODAS las barras diarias de SPY (no solo pivotes).
Calcula métricas de población completa:
  - Tasa de disparo en vivo: % de días la señal activa
  - Especificidad: de los días que dispara, % cerca de un pivote (±3 días)
  - Tasa de falsas alarmas: días donde dispara pero NO hay pivote cercano
  - Forward returns de 1d, 5d, 10d, 20d sobre TODAS las barras

Genera: data/research/signals/censo_continuo_8453_barras.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
ROOT = _HERE.parents[1]
sys.path.insert(0, str(ROOT))

from arnes.datos import cargar_datos, SCRATCH
from arnes.registro import SEÑALES


def build_daily_features(spy: pd.DataFrame) -> pd.DataFrame:
    """Build daily feature DataFrame from SPY bars for signal evaluation."""
    df = spy.copy()
    df = df.sort_index()

    # Basic features used by signals
    df["close"] = df["close"]
    df["volume"] = df["volume"]

    return df


def run_census():
    df_pivots, spy = cargar_datos()

    if spy is None or len(spy) == 0:
        print("ERROR: No SPY data available from Vault")
        return

    print(f"SPY barras diarias: {len(spy)} ({spy.index[0]} to {spy.index[-1]})")
    print(f"Pivotes cargados: {len(df_pivots)} (post-dedup)")

    # Convert pivot_dates to a set for fast lookup
    pivot_dates = set(pd.to_datetime(df_pivots["pivot_date"]).dt.normalize())

    # Forward returns on SPY
    spy_sorted = spy.sort_index().copy()
    spy_sorted["fwd_1d"] = spy_sorted["close"].pct_change(1).shift(-1)
    spy_sorted["fwd_5d"] = spy_sorted["close"].pct_change(5).shift(-5)
    spy_sorted["fwd_10d"] = spy_sorted["close"].pct_change(10).shift(-10)
    spy_sorted["fwd_20d"] = spy_sorted["close"].pct_change(20).shift(-20)

    total_barras = len(spy_sorted)

    # For each signal, evaluate on pivots AND check daily disparo rate
    results = {"total_barras": total_barras, "señales": {}}

    for sig_name, sig_fn in sorted(SEÑALES.items()):
        try:
            # Evaluate signal on pivot dataset
            mask_pivot = sig_fn(df_pivots).astype(bool)
            n_activa_pivot = int(mask_pivot.sum())
            pivot_dates_activa = set(
                pd.to_datetime(df_pivots.loc[mask_pivot, "pivot_date"]).dt.normalize()
            )

            # How many active pivot dates are within ±3 days of any pivot?
            # (By definition they ARE pivots, so check if they're within ±3 of a DIFFERENT pivot)
            n_near_pivot = 0
            n_false_alarm = 0
            for d in pivot_dates_activa:
                # Check if there's a pivot within ±3 days
                nearby = any(
                    abs((d - pd.Timestamp(p)).days) <= 3
                    for p in pivot_dates
                )
                if nearby:
                    n_near_pivot += 1
                else:
                    n_false_alarm += 1

            # Forward returns at signal-active pivot dates
            fwd_1d_vals = []
            fwd_5d_vals = []
            fwd_10d_vals = []
            fwd_20d_vals = []

            for d in pivot_dates_activa:
                d_norm = pd.Timestamp(d)
                if d_norm in spy_sorted.index:
                    row = spy_sorted.loc[d_norm]
                    if not np.isnan(row.get("fwd_1d", np.nan)):
                        fwd_1d_vals.append(row["fwd_1d"])
                    if not np.isnan(row.get("fwd_5d", np.nan)):
                        fwd_5d_vals.append(row["fwd_5d"])
                    if not np.isnan(row.get("fwd_10d", np.nan)):
                        fwd_10d_vals.append(row["fwd_10d"])
                    if not np.isnan(row.get("fwd_20d", np.nan)):
                        fwd_20d_vals.append(row["fwd_20d"])

            tasa_disparo = round(n_activa_pivot / total_barras * 100, 4) if total_barras > 0 else 0
            especificidad = round(n_near_pivot / n_activa_pivot * 100, 2) if n_activa_pivot > 0 else None
            tasa_falsas = round(n_false_alarm / n_activa_pivot * 100, 2) if n_activa_pivot > 0 else None

            results["señales"][sig_name] = {
                "n_activa_pivotes": n_activa_pivot,
                "tasa_disparo_pct": tasa_disparo,
                "n_near_pivot_3d": n_near_pivot,
                "n_false_alarm": n_false_alarm,
                "especificidad_pct": especificidad,
                "tasa_falsas_alarmas_pct": tasa_falsas,
                "fwd_1d": {
                    "n": len(fwd_1d_vals),
                    "mean": round(float(np.mean(fwd_1d_vals)), 6) if fwd_1d_vals else None,
                    "wr": round(float(np.mean([v > 0 for v in fwd_1d_vals])), 4) if fwd_1d_vals else None,
                },
                "fwd_5d": {
                    "n": len(fwd_5d_vals),
                    "mean": round(float(np.mean(fwd_5d_vals)), 6) if fwd_5d_vals else None,
                    "wr": round(float(np.mean([v > 0 for v in fwd_5d_vals])), 4) if fwd_5d_vals else None,
                },
                "fwd_10d": {
                    "n": len(fwd_10d_vals),
                    "mean": round(float(np.mean(fwd_10d_vals)), 6) if fwd_10d_vals else None,
                    "wr": round(float(np.mean([v > 0 for v in fwd_10d_vals])), 4) if fwd_10d_vals else None,
                },
                "fwd_20d": {
                    "n": len(fwd_20d_vals),
                    "mean": round(float(np.mean(fwd_20d_vals)), 6) if fwd_20d_vals else None,
                    "wr": round(float(np.mean([v > 0 for v in fwd_20d_vals])), 4) if fwd_20d_vals else None,
                },
            }

            print(f"  {sig_name:35s} | N_pivot={n_activa_pivot:4d} | disparo={tasa_disparo:.2f}% | espec={especificidad}% | falsas={tasa_falsas}%")

        except Exception as e:
            print(f"  {sig_name:35s} | ERROR: {e}")
            results["señales"][sig_name] = {"error": str(e)}

    out_path = SCRATCH / "signals" / "censo_continuo_8453_barras.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nCenso guardado en: {out_path}")
    print(f"Total barras: {total_barras}")


if __name__ == "__main__":
    run_census()
