"""Motor de medición: medir() — arnés estándar completo por señal; medir_cross_overlap().

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import numpy as np
import pandas as pd
from pathlib import Path

from .registro import SEÑALES, _CERTEZA
from .estadisticas import (_pctiles, _wins_losses, _bootstrap_ci, _lift_vs_baseline,
                           _clopper_pearson_ci, _fisher_pvalue)

# ── Market Structural Cycles (NOT calendar decades) ──────────────────────────
# Markets move by crisis-to-crisis regimes, not by arbitrary 10-year blocks.
MARKET_CYCLES = {
    "1_DotCom_Expansion": (1993, 2000),   # Tech expansion, positive rates
    "2_DotCom_Crash":     (2000, 2003),   # Structural tech collapse
    "3_Credit_Housing":   (2003, 2007),   # Housing bubble, bank leverage
    "4_GFC":              (2007, 2009),   # Global Financial Crisis, liquidity freeze
    "5_QE_ZIRP":          (2009, 2020),   # Fed Put, volatility suppression, ZIRP
    "6_COVID_Injection":  (2020, 2022),   # Flash panic + massive liquidity injection
    "7_QT_PostQE":        (2022, 2027),   # Inflation shock, rate hikes, sector dispersion
}
MACRO_ERAS = {
    "Pre_QE":   (1993, 2009),
    "QE_Era":   (2009, 2022),
    "Post_QE":  (2022, 2027),
}
from .timing import _mae_intratrade, _costo_tarde, _sensibilidad_timing
from .estructura import (_surprise_vector, _structural_momentum_filter,
                         _prev_leg_context, _divergence_regime)

def medir(señal_nombre, df, forward_col, spy=None, n_iter=3000, seed=42):
    if señal_nombre not in SEÑALES:
        raise ValueError(f"Señal desconocida: {señal_nombre}. Disponibles: {list(SEÑALES)}")
    señal = SEÑALES[señal_nombre](df)
    señal = señal.astype(bool)

    # forward: retorno de la pierna siguiente (default) o columna especificada
    if forward_col == "next_leg":
        fwd = df["prev_leg_return"].shift(-1)
    elif forward_col in df.columns:
        fwd = df[forward_col]
    else:
        raise ValueError(f"Columna forward desconocida: {forward_col}")

    rep = {"señal": señal_nombre, "forward": forward_col, "n_total": int(len(df))}

    # 4.1 distribución + wins/losses, señal activa vs baseline condicionado
    act = fwd[señal & fwd.notna()]

    # Baseline condicionado al mismo pivot_type (evita mezclar piernas bajistas en señales MIN)
    pivot_señal = df.loc[señal, "pivot_type"].unique()
    if len(pivot_señal) > 0 and len(pivot_señal) < len(df["pivot_type"].unique()):
        mask_base = (~señal) & df["pivot_type"].isin(pivot_señal) & fwd.notna()
        baseline_type = list(pivot_señal) if len(pivot_señal) > 1 else str(pivot_señal[0])
    else:
        mask_base = (~señal) & fwd.notna()
        baseline_type = "ALL"

    base = fwd[mask_base]
    rep["activa"] = {"dist": _pctiles(act), "wl": _wins_losses(act),
                     "ci_mean": _bootstrap_ci(np.mean, act, n_iter, seed)}
    rep["baseline"] = {"dist": _pctiles(base), "wl": _wins_losses(base)}
    rep["baseline_pivot_type"] = baseline_type
    if len(act) and len(base):
        rep["delta_media"] = float(np.nanmean(act) - np.nanmean(base))

    # 4.2 drawdown de timing (MAE intra-trade real, solo señal activa)
    maes = _mae_intratrade(spy, señal, df)
    rep["timing_temprano"] = {"estadistica": _pctiles(maes)}

    # 4.3 costo de oportunidad de entrar tarde (por trade)
    rep["costo_tarde"] = _costo_tarde(spy, señal, df, k=1)

    # 4.4 sensibilidad al timing (retraso en barras diarias continuas)
    rep["sensibilidad"] = _sensibilidad_timing(spy, señal, df, ks=(0, 1, 2, 3, 5))

    # 4.5 Medición por escala triádica: zz25, cascade_50, cascade_75, duration_bars
    c50_act = df.loc[señal, "cascade_50"].dropna()
    c50_base = df.loc[mask_base, "cascade_50"].dropna()
    c75_act = df.loc[señal, "cascade_75"].dropna()
    c75_base = df.loc[mask_base, "cascade_75"].dropna()
    dur_act = df.loc[señal, "duration_bars"].dropna()
    dur_base = df.loc[mask_base, "duration_bars"].dropna()

    c50_rate_act = float(c50_act.mean()) if len(c50_act) else 0.0
    c50_rate_base = float(c50_base.mean()) if len(c50_base) else 0.0
    c75_rate_act = float(c75_act.mean()) if len(c75_act) else 0.0
    c75_rate_base = float(c75_base.mean()) if len(c75_base) else 0.0

    rep["triada"] = {
        "zz25": {
            "mean": float(np.nanmean(act)) if len(act) else 0.0,
            "median": float(np.nanmedian(act)) if len(act) else 0.0,
            "win_rate": float((act > 0).mean()) if len(act) else 0.0,
            "n": int(len(act)),
        },
        "cascade_50": {
            "rate_activa": c50_rate_act,
            "rate_baseline": c50_rate_base,
            "delta": float(c50_rate_act - c50_rate_base),
            "n": int(len(c50_act)),
        },
        "cascade_75": {
            "rate_activa": c75_rate_act,
            "rate_baseline": c75_rate_base,
            "delta": float(c75_rate_act - c75_rate_base),
            "n": int(len(c75_act)),
        },
        "duracion_bars": {
            "mean": float(dur_act.mean()) if len(dur_act) else 0.0,
            "median": float(dur_act.median()) if len(dur_act) else 0.0,
            "baseline_mean": float(dur_base.mean()) if len(dur_base) else 0.0,
            "n": int(len(dur_act)),
        },
    }

    # 4.5b Desglose short/long por duration_bars
    if señal.sum() > 0 and "duration_bars" in df.columns:
        dur_sig = df.loc[señal, "duration_bars"].dropna()
        if len(dur_sig) >= 10:
            median_dur = float(dur_sig.median())
            cortas = señal & (df["duration_bars"] <= median_dur)
            largas = señal & (df["duration_bars"] > median_dur)
            fwd_cortas = fwd[cortas & fwd.notna()]
            fwd_largas = fwd[largas & fwd.notna()]
            rep["duracion_desglose"] = {
                "mediana_bars": round(median_dur, 1),
                "cortas": {
                    "n": int(len(fwd_cortas)),
                    "fwd_mean": round(float(np.nanmean(fwd_cortas)), 6) if len(fwd_cortas) else None,
                    "wr": round(float((fwd_cortas > 0).mean()), 4) if len(fwd_cortas) else None,
                },
                "largas": {
                    "n": int(len(fwd_largas)),
                    "fwd_mean": round(float(np.nanmean(fwd_largas)), 6) if len(fwd_largas) else None,
                    "wr": round(float((fwd_largas > 0).mean()), 4) if len(fwd_largas) else None,
                },
                "delta": round(float(np.nanmean(fwd_cortas) - np.nanmean(fwd_largas)), 6) if len(fwd_cortas) and len(fwd_largas) else None,
            }
        else:
            rep["duracion_desglose"] = None
    else:
        rep["duracion_desglose"] = None

    # 4.6 Anticipación temporal: días antes del pivot en que la señal ya estaba activa
    señal_shift1 = señal.shift(1, fill_value=False)
    señal_shift_1 = señal.shift(-1, fill_value=False)

    if señal.sum() > 0:
        anticipaciones_dias = []
        for i in np.where(señal.values)[0]:
            pivot_date_actual = df["pivot_date"].iloc[i]
            # Buscar pivote anterior con señal activa
            pivote_anterior_idx = None
            for j in range(i - 1, -1, -1):
                if señal.iloc[j]:
                    pivote_anterior_idx = j
                    break
            if pivote_anterior_idx is not None:
                fecha_anterior = df["pivot_date"].iloc[pivote_anterior_idx]
                dias_antes = (pivot_date_actual - fecha_anterior).days
            else:
                dias_antes = 0
            anticipaciones_dias.append(dias_antes)

        anticipaciones_arr = np.array(anticipaciones_dias)
        n_total = int(len(anticipaciones_dias))
        n_anticipados = int((anticipaciones_arr > 0).sum())
        rep["anticipacion_zigzag"] = {
            "mean_dias": round(float(np.mean(anticipaciones_arr)), 2),
            "median_dias": round(float(np.median(anticipaciones_arr)), 2),
            "p5_dias": round(float(np.percentile(anticipaciones_arr, 5)), 2),
            "p25_dias": round(float(np.percentile(anticipaciones_arr, 25)), 2),
            "p75_dias": round(float(np.percentile(anticipaciones_arr, 75)), 2),
            "p95_dias": round(float(np.percentile(anticipaciones_arr, 95)), 2),
            "n_total": n_total,
            "n_anticipados": n_anticipados,
            "pct_anticipados": round(float((anticipaciones_arr > 0).mean() * 100), 1),
        }
    else:
        rep["anticipacion_zigzag"] = None

    # 4.7 Capture ratio: forward_return / abs(prev_leg_return), separado por pivot_type
    zz25_act = act
    zz25_leg = df.loc[señal, "prev_leg_return"].dropna()
    if len(zz25_act) > 0 and len(zz25_leg) > 0:
        abs_leg_mean = float(np.nanmean(np.abs(zz25_leg)))
        fwd_mean = float(np.nanmean(zz25_act))
        cr_global = fwd_mean / abs_leg_mean if abs_leg_mean > 1e-8 else 0.0
        # Per pivot_type breakdown
        cr_by_type = {}
        for pt_val in df.loc[señal, "pivot_type"].unique():
            pt_mask = señal & (df["pivot_type"] == pt_val)
            pt_fwd = fwd[pt_mask & fwd.notna()]
            pt_leg = df.loc[pt_mask, "prev_leg_return"].dropna()
            if len(pt_fwd) >= 5 and len(pt_leg) >= 5:
                abs_leg = float(np.nanmean(np.abs(pt_leg)))
                pt_fwd_mean = float(np.nanmean(pt_fwd))
                cr_by_type[pt_val] = {
                    "ratio": round(pt_fwd_mean / abs_leg if abs_leg > 1e-8 else 0.0, 4),
                    "fwd_mean": round(pt_fwd_mean, 6),
                    "abs_leg_mean": round(abs_leg, 6),
                    "n": int(len(pt_fwd)),
                }
        rep["capture_ratio"] = {
            "ratio": round(cr_global, 4),
            "fwd_mean": round(fwd_mean, 6),
            "abs_leg_mean": round(abs_leg_mean, 6),
            "n": int(len(zz25_act)),
            "por_pivot_type": cr_by_type,
        }
    else:
        rep["capture_ratio"] = None

    # 4.8 Drawdown por anticipación (entrada temprana) y salida tardía
    if señal.sum() > 0:
        early_mask = señal_shift1 & señal
        early_fwd = fwd[early_mask & fwd.notna()]
        early_mae = _mae_intratrade(spy, early_mask, df) if spy is not None else []
        late_mask = señal & señal_shift_1
        late_fwd = fwd[late_mask & fwd.notna()]
        late_mae = _mae_intratrade(spy, late_mask, df) if spy is not None else []
        rep["drawdown_anticipacion"] = {
            "entrada_temprana": {
                "n": int(len(early_fwd)),
                "forward_mean": float(np.nanmean(early_fwd)) if len(early_fwd) else None,
                "mae_medio": float(np.nanmean(early_mae)) if len(early_mae) else None,
            },
            "salida_tardia": {
                "n": int(len(late_fwd)),
                "forward_mean": float(np.nanmean(late_fwd)) if len(late_fwd) else None,
                "mae_medio": float(np.nanmean(late_mae)) if len(late_mae) else None,
            },
        }
    else:
        rep["drawdown_anticipacion"] = None

    # 4.8 Desglose D2×D3: breakdown del forward por dimensión DENTRO del D1 filtrado
    # Detecta las estaciones primarias usadas por la señal (las _sk que tienen D1 uniforme)
    # ── Fase 2 V7: is_bear early detection for direction-aware tags ──
    _wr_global = float((act > 0).mean()) if len(act) >= 5 else 0.5
    _is_bear = _wr_global < 0.35
    desglose = {}
    sk_cols = [c for c in df.columns if c.endswith("_sk")]
    for sk_col in sk_cols:
        station = sk_col.replace("_sk", "")
        sk_series = df.loc[señal, sk_col].dropna()
        if len(sk_series) < 10:
            continue
        d1_vals = sk_series.str.split("__").str[0]
        # Only decompose if ≥80% of signal events share the same D1
        top_d1 = d1_vals.value_counts()
        if len(top_d1) == 0:
            continue
        dominant_d1 = top_d1.index[0]
        dominant_pct = top_d1.iloc[0] / len(d1_vals)
        if dominant_pct < 0.50:
            continue

        # D2 breakdown within dominant D1
        d1_mask = señal & (df[sk_col].str.split("__").str[0] == dominant_d1)
        d2_series = df.loc[d1_mask, sk_col].str.split("__").str[1]
        d3_series = df.loc[d1_mask, sk_col].str.split("__").str[2]

        d2_breakdown = {}
        d2_fwd_pools = {}  # store fwd arrays for CI calculation
        for d2v in sorted(d2_series.dropna().unique()):
            sub_mask = d1_mask & (df[sk_col].str.split("__").str[1] == d2v)
            sub_fwd = fwd[sub_mask & fwd.notna()]
            if len(sub_fwd) >= 5:
                wr = float((sub_fwd > 0).mean())
                wins = sub_fwd[sub_fwd > 0]
                losses = sub_fwd[sub_fwd < 0]
                mean_win = float(wins.mean()) if len(wins) else 0.0
                mean_loss = float(losses.mean()) if len(losses) else 0.0
                lgr = abs(mean_loss) / mean_win if mean_win > 0 else float('inf')
                ev_neto = wr * mean_win + (1 - wr) * mean_loss
                # ── Direction-aware tag with Fisher ──
                n_w, n_l = int(len(wins)), int(len(losses))
                n_bl_w = int((act > 0).sum())
                n_bl_l = int((act <= 0).sum())
                try:
                    fp = _fisher_pvalue(n_w, n_w + n_l, n_bl_w, n_bl_w + n_bl_l) or 1.0
                except Exception:
                    fp = 1.0
                if _is_bear:
                    bear_rate = 1 - wr
                    bl_bear_rate = 1 - _wr_global
                    lift_d = bear_rate / bl_bear_rate if bl_bear_rate > 0 else 1.0
                    tag = "FAVORABLE" if lift_d >= 1.15 and fp < 0.05 else "UNFAVORABLE" if lift_d < 0.85 else "NEUTRAL"
                else:
                    lift_d = wr / _wr_global if _wr_global > 0 else 1.0
                    tag = "FAVORABLE" if lift_d >= 1.15 and fp < 0.05 else "UNFAVORABLE" if lift_d < 0.85 else "NEUTRAL"
                d2_breakdown[d2v] = {
                    "n": int(len(sub_fwd)),
                    "mean": round(float(sub_fwd.mean()), 6),
                    "wr": round(wr, 4),
                    "tag": tag,
                    "mean_win": round(mean_win, 6),
                    "mean_loss": round(mean_loss, 6),
                    "loss_gain_ratio": round(lgr, 4),
                    "ev_neto": round(ev_neto, 6),
                    "fisher_p": round(fp, 6),
                    "lift_directional": round(lift_d, 4),
                }
                d2_fwd_pools[d2v] = sub_fwd.values

        # Bootstrap CI for best-vs-worst D2 spread
        d2_ci = None
        if len(d2_fwd_pools) >= 2:
            best_k = max(d2_fwd_pools, key=lambda k: np.nanmean(d2_fwd_pools[k]))
            worst_k = min(d2_fwd_pools, key=lambda k: np.nanmean(d2_fwd_pools[k]))
            b_arr, w_arr = d2_fwd_pools[best_k], d2_fwd_pools[worst_k]
            rng = np.random.default_rng(seed)
            diffs = [np.mean(rng.choice(b_arr, len(b_arr))) - np.mean(rng.choice(w_arr, len(w_arr))) for _ in range(n_iter)]
            ci_lo, ci_hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
            d2_ci = {"best": best_k, "worst": worst_k, "ci_lo": round(ci_lo, 6), "ci_hi": round(ci_hi, 6),
                     "significativo": ci_lo > 0}

        d3_breakdown = {}
        d3_fwd_pools = {}
        for d3v in sorted(d3_series.dropna().unique()):
            sub_mask = d1_mask & (df[sk_col].str.split("__").str[2] == d3v)
            sub_fwd = fwd[sub_mask & fwd.notna()]
            if len(sub_fwd) >= 5:
                wr = float((sub_fwd > 0).mean())
                wins = sub_fwd[sub_fwd > 0]
                losses = sub_fwd[sub_fwd < 0]
                mean_win = float(wins.mean()) if len(wins) else 0.0
                mean_loss = float(losses.mean()) if len(losses) else 0.0
                lgr = abs(mean_loss) / mean_win if mean_win > 0 else float('inf')
                ev_neto = wr * mean_win + (1 - wr) * mean_loss
                n_w, n_l = int(len(wins)), int(len(losses))
                n_bl_w = int((act > 0).sum())
                n_bl_l = int((act <= 0).sum())
                try:
                    fp = _fisher_pvalue(n_w, n_w + n_l, n_bl_w, n_bl_w + n_bl_l) or 1.0
                except Exception:
                    fp = 1.0
                if _is_bear:
                    bear_rate = 1 - wr
                    bl_bear_rate = 1 - _wr_global
                    lift_d = bear_rate / bl_bear_rate if bl_bear_rate > 0 else 1.0
                    tag = "FAVORABLE" if lift_d >= 1.15 and fp < 0.05 else "UNFAVORABLE" if lift_d < 0.85 else "NEUTRAL"
                else:
                    lift_d = wr / _wr_global if _wr_global > 0 else 1.0
                    tag = "FAVORABLE" if lift_d >= 1.15 and fp < 0.05 else "UNFAVORABLE" if lift_d < 0.85 else "NEUTRAL"
                d3_breakdown[d3v] = {
                    "n": int(len(sub_fwd)),
                    "mean": round(float(sub_fwd.mean()), 6),
                    "wr": round(wr, 4),
                    "tag": tag,
                    "mean_win": round(mean_win, 6),
                    "mean_loss": round(mean_loss, 6),
                    "loss_gain_ratio": round(lgr, 4),
                    "ev_neto": round(ev_neto, 6),
                    "fisher_p": round(fp, 6),
                    "lift_directional": round(lift_d, 4),
                }
                d3_fwd_pools[d3v] = sub_fwd.values

        # Bootstrap CI for best-vs-worst D3 spread
        d3_ci = None
        if len(d3_fwd_pools) >= 2:
            best_k = max(d3_fwd_pools, key=lambda k: np.nanmean(d3_fwd_pools[k]))
            worst_k = min(d3_fwd_pools, key=lambda k: np.nanmean(d3_fwd_pools[k]))
            b_arr, w_arr = d3_fwd_pools[best_k], d3_fwd_pools[worst_k]
            rng = np.random.default_rng(seed)
            diffs = [np.mean(rng.choice(b_arr, len(b_arr))) - np.mean(rng.choice(w_arr, len(w_arr))) for _ in range(n_iter)]
            ci_lo, ci_hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
            d3_ci = {"best": best_k, "worst": worst_k, "ci_lo": round(ci_lo, 6), "ci_hi": round(ci_hi, 6),
                     "significativo": ci_lo > 0}

        if d2_breakdown or d3_breakdown:
            desglose[station] = {
                "d1_dominante": dominant_d1,
                "d1_pct": round(float(dominant_pct * 100), 1),
                "n_d1": int(d1_mask.sum()),
                "d2_velocity": d2_breakdown,
                "d2_ci95": d2_ci,
                "d3_station_vol": d3_breakdown,
                "d3_ci95": d3_ci,
            }
    rep["desglose_d2d3"] = desglose if desglose else None

    # 4.9 Estabilidad por Ciclo de Mercado (reemplaza décadas civiles — 28-Ago-2026)
    rep["estabilidad_ciclo"] = {}
    for cycle_name, (yr_start, yr_end) in MARKET_CYCLES.items():
        mask_cycle = señal & df["pivot_year"].between(yr_start, yr_end - 1)
        cycle_fwd = fwd[mask_cycle & fwd.notna()]
        if len(cycle_fwd) >= 3:
            rep["estabilidad_ciclo"][cycle_name] = {
                "n": int(len(cycle_fwd)),
                "mean": round(float(np.nanmean(cycle_fwd)), 6),
                "wr": round(float((cycle_fwd > 0).mean()), 4),
                "rango": f"{yr_start}-{yr_end}",
            }
        else:
            rep["estabilidad_ciclo"][cycle_name] = {
                "n": int(len(cycle_fwd)), "mean": None, "wr": None,
                "rango": f"{yr_start}-{yr_end}",
            }
    # Macro-eras (Pre-QE / QE / Post-QE)
    rep["estabilidad_macro_era"] = {}
    for era_name, (yr_start, yr_end) in MACRO_ERAS.items():
        mask_era = señal & df["pivot_year"].between(yr_start, yr_end - 1)
        era_fwd = fwd[mask_era & fwd.notna()]
        if len(era_fwd) >= 3:
            rep["estabilidad_macro_era"][era_name] = {
                "n": int(len(era_fwd)),
                "mean": round(float(np.nanmean(era_fwd)), 6),
                "wr": round(float((era_fwd > 0).mean()), 4),
                "rango": f"{yr_start}-{yr_end}",
            }
        else:
            rep["estabilidad_macro_era"][era_name] = {
                "n": int(len(era_fwd)), "mean": None, "wr": None,
                "rango": f"{yr_start}-{yr_end}",
            }

    # 4.10 Puntería por escala zigzag: capture ratio por zz25/zz50/zz75
    rep["punteria"] = {}
    for escala, col_cascade, objetivo in [("zz25", None, 0.025), ("zz50", "cascade_50", 0.05), ("zz75", "cascade_75", 0.075)]:
        if escala == "zz25":
            mask = señal & fwd.notna()
            lag = fwd[mask]
        else:
            mask = señal & (df[col_cascade] == 1) & fwd.notna()
            lag = fwd[mask]
        if len(lag) >= 5:
            rep["punteria"][escala] = {
                "n": int(len(lag)),
                "forward_mean": float(np.nanmean(lag)),
                "win_rate": float((lag > 0).mean()),
                "capture_ratio": float(np.nanmean(lag) / objetivo),
                "mae_medio": float(np.nanmean(_mae_intratrade(spy, mask, df))) if spy is not None else None,
            }

    # 4.11 Offset de entrada: capture ratio si entro ±1 barra del pivote
    if spy is not None:
        rep["offset_entrada"] = {}
        for offset in [-1, 0, 1]:
            off_mask = señal.values.copy()
            if offset != 0:
                off_mask = np.roll(off_mask, -offset)
            off_mask = pd.Series(off_mask, index=señal.index).astype(bool)
            off_fwd = fwd[off_mask & fwd.notna()]
            if len(off_fwd) >= 5:
                leg_mean = float(np.nanmean(np.abs(df.loc[señal, "prev_leg_return"])))
                rep["offset_entrada"][f"{offset:+d}"] = {
                    "n": int(len(off_fwd)),
                    "forward_mean": float(np.nanmean(off_fwd)),
                    "win_rate": float((off_fwd > 0).mean()),
                    "capture_ratio": float(np.nanmean(off_fwd) / leg_mean) if leg_mean > 0 else 0,
                }

    # 4.12 Lookback crash — señales activas en ventana [T0-3, T0+2]
    # Para cada pivote de caída (prev_leg_return < 0), buscar qué señales
    # estaban activas en la ventana diaria alrededor del pivote.
    import datetime as _dt
    crash_threshold = 0  # negativo = caída
    ventana_dias = 3  # [T0-3, T0+2]

    rep["lookback_crash"] = {}
    crash_pivots = señal & (df["prev_leg_return"] < crash_threshold)
    crash_idx = np.where(crash_pivots.values)[0]

    # Pre-compute all signal masks once (expensive to recompute per crash pivot)
    _all_sig_masks = {}
    for sig_name, sig_fn in SEÑALES.items():
        try:
            _all_sig_masks[sig_name] = sig_fn(df).astype(bool)
        except Exception:
            pass

    for escala, col_cascade, max_dur in [("zz25", None, 10), ("zz50", "cascade_50", 30), ("zz75", "cascade_75", 60)]:
        if len(crash_idx) == 0:
            continue

        # Filter crash pivots by zigzag scale
        if col_cascade is not None and col_cascade in df.columns:
            # For zz50/zz75: only crashes that reached the cascade threshold
            escala_mask = crash_pivots & df[col_cascade].notna() & (df[col_cascade] == True)
            escala_idx = np.where(escala_mask.values)[0]
        else:
            escala_idx = crash_idx

        if len(escala_idx) == 0:
            continue

        # Señales activas en la ventana [T0-ventana_dias, T0+2]
        activas_en_ventana = {sig: 0 for sig in _all_sig_masks}
        total_crashes_escala = 0

        for i in escala_idx:
            t0 = df["pivot_date"].iloc[i]
            t_min = t0 - _dt.timedelta(days=ventana_dias)
            t_max = t0 + _dt.timedelta(days=2)

            # Pivotes dentro de la ventana
            ventana = (df["pivot_date"] >= t_min) & (df["pivot_date"] <= t_max)
            if ventana.sum() == 0:
                continue

            total_crashes_escala += 1

            # Para cada señal, ¿estaba activa en algún pivote de la ventana?
            for sig_name, sig_serie in _all_sig_masks.items():
                if sig_serie[ventana].any():
                    activas_en_ventana[sig_name] += 1

        if total_crashes_escala > 0:
            rep["lookback_crash"][escala] = {
                "n_crashes": total_crashes_escala,
                "ventana_dias": ventana_dias,
                "señales": {},
            }
            for sig_name, n_activas in sorted(activas_en_ventana.items(), key=lambda x: -x[1]):
                if n_activas >= 3:  # mínimo 3 para reportar
                    pct = n_activas / total_crashes_escala * 100
                    rep["lookback_crash"][escala]["señales"][sig_name] = {
                        "n_crashes_con_senal": n_activas,
                        "pct_crashes": round(pct, 1),
                    }

    # 4.13 correlación Spearman señal-vs-forward
    rep["spearman"] = None

    # 4.14 ADDENDUM 1 — Structural Momentum (HH/HL/LH/LL)
    rep["structural_momentum"] = _structural_momentum_filter(señal, df, spy=spy)

    # 4.15 ADDENDUM 2 — Prev Leg Domino (post-crash context)
    rep["prev_leg_context"] = _prev_leg_context(señal, fwd, df)

    # 4.16 ADDENDUM 3 — Temporal Divergence Regime
    rep["divergence_regime"] = _divergence_regime(rep)

    # 4.17 ADDENDUM 9 — LIFT vs baseline condicionado por pivot_type (Enmienda 20-Ago-2026)
    rep["lift_vs_baseline"] = _lift_vs_baseline(señal, fwd, df)

    # ── 4.19 Fase 3 V7: Precursores t-1 / t-2 ──────────────────────────────
    from .precursores import analizar_precursores
    rep["precursores_t1_t2"] = analizar_precursores(señal, df, fwd)

    # ── 4.20 Fase 4 V7: Overflows en σ (D1, D2, D3) ──────────────────────
    # Uses sigma_overflow.py parameters to compute z-scores for all stations
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from backend.modules.entry_decision.domain.rules.sigma_overflow import STATION_MU_SIGMA

        overflow_eventos = []
        n_2sigma = 0
        n_3sigma = 0
        for station, dims in STATION_MU_SIGMA.items():
            sk_col = f"{station}_sk"
            if sk_col not in df.columns:
                continue
            for dim_name, (mu, sigma) in dims.items():
                if sigma <= 0:
                    continue
                # Map dim_name to the raw value column in quants_obs
                # d1 → _val (raw indicator), d2 → _vel (diff(3)), d3 → _vol (std(2)/std(10))
                _DIM_TO_COL = {"d1": "val", "d2": "vel", "d3": "vol"}
                col_suffix = _DIM_TO_COL.get(dim_name)
                val_col = f"{station}_{col_suffix}" if col_suffix else None
                if val_col not in df.columns:
                    continue
                vals = df.loc[señal, val_col].dropna()
                if len(vals) < 3:
                    continue
                z_scores = (vals - mu) / sigma
                overflows = z_scores[z_scores.abs() >= 2.0]
                if len(overflows) > 0:
                    n_2sigma += len(overflows)
                    n_3 = int((z_scores.abs() >= 3.0).sum())
                    n_3sigma += n_3
                    # Get WR for overflow events
                    ovf_mask = señal & df[val_col].notna()
                    z_all = (df.loc[ovf_mask, val_col] - mu) / sigma
                    ovf_idx = z_all[z_all.abs() >= 2.0].index
                    ovf_fwd = fwd.reindex(ovf_idx).dropna()
                    ovf_wr = float((ovf_fwd > 0).mean()) if len(ovf_fwd) >= 3 else None
                    overflow_eventos.append({
                        "estacion": station,
                        "dimension": dim_name,
                        "n_overflow_2sigma": int(len(overflows)),
                        "n_overflow_3sigma": n_3,
                        "z_mean": round(float(overflows.mean()), 2),
                        "z_max": round(float(overflows.abs().max()), 2),
                        "wr_en_overflow": round(ovf_wr, 4) if ovf_wr is not None else None,
                    })
        rep["overflows_sigma"] = {
            "n_eventos_2sigma": n_2sigma,
            "n_eventos_3sigma": n_3sigma,
            "eventos": overflow_eventos,
        }
    except Exception as _e:
        rep["overflows_sigma"] = {"error": str(_e)}

    # ── 4.21 Fase 5 V7: Divergencia Triádica (zz25 / zz50 / zz75) ────────
    div_triad = {}
    if "cascade_50" in df.columns and "cascade_75" in df.columns:
        for label, c50_val, c75_val in [
            ("solo_tactica", False, False),
            ("intermedia", True, False),
            ("estructural", True, True),
        ]:
            mask_scale = señal & fwd.notna()
            if c50_val:
                mask_scale = mask_scale & (df["cascade_50"] == True)
            else:
                mask_scale = mask_scale & ((df["cascade_50"] == False) | df["cascade_50"].isna())
            if c75_val:
                mask_scale = mask_scale & (df["cascade_75"] == True)
            else:
                if label != "solo_tactica":
                    mask_scale = mask_scale & ((df["cascade_75"] == False) | df["cascade_75"].isna())

            scale_fwd = fwd[mask_scale]
            n_scale = int(len(scale_fwd))
            if n_scale >= 3:
                wr_scale = float((scale_fwd > 0).mean())
                div_triad[label] = {
                    "n": n_scale,
                    "wr": round(wr_scale, 4),
                    "fwd_mean": round(float(scale_fwd.mean()), 6),
                    "fwd_median": round(float(scale_fwd.median()), 6),
                }
            else:
                div_triad[label] = {"n": n_scale, "wr": None, "fwd_mean": None}

        # Detect convergence/divergence pattern
        wrs = [div_triad.get(k, {}).get("wr") for k in ["solo_tactica", "intermedia", "estructural"]]
        wrs_valid = [w for w in wrs if w is not None]
        if len(wrs_valid) >= 2:
            if all(w > 0.55 for w in wrs_valid):
                patron = "CONVERGENCIA_ALCISTA"
            elif all(w < 0.45 for w in wrs_valid):
                patron = "CONVERGENCIA_BAJISTA"
            elif wrs_valid[0] > 0.55 and wrs_valid[-1] < 0.45:
                patron = "DIVERGENCIA_AGOTAMIENTO"
            elif wrs_valid[0] < 0.45 and wrs_valid[-1] > 0.55:
                patron = "DIVERGENCIA_REVERSION"
            else:
                patron = "MIXTO"
            gradiente = round(wrs_valid[-1] - wrs_valid[0], 4) if len(wrs_valid) >= 2 else None
            div_triad["patron"] = patron
            div_triad["gradiente_wr"] = gradiente
    rep["divergencia_triadica"] = div_triad if div_triad else None

    # ── 4.18 FICHA DE CREDIBILIDAD (28-Ago-2026) ──────────────────────────────
    # Bloque consolidado para interpretación autónoma por agentes AI.
    act_fwd = fwd[señal & fwd.notna()]
    n_act = int(len(act_fwd))
    n_wins_act = int((act_fwd > 0).sum()) if n_act > 0 else 0
    n_losses_act = n_act - n_wins_act
    wr_act = n_wins_act / n_act if n_act > 0 else 0.0

    # Baseline condicionado
    pivot_señal = df.loc[señal, "pivot_type"].unique()
    if len(pivot_señal) > 0 and len(pivot_señal) < len(df["pivot_type"].unique()):
        mask_bl = (~señal) & df["pivot_type"].isin(pivot_señal) & fwd.notna()
        bl_type = list(pivot_señal) if len(pivot_señal) > 1 else str(pivot_señal[0])
    else:
        mask_bl = (~señal) & fwd.notna()
        bl_type = "ALL"
    bl_fwd = fwd[mask_bl]
    n_bl = int(len(bl_fwd))
    n_wins_bl = int((bl_fwd > 0).sum()) if n_bl > 0 else 0
    wr_bl = n_wins_bl / n_bl if n_bl > 0 else 0.0

    # ── Signal direction detection ──
    # Bear/exit signals have WR < 35% (i.e. >65% of the time the market falls)
    is_bear = wr_act < 0.35 and n_act >= 5
    signal_direction = "BEAR" if is_bear else "BULL"

    # Directional LIFT: for bull signals, lift = WR/BL; for bear, lift = (1-WR)/(1-BL)
    if is_bear:
        bear_rate_act = 1.0 - wr_act
        bear_rate_bl = 1.0 - wr_bl
        lift_directional = round(bear_rate_act / bear_rate_bl, 4) if bear_rate_bl > 0 else None
    else:
        lift_directional = round(wr_act / wr_bl, 4) if wr_bl > 0 else None

    p_fisher = _fisher_pvalue(n_wins_act, n_act, n_wins_bl, n_bl)

    # Diamond protocol (§3.3) — direction-aware CI
    cp_ci = None
    if n_act < 21 and n_act > 0:
        if is_bear:
            # For bear: successes = losses (times market fell)
            cp_ci = _clopper_pearson_ci(n_losses_act, n_act)
        else:
            cp_ci = _clopper_pearson_ci(n_wins_act, n_act)

    # Retrieve metadata from registry
    meta_cert = _CERTEZA.get(señal_nombre, {})
    grade = meta_cert.get("validacion", "UNKNOWN")
    dsr = meta_cert.get("dsr", None)

    # Structural break detection across macro-eras
    # NOT applied to diamonds (N<21) where era variation is natural noise
    eras = rep.get("estabilidad_macro_era", {})
    era_wrs = [(k, v["wr"]) for k, v in eras.items() if v.get("wr") is not None]
    structural_break = False
    if n_act >= 21 and len(era_wrs) >= 2:
        wrs_vals = [w for _, w in era_wrs]
        structural_break = (max(wrs_vals) - min(wrs_vals)) > 0.20  # >20pp spread

    # Determine action recommendation
    if "RETIRADA" in grade or "RE-RETIRADA" in grade:
        accion = "RETIRADA"
    elif "DEGRADADA" in grade or structural_break:
        accion = "CUARENTENA"
    elif "RESCATADA" in grade:
        accion = "PRODUCCIÓN_DIAMANTE"
    elif lift_directional is not None and lift_directional >= 1.10 and (p_fisher is not None and p_fisher < 0.10):
        accion = "PRODUCCIÓN"
    elif n_act < 21 and cp_ci and cp_ci.get("ci_direccional"):
        accion = "PRODUCCIÓN_DIAMANTE"
    elif "VALIDATED" in grade:
        accion = "PRODUCCIÓN"
    elif is_bear and p_fisher is not None and p_fisher < 0.01:
        accion = "PRODUCCIÓN"  # strong bear signal with statistical proof
    elif "SPECULATIVE" in grade or "PROPOSED" in grade or "MODERATE" in grade:
        accion = "CUARENTENA"
    else:
        accion = "MONITOREO"

    rep["ficha_credibilidad"] = {
        "grade": grade,
        "tipo": meta_cert.get("tipo", "unknown"),
        "pivot_type": meta_cert.get("pivot_type", "BOTH"),
        "descripcion": meta_cert.get("descripcion", ""),
        "signal_direction": signal_direction,
        "n_total": n_act,
        "win_rate": round(wr_act, 4),
        "baseline_wr": round(wr_bl, 4),
        "baseline_type": bl_type if isinstance(bl_type, str) else "MIXED",
        "lift_directional": lift_directional,
        "p_value_fisher": p_fisher,
        "ci95_bootstrap": rep["activa"].get("ci_mean", {}),
        "dsr_pvalue": dsr,
        "diamante": cp_ci,
        "structural_break": structural_break,
        "accion_recomendada": accion,
    }

    return rep


def medir_cross_overlap(df, forward_col="next_leg", n_iter=3000, seed=42):
    """Mide edge de la intersección de cada par de señales registradas."""
    if forward_col == "next_leg":
        fwd = df["prev_leg_return"].shift(-1)
    else:
        fwd = df[forward_col]

    sig_masks = {name: fn(df).astype(bool) for name, fn in SEÑALES.items()}
    sig_names = sorted(sig_masks.keys())
    overlaps = []

    for i in range(len(sig_names)):
        for j in range(i + 1, len(sig_names)):
            s1, s2 = sig_names[i], sig_names[j]
            m1, m2 = sig_masks[s1], sig_masks[s2]
            both = m1 & m2
            n_both = int(both.sum())
            if n_both < 5:
                continue

            fwd_only1 = fwd[m1 & ~m2 & fwd.notna()]
            fwd_only2 = fwd[~m1 & m2 & fwd.notna()]
            fwd_both = fwd[both & fwd.notna()]

            if len(fwd_both) < 3:
                continue

            mean_1 = float(np.nanmean(fwd_only1)) if len(fwd_only1) else None
            mean_2 = float(np.nanmean(fwd_only2)) if len(fwd_only2) else None
            mean_both = float(np.nanmean(fwd_both))
            max_solo = max(mean_1 or 0, mean_2 or 0)

            if mean_both > max_solo + 0.002:
                tag = "ADITIVA"
            elif mean_both < min(mean_1 or 0, mean_2 or 0) - 0.002:
                tag = "CANCELATORIA"
            else:
                tag = "REDUNDANTE"

            overlaps.append({
                "par": f"{s1} × {s2}",
                "n_overlap": n_both,
                "pct_overlap": round(100 * n_both / min(m1.sum(), m2.sum()), 1),
                "solo_a": {"n": int(len(fwd_only1)), "mean": round(mean_1, 6) if mean_1 is not None else None, "wr": round(float((fwd_only1 > 0).mean()), 4) if len(fwd_only1) else None},
                "solo_b": {"n": int(len(fwd_only2)), "mean": round(mean_2, 6) if mean_2 is not None else None, "wr": round(float((fwd_only2 > 0).mean()), 4) if len(fwd_only2) else None},
                "ambas": {"n": int(len(fwd_both)), "mean": round(mean_both, 6), "wr": round(float((fwd_both > 0).mean()), 4)},
                "tag": tag,
            })

    return overlaps
