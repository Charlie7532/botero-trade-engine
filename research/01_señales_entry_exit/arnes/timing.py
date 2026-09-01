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


# ─────────────────────────────────────────────────────────────────────────────
# 7. CALIFICACIÓN CANÓNICA DE TIMING EN 6 SLOTS (HOMOLOGACIÓN INSTITUCIONAL)
# ─────────────────────────────────────────────────────────────────────────────
SLOT_ORDER = ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]


def classify_single_delta(sd: int) -> str:
    """Clasifica un delta temporal (signal_date - pivot_date en días/barras) en los 6 slots canónicos:
    - sd == 0:  't=0'   (Exacta / En punto)
    - sd == -1: 't-1'   (Anticipada 1 vela)
    - sd == -2: 't-2'   (Anticipada 2 velas)
    - sd == 1:  't+1'   (Retrasada 1 vela)
    - sd == 2:  't+2'   (Retrasada 2 velas)
    - else:     'ENTRE' (FUERA DE RANGO / Ruido intra-tramo)
    """
    return {0: "t=0", -1: "t-1", -2: "t-2", 1: "t+1", 2: "t+2"}.get(sd, "ENTRE")


def classify_timing_slots(signal_dates, pivot_dates, pivot_types=None, target_pivot_type=None, trading_index=None):
    """Clasifica un array de fechas de señal respecto a los pivotes ZigZag más cercanos.

    Args:
        signal_dates: array-like de datetime / Timestamp (fechas de disparo)
        pivot_dates: array-like de datetime / Timestamp (fechas de pivotes ZZ)
        pivot_types: array-like de str ("MIN" / "MAX"), opcional
        target_pivot_type: "MIN", "MAX" o None (para filtrar solo pivotes del tipo de interés)
        trading_index: pd.DatetimeIndex o array de fechas de trading continuas (ej. spy.index).
                       Si se provee, la distancia se calcula en BARRAS DE TRADING (velas).
                       Si es None, se calcula en días calendario.

    Returns:
        DataFrame con columnas:
          - signal_date
          - nearest_pivot_date
          - pivot_type
          - delta_days (o delta_bars si trading_index provisto)
          - slot ('t-2', 't-1', 't=0', 't+1', 't+2', 'ENTRE')
          - categoria ('ANTICIPADA', 'EXACTA', 'RETRASADA', 'FUERA_DE_RANGO')
    """
    if len(signal_dates) == 0 or len(pivot_dates) == 0:
        return pd.DataFrame(columns=["signal_date", "nearest_pivot_date", "pivot_type", "delta_days", "slot", "categoria"])

    sig_dt = pd.DatetimeIndex(pd.to_datetime(signal_dates)).normalize()
    piv_dt = pd.DatetimeIndex(pd.to_datetime(pivot_dates)).normalize()

    # Filtrar por tipo si se solicita
    if target_pivot_type is not None and pivot_types is not None:
        mask_t = np.array([pt == target_pivot_type for pt in pivot_types])
        piv_dt = piv_dt[mask_t]
        piv_types_arr = np.array(pivot_types)[mask_t]
    else:
        piv_types_arr = np.array(pivot_types) if pivot_types is not None else np.array(["?"] * len(piv_dt))

    if len(piv_dt) == 0:
        return pd.DataFrame(columns=["signal_date", "nearest_pivot_date", "pivot_type", "delta_days", "slot", "categoria"])

    # Ordenar pivotes
    sort_idx = np.argsort(piv_dt)
    piv_dt_sorted = piv_dt[sort_idx]
    piv_types_sorted = piv_types_arr[sort_idx]

    if trading_index is not None:
        t_idx = pd.DatetimeIndex(trading_index).normalize()
        sig_pos = t_idx.searchsorted(sig_dt)
        piv_pos = t_idx.searchsorted(piv_dt_sorted)

        idxs = np.searchsorted(piv_pos, sig_pos)
        idxs_c = np.clip(idxs, 0, len(piv_pos) - 1)
        idxs_p = np.clip(idxs - 1, 0, len(piv_pos) - 1)

        d_prev = sig_pos - piv_pos[idxs_p]   # signal - prev_pivot >= 0
        d_next = sig_pos - piv_pos[idxs_c]   # signal - next_pivot <= 0
    else:
        sig_int = sig_dt.values.astype("datetime64[D]").astype(int)
        piv_int = piv_dt_sorted.values.astype("datetime64[D]").astype(int)

        idxs = np.searchsorted(piv_int, sig_int)
        idxs_c = np.clip(idxs, 0, len(piv_int) - 1)
        idxs_p = np.clip(idxs - 1, 0, len(piv_int) - 1)

        d_prev = sig_int - piv_int[idxs_p]   # signal - prev_pivot >= 0
        d_next = sig_int - piv_int[idxs_c]   # signal - next_pivot <= 0

    best_delta = np.where(np.abs(d_prev) < np.abs(d_next), d_prev, d_next)
    best_piv_idx = np.where(np.abs(d_prev) < np.abs(d_next), idxs_p, idxs_c)

    slots = np.array([classify_single_delta(int(d)) for d in best_delta])

    def _cat(sl):
        if sl in ("t-2", "t-1"): return "ANTICIPADA"
        elif sl == "t=0": return "EXACTA"
        elif sl in ("t+1", "t+2"): return "RETRASADA"
        else: return "FUERA_DE_RANGO"

    categorias = np.array([_cat(sl) for sl in slots])

    return pd.DataFrame({
        "signal_date": sig_dt,
        "nearest_pivot_date": piv_dt_sorted[best_piv_idx],
        "pivot_type": piv_types_sorted[best_piv_idx],
        "delta_days": best_delta,
        "slot": slots,
        "categoria": categorias,
    })


