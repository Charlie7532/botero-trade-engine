import pytest
from backend.modules.portfolio_management.domain.rules.expectations_engine import ExpectationsEngine

def test_calculate_implied_growth():
    # If the company generates $10 FCF/share, with 10% WACC and 2% terminal growth,
    # what growth is required to justify a $200 price?
    implied_g = ExpectationsEngine.calculate_implied_growth(
        current_price=200.0,
        ttm_fcf_per_share=10.0,
        wacc=0.10,
        terminal_growth_rate=0.02,
        years=10
    )
    # The implied growth should be positive. Let's just assert it runs and returns a float.
    assert isinstance(implied_g, float)
    assert implied_g > 0.0

def test_assess_expectations_priced_for_perfection():
    # Historical is 5%, but implied is 20%. Market expects way more than history.
    result = ExpectationsEngine.assess_expectations(
        ticker="TEST",
        current_price=200.0,
        implied_growth=0.20,
        historical_growth=0.05
    )
    assert result.assessment == "PRICED_FOR_PERFECTION"
    assert result.growth_gap == pytest.approx(-0.15)

def test_assess_expectations_priced_for_failure():
    # Historical is 15%, but implied is -5%. Market expects it to die.
    result = ExpectationsEngine.assess_expectations(
        ticker="TEST",
        current_price=20.0,
        implied_growth=-0.05,
        historical_growth=0.15
    )
    assert result.assessment == "PRICED_FOR_FAILURE"

def test_assess_expectations_fairly_priced():
    # Historical is 10%, implied is 11%.
    result = ExpectationsEngine.assess_expectations(
        ticker="TEST",
        current_price=100.0,
        implied_growth=0.11,
        historical_growth=0.10
    )
    assert result.assessment == "FAIRLY_PRICED"
