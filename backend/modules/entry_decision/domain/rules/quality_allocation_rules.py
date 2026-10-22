"""
QUALITY ALLOCATION RULES — PURE DOMAIN RULES
============================================
Clean Architecture: Domain Layer (Pure Business Rules)
Module: entry_decision / domain / rules

Formal mathematical rules for the Quality Department Sector Portfolio Sizing:
  1. Cash allocation in CRASH_SISTEMICO (100% Cash / 0% Sectors).
  2. Defensive Pool Allocation in DISTRIBUCION_PRE_CRASH (50% Defensive XLP/XLU/XLV).
  3. Core Pool and Relative Strength selection in RE_ACUMULACION_ALCISTA.
  4. High-Beta beaten down recovery in PISO_GENERACIONAL.
  5. Tactical dip-buying volume alignment in PULLBACK_ALCISTA.
  6. Hybrid momentum resilience in RECUPERACION.
  7. Core vs Satellite stochastic divergence & Weinstein Stage 4 smart veto in MERCADO_SANO.
  8. QQQ Competitive Advantage substitution in broad bull regimes.
  9. SV5_Turbulence institutional volume risk dampeners (V41).

Zero infrastructure dependencies. Zero side-effects. Fully deterministic.
"""

from typing import Dict, Any, List, Optional
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS
from backend.modules.entry_decision.domain.rules.quality_regime_rules import QualityRegimeRules


class QualityAllocationRules:
    """
    Pure Domain Allocation Rule Engine for Quality Portfolio Target Weights.
    Calculates exact percentage allocations for the canonical B0 baseline.
    """

    @classmethod
    def calculate_target_weights(
        cls,
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
        sv5_turbulence: Optional[float] = None,
        sv5_shock: Optional[float] = None,
        vix: Optional[float] = None,
    ) -> Dict[str, float]:
        """Calculates sector target weights according to the canonical B0 baseline rules."""
        if not avail_sectors:
            return {}

        target: Dict[str, float] = {}

        if mode == "CRASH_SISTEMICO":
            return {s: 0.0 for s in avail_sectors}

        elif mode == "DISTRIBUCION_PRE_CRASH":
            def_pool = ["XLP", "XLU", "XLV"]
            tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in def_pool if s in avail_sectors)
            for s in def_pool:
                if s in avail_sectors:
                    target[s] = 0.50 * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)

        elif mode == "RE_ACUMULACION_ALCISTA":
            core_pool = [s for s, w in SECTOR_CAP_WEIGHTS.items() if w >= 0.08 and s in avail_sectors]
            if rs_roc_50d:
                rs_scores = {s: rs_roc_50d.get(s, -999.0) for s in core_pool if not (sec_stage4 and sec_stage4.get(s, False))}
                top_leaders = sorted(rs_scores.keys(), key=lambda x: rs_scores[x], reverse=True)[:2]
            else:
                top_leaders = []

            active_core = [s for s in core_pool if s in top_leaders or sec_fi.get(s, 100.0) <= 45.0]
            if not active_core:
                active_core = core_pool

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
            non_def = [s for s in avail_sectors if s not in ("XLP", "XLU", "XLV")]
            if not non_def:
                non_def = avail_sectors
            beaten_down = sorted(non_def, key=lambda s: sec_tw.get(s, 50.0))[:3]
            tot = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in beaten_down)
            scale = 1.0
            n_dead = sum(1 for s in avail_sectors if sec_th.get(s, 0) < 25.0)
            if n_dead >= 8 and (vix is not None and vix >= 40.0):
                scale = 0.70
            if tot > 0.0:
                for s in beaten_down:
                    target[s] = scale * SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot
            else:
                for s in beaten_down:
                    target[s] = scale / len(beaten_down)

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

            if sec_v_fi and rs_roc_5d:
                for s in sats:
                    if sec_th.get(s, 0) >= 40.0 and sec_fi.get(s, 100.0) <= 35.0:
                        rs_roc = rs_roc_5d.get(s, 0.0)
                        vol_div = sec_v_fi.get(s, 50.0) - sec_fi.get(s, 50.0)
                        if rs_roc > 0.0 and vol_div > 10.0:
                            score = vol_div * rs_roc

                            # Weinstein Stage 4 Smart Veto
                            if sec_stage4 and sec_stage4.get(s, False):
                                if vol_div <= 15.0:
                                    continue

                            if score > best_score:
                                best_score = score
                                best_sat = s
            else:
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

        # QQQ Competitive Advantage Directive
        if mode in ("NORMAL", "RE_ACUMULACION_ALCISTA", "MERCADO_SANO"):
            if "QQQ" in avail_sectors and "XLK" in target and target["XLK"] > 0:
                xlk_w = target.pop("XLK")
                target["QQQ"] = xlk_w

        tot_w = sum(target.values())
        if tot_w > 0:
            target = {s: w / tot_w for s, w in target.items()}

        # V41 SV5_TURBULENCE Institutional Volume Risk Modifiers
        if sv5_turbulence is None and sv5_shock is not None:
            sv5_turbulence = sv5_shock

        if sv5_turbulence is not None:
            if mode == "RECUPERACION" and sv5_turbulence > QualityRegimeRules.SV5_TURBULENCE_HIGH_THRESHOLD:
                target = {s: w * 0.50 for s, w in target.items()}
            elif mode == "RE_ACUMULACION_ALCISTA" and (QualityRegimeRules.SV5_TURBULENCE_HIGH_THRESHOLD <= sv5_turbulence < QualityRegimeRules.SV5_TURBULENCE_EXTREME_THRESHOLD):
                target = {s: w * 0.75 for s, w in target.items()}

        tot_w_final = sum(target.values())
        if tot_w_final > 0:
            return {s: round(w, 4) for s, w in target.items()}
        return {s: 0.0 for s in avail_sectors}
