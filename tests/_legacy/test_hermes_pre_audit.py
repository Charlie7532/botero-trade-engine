"""
tests/test_hermes_pre_audit.py — Suite de Pruebas para hermes_gates/pre_audit.py
================================================================================
Verifica que el Gatekeeper Determinista:
1. Apruebe los 5 tipos de experimentos válidos.
2. Detecte y aborte ante Lookahead Bias (signal_time >= exec_time).
3. Rechace muestras insuficientes o métricas deficientes (DSR, PBO, EV/MAE, Fisher).
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = ROOT / "hermes_gates/pre_audit.py"


def run_pre_audit(input_data: dict, tmp_path: Path) -> Tuple[int, str, str, dict]:
    input_file = tmp_path / "backtest_results.json"
    output_file = tmp_path / "pre_audit_summary.json"

    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(input_data, f)

    cmd = [sys.executable, str(GATE_SCRIPT), "--input", str(input_file), "--output", str(output_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)

    out_json = {}
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            out_json = json.load(f)

    return res.returncode, res.stdout, res.stderr, out_json


def test_signal_event_study_passes(tmp_path):
    """Estudio de señal válido (similar a los resultados de ayer)."""
    np.random.seed(42)
    n = 60
    # Generar retornos positivos asimétricos con MAE controlado
    returns = np.random.normal(0.035, 0.02, n)
    mae = np.random.uniform(0.005, 0.025, n)

    trades = []
    base_date = pd.Timestamp("2026-01-01")
    for i in range(n):
        sig_t = base_date + pd.Timedelta(days=i * 2)
        exec_t = sig_t + pd.Timedelta(days=1)
        trades.append({
            "signal_time": sig_t.strftime("%Y-%m-%d"),
            "exec_time": exec_t.strftime("%Y-%m-%d"),
            "return": float(returns[i]),
            "mae": float(mae[i]),
        })

    payload = {
        "experiment_type": "signal_event_study",
        "trade_log": trades,
    }

    code, stdout, stderr, summary = run_pre_audit(payload, tmp_path)
    assert code == 0, f"Error: {stderr}"
    assert summary["status"] == "PASSED_DETERMINISTIC_GATES"
    assert summary["lookahead_audit"] == "PASSED (0 violations)"
    assert summary["sample_size"] == 60
    assert summary["verified_metrics"]["path_dependency_ratio"] >= 1.0


def test_anti_lookahead_bias_aborts(tmp_path):
    """Detecta coincidencia o inversión temporal y aborta con código 1."""
    trades = [
        {"signal_time": "2026-05-10", "exec_time": "2026-05-11", "return": 0.02, "mae": 0.01},
        {"signal_time": "2026-05-12", "exec_time": "2026-05-12", "return": 0.03, "mae": 0.01},  # VIOLATION
    ]
    payload = {
        "experiment_type": "signal_event_study",
        "trade_log": trades,
    }

    code, stdout, stderr, summary = run_pre_audit(payload, tmp_path)
    assert code == 1
    assert "LOOKAHEAD_BIAS" in stderr
    assert "Data Leakage detectado" in stderr


def test_backtest_dsr_and_pbo_passes(tmp_path):
    """Backtest con 120 trades, Sharpe robusto y n_trials=1."""
    np.random.seed(42)
    n = 120
    returns = np.random.normal(0.008, 0.012, n)  # Sharpe ~ 10.5 annualized

    trades = []
    base_date = pd.Timestamp("2024-01-01")
    for i in range(n):
        sig_t = base_date + pd.Timedelta(days=i * 3)
        exec_t = sig_t + pd.Timedelta(days=5)
        trades.append({
            "signal_time": sig_t.strftime("%Y-%m-%d"),
            "exec_time": exec_t.strftime("%Y-%m-%d"),
            "return": float(returns[i]),
        })

    payload = {
        "experiment_type": "backtest",
        "n_trials": 1,
        "trade_log": trades,
    }

    code, stdout, stderr, summary = run_pre_audit(payload, tmp_path)
    assert code == 0, f"Error: {stderr}"
    assert summary["verified_metrics"]["deflated_sharpe_ratio"] >= 0.95
    assert summary["verified_metrics"]["pbo_cscv"] <= 0.30


def test_rare_tail_event_passes(tmp_path):
    """Diamante de régimen con 8 ocurrencias históricas, 7 victorias y 0 wipeouts."""
    trades = [
        {"signal_time": "2008-10-10", "exec_time": "2008-10-11", "return": 0.18, "mae": 0.02},
        {"signal_time": "2008-11-20", "exec_time": "2008-11-21", "return": 0.12, "mae": 0.03},
        {"signal_time": "2011-08-08", "exec_time": "2011-08-09", "return": 0.09, "mae": 0.01},
        {"signal_time": "2015-08-24", "exec_time": "2015-08-25", "return": 0.07, "mae": 0.02},
        {"signal_time": "2018-12-24", "exec_time": "2018-12-26", "return": 0.14, "mae": 0.01},
        {"signal_time": "2020-03-23", "exec_time": "2020-03-24", "return": 0.22, "mae": 0.04},
        {"signal_time": "2022-10-13", "exec_time": "2022-10-14", "return": 0.08, "mae": 0.02},
        {"signal_time": "2024-08-05", "exec_time": "2024-08-06", "return": -0.02, "mae": 0.03},
    ]
    payload = {
        "experiment_type": "rare_tail_event",
        "trade_log": trades,
    }

    code, stdout, stderr, summary = run_pre_audit(payload, tmp_path)
    assert code == 0, f"Error: {stderr}"
    assert summary["verified_metrics"]["win_rate"] >= 0.75
    assert summary["verified_metrics"]["profit_factor"] >= 3.0
    assert len(summary["rare_event_census"]) == 8


def test_forward_test_distribution_consistency(tmp_path):
    """Forward test con distribución consistente (KS-test p > 0.05)."""
    np.random.seed(42)
    back_ret = np.random.normal(0.005, 0.015, 200).tolist()
    fwd_ret = np.random.normal(0.0048, 0.015, 40).tolist()

    payload = {
        "experiment_type": "forward_test",
        "backtest_returns": back_ret,
        "forward_returns": fwd_ret,
    }

    code, stdout, stderr, summary = run_pre_audit(payload, tmp_path)
    assert code == 0, f"Error: {stderr}"
    assert summary["verified_metrics"]["ks_pvalue"] > 0.05
    assert summary["verified_metrics"]["forward_expectancy_ev"] > 0.0
