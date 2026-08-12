"""
CNN Fear & Greed SPIndex (FG_SP) Vault Provider — Production Provider
======================================================================
Daily Vault provider for the 7 sub-indicators + FG_SP composite:

  1. FG_MOMENTUM  : SPY vs 125d MA % distance
  2. FG_STRENGTH  : SP500 52-week Highs/Lows ratio (log-transformed)
  3. FG_BREADTH   : SP500 McClellan Volume Summation Index
  4. FG_PUTCALL   : CBOE Put/Call Ratio (inverted)
  5. FG_VIX       : CBOE VIX Level (inverted)
  6. FG_JUNKBOND  : HYG/LQD Price Ratio
  7. FG_SAFEHAVEN : SPY vs TLT 20-day return differential

  Composite FG_SP : Mean of 0-100 percentile scores across all 7 sub-indicators over a 504-day rolling window.

EXECUTION ORDER: Runs in Tier 3b during daily data_vault_daemon execution.
Persists all 7 sub-indicators + FG_SP composite as OHLCV bars in market.ohlcv_bars.
"""
import logging
from datetime import datetime, UTC
import numpy as np

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.cnn_fg_breadth_calculator import (
    calculate_highs_lows_ratio,
    calculate_mcclellan_vsi,
)
from backend.modules.shared.domain.rules.cnn_fg_composite_calculator import (
    calculate_momentum,
    calculate_putcall,
    calculate_vix,
    calculate_junkbond,
    calculate_safehaven,
    percentile_score,
    calculate_composite,
    INVERTED_INDICATORS,
)

logger = logging.getLogger(__name__)

PERCENTILE_WINDOW = 504


class CnnFgSpProvider:
    """Vault provider for daily FG_SP (Fear & Greed SPIndex) + 7 sub-indicators."""

    name = "cnn_fg_sp"
    categories = ["cnn_fg_sp", "sentiment", "macro"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Calculate and persist all 7 F&G sub-indicators + FG_SP composite."""
        if _already_vaulted_today(store, "macro/cnn_fg_sp", "COMPOSITE"):
            logger.info("📊 CNN FG_SP already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Market-wide provider — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> dict:
        """Core daily computation & persistence."""
        try:
            now = datetime.now(UTC)

            # ── 1. Load SP500 closes/volumes for Strength & Breadth ──
            all_closes = store.load_all_latest_closes(days=400, sp500_only=True)
            all_volumes = store.load_all_latest_volumes(days=400, sp500_only=True)

            if not all_closes:
                logger.warning("FG_SP Provider: no SP500 OHLCV data available")
                return {"status": "error", "reason": "no_sp500_data"}

            hl_ratio = calculate_highs_lows_ratio(all_closes, lookback=252)
            mvsi = calculate_mcclellan_vsi(all_closes, all_volumes)
            n_constituents = len(all_closes)

            # Raw values dictionary for today
            raw_today = {}

            if hl_ratio is not None:
                # Log transform matching historical standard
                import math
                if hl_ratio > 0:
                    raw_today["FG_STRENGTH"] = round(math.log(hl_ratio), 4)
                else:
                    raw_today["FG_STRENGTH"] = 0.0

            if mvsi is not None:
                raw_today["FG_BREADTH"] = round(mvsi, 2)

            # ── 2. Load individual indicator series for the other 5 ──
            spy_bars = store.load_bars("SPY", "1d")
            vix_bars = store.load_bars("VIX", "1d")
            pcr_bars = store.load_bars("CBOE_PCR", "1d")
            hyg_bars = store.load_bars("HYG", "1d")
            lqd_bars = store.load_bars("LQD", "1d")
            tlt_bars = store.load_bars("TLT", "1d")

            if spy_bars is not None:
                raw_today["FG_MOMENTUM"] = calculate_momentum(spy_bars["close"].tolist(), 125)
            if pcr_bars is not None:
                raw_today["FG_PUTCALL"] = calculate_putcall(pcr_bars["close"].tolist())
            if vix_bars is not None:
                raw_today["FG_VIX"] = calculate_vix(vix_bars["close"].tolist())
            if hyg_bars is not None and lqd_bars is not None:
                raw_today["FG_JUNKBOND"] = calculate_junkbond(
                    hyg_bars["close"].tolist(), lqd_bars["close"].tolist()
                )
            if spy_bars is not None and tlt_bars is not None:
                raw_today["FG_SAFEHAVEN"] = calculate_safehaven(
                    spy_bars["close"].tolist(), tlt_bars["close"].tolist(), 20
                )

            # ── 3. Upsert raw sub-indicators for today ──
            for ticker, val in raw_today.items():
                if val is not None:
                    store.upsert_ticker_metadata(
                        ticker=ticker, sector="Sentiment",
                        industry="INDICATOR", market_cap_bucket=None,
                    )
                    vol = n_constituents if ticker in ("FG_STRENGTH", "FG_BREADTH") else 0
                    store.upsert_ohlcv_bar(
                        ticker=ticker, timeframe="1d", time=now,
                        open=float(val), high=float(val), low=float(val), close=float(val),
                        volume=vol,
                    )

            # ── 4. Compute 0-100 Percentile Scores using 504d history ──
            today_scores = {}
            for ticker in [
                "FG_MOMENTUM", "FG_STRENGTH", "FG_BREADTH",
                "FG_PUTCALL", "FG_VIX", "FG_JUNKBOND", "FG_SAFEHAVEN",
            ]:
                if ticker in raw_today and raw_today[ticker] is not None:
                    # Load historical values for percentile ranking
                    hist_bars = store.load_bars(ticker, "1d")
                    if hist_bars is not None and len(hist_bars) >= 30:
                        hist_vals = hist_bars["close"].iloc[-PERCENTILE_WINDOW:].tolist()
                        invert = ticker in INVERTED_INDICATORS
                        today_scores[ticker] = percentile_score(
                            raw_today[ticker], hist_vals, invert=invert
                        )

            # ── 5. Compute and Upsert Composite FG_SP ──
            composite_score = calculate_composite(today_scores)

            if composite_score is not None:
                store.upsert_ticker_metadata(
                    ticker="FG_SP", sector="Sentiment",
                    industry="INDICATOR", market_cap_bucket=None,
                )
                store.upsert_ohlcv_bar(
                    ticker="FG_SP", timeframe="1d", time=now,
                    open=float(composite_score), high=float(composite_score),
                    low=float(composite_score), close=float(composite_score),
                    volume=len(today_scores),
                )

            # Snapshot for idempotency
            snapshot = {
                "fg_sp_composite": composite_score,
                "sub_scores": today_scores,
                "raw_today": raw_today,
                "n_sub_indicators": len(today_scores),
                "timestamp": now.isoformat(),
            }
            store.save_mcp_snapshot("macro/cnn_fg_sp", "COMPOSITE", snapshot)

            score_str = f"{composite_score:.1f}" if composite_score is not None else "N/A"
            logger.info(
                f"📊 CNN FG_SP Provider: Composite={score_str} ({len(today_scores)}/7 sub-indicators scored)"
            )

            return {
                "status": "ok",
                "fg_sp_composite": composite_score,
                "n_sub_indicators": len(today_scores),
                "scores": today_scores,
            }

        except Exception as e:
            logger.warning(f"CNN FG_SP Provider vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(CnnFgSpProvider())
