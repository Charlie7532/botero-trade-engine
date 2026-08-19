#!/usr/bin/env python3
"""
hermes_gates/pre_audit.py — Gatekeeper Determinista Cuantitativo
================================================================
Filtro de validación matemática e industrial ($0 tokens de API) basado en
la metodología de Marcos López de Prado (Advances in Financial Machine Learning)
y Teoría de Valores Extremos (EVT).

Audita '{worktree}/artifacts/backtest_results.json' antes de que el auditor
epistemológico (Kimi-k3) sea invocado.

Uso CLI:
  python3 hermes_gates/pre_audit.py \
      --input /path/to/backtest_results.json \
      --output /path/to/pre_audit_summary.json

Códigos de salida:
  0: Aprobado (status: PASSED_DETERMINISTIC_GATES)
  1: Rechazado o error de esquema (mensaje descriptivo en stderr)
"""
import argparse
import datetime
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import scipy.stats


# ─────────────────────────────────────────────────────────────────────────────
# 1. FUNCIONES MATEMÁTICAS PURAS (López de Prado & EVT)
# ─────────────────────────────────────────────────────────────────────────────

def compute_dsr(returns: np.ndarray, n_trials: int = 1, periods_per_year: int = 252) -> float:
    """
    Deflated Sharpe Ratio (López de Prado, 2014 / Bailey & López de Prado, 2012).
    Ajusta el Sharpe por sesgo de selección de K ensayos y momentos de orden superior.
    """
    n = len(returns)
    if n < 2:
        return 0.0

    mean_r = float(np.mean(returns))
    std_r = float(np.std(returns, ddof=1))
    if std_r == 0:
        return 0.0

    # Sharpe por periodo (sin anualizar)
    sr_1 = mean_r / std_r
    # Sharpe anualizado
    sr_ann = sr_1 * np.sqrt(periods_per_year)

    # Momentos de la distribución
    skew = float(scipy.stats.skew(returns))
    kurt = float(scipy.stats.kurtosis(returns, fisher=False))  # Pearson (normal=3)

    # Varianza asintótica por periodo (Bailey & López de Prado, 2012 eq. 10)
    var_sr_1 = (1.0 - skew * sr_1 + ((kurt - 1.0) / 4.0) * (sr_1 ** 2)) / (n - 1)
    if var_sr_1 <= 0:
        return 0.0

    # Varianza escalada al horizonte anualizado
    var_sr_ann = periods_per_year * var_sr_1

    # SR* benchmark ajustado por número de ensayos (Gumbel extrema / Euler-Mascheroni)
    if n_trials > 1:
        euler_mascheroni = 0.5772156649
        z1 = scipy.stats.norm.ppf(1.0 - 1.0 / n_trials)
        z2 = scipy.stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        sr_star = np.sqrt(var_sr_ann) * ((1.0 - euler_mascheroni) * z1 + euler_mascheroni * z2)
    else:
        sr_star = 0.0

    dsr = scipy.stats.norm.cdf((sr_ann - sr_star) / np.sqrt(var_sr_ann))
    return float(dsr)


def compute_pbo_cscv(returns: np.ndarray, n_splits: int = 8, embargo: int = 5) -> float:
    """
    Probability of Backtest Overfitting (PBO) vía Combinatorially Symmetric Cross-Validation (CSCV)
    con particiones cronológicas continuas y buffer de embargo.
    """
    n = len(returns)
    if n < n_splits * 2:
        return 0.0

    # Dividir retornos en n_splits bloques contiguos
    split_size = n // n_splits
    blocks = [returns[i * split_size:(i + 1) * split_size] for i in range(n_splits)]

    # 8 particiones -> 70 combinaciones de 4 train / 4 test
    k = n_splits // 2
    combos = list(itertools.combinations(range(n_splits), k))

    oos_negative_count = 0
    total_valid_combos = 0

    for train_idx in combos:
        test_idx = [i for i in range(n_splits) if i not in train_idx]

        # Concatenar bloques de test aplicando embargo en las fronteras
        test_parts = []
        for idx in test_idx:
            blk = blocks[idx]
            if len(blk) > embargo:
                test_parts.append(blk[embargo:])
            else:
                test_parts.append(blk)

        if not test_parts:
            continue

        test_data = np.concatenate(test_parts)
        if len(test_data) < 2:
            continue

        mean_oos = np.mean(test_data)
        std_oos = np.std(test_data, ddof=1)
        sr_oos = (mean_oos / std_oos) if std_oos > 0 else 0.0

        if sr_oos <= 0.0:
            oos_negative_count += 1
        total_valid_combos += 1

    if total_valid_combos == 0:
        return 0.0

    pbo = oos_negative_count / total_valid_combos
    return float(pbo)


