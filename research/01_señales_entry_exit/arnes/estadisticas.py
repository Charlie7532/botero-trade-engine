"""Estadística de medición: percentiles, wins/losses, bootstrap CI95, LIFT vs baseline.

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import numpy as np
import pandas as pd  # noqa: F401

def _pctiles(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return {"n": 0}
    return {
        "n": int(len(x)),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "p5": float(np.percentile(x, 5)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "p95": float(np.percentile(x, 95)),
        "std": float(np.std(x)),
    }


def _wins_losses(x):
    """wins/losses separados: win_rate, mean_win, mean_loss, profit_factor."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    wins = x[x > 0]
    losses = x[x < 0]
    if len(x) == 0:
        return {}
    gross_win = wins.sum() if len(wins) else 0.0
    gross_loss = abs(losses.sum()) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return {
        "win_rate": float(len(wins) / len(x)),
        "n_wins": int(len(wins)),
        "n_losses": int(len(losses)),
        "mean_win": float(wins.mean()) if len(wins) else None,
        "mean_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": pf if pf != float("inf") else None,
    }


def _bootstrap_ci(metric_fn, data, n_iter=3000, seed=42):
    """CI95 bootstrap pareado de una métrica (media por defecto)."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 20:
        return {"ci_lo": None, "ci_hi": None, "n": int(len(arr)), "nota": "N<20"}
    boots = []
    for _ in range(n_iter):
        idx = rng.integers(0, len(arr), len(arr))
        boots.append(metric_fn(arr[idx]))
    boots = np.array(boots)
    return {
        "ci_lo": float(np.percentile(boots, 2.5)),
        "ci_hi": float(np.percentile(boots, 97.5)),
        "n": int(len(arr)),
    }


def _lift_vs_baseline(señal, fwd, df):
    """Calcula lift = P(cae | señal) / P(cae | ¬señal) condicionado por pivot_type."""
    pivot_types = df.loc[señal, "pivot_type"].unique()
    lifts = {}
    for pt in pivot_types:
        mask_pt = df["pivot_type"] == pt
        mask_activa = señal & mask_pt & fwd.notna()
        mask_no_activa = (~señal) & mask_pt & fwd.notna()
        n_act = mask_activa.sum()
        n_noact = mask_no_activa.sum()
        if n_act < 3 or n_noact < 3:
            continue
        p_cae_act = float((fwd[mask_activa] <= 0).mean())
        p_cae_noact = float((fwd[mask_no_activa] <= 0).mean())
        lift = p_cae_act / p_cae_noact if p_cae_noact > 0 else 999.0
        lifts[pt] = {
            "n_activa": int(n_act), "n_no_activa": int(n_noact),
            "pct_cae_activa": round(p_cae_act * 100, 1),
            "pct_cae_no_activa": round(p_cae_noact * 100, 1),
            "lift": round(lift, 3),
            "interpretacion": ">1.0=señal real, <1.0=anti-señal, ≈1.0=ruido"
        }
    return lifts


def _clopper_pearson_ci(n_successes: int, n_total: int, alpha: float = 0.05):
    """Exact Clopper-Pearson CI95 for binomial proportion.
    Required by Diamond Protocol §3.3 for signals with N < 21."""
    from scipy.stats import beta as beta_dist
    if n_total == 0:
        return {"ci_lo": None, "ci_hi": None, "n": 0, "p_raw": None}
    p_raw = n_successes / n_total
    ci_lo = beta_dist.ppf(alpha / 2, n_successes, n_total - n_successes + 1) if n_successes > 0 else 0.0
    ci_hi = beta_dist.ppf(1 - alpha / 2, n_successes + 1, n_total - n_successes) if n_successes < n_total else 1.0
    return {
        "p_raw": round(p_raw, 4),
        "ci_lo": round(float(ci_lo), 4),
        "ci_hi": round(float(ci_hi), 4),
        "n": int(n_total),
        "es_diamante": n_total < 21,
        "ci_direccional": ci_lo > 0.5 or ci_hi < 0.5,
    }


def _fisher_pvalue(n_wins_signal, n_total_signal, n_wins_baseline, n_total_baseline):
    """Fisher exact test: is the signal's WR significantly different from baseline?"""
    from scipy.stats import fisher_exact
    if n_total_signal == 0 or n_total_baseline == 0:
        return None
    a = n_wins_signal
    b = n_total_signal - n_wins_signal
    c = n_wins_baseline
    d = n_total_baseline - n_wins_baseline
    _, p = fisher_exact([[a, b], [c, d]], alternative='two-sided')
    return round(float(p), 6)


