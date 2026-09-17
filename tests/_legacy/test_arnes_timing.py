import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

from arnes.timing import (
    classify_single_delta,
    classify_timing_slots,
    calc_timing_distribution,
    SLOT_ORDER,
)


def test_classify_single_delta():
    assert classify_single_delta(0) == "t=0"
    assert classify_single_delta(-1) == "t-1"
    assert classify_single_delta(-2) == "t-2"
    assert classify_single_delta(1) == "t+1"
    assert classify_single_delta(2) == "t+2"
    assert classify_single_delta(3) == "ENTRE"
    assert classify_single_delta(-3) == "ENTRE"
    assert classify_single_delta(10) == "ENTRE"
    assert classify_single_delta(-15) == "ENTRE"


def test_classify_timing_slots_accuracy():
    pivots = pd.to_datetime(["2026-01-10", "2026-01-20"])
    pivot_types = ["MIN", "MAX"]

    signals = pd.to_datetime([
        "2026-01-08",  # 2 days before 1st pivot (t-2) -> ANTICIPADA
        "2026-01-09",  # 1 day before 1st pivot (t-1) -> ANTICIPADA
        "2026-01-10",  # exact on 1st pivot (t=0) -> EXACTA
        "2026-01-11",  # 1 day after 1st pivot (t+1) -> RETRASADA
        "2026-01-12",  # 2 days after 1st pivot (t+2) -> RETRASADA
        "2026-01-15",  # 5 days from both (ENTRE) -> FUERA_DE_RANGO
        "2026-01-19",  # 1 day before 2nd pivot (t-1) -> ANTICIPADA
    ])

    df = classify_timing_slots(signals, pivots, pivot_types)

    expected_slots = ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE", "t-1"]
    expected_cats = ["ANTICIPADA", "ANTICIPADA", "EXACTA", "RETRASADA", "RETRASADA", "FUERA_DE_RANGO", "ANTICIPADA"]

    assert list(df["slot"]) == expected_slots
    assert list(df["categoria"]) == expected_cats


def test_calc_timing_distribution():
    pivots = pd.to_datetime(["2026-01-10"])
    signals = pd.to_datetime([
        "2026-01-08",  # t-2
        "2026-01-09",  # t-1
        "2026-01-10",  # t=0
        "2026-01-11",  # t+1
        "2026-01-12",  # t+2
        "2026-01-15",  # ENTRE
    ])

    dist = calc_timing_distribution(signals, pivots)

    assert dist["n_total"] == 6
    assert dist["counts"]["t-2"] == 1
    assert dist["counts"]["t-1"] == 1
    assert dist["counts"]["t=0"] == 1
    assert dist["counts"]["t+1"] == 1
    assert dist["counts"]["t+2"] == 1
    assert dist["counts"]["ENTRE"] == 1

    assert dist["n_anticipada"] == 2
    assert dist["n_exacta"] == 1
    assert dist["n_retrasada"] == 2
    assert dist["n_fuera"] == 1
    assert dist["n_en_rango"] == 5
    assert round(dist["pct_en_rango"], 1) == 83.3
