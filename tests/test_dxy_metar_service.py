import pytest
from backend.modules.entry_decision.domain.services.dxy_metar_service import get_dxy_market_metar, MarketMETAR
from backend.modules.entry_decision.domain.rules.dxy_lookup import dxy_lookup


def test_dxy_lookup_quantiles():
    # Test D1 deep crush
    g = dxy_lookup.lookup_dxy_guidance(val=75.0, d3_speed=-2.0)
    assert g is not None
    assert g.dxy_bin == "DEEP_DOLLAR_CRUSH"
    assert g.velocity_vector == "FAST_CRUSH_3D"

    # Test D1 spike crisis
    g2 = dxy_lookup.lookup_dxy_guidance(val=140.0, d3_speed=2.5)
    assert g2 is not None
    assert g2.dxy_bin == "DOLLAR_SPIKE_CRISIS"
    assert g2.velocity_vector == "FAST_SPIKE_3D"
    assert g2.operational_guidance == "STK_BLOCK_CRISIS"


def test_dxy_metar_service_live():
    metar = get_dxy_market_metar()
    assert isinstance(metar, MarketMETAR)
    assert metar.metar_id.startswith("METAR-DXY-")
    assert metar.dxy_index_value > 0
    assert metar.n_samples > 0
    assert metar.primary_p_bull >= 0.0
