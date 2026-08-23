"""Estructura de mercado: vector sorpresa (fact stores), filtro structural momentum, contexto de pierna y régimen de divergencia.

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import json

import numpy as np
import pandas as pd

from .datos import ROOT

_FS_DIR = ROOT / "backend/modules/entry_decision/domain/rules"
_ESTACIONES = ["vix", "bsi", "fg", "credit", "rotation",
               "sv5_turbulence", "skew", "pcr", "vvix", "yield_curve", "dxy"]
_CAT = {
    "credit": 1, "yield_curve": 1, "dxy": 1, "rotation": 1,
    "vix": 2, "vvix": 2, "pcr": 2, "skew": 2,
    "bsi": 3, "sv5_turbulence": 3, "fg": 3,
}


def _surprise_vector(df):
    """surprise_i = -log2(N_estado / N_total) por estación. Retorna DataFrame."""
    out = {}
    for code in _ESTACIONES:
        fp = _FS_DIR / f"{code}_fact_store.json"
        if not fp.exists():
            out[code] = np.nan
            continue
        with open(fp) as f:
            fs = json.load(f)
        states = fs.get("states", {})
        n_total = sum(s.get("n", 0) or 0 for s in states.values())
        sk_col = f"{code}_sk"
        if sk_col not in df.columns:
            out[code] = np.nan
            continue
        n_by_sk = {sk: (s.get("n", 0) or 0) for sk, s in states.items()}
        vals = []
        for sk in df[sk_col]:
            n = n_by_sk.get(sk, 0)
            if n <= 0 or n_total <= 0:
                vals.append(np.nan)
            else:
                vals.append(-np.log2(n / n_total))
        out[code] = vals
    return pd.DataFrame(out, index=df.index)


def _structural_momentum_filter(señal, df, spy=None):
    """Clasifica momentum estructural (HL/LL para ENTRY, LH/HH para EXIT).
    HL = Higher Low → comprable. LL = Lower Low → TRAMPA bajista.
    LH = Lower High → deterioro. HH = Higher High → clímax de distribución.
    NOTA (validacion_5_interpretaciones_fact_store.md, P1): p_continuation y p_bull
    son ORTOGONALES (r=0.015). Reportar ambos por separado.
    Usa precios SPY en fechas de pivote para clasificar HL/LL y LH/HH correctamente.
    """
    rep_sm = {}
    if señal.sum() == 0:
        return rep_sm

    pivot_types_activos = df.loc[señal, "pivot_type"].unique()

    # Construir serie de precios SPY en fechas de pivote (si spy disponible)
    spy_close_at_pivot = None
    if spy is not None and "close" in spy.columns:
        try:
            closes = spy["close"]
            positions = closes.index.get_indexer(df["pivot_date"], method="nearest")
            spy_close_at_pivot = pd.Series(
                closes.iloc[positions].values, index=df.index
            )
            # Marcar NaN donde el indexer falló (-1)
            spy_close_at_pivot[positions == -1] = np.nan
        except Exception:
            spy_close_at_pivot = None

    # ENTRY (MIN pivots): HL vs LL
    if "MIN" in pivot_types_activos:
        min_mask = señal & (df["pivot_type"] == "MIN")
        min_idx = df.index[min_mask]

        if spy_close_at_pivot is not None and spy_close_at_pivot[min_mask].notna().sum() >= 5:
            # Clasificación por precio: MIN actual vs MIN anterior (en secuencia completa)
            all_min_idx = df.index[df["pivot_type"] == "MIN"]
            all_min_prices = spy_close_at_pivot[all_min_idx]
            # Para cada MIN activo en la señal, encontrar el MIN anterior en secuencia completa
            hl_count, ll_count = 0, 0
            for idx in min_idx:
                pos_in_all_min = all_min_idx.get_loc(idx)
                if pos_in_all_min == 0:
                    continue
                prev_min_idx = all_min_idx[pos_in_all_min - 1]
                p_curr = spy_close_at_pivot.get(idx)
                p_prev = spy_close_at_pivot.get(prev_min_idx)
                if p_curr is None or p_prev is None or pd.isna(p_curr) or pd.isna(p_prev):
                    continue
                if p_curr > p_prev:
                    hl_count += 1
                else:
                    ll_count += 1
            n_total = hl_count + ll_count
            if n_total > 0:
                rep_sm["entry"] = {
                    "n_hl": hl_count, "n_ll": ll_count, "n_total": n_total,
                    "p_hl": round(hl_count / n_total, 3),
                    "metodo": "precio SPY en pivotes MIN consecutivos",
                    "interpretacion": "HL = comprable. LL = TRAMPA (estructura bajista). "
                                      "p_hl y p_bull son ejes ORTOGONALES (r=0.015)."
                }
        else:
            # Fallback: heurística con prev_leg_return
            min_pivots = df[min_mask]
            prev_leg_shift = min_pivots["prev_leg_return"].shift(1)
            valid = prev_leg_shift.notna()
            hl_count = int((prev_leg_shift[valid] > 0).sum())
            ll_count = int((prev_leg_shift[valid] <= 0).sum())
            n_total = hl_count + ll_count
            if n_total > 0:
                rep_sm["entry"] = {
                    "n_hl": hl_count, "n_ll": ll_count, "n_total": n_total,
                    "p_hl": round(hl_count / n_total, 3),
                    "metodo": "heurística prev_leg_return (fallback)",
                    "interpretacion": "HL = comprable. LL = TRAMPA (estructura bajista). "
                                      "p_hl y p_bull son ejes ORTOGONALES (r=0.015)."
                }

    # EXIT (MAX pivots): LH vs HH
    if "MAX" in pivot_types_activos:
        max_mask = señal & (df["pivot_type"] == "MAX")
        max_idx = df.index[max_mask]

        if spy_close_at_pivot is not None and spy_close_at_pivot[max_mask].notna().sum() >= 5:
            all_max_idx = df.index[df["pivot_type"] == "MAX"]
            all_max_prices = spy_close_at_pivot[all_max_idx]
            lh_count, hh_count = 0, 0
            for idx in max_idx:
                pos_in_all_max = all_max_idx.get_loc(idx)
                if pos_in_all_max == 0:
                    continue
                prev_max_idx = all_max_idx[pos_in_all_max - 1]
                p_curr = spy_close_at_pivot.get(idx)
                p_prev = spy_close_at_pivot.get(prev_max_idx)
                if p_curr is None or p_prev is None or pd.isna(p_curr) or pd.isna(p_prev):
                    continue
                if p_curr < p_prev:
                    lh_count += 1
                else:
                    hh_count += 1
            n_total = lh_count + hh_count
            if n_total > 0:
                rep_sm["exit"] = {
                    "n_lh": lh_count, "n_hh": hh_count, "n_total": n_total,
                    "p_hh": round(hh_count / n_total, 3),
                    "metodo": "precio SPY en pivotes MAX consecutivos",
                    "interpretacion": "HH cae 90.2% de las veces (33años SPY N=429). "
                                      "AMPLIFICAR EXIT en HH. LH cae 75.3% (N=364)."
                }
        else:
            # Fallback: heurística con prev_leg_return
            max_pivots = df[max_mask]
            prev_leg_shift = max_pivots["prev_leg_return"].shift(1)
            valid = prev_leg_shift.notna()
            lh_count = int((prev_leg_shift[valid] < 0).sum())
            hh_count = int((prev_leg_shift[valid] >= 0).sum())
            n_total = lh_count + hh_count
            if n_total > 0:
                rep_sm["exit"] = {
                    "n_lh": lh_count, "n_hh": hh_count, "n_total": n_total,
                    "p_hh": round(hh_count / n_total, 3),
                    "metodo": "heurística prev_leg_return (fallback)",
                    "interpretacion": "HH cae 90.2% de las veces (33años SPY N=429). "
                                      "AMPLIFICAR EXIT en HH. LH cae 75.3% (N=364)."
                }
    return rep_sm


# ─── ADDENDUM 2: Prev Leg Domino (Lookback) ───
def _prev_leg_context(señal, fwd, df):
    """Contexto de la pierna previa: ¿venimos de un crash (>P90) o de un drift normal?
    NOTA (validacion_5_interpretaciones_fact_store.md, P2): umbral >50% es inalcanzable
    en VIX (0/47 estados). Usar >20% o >30% como umbral operativo.
    """
    abs_prev = df["prev_leg_return"].abs()
    p90_thr = float(np.percentile(abs_prev.dropna(), 90))

    prev_leg_act = abs_prev[señal].dropna()
    n_extreme = int((prev_leg_act > p90_thr).sum())
    n_normal = int((prev_leg_act <= p90_thr).sum())

    rep_plc = {
        "p90_threshold_abs_return": round(p90_thr, 4),
        "n_extreme_prev_leg": n_extreme,
        "n_normal_prev_leg": n_normal,
        "pct_extreme": round(n_extreme / len(prev_leg_act), 3) if len(prev_leg_act) > 0 else 0,
        "umbral_operativo": ">20% o >30% (el >50% es inalcanzable en VIX fact store)",
        "interpretacion": "pct_extreme alto = señal activada post-crash. Edge amplificado."
    }

    # Desglose forward por contexto (solo si ambos tienen n>=3)
    if n_extreme >= 3 and n_normal >= 3:
        fwd_extreme = fwd[señal & (abs_prev > p90_thr) & fwd.notna()]
        fwd_normal = fwd[señal & (abs_prev <= p90_thr) & fwd.notna()]
        if len(fwd_extreme) > 0:
            rep_plc["forward_extreme_prev"] = {
                "n": int(len(fwd_extreme)),
                "mean": round(float(np.nanmean(fwd_extreme)), 4),
                "win_rate": round(float((fwd_extreme > 0).mean()), 3)
            }
        if len(fwd_normal) > 0:
            rep_plc["forward_normal_prev"] = {
                "n": int(len(fwd_normal)),
                "mean": round(float(np.nanmean(fwd_normal)), 4),
                "win_rate": round(float((fwd_normal > 0).mean()), 3)
            }
    return rep_plc


# ─── ADDENDUM 3: Temporal Divergence Regime ───
def _divergence_regime(rep):
    """Clasifica convergencia/divergencia entre las 3 escalas zigzag.
    CONCEPTO DERIVADO: el fact store NO tiene este campo. Se deriva
    comparando p_bull en las 3 escalas (zz25/zz50/zz75).
    """
    tr = rep.get("triada", {})
    zz25_wr = tr.get("zz25", {}).get("win_rate", 0.0)
    c50 = tr.get("cascade_50", {}).get("rate_activa", 0.0)
    c75 = tr.get("cascade_75", {}).get("rate_activa", 0.0)
    n_activo = tr.get("zz25", {}).get("n", 0)

    # PROTOCOLO DIAMANTES (fact_store_v3_architecture.md §3.3):
    # N bajo ≠ descartable. Los eventos raros son diamantes estadísticos
    # que se analizan por separado, listando cada evento individualmente
    # con la tasa CRUDA (sin shrinkage agresivo).
    if n_activo < 3:
        return {
            "regime": "DIAMANTE_ANECDOTAL",
            "tier": "ANECDOTAL (N=1-2)" if n_activo >= 1 else "NONE (N=0)",
            "n_activo": n_activo,
            "interpretacion": "Diamante estadístico: el evento existe y tuvo un resultado "
                              "específico, pero no permite inferencia probabilística. "
                              "Analizar CADA evento individualmente (fecha, contexto, resultado). "
                              "NUNCA descartar por N bajo.",
            "zz25_wr": round(zz25_wr, 4),
            "cascade_50_rate": round(c50, 4),
            "cascade_75_rate": round(c75, 4),
            "fuente": "fact_store_v3_architecture.md §3.3 — Diamantes Estadísticos."
        }

    # Umbrales calibrados contra datos reales (20-Ago-2026):
    #   credit_easing_k1: WR=93.8%, c50=53.6%, c75=32.1% → FULL_CONVERGENT_BULL
    #   sub_reaccion:     WR=50.2%, c50=40.8%, c75=20.5% → MIXED_HORIZON_TRANSITION
    if zz25_wr > 0.55 and c50 > 0.50 and c75 > 0.28:
        regime = "FULL_CONVERGENT_BULL"
        interp = "Las 3 escalas confirman: señal ALCISTA en retracción, corrección y depresión."
    elif zz25_wr < 0.45 and c50 < 0.45 and c75 < 0.30:
        regime = "FULL_CONVERGENT_BEAR"
        interp = "Las 3 escalas confirman: señal BAJISTA en todas las dimensiones."
    elif zz25_wr > 0.55 and c50 < 0.45:
        regime = "TACTICAL_ONLY"
        interp = "Funciona en zz25 pero NO escala a zz50. Movimiento táctico contenido."
    elif zz25_wr < 0.50 and c50 > 0.55:
        regime = "STRUCTURAL_BUILDUP"
        interp = "Ambigua en zz25 pero SÍ escala a zz50. Mercado preparándose para movimiento mayor."
    elif c50 > 0.50 and c75 < 0.25:
        regime = "CORRECTION_CONTAINED"
        interp = "Corrección intermedia pero NO depresión. Contenido en zz50."
    else:
        regime = "MIXED_HORIZON_TRANSITION"
        interp = "Las escalas no convergen — transición entre regímenes."

    return {
        "regime": regime,
        "interpretacion": interp,
        "zz25_wr": round(zz25_wr, 4),
        "cascade_50_rate": round(c50, 4),
        "cascade_75_rate": round(c75, 4),
        "fuente": "CONCEPTO DERIVADO — el fact store NO tiene este campo nativo."
    }
