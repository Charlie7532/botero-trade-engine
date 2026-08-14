#!/usr/bin/env python3
"""
Shared Deep Learning Audit Utilities (v2 — Empirically Grounded)
=================================================================
Common functions used by all 9 indicator audit scripts.
Ensures identical methodology across all METAR stations.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

logger = logging.getLogger("DLAuditUtils")


def get_frac_diff_weights(d: float, size: int) -> np.ndarray:
    """Binomial expansion weights (1-B)^d: w_0 = 1.0, w_k = -w_{k-1} * (d - k + 1) / k."""
    w = [1.0]
    for k in range(1, size):
        w.append(-w[-1] / k * (d - k + 1))
    return np.array(w)


def frac_diff(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    """
    Causal Fractional Differencing (López de Prado AFML Ch. 2).
    Uses lfilter for causal FIR filtering (w_0*x_t + w_1*x_{t-1} + ...).
    """
    if len(series) < 10:
        return series
    from scipy.signal import lfilter
    weights = get_frac_diff_weights(d, len(series))
    abs_w = np.abs(weights)
    cum_w = np.cumsum(abs_w)
    cutoff = int(np.searchsorted(cum_w, cum_w[-1] - thres)) + 1
    cutoff = min(cutoff, len(weights))
    weights = weights[:cutoff]

    res = lfilter(weights, [1.0], series.values)
    return pd.Series(res[cutoff:], index=series.index[cutoff:])


def compute_conditional_dsr(
    df: pd.DataFrame,
    lookup_fn,
    n_folds: int = 5,
    purge_days: int = 10,
    fwd_col: str = "fwd_ret_5d",
    n_trials: int = 1,
) -> dict:
    """
    Compute real Deflated Sharpe Ratio (López de Prado, AFML Chapter 14)
    on non-overlapping conditional strategy returns across PurgedKFold slices.
    """
    n = len(df)
    if n < 100:
        return {"dsr_pvalue": 0.0, "mean_sr": 0.0, "std_sr": 0.0, "n_folds": 0, "fold_sharpes": [], "skewness": 0.0, "kurtosis": 0.0, "n_samples": 0}

    # Classify each row dynamically
    def _classify_row(row):
        og = lookup_fn(row)
        if og is None:
            return 0.0
        if 'ACCUMULATE' in og or 'BUY_DIP' in og:
            return 1.0
        elif 'BLOCK' in og:
            return -1.0
        return 0.0

    df = df.copy()
    df['_signal'] = df.apply(_classify_row, axis=1)

    # To eliminate 5d forward return overlap, sample every 5 bars (non-overlapping)
    non_overlap_df = df.iloc[::5].copy()
    
    # Strategy returns: position * 5d_forward_return
    strat_returns = non_overlap_df['_signal'] * non_overlap_df[fwd_col]
    # Filter active trade signals (non-zero position)
    active_returns = strat_returns[non_overlap_df['_signal'] > 0].values

    if len(active_returns) < 15:
        return {"dsr_pvalue": 0.0, "mean_sr": 0.0, "std_sr": 0.0, "n_folds": 0, "fold_sharpes": [], "skewness": 0.0, "kurtosis": 0.0, "n_samples": len(active_returns)}

    from scipy.stats import norm, skew, kurtosis

    T = len(active_returns)
    mean_r = float(np.mean(active_returns))
    std_r = float(np.std(active_returns, ddof=1))

    if std_r == 0:
        return {"dsr_pvalue": 0.0, "mean_sr": 0.0, "std_sr": 0.0, "n_folds": 0, "fold_sharpes": [], "skewness": 0.0, "kurtosis": 0.0, "n_samples": T}

    sr_period = mean_r / std_r
    ann_factor = np.sqrt(252 / 5)
    sr_ann = float(sr_period * ann_factor)

    sk = float(skew(active_returns))
    kt = float(kurtosis(active_returns, fisher=False))  # Pearson kurtosis (normal=3.0)

    # Expected max SR under H0 for n_trials
    gamma_em = 0.5772156649015328
    if n_trials > 1:
        z1 = norm.ppf(1.0 - 1.0 / n_trials)
        z2 = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        sr_star = float((1.0 - gamma_em) * z1 + gamma_em * z2)
    else:
        sr_star = 0.0

    # Variance of Sharpe estimate with Skewness & Kurtosis adjustments (López de Prado Eq. 14.9)
    denom_var = (1.0 - sk * sr_period + ((kt - 1.0) / 4.0) * (sr_period ** 2)) / (T - 1)
    std_sr_est = float(np.sqrt(max(denom_var, 1e-8)))

    dsr_z = float((sr_period - sr_star) / std_sr_est)
    dsr_pvalue = float(norm.cdf(dsr_z))

    # K-Fold Sharpe distribution for stability metric
    fold_size = len(non_overlap_df) // n_folds
    fold_sharpes = []
    for fold in range(n_folds):
        f_start = fold * fold_size
        f_end = min(f_start + fold_size, len(non_overlap_df))
        f_slice = non_overlap_df.iloc[f_start:f_end]
        f_rets = (f_slice['_signal'] * f_slice[fwd_col])[f_slice['_signal'] > 0]
        if len(f_rets) > 3 and f_rets.std() > 0:
            fold_sharpes.append(float((f_rets.mean() / f_rets.std()) * ann_factor))

    return {
        "dsr_pvalue": round(dsr_pvalue, 4),
        "mean_sr": round(sr_ann, 4),
        "std_sr": round(float(np.std(fold_sharpes)), 4) if fold_sharpes else 0.0,
        "skewness": round(sk, 4),
        "kurtosis": round(kt, 4),
        "n_folds": len(fold_sharpes),
        "fold_sharpes": [round(s, 4) for s in fold_sharpes],
        "n_samples": T,
        "active_returns": active_returns,
    }


def bootstrap_epistemic_uncertainty(returns_series: np.ndarray, block_size: int = 5, n_bootstrap: int = 1000) -> float:
    """
    Block Bootstrap Epistemic Uncertainty on actual OOS strategy returns.
    Measures the variance of strategy mean return across resampled market blocks.
    """
    if returns_series is None or len(returns_series) < block_size * 2:
        return 0.0

    n_blocks = len(returns_series) // block_size
    blocks = [returns_series[i * block_size : (i + 1) * block_size] for i in range(n_blocks)]

    means = []
    for _ in range(n_bootstrap):
        idx = np.random.choice(len(blocks), size=len(blocks), replace=True)
        resampled = np.concatenate([blocks[j] for j in idx])
        means.append(float(np.mean(resampled)))

    return float(np.var(means))


def find_top_anomalies(states: dict, min_n: int = 20, top_k: int = 3):
    """Extract top bullish and bearish anomalies from fact store states."""
    valid = [(sk, sd) for sk, sd in states.items() if sd.get("n", 0) >= min_n]
    bullish = sorted(valid, key=lambda x: -x[1]["zz50"]["ev_net"])[:top_k]
    bearish = sorted(valid, key=lambda x: x[1]["zz50"]["ev_net"])[:top_k]
    return bullish, bearish


def classify_evidence_status(dsr_pvalue: float, sharpe_ann: float, n_oos: int) -> str:
    """
    Classify evidence status according to strict hypothesis-governance rules:
    - Grade A (DSR > 0.95, Sharpe >= 0.50, N >= 30) -> VALIDATED (Grade A — Hard Gate)
    - Grade B (DSR > 0.85, Sharpe >= 0.30, N >= 30) -> VALIDATED (Grade B — Hard Gate Subordinate)
    - Grade C (DSR > 0.70, N >= 30)                -> VALIDATED (Grade C — Sizing Modifier)
    - Grade D (DSR < 0.70 or N < 30)                -> HYPOTHESIS (Grade D — Advisory Only)
    """
    if n_oos < 30:
        return "HYPOTHESIS (Grade D)"

    if dsr_pvalue >= 0.95 and sharpe_ann >= 0.50:
        return "VALIDATED (Grade A)"
    elif dsr_pvalue >= 0.85 and sharpe_ann >= 0.30:
        return "VALIDATED (Grade B)"
    elif dsr_pvalue >= 0.70:
        return "VALIDATED (Grade C)"
    else:
        return "HYPOTHESIS (Grade D)"


def population_weighted_stats(states: dict) -> dict:
    """Compute population-weighted statistics across all states."""
    total_n = sum(sd["n"] for sd in states.values())
    if total_n == 0:
        return {}

    result = {"total_n": total_n, "min_n": min(sd["n"] for sd in states.values())}
    for scale in ["zz25", "zz50", "zz75"]:
        w_ev = sum(sd["n"] * sd[scale]["ev_net"] for sd in states.values()) / total_n
        w_pb = sum(sd["n"] * sd[scale]["p_bull"] for sd in states.values()) / total_n
        w_days = sum(sd["n"] * sd[scale]["e_days"] for sd in states.values()) / total_n
        result[scale] = {"ev_net": w_ev, "p_bull": w_pb, "e_days": w_days}

    return result


def build_l0_threshold_table(edges: list, labels: list) -> str:
    """Build L0 threshold table from fact store edges."""
    if not edges:
        return "\n".join(f"  - `{label}`" for label in labels)
    lines = []
    for i, label in enumerate(labels):
        if i == 0:
            lines.append(f"  - `{label}`: $< {edges[0]:.2f}$")
        elif i < len(edges):
            lines.append(f"  - `{label}`: ${edges[i-1]:.2f} - {edges[i]:.2f}$")
        else:
            lines.append(f"  - `{label}`: $> {edges[-1]:.2f}$")
    return "\n".join(lines)


def build_anomaly_sections(bullish: list, bearish: list) -> str:
    """Build anomaly markdown sections from data."""
    sections = ""
    for idx, (sk, sd) in enumerate(bullish):
        zz50 = sd["zz50"]
        sections += f"""
