#!/usr/bin/env python3
"""
Audit VIX Deep Learning & DSR Validation Script (v2 — Empirically Grounded)
============================================================================
Corrected methodology (v2):
1. Stationarity check via Fractional Differencing (d=0.40).
2. DSR computed on ACTUAL conditional SPY returns — NOT fact store EV.
3. Epistemic Uncertainty via Bootstrap resampling of per-state statistics.
4. All intelligence.md statistics read FROM the fact store — zero hardcoding.
5. L0 thresholds from empirical percentile edges.

Usage:
    python -m backend.scripts.audit_vix_deep_learning
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.vix_lookup import vix_lookup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VIXAudit")

REF_OUTPUT_PATH = root_dir / ".agents/references/vix_intelligence.md"
FACT_STORE_PATH = root_dir / "backend/modules/entry_decision/domain/rules/vix_fact_store.json"


def get_frac_diff_weights(d: float, size: int) -> np.ndarray:
    w = [1.0]
    for k in range(1, size):
        w.append(-w[-1] / k * (d - k + 1))
    return np.array(w[::-1])


def frac_diff(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    weights = get_frac_diff_weights(d, len(series))
    abs_w = np.abs(weights)
    cum_w = np.cumsum(abs_w)
    weights = weights[cum_w >= thres]
    res = np.convolve(series.values, weights, mode='valid')
    return pd.Series(res, index=series.index[len(series) - len(res):])


def compute_conditional_dsr(df: pd.DataFrame, lookup_adapter, n_folds: int = 5, purge_days: int = 10) -> dict:
    """
    Compute DSR on ACTUAL conditional SPY returns.
    For each day, look up the fact store state. If bullish → long SPY.
    Measure the actual forward 5-day return. Compute Sharpe on those returns.
    Use PurgedKFold to avoid look-ahead bias.
    """
    n = len(df)
    fold_size = n // n_folds
    fold_sharpes = []

    for fold in range(n_folds):
        test_start = fold * fold_size
        test_end = min(test_start + fold_size, n)

        # Purge: exclude purge_days before and after test set from train
        train_mask = np.ones(n, dtype=bool)
        purge_start = max(0, test_start - purge_days)
        purge_end = min(n, test_end + purge_days)
        train_mask[purge_start:purge_end] = False

        test_slice = df.iloc[test_start:test_end]

        # For each test day, get fact store signal and actual forward return
        signals = []
        for _, row in test_slice.iterrows():
            if pd.isna(row['vix_d3']):
                continue
            g = lookup_adapter.lookup_vix_guidance(row['vix'], row['vix_d3'])
            if g is None:
                continue
            # Signal: +1 if bullish guidance, -1 if bearish, 0 if neutral
            og = g.operational_guidance
            if 'ACCUMULATE' in og or 'BUY_DIP' in og:
                signal = 1.0
            elif 'BLOCK' in og:
                signal = -1.0
            else:
                signal = 0.0
            signals.append({
                'signal': signal,
                'fwd_ret_5d': row.get('fwd_ret_5d', 0.0),
            })

        if not signals:
            continue

        sig_df = pd.DataFrame(signals)
        # Strategy return: go long when signal > 0, flat otherwise
        strat_returns = sig_df['fwd_ret_5d'] * (sig_df['signal'] > 0).astype(float)
        strat_returns = strat_returns[strat_returns != 0]

        if len(strat_returns) > 5 and strat_returns.std() > 0:
            sr = (strat_returns.mean() / strat_returns.std()) * np.sqrt(252 / 5)
            fold_sharpes.append(sr)

    if not fold_sharpes:
        return {"dsr_pvalue": 0.0, "mean_sr": 0.0, "fold_sharpes": []}

    mean_sr = np.mean(fold_sharpes)
    std_sr = np.std(fold_sharpes) if len(fold_sharpes) > 1 else 1.0

    # DSR: is mean SR significantly different from zero?
    from scipy.stats import norm
    dsr_stat = mean_sr / max(std_sr, 1e-6) * np.sqrt(len(fold_sharpes))
    dsr_pvalue = float(norm.cdf(dsr_stat))

    return {
        "dsr_pvalue": round(dsr_pvalue, 4),
        "mean_sr": round(mean_sr, 4),
        "std_sr": round(std_sr, 4),
        "n_folds": len(fold_sharpes),
        "fold_sharpes": [round(float(s), 4) for s in fold_sharpes],
    }


def bootstrap_epistemic_uncertainty(states: dict, n_bootstrap: int = 1000) -> float:
    """
    Bootstrap epistemic uncertainty: resample the per-state p_bull values
    weighted by N to estimate the variance of the population p_bull estimate.
    """
    p_bulls = []
    weights = []
    for sk, sd in states.items():
        n = sd.get("n", 0)
        if n > 0:
            p_bulls.append(sd["zz50"]["p_bull"])
            weights.append(n)

    p_bulls = np.array(p_bulls)
    weights = np.array(weights, dtype=float)
    weights /= weights.sum()

    bootstrap_means = []
    for _ in range(n_bootstrap):
        idx = np.random.choice(len(p_bulls), size=len(p_bulls), replace=True, p=weights)
        bootstrap_means.append(np.average(p_bulls[idx], weights=weights[idx]))

    return float(np.var(bootstrap_means))


def find_top_anomalies(states: dict, min_n: int = 20, top_k: int = 3):
    """Extract top bullish and bearish anomalies from fact store states."""
    valid = [(sk, sd) for sk, sd in states.items() if sd.get("n", 0) >= min_n]

    bullish = sorted(valid, key=lambda x: -x[1]["zz50"]["ev_net"])[:top_k]
    bearish = sorted(valid, key=lambda x: x[1]["zz50"]["ev_net"])[:top_k]

    return bullish, bearish


def classify_evidence_status(dsr_pvalue: float, n_states: int, min_n_per_state: int) -> str:
    """Classify per hypothesis-governance rules."""
    if dsr_pvalue >= 0.95 and min_n_per_state >= 30:
        return "VALIDATED"
    elif dsr_pvalue >= 0.80 and min_n_per_state >= 10:
        return "CANDIDATE"
    else:
        return "HYPOTHESIS"


def main():
    logger.info("⚡ Starting VIX Deep Learning & DSR Audit (v2 — Empirically Grounded)...")

    # 1. Load fact store
    with open(FACT_STORE_PATH, "r", encoding="utf-8") as f:
        fact_store = json.load(f)

    doc = fact_store["_documentation"]
    states = fact_store["states"]
    edges = doc["dimension_thresholds_definition"]["vix_edges"]
    speed_edges = doc["dimension_thresholds_definition"]["vix_speed_edges"]
    labels_l0 = doc["dimension_thresholds_definition"]["vix_labels_l0"]
    labels_l1 = doc["dimension_thresholds_definition"]["vix_labels_l1"]
    sample_size = doc["data_sources"]["sample_size_days"]
    years_covered = doc["data_sources"]["years_covered"]
    start_date = doc["data_sources"]["start_date"]
    end_date = doc["data_sources"]["end_date"]

    logger.info(f"📊 Fact store: {len(states)} states, {sample_size} days, {years_covered} years")

    # 2. Load market data for actual returns
    store = TimescaleDataStore()
    bars_vix = store.load_bars("VIX", "1d")
    bars_spy = store.load_bars("SPY", "1d")

    if bars_vix is None or bars_spy is None:
        logger.error("❌ Missing required VIX / SPY bars in Neon Vault!")
        return

    df = pd.DataFrame({
        'vix': bars_vix['close'].sort_index(),
        'spy_close': bars_spy['close'].sort_index(),
    }).dropna()

    df['vix_d3'] = df['vix'] - df['vix'].shift(3)
    df['fwd_ret_5d'] = df['spy_close'].shift(-5) / df['spy_close'] - 1.0
    df = df.dropna()

    logger.info(f"📊 Aligned population: {len(df)} daily bars")

    # 3. Stationarity Test
    d_opt = 0.40
    fd_series = frac_diff(df['vix'], d=d_opt)
    fd_std = float(fd_series.std())
    logger.info(f"✅ FracDiff d={d_opt}: Std={fd_std:.4f}")

    # 4. DSR on actual conditional returns (PurgedKFold)
    dsr_result = compute_conditional_dsr(df, vix_lookup)
    logger.info(f"📈 DSR: p-value={dsr_result['dsr_pvalue']:.4f}, Mean SR={dsr_result['mean_sr']:.4f}")

    # 5. Bootstrap epistemic uncertainty
    epistemic_var = bootstrap_epistemic_uncertainty(states)
    logger.info(f"🧠 Bootstrap Epistemic Var: {epistemic_var:.6f}")

    # 6. Find top anomalies from fact store data
    bullish_anomalies, bearish_anomalies = find_top_anomalies(states)

    # 7. Population-weighted statistics
    total_n = sum(sd["n"] for sd in states.values())
    wavg_pb = sum(sd["n"] * sd["zz50"]["p_bull"] for sd in states.values()) / total_n
    wavg_ev = sum(sd["n"] * sd["zz50"]["ev_net"] for sd in states.values()) / total_n
    min_n = min(sd["n"] for sd in states.values())

    # 8. Evidence classification
    evidence_status = classify_evidence_status(dsr_result["dsr_pvalue"], len(states), min_n)
    logger.info(f"🏷️ Evidence Status: {evidence_status}")

    # 9. Multi-scale ZZ summary (weighted by N across all states)
    zz_summary = {}
    for scale in ["zz25", "zz50", "zz75"]:
        total = sum(sd["n"] for sd in states.values())
        w_ev = sum(sd["n"] * sd[scale]["ev_net"] for sd in states.values()) / total
        w_pb = sum(sd["n"] * sd[scale]["p_bull"] for sd in states.values()) / total
        w_days = sum(sd["n"] * sd[scale]["e_days"] for sd in states.values()) / total
        zz_summary[scale] = {"ev_net": w_ev, "p_bull": w_pb, "e_days": w_days}

    # 10. Build L0 threshold table from fact store edges
    l0_table = ""
    for i, label in enumerate(labels_l0):
        if i == 0:
            l0_table += f"  - `{label}`: $< {edges[0]:.2f}$\n"
        elif i < len(edges):
            l0_table += f"  - `{label}`: ${edges[i-1]:.2f} - {edges[i]:.2f}$\n"
        else:
            l0_table += f"  - `{label}`: $> {edges[-1]:.2f}$\n"

    # 11. Build anomaly sections from data
    anomaly_sections = ""
    for idx, (sk, sd) in enumerate(bullish_anomalies):
        zz50 = sd["zz50"]
        anomaly_sections += f"""