def compute_max_drawdown(returns: np.ndarray) -> float:
    """Calcula el Maximum Drawdown de la curva de capital acumulada."""
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    drawdowns = (equity - peak) / peak
    return float(np.abs(np.min(drawdowns))) if len(drawdowns) > 0 else 0.0


def compute_profit_factor(returns: np.ndarray) -> float:
    """Calcula el Profit Factor (Suma Ganancias / |Suma Pérdidas|)."""
    gains = returns[returns > 0]
    losses = returns[returns < 0]
    sum_gains = np.sum(gains) if len(gains) > 0 else 0.0
    sum_losses = np.abs(np.sum(losses)) if len(losses) > 0 else 0.0
    if sum_losses == 0:
        return 100.0 if sum_gains > 0 else 0.0
    return float(sum_gains / sum_losses)


def compute_win_rate(returns: np.ndarray) -> float:
    """Calcula el Win Rate (proporción de retornos > 0)."""
    if len(returns) == 0:
        return 0.0
    return float(np.sum(returns > 0) / len(returns))


# ─────────────────────────────────────────────────────────────────────────────
# 2. VALIDACIÓN DE ESQUEMA Y ANTI-LOOKAHEAD
# ─────────────────────────────────────────────────────────────────────────────

def validate_schema_and_anti_lookahead(data: Dict[str, Any]) -> Tuple[str, Optional[pd.DataFrame]]:
    """Valida esquema requerido y aserción signal_time < exec_time."""
    if "experiment_type" not in data:
        sys.stderr.write("JSON_SCHEMA_ERROR: Falta el campo obligatorio 'experiment_type' en la raíz del JSON.\n")
        sys.exit(1)

    exp_type = data["experiment_type"]
    valid_types = {"backtest", "benchmark_comparison", "forward_test", "signal_event_study", "rare_tail_event"}
    if exp_type not in valid_types:
        sys.stderr.write(f"JSON_SCHEMA_ERROR: 'experiment_type'='{exp_type}' inválido. Opciones válidas: {sorted(valid_types)}.\n")
        sys.exit(1)

    # Validación específica por tipo
    if exp_type in {"backtest", "signal_event_study", "benchmark_comparison", "rare_tail_event"}:
        if "trade_log" not in data or not isinstance(data["trade_log"], list):
            sys.stderr.write(f"JSON_SCHEMA_ERROR: '{exp_type}' requiere el campo 'trade_log' (array de objetos).\n")
            sys.exit(1)

        trades = data["trade_log"]
        if len(trades) == 0:
            sys.stderr.write("PRE-AUDIT FAILED: 'trade_log' está vacío (N=0).\n")
            sys.exit(1)

        df_trades = pd.DataFrame(trades)

        # Validar campos en cada trade
        req_cols = {"signal_time", "exec_time", "return"}
        if exp_type in {"signal_event_study", "rare_tail_event"}:
            req_cols.add("mae")

        missing_cols = req_cols - set(df_trades.columns)
        if missing_cols:
            sys.stderr.write(f"JSON_SCHEMA_ERROR: '{exp_type}' requiere los campos {sorted(missing_cols)} en cada trade.\n")
            sys.exit(1)

        # Validación Anti-Lookahead
        try:
            sig_times = pd.to_datetime(df_trades["signal_time"])
            exec_times = pd.to_datetime(df_trades["exec_time"])
        except Exception as e:
            sys.stderr.write(f"JSON_SCHEMA_ERROR: Error al parsear fechas temporales con pd.to_datetime: {e}\n")
            sys.exit(1)

        violations = sig_times >= exec_times
        if violations.any():
            first_idx = int(np.where(violations)[0][0])
            bad_sig = df_trades.iloc[first_idx]["signal_time"]
            bad_exec = df_trades.iloc[first_idx]["exec_time"]
            sys.stderr.write(
                f"LOOKAHEAD_BIAS: Trade #{first_idx} tiene signal_time='{bad_sig}' >= exec_time='{bad_exec}'. "
                f"Data Leakage detectado.\n"
            )
            sys.exit(1)

        if exp_type == "benchmark_comparison":
            if "benchmark_returns" not in data or not isinstance(data["benchmark_returns"], list):
                sys.stderr.write("JSON_SCHEMA_ERROR: 'benchmark_comparison' requiere 'benchmark_returns' (array paralelo) en la raíz.\n")
                sys.exit(1)

        return exp_type, df_trades

    elif exp_type == "forward_test":
        if "backtest_returns" not in data or "forward_returns" not in data:
            sys.stderr.write("JSON_SCHEMA_ERROR: 'forward_test' requiere 'backtest_returns' y 'forward_returns' en la raíz del JSON.\n")
            sys.exit(1)
        return exp_type, None

    return exp_type, None


