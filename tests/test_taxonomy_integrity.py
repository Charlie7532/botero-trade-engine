"""
Test de Integridad Taxonómica — Guardrail Anti-Hallucination
=============================================================
Verifica que CUALQUIER archivo que use D1 labels, D2 labels, o state_keys
sea consistente con la fuente canónica: los generadores de producción.

Este test existe porque un agente AI inventó labels D1 para 9 de 11 estaciones
en build_continuous_metar_lake.py (29-Ago-2026), incluyendo una inversión
física del Credit que etiquetaba la GFC 2008 como "EXTREME_EASE".

Fuentes canónicas:
  - D1: backend/scripts/generators/generate_{station}_fact_table.py
  - D2: Universal labels (FAST_CRUSH_3D ... FAST_SPIKE_3D)
  - D3: Universal labels (VOL_EXTREME_SQUEEZE ... VOL_PEAK_DECELERATION)
  - Referencia: .agents/references/fact_store_v3_architecture.md §4.2
"""
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ══════════════════════════════════════════════════════════════
# CANONICAL D1 LABELS — extracted from production generators
# These are the ONLY acceptable D1 labels for each station.
# If a generator changes, this dict MUST be updated in parallel.
# ══════════════════════════════════════════════════════════════
CANONICAL_D1_LABELS = {
    "vix": ["EXTREME_COMPLACENCY", "COMPLACENCY", "NEUTRAL_CALM", "NEUTRAL_ALERT", "PANIC", "EXTREME_PANIC"],
    "vvix": ["EXTREME_STABILITY", "STABILITY", "NEUTRAL_STABLE", "NEUTRAL_UNSTABLE", "INSTABILITY", "EXTREME_INSTABILITY"],
    "pcr": ["EXTREME_CALL_EUPHORIA", "CALL_EUPHORIA", "NEUTRAL_CALL_BIAS", "NEUTRAL_PUT_BIAS", "PUT_PANIC", "EXTREME_PUT_PANIC"],
    "fg": ["EXTREME_FEAR", "FEAR", "NEUTRAL_FEAR", "NEUTRAL_GREED", "GREED", "EXTREME_GREED"],
    "sv5_turbulence": ["EXTREME_CALM", "CALM", "NEUTRAL_CALM", "NEUTRAL_TURBULENT", "TURBULENT", "EXTREME_TURBULENT"],
    "skew": ["EXTREME_CONFIDENCE", "CONFIDENCE", "NEUTRAL_CONFIDENT", "NEUTRAL_PARANOID", "PARANOIA", "EXTREME_PARANOIA"],
    "credit": ["EXTREME_STRESS", "STRESS", "NEUTRAL_TIGHT", "NEUTRAL_LOOSE", "EASE", "EXTREME_EASE"],
    "yield_curve": ["DEEP_INVERSION", "MODERATE_INVERSION", "FLAT_CURVE", "NORMAL_CURVE", "STEEPNING_CURVE", "EXTREME_STEEPNING"],
    "rotation": ["EXTREME_DEFENSIVE", "DEFENSIVE", "NEUTRAL_DEFENSIVE", "NEUTRAL_OFFENSIVE", "OFFENSIVE", "EXTREME_OFFENSIVE"],
    "dxy": ["EXTREME_WEAKNESS", "WEAKNESS", "NEUTRAL_WEAK", "NEUTRAL_STRONG", "STRENGTH", "EXTREME_STRENGTH"],
    "bsi": ["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH", "NEUTRAL_HIGH_BREADTH", "EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"],
}

CANONICAL_D2_LABELS = [
    "FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D",
    "ACCELERATING_UP_3D", "FAST_SPIKE_3D",
]

CANONICAL_D3_LABELS = [
    "VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE",
    "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION",
]


class TestCanonicalLabelsMatchGenerators:
    """Verify that CANONICAL_D1_LABELS in this test match the production generators."""

    GENERATOR_DIR = ROOT / "backend" / "scripts" / "generators"

    # Map station names to generator file patterns
    STATION_TO_GENERATOR = {
        "vix": "generate_vix_fact_table.py",
        "vvix": "generate_vvix_fact_table.py",
        "pcr": "generate_pcr_fact_table.py",
        "fg": "generate_fg_fact_table.py",
        "sv5_turbulence": "generate_sv5_turbulence_fact_table.py",
        "skew": "generate_skew_fact_table.py",
        "credit": "generate_credit_fact_table.py",
        "yield_curve": "generate_yield_curve_fact_table.py",
        "rotation": "generate_rotation_fact_table.py",
        "bsi": "generate_bsi_fact_table.py",
    }

    @pytest.mark.parametrize("station", list(STATION_TO_GENERATOR.keys()))
    def test_d1_labels_match_generator(self, station):
        """Each station's canonical D1 labels must match the generator source."""
        gen_file = self.GENERATOR_DIR / self.STATION_TO_GENERATOR[station]
        if not gen_file.exists():
            pytest.skip(f"Generator {gen_file.name} not found")

        content = gen_file.read_text()
        # Extract D1_LABELS list from generator source
        import re
        match = re.search(r'D1_LABELS\s*=\s*\[([^\]]+)\]', content)
        if not match:
            match = re.search(r'D1_BINS\s*=\s*\[([^\]]+)\]', content)
        assert match, f"Could not find D1_LABELS or D1_BINS in {gen_file.name}"

        raw = match.group(1)
        gen_labels = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]

        canonical = CANONICAL_D1_LABELS[station]
        assert gen_labels == canonical, (
            f"D1 labels mismatch for {station}!\n"
            f"  Generator ({gen_file.name}): {gen_labels}\n"
            f"  Canonical (this test):       {canonical}"
        )


