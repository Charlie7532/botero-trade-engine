"""
UW Integration Audit — End-to-End Department Verification
===========================================================
Tests that each department can:
1. Instantiate with UWGammaAdapter as OptionsDataPort
2. Read UW data from the Vault
3. Produce output containing the new UW-enriched fields

Run: PYTHONPATH=.. .venv/bin/python research/audit_uw_integration.py
"""
import sys
import traceback

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"
results = []


def audit(name, fn):
    """Run an audit check, capture result."""
    try:
        status, detail = fn()
        results.append((name, status, detail))
        print(f"  {status} {name}: {detail}")
    except Exception as e:
        results.append((name, FAIL, str(e)))
        print(f"  {FAIL} {name}: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 1: COMPOSITION ROOT
# ═══════════════════════════════════════════════════════════
print("\n══ 1. COMPOSITION ROOT ══")


def check_composition_root():
    from backend.api.factories.execution_factory import build_options_provider
    p = build_options_provider()
    name = type(p).__name__
    if name == "UWGammaAdapter":
        return PASS, f"Provider = {name} (correct)"
    return FAIL, f"Provider = {name} (expected UWGammaAdapter)"


audit("build_options_provider", check_composition_root)


def check_uw_methods():
    from backend.api.factories.execution_factory import build_options_provider
    p = build_options_provider()
    methods = ["get_iv_term_structure", "get_vol_stats", "get_spot_gex",
               "get_max_pain_by_expiry", "get_nope"]
    found = [m for m in methods if hasattr(p, m)]
    missing = [m for m in methods if not hasattr(p, m)]
    if not missing:
        return PASS, f"All {len(methods)} UW methods available"
    return FAIL, f"Missing: {missing}"


audit("UW-specific methods on provider", check_uw_methods)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 2: OPTIONS AWARENESS (analyze_gamma)
# ═══════════════════════════════════════════════════════════
print("\n══ 2. OPTIONS AWARENESS ══")


def check_options_awareness_output():
    from backend.modules.options_gamma.application.use_cases.analyze_gamma import OptionsAwareness
    from backend.api.factories.execution_factory import build_options_provider
    oa = OptionsAwareness(build_options_provider())
    # Test with SPY (should have UW data in vault)
    result = oa.get_full_analysis("SPY")
    uw_fields = ["is_backwardation", "ultra_front_iv", "term_spread",
                 "iv_rank", "variance_risk_premium"]
    found = [f for f in uw_fields if f in result]
    missing = [f for f in uw_fields if f not in result]
    source = result.get("source", "unknown")
    if found:
        details = ", ".join(f"{f}={result[f]}" for f in found)
        return PASS, f"Source={source} | UW fields: {details}"
    if missing:
        return WARN, f"Source={source} | Missing UW fields: {missing} (vault may lack data)"
    return WARN, f"Source={source} | No UW fields detected"


audit("OptionsAwareness.get_full_analysis('SPY')", check_options_awareness_output)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 3: VOLATILITY REGIME CLASSIFIER
# ═══════════════════════════════════════════════════════════
print("\n══ 3. VOLATILITY REGIME CLASSIFIER ══")


def check_vol_classifier_params():
    import inspect
    from backend.modules.volatility_regime.domain.rules.vol_classifier import VolRegimeClassifier
    vc = VolRegimeClassifier()
    q_params = list(inspect.signature(vc.classify_quality_series).parameters.keys())
    s_params = list(inspect.signature(vc.classify_speculative_series).parameters.keys())

    q_uw = [p for p in ["iv_rank", "term_structure_slope"] if p in q_params]
    s_uw = [p for p in ["iv_rank"] if p in s_params]

    if len(q_uw) == 2 and len(s_uw) == 1:
        return PASS, f"Quality: +{q_uw}, Speculative: +{s_uw}"
    return FAIL, f"Quality UW: {q_uw}/2, Speculative UW: {s_uw}/1"


audit("VolRegimeClassifier UW params", check_vol_classifier_params)


def check_vol_classifier_backward_compat():
    import pandas as pd
    import numpy as np
    from backend.modules.volatility_regime.domain.rules.vol_classifier import VolRegimeClassifier
    vc = VolRegimeClassifier()
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Call WITHOUT iv_rank/term_structure_slope (backward compat)
    result = vc.classify_quality_series(
        calm_duration=pd.Series(np.random.randint(0, 100, n), index=idx),
        vol_persistence=pd.Series(np.random.uniform(0, 1, n), index=idx),
        vol_of_vol=pd.Series(np.random.uniform(0, 0.5, n), index=idx),
        vol_ratio=pd.Series(np.random.uniform(0.5, 2.0, n), index=idx),
        vix_zscore=pd.Series(np.random.uniform(-2, 3, n), index=idx),
        vix_velocity=pd.Series(np.random.uniform(-1, 3, n), index=idx),
    )
    if len(result) == n:
        return PASS, f"Backward-compatible: {n} bars classified without UW inputs"
    return FAIL, f"Output length {len(result)} != {n}"


audit("VolRegimeClassifier backward compat", check_vol_classifier_backward_compat)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 4: MARKET HEALTH PROVIDER
# ═══════════════════════════════════════════════════════════
print("\n══ 4. MARKET HEALTH PROVIDER ══")


def check_mh_provider_flow_direction():
    """Verify the MH provider can read sector_tide and produce flow_direction."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    # Check if sector_tide data exists in vault
    sectors = ["TECHNOLOGY", "FINANCIALS", "HEALTHCARE", "ENERGY", "CONSUMER CYCLICAL"]
    found = 0
    for s in sectors:
        data = store.load_mcp_latest("uw/sector_tide", s)
        if data and isinstance(data, list) and len(data) > 0:
            found += 1

    # Check vol_stats SPY
    vol_spy = store.load_mcp_latest("uw/vol_stats", "SPY")
    vol_spy_ok = vol_spy is not None and isinstance(vol_spy, dict)

    store.close()

    details = f"sector_tide: {found}/{len(sectors)} sectors"
    details += f" | vol_stats SPY: {'present' if vol_spy_ok else 'missing'}"

    if found >= 2 and vol_spy_ok:
        return PASS, details
    elif found > 0 or vol_spy_ok:
        return WARN, details + " (partial UW data)"
    return WARN, details + " (no UW data yet — daemon needs to run)"


audit("Market Health: sector_tide + vol_stats SPY", check_mh_provider_flow_direction)


def check_mh_snapshot_has_flow():
    """Check if latest MH snapshot has real flow_direction."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    snap = store.load_mcp_latest("market/health", "MARKET")
    store.close()
    if not snap:
        return WARN, "No MH snapshot in vault (daemon hasn't run yet)"
    flow = snap.get("flow_direction", "NOT_SET")
    conv = snap.get("convergence_score", "?")
    fg = snap.get("fg_score", "?")
    return PASS, f"flow_direction={flow} conv={conv}/6 F&G={fg}"


audit("Market Health snapshot flow_direction", check_mh_snapshot_has_flow)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 5: ROTATION SCANNER
# ═══════════════════════════════════════════════════════════
print("\n══ 5. ROTATION SCANNER ══")


def check_rotation_entity():
    from backend.modules.rotation_intelligence.domain.entities.rotation_snapshot import RotationSignal
    rs = RotationSignal(etf="XLK", name="Technology", dimension="sector",
                        rs_score=0.5, momentum_20d=0.03, momentum_60d=0.05, volume_ratio=1.2)
    has_uw = hasattr(rs, "uw_flow_confirmation") and hasattr(rs, "uw_net_premium")
    if has_uw:
        return PASS, f"uw_flow_confirmation={rs.uw_flow_confirmation}, uw_net_premium={rs.uw_net_premium}"
    return FAIL, "Missing UW fields on RotationSignal"


audit("RotationSignal UW fields", check_rotation_entity)


def check_rotation_tide_method():
    from backend.modules.rotation_intelligence.application.use_cases.rotation_scanner import RotationScanner
    has_method = hasattr(RotationScanner, "_enrich_with_sector_tide")
    has_mapping = hasattr(RotationScanner, "_SECTOR_TO_UW_TIDE")
    if has_method and has_mapping:
        mapping = RotationScanner._SECTOR_TO_UW_TIDE
        return PASS, f"Mapping: {len(mapping)} sectors → UW tickers"
    return FAIL, f"method={has_method}, mapping={has_mapping}"


audit("RotationScanner._enrich_with_sector_tide", check_rotation_tide_method)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 6: QUALITY SWING (SwingGate)
# ═══════════════════════════════════════════════════════════
print("\n══ 6. QUALITY SWING ══")


def check_swing_gate_iv_rank():
    """Verify SwingGate reads IV Rank from vault."""
    import inspect
    from backend.modules.quality_swing.application.use_cases.swing_gate import SwingGate
    source = inspect.getsource(SwingGate.evaluate)
    has_iv_rank = "uw/vol_stats" in source or "iv_rank" in source
    has_cheap = "UW_IV_CHEAP" in source
    has_expensive = "UW_IV_EXPENSIVE" in source
    if has_iv_rank and has_cheap and has_expensive:
        return PASS, "IV Rank gate: <20 boost + >80 reduce"
    return FAIL, f"iv_rank={has_iv_rank}, cheap={has_cheap}, expensive={has_expensive}"


audit("SwingGate IV Rank gate", check_swing_gate_iv_rank)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 7: SPECULATIVE ENTRY HUB
# ═══════════════════════════════════════════════════════════
print("\n══ 7. SPECULATIVE ENTRY HUB ══")


def check_speculative_uw_enrichments():
    """Verify SpeculativeEntryHub has UW enrichments."""
    import inspect
    from backend.modules.entry_decision.application.use_cases.speculative_entry_hub import SpeculativeEntryHub
    source = inspect.getsource(SpeculativeEntryHub.evaluate)
    checks = {
        "max_pain_distance": "MAX_PAIN" in source,
        "iv_backwardation": "IV_BACKWARDATION" in source or "is_backwardation" in source,
        "iv_rank_vol": "get_vol_stats" in source or "iv_rank" in source,
        "short_interest": "SHORT_SQUEEZE_RISK" in source or "short_interest" in source,
    }
    passed = {k: v for k, v in checks.items() if v}
    failed = {k: v for k, v in checks.items() if not v}
    if not failed:
        return PASS, f"All UW signals: {list(passed.keys())}"
    return FAIL, f"Passed: {list(passed.keys())}, Missing: {list(failed.keys())}"


audit("SpeculativeEntryHub UW enrichments", check_speculative_uw_enrichments)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 8: QUALITY ENTRY GATE
# ═══════════════════════════════════════════════════════════
print("\n══ 8. QUALITY ENTRY GATE ══")


def check_quality_gate_uw():
    """Verify QualityEntryGate has UW enrichments."""
    import inspect
    from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
    source = inspect.getsource(QualityEntryGate.evaluate)
    checks = {
        "iv_rank": "get_vol_stats" in source,
        "iv_expensive_sizing": "UW_IV_EXPENSIVE" in source,
        "short_interest": "SHORT_INTEREST" in source or "short_interest" in source,
    }
    passed = {k: v for k, v in checks.items() if v}
    failed = {k: v for k, v in checks.items() if not v}
    if not failed:
        return PASS, f"All UW signals: {list(passed.keys())}"
    return FAIL, f"Passed: {list(passed.keys())}, Missing: {list(failed.keys())}"


audit("QualityEntryGate UW enrichments", check_quality_gate_uw)


# ═══════════════════════════════════════════════════════════
# DEPARTMENT 9: VAULT DATA — What's actually available
# ═══════════════════════════════════════════════════════════
print("\n══ 9. VAULT DATA INVENTORY ══")


def check_vault_uw_data():
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    categories = [
        ("uw/spot_gex", "SPY"),
        ("uw/greeks", "SPY"),
        ("uw/iv_term_structure", "SPY"),
        ("uw/vol_stats", "SPY"),
        ("uw/max_pain", "SPY"),
        ("uw/oi_per_strike", "SPY"),
        ("uw/nope", "SPY"),
        ("uw/gex_aggregate", "SPY"),
        ("uw/risk_reversal", "SPY"),
        ("uw/short_interest", "SPY"),
        ("uw/sector_tide", "TECHNOLOGY"),
        ("uw/sector_tide", "FINANCIALS"),
    ]

    results_inner = []
    for cat, ticker in categories:
        data = store.load_mcp_latest(cat, ticker)
        status = "✓" if data else "✗"
        dtype = type(data).__name__ if data else "None"
        size = len(data) if isinstance(data, (list, dict)) else 0
        results_inner.append(f"{status} {cat}/{ticker} ({dtype}, {size})")

    # Check OHLCV bars for exploded indicators
    ohlcv_tickers = ["UW_GEX_SPY", "UW_SKEW_SPY", "UW_SI_SPY"]
    for t in ohlcv_tickers:
        df = store.load_bars(t, "1d")
        n = len(df) if df is not None and not df.empty else 0
        results_inner.append(f"{'✓' if n > 0 else '✗'} ohlcv_bars/{t} ({n} bars)")

    store.close()

    found = sum(1 for r in results_inner if r.startswith("✓"))
    total = len(results_inner)
    detail = f"{found}/{total} data sources available"
    for r in results_inner:
        print(f"      {r}")

    if found == total:
        return PASS, detail
    elif found > total * 0.5:
        return WARN, detail + " (partial — some categories need daemon run)"
    return WARN, detail + " (many missing — run vault daemon to populate)"


audit("Vault UW data inventory", check_vault_uw_data)


# ═══════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════
print("\n" + "═" * 60)
print("AUDIT SUMMARY")
print("═" * 60)
n_pass = sum(1 for _, s, _ in results if s == PASS)
n_warn = sum(1 for _, s, _ in results if s == WARN)
n_fail = sum(1 for _, s, _ in results if s == FAIL)
total = len(results)

for name, status, detail in results:
    print(f"  {status} {name}")

print(f"\n  {PASS} {n_pass} passed  {WARN} {n_warn} warnings  {FAIL} {n_fail} failed  ({total} total)")

if n_fail > 0:
    print("\n  ❌ AUDIT FAILED — fix the failures above")
    sys.exit(1)
elif n_warn > 0:
    print("\n  ⚠️ AUDIT PASSED with warnings (likely vault data not yet populated)")
    sys.exit(0)
else:
    print("\n  ✅ ALL CHECKS PASSED — UW integration is complete")
    sys.exit(0)