# ─────────────────────────────────────────────────────────────────────────────
# 3. BATERÍAS DE TESTS DETERMINISTAS
# ─────────────────────────────────────────────────────────────────────────────

def audit_backtest(data: Dict[str, Any], df_trades: pd.DataFrame) -> Dict[str, Any]:
    returns = df_trades["return"].to_numpy(dtype=float)
    n = len(returns)
    if n < 100:
        sys.stderr.write(f"PRE-AUDIT FAILED: backtest | sample_size: obtenido={n} vs requerido=100\n")
        sys.exit(1)

    ev = float(np.mean(returns))
    pf = compute_profit_factor(returns)
    wr = compute_win_rate(returns)
    max_dd = compute_max_drawdown(returns)

    if ev <= 0.0:
        sys.stderr.write(f"PRE-AUDIT FAILED: backtest | expectancy_ev: obtenido={ev:.4f} vs requerido > 0.0\n")
        sys.exit(1)

    if pf < 1.30:
        sys.stderr.write(f"PRE-AUDIT FAILED: backtest | profit_factor: obtenido={pf:.2f} vs requerido >= 1.30\n")
        sys.exit(1)

    if max_dd > 0.25:
        sys.stderr.write(f"PRE-AUDIT FAILED: backtest | max_drawdown: obtenido={max_dd:.2%} vs requerido <= 25.0%\n")
        sys.exit(1)

    n_trials = int(data.get("n_trials", 1))
    dsr = compute_dsr(returns, n_trials=n_trials)
    if dsr < 0.95:
        sys.stderr.write(f"PRE-AUDIT FAILED: backtest | deflated_sharpe_ratio: obtenido={dsr:.4f} vs requerido >= 0.95 (n_trials={n_trials})\n")
        sys.exit(1)

    # Holding period para embargo adaptativo
    sig_times = pd.to_datetime(df_trades["signal_time"])
    exec_times = pd.to_datetime(df_trades["exec_time"])
    holding_days = (exec_times - sig_times).dt.days
    median_holding = int(np.median(holding_days)) if len(holding_days) > 0 else 5
    embargo = max(5, median_holding)

    pbo = compute_pbo_cscv(returns, n_splits=8, embargo=embargo)
    if pbo > 0.30:
        sys.stderr.write(f"PRE-AUDIT FAILED: backtest | pbo_cscv: obtenido={pbo:.2%} vs requerido <= 30.0% (embargo={embargo}d)\n")
        sys.exit(1)

    # Anti-concentración: Top 5% trades <= 40% del total de ganancias positivas
    positive_gains = returns[returns > 0]
    if len(positive_gains) > 0:
        sorted_gains = np.sort(positive_gains)[::-1]
        top_5_pct_count = max(1, int(np.ceil(0.05 * len(returns))))
        top_5_sum = np.sum(sorted_gains[:top_5_pct_count])
        total_gain_sum = np.sum(positive_gains)
        concentration_ratio = (top_5_sum / total_gain_sum) if total_gain_sum > 0 else 1.0
        if concentration_ratio > 0.40:
            sys.stderr.write(f"PRE-AUDIT FAILED: backtest | top_5pct_concentration: obtenido={concentration_ratio:.2%} vs requerido <= 40.0%\n")
            sys.exit(1)
    else:
        concentration_ratio = 0.0

    return {
        "expectancy_ev": ev,
        "profit_factor": pf,
        "win_rate": wr,
        "max_drawdown": max_dd,
        "deflated_sharpe_ratio": dsr,
        "n_trials": n_trials,
        "pbo_cscv": pbo,
        "adaptive_embargo_bars": embargo,
        "top_5pct_concentration": concentration_ratio,
    }


