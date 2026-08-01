"""
Unit Tests for CreditSigmetService (Credit Stress Intelligence)
================================================================
Verifica el comportamiento del Credit SIGMET Service:
  - Clasificación en los regímenes empíricos de crédito.
  - Tolerancia y política estricta ante falta de datos (StrictDataPolicyError).
  - Persistencia de StateSnapshot vía RegimeStatePort (clave: credit:entry_decision:MARKET).
  - Formateo de difusión CLI / Broadcast.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.credit_sigmet_service import (
    CreditSigmetService,
    StrictDataPolicyError,
    MarketSIGMET,
    get_credit_market_sigmet,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    return port


def test_credit_sigmet_service_strict_error_on_empty(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        svc = CreditSigmetService(data_store=mock_store, regime_state_port=mock_port)
        
        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "SIGMET NOT AVAILABLE" in str(exc_info.value)


def test_credit_sigmet_service_expansion(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_hyg = pd.DataFrame({"date": dates, "ticker": "HYG", "close": 78.0})
    df_tlt = pd.DataFrame({"date": dates, "ticker": "TLT", "close": 90.0})
    df = pd.concat([df_hyg, df_tlt])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = CreditSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        assert isinstance(sigmet, MarketSIGMET)
        assert sigmet.action_code in [
            "MKT_CREDIT_EXPANSION_STABLE",
            "MKT_CREDIT_STRESS_ELEVATED",
            "MKT_CREDIT_FREEZE_EXTREME",
        ]
        assert sigmet.credit_ratio_value == pytest.approx(78.0 / 90.0, rel=1e-3)
        assert mock_port.commit_transition.called
        assert mock_port.commit_transition.call_args[1]["key"] == "credit:entry_decision:MARKET"


def test_credit_sigmet_service_freeze(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Low ratio HYG/TLT = 30.0 / 100.0 = 0.30 (Extreme freeze)
    df_hyg = pd.DataFrame({"date": dates, "ticker": "HYG", "close": 30.0})
    df_tlt = pd.DataFrame({"date": dates, "ticker": "TLT", "close": 100.0})
    df = pd.concat([df_hyg, df_tlt])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = CreditSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        assert sigmet.action_code == "MKT_CREDIT_FREEZE_EXTREME"
        assert sigmet.is_crisis_override is True
        assert sigmet.credit_bin == "EXTREME_CREDIT_FREEZE"


def test_credit_sigmet_cli_broadcast(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_hyg = pd.DataFrame({"date": dates, "ticker": "HYG", "close": 70.0})
    df_tlt = pd.DataFrame({"date": dates, "ticker": "TLT", "close": 100.0})
    df = pd.concat([df_hyg, df_tlt])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = CreditSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        broadcast = sigmet.format_cli_broadcast()
        assert "MARKET SIGMET — CREDIT STRESS RATIO" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
