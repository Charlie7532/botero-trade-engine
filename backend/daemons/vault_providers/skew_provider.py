"""
CBOE SKEW Index (Tail Risk) Vault Provider
==========================================
Vault provider for SKEW Market SIGMET & 3-Day Kinematic Velocity Telemetry.
Reads SKEW from Vault, generates authoritative MarketSIGMET, and persists:
  1. MCP Snapshot: mcp_snapshot("skew/sigmet", "MARKET")
  2. Stateful-First Regime Transitions: market.regime_states ("skew:sigmet:MARKET")

All inputs read from Vault — zero external API calls in the domain layer.
Follows Rules 13, 15, 16, 17, 18.
"""
import logging
from typing import Dict, Any, Optional

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state import PostgresRegimeStateAdapter
from backend.modules.entry_decision.domain.services.skew_sigmet_service import (
    get_skew_market_sigmet,
    StrictDataPolicyError,
)

logger = logging.getLogger(__name__)


class SkewProvider:
    """Vault provider for CBOE SKEW Index (Tail Risk) SIGMET and state transitions."""

    name = "skew"
    categories = ["skew", "cboe_skew"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Compute and persist SKEW Market SIGMET and regime state from Vault data."""
        if _already_vaulted_today(store, "skew/sigmet", "MARKET"):
            logger.info("📊 SKEW Market SIGMET already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """SKEW SIGMET is market-wide — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> Dict[str, Any]:
        """Core computation: read Vault → SIGMET service → persist snapshot & regime state."""
        try:
            # 1. Generate live authoritative Market SIGMET using zero-fallback policy
            sigmet = get_skew_market_sigmet()

            # 2. Persist MCP Snapshot ("skew/sigmet", "MARKET")
            store.save_mcp_snapshot("skew/sigmet", "MARKET", sigmet.to_dict())

            # 3. Stateful-First Regime State Persistence (Rules 15 & 16)
            try:
                regime_store = PostgresRegimeStateAdapter()

                state_keys = [
                    ("skew:sigmet:MARKET", sigmet.state_key),
                    ("skew:regime:MARKET", sigmet.divergence_regime),
                    ("skew:guidance:MARKET", sigmet.operational_guidance),
                ]

                for key, state_label in state_keys:
                    current = regime_store.get_current(key)
                    if current is None or current.current_state != state_label:
                        trigger_msg = f"SKEW={sigmet.skew_index_value:.2f}, d3={sigmet.skew_velocity_3d:+.2f}"
                        regime_store.commit_transition(key, state_label, trigger=trigger_msg)
                        logger.info(
                            f"🔄 RegimeState Transition [{key}]: "
                            f"{current.current_state if current else '(none)'} → {state_label} ({trigger_msg})"
                        )
                    else:
                        regime_store.increment_duration(key)

                regime_store.close()
            except Exception as e:
                logger.warning(f"SKEW Provider: Regime state persistence skipped: {e}")

            logger.info(
                f"📊 SKEW SIGMET Vaulted: State={sigmet.state_key} | "
                f"Regime={sigmet.divergence_regime} | Directive={sigmet.operational_guidance}"
            )

            return {
                "status": "ok",
                "sigmet_id": sigmet.sigmet_id,
                "as_of_date": sigmet.as_of_date,
                "state_key": sigmet.state_key,
                "divergence_regime": sigmet.divergence_regime,
                "operational_guidance": sigmet.operational_guidance,
                "skew_value": sigmet.skew_index_value,
                "skew_d3": sigmet.skew_velocity_3d,
            }

        except StrictDataPolicyError as spe:
            logger.warning(f"SKEW Provider: Strict Data Policy notice — {spe}")
            return {"status": "skipped", "reason": str(spe)}
        except Exception as e:
            logger.error(f"SKEW Provider computation failed: {e}")
            return {"status": "error", "error": str(e)}


register_provider(SkewProvider())
