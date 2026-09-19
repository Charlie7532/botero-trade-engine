"""
METAR Compositor Vault Provider — Unified Pipeline
====================================================
Replaces 11 individual station providers with a single compositor-based
provider that runs the full pipeline once and persists everything:

  1. Run ConvergenceCompositor.compute() (single pass for all 11 stations)
  2. Persist each station's raw METAR snapshot to MCP
  3. Persist regime state transitions for all stations
  4. Persist pre-computed SIGMET evaluation
  5. Persist pre-computed TAF composite
  6. Persist the full convergence report

EXECUTION ORDER: MUST run AFTER ohlcv_provider, breadth_provider, fear_greed,
synthetic_indicators_provider. All inputs read from Vault — zero external API calls.

Follows Rules 13, 15, 16, 17, 18.
"""
import logging
from typing import Dict, Any

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


# Station code → regime key prefix mapping
# Each station persists 3 regime keys: state_key, divergence_regime, action_code
STATION_REGIME_KEYS = {
    "vix": "vix",
    "vvix": "vvix",
    "pcr": "pcr",
    "fg": "fg",
    "sv5_turbulence": "sv5_turbulence",
    "skew": "skew",
    "credit": "credit",
    "yield_curve": "yield_curve",
    "rotation": "rotation",
    "bsi": "bsi",
    "dxy": "dxy",
}

# Station code → value field names for trigger messages
STATION_VALUE_FIELDS = {
    "vix": ("vix_index_value", "vix_velocity_3d"),
    "vvix": ("vvix_index_value", "vvix_velocity_3d"),
    "pcr": ("pcr_value", "pcr_velocity_3d"),
    "fg": ("fg_value", "fg_velocity_3d"),
    "sv5_turbulence": ("turbulence_value", "turbulence_velocity_3d"),
    "skew": ("skew_value", "skew_velocity_3d"),
    "credit": ("credit_ratio_value", "credit_velocity_3d"),
    "yield_curve": ("spread_value", "spread_velocity_3d"),
    "rotation": ("rotation_index_value", "rotation_velocity_3d"),
    "bsi": ("bsi_value", "bsi_velocity_3d"),
    "dxy": ("dxy_index_value", "dxy_velocity_3d"),
}


class MetarCompositorProvider:
    """Vault provider for unified METAR pipeline — single compositor pass."""

    name = "metar_compositor"
    categories = ["metar", "sigmet", "taf", "volatility", "credit", "rotation", "bsi"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Compute and persist all METAR stations via compositor."""
        if _already_vaulted_today(store, "metar/convergence", "MARKET"):
            logger.info("🌤️ METAR Compositor already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """METAR is market-wide — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> Dict[str, Any]:
        """Core computation: single compositor pass → persist all outputs."""
        try:
            from backend.modules.entry_decision.domain.services.convergence_compositor import (
                ConvergenceCompositor,
            )
            from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import (
                evaluate_sigmets_from_metar_dicts,
            )
            from backend.modules.entry_decision.domain.services.taf_service import (
                compute_composite_taf_from_summaries,
            )
            from backend.modules.entry_decision.domain.exceptions import StrictDataPolicyError

            # ── Single compositor pass ──────────────────────────────────
            compositor = ConvergenceCompositor()
            report = compositor.compute()

            # ── 1. Persist each station's METAR snapshot ────────────────
            stations_persisted = 0
            for code, metar_dict in report.metar_snapshots.items():
                store.save_mcp_snapshot(f"{code}/sigmet", "MARKET", metar_dict)
                stations_persisted += 1

            # ── 2. Persist regime state transitions ─────────────────────
            regime_transitions = 0
            try:
                from backend.modules.shared.infrastructure.postgres_regime_state import (
                    PostgresRegimeStateAdapter,
                )
                regime_store = PostgresRegimeStateAdapter()

                for code, metar_dict in report.metar_snapshots.items():
                    prefix = STATION_REGIME_KEYS.get(code, code)
                    state_key = metar_dict.get("state_key", "UNKNOWN")
                    div_regime = metar_dict.get("divergence_regime", "UNKNOWN")
                    action = metar_dict.get("action_code", "UNKNOWN")

                    # Get value fields for trigger message
                    val_field, vel_field = STATION_VALUE_FIELDS.get(code, ("", ""))
                    val = metar_dict.get(val_field, 0)
                    vel = metar_dict.get(vel_field, 0)
                    trigger_msg = f"{code.upper()}={val}, d3={vel}"

                    for key, state_label in [
                        (f"{prefix}:sigmet:MARKET", state_key),
                        (f"{prefix}:regime:MARKET", div_regime),
                        (f"{prefix}:guidance:MARKET", action),
                    ]:
                        current = regime_store.get_current(key)
                        if current is None or current.current_state != state_label:
                            regime_store.commit_transition(
                                key, state_label, trigger=trigger_msg
                            )
                            regime_transitions += 1
                        else:
                            regime_store.increment_duration(key)

                regime_store.close()
            except Exception as e:
                logger.warning(f"METAR Compositor: Regime state persistence skipped: {e}")

            # ── 3. Persist SIGMET evaluation ────────────────────────────
            try:
                sigmets = evaluate_sigmets_from_metar_dicts(
                    metar_dicts=report.metar_snapshots,
                    family_report=report.family_sequence,
                    as_of_date=report.as_of_date,
                )
                store.save_mcp_snapshot("sigmet/active", "MARKET", {
                    "status": "CLEAR" if not sigmets else "HAZARD_WARNING",
                    "active_sigmet_count": len(sigmets),
                    "sigmets": [s.to_dict() for s in sigmets],
                    "as_of_date": report.as_of_date,
                })
            except Exception as e:
                logger.warning(f"METAR Compositor: SIGMET persistence skipped: {e}")

            # ── 4. Persist TAF composite ────────────────────────────────
            try:
                taf_composite = compute_composite_taf_from_summaries(
                    report.station_summaries
                )
                taf_composite["as_of_date"] = report.as_of_date
                taf_composite["timestamp_utc"] = report.timestamp_utc
                store.save_mcp_snapshot("taf/composite", "MARKET", taf_composite)
            except Exception as e:
                logger.warning(f"METAR Compositor: TAF persistence skipped: {e}")

            # ── 5. Persist full convergence report ──────────────────────
            store.save_mcp_snapshot("metar/convergence", "MARKET", report.to_dict())

            logger.info(
                f"🌤️ METAR Compositor: {stations_persisted} stations | "
                f"{regime_transitions} regime transitions | "
                f"EV₁d={report.composite_ev_1d:+.4f} EV₅d={report.composite_ev_5d:+.4f} | "
                f"Rarity={report.rarity_score:.3f} | "
                f"Date={report.as_of_date} | "
                f"{report.execution_time_ms:.0f}ms"
            )

            return {
                "status": "ok",
                "as_of_date": report.as_of_date,
                "stations_persisted": stations_persisted,
                "regime_transitions": regime_transitions,
                "composite_ev_1d": report.composite_ev_1d,
                "composite_ev_5d": report.composite_ev_5d,
                "rarity_score": report.rarity_score,
                "execution_time_ms": report.execution_time_ms,
                "blind_stations": report.blind_stations,
            }

        except StrictDataPolicyError as spe:
            logger.warning(f"METAR Compositor: Strict Data Policy — {spe}")
            return {"status": "skipped", "reason": str(spe)}
        except Exception as e:
            logger.error(f"METAR Compositor computation failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


register_provider(MetarCompositorProvider())
