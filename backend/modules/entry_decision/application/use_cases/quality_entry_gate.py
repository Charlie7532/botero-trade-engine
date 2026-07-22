"""
QUALITY ENTRY GATE (V26 RECUPERACION SPY BLEND)
==================================================
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
     Backtest: +8.84 acciones adicionales (381.98 total).
"""

from typing import Dict, Any, List, Optional
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

class QualityEntryGate:
    """
    Gate V26 Recuperacion SPY Blend para asignación de cartera de calidad sectorial.
    Logra 381.98 acciones finales de SPY (+281.98 sobre benchmark), +35.11 sobre V23 Pro,
    en 27.5 años de auditoría (1999-2026).
    V25: SV5_TW >= 50% en PULLBACK_ALCISTA (+26.27 acc).
    V26: 50% SPY + 50% sectores en RECUPERACION (+8.84 acc).
    """

    def __init__(self, min_regime_days: int = 20):
        self.min_regime_days = min_regime_days
        self.inv_fi_streak = 0

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
        fi_velocity: float = 0.0,
        current_mode: str = "NORMAL",
        days_in_mode: int = 25,
    ) -> str:
        """
        Clasifica el modo de mercado usando las 2 Antenas Pre-Evento de V20.
        """
        n_dead = sum(1 for v in sec_th.values() if v < 25.0)
        can_switch = days_in_mode >= self.min_regime_days
        
        # Antena 1: Inversión Persistente SV5_FI > S5_FI
        spread_fi = fi - v_fi
        if spread_fi < -5.0:
            self.inv_fi_streak += 1
        else:
            self.inv_fi_streak = 0
            
        is_pre_crash_distribution = (self.inv_fi_streak >= 10)
        is_falling_knife = (fi_velocity >= 5.0 or (fi < 30.0 and tw < 15.0 and th > 35.0))
        
        is_bullish_reabsorption = (th >= 60.0 and fi <= 45.0 and v_tw >= 60.0)
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
                new_mode = "PULLBACK_ALCISTA"
            elif th > 60.0 and fi > 50.0 and tw > 40.0:
                new_mode = "MERCADO_SANO"
            elif th < 40.0 and fi < 35.0 and tw > 35.0:
                new_mode = "RECUPERACION"

        elif current_mode == "DISTRIBUCION_PRE_CRASH":
            if th < 30.0 and fi < 25.0 and tw < 20.0:
                new_mode = "CRASH_SISTEMICO"
            elif not is_pre_crash_distribution and can_switch and th > 50.0:
                new_mode = "MERCADO_SANO"

        elif current_mode == "CRASH_SISTEMICO":
            if is_volume_capitulation or (has_defensive_floor and can_switch):
                new_mode = "PISO_GENERACIONAL"
            elif can_switch and tw > 45.0 and fi > 35.0 and th > 25.0 and n_dead <= 4:
                new_mode = "RECUPERACION"
            elif n_dead >= 6 and tw > 40.0 and can_switch:
                new_mode = "PISO_GENERACIONAL"

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
            if is_bullish_reabsorption:
                new_mode = "RE_ACUMULACION_ALCISTA"
            elif is_falling_knife:
                pass
            elif tw > 40.0 or (can_switch and fi > 50.0):
                new_mode = "NORMAL"
            elif th < 35.0:
                new_mode = "BEAR_RALLY"

        elif current_mode == "RECUPERACION":
            if can_switch and th > 50.0 and fi > 50.0:
                new_mode = "MERCADO_SANO"
            elif th < 25.0 and n_dead >= 5:
                new_mode = "CRASH_SISTEMICO"

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
    ) -> Dict[str, float]:
        """
        Calcula las ponderaciones objetivo por sector según el modo V25.
        V25: adds SV5_TW tactical volume filter in PULLBACK_ALCISTA (+26.27 acc backtest).
        """
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
            core_pool = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP"]
            oversold_core = [s for s in core_pool if s in avail_sectors and sec_fi.get(s, 100.0) <= 45.0]
            if not oversold_core:
                oversold_core = [s for s in core_pool if s in avail_sectors]
            tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in oversold_core)
            for s in oversold_core:
                target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap

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
            for s, _ in survivors:
                target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot

        elif mode == "PISO_GENERACIONAL":
            if sec_v_fi:
                floor_candidates = sorted([(s, sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:5]
            else:
                floor_candidates = sorted([(s, sec_tw.get(s, 0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:5]
            tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s, _ in floor_candidates)
            for s, _ in floor_candidates:
                target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot

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
            for s, _ in oversold:
                target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot

        elif mode == "RECUPERACION":
            # V26: 50% SPY + 50% sector leaders during recovery.
            # SPY captures the broad rebound of sectors excluded from Core
            # (XLY, XLE, XLB) that often bounce harder in early recovery.
            # Backtest: +8.84 shares over 27.5 years.
            recov = [(s, sec_fi.get(s, 0)) for s in avail_sectors if sec_tw.get(s, 0) > 35.0 and sec_th.get(s, 0) > 25.0]
            if not recov:
                recov = sorted([(s, sec_fi.get(s, 0)) for s in avail_sectors], key=lambda x: x[1], reverse=True)[:5]
            tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s, _ in recov)
            for s, _ in recov:
                target[s] = 0.50 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot)
            target["SPY"] = 0.50

        else:  # NORMAL, MERCADO_SANO
            # Antena 2: Excluir del Core Pool a sectores estancados (S5_FI < 55%) en Mercado Sano
            core_pool = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP"]
            healthy_core = [s for s in core_pool if s in avail_sectors and sec_th.get(s, 0) >= 40.0 and sec_fi.get(s, 0) >= 55.0]
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
                for s in healthy_core:
                    target[s] = 0.80 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)
                target[best_sat] = 0.20
            else:
                tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in healthy_core)
                for s in healthy_core:
                    target[s] = SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap

        tot_w = sum(target.values())
        if tot_w > 0:
            return {s: round(w / tot_w, 4) for s, w in target.items()}
        return {s: 0.0 for s in avail_sectors}
