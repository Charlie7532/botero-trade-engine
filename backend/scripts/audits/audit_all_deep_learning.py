#!/usr/bin/env python3
"""
Unified Deep Learning Audit — All 9 METAR Indicators (v2)
===========================================================
Runs corrected DSR validation (actual conditional SPY returns),
bootstrap epistemic uncertainty, and generates intelligence.md
for ALL 9 indicators in a single execution.

Methodology:
- DSR computed on ACTUAL 5-day SPY forward returns, conditioned by fact store signal
- PurgedKFold with 10-day purge window
- Bootstrap epistemic uncertainty (1000 resamples of per-state p_bull)
- All statistics read programmatically from fact stores
- L0 thresholds from empirical percentile edges

Usage:
    python -m backend.scripts.audit_all_deep_learning
"""
import sys
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.scripts._lib.dl_audit_utils import (
    frac_diff, compute_conditional_dsr, bootstrap_epistemic_uncertainty,
    find_top_anomalies, classify_evidence_status, population_weighted_stats,
    build_anomaly_sections, generate_intelligence_md,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UnifiedDLAudit")

RULES_DIR = root_dir / "backend/modules/entry_decision/domain/rules"
REF_DIR = root_dir / ".agents/references"


# ─── Composite Indicator Loaders ──────────────────────────────────────────────

def load_credit_ratio(store) -> pd.Series:
    """Credit stress = HYG / TLT (high yield vs treasury)."""
    hyg = store.load_bars("HYG", "1d")
    tlt = store.load_bars("TLT", "1d")
    if hyg is None or tlt is None:
        return pd.Series(dtype=float)
    ratio = (hyg['close'] / tlt['close']).sort_index().dropna()
    return ratio


def load_yield_spread(store) -> pd.Series:
    """Yield curve spread = TNX - IRX (10Y - 3M)."""
    tnx = store.load_bars("TNX", "1d")
    irx = store.load_bars("IRX", "1d")
    if tnx is None or irx is None:
        return pd.Series(dtype=float)
    spread = (tnx['close'] - irx['close']).sort_index().dropna()
    return spread


def load_rotation_index(store) -> pd.Series:
    """Rotation = z(XLY/XLP, 252d) + z(XLK/XLU, 252d)."""
    xly = store.load_bars("XLY", "1d")
    xlp = store.load_bars("XLP", "1d")
    xlk = store.load_bars("XLK", "1d")
    xlu = store.load_bars("XLU", "1d")
    if any(x is None for x in [xly, xlp, xlk, xlu]):
        return pd.Series(dtype=float)

    r1 = (xly['close'] / xlp['close']).sort_index()
    r2 = (xlk['close'] / xlu['close']).sort_index()

    common = r1.index.intersection(r2.index)
    r1, r2 = r1.loc[common], r2.loc[common]

    m1 = r1.rolling(252, min_periods=20).mean()
    s1 = r1.rolling(252, min_periods=20).std().replace(0, np.nan)
    z1 = (r1 - m1) / s1

    m2 = r2.rolling(252, min_periods=20).mean()
    s2 = r2.rolling(252, min_periods=20).std().replace(0, np.nan)
    z2 = (r2 - m2) / s2

    return (z1 + z2).dropna()



# ─── Indicator Configs ────────────────────────────────────────────────────────

INDICATORS = [
    {
        "name": "VIX",
        "full_name": "CBOE Volatility Index",
        "formula": "Volatilidad implícita a 30 días calculada de las opciones OTM de SPX.",
        "vault_ticker": "VIX",
        "fact_store": "vix_fact_store.json",
        "output": "vix_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.vix_lookup",
        "lookup_instance": "vix_lookup",
        "lookup_method": "lookup_vix_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "vix_edges",
        "label_key": "vix_labels_l0",
        "directives": """1. **`QualityEntryGate`**: Consultar fact store para señal específica por nivel + velocidad.
2. **`SpeculativeEntryHub`**: En estados `FULL_STRUCTURAL_BEAR`, respetar el bloqueo.""",
    },
    {
        "name": "VVIX",
        "full_name": "CBOE VVIX (Volatility of VIX)",
        "formula": "Volatilidad implícita del VIX — mide la inestabilidad del mercado de volatilidad.",
        "vault_ticker": "VVIX",
        "fact_store": "vvix_fact_store.json",
        "output": "vvix_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.vvix_lookup",
        "lookup_instance": "vvix_lookup",
        "lookup_method": "lookup_vvix_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "vvix_edges",
        "label_key": "vvix_labels_l0",
        "directives": """1. **`QualityEntryGate`**: VVIX es confirmador de régimen de VIX, no señal primaria.
2. **`SpeculativeEntryHub`**: VVIX > P95 indica transición de régimen vol.""",
    },
    {
        "name": "PCR",
        "full_name": "CBOE Put/Call Ratio",
        "formula": "Ratio total de volumen de puts vs calls en opciones CBOE.",
        "vault_ticker": "CBOE_PCR",
        "fact_store": "pcr_fact_store.json",
        "output": "pcr_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.pcr_lookup",
        "lookup_instance": "pcr_lookup",
        "lookup_method": "lookup_pcr_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "pcr_edges",
        "label_key": "pcr_labels_l0",
        "directives": """1. **`QualityEntryGate`**: PCR extremo (P95) es señal contrarian, no de pánico.
2. **`SpeculativeEntryHub`**: Consultar régimen de divergencia antes de actuar.""",
    },
    {
        "name": "Fear & Greed",
        "full_name": "CNN Fear & Greed Index",
        "formula": "Índice compuesto CNN de 7 indicadores de sentimiento (0=miedo extremo, 100=codicia extrema).",
        "vault_ticker": "FG",
        "fact_store": "fg_fact_store.json",
        "output": "fg_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.fg_lookup",
        "lookup_instance": "fg_lookup",
        "lookup_method": "lookup_fg_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "fg_edges",
        "label_key": "_infer_from_states",
        "directives": """1. **`QualityEntryGate`**: Fear extremo es contrarian — BUT requiere confirmación por velocidad.
2. **Greed extremo NO es señal bajista** — data empírica muestra EV positivo.""",
    },
    {
        "name": "SV5 Turbulence",
        "full_name": "SV5 Institutional Volume Turbulence",
        "formula": "std(Δ_SV5TW, 10d) — desviación estándar del cambio en participación institucional.",
        "vault_ticker": "SV5_TURBULENCE",
        "fact_store": "sv5_turbulence_fact_store.json",
        "output": "sv5_turbulence_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup",
        "lookup_instance": "sv5_turbulence_lookup",
        "lookup_method": "lookup_sv5_turbulence_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "turbulence_edges",
        "label_key": "turbulence_labels_l0",
        "directives": """1. **`QualityEntryGate`**: Turbulencia > P95 indica régimen de vol institucional.
2. **`CIO Allocator`**: Turbulencia es proxy de VIX cuando VIX no está disponible.""",
    },
    {
        "name": "SKEW",
        "full_name": "CBOE SKEW Index",
        "formula": "Medida de riesgo de cola: demanda de puts OTM en SPX. 100=neutral, >130=cola activa.",
        "vault_ticker": "SKEW",
        "fact_store": "skew_fact_store.json",
        "output": "skew_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.skew_lookup",
        "lookup_instance": "skew_lookup",
        "lookup_method": "lookup_skew_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "skew_edges",
        "label_key": "_infer_from_states",
        "directives": """1. **`QualityEntryGate`**: SKEW extremo (P95) indica protección de cola activa.
2. **`SpeculativeEntryHub`**: Consultar régimen de divergencia por velocidad.""",
    },
    {
        "name": "Credit Stress",
        "full_name": "High Yield Corporate Credit Stress Ratio (HYG/LQD)",
        "formula": "Ratio HYG/LQD — mide apetito por riesgo crediticio vs crédito investment-grade.",
        "vault_ticker": "CREDIT",
        "data_loader": load_credit_ratio,
        "fact_store": "credit_fact_store.json",
        "output": "credit_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.credit_lookup",
        "lookup_instance": "credit_lookup",
        "lookup_method": "lookup_credit_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "credit_edges",
        "label_key": "credit_labels_l0",
        "directives": """1. **`QualityEntryGate`**: Credit stress alto (P05-P15) es zona de alerta SIGMET.
2. **`CIO Allocator`**: Credit es dimensión independiente de volatilidad (bond market).""",
    },
    {
        "name": "Yield Curve",
        "full_name": "US Treasury Yield Curve Spread (TNX - IRX)",
        "formula": "Diferencial de rendimiento entre bonos del Tesoro a 10 años (TNX) y 3 meses (IRX).",
        "vault_ticker": "YIELD_CURVE",
        "data_loader": load_yield_spread,
        "fact_store": "yield_curve_fact_store.json",
        "output": "yield_curve_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.yield_curve_lookup",
        "lookup_instance": "yield_curve_lookup",
        "lookup_method": "lookup_yield_curve_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "yield_edges",
        "label_key": "yield_labels_l0",
        "directives": """1. **`QualityEntryGate`**: Inversión profunda (P05) es SIGMET — pero es crónica, filtrar por velocidad.
2. **`CIO Allocator`**: Yield curve es dimensión macro independiente.""",
    },
    {
        "name": "Sector Rotation",
        "full_name": "Defensive/Cyclical Sector Rotation Index",
        "formula": "Z-score de ratio XLY/XLP + XLK/XLU (rolling 252d) — mide rotación defensiva/cíclica.",
        "vault_ticker": "ROTATION",
        "data_loader": load_rotation_index,
        "fact_store": "rotation_fact_store.json",
        "output": "rotation_intelligence.md",
        "lookup_module": "backend.modules.entry_decision.domain.rules.rotation_lookup",
        "lookup_instance": "rotation_lookup",
        "lookup_method": "lookup_rotation_guidance",
        "lookup_args": lambda row: (row['indicator'], row['indicator_d3']),
        "edge_key": "rotation_edges",
        "label_key": "rotation_labels_l0",
        "directives": """1. **`QualityEntryGate`**: Rotación defensiva extrema (P05-P15) es SIGMET.
2. **`CIO Allocator`**: Rotation es dimensión de flujo de equity independiente.""",
    },
]


def load_indicator_data(store, vault_ticker: str) -> pd.Series:
    """Load indicator close values from Vault."""
    bars = store.load_bars(vault_ticker, "1d")
    if bars is None or bars.empty:
        return pd.Series(dtype=float)
    return bars['close'].sort_index()


def audit_single_indicator(config: dict, spy_close: pd.Series, store) -> dict:
    """Run full audit for a single indicator."""
    name = config["name"]
    logger.info(f"{'='*60}")
    logger.info(f"  Auditing: {name} ({config['vault_ticker']})")
    logger.info(f"{'='*60}")

    # Load fact store
    fs_path = RULES_DIR / config["fact_store"]
    if not fs_path.exists():
        logger.error(f"  ❌ Missing fact store: {fs_path}")
        return {"status": "ERROR", "name": name}

    with open(fs_path, "r", encoding="utf-8") as f:
        fact_store = json.load(f)

    doc = fact_store["_documentation"]
    states = fact_store["states"]
    thresh = doc["dimension_thresholds_definition"]
    edge_k = config["edge_key"]
    edges = thresh.get(edge_k, thresh.get(f"{edge_k}_d1", thresh.get(f"{config['name'].lower()}_edges_d1", [])))

    # Get labels: from fact store if available, else infer from state keys
    label_key = config["label_key"]
    if label_key == "_infer_from_states" or label_key not in thresh:
        # Infer L0 labels from state keys, sorted by their first edge match
        levels = sorted(set(sk.split('__')[0] for sk in states))
        labels_l0 = levels
    else:
        labels_l0 = thresh[label_key]

    logger.info(f"  Fact store: {len(states)} states")

    # Load indicator data (direct ticker or composite loader)
    custom_loader = config.get("data_loader")
    if custom_loader:
        indicator_data = custom_loader(store)
    else:
        indicator_data = load_indicator_data(store, config["vault_ticker"])

    if indicator_data.empty:
        logger.error(f"  ❌ No data for {config['vault_ticker']} in Vault")
        return {"status": "ERROR", "name": name}

    # Align with SPY
    df = pd.DataFrame({
        'indicator': indicator_data,
        'spy_close': spy_close,
    }).dropna()

    df['indicator_d3'] = df['indicator'] - df['indicator'].shift(3)
    df['fwd_ret_5d'] = df['spy_close'].shift(-5) / df['spy_close'] - 1.0
    df = df.dropna()
    logger.info(f"  Aligned population: {len(df)} bars")

    # Fractional Differencing
    fd_series = frac_diff(df['indicator'], d=0.40)
    fd_std = float(fd_series.std()) if len(fd_series) > 0 else 0.0
    logger.info(f"  FracDiff d=0.40: Std={fd_std:.4f}")

    # Load lookup adapter dynamically
    import importlib
    mod = importlib.import_module(config["lookup_module"])
    adapter = getattr(mod, config["lookup_instance"])
    lookup_method = getattr(adapter, config["lookup_method"])

    def lookup_fn(row):
        try:
            args = config["lookup_args"](row)
            if any(pd.isna(a) for a in args):
                return None
            g = lookup_method(*args)
            if g is None:
                return None
            return g.operational_guidance
        except Exception:
            return None

    # DSR on actual non-overlapping conditional returns (López de Prado AFML Ch. 14)
    dsr_result = compute_conditional_dsr(df, lookup_fn)
    logger.info(f"  DSR: p-value={dsr_result['dsr_pvalue']:.4f}, Ann SR={dsr_result['mean_sr']:.4f}, Skew={dsr_result['skewness']}, Kurt={dsr_result['kurtosis']}")

    # Block Bootstrap epistemic uncertainty on actual strategy returns
    epistemic_var = bootstrap_epistemic_uncertainty(dsr_result.get("active_returns", np.array([])))
    logger.info(f"  Epistemic Var (Block Bootstrap): {epistemic_var:.6f}")

    # Population stats
    pop_stats = population_weighted_stats(states)

    # Anomalies
    bullish, bearish = find_top_anomalies(states)
    anomaly_sections = build_anomaly_sections(bullish, bearish)

    # Evidence classification (evaluated against out-of-sample trade count N_OOS)
    evidence_status = classify_evidence_status(dsr_result["dsr_pvalue"], dsr_result["mean_sr"], dsr_result["n_samples"])
    logger.info(f"  Evidence Status: {evidence_status}")

    # Generate intelligence.md
    output_path = REF_DIR / config["output"]
    generate_intelligence_md(
        indicator_name=config["full_name"],
        indicator_formula=config["formula"],
        vault_ticker=config["vault_ticker"],
        fact_store_path=fs_path,
        edges=edges,
        labels_l0=labels_l0,
        fd_std=fd_std,
        dsr_result=dsr_result,
        epistemic_var=epistemic_var,
        pop_stats=pop_stats,
        anomaly_sections=anomaly_sections,
        evidence_status=evidence_status,
        n_states=len(states),
        directives=config["directives"],
        output_path=output_path,
    )

    logger.info(f"  ✅ Saved: {output_path}")

    return {
        "status": "OK",
        "name": name,
        "evidence_status": evidence_status,
        "dsr_pvalue": dsr_result["dsr_pvalue"],
        "mean_sr": dsr_result["mean_sr"],
        "epistemic_var": epistemic_var,
        "n_states": len(states),
        "population_n": pop_stats.get("total_n", 0),
        "min_n": pop_stats.get("min_n", 0),
    }


def main():
    logger.info("="*80)
    logger.info("  UNIFIED DEEP LEARNING AUDIT — ALL 9 METAR INDICATORS (v2)")
    logger.info("  Methodology: Actual conditional SPY returns, PurgedKFold DSR")
    logger.info("="*80)

    t0 = time.time()
    store = TimescaleDataStore()

    # Load SPY once for all indicators
    spy_bars = store.load_bars("SPY", "1d")
    if spy_bars is None:
        logger.error("❌ Missing SPY bars in Vault!")
        return
    spy_close = spy_bars['close'].sort_index()
    logger.info(f"SPY loaded: {len(spy_close)} bars")

    # Run all indicators
    results = []
    for config in INDICATORS:
        try:
            result = audit_single_indicator(config, spy_close, store)
            results.append(result)
        except Exception as e:
            logger.error(f"❌ {config['name']} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append({"status": "ERROR", "name": config["name"], "error": str(e)})

    elapsed = time.time() - t0

    # Summary table
    print(f"\n{'='*100}")
    print(f"  AUDIT SUMMARY — {len([r for r in results if r['status'] == 'OK'])}/{len(results)} OK | Time: {elapsed:.1f}s")
    print(f"{'='*100}")
    print(f"  {'Indicator':<20s} | {'Status':<12s} | {'DSR':>6s} | {'SR':>7s} | {'Epistemic':>10s} | {'N States':>8s} | {'Min N':>6s} | Evidence")
    print(f"  {'-'*18:<20s} | {'-'*10:<12s} | {'-'*6:>6s} | {'-'*7:>7s} | {'-'*10:>10s} | {'-'*8:>8s} | {'-'*6:>6s} | {'-'*12}")
    for r in results:
        if r["status"] == "OK":
            print(f"  {r['name']:<20s} | {'✅ OK':<12s} | {r['dsr_pvalue']:>6.4f} | {r['mean_sr']:>7.4f} | {r['epistemic_var']:>10.6f} | {r['n_states']:>8d} | {r['min_n']:>6d} | {r['evidence_status']}")
        else:
            print(f"  {r['name']:<20s} | {'❌ ERROR':<12s} | {'—':>6s} | {'—':>7s} | {'—':>10s} | {'—':>8s} | {'—':>6s} | —")


if __name__ == "__main__":
    main()
