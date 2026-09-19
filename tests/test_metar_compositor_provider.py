"""
Unit tests for METAR Compositor Vault Provider (Unified Daemon Pipeline)
"""
import pytest
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.daemons.vault_providers.metar_compositor_provider import MetarCompositorProvider


def test_metar_compositor_provider_registration():
    """Verify that MetarCompositorProvider registers under metar category."""
    provider = MetarCompositorProvider()
    assert provider.name == "metar_compositor"
    assert "metar" in provider.categories
    assert "sigmet" in provider.categories
    assert "taf" in provider.categories
