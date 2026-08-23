"""Métricas de timing: MAE intra-trade, costo de comprar tarde, sensibilidad al retraso.

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import numpy as np
import pandas as pd  # noqa: F401

def _mae_intratrade(spy, señal, df):
    """MAE intra-trade real (máxima excursión adversa usando el Low del Vault).
    MAE_i = min_{t in [T0, T1]} (Low_t - Close_T0) / Close_T0, ≤ 0.
    T0 = fecha del pivote de señal, T1 = fecha del pivote siguiente en quants_obs.
    """
    if spy is None:
        return []
    maes = []
    for i in np.where(señal.values)[0]:
        t0 = df["pivot_date"].iloc[i]
        t1 = df["pivot_date"].iloc[i + 1] if i + 1 < len(df) else None
        loc0 = spy.index.searchsorted(t0)
        if loc0 >= len(spy):
            continue
        loc1 = spy.index.searchsorted(t1) if t1 is not None else len(spy) - 1
        if loc1 < loc0:
            loc1 = loc0
        slice_df = spy.iloc[loc0 : loc1 + 1]
        if len(slice_df) == 0:
            continue
        c0 = float(spy["close"].iloc[loc0])
        min_low = float(slice_df["low"].min())
        mae = (min_low - c0) / c0
        maes.append(mae)
    return maes


def _costo_tarde(spy, señal, df, k=1):
    """Costo medio de retrasar la entrada k barras, por trade.
    ΔOpportunity_i(k) = (Close[T0+k] - Close[T0]) / Close[T0]
    (el retorno que se pierde por esperar k barras tras la señal).
    """
    if spy is None:
        return {"n": 0, "costo_medio": None}
    costos = []
    for i in np.where(señal.values)[0]:
        t0 = df["pivot_date"].iloc[i]
        loc = spy.index.searchsorted(t0)
        if loc + k >= len(spy):
            continue
        c0 = float(spy["close"].iloc[loc])
        ck = float(spy["close"].iloc[loc + k])
        costos.append((ck - c0) / c0)
    if not costos:
        return {"n": 0, "costo_medio": None}
    return {
        "n": int(len(costos)),
        "costo_medio": float(np.mean(costos)),
        "p50": float(np.median(costos)),
        "p5": float(np.percentile(costos, 5)),
        "p95": float(np.percentile(costos, 95)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. SENSIBILIDAD AL TIMING (BARRAS DIARIAS CONTINUAS)
# ─────────────────────────────────────────────────────────────────────────────
def _sensibilidad_timing(spy, señal, df, ks=(0, 1, 2, 3, 5)):
    """Para cada k de retraso en BARRAS, medir el forward retorno medio
    si la entrada se ejecuta k barras después de la señal.
    forward_k_i = (Close[T1] - Close[T0+k]) / Close[T0+k].
    """
    if spy is None:
        return []
    res = []
    for k in ks:
        rets = []
        for i in np.where(señal.values)[0]:
            t0 = df["pivot_date"].iloc[i]
            t1 = df["pivot_date"].iloc[i + 1] if i + 1 < len(df) else None
            loc0 = spy.index.searchsorted(t0)
            loc_k = loc0 + k
            loc1 = spy.index.searchsorted(t1) if t1 is not None else len(spy) - 1
            if loc_k >= len(spy) or loc1 >= len(spy) or loc_k > loc1:
                continue
            c_k = float(spy["close"].iloc[loc_k])
            c_1 = float(spy["close"].iloc[loc1])
            ret_k = (c_1 - c_k) / c_k
            rets.append(ret_k)
        if len(rets) < 20:
            res.append({"k": int(k), "n": int(len(rets)), "mean": None})
        else:
            res.append({"k": int(k), "n": int(len(rets)), "mean": float(np.nanmean(rets))})
    return res
