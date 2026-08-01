"""
Unit Tests for YieldCurveSigmetService (Macro Yield Curve Spread Intelligence)
================================================================================
Verifica el comportamiento del Yield Curve SIGMET Service:
  - Clasificación en los regímenes empíricos de la curva de rendimiento.
  - Tolerancia y política estricta ante falta de datos (StrictDataPolicyError).
  - Persistencia de StateSnapshot vía RegimeStatePort (clave: yield_curve:entry_decision:MARKET).
  - Formateo de difusión CLI / Broadcast.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.yield_curve_sigmet_service import (
    YieldCurveSigmetService,
    StrictDataPolicyError,
    MarketSIGMET,
    get_yield_curve_market_sigmet,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    return port


def test_yield_curve_sigmet_service_strict_error_on_empty(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        svc = YieldCurveSigmetService(data_store=mock_store, regime_state_port=mock_port)
        
        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "SIGMET NOT AVAILABLE" in str(exc_info.value)


def test_yield_curve_sigmet_service_normal_steep(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 4.2})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 3.5})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        assert isinstance(sigmet, MarketSIGMET)
        assert sigmet.action_code in [
            "MKT_YIELD_CURVE_NORMAL_STEEP",
            "MKT_YIELD_CURVE_FLAT_WARNING",
            "MKT_YIELD_CURVE_INVERTED_CRISIS",
            "MKT_YIELD_CURVE_UNINVERSION_STEEPENING",
        ]
        assert sigmet.spread_value == pytest.approx(4.2 - 3.5, rel=1e-3)
        assert mock_port.commit_transition.called
        assert mock_port.commit_transition.call_args[1]["key"] == "yield_curve:entry_decision:MARKET"


def test_yield_curve_sigmet_service_deep_inversion(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Low spread TNX - IRX = 3.0 - 5.0 = -2.0 (Deep Inversion)
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 3.0})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 5.0})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        assert sigmet.action_code == "MKT_YIELD_CURVE_INVERTED_CRISIS"
        assert sigmet.is_crisis_override is True
        assert sigmet.yield_bin == "DEEP_INVERSION"


def test_yield_curve_sigmet_service_uninversion_steepening(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Rapid steepening uninversion (large positive spread > P95)
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 6.0})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 2.0})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        assert sigmet.action_code == "MKT_YIELD_CURVE_UNINVERSION_STEEPENING"
        assert sigmet.is_crisis_override is True
        assert sigmet.yield_bin == "EXTREME_STEEPENING_UNINVERSION"


def test_yield_curve_sigmet_cli_broadcast(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 4.5})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 3.8})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveSigmetService(data_store=mock_store, regime_state_port=mock_port)
        sigmet = svc.evaluate("2026-07-31")

        broadcast = sigmet.format_cli_broadcast()
        assert "MARKET SIGMET — YIELD CURVE SPREAD" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
