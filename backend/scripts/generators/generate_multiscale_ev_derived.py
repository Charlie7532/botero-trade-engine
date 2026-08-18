#!/usr/bin/env python3
"""
Generate Multiscale EV Derived Tree — Stage 2 Script
=====================================================
Reads raw empirical probability table (rc_ev_multiscale_probability_table.json)
and derives the final Rule 21 compliant Fact Store (rc_ev_multiscale_tree.json).

Applies:
  1. Hierarchical Bayesian Shrinkage (L6 -> L3 -> L1 -> L0): Shrinks low-N cells (N < 30)
     toward their parent triad/macro node rather than the global baseline.
  2. Preserves Rare States entropy (is_rare_state flag and asymmetric tail payoffs).
  3. Scale-Specific Maturation & Capital Velocity: e_days and ev_per_day for 2.5%, 5.0%, 7.5%.
  4. Risk & Payoff Metrics: std_return, Sharpe, and Risk/Reward Asymmetry Ratio.
  5. Rule 21 Compliance: Complete 6-block standardized metadata in _documentation.

Output: backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json
"""
import sys
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateMultiscaleEVDerived")

INPUT_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_ev_multiscale_probability_table.json"
OUTPUT_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json"

DEFAULT_FRICTION_BPS = 0.0010
PRIOR_WEIGHT = 20.0


def shrink_cell(cell: dict, parent_cell: dict) -> dict:
    """Applies Hierarchical Bayesian Shrinkage on raw cell metrics toward parent_cell."""
    if not cell:
        return parent_cell or {}

    n = float(cell.get("n", 0))
    parent = parent_cell or {}

    def shrink_scale(scale_prefix):
        n_pos = float(cell.get(f"n_pos_{scale_prefix}", 0))
        n_neg = float(cell.get(f"n_neg_{scale_prefix}", 0))
        sum_pos = float(cell.get(f"sum_max_{scale_prefix}", 0.0))
        sum_neg = float(cell.get(f"sum_min_{scale_prefix}", 0.0))
        e_days_raw = float(cell.get(f"e_days_{scale_prefix}", 10.0))

        n_tot = n_pos + n_neg

        # Parent priors
        p_parent = parent.get(f"p_bull_{scale_prefix}", 0.50)
        e_max_parent = parent.get(f"e_ret_max_{scale_prefix}", 0.05)
        e_min_parent = parent.get(f"e_ret_min_{scale_prefix}", -0.04)
        days_parent = parent.get(f"e_days_{scale_prefix}", 10.0)

        if n_tot > 0:
            raw_p_bull = n_neg / n_tot
            e_max = sum_pos / n_pos if n_pos > 0 else e_max_parent
            e_min = sum_neg / n_neg if n_neg > 0 else e_min_parent
            e_days = e_days_raw
        else:
            raw_p_bull = p_parent
            e_max = e_max_parent
            e_min = e_min_parent
            e_days = days_parent

        # Hierarchical Bayesian Shrinkage
        p_bull = (n_tot * raw_p_bull + PRIOR_WEIGHT * p_parent) / (n_tot + PRIOR_WEIGHT)
        p_bear = 1.0 - p_bull

        ev_net = (p_bull * e_max + p_bear * e_min) - DEFAULT_FRICTION_BPS
        ev_per_day = ev_net / max(e_days, 1.0)

        return {
            f"p_bull_{scale_prefix}": round(p_bull, 4),
            f"p_bear_{scale_prefix}": round(p_bear, 4),
            f"e_ret_max_{scale_prefix}": round(e_max, 4),
            f"e_ret_min_{scale_prefix}": round(e_min, 4),
            f"ev_net_{scale_prefix}": round(ev_net, 4),
            f"e_days_{scale_prefix}": round(e_days, 1),
            f"ev_per_day_{scale_prefix}": round(ev_per_day, 6),
        }

    sc25 = shrink_scale("25")
    sc50 = shrink_scale("50")
    sc75 = shrink_scale("75")

    std_ret = float(cell.get("std_return", parent.get("std_return", 0.05)))
    ev_global = (sc25["ev_net_25"] + sc50["ev_net_50"] + sc75["ev_net_75"]) / 3.0
    sharpe = round(ev_global / (std_ret + 1e-6), 4)

    abs_min = abs(sc25["e_ret_min_25"]) if abs(sc25["e_ret_min_25"]) > 1e-6 else 1e-6
    rr_asymmetry = round(sc25["e_ret_max_25"] / abs_min, 4)

    result = {
        "n": int(n),
        "is_rare_state": n < 30,
    }
    result.update(sc25)
    result.update(sc50)
    result.update(sc75)

    result.update({
        "ev_net_global": round(ev_global, 4),
        "std_return": round(std_ret, 4),
        "sharpe": sharpe,
        "rr_asymmetry": rr_asymmetry,
    })
    return result


