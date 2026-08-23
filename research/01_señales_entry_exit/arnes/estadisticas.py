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
