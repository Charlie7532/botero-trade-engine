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
        """Fetch latest CBOE official daily PCR bars, then compute and persist METAR & regime state."""
        sync_res = self._sync_cboe_bars(store)
        
        # If no new bars were added and already vaulted today, skip computation
        if sync_res.get("new_bars", 0) == 0 and _already_vaulted_today(store, "pcr/sigmet", "MARKET"):
            logger.info("📊 PCR Market METAR already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today", "sync": sync_res}

        res = self._compute(store)
        res["sync"] = sync_res
        return res

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """PCR METAR is market-wide — falls back to run_full."""
        return self.run_full(store)

    def _sync_cboe_bars(self, store: TimescaleDataStore) -> Dict[str, Any]:
        """Fetch and persist official daily CBOE Put/Call Ratio bars directly from CBOE."""
        import requests
        import re
        import json
        import pandas as pd
        from datetime import datetime, UTC, timedelta

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'RSC': '1',
        }

        def fetch_cboe_daily(date_str: str) -> Optional[tuple]:
            url = f"https://www.cboe.com/us/options/market_statistics/daily/?dt={date_str}"
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code != 200:
                    return None
                m_ratios = re.search(r'\"ratios\":(\[\{.*?\}\])', r.text)
                if not m_ratios:
                    return None
                m_dt = re.search(r'\"selectedDate\":\"([0-9-]+)\"', r.text)
                actual_date = m_dt.group(1) if m_dt else date_str
                if actual_date != date_str:
                    return None
                ratios = json.loads(m_ratios.group(1))
                ratio_map = {item['name']: float(item['value']) for item in ratios if 'name' in item and 'value' in item}
                return actual_date, ratio_map
            except Exception as e:
                logger.warning(f"Failed to fetch CBOE data for {date_str}: {e}")
                return None

        try:
            last_date = store.bars_last_date("CBOE_PCR", "1d")
            now_utc = datetime.now(UTC)
            ref_date = now_utc.date()

            if not last_date:
                start_date = ref_date - timedelta(days=30)
            else:
                last_dt = last_date.date() if isinstance(last_date, datetime) else last_date
                start_date = last_dt + timedelta(days=1)

            if start_date > ref_date:
                return {"status": "ok", "new_bars": 0}

            bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start_date, ref_date)]
            if not bdays:
                return {"status": "ok", "new_bars": 0}

            pcr_rows = []
            cpce_rows = []
            for d in bdays:
                res = fetch_cboe_daily(d)
                if res:
                    adate, rmap = res
                    tot = rmap.get("TOTAL PUT/CALL RATIO")
                    eq = rmap.get("EQUITY PUT/CALL RATIO")
                    ts = pd.to_datetime(adate).tz_localize("UTC")
                    if tot is not None:
                        pcr_rows.append({"time": ts, "open": tot, "high": tot, "low": tot, "close": tot, "volume": 0})
                    if eq is not None:
                        cpce_rows.append({"time": ts, "open": eq, "high": eq, "low": eq, "close": eq, "volume": 0})

            new_count = 0
            if pcr_rows:
                df_pcr = pd.DataFrame(pcr_rows).set_index("time")
                store.save_bars("CBOE_PCR", "1d", df_pcr)
                store.upsert_ticker_metadata(ticker="CBOE_PCR", sector="Options", industry="INDICATOR")
                new_count = len(df_pcr)

            if cpce_rows:
                df_cpce = pd.DataFrame(cpce_rows).set_index("time")
                store.save_bars("CBOE_CPCE", "1d", df_cpce)
                store.upsert_ticker_metadata(ticker="CBOE_CPCE", sector="Options", industry="INDICATOR")

            if new_count > 0:
                logger.info(f"📊 CBOE_PCR vault: {new_count} new bars saved from official CBOE feed")

            return {"status": "ok", "new_bars": new_count}
        except Exception as e:
            logger.error(f"CBOE daily sync failed: {e}")
            return {"status": "error", "error": str(e), "new_bars": 0}

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