def audit_benchmark_comparison(data: Dict[str, Any], df_trades: pd.DataFrame) -> Dict[str, Any]:
    strat_returns = df_trades["return"].to_numpy(dtype=float)
    bench_returns = np.array(data["benchmark_returns"], dtype=float)

    n = min(len(strat_returns), len(bench_returns))
    if n < 50:
        sys.stderr.write(f"PRE-AUDIT FAILED: benchmark_comparison | sample_size: obtenido={n} vs requerido=50\n")
        sys.exit(1)

    s_ret = strat_returns[:n]
    b_ret = bench_returns[:n]

    # Alpha anualizado simple vs Benchmark
    cum_s = np.prod(1.0 + s_ret) - 1.0
    cum_b = np.prod(1.0 + b_ret) - 1.0
    alpha = cum_s - cum_b
    if alpha <= 0.0:
        sys.stderr.write(f"PRE-AUDIT FAILED: benchmark_comparison | alpha_vs_benchmark: obtenido={alpha:.4f} vs requerido > 0.0\n")
        sys.exit(1)

    # Downside Protection Score: retorno relativo medio cuando el benchmark es negativo
    down_mask = b_ret < 0.0
    if np.sum(down_mask) > 0:
        downside_relative = np.mean(s_ret[down_mask] - b_ret[down_mask])
        if downside_relative < 0.0:
            sys.stderr.write(f"PRE-AUDIT FAILED: benchmark_comparison | downside_protection_score: obtenido={downside_relative:.4f} vs requerido >= 0.0\n")
            sys.exit(1)
    else:
        downside_relative = 0.0

    # Information Ratio
    active_ret = s_ret - b_ret
    te = np.std(active_ret, ddof=1)
    ir = (np.mean(active_ret) / te) * np.sqrt(252) if te > 0 else 0.0
    if ir < 0.50:
        sys.stderr.write(f"PRE-AUDIT FAILED: benchmark_comparison | information_ratio: obtenido={ir:.2f} vs requerido >= 0.50\n")
        sys.exit(1)

    return {
        "alpha_vs_benchmark": float(alpha),
        "downside_protection_score": float(downside_relative),
        "information_ratio": float(ir),
        "benchmark_sample_size": n,
    }


def audit_forward_test(data: Dict[str, Any]) -> Dict[str, Any]:
    back_ret = np.array(data["backtest_returns"], dtype=float)
    fwd_ret = np.array(data["forward_returns"], dtype=float)

    n_fwd = len(fwd_ret)
    if n_fwd < 25:
        sys.stderr.write(f"PRE-AUDIT FAILED: forward_test | forward_sample_size: obtenido={n_fwd} vs requerido=25\n")
        sys.exit(1)

    # Kolmogorov-Smirnov 2-sample test
    ks_res = scipy.stats.ks_2samp(back_ret, fwd_ret)
    if ks_res.pvalue <= 0.05:
        sys.stderr.write(f"PRE-AUDIT FAILED: forward_test | ks_distribution_pvalue: obtenido={ks_res.pvalue:.4f} vs requerido > 0.05 (distribución rota)\n")
        sys.exit(1)

    ev_fwd = float(np.mean(fwd_ret))
    if ev_fwd <= 0.0:
        sys.stderr.write(f"PRE-AUDIT FAILED: forward_test | forward_expectancy_ev: obtenido={ev_fwd:.4f} vs requerido > 0.0\n")
        sys.exit(1)

    wr_back = compute_win_rate(back_ret)
    wr_fwd = compute_win_rate(fwd_ret)
    wr_drop = wr_back - wr_fwd
    if wr_drop > 0.10:
        sys.stderr.write(f"PRE-AUDIT FAILED: forward_test | win_rate_degradation: obtenido={wr_drop:.2%} vs requerido <= 10.0%\n")
        sys.exit(1)

    return {
        "ks_stat": float(ks_res.statistic),
        "ks_pvalue": float(ks_res.pvalue),
        "forward_expectancy_ev": ev_fwd,
        "backtest_win_rate": float(wr_back),
        "forward_win_rate": float(wr_fwd),
        "win_rate_degradation": float(wr_drop),
    }


