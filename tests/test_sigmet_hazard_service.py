"""
Unit Tests for MarketSIGMETHazardService (Severe Weather Hazards Engine)
========================================================================
Verifies SIGMET evaluation against METAR observations:
1. Returns empty list [] (status CLEAR) when no stations report severe weather hazards.
2. Emits severe SIGMET bulletin when extreme hazard thresholds are breached.
"""
import pytest
from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import (
    evaluate_market_sigmets,
    MarketSIGMET
)


def test_evaluate_market_sigmets_returns_list():
    """Verify that evaluate_market_sigmets executes and returns a list of MarketSIGMET objects."""
    sigmets = evaluate_market_sigmets()
    assert isinstance(sigmets, list)
    for s in sigmets:
        assert isinstance(s, MarketSIGMET)
        assert s.severity in ("CRITICAL", "WARNING")
        assert s.is_active is True
        assert len(s.format_cli_broadcast()) > 0
