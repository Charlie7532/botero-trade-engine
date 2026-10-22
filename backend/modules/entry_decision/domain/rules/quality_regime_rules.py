"""
QUALITY REGIME RULES — PURE DOMAIN RULES
========================================
Clean Architecture: Domain Layer (Pure Business Rules)
Module: entry_decision / domain / rules

Formal mathematical rules for the Quality Department Regime State Machine:
  1. Nested S5 x SV5 joint state classification (5x5x5 Gaussian sigma bins).
  2. Pre-Crash Antennas (Persistent volume inversion fi - v_fi < -5 for >= 10 bars,
     Divergent Leadership hot_tw <= 1 & cold_tw >= 7, Joint distribution states).
  3. Bullish Re-Absorption and Volume Capitulation Floors.
  4. V36 Calibrated Redirection & V40 SV5_Turbulence institutional crash detector.
  5. Deterministic transitions across all 8 market regimes.

Zero infrastructure dependencies. Zero side-effects. Fully deterministic.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class QualityRegimeRules:
    """
    Pure Domain Rule Engine for Quality Regime Transitions.
    Governs the canonical B0 baseline state machine (584.52 shares / -34.93% MaxDD T+0).
    """

    # Constantes de clasificación para el anidamiento conjunto S5xSV5
    S5_EDGES: Dict[str, List[float]] = {
        "TH": [27.6, 54.8, 82.8, 93.5],
        "FI": [20.0, 46.7, 76.9, 90.4],
        "TW": [16.7, 41.9, 75.0, 90.0],
    }
    SV5_EDGES: Dict[str, List[float]] = {
        "TH": [24.6, 37.2, 58.0, 73.8],
        "FI": [27.0, 37.8, 55.5, 68.4],
        "TW": [23.9, 34.5, 50.8, 65.4],
    }
    LABELS: List[str] = ["<<", "<", "~", ">", ">>"]

    # Estados de distribución optimizados (Subset 2: dirección '+')
    TOP_DISTRIBUTION_STATES: set = {
        "<<|<<|~|>>|>>|<|+",
        "<<|<<|<<|>>|>>|>>|+",
        "<<|<<|~|>>|>>|<<|+",
        "<<|<<|<<|>>|>>|>|+",
        ">>|>|>|<<|~|~|+",
        "<<|~|~|~|>|~|+",
        "<<|<<|<<|>|>>|>>|+",
    }

    @staticmethod
    def _load_turbulence_thresholds() -> Tuple[float, float, float]:
        """Dynamically load empirical thresholds from sv5_turbulence_fact_store.json (Rule 21).

        Returns:
            (crash_thresh, high_thresh, extreme_thresh) from fact store operational_thresholds.
            Explicitly declared fallback for offline/cold-start: (11.21, 8.82, 12.06).
        """
        DECLARED_FALLBACK = (11.21, 8.82, 12.06)
        fact_path = Path(__file__).resolve().parent / "sv5_turbulence_fact_store.json"
        try:
            if fact_path.exists():
                with open(fact_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                doc = data.get("_documentation", {})
                op_thresh = doc.get("operational_thresholds", {})
                if op_thresh:
                    crash_thresh = float(op_thresh.get("crash_threshold", DECLARED_FALLBACK[0]))
                    high_thresh = float(op_thresh.get("high_threshold", DECLARED_FALLBACK[1]))
                    extreme_thresh = float(op_thresh.get("extreme_threshold", DECLARED_FALLBACK[2]))
                    return crash_thresh, high_thresh, extreme_thresh

                edges = doc.get("taxonomy", {}).get("d1", {}).get("value_edges", [])
                if len(edges) >= 5:
                    crash_thresh = round(float(edges[3]), 2)
                    high_thresh = DECLARED_FALLBACK[1]
                    extreme_thresh = DECLARED_FALLBACK[2]
                    return crash_thresh, high_thresh, extreme_thresh
        except Exception:
            pass
        return DECLARED_FALLBACK

    _CRASH_TH, _HIGH_TH, _EXTREME_TH = _load_turbulence_thresholds.__func__()
    SV5_STD_VIX_CRASH_THRESHOLD: float = _CRASH_TH
    SV5_TURBULENCE_HIGH_THRESHOLD: float = _HIGH_TH
    SV5_TURBULENCE_EXTREME_THRESHOLD: float = _EXTREME_TH
    SV5_SHOCK_HIGH_THRESHOLD: float = _HIGH_TH
    SV5_SHOCK_EXTREME_THRESHOLD: float = _EXTREME_TH

    @classmethod
    def classify_bin(cls, v: float, edges: List[float]) -> str:
        for idx, e in enumerate(edges):
            if v < e:
                return cls.LABELS[idx]
        return cls.LABELS[-1]

    @classmethod
    def get_spy_joint_state(
        cls,
        th: float,
        fi: float,
        tw: float,
        tw_prev: float,
        v_th: float,
        v_fi: float,
        v_tw: float,
    ) -> str:
        s5_th_b = cls.classify_bin(th, cls.S5_EDGES["TH"])
        s5_fi_b = cls.classify_bin(fi, cls.S5_EDGES["FI"])
        s5_tw_b = cls.classify_bin(tw, cls.S5_EDGES["TW"])
        dir_b = "+" if tw > tw_prev else "-"
        sv5_th_b = cls.classify_bin(v_th, cls.SV5_EDGES["TH"])
        sv5_fi_b = cls.classify_bin(v_fi, cls.SV5_EDGES["FI"])
        sv5_tw_b = cls.classify_bin(v_tw, cls.SV5_EDGES["TW"])
        return f"{s5_th_b}|{s5_fi_b}|{s5_tw_b}|{sv5_th_b}|{sv5_fi_b}|{sv5_tw_b}|{dir_b}"

    @classmethod
    def evaluate_transition(
        cls,
        th: float,
        fi: float,
        tw: float,
        v_th: float,
        v_fi: float,
        v_tw: float,
        sec_th: Dict[str, float],
        sec_fi: Dict[str, float],
        sec_tw: Dict[str, float],
        sec_v_tw: Optional[Dict[str, float]] = None,
        fi_velocity: float = 0.0,
        current_mode: str = "NORMAL",
        days_in_mode: int = 25,
        tw_prev: Optional[float] = None,
        fgbi: Optional[float] = None,
        vbi: Optional[float] = None,
        fgbi_peak_15d: Optional[float] = None,
        vix: Optional[float] = None,
        sv5_turbulence: Optional[float] = None,
        sv5_shock: Optional[float] = None,
        min_regime_days: int = 20,
        dist_exit_confirm: int = 2,
        dist_exit_hyst: bool = True,
        inv_fi_streak: int = 0,
        exit_count: int = 0,
        fgbi_window: Optional[List[float]] = None,
        ratio_window: Optional[List[float]] = None,
    ) -> Tuple[str, int, int]:
        """
        Pure Domain Transition Function.
        Evaluates current market indicators against regime transition rules.

        Returns:
            (new_mode, updated_inv_fi_streak, updated_exit_count)
        """
        if sv5_turbulence is None and sv5_shock is not None:
            sv5_turbulence = sv5_shock

        ratio_window = ratio_window or []
        fgbi_window = fgbi_window or []

        n_dead = sum(1 for v in sec_th.values() if v < 25.0)
        can_switch = days_in_mode >= min_regime_days

        # Antena 1: Inversión Persistente SV5_FI > S5_FI
        spread_fi = fi - v_fi
        if spread_fi < -5.0:
            inv_fi_streak += 1
        else:
            inv_fi_streak = 0

        effective_tw_prev = tw if tw_prev is None else tw_prev

        # Disparador híbrido basado en estados conjuntos de SPY
        spy_joint = cls.get_spy_joint_state(th, fi, tw, effective_tw_prev, v_th, v_fi, v_tw)
        is_pre_crash_distribution = (inv_fi_streak >= 10) or (spy_joint in cls.TOP_DISTRIBUTION_STATES)

        # Antena 3 (V28): Divergent Leadership
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        is_divergent_leadership = (hot_tw <= 1 and cold_tw >= 7)
        is_pre_crash_distribution = is_pre_crash_distribution or is_divergent_leadership

        is_falling_knife = (fi_velocity >= 5.0 or (fi < 30.0 and tw < 15.0 and th > 35.0))

        # V37.1 Approved 3D Re-absorption
        div_fi = v_fi - fi
        ratio_tw_fi = tw / max(1.0, fi)
        is_bullish_reabsorption = (th >= 60.0 and fi <= 45.0 and v_tw >= 60.0 and ratio_tw_fi <= 1.2 and div_fi >= 0.0)
        is_volume_capitulation = (th <= 25.0 and v_tw >= 60.0)

        # Antena de Capitulación Defensiva (XLP Floor)
        xlp_fi = sec_fi.get("XLP", 50.0)
        has_defensive_floor = (xlp_fi >= 25.0 and n_dead <= 5 and (vix is None or vix < 35.0))

        new_mode = current_mode

        if current_mode in ("NORMAL", "MERCADO_SANO", "RE_ACUMULACION_ALCISTA"):
            if th < 30.0 and fi < 25.0 and tw < 20.0:
                new_mode = "CRASH_SISTEMICO" if n_dead >= 5 else "CAPITULACION_SECTORIAL"
            elif is_pre_crash_distribution:
                new_mode = "DISTRIBUCION_PRE_CRASH"
            elif is_volume_capitulation:
                new_mode = "PISO_GENERACIONAL"
            elif is_bullish_reabsorption:
                new_mode = "RE_ACUMULACION_ALCISTA"
            elif is_falling_knife:
                pass
            elif th < 35.0 and fi < 30.0 and tw > 40.0:
                new_mode = "BEAR_RALLY"
            elif th > 40.0 and fi > 40.0 and tw < 30.0 and can_switch:
                vol_div = v_tw - tw
                sec_v_tw_dict = sec_v_tw if sec_v_tw is not None else {}
                strong_sec_vol = sum(1 for s in sec_v_tw_dict.values() if s >= 40.0)
                if vol_div >= -5.0 and (not sec_v_tw_dict or strong_sec_vol >= 2):
                    had_recent_ceiling = any(r >= 3.50 for r in ratio_window[:-1]) if len(ratio_window) > 1 else False
                    if not had_recent_ceiling:
                        new_mode = "PULLBACK_ALCISTA"
            elif th > 60.0 and fi > 50.0 and tw > 40.0:
                new_mode = "MERCADO_SANO"
            elif th < 40.0 and fi < 35.0 and tw > 35.0:
                new_mode = "RECUPERACION"

        elif current_mode == "DISTRIBUCION_PRE_CRASH":
            if th < 30.0 and fi < 25.0 and tw < 20.0:
                new_mode = "CRASH_SISTEMICO"
                exit_count = 0
            else:
                ex_re = is_bullish_reabsorption or (n_dead == 0 and th > 50.0 and (not dist_exit_hyst or not is_pre_crash_distribution))
                ex_ms = (not is_pre_crash_distribution) and can_switch and th > 50.0
                if ex_re or ex_ms:
                    exit_count += 1
                    if exit_count >= dist_exit_confirm:
                        new_mode = "RE_ACUMULACION_ALCISTA" if ex_re else "MERCADO_SANO"
                        exit_count = 0
                else:
                    exit_count = 0

        elif current_mode == "CRASH_SISTEMICO":
            can_switch_crash = (days_in_mode >= 3)
            is_fgbi_reversal = False
            effective_peak = fgbi_peak_15d if fgbi_peak_15d is not None else (max(fgbi_window) if fgbi_window else None)
            if fgbi is not None and effective_peak is not None:
                if effective_peak > 20.0 and (fgbi < 15.0 or fgbi <= (effective_peak - 5.0)):
                    if th >= 40.0 or (vbi is not None and vbi > 1.5):
                        is_fgbi_reversal = True

            washout = (n_dead >= 6 and tw > 40.0 and can_switch_crash)
            if is_volume_capitulation or (has_defensive_floor and can_switch_crash) or (is_fgbi_reversal and can_switch_crash) or washout:
                new_mode = "PISO_GENERACIONAL"
            elif can_switch_crash and tw > 45.0 and fi > 35.0 and th > 25.0 and n_dead <= 4:
                new_mode = "RECUPERACION"

        elif current_mode == "CAPITULACION_SECTORIAL":
            if n_dead >= 5:
                new_mode = "CRASH_SISTEMICO"
            elif is_volume_capitulation or (has_defensive_floor and can_switch):
                new_mode = "PISO_GENERACIONAL"
            elif can_switch and th > 40.0:
                new_mode = "NORMAL"
            elif can_switch and fi > 40.0 and tw > 40.0:
                new_mode = "RECUPERACION"

        elif current_mode == "PISO_GENERACIONAL":
            if can_switch and th > 35.0:
                new_mode = "NORMAL"
            elif can_switch and fi > 50.0:
                new_mode = "RECUPERACION"

        elif current_mode == "BEAR_RALLY":
            if th < 30.0 and fi < 25.0 and tw < 20.0:
                new_mode = "CRASH_SISTEMICO" if n_dead >= 5 else "CAPITULACION_SECTORIAL"
            elif can_switch and th > 45.0:
                new_mode = "NORMAL"

        elif current_mode == "PULLBACK_ALCISTA":
            if is_pre_crash_distribution:
                new_mode = "DISTRIBUCION_PRE_CRASH"
            elif is_bullish_reabsorption:
                new_mode = "RE_ACUMULACION_ALCISTA"
            elif is_falling_knife:
                pass
            elif tw > 40.0 or (can_switch and fi > 50.0):
                new_mode = "NORMAL"
            elif th < 35.0:
                new_mode = "BEAR_RALLY"

        elif current_mode == "RECUPERACION":
            if can_switch and ((th > 50.0 and fi > 50.0) or (tw > 60.0 and v_fi > 55.0 and th > 40.0)):
                new_mode = "MERCADO_SANO"
            elif th < 25.0 and n_dead >= 5:
                new_mode = "CRASH_SISTEMICO"

        # V36 Calibrated Redirection & V40 Turbulence Detector
        if current_mode != "CRASH_SISTEMICO" and new_mode == "CRASH_SISTEMICO" and v_th >= 25.0:
            if vix is not None:
                if vix <= 28.0:
                    new_mode = "PISO_GENERACIONAL"
            elif sv5_turbulence is not None and sv5_turbulence <= cls.SV5_STD_VIX_CRASH_THRESHOLD:
                new_mode = "PISO_GENERACIONAL"

        return new_mode, inv_fi_streak, exit_count