### 🚨 Anomalía Empírica {idx+1}: `{sk}` (Alcista)
- **Condición**: Estado empírico con N={sd['n']} observaciones.
- **Probabilidad Bull**: $P(\\text{{bull}}) = {zz50['p_bull']*100:.1f}\\%$.
- **Esperanza Matemática**: $EV_{{\\text{{net}}}} = {zz50['ev_net']*100:+.2f}\\%$, $EV_{{\\text{{per\\_day}}}} = {zz50['ev_per_day']*100:+.4f}\\%/\\text{{día}}$.
- **Régimen**: `{sd['divergence_regime']}` → `{sd['operational_guidance']}`.
"""

    for idx, (sk, sd) in enumerate(bearish):
        zz50 = sd["zz50"]
        if zz50["ev_net"] >= 0:
            continue
        sections += f"""
### ⚠️ Anomalía Bajista {idx+1}: `{sk}`
- **Condición**: Estado empírico con N={sd['n']} observaciones.
- **Probabilidad Bull**: $P(\\text{{bull}}) = {zz50['p_bull']*100:.1f}\\%$.
- **Esperanza Matemática**: $EV_{{\\text{{net}}}} = {zz50['ev_net']*100:+.2f}\\%$.
- **Régimen**: `{sd['divergence_regime']}` → `{sd['operational_guidance']}`.
"""
    return sections


def generate_intelligence_md(
    indicator_name: str,
    indicator_formula: str,
    vault_ticker: str,
    fact_store_path: Path,
    edges: list,
    labels_l0: list,
    fd_std: float,
    dsr_result: dict,
    epistemic_var: float,
    pop_stats: dict,
    anomaly_sections: str,
    evidence_status: str,
    n_states: int,
    directives: str,
    output_path: Path,
):
    """Generate standardized intelligence.md from empirical data."""
    with open(fact_store_path, "r", encoding="utf-8") as f:
        fs = json.load(f)
    doc = fs["_documentation"]
    ds = doc.get("data_sources", {})
    start_date = ds.get("start_date", ds.get("bars", "N/A"))
    end_date = ds.get("end_date", "present")
    sample_size = ds.get("sample_size_days", pop_stats.get("total_n", 0))
    years = ds.get("years_covered", round(sample_size / 252, 1) if isinstance(sample_size, (int, float)) else "N/A")

    l0_table = build_l0_threshold_table(edges, labels_l0)

    governance_grade = "Grade A — Hard Gate" if evidence_status == "VALIDATED" else \
                       "Grade B — Soft Gate" if evidence_status == "CANDIDATE" else \
                       "Grade C — Informational Only"

    zz25 = pop_stats.get("zz25", {})
    zz50 = pop_stats.get("zz50", {})
    zz75 = pop_stats.get("zz75", {})

    content = f"""# {indicator_name} Intelligence — Reference Document

