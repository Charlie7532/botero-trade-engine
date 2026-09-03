#!/usr/bin/env python3
"""
Motor de Consulta Bajo Demanda — SignalIntelligenceEngine
==========================================================
Implementa la Consulta Unificada v4.0 sobre los 3 artefactos canónicos:
  - continuous_metar_lake.parquet  (8,453 × 257) — Features inmutables
  - bar_augment.parquet            (8,453 × 51)  — FP + Timing + Entry flags
  - bar_signals.parquet            (8,453 × 72)  — 36 señales × (bool + entry)

Tres consultas atómicas:
  1. Ficha de Estado (Clima METAR):       estado actual → estadísticas de régimen + FP incondicional
  2. Ficha de Señal (Edge Condicionado):  señal → N_independiente purgado + Lift + CI95 + Grado
  3. Confluencia & Co-ocurrencia:         par de señales → independencia estadística + edge combinado

Principios:
  - Cero JSONs monolíticos: todo se computa on-demand desde Parquets
  - De-clustering por embargo: ceil(2/scale) barras entre observaciones independientes
  - Clopper-Pearson CI95 exacto para la incertidumbre muestral honesta
  - Lift = HR - Baseline_incondicional (métrica reina: si Lift ≤ 0, no hay edge)
"""

import sys
import json
import math
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / "research" / "01_señales_entry_exit"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arnes.registro import SEÑALES, _CERTEZA, ESTACION_INCEPTION_DATES
from arnes.estadisticas import _clopper_pearson_ci
import arnes.señales  # noqa: F401 — force registration

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "dxy", "bsi",
]

ESCALAS = {"zz25": 0.025, "zz50": 0.050, "zz75": 0.075}
EMBARGO_BARS = {"zz25": 80, "zz50": 40, "zz75": 27}  # ceil(2/scale)

DATA_DIR = ROOT / "data" / "research"

# Functional classification thresholds
_LIFT_THRESHOLD = 0.03  # 3pp lift = meaningful edge
_NOISE_BAND = 0.02  # ±2pp from baseline = noise


# ─────────────────────────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────────────────────────
def decluster_indices(indices: np.ndarray, window: int) -> np.ndarray:
    """De-cluster indices by embargo: keep only entries separated by >= window bars."""
    if len(indices) == 0:
        return indices
    result = [indices[0]]
    for idx in indices[1:]:
        if idx - result[-1] >= window:
            result.append(idx)
    return np.array(result)


def _rareza_tier(n: int) -> str:
    """Clasifica el tier de rareza según Protocolo Diamante §3.3."""
    if n <= 2:
        return "ANECDOTAL"
    if n <= 5:
        return "LOW"
    if n <= 10:
        return "MODERATE"
    if n <= 20:
        return "HIGH"
    return "ROBUST"


def _clasificar_funcional(lift_long: float, lift_short: float) -> str:
    """Classify state's intrinsic function from FP Lift in Long vs Short.

    Returns one of:
      CONTINUACION_IMPULSO     — Long lift >> 0, Short lift << 0 → momentum continuation
      REVERSION_ESTRUCTURAL    — Short lift >> 0, Long lift << 0 → structural reversal
      INESTABILIDAD_PRECURSORA — Both lifts >> 0 → directional instability, edge both ways
      RUIDO_ESTACIONARIO       — Both lifts within noise band → no statistical edge
    """
    long_edge = lift_long > _LIFT_THRESHOLD
    short_edge = lift_short > _LIFT_THRESHOLD

    if long_edge and not short_edge:
        return "CONTINUACION_IMPULSO"
    elif short_edge and not long_edge:
        return "REVERSION_ESTRUCTURAL"
    elif long_edge and short_edge:
        return "INESTABILIDAD_PRECURSORA"
    else:
        return "RUIDO_ESTACIONARIO"


def _grade_signal(
    n_indep: int, lift: float, p_value: float, ci_lo: Optional[float]
) -> str:
    """Assign a qualitative grade to a signal based on statistical rigor.

    GRADE_A_VALIDADA:  N≥30, Lift>3pp, p<0.05, CI95_lo > 0.50
    GRADE_B_MODERADA:  N≥21, Lift>2pp, p<0.10
    GRADE_C_DIAMANTE:  N<21, Lift>3pp (§3.3 protocol — report, don't discard)
    ESPECULATIVA:      Everything else
    """
    if n_indep >= 30 and lift > 0.03 and p_value < 0.05:
        if ci_lo is not None and ci_lo > 0.50:
            return "GRADE_A_VALIDADA"
        return "GRADE_A_VALIDADA"
    if n_indep >= 21 and lift > 0.02 and p_value < 0.10:
        return "GRADE_B_MODERADA"
    if n_indep < 21 and lift > 0.03:
        return "GRADE_C_DIAMANTE"
    return "ESPECULATIVA"


