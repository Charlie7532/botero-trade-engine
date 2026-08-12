"""
Unit Tests for BSIMetarService (Breadth Shock Index Intelligence)
================================================================
Verifies BSIMetarService:
  - Classification across Gaussian empirical breadth regimes.
  - Strict Data Policy error enforcement on empty/missing Vault data.
  - StateSnapshot persistence to RegimeStatePort (key: bsi:entry_decision:MARKET).
  - CLI broadcast string formatting.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.bsi_metar_service import (
    BSIMetarService,
    StrictDataPolicyError,
    MarketMETAR,
    get_bsi_market_metar,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    return port


def test_bsi_metar_service_strict_error_on_empty(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        svc = BSIMetarService(data_store=mock_store, regime_state_port=mock_port)
        
        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "METAR NOT AVAILABLE" in str(exc_info.value)


def test_bsi_metar_service_expansive(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_s5tw = pd.DataFrame({"date": dates, "ticker": "S5TW", "close": 65.0})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df_s5tw)
        svc = BSIMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert isinstance(metar, MarketMETAR)
        assert metar.action_code in [
            "MKT_BREADTH_EXPANSIVE",
            "MKT_BREADTH_NEUTRAL",
            "MKT_BREADTH_SHOCK_REVERSAL",
            "MKT_BREADTH_WASHED_OUT"
        ]
        assert metar.bsi_value == pytest.approx(65.0, rel=1e-3)
        assert mock_port.commit_transition.called
        assert mock_port.commit_transition.call_args[1]["key"] == "bsi:entry_decision:MARKET"


def test_bsi_metar_service_washed_out(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Low S5TW = 8.0% (BREADTH_WASHED_OUT)
    df_s5tw = pd.DataFrame({"date": dates, "ticker": "S5TW", "close": 8.0})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df_s5tw)
        svc = BSIMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert metar.action_code == "MKT_BREADTH_WASHED_OUT"
        assert metar.is_crisis_override is True
        assert metar.bsi_bin == "BREADTH_WASHED_OUT"


def test_bsi_metar_cli_broadcast(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_s5tw = pd.DataFrame({"date": dates, "ticker": "S5TW", "close": 55.0})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df_s5tw)
        svc = BSIMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        broadcast = metar.format_cli_broadcast()
        assert "MARKET METAR — BREADTH SHOCK INDEX" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