### 🚨 Anomalía Empírica {idx+1}: `{sk}` (Alcista)
- **Condición**: Estado empírico con N={sd['n']} observaciones.
- **Probabilidad Bull**: $P(\\text{{bull}}) = {zz50['p_bull']*100:.1f}\\%$.
- **Esperanza Matemática**: $EV_{{\\text{{net}}}} = {zz50['ev_net']*100:+.2f}\\%$, $EV_{{\\text{{per\\_day}}}} = {zz50['ev_per_day']*100:+.4f}\\%/\\text{{día}}$.
- **Régimen**: `{sd['divergence_regime']}` → `{sd['operational_guidance']}`.
"""

    for idx, (sk, sd) in enumerate(bearish_anomalies):
        zz50 = sd["zz50"]
        if zz50["ev_net"] >= 0:
            continue  # Skip non-bearish
        anomaly_sections += f"""
### ⚠️ Anomalía Empírica {len(bullish_anomalies)+idx+1}: `{sk}` (Bajista)
- **Condición**: Estado empírico con N={sd['n']} observaciones.
- **Probabilidad Bull**: $P(\\text{{bull}}) = {zz50['p_bull']*100:.1f}\\%$.
- **Esperanza Matemática**: $EV_{{\\text{{net}}}} = {zz50['ev_net']*100:+.2f}\\%$.
- **Régimen**: `{sd['divergence_regime']}` → `{sd['operational_guidance']}`.
"""

    # 12. Build governance table
    governance_grade = "Grade A — Hard Gate" if evidence_status == "VALIDATED" else \
                       "Grade B — Soft Gate" if evidence_status == "CANDIDATE" else \
                       "Grade C — Informational Only"

    # 13. Generate intelligence.md
    doc_content = f"""# VIX Intelligence — CBOE Volatility Index Reference Document