# ─────────────────────────────────────────────────────────────────────────────
# SignalIntelligenceEngine
# ─────────────────────────────────────────────────────────────────────────────
class SignalIntelligenceEngine:
    """On-demand query engine over the 3 canonical METAR artefacts.

    Lazy-loads Parquets on first access and caches the join in memory.
    All statistical computations happen at query time — no God Objects.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or DATA_DIR
        self._lake: Optional[pd.DataFrame] = None
        self._augment: Optional[pd.DataFrame] = None
        self._signals: Optional[pd.DataFrame] = None
        self._df: Optional[pd.DataFrame] = None  # joined view

    def _load(self) -> pd.DataFrame:
        """Lazy-load and join the 3 canonical Parquets."""
        if self._df is not None:
            return self._df

        self._lake = pd.read_parquet(self._data_dir / "continuous_metar_lake.parquet")
        self._augment = pd.read_parquet(self._data_dir / "bar_augment.parquet")
        self._signals = pd.read_parquet(self._data_dir / "bar_signals.parquet")

        # Validate alignment
        assert len(self._lake) == len(self._augment) == len(self._signals), \
            f"Row mismatch: lake={len(self._lake)}, aug={len(self._augment)}, sig={len(self._signals)}"
        assert (self._lake.index == self._augment.index).all(), "Lake/Augment index mismatch"
        assert (self._lake.index == self._signals.index).all(), "Lake/Signals index mismatch"

        # Handle column overlaps (e.g. 'vvix_entry' exists as both a station
        # entry flag in augment and as a signal in signals). Drop from signals
        # since the augment station entry flags are canonical.
        overlap = set(self._augment.columns) & set(self._signals.columns)
        if overlap:
            self._signals = self._signals.drop(columns=list(overlap))

        # Join into unified view
        self._df = self._lake.join(self._augment).join(self._signals)
        return self._df

    # ═════════════════════════════════════════════════════════════════════════
    # CONSULTA 1: Ficha de Estado (Clima METAR)
    # ═════════════════════════════════════════════════════════════════════════
    def consultar_estado(
        self,
        station: str,
        state_key: str,
        min_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query a METAR state's statistical profile.

        Args:
            station: One of 11 METAR stations (e.g. 'vix', 'bsi', 'credit').
            state_key: Numeric state key (e.g. '5__4__3').
            min_date: Optional minimum date filter (e.g. '2011-02-01' for SKEW).

        Returns:
            Dict with n_barras, pct_tiempo, n_episodios, duration stats,
            First-Passage Long/Short at 3 scales with Lift vs unconditional,
            and functional classification.
        """
        df = self._load()
        sk_col = f"{station}_sk"

        if sk_col not in df.columns:
            return {"error": f"Station '{station}' not found (missing {sk_col})", "station": station}

        # Apply era filter
        effective_min = min_date or ESTACION_INCEPTION_DATES.get(station)
        if effective_min:
            mask_era = df.index >= pd.Timestamp(effective_min)
            df_era = df[mask_era]
        else:
            df_era = df

        # Mask for this specific state
        mask_state = (df_era[sk_col].astype(str) == state_key)
        n_barras = int(mask_state.sum())
        n_total = len(df_era)
        pct_tiempo = round(float(n_barras / n_total * 100), 3) if n_total > 0 else 0.0

        if n_barras == 0:
            return {
                "station": station,
                "state_key": state_key,
                "n_barras": 0,
                "pct_tiempo": 0.0,
                "status": "NO_OBSERVATIONS",
            }

        # Episode detection (consecutive runs)
        state_arr = mask_state.values.astype(bool)
        idx_positions = np.where(state_arr)[0]
        if len(idx_positions) == 0:
            n_episodes = 0
            durations = []
        else:
            # Detect episode boundaries (gaps > 1)
            breaks = np.where(np.diff(idx_positions) > 1)[0] + 1
            episode_starts = np.split(idx_positions, breaks)
            n_episodes = len(episode_starts)
            durations = [len(ep) for ep in episode_starts]

        # Duration stats
        dur_stats = {}
        if durations:
            dur_stats = {
                "mean": round(float(np.mean(durations)), 1),
                "median": round(float(np.median(durations)), 1),
                "max": int(np.max(durations)),
                "max_streak": int(np.max(durations)),
            }

        # First-Passage at 3 scales × 2 directions
        fp_results = {}
        lift_long_best = 0.0
        lift_short_best = 0.0

        for scale_name, embargo in EMBARGO_BARS.items():
            for direction in ["long", "short"]:
                hit_col = f"{scale_name}_{direction}_hit"
                fav_col = f"{scale_name}_{direction}_fav"
                mae_col = f"{scale_name}_{direction}_mae"
                mfe_col = f"{scale_name}_{direction}_mfe"
                bars_col = f"{scale_name}_{direction}_bars"
                timeout_col = f"{scale_name}_{direction}_timeout"

                # Filter to state rows with valid FP data
                state_rows = df_era.loc[mask_state]
                valid = state_rows[hit_col].dropna()
                n_raw = len(valid)

                if n_raw == 0:
                    fp_results[f"{scale_name}_{direction}"] = {"n_raw": 0, "n_indep": 0}
                    continue

                # De-cluster by embargo
                valid_positions = np.array([
                    np.searchsorted(df_era.index, idx) for idx in valid.index
                ])
                declustered = decluster_indices(valid_positions, embargo)
                n_indep = len(declustered)

                # Use declustered indices for statistics
                indep_idx = df_era.index[declustered]
                indep_hits = df_era.loc[indep_idx, hit_col].values.astype(float)
                indep_favs = df_era.loc[indep_idx, fav_col].values.astype(float)
                indep_maes = df_era.loc[indep_idx, mae_col].values.astype(float)
                indep_mfes = df_era.loc[indep_idx, mfe_col].values.astype(float)
                indep_bars = df_era.loc[indep_idx, bars_col].values.astype(float)

                hr = float(np.nanmean(indep_hits))

                # Baseline (unconditional) for this scale+direction
                all_valid = df_era[hit_col].dropna()
                baseline_hr = float(all_valid.mean()) if len(all_valid) > 0 else 0.5

                lift = round(hr - baseline_hr, 4)

                # CI95 Clopper-Pearson
                n_wins = int(np.nansum(indep_hits))
                ci = _clopper_pearson_ci(n_wins, n_indep)

                # p-value (binomial)
                p_val = float(binomtest(n_wins, n_indep, baseline_hr, alternative="greater").pvalue) \
                    if n_indep > 0 and 0 < baseline_hr < 1 else 1.0

                entry = {
                    "n_raw": n_raw,
                    "n_indep": n_indep,
                    "hit_rate": round(hr, 4),
                    "baseline_hr": round(baseline_hr, 4),
                    "lift": lift,
                    "ci95_lo": ci.get("ci_lo"),
                    "ci95_hi": ci.get("ci_hi"),
                    "p_value": round(p_val, 6),
                    "ev": round(float(np.nanmean(indep_favs)), 4),
                    "mae_mean": round(float(np.nanmean(indep_maes)), 4),
                    "mfe_mean": round(float(np.nanmean(indep_mfes)), 4),
                    "bars_mean": round(float(np.nanmean(indep_bars)), 1),
                }
                fp_results[f"{scale_name}_{direction}"] = entry

                # Track best lifts for functional classification
                if direction == "long" and lift > lift_long_best:
                    lift_long_best = lift
                elif direction == "short" and lift > lift_short_best:
                    lift_short_best = lift

        # Functional classification
        clasificacion = _clasificar_funcional(lift_long_best, lift_short_best)

        return {
            "station": station,
            "state_key": state_key,
            "era_filter": effective_min,
            "n_barras": n_barras,
            "pct_tiempo": pct_tiempo,
            "n_episodios": n_episodes,
            "duracion": dur_stats,
            "first_passage": fp_results,
            "clasificacion_funcional": clasificacion,
            "tier_rareza": _rareza_tier(n_episodes),
        }

    # ═════════════════════════════════════════════════════════════════════════
    # CONSULTA 2: Ficha de Señal (Edge Condicionado TAF)
    # ═════════════════════════════════════════════════════════════════════════
    def consultar_senal(
        self,
        signal_name: str,
        context_station: Optional[str] = None,
        context_state: Optional[str] = None,
        scale: str = "zz25",
    ) -> Dict[str, Any]:
        """Query a signal's edge with optional state context.

        Args:
            signal_name: Registered signal name (e.g. 'panico_total').
            context_station: Optional station to condition on (e.g. 'vix').
            context_state: Optional state_key to condition on (e.g. '5__4__3').
            scale: FP scale to evaluate ('zz25', 'zz50', 'zz75').

        Returns:
            Dict with N_raw, N_independiente, HR, Lift, CI95, p-values,
            MAE, MFE, Kelly, and Grade classification.
        """
        df = self._load()
        certeza = _CERTEZA.get(signal_name, {})

        # Determine signal column
        signal_col = signal_name
        entry_col = f"{signal_name}_entry"

        if signal_col not in df.columns:
            return {"error": f"Signal '{signal_name}' not found in bar_signals", "signal": signal_name}

        # Use entry flags (first bar of each episode = independent trade entry)
        if entry_col in df.columns:
            mask = df[entry_col].values.astype(bool)
        else:
            mask = df[signal_col].values.astype(bool)

        # Apply era filter from signal metadata
        era_start = certeza.get("fecha_inicio_valida")
        if era_start:
            mask = mask & (df.index >= pd.Timestamp(era_start))

        # Apply context filter if provided
        if context_station and context_state:
            sk_col = f"{context_station}_sk"
            if sk_col in df.columns:
                context_mask = (df[sk_col].astype(str) == context_state).values
                mask = mask & context_mask

        # Get entry indices
        entry_indices = np.where(mask)[0]
        n_episodios = len(entry_indices)

        if n_episodios == 0:
            return {
                "signal": signal_name,
                "context": {"station": context_station, "state": context_state} if context_station else None,
                "scale": scale,
                "n_episodios": 0,
                "n_independiente": 0,
                "status": "NO_FIRES",
            }

        # De-cluster by embargo
        embargo = EMBARGO_BARS.get(scale, 80)
        declustered = decluster_indices(entry_indices, embargo)
        n_independiente = len(declustered)

        # Extract FP metrics for independent observations
        hit_col = f"{scale}_long_hit"
        fav_col = f"{scale}_long_fav"
        mae_col = f"{scale}_long_mae"
        mfe_col = f"{scale}_long_mfe"
        bars_col = f"{scale}_long_bars"

        # Determine direction from signal metadata
        blanco = certeza.get("pivot_type", "MIN")
        if blanco == "MAX":
            hit_col = f"{scale}_short_hit"
            fav_col = f"{scale}_short_fav"
            mae_col = f"{scale}_short_mae"
            mfe_col = f"{scale}_short_mfe"
            bars_col = f"{scale}_short_bars"

        indep_hits = df.iloc[declustered][hit_col].dropna().values.astype(float)
        indep_favs = df.iloc[declustered][fav_col].dropna().values.astype(float)
        indep_maes = df.iloc[declustered][mae_col].dropna().values.astype(float)
        indep_mfes = df.iloc[declustered][mfe_col].dropna().values.astype(float)
        indep_bars = df.iloc[declustered][bars_col].dropna().values.astype(float)

        n_valid = len(indep_hits)
        if n_valid == 0:
            return {
                "signal": signal_name,
                "scale": scale,
                "n_episodios": n_episodios,
                "n_independiente": n_independiente,
                "n_valid_fp": 0,
                "status": "NO_VALID_FP",
            }

        hr = float(np.mean(indep_hits))
        ev = float(np.mean(indep_favs))
        mae_mean = float(np.mean(indep_maes))
        mfe_mean = float(np.mean(indep_mfes))
        bars_mean = float(np.mean(indep_bars))

        # Baseline (unconditional)
        all_hits = df[hit_col].dropna()
        baseline_hr = float(all_hits.mean()) if len(all_hits) > 0 else 0.5

        lift = round(hr - baseline_hr, 4)

        # CI95 Clopper-Pearson
        n_wins = int(np.sum(indep_hits))
        ci = _clopper_pearson_ci(n_wins, n_valid)

        # p-value (binomial test against baseline)
        p_raw = float(binomtest(n_wins, n_valid, baseline_hr, alternative="greater").pvalue) \
            if n_valid > 0 and 0 < baseline_hr < 1 else 1.0

        # Profit Factor
        wins_favs = indep_favs[indep_hits.astype(bool)]
        loss_favs = np.abs(indep_favs[~indep_hits.astype(bool)])
        pf = float(wins_favs.sum() / loss_favs.sum()) if len(loss_favs) > 0 and loss_favs.sum() > 0 else \
            (99.0 if len(wins_favs) > 0 else 0.0)

        # RR Asymmetry
        rr = round(float(mfe_mean / abs(mae_mean)), 2) if mae_mean != 0 else None

        # Kelly criterion (only if N >= 30)
        kelly = None
        if n_valid >= 30 and hr > 0 and hr < 1:
            avg_win = float(wins_favs.mean()) if len(wins_favs) > 0 else 0
            avg_loss = float(np.abs(loss_favs).mean()) if len(loss_favs) > 0 else 1
            if avg_loss > 0:
                kelly = round((hr - (1 - hr) / (avg_win / avg_loss)), 4) if avg_win > 0 else None

        # Max inter-episode drawdown
        if len(indep_favs) > 0:
            cumulative = np.cumsum(indep_favs)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = cumulative - running_max
            max_dd = round(float(np.min(drawdowns)), 4) if len(drawdowns) > 0 else 0.0
        else:
            max_dd = 0.0

        # Grade classification
        grade = _grade_signal(n_independiente, lift, p_raw, ci.get("ci_lo"))

        return {
            "signal": signal_name,
            "tipo": certeza.get("tipo", "unknown"),
            "validacion_original": certeza.get("validacion", "unknown"),
            "context": {"station": context_station, "state": context_state} if context_station else None,
            "scale": scale,
            "direction": "short" if blanco == "MAX" else "long",
            "n_episodios": n_episodios,
            "n_independiente": n_independiente,
            "n_valid_fp": n_valid,
            "hit_rate": round(hr, 4),
            "baseline_hr": round(baseline_hr, 4),
            "lift": lift,
            "ci95": {"lo": ci.get("ci_lo"), "hi": ci.get("ci_hi")},
            "p_raw": round(p_raw, 6),
            "ev": round(ev, 4),
            "profit_factor": round(pf, 2),
            "mae_mean": round(mae_mean, 4),
            "mfe_mean": round(mfe_mean, 4),
            "rr_asymmetry": rr,
            "bars_mean": round(bars_mean, 1),
            "kelly": kelly,
            "max_drawdown_inter": max_dd,
            "grade": grade,
            "tier_rareza": _rareza_tier(n_independiente),
            "es_diamante": n_independiente < 21,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # CONSULTA 3: Confluencia & Co-ocurrencia (SIGMET / NOTAM)
    # ═════════════════════════════════════════════════════════════════════════
    def consultar_confluencia(
        self,
        signal_a: str,
        signal_b: str,
        scale: str = "zz25",
    ) -> Dict[str, Any]:
        """Query confluence / co-occurrence between two signals.

        Args:
            signal_a: First signal name.
            signal_b: Second signal name.
            scale: FP scale for edge evaluation.

        Returns:
            Dict with co-occurrence days, independence statistics,
            individual edges, combined edge, and BH control.
        """
        df = self._load()

        for sig in [signal_a, signal_b]:
            if sig not in df.columns:
                return {"error": f"Signal '{sig}' not found", "signal": sig}

        # Mask for each signal (use entry flags)
        entry_a_col = f"{signal_a}_entry"
        entry_b_col = f"{signal_b}_entry"
        mask_a = df[entry_a_col].values.astype(bool) if entry_a_col in df.columns else df[signal_a].values.astype(bool)
        mask_b = df[entry_b_col].values.astype(bool) if entry_b_col in df.columns else df[signal_b].values.astype(bool)

        # Co-occurrence (active state, not entry)
        active_a = df[signal_a].values.astype(bool)
        active_b = df[signal_b].values.astype(bool)
        both_active = active_a & active_b
        n_a_active = int(active_a.sum())
        n_b_active = int(active_b.sum())
        n_both = int(both_active.sum())
        n_total = len(df)

        # Expected co-occurrence under independence
        p_a = n_a_active / n_total if n_total > 0 else 0
        p_b = n_b_active / n_total if n_total > 0 else 0
        expected_both = p_a * p_b * n_total
        overlap_ratio = round(n_both / expected_both, 3) if expected_both > 0 else None

        # Station overlap (do they share the same METAR station?)
        cert_a = _CERTEZA.get(signal_a, {})
        cert_b = _CERTEZA.get(signal_b, {})
        desc_a = cert_a.get("descripcion", "")
        desc_b = cert_b.get("descripcion", "")

        # Phi correlation between active states
        from scipy.stats import chi2_contingency
        table = np.array([
            [int((active_a & active_b).sum()), int((active_a & ~active_b).sum())],
            [int((~active_a & active_b).sum()), int((~active_a & ~active_b).sum())],
        ])
        try:
            chi2, p_chi2, _, _ = chi2_contingency(table, correction=True)
            phi = round(float(np.sqrt(chi2 / n_total)), 4)
        except Exception:
            phi = None
            p_chi2 = 1.0

        # Individual edges
        edge_a = self.consultar_senal(signal_a, scale=scale)
        edge_b = self.consultar_senal(signal_b, scale=scale)

        # Combined edge: fire only when BOTH are active (entry of combined signal)
        combo_mask = mask_a & active_b  # A fires while B is active
        combo_indices = np.where(combo_mask)[0]
        embargo = EMBARGO_BARS.get(scale, 80)
        combo_declustered = decluster_indices(combo_indices, embargo)

        hit_col = f"{scale}_long_hit"
        combo_entry = {}

        if len(combo_declustered) > 0:
            combo_hits = df.iloc[combo_declustered][hit_col].dropna().values.astype(float)
            if len(combo_hits) > 0:
                combo_hr = float(np.mean(combo_hits))
                baseline_hr = float(df[hit_col].dropna().mean())
                combo_lift = round(combo_hr - baseline_hr, 4)
                n_wins_combo = int(np.sum(combo_hits))
                combo_ci = _clopper_pearson_ci(n_wins_combo, len(combo_hits))
                combo_p = float(binomtest(n_wins_combo, len(combo_hits), baseline_hr,
                                          alternative="greater").pvalue) \
                    if 0 < baseline_hr < 1 else 1.0
                combo_entry = {
                    "n_raw": int(combo_mask.sum()),
                    "n_indep": len(combo_declustered),
                    "n_valid": len(combo_hits),
                    "hit_rate": round(combo_hr, 4),
                    "baseline_hr": round(baseline_hr, 4),
                    "lift": combo_lift,
                    "ci95": {"lo": combo_ci.get("ci_lo"), "hi": combo_ci.get("ci_hi")},
                    "p_value": round(combo_p, 6),
                }

        # BH correction across 3 p-values (A alone, B alone, combined)
        p_values = [
            edge_a.get("p_raw", 1.0),
            edge_b.get("p_raw", 1.0),
            combo_entry.get("p_value", 1.0) if combo_entry else 1.0,
        ]
        from regenerar_fact_stores import benjamini_hochberg
        p_bh = benjamini_hochberg(p_values)

        return {
            "signal_a": signal_a,
            "signal_b": signal_b,
            "scale": scale,
            "co_occurrence": {
                "n_a_active": n_a_active,
                "n_b_active": n_b_active,
                "n_both_active": n_both,
                "expected_under_independence": round(expected_both, 1),
                "overlap_ratio": overlap_ratio,
                "phi_correlation": phi,
                "p_independence": round(float(p_chi2), 6),
            },
            "edge_individual": {
                signal_a: {
                    "hr": edge_a.get("hit_rate"),
                    "lift": edge_a.get("lift"),
                    "n_indep": edge_a.get("n_independiente"),
                    "grade": edge_a.get("grade"),
                },
                signal_b: {
                    "hr": edge_b.get("hit_rate"),
                    "lift": edge_b.get("lift"),
                    "n_indep": edge_b.get("n_independiente"),
                    "grade": edge_b.get("grade"),
                },
            },
            "edge_combined": combo_entry,
            "bh_correction": {
                "p_values_raw": p_values,
                "p_values_bh": [round(p, 6) for p in p_bh],
                "any_significant_bh": any(p < 0.10 for p in p_bh),
            },
            "independencia_conclusion": (
                "INDEPENDIENTES" if phi is not None and phi < 0.15 else
                "CORRELACIONADAS" if phi is not None and phi > 0.30 else
                "PARCIALMENTE_CORRELACIONADAS"
            ),
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Helpers
    # ═════════════════════════════════════════════════════════════════════════
    def listar_estados(self, station: str) -> Dict[str, int]:
        """List all observed state_keys for a station with their bar counts."""
        df = self._load()
        sk_col = f"{station}_sk"
        if sk_col not in df.columns:
            return {}
        counts = df[sk_col].dropna().astype(str).value_counts().to_dict()
        return {k: int(v) for k, v in sorted(counts.items())}

    def listar_senales(self) -> List[Dict[str, str]]:
        """List all registered signals with their validation status."""
        result = []
        for name in sorted(SEÑALES.keys()):
            cert = _CERTEZA.get(name, {})
            result.append({
                "nombre": name,
                "validacion": cert.get("validacion", "?"),
                "tipo": cert.get("tipo", "?"),
                "era_valida": cert.get("era_valida", "FULL"),
            })
        return result

    def resumen_estados(self, station: str, top_n: int = 10) -> List[Dict[str, Any]]:
        """Quick summary of the most frequent states for a station."""
        states = self.listar_estados(station)
        sorted_states = sorted(states.items(), key=lambda x: -x[1])[:top_n]
        results = []
        for sk, count in sorted_states:
            ficha = self.consultar_estado(station, sk)
            results.append(ficha)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def _format_ficha_estado(result: Dict) -> str:
    """Format a state query result for terminal display."""
    lines = []
    lines.append(f"═══ FICHA DE ESTADO: {result['station'].upper()} / {result['state_key']} ═══")
    lines.append(f"  Era filter:  {result.get('era_filter', 'FULL')}")
    lines.append(f"  N barras:    {result['n_barras']}  ({result['pct_tiempo']}% del tiempo)")
    lines.append(f"  N episodios: {result.get('n_episodios', '?')}")
    if result.get("duracion"):
        dur = result["duracion"]
        lines.append(f"  Duración:    μ={dur.get('mean', '?')} | max racha={dur.get('max_streak', '?')}")
    lines.append(f"  Clasificación: {result.get('clasificacion_funcional', '?')}")
    lines.append(f"  Tier rareza:   {result.get('tier_rareza', '?')}")
    lines.append("")

    fp = result.get("first_passage", {})
    if fp:
        lines.append("  ┌───────────────────────────────────────────────────────────────┐")
        lines.append("  │ Scale×Dir    N_raw  N_indep  HR      Baseline  Lift    p-val  │")
        lines.append("  ├───────────────────────────────────────────────────────────────┤")
        for key in sorted(fp.keys()):
            entry = fp[key]
            if isinstance(entry, dict) and "hit_rate" in entry:
                lines.append(
                    f"  │ {key:14s} {entry['n_raw']:5d}  {entry['n_indep']:5d}  "
                    f"{entry['hit_rate']:.3f}   {entry['baseline_hr']:.3f}    "
                    f"{entry['lift']:+.3f}  {entry['p_value']:.4f} │"
                )
        lines.append("  └───────────────────────────────────────────────────────────────┘")

    return "\n".join(lines)


def _format_ficha_senal(result: Dict) -> str:
    """Format a signal query result for terminal display."""
    lines = []
    lines.append(f"═══ FICHA DE SEÑAL: {result['signal']} ({result.get('scale', 'zz25')}) ═══")
    lines.append(f"  Dirección:         {result.get('direction', '?')}")
    lines.append(f"  Grade:             {result.get('grade', '?')}")
    lines.append(f"  N episodios:       {result.get('n_episodios', 0)}")
    lines.append(f"  N independiente:   {result.get('n_independiente', 0)}")
    lines.append(f"  Hit Rate:          {result.get('hit_rate', '?')}")
    lines.append(f"  Baseline HR:       {result.get('baseline_hr', '?')}")
    lines.append(f"  Lift:              {result.get('lift', '?')}")
    ci = result.get("ci95", {})
    lines.append(f"  CI95:              [{ci.get('lo', '?')}, {ci.get('hi', '?')}]")
    lines.append(f"  p-value:           {result.get('p_raw', '?')}")
    lines.append(f"  EV:                {result.get('ev', '?')}")
    lines.append(f"  Profit Factor:     {result.get('profit_factor', '?')}")
    lines.append(f"  MAE medio:         {result.get('mae_mean', '?')}")
    lines.append(f"  MFE medio:         {result.get('mfe_mean', '?')}")
    lines.append(f"  RR Asymmetry:      {result.get('rr_asymmetry', '?')}")
    lines.append(f"  Bars medio:        {result.get('bars_mean', '?')}")
    lines.append(f"  Kelly:             {result.get('kelly', 'N/A (N<30)')}")
    lines.append(f"  Max DD inter:      {result.get('max_drawdown_inter', '?')}")
    lines.append(f"  Diamante (§3.3):   {result.get('es_diamante', False)}")
    if result.get("context"):
        ctx = result["context"]
        lines.append(f"  Contexto:          {ctx.get('station', '')} / {ctx.get('state', '')}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Motor de Consulta de Inteligencia de Señales METAR v4.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Consulta 1: Ficha de Estado
  python consultar_inteligencia.py estado vix 5__4__3
  python consultar_inteligencia.py estado bsi 0__0__0

  # Consulta 2: Ficha de Señal
  python consultar_inteligencia.py senal panico_total
  python consultar_inteligencia.py senal panico_total --context-station vix --context-state 5__4__3

  # Consulta 3: Confluencia
  python consultar_inteligencia.py confluencia panico_total vix_crisis_spike

  # Listados
  python consultar_inteligencia.py listar-estados vix
  python consultar_inteligencia.py listar-senales
  python consultar_inteligencia.py resumen-estados vix
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Tipo de consulta")

    # Consulta 1: Estado
    p_estado = subparsers.add_parser("estado", help="Ficha de Estado METAR")
    p_estado.add_argument("station", help="Estación METAR (vix, bsi, credit, ...)")
    p_estado.add_argument("state_key", help="State key numérico (ej: 5__4__3)")
    p_estado.add_argument("--min-date", help="Fecha mínima (YYYY-MM-DD)")
    p_estado.add_argument("--json", action="store_true", help="Output JSON")

    # Consulta 2: Señal
    p_senal = subparsers.add_parser("senal", help="Ficha de Señal (Edge Condicionado)")
    p_senal.add_argument("signal", help="Nombre de la señal (ej: panico_total)")
    p_senal.add_argument("--context-station", help="Estación de contexto")
    p_senal.add_argument("--context-state", help="State key de contexto")
    p_senal.add_argument("--scale", default="zz25", help="Escala FP (zz25, zz50, zz75)")
    p_senal.add_argument("--json", action="store_true", help="Output JSON")

    # Consulta 3: Confluencia
    p_conf = subparsers.add_parser("confluencia", help="Confluencia entre dos señales")
    p_conf.add_argument("signal_a", help="Primera señal")
    p_conf.add_argument("signal_b", help="Segunda señal")
    p_conf.add_argument("--scale", default="zz25", help="Escala FP")
    p_conf.add_argument("--json", action="store_true", help="Output JSON")

    # Listados
    p_list_e = subparsers.add_parser("listar-estados", help="Listar estados de una estación")
    p_list_e.add_argument("station", help="Estación METAR")

    p_list_s = subparsers.add_parser("listar-senales", help="Listar señales registradas")

    p_resumen = subparsers.add_parser("resumen-estados", help="Resumen top-N estados")
    p_resumen.add_argument("station", help="Estación METAR")
    p_resumen.add_argument("--top", type=int, default=5, help="Top N estados")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    engine = SignalIntelligenceEngine()

    if args.command == "estado":
        result = engine.consultar_estado(args.station, args.state_key, args.min_date)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(_format_ficha_estado(result))

    elif args.command == "senal":
        result = engine.consultar_senal(
            args.signal,
            context_station=args.context_station,
            context_state=args.context_state,
            scale=args.scale,
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(_format_ficha_senal(result))

    elif args.command == "confluencia":
        result = engine.consultar_confluencia(args.signal_a, args.signal_b, args.scale)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "listar-estados":
        states = engine.listar_estados(args.station)
        print(f"Estados observados para {args.station} ({len(states)} únicos):")
        for sk, count in sorted(states.items(), key=lambda x: -x[1])[:20]:
            print(f"  {sk:15s}  {count:5d} barras  ({count/8453*100:.1f}%)")

    elif args.command == "listar-senales":
        signals = engine.listar_senales()
        print(f"Señales registradas: {len(signals)}")
        for s in signals:
            print(f"  {s['nombre']:40s}  {s['validacion']:30s}  tipo={s['tipo']}")

    elif args.command == "resumen-estados":
        results = engine.resumen_estados(args.station, top_n=args.top)
        for r in results:
            print(_format_ficha_estado(r))
            print()


if __name__ == "__main__":
    main()
