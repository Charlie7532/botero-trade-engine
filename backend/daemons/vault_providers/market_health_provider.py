"""
Market Health Provider — Vault Provider

Computes the MarketHealthSnapshot from Vault data and persists
it as mcp_snapshot("market/health", "MARKET").

EXECUTION ORDER: MUST run AFTER breadth + fear_greed + ohlcv providers.
All inputs read from Vault — zero external API calls.
"""
import logging
from datetime import datetime, UTC

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class MarketHealthProvider:
    """Vault provider for Market Health Intelligence snapshot."""

    name = "market_health"
    categories = ["market_health"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Compute and persist MarketHealthSnapshot from Vault data."""
        if _already_vaulted_today(store, "market/health", "MARKET"):
            logger.info("🏥 Market Health already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Market health is market-wide — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> dict:
        """Core computation: read Vault → compositor → persist."""
        try:
            from backend.modules.market_health.domain.use_cases.compute_market_health import (
                compute_market_health,
            )
            from datetime import date, timedelta

            start = date.today() - timedelta(days=120)

            # ── Load all inputs from Vault ──
            s5fi = store.load_bars("S5FI", "1d", start=start)
            s5th = store.load_bars("S5TH", "1d", start=start)
            s5tw = store.load_bars("S5TW", "1d", start=start)
            fg = store.load_bars("FG", "1d", start=start)
            hyg = store.load_bars("HYG", "1d", start=start)
            tlt = store.load_bars("TLT", "1d", start=start)

            # VIX from ohlcv_bars (canonical ticker: VIX)
            vix = store.load_bars("VIX", "1d", start=start)

            # FRED macro snapshot
            fred = store.load_mcp_latest("macro/fred_real", "SUMMARY")
            if not fred:
                fred = store.load_mcp_latest("macro/fred", "SUMMARY")

            # Yields from ohlcv_bars (Rule 14 unified schema)
            tnx_df = store.load_bars("TNX", "1d", start=start)
            irx_df = store.load_bars("IRX", "1d", start=start)

            # Rotation snapshot (if available)
            rotation_phase = "UNKNOWN"
            dominant_rotation = "NEUTRAL"
            capitulation_level = 0
            rot_snap = store.load_mcp_latest("rotation/snapshot", "MARKET")
            if rot_snap and isinstance(rot_snap, dict):
                rotation_phase = rot_snap.get("cycle_phase", "UNKNOWN")
                dominant_rotation = rot_snap.get("dominant_rotation", "NEUTRAL")
                capitulation_level = rot_snap.get("capitulation_level", 0)

            # SPY 20d return for narrow market detection
            spy_pct = 0.0
            spy_df = store.load_bars("SPY", "1d", start=start)
            if spy_df is not None and len(spy_df) >= 20:
                spy_close = spy_df["close"]
                spy_pct = float(spy_close.iloc[-1] / spy_close.iloc[-20] - 1)

            # ── Compute ──
            snapshot = compute_market_health(
                s5fi_df=s5fi,
                s5th_df=s5th,
                s5tw_df=s5tw,
                fg_df=fg,
                hyg_df=hyg,
                tlt_df=tlt,
                vix_df=vix,
                yields_10y=tnx_df,
                yields_3m=irx_df,
                fred_snapshot=fred,
                rotation_phase=rotation_phase,
                dominant_rotation=dominant_rotation,
                capitulation_level=capitulation_level,
                spy_pct_change_20d=spy_pct,
            )

            # ── Inject Vol Regime (infra layer responsibility) ──
            # The compositor computes VIX z-score (domain). The provider
            # runs VolRegimeClassifier on SPY prices (cross-module, infra-ok).
            try:
                from backend.modules.entry_decision.domain.rules.vol_regime_gate import (
                    compute_vol_regime_snapshot,
                )
                vix_z = getattr(snapshot, "_vix_zscore", 0.0)
                if spy_df is not None and len(spy_df) >= 60:
                    regime = compute_vol_regime_snapshot(spy_df, vix_zscore=vix_z)
                    snapshot.vol_regime_quality = regime.quality_label
                    snapshot.vol_regime_speculative = regime.speculative_label
            except Exception as e:
                logger.debug(f"MH Provider: Vol regime injection skipped: {e}")

            # ── Persist ──
            store.save_mcp_snapshot("market/health", "MARKET", snapshot.to_dict())

            logger.info(
                f"🏥 Market Health: Conv={snapshot.convergence_score}/6 "
                f"{snapshot.convergence_direction} | "
                f"Cascade={snapshot.cascade_state} Vol={snapshot.vol_regime_quality} "
                f"Credit={snapshot.credit_regime} | "
                f"F&G={snapshot.fg_score:.0f} ({snapshot.fg_action})"
            )

            return {
                "status": "ok",
                "convergence_score": snapshot.convergence_score,
                "convergence_direction": snapshot.convergence_direction,
                "fg_action": snapshot.fg_action,
            }

        except Exception as e:
            logger.warning(f"Market Health computation failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(MarketHealthProvider())