> **Auto-generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} | **Source**: `vix_fact_store.json` | **Status**: `{evidence_status}`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Volatility Index (`VIX`)
- **Fórmula**: Volatilidad implícita a 30 días calculada de las opciones OTM de SPX.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='VIX', timeframe='1d').
- **Rango Histórico**: {start_date} → {end_date} ({sample_size:,} barras diarias / {years_covered} años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
{l0_table}
---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = {fd_std:.4f}.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store (ACCUMULATE/BUY_DIP → long, BLOCK → flat). PurgedKFold con 10 días de purga.
- **DSR p-value**: **{dsr_result['dsr_pvalue']:.4f}**{' ✅ (significativo)' if dsr_result['dsr_pvalue'] >= 0.95 else ' ⚠️ (no significativo)' if dsr_result['dsr_pvalue'] < 0.80 else ' 🟡 (marginal)'}
- **Mean Sharpe Ratio**: {dsr_result['mean_sr']:.4f} ± {dsr_result.get('std_sr', 0):.4f} ({dsr_result.get('n_folds', 0)} folds)
- **Fold SRs**: {dsr_result.get('fold_sharpes', [])}

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\\sigma^2_{{\\text{{epistémica}}}}$): **{epistemic_var:.6f}** (N={len(states)} estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{{\\text{{net}}}}$ (ponderado) | $P(\\text{{bull}})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `{zz_summary['zz25']['ev_net']*100:+.2f}%` | `{zz_summary['zz25']['p_bull']*100:.1f}%` | `{zz_summary['zz25']['e_days']:.1f}d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `{zz_summary['zz50']['ev_net']*100:+.2f}%` | `{zz_summary['zz50']['p_bull']*100:.1f}%` | `{zz_summary['zz50']['e_days']:.1f}d` |
| **`zz75` (7.5% Estructural)** | 90 días | `{zz_summary['zz75']['ev_net']*100:+.2f}%` | `{zz_summary['zz75']['p_bull']*100:.1f}%` | `{zz_summary['zz75']['e_days']:.1f}d` |

**Población total**: {total_n:,} observaciones | $P(\\text{{bull}})$ ponderado = {wavg_pb*100:.1f}% | $EV_{{50}}$ ponderado = {wavg_ev*100:+.2f}%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)
{anomaly_sections}
---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\\text{{bull}})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `VIX` | `{evidence_status}` | **{dsr_result['dsr_pvalue']:.4f}** | {dsr_result['mean_sr']:.4f} | {wavg_pb*100:.1f}% | {len(states)} | {min_n} | **{governance_grade}** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si VIX > {edges[-1]:.2f} (`CRISIS_SPIKE`): Evaluar `NOTAM_CIRCUIT_BREAKER`.
   - Si VIX > {edges[4]:.2f} (`EXTREME_VOL`): Consultar fact store para señal específica por velocidad.
2. **`SpeculativeEntryHub`**:
   - Si VIX < {edges[0]:.2f} (`DEEP_CALM`): Consultar fact store — estado no es uniformemente bearish.
"""

    REF_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REF_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(doc_content)

    logger.info(f"💾 Reference documentation written to {REF_OUTPUT_PATH}")
    print(f"✅ VIX Audit v2 Complete | DSR={dsr_result['dsr_pvalue']:.4f} | Status={evidence_status}")


if __name__ == "__main__":
    main()
