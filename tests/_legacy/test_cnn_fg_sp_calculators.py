"""
Unit tests for CNN Fear & Greed SPIndex domain calculators.
Tests cnn_fg_breadth_calculator and cnn_fg_composite_calculator.
"""
import pytest
from backend.modules.shared.domain.rules.cnn_fg_breadth_calculator import (
    calculate_highs_lows_ratio,
    calculate_mcclellan_vsi,
)
from backend.modules.shared.domain.rules.cnn_fg_composite_calculator import (
    calculate_momentum,
    calculate_putcall,
    calculate_vix,
    calculate_junkbond,
    calculate_safehaven,
    percentile_score,
    calculate_composite,
)


def test_calculate_highs_lows_ratio():
    # Mock closes for 100 stocks across 252 days
    all_closes = {}
    for i in range(100):
        # Stock 0-9 hit 52wk high (current = max)
        if i < 10:
            closes = [100.0] * 251 + [105.0]
        # Stock 10-14 hit 52wk low (current = min)
        elif i < 15:
            closes = [100.0] * 251 + [90.0]
        else:
            # Fluctuating stock (min 95, max 105, current 100)
            closes = [95.0, 105.0] + [100.0] * 250
        all_closes[f"STOCK_{i}"] = closes

    ratio = calculate_highs_lows_ratio(all_closes, lookback=252)
    assert ratio is not None
    # 10 highs / 5 lows = 2.0
    assert ratio == 2.0


def test_calculate_mcclellan_vsi():
    all_closes = {}
    all_volumes = {}
    for i in range(60):
        # 60 days of data
        closes = [100.0 + (j if i < 30 else -j) for j in range(60)]
        volumes = [1000.0] * 60
        all_closes[f"STK_{i}"] = closes
        all_volumes[f"STK_{i}"] = volumes

    mvsi = calculate_mcclellan_vsi(all_closes, all_volumes)
    assert mvsi is not None
    assert isinstance(mvsi, float)


def test_calculate_momentum():
    spy_closes = [100.0] * 125
    spy_closes[-1] = 110.0  # 10% above MA
    # MA is (124*100 + 110)/125 = 100.08
    momentum = calculate_momentum(spy_closes, ma_period=125)
    assert momentum is not None
    assert momentum > 0


def test_calculate_junkbond_and_safehaven():
    hyg = [90.0, 91.0]
    lqd = [100.0, 100.0]
    jb = calculate_junkbond(hyg, lqd)
    assert jb == round(91.0 / 100.0, 4)

    spy = [500.0] * 21
    spy[-1] = 550.0  # +10%
    tlt = [100.0] * 21
    tlt[-1] = 102.0  # +2%
    sh = calculate_safehaven(spy, tlt, period=20)
    assert sh is not None
    assert sh == 8.0  # 10% - 2% = 8pp


def test_percentile_score_and_composite():
    history = list(range(1, 101))  # 1 to 100
    score_normal = percentile_score(80, history, invert=False)
    assert score_normal == 79.0  # 79 items lower than 80

    score_inverted = percentile_score(20, history, invert=True)
    assert score_inverted == 80.0  # 80 items higher than 20

    scores = {
        "FG_MOMENTUM": 80.0,
        "FG_STRENGTH": 60.0,
        "FG_BREADTH": 70.0,
        "FG_PUTCALL": 50.0,
        "FG_VIX": 90.0,
        "FG_JUNKBOND": 85.0,
        "FG_SAFEHAVEN": 75.0,
    }
    composite = calculate_composite(scores)
    assert composite == round(sum(scores.values()) / 7, 1)