def audit_signal_event_study(df_trades: pd.DataFrame) -> Dict[str, Any]:
    returns = df_trades["return"].to_numpy(dtype=float)
    mae = np.abs(df_trades["mae"].to_numpy(dtype=float))

    n = len(returns)
    if n < 30:
        sys.stderr.write(f"PRE-AUDIT FAILED: signal_event_study | sample_size: obtenido={n} vs requerido=30\n")
        sys.exit(1)

    # T-test de 1 muestra vs 0.0
    t_res = scipy.stats.ttest_1samp(returns, 0.0)
    if t_res.pvalue >= 0.01 or t_res.statistic <= 2.50:
        sys.stderr.write(f"PRE-AUDIT FAILED: signal_event_study | car_t_test: t_stat={t_res.statistic:.2f} (req > 2.50), p_value={t_res.pvalue:.4f} (req < 0.01)\n")
        sys.exit(1)

    ev = float(np.mean(returns))
    mae_mean = float(np.mean(mae))
    path_quality = (ev / mae_mean) if mae_mean > 0 else 100.0
    if path_quality < 1.0:
        sys.stderr.write(f"PRE-AUDIT FAILED: signal_event_study | path_dependency_ratio (EV/|MAE|): obtenido={path_quality:.2f} vs requerido >= 1.0\n")
        sys.exit(1)

    gains = returns[returns > 0]
    losses = np.abs(returns[returns < 0])
    mean_gain = np.mean(gains) if len(gains) > 0 else 0.0
    mean_loss = np.mean(losses) if len(losses) > 0 else 0.0
    asymmetry = (mean_gain / mean_loss) if mean_loss > 0 else 100.0
    if asymmetry < 1.20:
        sys.stderr.write(f"PRE-AUDIT FAILED: signal_event_study | return_asymmetry: obtenido={asymmetry:.2f} vs requerido >= 1.20\n")
        sys.exit(1)

    return {
        "cumulative_abnormal_return_mean": ev,
        "t_stat": float(t_res.statistic),
        "t_pvalue": float(t_res.pvalue),
        "mae_mean": mae_mean,
        "path_dependency_ratio": float(path_quality),
        "return_asymmetry": float(asymmetry),
    }


def audit_rare_tail_event(df_trades: pd.DataFrame) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    returns = df_trades["return"].to_numpy(dtype=float)
    mae = np.abs(df_trades["mae"].to_numpy(dtype=float))

    n = len(returns)
    if n < 5:
        sys.stderr.write(f"PRE-AUDIT FAILED: rare_tail_event | sample_size: obtenido={n} vs requerido=5 (censo histórico del Vault)\n")
        sys.exit(1)

    wr = compute_win_rate(returns)
    pf = compute_profit_factor(returns)

    if wr < 0.75:
        sys.stderr.write(f"PRE-AUDIT FAILED: rare_tail_event | win_rate: obtenido={wr:.2%} vs requerido >= 75.0%\n")
        sys.exit(1)

    if pf < 3.0:
        sys.stderr.write(f"PRE-AUDIT FAILED: rare_tail_event | profit_factor: obtenido={pf:.2f} vs requerido >= 3.0\n")
        sys.exit(1)

    # Cero wipeouts: ningún trade con pérdida > 2x la media de pérdidas (o > 15%)
    losses = np.abs(returns[returns < 0])
    if len(losses) > 0:
        mean_loss = np.mean(losses)
        max_loss = np.max(losses)
        if max_loss > 2.0 * mean_loss and max_loss > 0.10:
            sys.stderr.write(f"PRE-AUDIT FAILED: rare_tail_event | wipeout_detected: max_loss={max_loss:.2%} excede 2x pérdida media ({mean_loss:.2%})\n")
            sys.exit(1)

    # Test no paramétrico binomial de aciertos vs 50% azar
    n_wins = int(np.sum(returns > 0))
    binom_p = scipy.stats.binomtest(n_wins, n, p=0.5, alternative="greater").pvalue
    if binom_p >= 0.05:
        sys.stderr.write(f"PRE-AUDIT FAILED: rare_tail_event | non_parametric_pvalue: obtenido={binom_p:.4f} vs requerido < 0.05\n")
        sys.exit(1)

    census_records = []
    for _, row in df_trades.iterrows():
        census_records.append({
            "signal_time": str(row["signal_time"]),
            "exec_time": str(row["exec_time"]),
            "return": float(row["return"]),
            "mae": float(row["mae"]),
        })

    metrics = {
        "win_rate": wr,
        "profit_factor": pf,
        "sample_size": n,
        "binomial_pvalue": float(binom_p),
        "rare_event_census_count": n,
    }
    return metrics, census_records


