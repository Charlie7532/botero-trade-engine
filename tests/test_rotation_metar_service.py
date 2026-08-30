"""
Unit Tests for RotationMetarService (Sector Rotation Intelligence)
====================================================================
Verifies Sector Rotation METAR Service behavior:
  - Evaluation of composite rotation index (XLY/XLP + XLK/XLU Z-scores).
  - Strict Data Policy enforcement (StrictDataPolicyError).
  - RegimeStatePort persistence (key: rotation:entry_decision:MARKET).
  - Formatted CLI broadcast output.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from backend.modules.entry_decision.domain.services.rotation_metar_service import (
    RotationMetarService,
    StrictDataPolicyError,
    MarketMETAR,
    get_rotation_market_metar,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    return port


def test_rotation_metar_service_strict_error_on_empty(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame(columns=["max_date", "date", "ticker", "close"]))
        svc = RotationMetarService(data_store=mock_store, regime_state_port=mock_port)

        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "METAR NOT AVAILABLE" in str(exc_info.value)


def test_rotation_metar_service_evaluation(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=300, freq="D")
    df_xly = pd.DataFrame({"date": dates, "ticker": "XLY", "close": 180.0})
    df_xlp = pd.DataFrame({"date": dates, "ticker": "XLP", "close": 75.0})
    df_xlk = pd.DataFrame({"date": dates, "ticker": "XLK", "close": 210.0})
    df_xlu = pd.DataFrame({"date": dates, "ticker": "XLU", "close": 65.0})
    df = pd.concat([df_xly, df_xlp, df_xlk, df_xlu])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = RotationMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert isinstance(metar, MarketMETAR)
        assert metar.action_code in [
            "MKT_ROTATION_CYCLICAL_EXPANSION",
            "MKT_ROTATION_NEUTRAL_BALANCED",
            "MKT_ROTATION_DEFENSIVE_FLIGHT",
            "MKT_ROTATION_DEFENSIVE_FREEZE",
            "STK_HOLD_STABLE",
            "STK_ACCUMULATE_STRUCTURAL",
            "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION",
            "STK_TRIM_TACTICAL",
            "STK_BLOCK_CRISIS",
        ]
        assert metar.as_of_date == "2026-07-31"
        assert mock_port.commit_transition.called
        committed_keys = [call[0][0] for call in mock_port.commit_transition.call_args_list]
        assert "rotation:entry_decision:MARKET" in committed_keys




def test_rotation_metar_cli_broadcast(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=300, freq="D")
    df_xly = pd.DataFrame({"date": dates, "ticker": "XLY", "close": 180.0})
    df_xlp = pd.DataFrame({"date": dates, "ticker": "XLP", "close": 75.0})
    df_xlk = pd.DataFrame({"date": dates, "ticker": "XLK", "close": 210.0})
    df_xlu = pd.DataFrame({"date": dates, "ticker": "XLU", "close": 65.0})
    df = pd.concat([df_xly, df_xlp, df_xlk, df_xlu])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = RotationMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        broadcast = metar.format_cli_broadcast()
        assert "MARKET METAR — SECTOR ROTATION INTELLIGENCE" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