def calc_timing_distribution(signal_dates, pivot_dates, pivot_types=None, target_pivot_type=None, trading_index=None) -> dict:
    """Calcula el resumen estadístico homologado de timing en 6 slots."""
    df_timing = classify_timing_slots(signal_dates, pivot_dates, pivot_types, target_pivot_type, trading_index=trading_index)
    n_total = len(df_timing)
    if n_total == 0:
        return {
            "n_total": 0,
            "counts": {s: 0 for s in SLOT_ORDER},
            "pcts": {s: 0.0 for s in SLOT_ORDER},
            "n_en_rango": 0, "pct_en_rango": 0.0,
            "n_anticipada": 0, "pct_anticipada": 0.0,
            "n_exacta": 0, "pct_exacta": 0.0,
            "n_retrasada": 0, "pct_retrasada": 0.0,
            "n_fuera": 0, "pct_fuera": 0.0,
        }

    counts = {s: int((df_timing["slot"] == s).sum()) for s in SLOT_ORDER}
    pcts = {s: round(counts[s] / n_total * 100, 2) for s in SLOT_ORDER}

    n_ant = counts["t-2"] + counts["t-1"]
    n_exa = counts["t=0"]
    n_ret = counts["t+1"] + counts["t+2"]
    n_fue = counts["ENTRE"]
    n_rng = n_ant + n_exa + n_ret

    deltas_abs = np.abs(df_timing["delta_days"].values)

    return {
        "n_total": n_total,
        "counts": counts,
        "pcts": pcts,
        "n_en_rango": n_rng, "pct_en_rango": round(n_rng / n_total * 100, 2),
        "n_anticipada": n_ant, "pct_anticipada": round(n_ant / n_total * 100, 2),
        "n_exacta": n_exa, "pct_exacta": round(n_exa / n_total * 100, 2),
        "n_retrasada": n_ret, "pct_retrasada": round(n_ret / n_total * 100, 2),
        "n_fuera": n_fue, "pct_fuera": round(n_fue / n_total * 100, 2),
        "delta_medio": round(float(np.mean(deltas_abs)), 1),
        "delta_mediana": round(float(np.median(deltas_abs)), 1),
    }