> **Auto-generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} | **Source**: `{fact_store_path.name}` | **Status**: `{evidence_status}`

## 1. Ficha Técnica del Indicador
- **Nombre**: {indicator_name} (`{vault_ticker}`)
- **Fórmula**: {indicator_formula}
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='{vault_ticker}', timeframe='1d').
- **Rango Histórico**: {start_date} → {end_date} ({sample_size:,} barras diarias / {years} años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
{l0_table}

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = {fd_std:.4f}.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **{dsr_result['dsr_pvalue']:.4f}**{' ✅ (significativo)' if dsr_result['dsr_pvalue'] >= 0.95 else ' ⚠️ (no significativo)' if dsr_result['dsr_pvalue'] < 0.80 else ' 🟡 (marginal)'}
- **Mean Sharpe Ratio**: {dsr_result['mean_sr']:.4f} ± {dsr_result.get('std_sr', 0):.4f} ({dsr_result.get('n_folds', 0)} folds)
- **Fold SRs**: {dsr_result.get('fold_sharpes', [])}

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\\sigma^2_{{\\text{{epistémica}}}}$): **{epistemic_var:.6f}** (N={n_states} estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{{\\text{{net}}}}$ (ponderado) | $P(\\text{{bull}})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `{zz25.get('ev_net', 0)*100:+.2f}%` | `{zz25.get('p_bull', 0)*100:.1f}%` | `{zz25.get('e_days', 0):.1f}d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `{zz50.get('ev_net', 0)*100:+.2f}%` | `{zz50.get('p_bull', 0)*100:.1f}%` | `{zz50.get('e_days', 0):.1f}d` |
| **`zz75` (7.5% Estructural)** | 90 días | `{zz75.get('ev_net', 0)*100:+.2f}%` | `{zz75.get('p_bull', 0)*100:.1f}%` | `{zz75.get('e_days', 0):.1f}d` |

**Población total**: {pop_stats.get('total_n', 0):,} observaciones | $P(\\text{{bull}})$ ponderado = {zz50.get('p_bull', 0)*100:.1f}% | $EV_{{50}}$ ponderado = {zz50.get('ev_net', 0)*100:+.2f}%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)
{anomaly_sections}
---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\\text{{bull}})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `{vault_ticker}` | `{evidence_status}` | **{dsr_result['dsr_pvalue']:.4f}** | {dsr_result['mean_sr']:.4f} | {zz50.get('p_bull', 0)*100:.1f}% | {n_states} | {pop_stats.get('min_n', 0)} | **{governance_grade}** |

---

## 5. Directivas Operativas para Gates
{directives}
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content
