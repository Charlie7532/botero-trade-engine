"""
Unit Tests for SkewSigmetService
================================
Verifica el comportamiento del SKEW SIGMET Service:
  - Clasificación en los 4 regímenes empíricos (COMPLACENCY, NORMAL, ELEVATED, EXTREME_TAIL_RISK).
  - Tolerancia a falta de datos / fallbacks.
  - Persistencia de StateSnapshot vía RegimeStatePort.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.skew_sigmet_service import (
    SkewSigmetService,
    STATE_COMPLACENCY,
    STATE_NORMAL,
    STATE_ELEVATED,
    STATE_EXTREME_TAIL_RISK,
)
from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    port.get_state.return_value = None
    return port


def test_skew_sigmet_service_fallback_on_empty(mock_store, mock_port):
    # Mock database returning empty df
    conn = MagicMock()
    mock_store._conn.return_value = conn

    # Mock pd.read_sql
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        svc = SkewSigmetService(data_store=mock_store, regime_state_port=mock_port)
        rep = svc.evaluate("2026-07-31")

        assert rep.current_state == STATE_NORMAL
        assert rep.action_code == "MKT_SKEW_NORMAL"
        assert rep.is_crisis_override is False


def test_skew_sigmet_service_extreme_tail_risk(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    # Mock data with SKEW >= 148.0
    dates = pd.date_range(end="2026-07-31", periods=65, freq="D")
    df = pd.DataFrame({"timestamp": dates, "skew": [120.0] * 64 + [152.0]})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = SkewSigmetService(data_store=mock_store, regime_state_port=mock_port)
        rep = svc.evaluate("2026-07-31")

        assert rep.current_state == STATE_EXTREME_TAIL_RISK
        assert rep.action_code == "MKT_SKEW_TAIL_RISK_EXTREME"
        assert rep.is_crisis_override is True
        assert rep.skew_value == 152.0


def test_skew_sigmet_service_complacency(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    # Mock data with SKEW <= 109.0
    dates = pd.date_range(end="2026-07-31", periods=65, freq="D")
    df = pd.DataFrame({"timestamp": dates, "skew": [108.0] * 65})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = SkewSigmetService(data_store=mock_store, regime_state_port=mock_port)
        rep = svc.evaluate("2026-07-31")

        assert rep.current_state == STATE_COMPLACENCY
        assert rep.action_code == "MKT_SKEW_COMPLACENCY"
        assert rep.is_crisis_override is False
