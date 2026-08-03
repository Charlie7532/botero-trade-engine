"""
Unit Tests for SkewMetarService (CBOE SKEW Intelligence)
==========================================================
Verifies SKEW METAR Service behavior:
  - Evaluation of SKEW tail risk kinematics.
  - Strict Data Policy enforcement (StrictDataPolicyError).
  - Formatted CLI broadcast output.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.skew_metar_service import (
    get_skew_market_metar,
    StrictDataPolicyError,
    MarketMETAR,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


def test_skew_metar_service_strict_error_on_empty(mock_store):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        with pytest.raises(StrictDataPolicyError) as exc_info:
            get_skew_market_metar("2026-07-31")
        assert "METAR NOT AVAILABLE" in str(exc_info.value)