# ─────────────────────────────────────────────────────────────────────────────
# 4. ENTRYPOINT CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="hermes_gates/pre_audit.py — Gatekeeper Cuantitativo Determinista")
    parser.add_argument("--input", required=True, help="Ruta a backtest_results.json")
    parser.add_argument("--output", required=True, help="Ruta a pre_audit_summary.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        sys.stderr.write(f"FILE_NOT_FOUND: No se encontró el archivo de entrada '{input_path}'.\n")
        sys.exit(1)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"JSON_PARSE_ERROR: Error al leer JSON '{input_path}': {e}\n")
        sys.exit(1)

    exp_type, df_trades = validate_schema_and_anti_lookahead(data)

    verified_metrics: Dict[str, Any] = {}
    census_list: Optional[List[Dict[str, Any]]] = None
    all_returns: np.ndarray = np.array([])
    sample_size = 0
    temporal_span = {"start": "N/A", "end": "N/A"}
    mae_mean: Optional[float] = None

    if exp_type == "backtest":
        assert df_trades is not None
        verified_metrics = audit_backtest(data, df_trades)
        all_returns = df_trades["return"].to_numpy(dtype=float)
        sample_size = len(df_trades)
        temporal_span = {
            "start": str(df_trades["signal_time"].min()),
            "end": str(df_trades["exec_time"].max()),
        }

    elif exp_type == "benchmark_comparison":
        assert df_trades is not None
        verified_metrics = audit_benchmark_comparison(data, df_trades)
        all_returns = df_trades["return"].to_numpy(dtype=float)
        sample_size = len(df_trades)
        temporal_span = {
            "start": str(df_trades["signal_time"].min()),
            "end": str(df_trades["exec_time"].max()),
        }

    elif exp_type == "forward_test":
        verified_metrics = audit_forward_test(data)
        all_returns = np.array(data["forward_returns"], dtype=float)
        sample_size = len(all_returns)
        temporal_span = {"start": "FORWARD_START", "end": "FORWARD_END"}

    elif exp_type == "signal_event_study":
        assert df_trades is not None
        verified_metrics = audit_signal_event_study(df_trades)
        all_returns = df_trades["return"].to_numpy(dtype=float)
        sample_size = len(df_trades)
        mae_mean = float(np.mean(np.abs(df_trades["mae"])))
        temporal_span = {
            "start": str(df_trades["signal_time"].min()),
            "end": str(df_trades["exec_time"].max()),
        }

    elif exp_type == "rare_tail_event":
        assert df_trades is not None
        verified_metrics, census_list = audit_rare_tail_event(df_trades)
        all_returns = df_trades["return"].to_numpy(dtype=float)
        sample_size = len(df_trades)
        mae_mean = float(np.mean(np.abs(df_trades["mae"])))
        temporal_span = {
            "start": str(df_trades["signal_time"].min()),
            "end": str(df_trades["exec_time"].max()),
        }

    skew = float(scipy.stats.skew(all_returns)) if len(all_returns) > 2 else 0.0
    kurt = float(scipy.stats.kurtosis(all_returns, fisher=False)) if len(all_returns) > 2 else 3.0

    summary = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "experiment_type": exp_type,
        "status": "PASSED_DETERMINISTIC_GATES",
        "sample_size": sample_size,
        "n_trials": int(data.get("n_trials", 1)),
        "temporal_span": temporal_span,
        "lookahead_audit": "PASSED (0 violations)",
        "distribution_metrics": {
            "skewness": skew,
            "kurtosis": kurt,
            "mae_mean": mae_mean,
        },
        "verified_metrics": verified_metrics,
        "rare_event_census": census_list,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[PRE-AUDIT: PASSED] Type: {exp_type} | N={sample_size} | Status: PASSED_DETERMINISTIC_GATES")
    sys.exit(0)


if __name__ == "__main__":
    main()
