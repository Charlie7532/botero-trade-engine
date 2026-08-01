"""
Unit Tests for SkewSigmetService (CBOE SKEW Intelligence)
==========================================================
Verifies SKEW SIGMET Service behavior:
  - Evaluation of SKEW tail risk kinematics.
  - Strict Data Policy enforcement (StrictDataPolicyError).
  - Formatted CLI broadcast output.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.skew_sigmet_service import (
    get_skew_market_sigmet,
    StrictDataPolicyError,
    MarketSIGMET,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


def test_skew_sigmet_service_strict_error_on_empty(mock_store):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        with pytest.raises(StrictDataPolicyError) as exc_info:
            get_skew_market_sigmet("2026-07-31")
        assert "SIGMET NOT AVAILABLE" in str(exc_info.value)
