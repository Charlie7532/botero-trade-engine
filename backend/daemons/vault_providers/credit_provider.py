"""
High Yield Corporate Credit Stress (CREDIT) Vault Provider
===========================================================
Vault provider for Credit Stress Market METAR & 3-Day Kinematic Velocity Telemetry.
Reads HYG/TLT credit stress ratio from Vault, generates authoritative MarketMETAR, and persists:
  1. MCP Snapshot: mcp_snapshot("credit/sigmet", "MARKET")
  2. Stateful-First Regime Transitions: market.regime_states ("credit:entry_decision:MARKET")

All inputs read from Vault — zero external API calls in the domain layer.
Follows Rules 13, 15, 16, 17, 18.
"""
import logging
from typing import Dict, Any, Optional

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state import PostgresRegimeStateAdapter
from backend.modules.entry_decision.domain.services.credit_metar_service import (
    get_credit_market_metar,
    StrictDataPolicyError,
)

logger = logging.getLogger(__name__)


class CreditProvider:
    """Vault provider for Credit Stress Index METAR and state transitions."""

    name = "credit"
    categories = ["credit", "hyg_tlt"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Compute and persist Credit Stress Market METAR and regime state from Vault data."""
        if _already_vaulted_today(store, "credit/sigmet", "MARKET"):
            logger.info("📊 Credit Stress Market METAR already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """Credit METAR is market-wide — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> Dict[str, Any]:
        """Core computation: read Vault → METAR service → persist snapshot & regime state."""
        try:
            sigmet = get_credit_market_metar()
            store.save_mcp_snapshot("credit/sigmet", "MARKET", sigmet.to_dict())

            try:
                regime_store = PostgresRegimeStateAdapter()

                state_keys = [
                    ("credit:entry_decision:MARKET", sigmet.state_key),
                    ("credit:regime:MARKET", sigmet.divergence_regime),
                    ("credit:guidance:MARKET", sigmet.operational_guidance),
                ]

                for key, state_label in state_keys:
                    current = regime_store.get_current(key)
                    if current is None or current.current_state != state_label:
                        trigger_msg = f"CREDIT={sigmet.credit_ratio_value:.4f}, d3={sigmet.credit_velocity_3d:+.4f}"
                        regime_store.commit_transition(key, state_label, trigger=trigger_msg)
                    else:
                        regime_store.increment_duration(key)

                regime_store.close()
            except Exception as e:
                logger.warning(f"Credit Provider: Regime state persistence skipped: {e}")

            logger.info(
                f"📊 Credit METAR Vaulted: State={sigmet.state_key} | "
                f"Regime={sigmet.divergence_regime} | Directive={sigmet.operational_guidance}"
            )

            return {
                "status": "ok",
                "metar_id": sigmet.metar_id,
                "as_of_date": sigmet.as_of_date,
                "state_key": sigmet.state_key,
                "divergence_regime": sigmet.divergence_regime,
                "operational_guidance": sigmet.operational_guidance,
                "credit_value": sigmet.credit_ratio_value,
                "credit_d3": sigmet.credit_velocity_3d,
            }

        except StrictDataPolicyError as spe:
            logger.warning(f"Credit Provider: Strict Data Policy notice — {spe}")
            return {"status": "skipped", "reason": str(spe)}
        except Exception as e:
            logger.error(f"Credit Provider computation failed: {e}")
            return {"status": "error", "error": str(e)}


register_provider(CreditProvider())
