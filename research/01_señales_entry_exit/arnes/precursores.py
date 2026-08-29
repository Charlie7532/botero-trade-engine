"""Análisis de señales precursoras t-1 / t-2 para cada señal.

Fase 3 del Plan V7: consume las 22 columnas {station}_sk_t1 y {station}_sk_t2
que ya existen en quants_obs.pkl pero nunca se integraron en medicion.py.

Para cada señal activa, identifica:
- El estado D1×D2×D3 dominante en t-1 y t-2
- La transición más frecuente (t-2 → t-1 → t-0)
- Si el precursor amplifica o cancela el edge de la señal
"""
import numpy as np
import pandas as pd


STATIONS = [
    "vix", "vvix", "bsi", "credit", "pcr", "fg",
    "skew", "rotation", "dxy", "sv5_turbulence", "yield_curve",
]


def analizar_precursores(señal_mask, df, fwd, min_n=5):
    """Analiza los estados precursores t-1 y t-2 para una señal activa.

    Args:
        señal_mask: boolean Series indicating signal active days
        df: DataFrame with _sk, _sk_t1, _sk_t2 columns
        fwd: forward return Series
        min_n: minimum observations for reporting

    Returns:
        dict with per-station precursor analysis
    """
    result = {}
    act_fwd = fwd[señal_mask & fwd.notna()]
    wr_global = float((act_fwd > 0).mean()) if len(act_fwd) >= 5 else 0.5

    for station in STATIONS:
        sk_t0 = f"{station}_sk"
        sk_t1 = f"{station}_sk_t1"
        sk_t2 = f"{station}_sk_t2"

        # Skip if precursor columns don't exist
        if sk_t1 not in df.columns or sk_t2 not in df.columns:
            continue

        # Get precursor states for signal-active rows
        t1_series = df.loc[señal_mask, sk_t1].dropna()
        t2_series = df.loc[señal_mask, sk_t2].dropna()

        if len(t1_series) < min_n:
            continue

        # t-1 dominant state
        t1_counts = t1_series.value_counts()
        t1_dom = t1_counts.index[0]
        t1_dom_n = int(t1_counts.iloc[0])
        t1_dom_pct = round(t1_dom_n / len(t1_series) * 100, 1)

        # WR when t-1 is the dominant state vs when it's not
        t1_dom_mask = señal_mask & (df[sk_t1] == t1_dom)
        t1_dom_fwd = fwd[t1_dom_mask & fwd.notna()]
        t1_dom_wr = float((t1_dom_fwd > 0).mean()) if len(t1_dom_fwd) >= 3 else None

        t1_other_mask = señal_mask & (df[sk_t1] != t1_dom) & df[sk_t1].notna()
        t1_other_fwd = fwd[t1_other_mask & fwd.notna()]
        t1_other_wr = float((t1_other_fwd > 0).mean()) if len(t1_other_fwd) >= 3 else None

        # Delta WR: does the dominant precursor amplify or cancel?
        delta_wr = None
        amplifica = None
        if t1_dom_wr is not None and t1_other_wr is not None:
            delta_wr = round(t1_dom_wr - t1_other_wr, 4)
            amplifica = delta_wr > 0.05  # precursor amplifies if WR improves >5pp

        # t-2 dominant state
        t2_dom = None
        t2_dom_n = 0
        if len(t2_series) >= min_n:
            t2_counts = t2_series.value_counts()
            t2_dom = t2_counts.index[0]
            t2_dom_n = int(t2_counts.iloc[0])

        # D1 transition (extract just D1 from full state_key)
        t1_d1 = t1_series.str.split("__").str[0]
        t0_d1 = df.loc[señal_mask, sk_t0].dropna().str.split("__").str[0]
        t2_d1 = t2_series.str.split("__").str[0] if len(t2_series) >= min_n else pd.Series(dtype=str)

        # Most frequent D1 transition chain
        transition = None
        if len(t2_d1) >= min_n and len(t1_d1) >= min_n and len(t0_d1) >= min_n:
            t2_top = t2_d1.value_counts().index[0] if len(t2_d1) else "?"
            t1_top = t1_d1.value_counts().index[0] if len(t1_d1) else "?"
            t0_top = t0_d1.value_counts().index[0] if len(t0_d1) else "?"
            transition = f"{t2_top} → {t1_top} → {t0_top}"

        entry = {
            "t1_dominante": t1_dom,
            "t1_n": t1_dom_n,
            "t1_pct": t1_dom_pct,
            "t1_wr_con_precursor": t1_dom_wr,
            "t1_wr_sin_precursor": t1_other_wr,
            "delta_wr_precursor": delta_wr,
            "amplifica": amplifica,
            "t2_dominante": t2_dom,
            "t2_n": t2_dom_n,
            "transicion_d1_frecuente": transition,
        }
        result[station] = entry

    return result if result else None
