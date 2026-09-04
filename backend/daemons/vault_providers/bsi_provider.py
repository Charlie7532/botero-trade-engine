"""
Breadth Shock Index (BSI / S5TW) Vault Provider
==============================================
Vault provider for BSI (S5TW Tactical Breadth Shock) Market METAR & 3-Day Kinematic Velocity Telemetry.
Reads S5TW breadth indicator from Vault, generates authoritative MarketMETAR, and persists:
  1. MCP Snapshot: mcp_snapshot("bsi/sigmet", "MARKET")
  2. Stateful-First Regime Transitions: market.regime_states ("bsi:entry_decision:MARKET")

All inputs read from Vault — zero external API calls in the domain layer.
Follows Rules 13, 15, 16, 17, 18.
"""
import logging
from typing import Dict, Any, Optional
from datetime import timedelta, datetime, UTC
import pandas as pd

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state import PostgresRegimeStateAdapter
from backend.modules.entry_decision.domain.services.bsi_metar_service import (
    get_bsi_market_metar,
    StrictDataPolicyError,
)

logger = logging.getLogger(__name__)


class BSIProvider:
    """Vault provider for Breadth Shock Index METAR and state transitions."""

    name = "bsi"
    categories = ["bsi", "s5tw", "breadth_shock"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Compute and persist BSI Market METAR, bars, and regime state from Vault data."""
        last_bsi = store.bars_last_date("BSI", "1d")
        last_s5tw = store.bars_last_date("S5TW", "1d")

        # Only skip if already vaulted today AND BSI bars are fully synchronized with S5TW
        if last_bsi and last_s5tw and last_bsi >= last_s5tw:
            if _already_vaulted_today(store, "bsi/sigmet", "MARKET"):
                logger.info("📊 BSI Market METAR already vaulted today — skipping")
                return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """BSI METAR is market-wide — falls back to run_full."""
        return self._compute(store)

    def _sync_s5tw_to_bsi(self, store: TimescaleDataStore) -> int:
        """Ensure BSI OHLCV bars in market.ohlcv_bars match S5TW breadth series."""
        last_bsi = store.bars_last_date("BSI", "1d")
        last_s5tw = store.bars_last_date("S5TW", "1d")

        if not last_s5tw:
            return 0

        if last_bsi and last_bsi >= last_s5tw:
            return 0

        start = (last_bsi + timedelta(days=1)) if last_bsi else None
        s5tw_bars = store.load_bars("S5TW", "1d", start=start)
        if s5tw_bars is None or s5tw_bars.empty:
            return 0

        df_sync = pd.DataFrame({
            "open": s5tw_bars["close"],
            "high": s5tw_bars["close"],
            "low": s5tw_bars["close"],
            "close": s5tw_bars["close"],
            "volume": 0,
        }, index=s5tw_bars.index)
        store.save_bars("BSI", "1d", df_sync)
        store.upsert_ticker_metadata(ticker="BSI", sector="Breadth", industry="INDICATOR")
        logger.info(f"📊 BSI synced {len(df_sync)} bars from S5TW (up to {last_s5tw})")
        return len(df_sync)

    def _compute(self, store: TimescaleDataStore) -> Dict[str, Any]:
        """Core computation: sync bars → METAR service → persist snapshot & regime state."""
        try:
            # 1. Ensure BSI OHLCV bars are synchronized from S5TW
            synced_bars = self._sync_s5tw_to_bsi(store)

            # 2. Generate live authoritative Market METAR
            sigmet = get_bsi_market_metar()

            # 3. Persist latest BSI bar to market.ohlcv_bars
            bsi_val = float(sigmet.bsi_value)
            time_val = pd.to_datetime(sigmet.as_of_date).tz_localize("UTC")
            store.upsert_ohlcv_bar(
                ticker="BSI",
                timeframe="1d",
                time=time_val,
                open=bsi_val,
                high=bsi_val,
                low=bsi_val,
                close=bsi_val,
                volume=0,
            )
            store.upsert_ticker_metadata(ticker="BSI", sector="Breadth", industry="INDICATOR")

            # 4. Save MCP snapshot
            store.save_mcp_snapshot("bsi/sigmet", "MARKET", sigmet.to_dict())

            # 5. Save regime states
            try:
                regime_store = PostgresRegimeStateAdapter()

                state_keys = [
                    ("bsi:entry_decision:MARKET", sigmet.state_key),
                    ("bsi:regime:MARKET", sigmet.divergence_regime),
                    ("bsi:guidance:MARKET", sigmet.operational_guidance),
                ]

                for key, state_label in state_keys:
                    current = regime_store.get_current(key)
                    if current is None or current.current_state != state_label:
                        trigger_msg = f"S5TW={sigmet.bsi_value:.2f}%, d3={sigmet.bsi_velocity_3d:+.2f}pp"
                        regime_store.commit_transition(key, state_label, trigger=trigger_msg)
                    else:
                        regime_store.increment_duration(key)

                regime_store.close()
            except Exception as e:
                logger.warning(f"BSI Provider: Regime state persistence skipped: {e}")

            logger.info(
                f"📊 BSI METAR Vaulted: State={sigmet.state_key} | "
                f"Regime={sigmet.divergence_regime} | Directive={sigmet.operational_guidance}"
            )

            return {
                "status": "ok",
                "metar_id": sigmet.metar_id,
                "as_of_date": sigmet.as_of_date,
                "state_key": sigmet.state_key,
                "divergence_regime": sigmet.divergence_regime,
                "operational_guidance": sigmet.operational_guidance,
                "bsi_value": sigmet.bsi_value,
                "bsi_d3": sigmet.bsi_velocity_3d,
            }

        except StrictDataPolicyError as spe:
            logger.warning(f"BSI Provider: Strict Data Policy notice — {spe}")
            return {"status": "skipped", "reason": str(spe)}
        except Exception as e:
            logger.error(f"BSI Provider computation failed: {e}")
            return {"status": "error", "error": str(e)}


register_provider(BSIProvider())
