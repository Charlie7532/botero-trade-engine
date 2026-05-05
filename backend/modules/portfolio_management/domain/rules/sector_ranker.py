"""
Sector Ranker — Rotation-Aware Sector Eligibility
=====================================================
Ranks GICS sectors by Weinstein Stage + Wyckoff Flow + Breadth Divergence.
Consumes a RotationSnapshot from the unified RotationScanner.

Replaces the previous stub that returned rs_score=0.0 for all sectors.
"""
import logging
from typing import Optional

from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

logger = logging.getLogger(__name__)


class SectorRanker:
    """Ranks sectors using the unified RotationSnapshot."""

    def rank_sectors(self, rotation_snapshot=None) -> list[dict]:
        """
        Rank sectors by rotation health.

        Args:
            rotation_snapshot: RotationSnapshot from RotationScanner.
                               If None, returns all sectors as eligible (safe default).

        Returns:
            List of dicts with keys:
                sector, etf, rs_score, stage, flow_signal,
                breadth_divergence, eligible, reason
        """
        rankings = []

        # Build lookup from snapshot signals
        signal_by_name = {}
        if rotation_snapshot:
            for sig in rotation_snapshot.signals:
                if sig.dimension == "sector":
                    signal_by_name[sig.name] = sig

        for etf, sector in SECTOR_ETFS.items():
            sig = signal_by_name.get(sector)

            if sig:
                rs_score = sig.rs_score
                stage = sig.stage
                flow = sig.flow_signal
                divergence = sig.breadth_divergence
                eligible, reason = self._evaluate_eligibility(
                    stage, flow, divergence
                )
            else:
                rs_score = 0.0
                stage = 0
                flow = "UNKNOWN"
                divergence = 0.0
                eligible = True
                reason = "no_rotation_data"

            rankings.append({
                "sector": sector,
                "etf": etf,
                "rs_score": rs_score,
                "stage": stage,
                "flow_signal": flow,
                "breadth_divergence": divergence,
                "eligible": eligible,
                "reason": reason,
            })

        # Sort by rs_score descending (strongest sectors first)
        rankings.sort(key=lambda x: x["rs_score"], reverse=True)

        eligible_count = sum(1 for r in rankings if r["eligible"])
        logger.info(
            f"SectorRanker: {eligible_count}/{len(rankings)} sectors eligible"
        )

        return rankings

    @staticmethod
    def _evaluate_eligibility(
        stage: int, flow: str, divergence: float
    ) -> tuple[bool, str]:
        """
        Determine if a sector passes the rotation filter.

        Rules:
        1. Stage 4 (Declining) → NOT eligible (capital exiting)
        2. Stage 4 + DISTRIBUTION → NOT eligible (double confirmation)
        3. Stage 3 + DISTRIBUTION + negative divergence → NOT eligible
           (topping with institutional selling AND narrow market)
        4. Everything else → eligible
        """
        if stage == 4:
            return False, "stage_4_declining"

        if stage == 3 and flow == "DISTRIBUTION" and divergence < -0.02:
            return False, "stage_3_distribution_narrow"

        return True, "eligible"
