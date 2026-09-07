"""
Test Suite: Verificación de Integridad de los 11 Timing Fact Stores (Chronos Engine)
=====================================================================================
Valida la consistencia estructural, matemática, cumplimiento de la Regla 21 y la
ausencia total de juicios cualitativos en los 11 Timing Fact Stores generados.
"""

import json
import pytest
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[1] / "backend" / "modules" / "entry_decision" / "domain" / "rules"

STATIONS = [
    "vix",
    "vvix",
    "pcr",
    "fg",
    "sv5_turbulence",
    "skew",
    "credit",
    "yield_curve",
    "rotation",
    "bsi",
    "dxy",
]

SLOT_KEYS = ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]
SCALES = ["zz25", "zz50", "zz75"]

FORBIDDEN_JUDGMENT_KEYS = {
    "identidad_funcional",
    "calificacion_operativa",
    "sesgo_dominante",
    "diagnostico_giro",
    "d1_label",
    "d2_label",
    "d3_label",
}


@pytest.mark.parametrize("station", STATIONS)
def test_timing_fact_store_exists_and_loads(station):
    """Verifica que el archivo JSON de cada estación exista y sea un JSON válido."""
    path = RULES_DIR / f"{station}_timing_fact_store.json"
    assert path.exists(), f"Falta el archivo: {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert data.get("station") == station.upper()


@pytest.mark.parametrize("station", STATIONS)
def test_documentation_rule_21_compliance(station):
    """Verifica que el bloque _documentation cumpla con todos los requisitos de la Regla 21."""
    path = RULES_DIR / f"{station}_timing_fact_store.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    doc = data.get("_documentation")
    assert doc is not None, "Falta el bloque _documentation"

    # Bloques obligatorios
    assert "model_purpose" in doc, "Falta model_purpose"
    assert "data_sources" in doc, "Falta data_sources"
    assert "return_formula" in doc, "Falta return_formula"
    assert "state_hierarchy" in doc, "Falta state_hierarchy"
    assert "taxonomy" in doc, "Falta taxonomy"
    assert "dimension_thresholds_definition" in doc, "Falta dimension_thresholds_definition"
    assert "zigzag_scale_classification" in doc, "Falta zigzag_scale_classification"
    assert "field_glossary" in doc, "Falta field_glossary"
    assert "signal_interpretation_policy" in doc, "Falta signal_interpretation_policy"


@pytest.mark.parametrize("station", STATIONS)
def test_state_counts_match_v1_registered(station):
    """Verifica que el número de estados coincida exactamente con los registrados en el fact store V1."""
    timing_path = RULES_DIR / f"{station}_timing_fact_store.json"
    v1_path = RULES_DIR / f"{station}_fact_store.json"

    with open(timing_path, "r", encoding="utf-8") as f:
        t_data = json.load(f)
    with open(v1_path, "r", encoding="utf-8") as f:
        v1_data = json.load(f)

    v1_states = set(v1_data.get("states", {}).keys())
    timing_states = set(t_data.get("states", {}).keys())

    assert timing_states == v1_states, (
        f"Divergencia de estados en {station}: "
        f"Faltan en timing: {v1_states - timing_states}, "
        f"Extras en timing: {timing_states - v1_states}"
    )


@pytest.mark.parametrize("station", STATIONS)
def test_zero_judgment_compliance(station):
    """Verifica que NINGÚN estado contenga campos adjetivales o de juicio cualitativo."""
    timing_path = RULES_DIR / f"{station}_timing_fact_store.json"
    with open(timing_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for sk, sdata in data.get("states", {}).items():
        if not isinstance(sdata, dict):
            continue
        found_forbidden = set(sdata.keys()) & FORBIDDEN_JUDGMENT_KEYS
        assert not found_forbidden, (
            f"Violación de 'Cero Juicio' en {station} estado {sk}: claves prohibidas encontradas: {found_forbidden}"
        )


@pytest.mark.parametrize("station", STATIONS)
def test_mathematical_consistency_populated_states(station):
    """Valida la consistencia aritmética de timing slots, episodios y baselines."""
    timing_path = RULES_DIR / f"{station}_timing_fact_store.json"
    with open(timing_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for sk, sdata in data.get("states", {}).items():
        pob = sdata.get("poblacion", {})
        n_ep = pob.get("n_episodios", 0)
        if n_ep == 0:
            continue

        # Overflows
        ovf = sdata.get("overflows", {})
        assert "n_episodios_tier_gte_1" in ovf
        assert "pct_episodios_overflow" in ovf
        assert 0 <= ovf["pct_episodios_overflow"] <= 100.0

        for blanco in ["medicion_min", "medicion_max"]:
            med = sdata.get(blanco)
            assert med is not None, f"Falta {blanco} en {station} {sk}"

            # Resumen rango
            rng = med.get("resumen_rango", {})
            slots = med.get("slots_zz25", {})

            # Suma de episodios en slots == n_episodios
            slot_n_sum = sum(slots[s]["n"] for s in SLOT_KEYS)
            assert slot_n_sum == n_ep, f"Suma de slots {slot_n_sum} != n_episodios {n_ep} en {station} {sk} {blanco}"

            # Consistencia de n_en_rango
            assert rng["n_en_rango"] + slots["ENTRE"]["n"] == n_ep

            # Suma de porcentajes ~ 100%
            pct_sum = sum(slots[s]["pct"] for s in SLOT_KEYS)
            assert 99.0 <= pct_sum <= 101.0, f"Suma de pcts {pct_sum} fuera de 100% en {station} {sk} {blanco}"

            # First passage
            fp = med.get("first_passage", {})
            for sc in SCALES:
                if sc in fp:
                    entry = fp[sc]
                    assert "hit_rate" in entry
                    assert "baseline_hit" in entry
                    assert "ev" in entry
                    assert "profit_factor" in entry
                    assert "bars_medio" in entry
                    # Verificación de signo de MAE según dirección
                    # After excluding entry bar from MAE, small positive values
                    # are possible when the trade resolved in 1-2 bars (N small).
                    # Only check with sufficient sample.
                    if n_ep >= 10:
                        if blanco == "medicion_min":
                            assert entry["mae_medio"] <= 0.005, f"MAE medio MIN debería ser <= ~0 en {station} {sk} {sc} (N={n_ep})"
                        else:
                            assert entry["mae_medio"] >= -0.005, f"MAE medio MAX debería ser >= ~0 en {station} {sk} {sc} (N={n_ep})"
