#!/usr/bin/env python3
"""
Ejercicios Probatorios de Régimen de Mercado (E1 a E6)
=====================================================
Batería experimental para validación cuantitativa de hipótesis de régimen:
  E1 — Asimetría de Régimen en Cascada (cascade_reversal en ALZA vs BAJA)
  E2 — Invarianza Temporal de Extremos VIX (vix_crisis_spike pre vs post-2010)
  E3 — Dinámica de Colapso de Crédito vs Equity (credit_stress vs suelos de SPY)
  E4 — Reversión en Ráfaga de Turbulencia (sv5_turbulence decaimiento y resolución)
  E5 — Confluencia de Pánico Multi-Estación (confluencia >= 2 estaciones)
  E6 — Asimetría de Euforia de Sentimiento (fg_extreme_greed condicionado a tendencia)

Correcciones aplicadas (1-Sep-2026):
  C11: Framework de conclusiones dinámicas (_generar_conclusion)
  C5:  CI95 Clopper-Pearson en todas las métricas de hit rate
  C7:  p-values correctos por tipo: Fisher (E1/E2), sign-test (E3), binomial (E4-E6)
  C1-C4: Conclusiones hardcoded eliminadas — ahora generadas desde datos

Guarda resultados en `data/research/signals/ejercicios_regimen_e1_e6.json`.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent.parent
DIR_DATA = ROOT / "data" / "research" / "signals"
FILE_OUT = DIR_DATA / "ejercicios_regimen_e1_e6.json"

from arnes.datos import cargar_datos
from arnes.registro import SEÑALES
import arnes.señales  # noqa - triggers signal registration
from arnes.timing import classify_timing_slots
from evaluador_general import cargar_entorno_evaluacion, build_episodes, first_passage_bar, _CACHE_DATA


def test_fisher_significancia(hits_a: int, fails_a: int, hits_b: int, fails_b: int) -> float:
    """Calcula p-value exacto de Fisher para comparar dos proporciones binomiales."""
    table = [[hits_a, fails_a], [hits_b, fails_b]]
    _, p_val = stats.fisher_exact(table)
    return float(p_val)


def eval_fp(t0: int, blanco: str, scale: float) -> Dict[str, Any]:
    """Helper para ejecutar first-passage sobre el array global de SPY."""
    res = first_passage_bar(
        _CACHE_DATA["spy_close"],
        _CACHE_DATA["spy_high"],
        _CACHE_DATA["spy_low"],
        t0=t0,
        scale=scale,
        blanco=blanco,
    )
    if res is None or not res.get("resuelto", False):
        return {"resuelto": False, "hit": False, "favorable": 0.0, "bars": 0}
    return res


# ── CI95 y Conclusiones Dinámicas (C5 + C11) ────────────────────────────────

def _ci95(hits: int, n: int) -> Dict[str, Any]:
    """Clopper-Pearson exact CI95 for a binomial proportion."""
    from scipy.stats import beta as beta_dist
    if n == 0:
        return {"ci95_lo": None, "ci95_hi": None}
    ci_lo = beta_dist.ppf(0.025, hits, n - hits + 1) if hits > 0 else 0.0
    ci_hi = beta_dist.ppf(0.975, hits + 1, n - hits) if hits < n else 1.0
    return {"ci95_lo": round(float(ci_lo), 4), "ci95_hi": round(float(ci_hi), 4)}


# Bonferroni alpha' for 6 exercises
ALPHA_BONF = 0.05 / 6  # 0.00833


def _generar_conclusion(ejercicio: str, resultados: Dict[str, Any]) -> str:
    """Framework C11: genera conclusión dinámica basada en los datos, no templates."""
    if ejercicio == "E1":
        hr_a = resultados["hit_rate_alza"]
        hr_b = resultados["hit_rate_baja"]
        n_a = resultados["n_alza"]
        n_b = resultados["n_baja"]
        p = resultados["p_value_fisher"]
        delta = hr_a - hr_b
        sig = "SIGNIFICATIVO" if p < ALPHA_BONF else "NO significativo"
        return (f"ALZA: HR={hr_a:.1%} (N={n_a}) vs BAJA: HR={hr_b:.1%} (N={n_b}). "
                f"Delta={delta:+.1%}, p={p:.4f} ({sig} tras Bonferroni α'={ALPHA_BONF:.4f}).")

    elif ejercicio == "E2":
        n_pre = resultados["n_pre_2010"]
        n_post = resultados["n_post_2010"]
        hr_pre = resultados["hit_rate_pre_2010"]
        hr_post = resultados["hit_rate_post_2010"]
        p = resultados["p_value_fisher"]
        if n_post < 21:
            return (f"PENDIENTE — N_post={n_post} insuficiente (Diamante §3.3). "
                    f"Pre: HR={hr_pre:.1%} (N={n_pre}), Post: HR={hr_post:.1%} (N={n_post}). "
                    f"p={p:.4f}. Sin poder estadístico para confirmar ni rechazar invarianza.")
        sig = "Invarianza rechazada" if p < ALPHA_BONF else "Sin evidencia de diferencia"
        return (f"{sig}: Pre HR={hr_pre:.1%} (N={n_pre}) vs Post HR={hr_post:.1%} (N={n_post}). "
                f"p={p:.4f} (Bonferroni α'={ALPHA_BONF:.4f}).")

    elif ejercicio == "E3":
        pct_lead = resultados["pct_anticipada_lead"]
        pct_exact = resultados["pct_coincidente_exacta"]
        pct_lag = resultados["pct_retrasada_lag"]
        med = resultados["delta_mediana_barras"]
        p = resultados.get("p_value_sign_test")
        pstr = f", sign-test p={p:.4f}" if p is not None else ""
        if pct_lead + pct_exact > 60:
            tipo = "Leading/coincidente"
        elif pct_lag > 50:
            tipo = "Lagging"
        else:
            tipo = "Coincidente"
        return (f"{tipo}: anticipada={pct_lead:.1f}%, exacta={pct_exact:.1f}%, retrasada={pct_lag:.1f}%. "
                f"Mediana delta={med:.0f} barras (trading days){pstr}.")

    elif ejercicio == "E4":
        hr = resultados["hit_rate_zz25"]
        n = resultados["n_episodios"]
        med = resultados["mediana_barras_resolucion"]
        p90 = resultados["p90_barras_resolucion"]
        p = resultados.get("p_value_binom")
        pstr = f", p={p:.4f}" if p is not None else ""
        return (f"HR={hr:.1%} (N={n}). Mediana resolución={med:.0f} barras, P90={p90:.0f} barras{pstr}.")

    elif ejercicio == "E5":
        hr = resultados["hit_rate_zz50"]
        lift = resultados["lift_vs_unconditional"]
        n = resultados["n_episodios_confluencia"]
        p = resultados.get("p_value_binom")
        pstr = f", p={p:.4f}" if p is not None else ""
        if lift < 0:
            return (f"RECHAZADA — lift negativo: HR={hr:.1%} (N={n}), lift={lift:+.1%} vs baseline incondicional{pstr}. "
                    f"Confluencia ≥2 estaciones NO produce edge sobre azar.")
        return (f"Edge de confluencia: HR={hr:.1%} (N={n}), lift={lift:+.1%} vs baseline{pstr}.")

    elif ejercicio == "E6":
        n_bull = resultados["n_en_bull_trend"]
        n_bear = resultados["n_en_bear_trend"]
        hr_bull = resultados["hit_rate_bull"]
        if n_bear == 0:
            return (f"INCONCLUSO — sin datos de bear (N=0). Bull: HR={hr_bull:.1%} (N={n_bull}). "
                    f"La señal es intrínsecamente procíclica (solo dispara en bull markets).")
        hr_bear = resultados["hit_rate_bear"]
        return (f"Bull: HR={hr_bull:.1%} (N={n_bull}) vs Bear: HR={hr_bear:.1%} (N={n_bear}).")

    return "Sin conclusión generada."


# ── E1: Asimetría de Régimen en Cascada ─────────────────────────────────────────
def ejecutar_e1_cascada(quants: pd.DataFrame, spy: pd.DataFrame) -> Dict[str, Any]:
    """H0: cascade_reversal tiene el mismo hit rate en régimen ALZA que en BAJA."""
    from evaluador_vela_a_vela import evaluar as evaluar_vav
    res_vav = evaluar_vav("cascade_reversal")
    
    perfil = res_vav.get("perfil_3d_régimen", {})
    alza = perfil.get("zz25|ALZA", {})
    baja = perfil.get("zz25|BAJA", {})

    n_a = alza.get("n", 0)
    n_b = baja.get("n", 0)
    hr_a = alza.get("hit_rate", 0.0)
    hr_b = baja.get("hit_rate", 0.0)

    hits_a = int(round(hr_a * n_a))
    hits_b = int(round(hr_b * n_b))

    p_val = test_fisher_significancia(hits_a, n_a - hits_a, hits_b, n_b - hits_b)
    ci_a = _ci95(hits_a, n_a)
    ci_b = _ci95(hits_b, n_b)

    res = {
        "ejercicio": "E1 — Asimetría de Régimen en Cascada",
        "descripcion": "Verifica si cascade_reversal funciona como killer exit en ALZA pero pierde edge en BAJA",
        "n_alza": n_a, "hit_rate_alza": round(hr_a, 4), "ci95_alza": ci_a,
        "fav_neto_alza": alza.get("fav_neto"),
        "n_baja": n_b, "hit_rate_baja": round(hr_b, 4), "ci95_baja": ci_b,
        "fav_neto_baja": baja.get("fav_neto"),
        "delta_hit_rate": round(hr_a - hr_b, 4),
        "p_value_fisher": round(p_val, 5),
        "rechaza_h0": bool(p_val < ALPHA_BONF),
    }
    res["conclusion"] = _generar_conclusion("E1", res)
    return res


# ── E2: Invarianza Temporal de Extremos VIX ────────────────────────────────────
def ejecutar_e2_vix_invarianza(lake: pd.DataFrame, spy: pd.DataFrame) -> Dict[str, Any]:
    """H0: El edge de vix_crisis_spike es idéntico pre-2010 vs post-2010."""
    from arnes.registro import SEÑALES
    fn_sig = SEÑALES["vix_crisis_spike"]
    sig_mask = fn_sig(lake)
    episodes = build_episodes(sig_mask.values, lake.index)

    pre_2010 = [ep for ep in episodes if pd.Timestamp(ep["start_date"]) < pd.Timestamp("2010-01-01")]
    post_2010 = [ep for ep in episodes if pd.Timestamp(ep["start_date"]) >= pd.Timestamp("2010-01-01")]

    res_pre = [eval_fp(ep["start_idx"], "MIN", 0.05) for ep in pre_2010]
    res_post = [eval_fp(ep["start_idx"], "MIN", 0.05) for ep in post_2010]

    hits_pre = sum(1 for r in res_pre if r["hit"])
    hits_post = sum(1 for r in res_post if r["hit"])
    hr_pre = hits_pre / len(res_pre) if res_pre else 0.0
    hr_post = hits_post / len(res_post) if res_post else 0.0

    p_val = test_fisher_significancia(hits_pre, len(res_pre) - hits_pre, hits_post, len(res_post) - hits_post)
    ci_pre = _ci95(hits_pre, len(res_pre))
    ci_post = _ci95(hits_post, len(res_post))

    res = {
        "ejercicio": "E2 — Invarianza Temporal de Extremos VIX",
        "descripcion": "Verifica estabilidad del edge de compra en pánico de volatilidad pre vs post QE",
        "n_pre_2010": len(pre_2010), "hit_rate_pre_2010": round(hr_pre, 4), "ci95_pre": ci_pre,
        "n_post_2010": len(post_2010), "hit_rate_post_2010": round(hr_post, 4), "ci95_post": ci_post,
        "delta_hit_rate": round(hr_post - hr_pre, 4),
        "p_value_fisher": round(p_val, 5),
        "es_invariante": bool(p_val >= ALPHA_BONF),
    }
    res["conclusion"] = _generar_conclusion("E2", res)
    return res


# ── E3: Dinámica de Colapso de Crédito vs Equity ────────────────────────────────
def ejecutar_e3_credito_timing(lake: pd.DataFrame, quants: pd.DataFrame) -> Dict[str, Any]:
    """Mide el lead/lag entre credit_stress y el suelo definitivo de SPY (pivote MIN)."""
    from arnes.registro import SEÑALES
    fn_sig = SEÑALES["credit_stress"]
    sig_mask = fn_sig(lake)
    episodes = build_episodes(sig_mask.values, lake.index)

    piv_min = quants[quants["pivot_type"] == "MIN"]
    piv_dates = pd.to_datetime(piv_min["pivot_date"])
    sig_dates = pd.to_datetime([ep["start_date"] for ep in episodes])

    slots = classify_timing_slots(sig_dates, piv_dates, target_pivot_type="MIN", trading_index=lake.index)
    deltas = slots["delta_days"].values

    lead_episodes = sum(1 for d in deltas if d < 0)  # Anticipada
    exact_episodes = sum(1 for d in deltas if d == 0)
    lag_episodes = sum(1 for d in deltas if d > 0)  # Retrasada

    # Sign test: H0 = median delta is 0 (coincident indicator)
    nonzero_deltas = deltas[deltas != 0]
    p_sign = float(stats.binomtest(
        int(sum(nonzero_deltas > 0)), len(nonzero_deltas), 0.5
    ).pvalue) if len(nonzero_deltas) > 0 else None

    res = {
        "ejercicio": "E3 — Dinámica de Colapso de Crédito vs Equity",
        "descripcion": "Analiza si el spread de crédito anticipa suelos de equity (Lead Indicator). "
                       "Nota: delta_mediana_barras usa barras de trading (no días calendario).",
        "n_episodios": len(deltas),
        "pct_anticipada_lead": round(lead_episodes / len(deltas) * 100, 1) if len(deltas) else 0.0,
        "pct_coincidente_exacta": round(exact_episodes / len(deltas) * 100, 1) if len(deltas) else 0.0,
        "pct_retrasada_lag": round(lag_episodes / len(deltas) * 100, 1) if len(deltas) else 0.0,
        "delta_mediana_barras": float(np.median(deltas)) if len(deltas) else 0.0,
        "p_value_sign_test": round(p_sign, 5) if p_sign is not None else None,
    }
    res["conclusion"] = _generar_conclusion("E3", res)
    return res


# ── E4: Reversión en Ráfaga de Turbulencia ──────────────────────────────────────
def ejecutar_e4_turbulencia_reversion(lake: pd.DataFrame, spy: pd.DataFrame) -> Dict[str, Any]:
    """Mide la velocidad de resolución favorable tras spike de SV5_Turbulence (D1=5)."""
    sv5_sk = lake["sv5_turbulence_sk"] if "sv5_turbulence_sk" in lake.columns else pd.Series("", index=lake.index)
    mask = sv5_sk.fillna("").str.startswith("5__")
    episodes = build_episodes(mask.values.astype(bool), lake.index)

    res_fp = [eval_fp(ep["start_idx"], "MIN", 0.025) for ep in episodes]
    valid = [r for r in res_fp if r.get("resuelto", False)]
    hits = [r for r in valid if r["hit"]]
    bars_to_hit = [r["bars"] for r in hits]

    n_valid = len(valid)
    n_hits = len(hits)
    hr = n_hits / n_valid if n_valid else 0.0

    # Binomial test: is HR > baseline (0.548 for zz25 MIN)
    p_binom = float(stats.binomtest(
        n_hits, n_valid, 0.548, alternative="greater"
    ).pvalue) if n_valid > 0 else None
    ci = _ci95(n_hits, n_valid)

    res = {
        "ejercicio": "E4 — Reversión en Ráfaga de Turbulencia",
        "descripcion": "Velocidad de absorción de shocks de volumen institucional (SV5_Turbulence D1=5)",
        "n_episodios": len(episodes),
        "n_resueltos": n_valid,
        "hit_rate_zz25": round(hr, 4), "ci95_hr": ci,
        "mediana_barras_resolucion": float(np.median(bars_to_hit)) if bars_to_hit else 0.0,
        "p90_barras_resolucion": round(float(np.percentile(bars_to_hit, 90)), 1) if bars_to_hit else 0.0,
        "p_value_binom": round(p_binom, 5) if p_binom is not None else None,
    }
    res["conclusion"] = _generar_conclusion("E4", res)
    return res


# ── E5: Confluencia de Pánico Multi-Estación ────────────────────────────────────
def ejecutar_e5_confluencia_panico(lake: pd.DataFrame, spy: pd.DataFrame) -> Dict[str, Any]:
    """Evalúa edge cuando >=2 estaciones METAR están en overflow simultáneo de pánico.
    Usa bins D1 como proxy de overflow gaussiano (D1>=5 = >+2σ, D1<=0 = <-2σ)."""
    # Usar bins como proxy de z-score overflow (bins = clasificación gaussiana)
    panic_scores = np.zeros(len(lake), dtype=int)
    for st in ["vix", "vvix", "pcr", "sv5_turbulence"]:
        col = f"{st}_sk"
        if col in lake.columns:
            panic_scores += (lake[col].fillna("").str.startswith("5__")).astype(int)
    for st in ["bsi", "credit"]:
        col = f"{st}_sk"
        if col in lake.columns:
            panic_scores += (lake[col].fillna("").str.startswith("0__")).astype(int)

    mask_confluencia = panic_scores >= 2
    episodes = build_episodes(mask_confluencia, lake.index)

    res_fp = [eval_fp(ep["start_idx"], "MIN", 0.05) for ep in episodes]
    valid = [r for r in res_fp if r.get("resuelto", False)]
    hits = sum(1 for r in valid if r["hit"])
    hr = hits / len(valid) if valid else 0.0

    # Baseline for zz50 MIN ≈ 0.58
    baseline_hr = 0.58
    lift = hr - baseline_hr

    p_binom = float(stats.binomtest(
        hits, len(valid), baseline_hr, alternative="greater"
    ).pvalue) if valid else None
    ci = _ci95(hits, len(valid))

    res = {
        "ejercicio": "E5 — Confluencia de Pánico Multi-Estación",
        "descripcion": "Rendimiento de compra en confluencia simultánea de estrés multi-activo (≥2 estaciones en overflow D1 extremo)",
        "n_episodios_confluencia": len(episodes),
        "n_resueltos": len(valid),
        "hit_rate_zz50": round(hr, 4), "ci95_hr": ci,
        "lift_vs_unconditional": round(lift, 4),
        "p_value_binom": round(p_binom, 5) if p_binom is not None else None,
    }
    res["conclusion"] = _generar_conclusion("E5", res)
    return res


# ── E6: Asimetría de Euforia de Sentimiento ────────────────────────────────────
def ejecutar_e6_euforia_sentimiento(lake: pd.DataFrame, spy: pd.DataFrame) -> Dict[str, Any]:
    """Evalúa fg_extreme_greed en tendencia alcista (SPY > 200 SMA) vs bajista."""
    from arnes.registro import SEÑALES
    fn_sig = SEÑALES["fg_extreme_greed"]
    sig_mask = fn_sig(lake)
    episodes = build_episodes(sig_mask.values, lake.index)

    close_arr = _CACHE_DATA["spy_close"]
    sma200 = pd.Series(close_arr).rolling(200).mean().values

    res_bull = []
    res_bear = []

    for ep in episodes:
        idx = ep["start_idx"]
        c_price = close_arr[idx]
        c_sma = sma200[idx] if idx < len(sma200) else np.nan

        r = eval_fp(idx, "MAX", 0.025)
        if not np.isnan(c_sma) and c_price > c_sma:
            res_bull.append(r)
        else:
            res_bear.append(r)

    valid_bull = [r for r in res_bull if r.get("resuelto", False)]
    valid_bear = [r for r in res_bear if r.get("resuelto", False)]
    hits_bull = sum(1 for r in valid_bull if r["hit"])
    hits_bear = sum(1 for r in valid_bear if r["hit"])
    hr_bull = hits_bull / len(valid_bull) if valid_bull else 0.0
    hr_bear = hits_bear / len(valid_bear) if valid_bear else 0.0

    ci_bull = _ci95(hits_bull, len(valid_bull))
    ci_bear = _ci95(hits_bear, len(valid_bear))

    res = {
        "ejercicio": "E6 — Asimetría de Euforia de Sentimiento",
        "descripcion": "Verifica si la euforia extrema produce falsas salidas en bull market secular",
        "n_en_bull_trend": len(valid_bull), "hit_rate_bull": round(hr_bull, 4), "ci95_bull": ci_bull,
        "n_en_bear_trend": len(valid_bear), "hit_rate_bear": round(hr_bear, 4), "ci95_bear": ci_bear,
    }
    res["conclusion"] = _generar_conclusion("E6", res)
    return res


def ejecutar_todos_los_ejercicios():
    print("\n" + "=" * 110)
    print("EJECUCIÓN DE EJERCICIOS PROBATORIOS DE RÉGIMEN DE MERCADO (E1 a E6)")
    print("=" * 110)

    lake, quants = cargar_entorno_evaluacion()
    spy, _ = cargar_datos()

    resultados = {
        "E1": ejecutar_e1_cascada(quants, spy),
        "E2": ejecutar_e2_vix_invarianza(lake, spy),
        "E3": ejecutar_e3_credito_timing(lake, quants),
        "E4": ejecutar_e4_turbulencia_reversion(lake, spy),
        "E5": ejecutar_e5_confluencia_panico(lake, spy),
        "E6": ejecutar_e6_euforia_sentimiento(lake, spy),
    }

    for k, res in resultados.items():
        print(f"\n[{k}] {res['ejercicio']}")
        print(f"  • Objetivo  : {res['descripcion']}")
        for key, val in res.items():
            if key not in ("ejercicio", "descripcion", "conclusion"):
                print(f"  • {key:<25s}: {val}")
        print(f"  📌 Conclusión: {res['conclusion']}")

    FILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    FILE_OUT.write_text(json.dumps(resultados, indent=2, ensure_ascii=False))
    print("\n" + "=" * 110)
    print(f"✅ Todos los ejercicios completados y guardados en: {FILE_OUT}\n")
    return resultados


if __name__ == "__main__":
    ejecutar_todos_los_ejercicios()
