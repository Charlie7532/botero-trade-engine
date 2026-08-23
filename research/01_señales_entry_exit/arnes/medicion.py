"""Motor de medición: medir() — arnés estándar completo por señal; medir_cross_overlap().

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import numpy as np
import pandas as pd

from .registro import SEÑALES, _CERTEZA
from .estadisticas import _pctiles, _wins_losses, _bootstrap_ci, _lift_vs_baseline
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
                d2_breakdown[d2v] = {
                    "n": int(len(sub_fwd)),
                    "mean": round(float(sub_fwd.mean()), 6),
                    "wr": round(wr, 4),
                    "tag": "FAVORABLE" if wr > 0.55 else "UNFAVORABLE" if wr < 0.45 else "NEUTRAL",
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
                d3_breakdown[d3v] = {
                    "n": int(len(sub_fwd)),
                    "mean": round(float(sub_fwd.mean()), 6),
                    "wr": round(wr, 4),
                    "tag": "FAVORABLE" if wr > 0.55 else "UNFAVORABLE" if wr < 0.45 else "NEUTRAL",
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

    # 4.9 Estabilidad por década
    rep["estabilidad_decada"] = {}
    for decada in ["1990", "2000", "2010", "2020"]:
        yr_start, yr_end = int(decada), int(decada) + 9
        mask_dec = señal & df["pivot_year"].between(yr_start, yr_end)
        dec_fwd = fwd[mask_dec & fwd.notna()]
        if len(dec_fwd) >= 3:
            rep["estabilidad_decada"][decada] = {
                "n": int(len(dec_fwd)),
                "mean": round(float(np.nanmean(dec_fwd)), 6),
                "wr": round(float((dec_fwd > 0).mean()), 4),
            }
        else:
            rep["estabilidad_decada"][decada] = {"n": int(len(dec_fwd)), "mean": None, "wr": None}

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
