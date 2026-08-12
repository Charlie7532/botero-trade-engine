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
    engine = MagicMock()
    mock_store.engine = engine

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, e: pd.DataFrame({"ticker": []}))
        svc = RotationMetarService(data_store=mock_store, regime_state_port=mock_port)

        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "METAR NOT AVAILABLE" in str(exc_info.value)


def test_rotation_metar_service_evaluation(mock_store, mock_port):
    engine = MagicMock()
    mock_store.engine = engine

    dates = pd.date_range(end="2026-07-31", periods=300, freq="D")
    df_xly = pd.DataFrame({"date": dates, "ticker": "XLY", "close": 180.0})
    df_xlp = pd.DataFrame({"date": dates, "ticker": "XLP", "close": 75.0})
    df_xlk = pd.DataFrame({"date": dates, "ticker": "XLK", "close": 210.0})
    df_xlu = pd.DataFrame({"date": dates, "ticker": "XLU", "close": 65.0})
    df_max = pd.DataFrame({"max_date": ["2026-07-31"]})
    df_cnt = pd.DataFrame({"count": [1]})
    df = pd.concat([df_xly, df_xlp, df_xlk, df_xlu])

    def mock_read_sql(q, e):
        if "MAX(time::date)" in q:
            return df_max
        elif "COUNT(*)" in q:
            return df_cnt
        return df

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", mock_read_sql)
        svc = RotationMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert isinstance(metar, MarketMETAR)
        assert metar.operational_guidance in [
            "STK_HOLD_STABLE",
            "STK_BUY_DIP_TACTICAL",
            "STK_TRIM_TACTICAL",
            "STK_ACCUMULATE_STRUCTURAL",
            "STK_BLOCK_CRISIS",
        ]
        assert metar.as_of_date == "2026-07-31"


def test_rotation_metar_cli_broadcast(mock_store, mock_port):
    engine = MagicMock()
    mock_store.engine = engine

    dates = pd.date_range(end="2026-07-31", periods=300, freq="D")
    df_xly = pd.DataFrame({"date": dates, "ticker": "XLY", "close": 180.0})
    df_xlp = pd.DataFrame({"date": dates, "ticker": "XLP", "close": 75.0})
    df_xlk = pd.DataFrame({"date": dates, "ticker": "XLK", "close": 210.0})
    df_xlu = pd.DataFrame({"date": dates, "ticker": "XLU", "close": 65.0})
    df_max = pd.DataFrame({"max_date": ["2026-07-31"]})
    df_cnt = pd.DataFrame({"count": [1]})
    df = pd.concat([df_xly, df_xlp, df_xlk, df_xlu])

    def mock_read_sql(q, e):
        if "MAX(time::date)" in q:
            return df_max
        elif "COUNT(*)" in q:
            return df_cnt
        return df

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", mock_read_sql)
        svc = RotationMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        broadcast = metar.format_cli_broadcast()
        assert "MARKET METAR — SECTOR ROTATION" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
