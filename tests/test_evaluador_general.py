import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / "research" / "01_señales_entry_exit"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from evaluador_general import (
    cargar_entorno_evaluacion,
    build_episodes,
    first_passage_bar,
    evaluar_condicion_booleana,
    evaluar_senal,
    ESCALAS,
)


def test_build_episodes_basic():
    index = pd.date_range("2026-01-01", periods=10, freq="D")
    mask = np.array([0, 1, 1, 1, 0, 0, 1, 1, 0, 1], dtype=bool)

    episodes = build_episodes(mask, index)
    assert len(episodes) == 3

    # Episode 1: idxs 1,2,3 -> duration 3
    assert episodes[0]["start_idx"] == 1
    assert episodes[0]["end_idx"] == 3
    assert episodes[0]["duration_bars"] == 3
    assert episodes[0]["start_date"] == index[1]

    # Episode 2: idxs 6,7 -> duration 2
    assert episodes[1]["start_idx"] == 6
    assert episodes[1]["end_idx"] == 7
    assert episodes[1]["duration_bars"] == 2

    # Episode 3: idx 9 -> duration 1
    assert episodes[2]["start_idx"] == 9
    assert episodes[2]["end_idx"] == 9
    assert episodes[2]["duration_bars"] == 1


def test_first_passage_bar_mechanics():
    # Construct synthetic price path
    close = np.array([100.0, 101.0, 102.0, 103.0, 100.0, 95.0])
    highs = np.array([100.5, 101.5, 102.5, 103.5, 100.5, 95.5])
    lows = np.array([99.5, 100.5, 101.5, 102.0, 99.0, 94.0])

    # MIN / Long with 2.5% target (up target = 102.5, down target = 97.5)
    r_min = first_passage_bar(close, highs, lows, t0=0, scale=0.025, blanco="MIN")
    assert r_min is not None
    assert r_min["resuelto"] is True
    assert r_min["hit"] is True  # Up barrier reached at bar 2 (high=102.5) before down
    assert r_min["bars"] == 2
    assert r_min["favorable"] > 0

    # MAX / Short with 2.5% target (up target = 102.5, down target = 97.5)
    r_max = first_passage_bar(close, highs, lows, t0=0, scale=0.025, blanco="MAX")
    assert r_max is not None
    assert r_max["resuelto"] is True
    assert r_max["hit"] is False  # Up reached first, so short was stopped out
    assert r_max["favorable"] < 0


def test_evaluar_condicion_booleana_end_to_end():
    lake, quants = cargar_entorno_evaluacion()
    assert len(lake) > 0
    assert len(quants) > 0

    # Create synthetic periodic signal
    synth_mask = pd.Series(False, index=lake.index)
    synth_mask.iloc[::200] = True  # fire every 200 bars

    res = evaluar_condicion_booleana(
        sig_mask=synth_mask,
        nombre="test_synth_signal",
        blanco="MIN",
    )

    assert res["status"] == "OK"
    assert res["poblacion"]["n_episodios"] > 0
    assert "timing_canonico" in res
    assert "escalas_zigzag" in res
    assert "zz25" in res["escalas_zigzag"]


def test_evaluar_senal_real():
    res = evaluar_senal("bsi_washed_out")
    assert res["status"] == "OK"
    assert res["blanco"] == "MIN"
    assert res["poblacion"]["n_episodios"] > 50
    assert res["timing_canonico"]["pct_en_rango"] > 80.0
    assert "rendimiento_por_slot" in res
    assert "t-1" in res["rendimiento_por_slot"]
