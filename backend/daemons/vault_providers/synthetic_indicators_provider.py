"""
Synthetic METAR Indicators Vault Provider
==========================================
Computes and persists the 3 synthetic METAR station indicators as pseudo-OHLCV
tickers in the Vault, so modules and the observatory can read them directly
via store.load_bars() instead of computing on-the-fly.

Indicators:
  1. CREDIT_RATIO    = HYG / TLT           (Credit stress ratio)
  2. YIELD_SPREAD    = TNX - IRX            (Yield curve spread: 10Y - 13W)
  3. ROTATION_INDEX  = z(XLY/XLP) + z(XLK/XLU)  (Sector rotation z-score)

Storage: open=high=low=close=value, volume=0 (Rule 14)
Midnight UTC timestamps enforced by TimescaleDataStore (Rule 18)

EXECUTION ORDER: MUST run AFTER ohlcv_provider (needs HYG, TLT, TNX, IRX,
XLY, XLP, XLK, XLU history).
"""
import logging
import math
from datetime import datetime, UTC, timedelta
from typing import Dict, Any

import pandas as pd
import numpy as np

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Rolling window for rotation z-score (annualized)
_ROTATION_WINDOW = 252


class SyntheticIndicatorsProvider:
    """Vault provider for the 3 synthetic METAR station indicators."""

    name = "synthetic_indicators"
    categories = ["synthetic_indicators", "credit_ratio", "yield_spread", "rotation_index"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Compute and persist all 3 synthetic indicators for today."""
        results = {}
        results["credit_ratio"] = self._compute_credit_ratio(store)
        results["yield_spread"] = self._compute_yield_spread(store)
        results["rotation_index"] = self._compute_rotation_index(store)
        return {"status": "ok", "indicators": results}

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """Synthetic indicators are market-wide — falls back to run_full."""
        return self.run_full(store)

    # ──────────────────────────────────────────────────────────────────
    # 1. CREDIT_RATIO = HYG / LQD
    # ──────────────────────────────────────────────────────────────────
    def _compute_credit_ratio(self, store: TimescaleDataStore) -> Dict[str, Any]:
        try:
            if _already_vaulted_today(store, "derived/credit_ratio", "MARKET"):
                logger.info("📊 CREDIT_RATIO already vaulted today — skipping")
                return {"status": "skipped"}

            start = (datetime.now(UTC) - timedelta(days=5)).date()
            hyg = store.load_bars("HYG", "1d", start=start)
            lqd = store.load_bars("LQD", "1d", start=start)

            if hyg is None or lqd is None or len(hyg) == 0 or len(lqd) == 0:
                return {"status": "error", "reason": "no_data"}

            hyg_last = float(hyg.sort_index().iloc[-1]["close"])
            lqd_last = float(lqd.sort_index().iloc[-1]["close"])
            credit_ratio = float(hyg_last / lqd_last)

            now = datetime.now(UTC)
            store.upsert_ohlcv_bar(
                ticker="CREDIT_RATIO",
                timeframe="1d",
                time=now,
                open=credit_ratio,
                high=credit_ratio,
                low=credit_ratio,
                close=credit_ratio,
                volume=0,
            )
            store.upsert_ticker_metadata(
                ticker="CREDIT_RATIO",
                sector="Credit",
                industry="INDICATOR",
                market_cap_bucket=None,
            )
            # Mark as vaulted today
            store.save_mcp_snapshot("derived/credit_ratio", "MARKET", {
                "value": credit_ratio,
                "hyg": hyg_last,
                "lqd": lqd_last,
            })
            logger.info(f"📊 CREDIT_RATIO vault: {credit_ratio:.4f} (HYG={hyg_last:.2f}, LQD={lqd_last:.2f})")
            return {"status": "ok", "value": credit_ratio}

        except Exception as e:
            logger.warning(f"CREDIT_RATIO vault failed: {e}")
            return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────
    # 2. YIELD_SPREAD = TNX - IRX
    # ──────────────────────────────────────────────────────────────────
    def _compute_yield_spread(self, store: TimescaleDataStore) -> Dict[str, Any]:
        try:
            if _already_vaulted_today(store, "derived/yield_spread", "MARKET"):
                logger.info("📊 YIELD_SPREAD already vaulted today — skipping")
                return {"status": "skipped"}

            start = (datetime.now(UTC) - timedelta(days=5)).date()
            tnx = store.load_bars("TNX", "1d", start=start)
            irx = store.load_bars("IRX", "1d", start=start)

            if tnx is None or irx is None or len(tnx) == 0 or len(irx) == 0:
                return {"status": "error", "reason": "no_data"}

            tnx_last = float(tnx.sort_index().iloc[-1]["close"])
            irx_last = float(irx.sort_index().iloc[-1]["close"])
            yield_spread = float(tnx_last - irx_last)

            now = datetime.now(UTC)
            store.upsert_ohlcv_bar(
                ticker="YIELD_SPREAD",
                timeframe="1d",
                time=now,
                open=yield_spread,
                high=yield_spread,
                low=yield_spread,
                close=yield_spread,
                volume=0,
            )
            store.upsert_ticker_metadata(
                ticker="YIELD_SPREAD",
                sector="Yields",
                industry="INDICATOR",
                market_cap_bucket=None,
            )
            store.save_mcp_snapshot("derived/yield_spread", "MARKET", {
                "value": yield_spread,
                "tnx": tnx_last,
                "irx": irx_last,
            })
            logger.info(f"📊 YIELD_SPREAD vault: {yield_spread:.2f}% (TNX={tnx_last:.2f}%, IRX={irx_last:.2f}%)")
            return {"status": "ok", "value": yield_spread}

        except Exception as e:
            logger.warning(f"YIELD_SPREAD vault failed: {e}")
            return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────
    # 3. ROTATION_INDEX = z(XLY/XLP) + z(XLK/XLU)
    # ──────────────────────────────────────────────────────────────────
    def _compute_rotation_index(self, store: TimescaleDataStore) -> Dict[str, Any]:
        try:
            if _already_vaulted_today(store, "derived/rotation_index", "MARKET"):
                logger.info("📊 ROTATION_INDEX already vaulted today — skipping")
                return {"status": "skipped"}

            # Need ~260 trading days for 252-day rolling z-score
            start = (datetime.now(UTC) - timedelta(days=400)).date()
            xly = store.load_bars("XLY", "1d", start=start)
            xlp = store.load_bars("XLP", "1d", start=start)
            xlk = store.load_bars("XLK", "1d", start=start)
            xlu = store.load_bars("XLU", "1d", start=start)

            for name, df in [("XLY", xly), ("XLP", xlp), ("XLK", xlk), ("XLU", xlu)]:
                if df is None or len(df) < _ROTATION_WINDOW:
                    return {"status": "error", "reason": f"{name}_insufficient_history"}

            m = pd.concat([
                xly["close"].rename("xly"),
                xlp["close"].rename("xlp"),
                xlk["close"].rename("xlk"),
                xlu["close"].rename("xlu"),
            ], axis=1).dropna().sort_index()

            r1 = m["xly"] / m["xlp"]
            r2 = m["xlk"] / m["xlu"]
            z1 = (r1 - r1.rolling(_ROTATION_WINDOW, min_periods=20).mean()) / r1.rolling(_ROTATION_WINDOW, min_periods=20).std()
            z2 = (r2 - r2.rolling(_ROTATION_WINDOW, min_periods=20).mean()) / r2.rolling(_ROTATION_WINDOW, min_periods=20).std()
            rotation_series = (z1 + z2).fillna(0.0)

            rotation_value = float(rotation_series.iloc[-1])

            now = datetime.now(UTC)
            store.upsert_ohlcv_bar(
                ticker="ROTATION_INDEX",
                timeframe="1d",
                time=now,
                open=rotation_value,
                high=rotation_value,
                low=rotation_value,
                close=rotation_value,
                volume=0,
            )
            store.upsert_ticker_metadata(
                ticker="ROTATION_INDEX",
                sector="Rotation",
                industry="INDICATOR",
                market_cap_bucket=None,
            )
            store.save_mcp_snapshot("derived/rotation_index", "MARKET", {
                "value": rotation_value,
            })
            logger.info(f"📊 ROTATION_INDEX vault: {rotation_value:+.4f}")
            return {"status": "ok", "value": rotation_value}

        except Exception as e:
            logger.warning(f"ROTATION_INDEX vault failed: {e}")
            return {"status": "error", "error": str(e)}


register_provider(SyntheticIndicatorsProvider())