def main():
    logger.info(f"Cargando censo empírico base desde {INPUT_PATH}...")
    if not INPUT_PATH.exists():
        logger.error(f"No existe el archivo {INPUT_PATH}. Ejecute primero train_multiscale_kinematic_ev_tree.py")
        sys.exit(1)

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    s0_raw = data.get("s0_global", {})
    s3_raw = data.get("s3_triad", {})
    s1_raw = data.get("s1_full", {})

    logger.info("Aplicando Shrinkage Bayesiano Jerárquico (L6 -> L3 -> L1 -> L0)...")

    # Format L0 global baseline
    s0_derived = shrink_cell(s0_raw, {})

    # Format L3 triad cells shrinking toward L0
    s3_derived = {}
    for k3, cell in s3_raw.items():
        s3_derived[k3] = shrink_cell(cell, s0_derived)

    # Format L6 full cells shrinking toward their parent L3 triad cell
    s1_derived = {}
    for k6, cell in s1_raw.items():
        parts = k6.split("#")
        traj_part = f"#{parts[1]}" if len(parts) > 1 else ""
        sub_parts = parts[0].split("|")

        if len(sub_parts) >= 3:
            parent_k3 = f"{sub_parts[0]}|{sub_parts[1]}|{sub_parts[2]}{traj_part}"
        else:
            parent_k3 = ""

        parent_cell = s3_derived.get(parent_k3, s0_derived)
        s1_derived[k6] = shrink_cell(cell, parent_cell)

    try:
        import subprocess
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        git_commit = "unknown"

    documentation = {
        "model_purpose": "Árbol Cinemático Multiescala de Esperanza Matemática Real con Normalización por Volatilidad y Shrinkage Bayesiano Jerárquico",
        "return_formula": "Esperanza Matemática Neta Punto-a-Punto Real: EV_net_s = P_bull_s * E[R_max_s] + P_bear_s * E[R_min_s] - friction_bps",
        "horizon_gate": "Pivotes ZigZag (2.5% minor, 5.0% medium, 7.5% major swing) con ventana causal prospectiva max 120d",
        "state_hierarchy": {
            "L0": "s0_global (Línea base global sobre 4.57M muestras empíricas)",
            "L1": "s1_full (Vector 6D completo: T|C|W|sc|sw|svw#traj - 450+ celdas granulares)",
            "L3": "s3_triad (Vector 3D Triada Normalizada: T|C|W#traj - 180 celdas)"
        },
        "dimension_thresholds_definition": {
            "volatility_normalization": "slope_norm = slope / max(ema_atr_14_pct, 0.005) contra cuantiles del 100% del censo (1999-2026)",
            "reference_quantiles": "backend/modules/quality_swing/domain/rules/rc_vol_normalized_thresholds.json"
        },
        "hypotheses_references": {
            "HYP_KINEMATIC_ABSORPTION": ".agents/skills/hypothesis-governance/SKILL.md",
            "HYP_FLOOR_EXHAUSTION": ".agents/skills/hypothesis-governance/SKILL.md",
            "HYP_MULTISCALE_CONVERGENCE": ".agents/skills/hypothesis-governance/SKILL.md"
        },
        "field_glossary": {
            "n": "Número total de observaciones empíricas procesadas en la celda",
            "is_rare_state": "Flag booleano de muestra baja (N < 30) preservado para eventos de cola / canarios en la mina",

            "p_bull_25": "Probabilidad bayesiana ajustada de piso en escala 2.5%",
            "p_bear_25": "Probabilidad bayesiana ajustada de techo/bajista en escala 2.5%",
            "e_ret_max_25": "Retorno medio esperado en operaciones alcistas escala 2.5%",
            "e_ret_min_25": "Retorno medio esperado en operaciones bajistas escala 2.5%",
            "ev_net_25": "Esperanza Matemática Neta escala 2.5%",
            "e_days_25": "Días promedio esperados hasta el pivote objetivo escala 2.5%",
            "ev_per_day_25": "Velocidad de Esperanza Matemática por día bloqueado escala 2.5%",

            "p_bull_50": "Probabilidad bayesiana ajustada de piso en escala 5.0%",
            "p_bear_50": "Probabilidad bayesiana ajustada de techo/bajista en escala 5.0%",
            "e_ret_max_50": "Retorno medio esperado en operaciones alcistas escala 5.0%",
            "e_ret_min_50": "Retorno medio esperado en operaciones bajistas escala 5.0%",
            "ev_net_50": "Esperanza Matemática Neta escala 5.0%",
            "e_days_50": "Días promedio esperados hasta el pivote objetivo escala 5.0%",
            "ev_per_day_50": "Velocidad de Esperanza Matemática por día bloqueado escala 5.0%",

            "p_bull_75": "Probabilidad bayesiana ajustada de piso en escala 7.5%",
            "p_bear_75": "Probabilidad bayesiana ajustada de techo/bajista en escala 7.5%",
            "e_ret_max_75": "Retorno medio esperado en operaciones alcistas escala 7.5%",
            "e_ret_min_75": "Retorno medio esperado en operaciones bajistas escala 7.5%",
            "ev_net_75": "Esperanza Matemática Neta escala 7.5%",
            "e_days_75": "Días promedio esperados hasta el pivote objetivo escala 7.5%",
            "ev_per_day_75": "Velocidad de Esperanza Matemática por día bloqueado escala 7.5%",

            "ev_net_global": "Esperanza Matemática Neta Promedio Compuesta de las 3 escalas",
            "std_return": "Desviación estándar de los retornos empíricos en la celda",
            "sharpe": "Ratio de Sharpe Bayesiano Neto por Celda",
            "rr_asymmetry": "Ratio de Asimetría Riesgo/Recompensa (e_ret_max_25 / |e_ret_min_25|)"
        },
        "signal_interpretation_policy": "Clean Architecture Protocol: Los adaptadores puros de dominio (rc_multiscale_ev_lookup.py) interpretan dinámicamente las métricas numéricas en taxonomías institucionales. Cero strings estáticos en JSON."
    }

    output_tree = {
        "_documentation": documentation,
        "version": "v2_multiscale_kinematic_2026",
        "git_commit": git_commit,
        "friction_bps": DEFAULT_FRICTION_BPS,
        "prior_weight": PRIOR_WEIGHT,
        "n_samples_total": int(data.get("n_samples_total", 0)),
        "s0_global": s0_derived,
        "s1_full": s1_derived,
        "s3_triad": s3_derived,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_tree, f, indent=2)

    logger.info(f"🎉 Árbol multiescala derivado generado exitosamente en {OUTPUT_PATH}")
    logger.info(f"   Celdas L3: {len(s3_derived)} | Celdas L6: {len(s1_derived)}")


if __name__ == "__main__":
    main()
