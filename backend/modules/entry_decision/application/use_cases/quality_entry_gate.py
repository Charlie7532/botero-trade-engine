"""
QUALITY ENTRY GATE (V28 DIVERGENT LEADERSHIP + WEINSTEIN SMART VETO)
=====================================================================
Capa de decisión táctica y de régimen de rotación sectorial basada en
la síntesis cuantitativa de 27.5 años (1999 - 2026):

  1. ANTENA PRE-CRASH (Inversión Persistente SV5_FI > S5_FI durante >= 10 días):
     Detecta la distribución de volumen institucional 30 días antes del techo
     (ganó +24.73 acciones de SPY en el Bear Market de 2022).
  2. ANTENA DE SELECCIÓN CORE DINÁMICA:
     Excluye sectores Core estancados (S5_FI < 55%) en Mercado Sano.
  3. Super-Patrón de Re-Absorción Alcista (S5_TH >= 60% + S5_FI <= 45% + SV5_TW >= 60% → 86.9% WR Buy).
  4. Gatillo de Capitulación de Volumen en Suelo (Anomalía C: S5_TH <= 25% + SV5_TW >= 60% → 82.8% WR Buy).
  5. Filtro Anti-Cuchillo Cayendo (v_FI <= -15pp → Congela rebalanceos en caída libre).
  6. V25 PULLBACK TACTICAL VOLUME: En PULLBACK_ALCISTA, prefiere sectores donde
     instituciones están comprando el dip activamente (SV5_TW >= 50%).
     Backtest: +26.27 acciones adicionales.
  7. V26 RECUPERACION SPY BLEND: En RECUPERACION, 50% SPY + 50% sectores líderes.
     SPY captura el rebote amplio de sectores excluidos del Core.
     Backtest: +8.84 acciones adicionales.
  8. V28 DIVERGENT LEADERSHIP (hot_tw <= 1 AND cold_tw >= 7):
     3er disparador de DISTRIBUCION_PRE_CRASH. Detecta mercados estrechos
     donde solo 1 sector lidera mientras 7+ colapsan en amplitud táctica.
     Backtest: +77.60 acciones sobre V27.
  9. V28 WEINSTEIN SMART VETO: Veta sectores en Stage 4 (precio < MA150,
     pendiente negativa) del pool de satélites, EXCEPTO cuando instituciones
     acumulan masivamente (vol_div > 15). Override por oportunidad clara.
     Backtest: +6.60 acciones solo, +84.79 combinado con H1a.
"""

from typing import Dict, Any, List, Optional
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

