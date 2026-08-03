"""
Unit Tests for YieldCurveMetarService (Macro Yield Curve Spread Intelligence)
================================================================================
Verifica el comportamiento del Yield Curve METAR Service:
  - Clasificación en los regímenes empíricos de la curva de rendimiento.
  - Tolerancia y política estricta ante falta de datos (StrictDataPolicyError).
  - Persistencia de StateSnapshot vía RegimeStatePort (clave: yield_curve:entry_decision:MARKET).
  - Formateo de difusión CLI / Broadcast.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.yield_curve_metar_service import (
    YieldCurveMetarService,
    StrictDataPolicyError,
    MarketMETAR,
    get_yield_curve_market_metar,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    return port


def test_yield_curve_metar_service_strict_error_on_empty(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        svc = YieldCurveMetarService(data_store=mock_store, regime_state_port=mock_port)
        
        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "METAR NOT AVAILABLE" in str(exc_info.value)


def test_yield_curve_metar_service_normal_steep(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 4.2})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 3.5})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert isinstance(metar, MarketMETAR)
        assert metar.action_code in [
            "MKT_YIELD_CURVE_NORMAL_STEEP",
            "MKT_YIELD_CURVE_FLAT_WARNING",
            "MKT_YIELD_CURVE_INVERTED_CRISIS",
            "MKT_YIELD_CURVE_UNINVERSION_STEEPENING",
        ]
        assert metar.spread_value == pytest.approx(4.2 - 3.5, rel=1e-3)
        assert mock_port.commit_transition.called
        assert mock_port.commit_transition.call_args[1]["key"] == "yield_curve:entry_decision:MARKET"


def test_yield_curve_metar_service_deep_inversion(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Low spread TNX - IRX = 3.0 - 5.0 = -2.0 (Deep Inversion)
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 3.0})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 5.0})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert metar.action_code == "MKT_YIELD_CURVE_INVERTED_CRISIS"
        assert metar.is_crisis_override is True
        assert metar.yield_bin == "DEEP_INVERSION"


def test_yield_curve_metar_service_uninversion_steepening(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Rapid steepening uninversion (large positive spread > P95)
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 6.0})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 2.0})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert metar.action_code == "MKT_YIELD_CURVE_UNINVERSION_STEEPENING"
        assert metar.is_crisis_override is True
        assert metar.yield_bin == "EXTREME_STEEPENING_UNINVERSION"


def test_yield_curve_metar_cli_broadcast(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_tnx = pd.DataFrame({"date": dates, "ticker": "TNX", "close": 4.5})
    df_irx = pd.DataFrame({"date": dates, "ticker": "IRX", "close": 3.8})
    df = pd.concat([df_tnx, df_irx])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = YieldCurveMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        broadcast = metar.format_cli_broadcast()
        assert "MARKET METAR — YIELD CURVE SPREAD" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