def edge_direccional(n_alza: int, hits_alza: int, n_baja: int, hits_baja: int,
                     baseline_alza: float, baseline_baja: float) -> dict:
    """Edge direccional condicionado: accuracy vs baseline PROPIO por dirección.

    Principio de López de Prado: probar contra la clase mayoritaria que la señal
    predice, no contra un baseline global agregado.

    Migrado de comite_metar/curador/modelador.py (Sep-2026 saneamiento).
    Usa _clopper_pearson_ci canónica (beta-based, arnes/).

    Args:
        n_alza: episodios donde la señal predijo ALZA
        hits_alza: aciertos de esos episodios
        n_baja: episodios donde la señal predijo BAJA
        hits_baja: aciertos de esos episodios
        baseline_alza: hit rate incondicional para movimientos alcistas
        baseline_baja: hit rate incondicional para movimientos bajistas

    Returns:
        Dict con edge_alza, edge_baja, edge_combinado, CI95, p_greater por dirección.
    """
    from scipy.stats import binomtest

    acc_a = round(hits_alza / n_alza, 4) if n_alza > 0 else None
    acc_b = round(hits_baja / n_baja, 4) if n_baja > 0 else None

    # Edge aditivo en puntos porcentuales
    edge_a = round(acc_a - baseline_alza, 4) if acc_a is not None else None
    edge_b = round(acc_b - baseline_baja, 4) if acc_b is not None else None

    # One-sided binomial test: accuracy > baseline
    p_a = None
    if n_alza > 0:
        p_a = round(float(binomtest(hits_alza, n_alza, baseline_alza,
                                     alternative="greater").pvalue), 6)
    p_b = None
    if n_baja > 0:
        p_b = round(float(binomtest(hits_baja, n_baja, baseline_baja,
                                     alternative="greater").pvalue), 6)

    # CI95 via canonical _clopper_pearson_ci
    ci_a = _clopper_pearson_ci(hits_alza, n_alza) if n_alza > 0 else {"ci_lo": None, "ci_hi": None}
    ci_b = _clopper_pearson_ci(hits_baja, n_baja) if n_baja > 0 else {"ci_lo": None, "ci_hi": None}

    # Combined (ponderado por N)
    n_tot = n_alza + n_baja
    h_tot = hits_alza + hits_baja
    if n_tot > 0:
        base_cond = round((n_alza * baseline_alza + n_baja * baseline_baja) / n_tot, 4)
        acc_tot = round(h_tot / n_tot, 4)
        edge_comb = round(acc_tot - base_cond, 4)
        ci_tot = _clopper_pearson_ci(h_tot, n_tot)
    else:
        base_cond = acc_tot = edge_comb = None
        ci_tot = {"ci_lo": None, "ci_hi": None}

    return {
        "n_alza": n_alza,
        "hits_alza": hits_alza,
        "accuracy_alza": acc_a,
        "baseline_alza": round(baseline_alza, 4),
        "edge_alza": edge_a,
        "p_greater_alza": p_a,
        "ci95_alza": [ci_a["ci_lo"], ci_a["ci_hi"]],

        "n_baja": n_baja,
        "hits_baja": hits_baja,
        "accuracy_baja": acc_b,
        "baseline_baja": round(baseline_baja, 4),
        "edge_baja": edge_b,
        "p_greater_baja": p_b,
        "ci95_baja": [ci_b["ci_lo"], ci_b["ci_hi"]],

        "n_total": n_tot,
        "hits_total": h_tot,
        "accuracy_total": acc_tot,
        "baseline_condicionado": base_cond,
        "edge_combinado": edge_comb,
        "ci95_total": [ci_tot["ci_lo"], ci_tot["ci_hi"]],
    }