class TestFactStoreStateKeysUseCanonicalLabels:
    """Verify that every state_key in production fact stores uses canonical labels."""

    FACT_STORE_DIR = ROOT / "backend" / "modules" / "entry_decision" / "domain" / "rules"

    @pytest.mark.parametrize("station", list(CANONICAL_D1_LABELS.keys()))
    def test_fact_store_d1_labels(self, station):
        """All D1 components of state_keys in fact stores must be canonical."""
        fs_path = self.FACT_STORE_DIR / f"{station}_fact_store.json"
        if not fs_path.exists():
            pytest.skip(f"Fact store {fs_path.name} not found")

        with open(fs_path) as f:
            fs = json.load(f)

        canonical_d1 = set(CANONICAL_D1_LABELS[station])
        canonical_d2 = set(CANONICAL_D2_LABELS)
        canonical_d3 = set(CANONICAL_D3_LABELS)

        for state_key in fs.get("states", {}).keys():
            parts = state_key.split("__")
            assert len(parts) == 3, f"Malformed state_key: {state_key}"
            d1_str, d2_str, d3_str = parts

            # State keys are now numeric bin indices
            d1 = int(d1_str)
            d2 = int(d2_str)
            d3 = int(d3_str)

            assert 0 <= d1 <= 5, (
                f"D1 bin index {d1} out of range [0,5] in {station}_fact_store.json key '{state_key}'"
            )
            assert 0 <= d2 <= 4, (
                f"D2 bin index {d2} out of range [0,4] in {station}_fact_store.json key '{state_key}'"
            )
            assert 0 <= d3 <= 4, (
                f"D3 bin index {d3} out of range [0,4] in {station}_fact_store.json key '{state_key}'"
            )


class TestLakeBuilderUsesCanonicalLabels:
    """Verify that build_continuous_metar_lake.py uses canonical labels."""

    LAKE_BUILDER = ROOT / "research" / "01_señales_entry_exit" / "build_continuous_metar_lake.py"

    def test_lake_builder_exists(self):
        assert self.LAKE_BUILDER.exists(), "Lake builder script not found"

    @pytest.mark.parametrize("station", list(CANONICAL_D1_LABELS.keys()))
    def test_lake_d1_labels_match_canonical(self, station):
        """Lake builder's STATION_D1_LABELS must match canonical labels exactly."""
        import re
        content = self.LAKE_BUILDER.read_text()

        # Find the line for this station in STATION_D1_LABELS
        pattern = rf'"{station}"\s*:\s*\[([^\]]+)\]'
        match = re.search(pattern, content)
        assert match, f"Could not find D1 labels for '{station}' in lake builder"

        raw = match.group(1)
        lake_labels = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]

        canonical = CANONICAL_D1_LABELS[station]
        assert lake_labels == canonical, (
            f"Lake builder D1 labels for {station} don't match canonical!\n"
            f"  Lake builder: {lake_labels}\n"
            f"  Canonical:    {canonical}\n"
            f"  This is the EXACT error that caused Credit physical inversion on 29-Aug-2026."
        )


class TestCreditPhysicalDirection:
    """Guard against the Credit inversion bug (29-Aug-2026).

    CREDIT_RATIO = HYG/LQD. Low ratio = stress. High ratio = ease.
    Bin 0 (lowest expanding rank) MUST map to EXTREME_STRESS, not EXTREME_EASE.
    """

    def test_credit_bin_0_is_crisis(self):
        """The first (lowest) D1 label for credit must be a stress label."""
        assert CANONICAL_D1_LABELS["credit"][0] == "EXTREME_STRESS", (
            "Credit Bin 0 must be EXTREME_STRESS (lowest HYG/LQD = stress). "
            "If this fails, Credit D1 labels are physically inverted."
        )

    def test_credit_bin_5_is_ease(self):
        """The last (highest) D1 label for credit must be an ease label."""
        assert CANONICAL_D1_LABELS["credit"][5] == "EXTREME_EASE", (
            "Credit Bin 5 must be EXTREME_EASE (highest HYG/LQD = ease). "
            "If this fails, Credit D1 labels are physically inverted."
        )


class TestAllStationsHave6D1Labels:
    """Every station must have exactly 6 D1 labels (Gaussian §24: 6 bins, 5 edges)."""

    @pytest.mark.parametrize("station", list(CANONICAL_D1_LABELS.keys()))
    def test_6_labels(self, station):
        assert len(CANONICAL_D1_LABELS[station]) == 6, (
            f"{station} has {len(CANONICAL_D1_LABELS[station])} D1 labels, expected 6 "
            f"(Rule 24: 6 bins from 5 Gaussian edges)"
        )