class QualityEntryGate:
    """
    Gate V28 Divergent Leadership + Weinstein Smart Veto.
    Logra 468.20 acciones finales de SPY (+368.20 sobre benchmark)
    en 27.5 años de auditoría (1999-2026).
    V25: SV5_TW >= 50% en PULLBACK_ALCISTA (+26.27 acc).
    V26: 50% SPY + 50% sectores en RECUPERACION (+8.84 acc).
    V28: Divergent Leadership + Weinstein Smart Veto (+84.79 acc).
    """

    # Constantes de clasificación para el anidamiento conjunto S5xSV5
    S5_EDGES = {
        "TH": [27.6, 54.8, 82.8, 93.5],
        "FI": [20.0, 46.7, 76.9, 90.4],
        "TW": [16.7, 41.9, 75.0, 90.0]
    }
    SV5_EDGES = {
        "TH": [17.5, 32.5, 60.5, 81.2],
        "FI": [19.0, 33.3, 59.3, 77.8],
        "TW": [15.8, 30.2, 55.3, 75.0]
    }
    LABELS = ["<<", "<", "~", ">", ">>"]

    # Estados de distribución optimizados (Subset 2: dirección '+')
    TOP_DISTRIBUTION_STATES = {
        "<<|<<|~|>>|>>|<|+",
        "<<|<<|<<|>>|>>|>>|+",
        "<<|<<|~|>>|>>|<<|+",
        "<<|<<|<<|>>|>>|>|+",
        ">>|>|>|<<|~|~|+",
        "<<|~|~|~|>|~|+",
        "<<|<<|<<|>|>>|>>|+"
    }

    # V40: SV5StdVIX threshold — empirically validated as VIX contingency (90.1% recovery)
    SV5_STD_VIX_CRASH_THRESHOLD = 10.0

    def __init__(self, min_regime_days: int = 20):
        self.min_regime_days = min_regime_days
        self.inv_fi_streak = 0
        self.prev_tw = None
        self.fgbi_window = []
        self.ratio_window = []

    def _classify_bin(self, v: float, edges: list[float]) -> str:
        for idx, e in enumerate(edges):
            if v < e: return self.LABELS[idx]
        return self.LABELS[-1]

    def _get_spy_joint_state(self, th: float, fi: float, tw: float, tw_prev: float, v_th: float, v_fi: float, v_tw: float) -> str:
        s5_th_b = self._classify_bin(th, self.S5_EDGES["TH"])
        s5_fi_b = self._classify_bin(fi, self.S5_EDGES["FI"])
        s5_tw_b = self._classify_bin(tw, self.S5_EDGES["TW"])
        dir_b = "+" if tw > tw_prev else "-"
        sv5_th_b = self._classify_bin(v_th, self.SV5_EDGES["TH"])
        sv5_fi_b = self._classify_bin(v_fi, self.SV5_EDGES["FI"])
        sv5_tw_b = self._classify_bin(v_tw, self.SV5_EDGES["TW"])
        return f"{s5_th_b}|{s5_fi_b}|{s5_tw_b}|{sv5_th_b}|{sv5_fi_b}|{sv5_tw_b}|{dir_b}"

    def evaluate_regime(
        self,
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
        sv5_shock: Optional[float] = None,
    ) -> str:
        """
        Clasifica el modo de mercado usando las 3 Antenas Pre-Evento de V28
        y disparadores híbridos de tríadas S5xSV5.
        """
        if fgbi is not None:
            self.fgbi_window.append(fgbi)
            if len(self.fgbi_window) > 15:
                self.fgbi_window.pop(0)

        # Track ratio history
        ratio = tw / max(1.0, v_tw)
        self.ratio_window.append(ratio)
        if len(self.ratio_window) > 7:
            self.ratio_window.pop(0)



        n_dead = sum(1 for v in sec_th.values() if v < 25.0)
        can_switch = days_in_mode >= self.min_regime_days
        
        # Antena 1: Inversión Persistente SV5_FI > S5_FI
        spread_fi = fi - v_fi
        if spread_fi < -5.0:
            self.inv_fi_streak += 1
        else:
            self.inv_fi_streak = 0
            
        # Calcular dirección del SPY de forma interna y robusta para retrocompatibilidad
        if tw_prev is None:
            tw_prev = self.prev_tw if self.prev_tw is not None else tw
        self.prev_tw = tw
        
        # Disparador híbrido basado en estados conjuntos de SPY
        spy_joint = self._get_spy_joint_state(th, fi, tw, tw_prev, v_th, v_fi, v_tw)
        is_pre_crash_distribution = (self.inv_fi_streak >= 10) or (spy_joint in self.TOP_DISTRIBUTION_STATES)

        # Antena 3 (V28): Divergent Leadership — mercado estrecho
        # Solo 1 sector caliente (TW > 50%) mientras 7+ colapsan (TW < 20%)
        # detecta distribución silenciosa invisible a las antenas agregadas.
        # Backtest: +77.60 acc, ganancias distribuidas en 16/20 años.
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        is_divergent_leadership = (hot_tw <= 1 and cold_tw >= 7)
        is_pre_crash_distribution = is_pre_crash_distribution or is_divergent_leadership
        
        is_falling_knife = (fi_velocity >= 5.0 or (fi < 30.0 and tw < 15.0 and th > 35.0))
        
        # V37.1 Approved 3D Re-absorption: Require tactical ratio TW/FI <= 1.2 and Div_FI >= 0.0
        div_fi = v_fi - fi
        ratio_tw_fi = tw / max(1.0, fi)
        is_bullish_reabsorption = (th >= 60.0 and fi <= 45.0 and v_tw >= 60.0 and ratio_tw_fi <= 1.2 and div_fi >= 0.0)
        is_volume_capitulation = (th <= 25.0 and v_tw >= 60.0)
        
        # Antena de Capitulación Defensiva (XLP Floor)
        xlp_fi = sec_fi.get("XLP", 50.0)
        has_defensive_floor = (xlp_fi >= 25.0)

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
                # V37 Spectral Check: Ensure volume divergence supports dip-buying (v_tw - tw >= -5.0)
                # and at least 2 sectors maintain active volume support (sec_v_tw >= 40.0)
                vol_div = v_tw - tw
                sec_v_tw_dict = sec_v_tw if sec_v_tw is not None else {}
                strong_sec_vol = sum(1 for s in sec_v_tw_dict.values() if s >= 40.0)
                if vol_div >= -5.0 and (not sec_v_tw_dict or strong_sec_vol >= 2):
                    # V37.2 Ceiling Filter: Block entry if a dilated ceiling (ratio >= 3.50) occurred in last 5 days
                    had_recent_ceiling = any(r >= 3.50 for r in self.ratio_window[:-1]) if len(self.ratio_window) > 1 else False
                    if not had_recent_ceiling:
                        new_mode = "PULLBACK_ALCISTA"
            elif th > 60.0 and fi > 50.0 and tw > 40.0:
                new_mode = "MERCADO_SANO"
            elif th < 40.0 and fi < 35.0 and tw > 35.0:
                new_mode = "RECUPERACION"

        elif current_mode == "DISTRIBUCION_PRE_CRASH":
            if th < 30.0 and fi < 25.0 and tw < 20.0:
                new_mode = "CRASH_SISTEMICO"
            elif is_bullish_reabsorption or (n_dead == 0 and th > 50.0):
                # V38 Directive: Transición inmediata a RE_ACUMULACION_ALCISTA si n_dead == 0 y TH > 50%
                new_mode = "RE_ACUMULACION_ALCISTA"
            elif not is_pre_crash_distribution and can_switch and th > 50.0:
                new_mode = "MERCADO_SANO"

        elif current_mode == "CRASH_SISTEMICO":
            # V32a: Candado táctico de 3 días para salir de cash en lugar del candado global de 20d
            can_switch_crash = (days_in_mode >= 3)
            
            # V34: FGBI Reversal + VBI Panic Capitulation filter
            is_fgbi_reversal = False
            effective_peak = fgbi_peak_15d if fgbi_peak_15d is not None else (max(self.fgbi_window) if self.fgbi_window else None)
            if fgbi is not None and effective_peak is not None:
                if effective_peak > 20.0 and (fgbi < 15.0 or fgbi <= (effective_peak - 5.0)):
                    if th >= 40.0 or (vbi is not None and vbi > 1.5):
                        is_fgbi_reversal = True

            if is_volume_capitulation or (has_defensive_floor and can_switch_crash) or (is_fgbi_reversal and can_switch_crash):
                new_mode = "PISO_GENERACIONAL"
            elif can_switch_crash and tw > 45.0 and fi > 35.0 and th > 25.0 and n_dead <= 4:
                new_mode = "RECUPERACION"
            elif n_dead >= 6 and tw > 40.0 and can_switch_crash:
                new_mode = "PISO_GENERACIONAL"

        # CAPITULACION_SECTORIAL: actualmente interceptado por H1a (Divergent Leadership)
        # antes de alcanzar estos umbrales. Contribución V28 = 0.00 acc en 27.5 años.
        # Se mantiene como red de seguridad si H1a se modifica en el futuro.
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
            # V37.1 Fast V-shaped recovery escape hatch: allow transition if momentum & volume lead (tw > 60, v_fi > 55, th > 40)
            if can_switch and ((th > 50.0 and fi > 50.0) or (tw > 60.0 and v_fi > 55.0 and th > 40.0)):
                new_mode = "MERCADO_SANO"
            elif th < 25.0 and n_dead >= 5:
                new_mode = "CRASH_SISTEMICO"

        # V36 Calibrated Redirection: If transitioning into CRASH_SISTEMICO from non-crash state,
        # but VIX <= 28.0 and v_th >= 25.0, redirect to PISO_GENERACIONAL.
        # V40: When VIX unavailable (None), use SV5_SHOCK from Vault as crash detector.
        # SV5_SHOCK = std(Δ_SV5TW, 10d). >10 = institutional panic = real crash.
        # Empirically recovers 96.9% of VIX's protective value (26yr benchmark).
        if current_mode != "CRASH_SISTEMICO" and new_mode == "CRASH_SISTEMICO" and v_th >= 25.0:
            if vix is not None:
                if vix <= 28.0:
                    new_mode = "PISO_GENERACIONAL"
            elif sv5_shock is not None and sv5_shock <= self.SV5_STD_VIX_CRASH_THRESHOLD:
                # V40 Contingency: institutions calm → not a real crash
                new_mode = "PISO_GENERACIONAL"

        return new_mode

    def calculate_target_weights(
        self,
        mode: str,
        sec_th: Dict[str, float],
        sec_fi: Dict[str, float],
        sec_tw: Dict[str, float],
        avail_sectors: List[str],
        sec_v_fi: Optional[Dict[str, float]] = None,
        sec_v_tw: Optional[Dict[str, float]] = None,
        rs_roc_5d: Optional[Dict[str, float]] = None,
        sec_stage4: Optional[Dict[str, bool]] = None,
        rs_roc_50d: Optional[Dict[str, float]] = None,
        rs_roc_20d: Optional[Dict[str, float]] = None,
        s5cap_fi: Optional[Dict[str, float]] = None,
        sec_vbi: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Calcula las ponderaciones objetivo por sector según el modo V35.
        V35: adds S5cap/VBI institutional filtering in MERCADO_SANO
             and VBI volume conviction boost in RE_ACUMULACION_ALCISTA.
        """
        if not avail_sectors:
            return {}
            
        target = {}

        if mode == "CRASH_SISTEMICO":
            return {s: 0.0 for s in avail_sectors}

        elif mode == "DISTRIBUCION_PRE_CRASH":
            def_pool = ["XLP", "XLU", "XLV"]
            tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in def_pool if s in avail_sectors)
            for s in def_pool:
                if s in avail_sectors:
                    target[s] = 0.50 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)

        elif mode == "RE_ACUMULACION_ALCISTA":
            # Regla 19: Core pool canónico CapWeight >= 8% (XLK, XLF, XLV, XLY, XLC, XLI)
            core_pool = [s for s, w in SECTOR_CAP_WEIGHTS.items() if w >= 0.08 and s in avail_sectors]
            if rs_roc_50d:
                rs_scores = {s: rs_roc_50d.get(s, -999.0) for s in core_pool if not (sec_stage4 and sec_stage4.get(s, False))}
                top_leaders = sorted(rs_scores.keys(), key=lambda x: rs_scores[x], reverse=True)[:2]
            else:
                top_leaders = []

            active_core = [s for s in core_pool if s in top_leaders or sec_fi.get(s, 100.0) <= 45.0]
            if not active_core:
                active_core = core_pool

            # V34: Cap-Weight Divergence extreme penalty (div > 25% gets 0.5x weight)
            # V35: VBI Volume Conviction Boost (> 0.8 gets 1.4x, < -0.2 gets 0.6x)
            tot_cap = 0.0
            weights_temp = {}
            for s in active_core:
                base_w = SECTOR_CAP_WEIGHTS.get(s, 0.05)
                if s5cap_fi is not None and s in s5cap_fi and s5cap_fi[s] is not None:
                    div = sec_fi.get(s, 50.0) - s5cap_fi[s]
                    if div > 25.0:
                        base_w *= 0.5
                if sec_vbi is not None and s in sec_vbi and sec_vbi[s] is not None:
                    vbi_val = sec_vbi[s]
                    if vbi_val > 0.8:
                        base_w *= 1.4
                    elif vbi_val < -0.2:
                        base_w *= 0.6
                weights_temp[s] = base_w
                tot_cap += base_w

            if tot_cap > 0.0:
                for s in active_core:
                    target[s] = weights_temp[s] / tot_cap
            else:
                for s in active_core:
                    target[s] = 1.0 / len(active_core)

        elif mode == "CAPITULACION_SECTORIAL":
            if sec_v_fi:
                survivors = sorted([(s, sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)) for s in avail_sectors if sec_th.get(s, 0) >= 30.0], key=lambda x: x[1], reverse=True)[:4]
                if not survivors:
                    survivors = sorted([(s, sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:4]
            else:
                survivors = [(s, sec_th[s]) for s in avail_sectors if sec_th.get(s, 0) >= 30.0]
                if not survivors:
                    survivors = sorted([(s, sec_th.get(s, 0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:4]
            tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s, _ in survivors)
            if tot > 0.0:
                for s, _ in survivors:
                    target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot
            else:
                for s, _ in survivors:
                    target[s] = 1.0 / len(survivors)

        elif mode == "PISO_GENERACIONAL":
            # V38 Directive: Acumulación Ofensiva en Sectores Alta Beta Castigados (No Defensivos: XLK, XLF, XLY, XLI, etc.)
            non_def = [s for s in avail_sectors if s not in ("XLP", "XLU", "XLV")]
            if not non_def:
                non_def = avail_sectors
            beaten_down = sorted(non_def, key=lambda s: sec_tw.get(s, 50.0))[:3]
            tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in beaten_down)
            if tot > 0.0:
                for s in beaten_down:
                    target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot
            else:
                for s in beaten_down:
                    target[s] = 1.0 / len(beaten_down)

        elif mode == "BEAR_RALLY":
            safe = [(s, sec_th[s]) for s in avail_sectors if sec_th.get(s, 0) >= 40.0]
            if safe:
                tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s, _ in safe)
                for s, _ in safe:
                    target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot
            else:
                target = {s: 0.0 for s in avail_sectors}

        elif mode == "PULLBACK_ALCISTA":
            if sec_v_fi:
                # V25: Prefer sectors where institutions are actively buying the dip
                # SV5_TW >= 50 = tactical volume spike confirms smart money accumulation
                if sec_v_tw:
                    oversold = sorted([
                        (s, sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0))
                        for s in avail_sectors
                        if sec_th.get(s, 0) > 45.0
                        and sec_tw.get(s, 0) < 35.0
                        and sec_v_tw.get(s, 50.0) >= 50.0
                    ], key=lambda x: x[1], reverse=True)[:5]
                else:
                    oversold = []
                # Fallback: drop SV5_TW filter if no sectors pass
                if not oversold:
                    oversold = sorted([(s, sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)) for s in avail_sectors if sec_th.get(s, 0) > 45.0 and sec_tw.get(s, 0) < 35.0], key=lambda x: x[1], reverse=True)[:5]
                if not oversold:
                    oversold = sorted([(s, sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:5]
            else:
                oversold = [(s, sec_th.get(s, 0) - sec_tw.get(s, 0)) for s in avail_sectors if sec_th.get(s, 0) > 45.0 and sec_tw.get(s, 0) < 35.0]
                if not oversold:
                    oversold = sorted([(s, sec_th.get(s, 0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:5]
            tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s, _ in oversold)
            if tot > 0.0:
                for s, _ in oversold:
                    target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot
            else:
                for s, _ in oversold:
                    target[s] = 1.0 / len(oversold)

        elif mode == "RECUPERACION":
            # V33c: Resiliencia Híbrida (RS 20d a la baja x Absorción de Volumen SV5_TW)
            hybrid_scores = {}
            for s in avail_sectors:
                rs_val = rs_roc_20d.get(s, 0.0) if rs_roc_20d else 0.0
                v_tw_val = sec_v_tw.get(s, 50.0) if sec_v_tw else 50.0
                hybrid_scores[s] = (rs_val + 1.0) * v_tw_val
            top_hyb = sorted(hybrid_scores.keys(), key=lambda x: hybrid_scores[x], reverse=True)[:3]
            tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in top_hyb)
            if tot_cap > 0.0:
                for s in top_hyb:
                    target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap
            else:
                for s in top_hyb:
                    target[s] = 1.0 / len(top_hyb)

        else:  # NORMAL, MERCADO_SANO
            # Antena 2: Excluir del Core Pool a sectores estancados (S5_FI < 55%) en Mercado Sano
            # V35: Excluir sectores con S5CAP_FI < 40.0 o VBI < -0.5 (distribución silenciosa)
            core_pool = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP"]
            healthy_core = [s for s in core_pool if s in avail_sectors and sec_th.get(s, 0) >= 40.0 and sec_fi.get(s, 0) >= 55.0]
            if s5cap_fi or sec_vbi:
                filtered_nextgen = []
                for s in healthy_core:
                    cap_val = s5cap_fi.get(s) if s5cap_fi else None
                    vbi_val = sec_vbi.get(s) if sec_vbi else None
                    if (cap_val is not None and cap_val < 40.0) or (vbi_val is not None and vbi_val < -0.5):
                        continue
                    filtered_nextgen.append(s)
                if filtered_nextgen:
                    healthy_core = filtered_nextgen

            if not healthy_core:
                healthy_core = [s for s in core_pool if s in avail_sectors and sec_th.get(s, 0) >= 40.0]
            if not healthy_core:
                healthy_core = [s for s in core_pool if s in avail_sectors]

            sats = [s for s in avail_sectors if s not in healthy_core]
            best_sat, best_score = None, 0.0
            
            # Si tenemos sec_v_fi y rs_roc_5d, aplicamos la optimización estocástica de cambio de sentido
            if sec_v_fi and rs_roc_5d:
                for s in sats:
                    if sec_th.get(s, 0) >= 40.0 and sec_fi.get(s, 100.0) <= 35.0:
                        rs_roc = rs_roc_5d.get(s, 0.0)
                        vol_div = sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)
                        if rs_roc > 0.0 and vol_div > 10.0:
                            score = vol_div * rs_roc

                            # V28: Weinstein Stage 4 Smart Veto
                            # Veta sectores en declive estructural (precio < MA150,
                            # pendiente negativa) del pool de satélites.
                            # Override: si vol_div > 15, instituciones están acumulando
                            # masivamente pese al Stage 4 → oportunidad clara, dejar pasar.
                            # Backtest: +6.60 acc solo, +84.79 combinado con H1a.
                            if sec_stage4 and sec_stage4.get(s, False):
                                if vol_div <= 15.0:
                                    continue  # Veto holds — no institutional interest
                                # else: override — clear opportunity

                            if score > best_score:
                                best_score = score
                                best_sat = s
            else:
                # Fallback clásico a V22
                for s in sats:
                    if sec_th.get(s, 0) >= 40.0 and sec_fi.get(s, 100.0) <= 35.0:
                        score = 40.0 - sec_fi.get(s, 40.0)
                        if score > best_score:
                            best_score = score
                            best_sat = s

            if best_sat:
                tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in healthy_core)
                if tot_cap > 0.0:
                    for s in healthy_core:
                        target[s] = 0.80 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)
                else:
                    for s in healthy_core:
                        target[s] = 0.80 / len(healthy_core)
                target[best_sat] = 0.20
            else:
                tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in healthy_core)
                if tot_cap > 0.0:
                    for s in healthy_core:
                        target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap
                else:
                    for s in healthy_core:
                        target[s] = 1.0 / len(healthy_core)

        # V39 Competitive Advantage Directive:
        # QQQ delivers massive alpha (+102.08 SPY shares) in NORMAL, RE_ACUMULACION_ALCISTA, and MERCADO_SANO.
        # In RECUPERACION, PISO_GENERACIONAL, and PULLBACK_ALCISTA, individual sector picking is preserved.
        if mode in ("NORMAL", "RE_ACUMULACION_ALCISTA", "MERCADO_SANO"):
            if "QQQ" in avail_sectors and "XLK" in target and target["XLK"] > 0:
                xlk_w = target.pop("XLK")
                target["QQQ"] = xlk_w

        tot_w = sum(target.values())

        if tot_w > 0:
            return {s: round(w / tot_w, 4) for s, w in target.items()}
        return {s: 0.0 for s in avail_sectors}

