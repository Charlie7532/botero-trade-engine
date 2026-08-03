"""
CBOE Equity Put/Call Ratio (PCR) Vault Provider
================================================
Vault provider for PCR Market NOTAM & 3-Day Kinematic Velocity Telemetry.
Reads CBOE_PCR from Vault, generates authoritative MarketNOTAM, and persists:
  1. MCP Snapshot: mcp_snapshot("pcr/notam", "MARKET")
  2. Stateful-First Regime Transitions: market.regime_states ("pcr:notam:MARKET")

All inputs read from Vault — zero external API calls in the domain layer.
Follows Rules 13, 15, 16, 17, 18.
"""
import logging
from typing import Dict, Any, Optional

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state import PostgresRegimeStateAdapter
from backend.modules.entry_decision.domain.services.pcr_metar_service import (
    get_pcr_market_metar,
    StrictDataPolicyError
)

logger = logging.getLogger(__name__)


class PCRProvider:
    """Vault provider for CBOE Equity Put/Call Ratio (PCR) NOTAM and state transitions."""

    name = "pcr"
    categories = ["pcr", "cboe_pcr"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Compute and persist PCR Market METAR and regime state from Vault data."""
        if _already_vaulted_today(store, "pcr/sigmet", "MARKET"):
            logger.info("📊 PCR Market METAR already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """PCR METAR is market-wide — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> Dict[str, Any]:
        """Core computation: read Vault → METAR service → persist snapshot & regime state."""
        try:
            # 1. Generate live authoritative Market METAR using zero-fallback policy
            sigmet = get_pcr_market_metar()

            # 2. Persist MCP Snapshot ("pcr/sigmet", "MARKET")
            store.save_mcp_snapshot("pcr/sigmet", "MARKET", sigmet.to_dict())

            # 3. Stateful-First Regime State Persistence (Rules 15 & 16)
            try:
                regime_store = PostgresRegimeStateAdapter()

                state_keys = [
                    ("pcr:sigmet:MARKET", sigmet.state_key),
                    ("pcr:regime:MARKET", sigmet.divergence_regime),
                    ("pcr:guidance:MARKET", sigmet.operational_guidance),
                ]

                for key, state_label in state_keys:
                    current = regime_store.get_current(key)
                    if current is None or current.current_state != state_label:
                        trigger_msg = f"PCR={sigmet.pcr_index_value:.4f}, d3={sigmet.pcr_velocity_3d:+.4f}"
                        regime_store.commit_transition(key, state_label, trigger=trigger_msg)
                        logger.info(
                            f"🔄 RegimeState Transition [{key}]: "
                            f"{current.current_state if current else '(none)'} → {state_label} ({trigger_msg})"
                        )
                    else:
                        regime_store.increment_duration(key)

                regime_store.close()
            except Exception as e:
                logger.warning(f"PCR Provider: Regime state persistence skipped: {e}")

            logger.info(
                f"📊 PCR METAR Vaulted: State={sigmet.state_key} | "
                f"Regime={sigmet.divergence_regime} | Directive={sigmet.operational_guidance}"
            )

            return {
                "status": "ok",
                "metar_id": sigmet.metar_id,
                "as_of_date": sigmet.as_of_date,
                "state_key": sigmet.state_key,
                "divergence_regime": sigmet.divergence_regime,
                "operational_guidance": sigmet.operational_guidance,
                "pcr_value": sigmet.pcr_index_value,
                "pcr_d3": sigmet.pcr_velocity_3d,
            }

        except StrictDataPolicyError as spe:
            logger.warning(f"PCR Provider: Strict Data Policy notice — {spe}")
            return {"status": "skipped", "reason": str(spe)}
        except Exception as e:
            logger.error(f"PCR Provider computation failed: {e}")
            return {"status": "error", "error": str(e)}


# Register provider instance in global registry
register_provider(PCRProvider())
