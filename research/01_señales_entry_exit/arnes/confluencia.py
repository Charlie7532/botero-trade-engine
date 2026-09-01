"""Confluencia de overflows — Panic y Euphoria Scores.

Extraído de research/_legacy/audit_vector_confluence.py.
Funciones puras deterministas para calcular scores de confluencia
basados en overflows ±2σ simultáneos de estaciones METAR.

Semántica:
  - Panic Score: conteo de dimensiones de estaciones "de miedo" en overflow positivo
    (VIX, VVIX, PCR, SV5_Turbulence ≥ +2σ) + estaciones "de confianza" en overflow
    negativo (FG, BSI, Credit, Rotation ≤ -2σ).
  - Euphoria Score: conteo de estaciones "de confianza" en overflow positivo
    (FG, BSI, Rotation ≥ +2σ) + estaciones "de miedo" en overflow negativo
    (VIX, PCR ≤ -2σ).
"""
from typing import Optional
import numpy as np
import pandas as pd


# Estaciones cuyo overflow POSITIVO (+2σ) indica pánico / estrés de mercado
PANIC_POSITIVE_STATIONS = {"vix", "vvix", "pcr", "sv5_turbulence", "skew", "dxy"}

# Estaciones cuyo overflow POSITIVO (+2σ) indica euforia / complacencia
EUPHORIA_POSITIVE_STATIONS = {"fg", "bsi", "rotation"}

# Estaciones cuyo overflow NEGATIVO (-2σ) indica pánico / contracción de liquidez
PANIC_NEGATIVE_STATIONS = {"fg", "bsi", "credit", "rotation", "yield_curve"}

# Estaciones cuyo overflow NEGATIVO (-2σ) indica euforia / complacencia extrema
EUPHORIA_NEGATIVE_STATIONS = {"vix", "pcr"}


def calcular_score_confluencia(
    z_mat: pd.DataFrame,
    sigma_threshold: float = 2.0,
    panic_pos: Optional[set[str]] = None,
    panic_neg: Optional[set[str]] = None,
    euphoria_pos: Optional[set[str]] = None,
    euphoria_neg: Optional[set[str]] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Calcula Panic Score y Euphoria Score: conteo de dimensiones en overflow simultáneo.

    Args:
        z_mat: DataFrame donde cada columna es '{station}.{dim}' (ej. 'vix.d1', 'pcr.d2')
               y cada fila es un día de trading. Valores son z-scores.
        sigma_threshold: Umbral de overflow (default 2.0σ).
        panic_pos: Conjunto opcional de estaciones para pánico positivo (default PANIC_POSITIVE_STATIONS).
        panic_neg: Conjunto opcional de estaciones para pánico negativo (default PANIC_NEGATIVE_STATIONS).
        euphoria_pos: Conjunto opcional de estaciones para euforia positiva (default EUPHORIA_POSITIVE_STATIONS).
        euphoria_neg: Conjunto opcional de estaciones para euforia negativa (default EUPHORIA_NEGATIVE_STATIONS).

    Returns:
        (panic_scores, euphoria_scores): Arrays de ints, longitud = len(z_mat).
        Cada valor es el conteo de dimensiones en overflow que contribuyen al score.
    """
    n = len(z_mat)
    panic_scores = np.zeros(n, dtype=int)
    euphoria_scores = np.zeros(n, dtype=int)

    p_pos = panic_pos if panic_pos is not None else PANIC_POSITIVE_STATIONS
    p_neg = panic_neg if panic_neg is not None else PANIC_NEGATIVE_STATIONS
    e_pos = euphoria_pos if euphoria_pos is not None else EUPHORIA_POSITIVE_STATIONS
    e_neg = euphoria_neg if euphoria_neg is not None else EUPHORIA_NEGATIVE_STATIONS

    for col in z_mat.columns:
        parts = col.split(".")
        if len(parts) != 2:
            continue
        st = parts[0]
        vals = z_mat[col].values
        pos = vals >= sigma_threshold
        neg = vals <= -sigma_threshold

        # Overflow positivo
        if st in p_pos:
            panic_scores += pos.astype(int)
        if st in e_pos:
            euphoria_scores += pos.astype(int)

        # Overflow negativo
        if st in p_neg:
            panic_scores += neg.astype(int)
        if st in e_neg:
            euphoria_scores += neg.astype(int)

    return panic_scores, euphoria_scores


def conteo_overflows_simultaneos(
    z_mat: pd.DataFrame,
    sigma_threshold: float = 2.0,
) -> np.ndarray:
    """Cuenta cuántas dimensiones están en overflow (≥ |threshold|σ) simultáneamente.

    Args:
        z_mat: DataFrame de z-scores '{station}.{dim}'.
        sigma_threshold: Umbral de overflow.

    Returns:
        Array de ints: conteo de dimensiones en overflow por día.
    """
    return (z_mat.abs() >= sigma_threshold).sum(axis=1).values
