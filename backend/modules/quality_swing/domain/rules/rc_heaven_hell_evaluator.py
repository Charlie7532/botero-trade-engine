"""
Heaven vs Hell Bifurcation Evaluator — Pure Domain Rule
=========================================================
Carga rc_scientific_fact_table.json (Regla 21) y evalúa en tiempo real:
  1. Esperanza Neta Ponderada E[R_net] = P(cielo)*E[R_cielo] - P(infierno)*|E[R_infierno]|
  2. Varianza Estocástica (σ^2) e Índice de Certidumbre Ω = 1 / σ^2
  3. Matriz de Decisión de Bifurcación:
     - AUMENTAR / SOSTENER: E[R_net] > 0 y Ω es alto.
     - SALIDA SÚBITA: E[R_net] < -0.02 o Señal Canario en VIX.
     - OBSERVACIÓN ADICIONAL: Alta varianza / incertidumbre (Ω bajo).

Clean Architecture: Módulo de dominio puro. Carga JSON una sola vez. Sin IO post-init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_FACT_TABLE: Optional[dict] = None
_FACT_PATH = Path(__file__).parent / "rc_scientific_fact_table.json"


@dataclass(frozen=True)
class BifurcationEvaluation:
    """Resultado de la Evaluación Ponderada Cielo vs Infierno."""
    state_key: str
    n_samples: int
    p_cielo: float
    p_infierno: float
    ev_net: float
    variance: float
    sharpe: float
    certitude_index_omega: float
    rr_asymmetry: float
    recommended_action: str  # "AUMENTAR_SOSTENER", "OBSERVACION_ADICIONAL", "SALIDA_SUBITA"
    kelly_allocation_factor: float


def _load_fact_table() -> dict:
    global _FACT_TABLE
    if _FACT_TABLE is None:
        if not _FACT_PATH.exists():
            raise FileNotFoundError(f"No se encontró la Tabla Fact Científica en {_FACT_PATH}")
        with open(_FACT_PATH, "r", encoding="utf-8") as f:
            _FACT_TABLE = json.load(f)
    return _FACT_TABLE


def evaluate_bifurcation_node(
    t_slope: float,
    c_slope: float,
    svw: float,
    vix: float = 20.0,
    svw_vel: float = 0.0
) -> BifurcationEvaluation:
    """Evalúa la bifurcación Cielo vs Infierno en tiempo real."""
    data = _load_fact_table()
    fact_entries: Dict[str, dict] = data.get("fact_entries", {})

    t_bin = "T+" if t_slope >= 0.05 else ("T-" if t_slope <= -0.05 else "T0")
    c_bin = "C+" if c_slope >= 0.05 else ("C-" if c_slope <= -0.05 else "C0")
    vw_bin = ">>" if svw >= 1.50 else ("<<" if svw <= -1.50 else "~")

    state_key = f"{t_bin}|{c_bin}|{vw_bin}"

    entry = fact_entries.get(state_key)
    if not entry:
        # Fallback a L2 (T | C)
        fallback_key = f"{t_bin}|{c_bin}|~"
        entry = fact_entries.get(fallback_key, {
            "n_samples": 30,
            "p_cielo": 0.50,
            "p_infierno": 0.50,
            "ev_net": 0.0,
            "variance": 0.01,
            "sharpe": 0.0,
            "certitude_index_omega": 100.0,
            "rr_asymmetry": 1.0,
        })

    p_cielo = entry["p_cielo"]
    p_infierno = entry["p_infierno"]
    ev_net = entry["ev_net"]
    variance = entry["variance"]
    omega = entry["certitude_index_omega"]
    rr_asymmetry = entry["rr_asymmetry"]
    n_samples = entry["n_samples"]
    sharpe = entry["sharpe"]

    # ── DETECCIÓN DE LA SEÑAL CANARIO (Disrupción Cinemática en VWAP + VIX) ──
    is_canary_disruption = (svw_vel <= -1.50 or vix >= 28.0) and (t_slope < 0.0)

    # ── ALOCACIÓN DE KELLY CONTINUA PONDERADA POR CERTIDUMBRE Ω ──
    kelly_allocation_factor = max(min(ev_net / (variance + 1e-4), 2.0), -1.0)

    # ── MATRIZ OPERATIVA DE DECISIÓN "CIELO VS INFIERNO" ──
    if is_canary_disruption or (ev_net < -0.02 and p_infierno >= 0.60):
        action = "SALIDA_SUBITA"
    elif ev_net > 0.01 and omega >= 20.0 and p_cielo >= 0.50:
        action = "AUMENTAR_SOSTENER"
    else:
        action = "OBSERVACION_ADICIONAL"

    return BifurcationEvaluation(
        state_key=state_key,
        n_samples=n_samples,
        p_cielo=p_cielo,
        p_infierno=p_infierno,
        ev_net=ev_net,
        variance=variance,
        sharpe=sharpe,
        certitude_index_omega=omega,
        rr_asymmetry=rr_asymmetry,
        recommended_action=action,
        kelly_allocation_factor=round(kelly_allocation_factor, 2)
    )
