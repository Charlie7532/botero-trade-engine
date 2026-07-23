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

            # ── UW Enrichment: Sector Tide → G3 Flow Direction ──
            flow_direction = "NEUTRAL"
            try:
                _sectors = ["TECHNOLOGY", "FINANCIALS", "HEALTHCARE", "ENERGY", "CONSUMER CYCLICAL"]
                _net_flow = 0.0
                _sectors_found = 0
                for _sector in _sectors:
                    _tide = store.load_mcp_latest("uw/sector_tide", _sector)
                    if _tide and isinstance(_tide, list) and len(_tide) > 0:
                        # Sum last hour of net premium flow
                        _recent = _tide[-12:] if len(_tide) > 12 else _tide
                        for _bar in _recent:
                            _net_flow += float(_bar.get("close", 0) or 0)
                        _sectors_found += 1
                if _sectors_found >= 2:
                    if _net_flow > 1_000_000:
                        flow_direction = "BULLISH"
                    elif _net_flow < -1_000_000:
                        flow_direction = "BEARISH"
                    logger.debug(
                        f"MH Provider: sector_tide net_flow=${_net_flow:,.0f} → {flow_direction} "
                        f"({_sectors_found} sectors)"
                    )
            except Exception as e:
                logger.debug(f"MH Provider: sector_tide read skipped: {e}")

            # ── UW Enrichment: Vol Stats SPY → G2 IV Rank ──
            iv_rank_spy = None
            try:
                _vol_stats = store.load_mcp_latest("uw/vol_stats", "SPY")
                if _vol_stats and isinstance(_vol_stats, dict):
                    _iv_rank = float(_vol_stats.get("iv_rank", 0) or 0)
                    if _iv_rank > 0:
                        iv_rank_spy = _iv_rank
                        logger.debug(f"MH Provider: SPY IV Rank = {iv_rank_spy:.1f}")
            except Exception as e:
                logger.debug(f"MH Provider: vol_stats read skipped: {e}")

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
                flow_direction=flow_direction,
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

            # ── Stateful-First: Persist vol regime transitions (Rule 15-16) ──
            # Writer: this daemon. Readers: gates, risk managers, Oracle Trainer.
            try:
                from backend.modules.shared.infrastructure.postgres_regime_state import (
                    PostgresRegimeStateAdapter,
                )
                _regime_store = PostgresRegimeStateAdapter()

                for _key, _label in [
                    ("vol:quality:MARKET", snapshot.vol_regime_quality),
                    ("vol:speculative:MARKET", snapshot.vol_regime_speculative),
                ]:
                    _current = _regime_store.get_current(_key)
                    if _current is None or _current.current_state != _label:
                        # Regime changed (or first-ever) → commit transition
                        _trigger = f"VIX_Z={vix_z:.2f}" if 'vix_z' in dir() else None
                        _regime_store.commit_transition(
                            _key, _label, trigger=_trigger,
                        )
                        logger.info(
                            f"🔄 RegimeState: {_key} "
                            f"{_current.current_state if _current else '(none)'}→{_label}"
                        )
                    else:
                        # Same regime → increment duration
                        _regime_store.increment_duration(_key)

                _regime_store.close()
            except Exception as e:
                logger.debug(f"MH Provider: Regime state persistence skipped: {e}")

            # ── Calculate and persist Fear & Greed Breadth Index (FGBI) ──
            try:
                def_sectors = ["XLP", "XLU", "XLV"]
                gro_sectors = ["XLK", "XLY", "XLC"]
                
                def_vals = []
                for sec in def_sectors:
                    # Prefer Cap-Weighted (S5CAP), fallback to Equal-Weighted (S5)
                    bar = store.load_bars(f"S5CAP_{sec}_FI", "1d", limit=1)
                    if bar is None or bar.empty:
                        bar = store.load_bars(f"S5_{sec}_FI", "1d", limit=1)
                    if bar is not None and not bar.empty:
                        def_vals.append(float(bar["close"].iloc[-1]))
                
                gro_vals = []
                for sec in gro_sectors:
                    bar = store.load_bars(f"S5CAP_{sec}_FI", "1d", limit=1)
                    if bar is None or bar.empty:
                        bar = store.load_bars(f"S5_{sec}_FI", "1d", limit=1)
                    if bar is not None and not bar.empty:
                        gro_vals.append(float(bar["close"].iloc[-1]))
                
                if len(def_vals) == 3 and len(gro_vals) == 3:
                    fgbi_val = round((sum(def_vals)/3.0) - (sum(gro_vals)/3.0), 2)
                    store.upsert_ohlcv_bar(
                        ticker="FGBI", timeframe="1d", time=datetime.now(UTC),
                        open=fgbi_val, high=fgbi_val, low=fgbi_val, close=fgbi_val,
                        volume=0
                    )
                    logger.info(f"🏥 FGBI calculated and saved: {fgbi_val:+.2f}")
            except Exception as e:
                logger.warning(f"FGBI computation failed (non-critical): {e}")

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
